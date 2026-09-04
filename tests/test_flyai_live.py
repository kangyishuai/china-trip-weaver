from __future__ import annotations

import os
import json
import sys
import tempfile
import unittest
import subprocess
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "plugins" / "china-trip-weaver" / "src"
sys.path.insert(0, str(SRC))

from china_trip_weaver.clock import FixedClock
from china_trip_weaver.contracts import ProviderRequest
from china_trip_weaver.credentials import resolve_credentials
from china_trip_weaver.flyai_inventory import FlyAIBackend
from china_trip_weaver.planning import RailBackend, plan_trip
from china_trip_weaver.providers.base import ContractMismatch, ProviderContext, ProviderTimeout
from china_trip_weaver.providers.flyai import FlyAIAdapter
from china_trip_weaver.providers.flyai_cli import FlyAISubprocessTransport


SERVER = ROOT / "tests" / "fixtures" / "flyai_cli_server.py"
CLOCK = FixedClock.from_iso("2026-09-03T23:05:00+08:00")
E2E = ROOT / "tests" / "fixtures" / "e2e" / "beijing-shanghai-3d"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def request(capability):
    if capability == "lodging":
        parameters = {"city": "上海", "check_in": "2026-09-10", "check_out": "2026-09-11"}
    else:
        parameters = {
            "origin": "北京", "destination": "上海", "date": "2026-09-10",
            "from_ref": "city-beijing", "to_ref": "city-shanghai",
        }
    return ProviderRequest(
        request_id="flyai-live-test",
        capability=capability,
        parameters=parameters,
        deadline_ms=2000,
        as_of="2026-09-10",
        cache_policy="bypass",
        trace={"stage": "test"},
    )


