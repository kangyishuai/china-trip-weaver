from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "plugins" / "china-trip-weaver" / "src"
sys.path.insert(0, str(SRC))

from china_trip_weaver.clock import FixedClock
from china_trip_weaver.contracts import ProviderRequest
from china_trip_weaver.credentials import resolve_credentials
from china_trip_weaver.flyai_inventory import FlyAIBackend
from china_trip_weaver.planning import RailBackend, plan_trip
from china_trip_weaver.providers.base import ContractMismatch, ProviderContext
from china_trip_weaver.providers.flyai_cli import FlyAISubprocessTransport
from china_trip_weaver.providers.variflight import VariFlightAdapter
from china_trip_weaver.providers.variflight_mcp import VariFlightMCPTransport
from china_trip_weaver.variflight_enrichment import VariFlightBackend


SERVER = ROOT / "tests" / "fixtures" / "variflight_mcp_server.py"
FLYAI_SERVER = ROOT / "tests" / "fixtures" / "flyai_cli_server.py"
E2E = ROOT / "tests" / "fixtures" / "e2e" / "beijing-shanghai-3d"
CLOCK = FixedClock.from_iso("2026-09-03T23:30:00+08:00")


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def credentials(configured):
    environment = {"VARIFLIGHT_API_KEY": "ctw-canary-variflight-live-not-real"} if configured else {}
    return resolve_credentials(environment, ROOT / ".tmp" / "variflight-live-no-file")


def request(action, subject_ref="leg-flight"):
    parameters = {
        "action": action,
        "date": "2026-09-10",
    }
    if action == "search":
        parameters.update({
            "dep_city": "BJS",
            "arr_city": "SHA",
            "subject_refs_by_service": {"XX1001": subject_ref},
        })
    else:
        parameters.update({"flight_no": "XX1001", "subject_ref": subject_ref})
    return ProviderRequest(
        request_id="variflight-test-" + action,
        capability="flight",
        parameters=parameters,
        deadline_ms=2000,
        as_of="2026-09-10",
        cache_policy="bypass",
        trace={"stage": "test"},
    )


class VariFlightLiveTests(unittest.TestCase):
    def transport(self, folder, resolved, mode):
        return VariFlightMCPTransport(
            resolved,
            cache_dir=Path(folder) / "npm-cache",
            temp_root=Path(folder) / "variflight-home",
            command=(sys.executable, str(SERVER), mode),
            cwd=ROOT,
        )

    def test_keyless_probe_lists_nine_tools_and_never_calls_business(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            resolved = credentials(False)
            transport = self.transport(temporary, resolved, "no-key")
            backend = VariFlightBackend("auto", resolved, transport)
            flight = {
                "leg_id": "leg-flight", "travel_mode": "flight", "from_ref": "city-beijing",
                "to_ref": "city-shanghai", "depart_at": "2026-09-10T22:00:00+08:00",
                "service_number": "XX1001", "claim_ids": [],
            }
            route = SimpleNamespace(
                from_place={"name": "北京", "ref_id": "city-beijing"},
                to_place={"name": "上海", "ref_id": "city-shanghai"},
                travel_date="2026-09-10",
            )
            result = backend.enrich([flight], [route], CLOCK)
        self.assertEqual("missing", result.health["status"])
        self.assertIn("tools=9", result.health["reason"])
        self.assertIn("business_calls=0", result.health["reason"])
        self.assertEqual(1, transport.probe_calls)
        self.assertEqual(0, transport.business_calls)

    def test_keyed_search_and_comfort_emit_attached_claims_with_redacted_stderr(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            resolved = credentials(True)
            transport = self.transport(temporary, resolved, "require-key")
            context = ProviderContext(CLOCK, resolved, transport)
            search = VariFlightAdapter().query(request("search"), context)
            comfort = VariFlightAdapter().query(request("comfort"), context)
        self.assertIsNone(search.error_class)
        self.assertIsNone(comfort.error_class)
        self.assertEqual("/status", search.claims[0]["field_path"])
        self.assertEqual("计划", search.claims[0]["value"]["state"])
        self.assertEqual("/comfort", comfort.claims[0]["field_path"])
        self.assertEqual("示例舒适", comfort.claims[0]["value"]["seat_width"])
        self.assertEqual("示例餐食", comfort.claims[0]["value"]["food"])
        diagnostics = "\n".join(transport.last_stderr)
        self.assertIn("[REDACTED]", diagnostics)
        self.assertNotIn(resolved.get("VARIFLIGHT_API_KEY"), diagnostics)
        self.assertEqual(2, transport.business_calls)

    def test_independent_search_emits_price_less_verify_on_click_candidate(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            resolved = credentials(True)
            transport = self.transport(temporary, resolved, "require-key")
            backend = VariFlightBackend("auto", resolved, transport)
            route = SimpleNamespace(
                from_place={"name": "北京", "ref_id": "city-beijing"},
                to_place={"name": "上海", "ref_id": "city-shanghai"},
                travel_date="2026-09-10",
            )
            result = backend.enrich([], [route], CLOCK)
        self.assertEqual(1, len(result.flights))
        candidate = result.flights[0]
        self.assertEqual("variflight", candidate["provider"])
        self.assertEqual("XX1001", candidate["service_number"])
        self.assertEqual(120, candidate["duration_minutes"])
        self.assertIsNone(candidate["price"]["amount"])
        self.assertEqual("verify-on-click", candidate["price"]["price_type"])
        self.assertEqual("ready", result.health["status"])
        self.assertIn("candidates=1", result.health["reason"])
        self.assertEqual(2, transport.business_calls)

    def test_tool_fingerprint_drift_fails_closed(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            resolved = credentials(False)
            transport = self.transport(temporary, resolved, "wrong-tools")
            with self.assertRaises(ContractMismatch):
                transport.probe(2)

    def test_full_plan_attaches_status_and_comfort_to_flyai_comparisons(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            folder = Path(temporary)
            flyai_credentials = resolve_credentials({}, folder / "no-flyai-key")
            flyai_transport = FlyAISubprocessTransport(
                flyai_credentials,
                cache_dir=folder / "flyai-npm-cache",
                temp_root=folder / "flyai-home",
                command=(sys.executable, str(FLYAI_SERVER), "normal"),
                cwd=ROOT,
            )
            flyai = FlyAIBackend("live", flyai_credentials, flyai_transport)
            variflight_credentials = credentials(True)
            variflight_transport = self.transport(folder, variflight_credentials, "require-key")
            variflight = VariFlightBackend("auto", variflight_credentials, variflight_transport)
            rail = RailBackend.from_spec("fixture:" + str(E2E / "rail.json"), ROOT)
            result = plan_trip(
                load(E2E / "request.json"),
                load(E2E / "candidates.json"),
                CLOCK,
                rail,
                flyai_backend=flyai,
                variflight_backend=variflight,
            )
        vf_claims = [item for item in result.trip["claims"] if item["provider"] == "variflight"]
        self.assertGreaterEqual(len(vf_claims), 2)
        self.assertIn("/status", {item["field_path"] for item in vf_claims})
        self.assertIn("/comfort", {item["field_path"] for item in vf_claims})
        health = next(item for item in result.trip["provider_health"] if item["provider"] == "variflight")
        self.assertEqual("ready", health["status"])
        self.assertEqual("live", health["mode"])
        claim_ids = {item["claim_id"] for item in vf_claims}
        enriched = [
            item for item in result.trip["transport_legs"]
            if item["travel_mode"] == "flight" and claim_ids.intersection(item["claim_ids"])
        ]
        self.assertTrue(enriched)


if __name__ == "__main__":
    unittest.main()
