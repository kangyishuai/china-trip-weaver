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
from china_trip_weaver.cli import _parser
from china_trip_weaver.providers.base import ContractMismatch, ProviderContext, ProviderTimeout, ReplayTransport
from china_trip_weaver.providers.flyai import FlyAIAdapter
from china_trip_weaver.providers.flyai_cli import FlyAISubprocessTransport


SERVER = ROOT / "tests" / "fixtures" / "flyai_cli_server.py"
CLOCK = FixedClock.from_iso("2026-09-03T23:05:00+08:00")
E2E = ROOT / "tests" / "fixtures" / "e2e" / "beijing-shanghai-3d"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def g2_flyai_transport():
    fixture = load(ROOT / "tests" / "fixtures" / "providers" / "flyai" / "g2" / "unverified_room_context.json")
    return fixture, {
        "kind": "response",
        "status_code": 200,
        "headers": {},
        "body": {
            "cliVersion": "1.0.16",
            "commands": ["search-hotel", "search-flight"],
            "probe": {
                "command": "search-hotel",
                "flags": ["--dest-name", "--check-in-date", "--check-out-date"],
            },
            "status": 0,
            "message": "success",
            "data": {"itemList": [fixture["provider_item"]]},
        },
    }


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

    def test_g2_numeric_lodging_without_quote_context_is_verify_on_click(self):
        fixture, transport_spec = g2_flyai_transport()

        class RecordingReplayTransport(ReplayTransport):
            def execute(self, provider, provider_request):
                self.request = provider_request
                return super().execute(provider, provider_request)

        resolved = resolve_credentials({}, ROOT / ".tmp" / "g2-flyai-no-key")
        transport = RecordingReplayTransport(transport_spec)
        backend = FlyAIBackend("live", resolved, transport)
        parameters = fixture["request_parameters"]
        result = backend.query_lodging(
            parameters["city"], parameters["check_in"], parameters["check_out"], CLOCK,
            party=parameters["party"], rooms=parameters["rooms"],
            adult_count=parameters["adult_count"], occupancy=parameters["occupancy"],
            bed_config=parameters["bed_config"],
            parking_required=parameters["parking_required"],
            cancellation_preference=parameters["cancellation_preference"],
        )
        self.assertIsNone(result.error_class)
        lodging = result.normalized_items[0]
        self.assertIsNone(lodging["price"]["amount"])
        self.assertEqual("verify-on-click", lodging["price"]["price_type"])
        self.assertIsNone(lodging["price"]["includes_taxes"])
        self.assertEqual({"adults": 3, "children": 0}, transport.request.parameters["party"])
        self.assertEqual(1, transport.request.parameters["rooms"])
        self.assertEqual(3, transport.request.parameters["adult_count"])
        self.assertEqual("3 adults in one room", transport.request.parameters["occupancy"])
        self.assertEqual("three-person room", transport.request.parameters["bed_config"])
        self.assertTrue(transport.request.parameters["parking_required"])
        self.assertEqual("free cancellation", transport.request.parameters["cancellation_preference"])

    def test_context_complete_lodging_quote_can_remain_live(self):
        fixture, transport_spec = g2_flyai_transport()
        raw = transport_spec["body"]["data"]["itemList"][0]
        raw["lodgingContext"] = {
            "check_in": "2026-09-10",
            "check_out": "2026-09-11",
            "party": {"adults": 3, "children": 0},
            "rooms": 1,
            "adult_count": 3,
            "occupancy": "3 adults in one room",
            "bed_config": "three-person room",
            "parking_required": True,
            "cancellation_preference": "free cancellation",
            "cancellation_policy": "free cancellation before synthetic deadline",
            "includes_taxes": True,
        }
        resolved = resolve_credentials({}, ROOT / ".tmp" / "g2-flyai-complete-no-key")
        backend = FlyAIBackend("live", resolved, ReplayTransport(transport_spec))
        result = backend.query_lodging(
            "上海", "2026-09-10", "2026-09-11", CLOCK,
            party={"adults": 3, "children": 0}, rooms=1, adult_count=3,
            occupancy="3 adults in one room", bed_config="three-person room",
            parking_required=True, cancellation_preference="free cancellation",
        )
        self.assertIsNone(result.error_class)
        self.assertEqual(4321.0, result.normalized_items[0]["price"]["amount"])
        self.assertEqual("live", result.normalized_items[0]["price"]["price_type"])
        self.assertTrue(result.normalized_items[0]["price"]["includes_taxes"])

    def test_lodging_cli_accepts_hard_constraint_flags(self):
        args = _parser().parse_args([
            "lodging", "--city", "上海", "--check-in", "2026-09-10",
            "--check-out", "2026-09-11", "--adults", "3", "--rooms", "1",
            "--room-constraint", "3 adults in one room",
            "--bed-config", "three-person room", "--parking-required",
            "--cancellation-preference", "free cancellation",
        ])
        self.assertEqual(3, args.adults)
        self.assertEqual(1, args.rooms)
        self.assertEqual("3 adults in one room", args.room_constraint)
        self.assertEqual("three-person room", args.bed_config)
        self.assertTrue(args.parking_required)
        self.assertEqual("free cancellation", args.cancellation_preference)

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

    def test_g2_live_plan_merges_inventory_and_preserves_locked_lodging_unknowns(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            resolved = resolve_credentials({}, Path(temporary) / "missing")
            transport = self.make_transport(temporary, resolved)
            flyai = FlyAIBackend("live", resolved, transport)
            rail = RailBackend.from_spec("fixture:" + str(E2E / "rail.json"), ROOT)
            request_value = load(E2E / "request.json")
            request_value.update({
                "party": {"adults": 3, "children": 0},
                "rooms": 1,
                "adult_count": 3,
                "occupancy": "3 adults in one room",
                "bed_config": "three-person room",
                "parking_required": True,
                "cancellation_preference": "free cancellation",
            })
            candidates_value = load(E2E / "candidates.json")
            candidates_value["lodgings"][0]["locked"] = True
            locked_id = candidates_value["lodgings"][0]["lodging_id"]
            locked_claim_ids = set(candidates_value["lodgings"][0]["claim_ids"])
            result = plan_trip(
                request_value,
                candidates_value,
                CLOCK,
                rail,
                flyai_backend=flyai,
            )
        health = next(item for item in result.trip["provider_health"] if item["provider"] == "flyai")
        self.assertEqual("ready", health["status"])
        self.assertEqual("live", health["mode"])
        self.assertEqual(1, len(result.trip["lodgings"]))
        self.assertEqual(locked_id, result.trip["lodgings"][0]["candidate_ref"])
        self.assertTrue(result.trip["lodgings"][0]["locked"])
        self.assertEqual("verify-on-click", result.trip["lodgings"][0]["price"]["price_type"])
        final_claim_ids = {claim["claim_id"] for claim in result.trip["claims"]}
        self.assertTrue(locked_claim_ids.issubset(final_claim_ids))
        self.assertTrue(any(
            item["field_path"] == "/lodgings/0/price/amount"
            and "cancellation" in item["reason"]
            for item in result.trip["unknowns"]
        ))
        for day in result.trip["days"][:-1]:
            covering = [
                stay for stay in result.trip["lodgings"]
                if stay["check_in"] <= day["date"] < stay["check_out"]
            ]
            self.assertEqual(1, len(covering), day)
        flights = [item for item in result.trip["transport_legs"] if item["travel_mode"] == "flight"]
        self.assertEqual(2, len(flights))
        scheduled_refs = {slot["ref_id"] for day in result.trip["days"] for slot in day["slots"]}
        self.assertTrue(all(item["leg_id"] not in scheduled_refs for item in flights))
        self.assertEqual(3, transport.calls)
        self.assertEqual(3, transport.probe_calls)
        self.assertEqual(3, len([item for item in result.business_calls if item.startswith("flyai.")]))


class FlyAIIsAnOptionalSourceTests(unittest.TestCase):
    """FlyAI is a third-party wrapper, so its failure must never block a plan."""

    class FailingTransport:
        """A transport whose every call fails the way an abandoned CLI would."""

        def __init__(self):
            self.calls = 0

        def execute(self, provider, request):
            self.calls += 1
            raise ProviderTimeout("flyai transport is unavailable")

    def plan_without_flyai_results(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            resolved = resolve_credentials({}, Path(temporary) / "missing")
            transport = self.FailingTransport()
            flyai = FlyAIBackend("live", resolved, transport)
            rail = RailBackend.from_spec("fixture:" + str(E2E / "rail.json"), ROOT)
            result = plan_trip(
                load(E2E / "request.json"),
                load(E2E / "candidates.json"),
                CLOCK,
                rail,
                flyai_backend=flyai,
            )
        return result, transport

    def test_a_failing_flyai_still_produces_a_valid_trip(self):
        from china_trip_weaver.render import render_trip, validate_html
        from china_trip_weaver.validate_trip import validate_trip

        result, transport = self.plan_without_flyai_results()
        self.assertGreater(transport.calls, 0)
        self.assertTrue(validate_trip(result.trip).ok)
        html = render_trip(result.trip)
        self.assertTrue(validate_html(html, result.trip).ok)

    def test_the_failure_is_reported_as_health_not_hidden(self):
        result, _ = self.plan_without_flyai_results()
        health = next(item for item in result.trip["provider_health"] if item["provider"] == "flyai")
        self.assertNotEqual("ready", health["status"])
        self.assertTrue(health["reason"])

    def test_no_flight_candidate_is_invented_when_flyai_fails(self):
        result, _ = self.plan_without_flyai_results()
        flights = [item for item in result.trip["transport_legs"] if item["travel_mode"] == "flight"]
        self.assertEqual([], flights)

    def test_lodging_falls_back_to_the_candidate_file(self):
        result, _ = self.plan_without_flyai_results()
        for lodging in result.trip["lodgings"]:
            self.assertNotEqual("live", lodging["price"]["price_type"])


if __name__ == "__main__":
    unittest.main()