class FlyAISubprocessTests(unittest.TestCase):
    def make_transport(self, folder, credentials, mode="normal"):
        return FlyAISubprocessTransport(
            credentials,
            cache_dir=Path(folder) / "npm-cache",
            temp_root=Path(folder) / "flyai-home",
            command=(sys.executable, str(SERVER), mode),
            cwd=ROOT,
        )

    def test_provider_only_environment_constant_argv_and_redacted_stderr(self):
        inherited = {
            "FLYAI_API_KEY": "ctw-canary-flyai-child-not-real",
            "AMAP_WEBSERVICE_KEY": "ctw-canary-amap-leak-not-real",
            "VARIFLIGHT_API_KEY": "ctw-canary-variflight-leak-not-real",
            "ANYSEARCH_API_KEY": "ctw-canary-anysearch-leak-not-real",
            "UNRELATED_TOKEN": "ctw-canary-unrelated-leak-not-real",
        }
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            resolved = resolve_credentials(inherited, Path(temporary) / "missing")
            transport = self.make_transport(temporary, resolved, "require-key")
            context = ProviderContext(CLOCK, resolved, transport)
            with mock.patch.dict(os.environ, inherited, clear=False):
                result = FlyAIAdapter().query(request("lodging"), context)
        self.assertIsNone(result.error_class)
        self.assertEqual(1, len(result.normalized_items))
        lodging = result.normalized_items[0]
        self.assertIsNone(lodging["price"]["amount"])
        self.assertEqual("verify-on-click", lodging["price"]["price_type"])
        self.assertEqual("provider-unknown", lodging["coordinates"]["source_crs"])
        self.assertIsNone(lodging["coordinates"]["wgs84"])
        self.assertIsNone(lodging["coordinates"]["gcj02"])
        argv = " ".join(part for call in transport.argv_history for part in call)
        self.assertNotIn(inherited["FLYAI_API_KEY"], argv)
        diagnostics = "\n".join(transport.last_stderr)
        self.assertIn("[REDACTED]", diagnostics)
        self.assertNotIn(inherited["FLYAI_API_KEY"], diagnostics)
        self.assertEqual(1, transport.calls)
        self.assertEqual(2, transport.probe_calls)

    def test_keyless_flight_uses_provider_field_names_and_numeric_string_price(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            resolved = resolve_credentials({}, Path(temporary) / "missing")
            transport = self.make_transport(temporary, resolved)
            context = ProviderContext(CLOCK, resolved, transport)
            result = FlyAIAdapter().query(request("flight"), context)
        self.assertIsNone(result.error_class)
        leg = result.normalized_items[0]
        self.assertEqual("XX1001", leg["service_number"])
        self.assertEqual("2026-09-10T10:00:00+08:00", leg["depart_at"])
        self.assertEqual("2026-09-10T12:00:00+08:00", leg["arrive_at"])
        self.assertEqual(120, leg["duration_minutes"])
        self.assertEqual(1001.0, leg["price"]["amount"])
        self.assertEqual("live", leg["price"]["price_type"])

    def test_root_and_command_help_drift_fail_closed(self):
        for mode in ("bad-root-help", "bad-command-help"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
                resolved = resolve_credentials({}, Path(temporary) / "missing")
                transport = self.make_transport(temporary, resolved, mode)
                with self.assertRaises(ContractMismatch):
                    transport.execute("flyai", request("lodging"))

    def test_absolute_deadline_terminates_slow_child(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            resolved = resolve_credentials({}, Path(temporary) / "missing")
            transport = self.make_transport(temporary, resolved, "slow")
            short = ProviderRequest(
                request_id="flyai-timeout",
                capability="lodging",
                parameters={"city": "上海", "check_in": "2026-09-10", "check_out": "2026-09-11"},
                deadline_ms=100,
                as_of="2026-09-10",
                cache_policy="bypass",
                trace={"stage": "test"},
            )
            with self.assertRaises(ProviderTimeout):
                transport.execute("flyai", short)

    def test_item_list_shape_drift_is_contract_mismatch(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            resolved = resolve_credentials({}, Path(temporary) / "missing")
            transport = self.make_transport(temporary, resolved, "wrong-shape")
            result = FlyAIAdapter().query(request("lodging"), ProviderContext(CLOCK, resolved, transport))
        self.assertEqual("contract_mismatch", result.error_class)
        self.assertEqual((), result.normalized_items)

    def test_node_preload_redirects_homedir_without_home_variable(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            resolved = resolve_credentials({}, Path(temporary) / "missing")
            transport = self.make_transport(temporary, resolved)
            environment = transport._environment()
            self.assertNotIn("HOME", environment)
            command = subprocess.run(
                ["node", "-e", "process.stdout.write(require('node:os').homedir())"],
                env=environment,
                text=True,
                capture_output=True,
                timeout=5,
            )
            self.assertEqual(0, command.returncode, command.stderr)
            self.assertEqual(str((Path(temporary) / "flyai-home" / "home").resolve()), command.stdout)

    def test_live_plan_replaces_static_lodging_and_adds_unscheduled_flight_comparisons(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            resolved = resolve_credentials({}, Path(temporary) / "missing")
            transport = self.make_transport(temporary, resolved)
            flyai = FlyAIBackend("live", resolved, transport)
            rail = RailBackend.from_spec("fixture:" + str(E2E / "rail.json"), ROOT)
            result = plan_trip(
                load(E2E / "request.json"),
                load(E2E / "candidates.json"),
                CLOCK,
                rail,
                flyai_backend=flyai,
            )
        health = next(item for item in result.trip["provider_health"] if item["provider"] == "flyai")
        self.assertEqual("ready", health["status"])
        self.assertEqual("live", health["mode"])
        self.assertEqual(1, len(result.trip["lodgings"]))
        self.assertEqual("verify-on-click", result.trip["lodgings"][0]["price"]["price_type"])
        flights = [item for item in result.trip["transport_legs"] if item["travel_mode"] == "flight"]
        self.assertEqual(2, len(flights))
        scheduled_refs = {slot["ref_id"] for day in result.trip["days"] for slot in day["slots"]}
        self.assertTrue(all(item["leg_id"] not in scheduled_refs for item in flights))
        self.assertEqual(3, transport.calls)
        self.assertEqual(3, transport.probe_calls)
        self.assertEqual(3, len([item for item in result.business_calls if item.startswith("flyai.")]))


if __name__ == "__main__":
    unittest.main()
