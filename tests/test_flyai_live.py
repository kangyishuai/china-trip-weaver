from __future__ import annotations

import concurrent.futures
import contextlib
import io
import os
import json
import sys
import tempfile
import threading
import time
import unittest
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "plugins" / "china-trip-weaver" / "src"
sys.path.insert(0, str(SRC))

from china_trip_weaver.clock import FixedClock
from china_trip_weaver.contracts import ProviderRequest
from china_trip_weaver.credentials import resolve_credentials
from china_trip_weaver.flyai_inventory import FlyAIBackend
from china_trip_weaver.planning import RailBackend, plan_trip
from china_trip_weaver.cli import _parser, main as cli_main
from china_trip_weaver.providers.base import (
    ContractMismatch,
    ProviderContext,
    ProviderTimeout,
    ReplayTransport,
    _retry_delay_seconds,
)
from china_trip_weaver.providers.amap import AMapAdapter
from china_trip_weaver.providers.amap_http import AMapCallBudget, AMapHTTPTransport
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

    def test_g8_concurrent_rate_limits_serialize_retry_once_and_dedupe(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            resolved = resolve_credentials({}, Path(temporary) / "missing")
            transport = G8FlyAITransport(temporary, resolved)
            backend = FlyAIBackend("live", resolved, transport, deadline_seconds=4)

            def query(index):
                return backend.query_lodging(
                    "合成城市%d" % index,
                    "2026-09-10",
                    "2026-09-11",
                    CLOCK,
                )

            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                results = list(executor.map(query, range(8)))

        self.assertTrue(all(result.error_class is None for result in results))
        self.assertEqual(1, transport.max_active_runs)
        self.assertEqual(2, transport.probe_calls)
        self.assertEqual(12, transport.calls)
        self.assertEqual([2, 2, 2, 2, 1, 1, 1, 1], sorted(transport.attempts.values(), reverse=True))
        retried = [result for result in results if "rate_limit_retry" in result.warnings]
        self.assertEqual(4, len(retried))
        self.assertTrue(all("rate_limit_retries=1" in result.health["reason"] for result in retried))
        lodging_ids = [item["lodging_id"] for result in results for item in result.normalized_items]
        self.assertEqual(8, len(lodging_ids))
        self.assertEqual(len(lodging_ids), len(set(lodging_ids)))

    def test_g8_rate_limit_retry_stops_after_one_retry(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            resolved = resolve_credentials({}, Path(temporary) / "missing")
            transport = G8FlyAITransport(temporary, resolved, persistent_city="持续限流城")
            result = FlyAIBackend(
                "live", resolved, transport, deadline_seconds=4,
            ).query_lodging("持续限流城", "2026-09-10", "2026-09-11", CLOCK)

        self.assertEqual("rate_limited", result.error_class)
        self.assertEqual(2, transport.attempts["持续限流城"])
        self.assertIn("rate_limit_retry", result.warnings)
        self.assertIn("rate_limit_retries=1", result.health["reason"])

    def test_progress_ndjson_has_five_allowlisted_event_types_and_scans_clean(self):
        secret = "gh" + "p_" + "0" * 30
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            folder = Path(temporary)
            resolved = resolve_credentials({"FLYAI_API_KEY": secret}, folder / "missing")
            transport = G8FlyAITransport(temporary, resolved)
            backend = FlyAIBackend("live", resolved, transport, deadline_seconds=4)
            stdout = io.StringIO()
            events = io.StringIO()
            with mock.patch.object(FlyAIBackend, "from_spec", return_value=backend):
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(events):
                    status = cli_main([
                        "lodging", "--city", "合成城市0",
                        "--check-in", "2026-09-10", "--check-out", "2026-09-11",
                        "--progress", "ndjson",
                    ])
            self.assertEqual(0, status, stdout.getvalue() + events.getvalue())
            lines = events.getvalue().splitlines()
            parsed = [json.loads(line) for line in lines]
            self.assertTrue(all(isinstance(event, dict) for event in parsed))
            self.assertEqual(
                {"probe", "query", "degrade", "retry", "completion"},
                {event["event"] for event in parsed},
            )
            self.assertNotIn(secret, events.getvalue())
            self.assertNotIn("itemList", events.getvalue())
            self.assertNotIn("合成酒店", events.getvalue())
            event_path = folder / "progress.ndjson"
            event_path.write_text(events.getvalue(), encoding="utf-8")
            scan = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "scan_secrets.py"), str(event_path)],
                text=True,
                capture_output=True,
            )
            self.assertEqual(0, scan.returncode, scan.stdout + scan.stderr)
            self.assertIn("0 finding(s)", scan.stdout)

    def test_progress_is_silent_by_default_and_root_position_is_supported(self):
        parsed = _parser().parse_args([
            "--progress", "ndjson", "lodging", "--city", "合成城市9",
            "--check-in", "2026-09-10", "--check-out", "2026-09-11",
        ])
        self.assertEqual("ndjson", parsed.progress)
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            resolved = resolve_credentials({}, Path(temporary) / "missing")
            transport = G8FlyAITransport(temporary, resolved)
            backend = FlyAIBackend("live", resolved, transport, deadline_seconds=4)
            stdout = io.StringIO()
            stderr = io.StringIO()
            with mock.patch.object(FlyAIBackend, "from_spec", return_value=backend):
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    status = cli_main([
                        "lodging", "--city", "合成城市9",
                        "--check-in", "2026-09-10", "--check-out", "2026-09-11",
                    ])
        self.assertEqual(0, status, stdout.getvalue() + stderr.getvalue())
        self.assertEqual("", stderr.getvalue())

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


class FlyAIBackendEntityFailureTests(unittest.TestCase):
    @staticmethod
    def synthetic_request():
        return {
            "start_date": "2026-09-10",
            "end_date": "2026-09-11",
            "destinations": [{"city": "合成云港"}],
            "travelers": 2,
        }

    @staticmethod
    def resolved_credentials():
        return resolve_credentials(
            {}, ROOT / ".tmp" / "flyai-book30-synthetic-no-file",
        )

    @staticmethod
    def synthetic_route():
        return SimpleNamespace(
            from_place={"name": "合成起城", "ref_id": "city-synthetic-origin"},
            to_place={"name": "合成终城", "ref_id": "city-synthetic-destination"},
            travel_date="2026-09-10",
        )

    def resolve_flight_failure(self, fixture_name):
        fixture = load(
            ROOT / "tests" / "fixtures" / "providers" / "flyai"
            / (fixture_name + ".json")
        )
        transport = ReplayTransport(fixture["transport"])
        result = FlyAIBackend(
            "live", self.resolved_credentials(), transport,
        ).resolve(
            {
                "start_date": "2026-09-10",
                "end_date": "2026-09-10",
                "destinations": [{"city": "合成终城"}],
                "travelers": 2,
            },
            (self.synthetic_route(),),
            CLOCK,
        )
        return result, transport

    def test_lodging_no_results_keeps_empty_inventory_with_ready_health_warning(self):
        transport = ReplayTransport({
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
                "data": {"itemList": []},
            },
        })
        result = FlyAIBackend(
            "live", self.resolved_credentials(), transport,
        ).resolve(self.synthetic_request(), (), CLOCK)

        self.assertEqual((), result.lodgings)
        self.assertEqual("ready", result.health["status"])
        self.assertEqual(
            "calls=1; credential=keyless-trial; lodging_items=0; "
            "flight_items=0; errors=no_results",
            result.health["reason"],
        )
        self.assertEqual(
            ("no_results:lodging@合成云港:city=合成云港;"
             "check_in=2026-09-10;check_out=2026-09-11",),
            result.warnings,
        )
        self.assertEqual(
            ("flyai.lodging:合成云港:2026-09-10:2026-09-11",),
            result.business_calls,
        )
        self.assertEqual(1, transport.calls)

    def test_lodging_network_failure_retries_then_degrades_exact_entity(self):
        transport = ReplayTransport({"kind": "network"})
        result = FlyAIBackend(
            "live", self.resolved_credentials(), transport,
        ).resolve(self.synthetic_request(), (), CLOCK)

        self.assertEqual((), result.lodgings)
        self.assertEqual("degraded", result.health["status"])
        self.assertEqual(
            "calls=1; credential=keyless-trial; lodging_items=0; "
            "flight_items=0; errors=network",
            result.health["reason"],
        )
        self.assertEqual(
            ("network:lodging@合成云港:city=合成云港;"
             "check_in=2026-09-10;check_out=2026-09-11",),
            result.warnings,
        )
        self.assertEqual(
            ("flyai.lodging:合成云港:2026-09-10:2026-09-11",),
            result.business_calls,
        )
        self.assertEqual(2, transport.calls)

    def test_flight_no_results_keeps_empty_comparisons_with_exact_warning_and_health(self):
        result, transport = self.resolve_flight_failure("empty")

        self.assertEqual((), result.flights)
        self.assertEqual((), result.claims)
        self.assertEqual(
            ("no_results:flight@city-synthetic-origin->city-synthetic-destination:"
             "route=city-synthetic-origin->city-synthetic-destination;date=2026-09-10",),
            result.warnings,
        )
        self.assertEqual(
            "calls=1; credential=keyless-trial; lodging_items=0; "
            "flight_items=0; errors=no_results",
            result.health["reason"],
        )
        self.assertEqual("ready", result.health["status"])
        self.assertEqual("static", result.health["mode"])
        self.assertEqual(
            ("flyai.flight:2026-09-10:合成起城:合成终城",),
            result.business_calls,
        )
        self.assertEqual(1, transport.calls)

    def test_flight_rate_limit_keeps_empty_comparisons_with_exact_warning_and_health(self):
        result, transport = self.resolve_flight_failure("rate_limit")

        self.assertEqual((), result.flights)
        self.assertEqual((), result.claims)
        self.assertEqual(
            ("rate_limited:flight@city-synthetic-origin->city-synthetic-destination:"
             "route=city-synthetic-origin->city-synthetic-destination;date=2026-09-10",),
            result.warnings,
        )
        self.assertEqual(
            "calls=1; credential=keyless-trial; lodging_items=0; "
            "flight_items=0; errors=rate_limited",
            result.health["reason"],
        )
        self.assertEqual("degraded", result.health["status"])
        self.assertEqual("static", result.health["mode"])
        self.assertEqual(
            ("flyai.flight:2026-09-10:合成起城:合成终城",),
            result.business_calls,
        )
        self.assertEqual(1, transport.calls)

    def test_flight_contract_drift_keeps_empty_comparisons_with_exact_warning_and_health(self):
        result, transport = self.resolve_flight_failure("wrong_shape")

        self.assertEqual((), result.flights)
        self.assertEqual((), result.claims)
        self.assertEqual(
            ("contract_mismatch:flight@city-synthetic-origin->city-synthetic-destination:"
             "route=city-synthetic-origin->city-synthetic-destination;date=2026-09-10",),
            result.warnings,
        )
        self.assertEqual(
            "calls=1; credential=keyless-trial; lodging_items=0; "
            "flight_items=0; errors=contract_mismatch",
            result.health["reason"],
        )
        self.assertEqual("contract_mismatch", result.health["status"])
        self.assertEqual("static", result.health["mode"])
        self.assertEqual(
            ("flyai.flight:2026-09-10:合成起城:合成终城",),
            result.business_calls,
        )
        self.assertEqual(1, transport.calls)

    def test_flight_network_failure_retries_and_keeps_empty_comparisons_with_exact_warning_and_health(self):
        result, transport = self.resolve_flight_failure("stderr_error")

        self.assertEqual((), result.flights)
        self.assertEqual((), result.claims)
        self.assertEqual(
            ("network:flight@city-synthetic-origin->city-synthetic-destination:"
             "route=city-synthetic-origin->city-synthetic-destination;date=2026-09-10",),
            result.warnings,
        )
        self.assertEqual(
            "calls=1; credential=keyless-trial; lodging_items=0; "
            "flight_items=0; errors=network",
            result.health["reason"],
        )
        self.assertEqual("degraded", result.health["status"])
        self.assertEqual("static", result.health["mode"])
        self.assertEqual(
            ("flyai.flight:2026-09-10:合成起城:合成终城",),
            result.business_calls,
        )
        self.assertEqual(2, transport.calls)


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

    def test_rate_limited_live_run_replaces_stale_lodging_unknown_reason(self):
        fixture = load(ROOT / "tests" / "fixtures" / "providers" / "flyai" / "rate_limit.json")
        resolved = resolve_credentials(
            {"FLYAI_API_KEY": "ctw-canary-flyai-rate-limit-not-real"},
            ROOT / ".tmp" / "flyai-rate-limit-no-file",
        )
        transport = ReplayTransport(fixture["transport"])
        result = plan_trip(
            load(E2E / "request.json"),
            load(E2E / "candidates.json"),
            CLOCK,
            RailBackend.from_spec("fixture:" + str(E2E / "rail.json"), ROOT),
            flyai_backend=FlyAIBackend("live", resolved, transport),
        )

        health = next(
            item for item in result.trip["provider_health"]
            if item["provider"] == "flyai"
        )
        unknown = next(
            item for item in result.trip["unknowns"]
            if item["field_path"] == "/lodgings/0/price/amount"
            and item["provider"] == "flyai"
        )
        self.assertEqual(3, transport.calls)
        self.assertEqual("degraded", health["status"])
        self.assertEqual(
            "rate_limited:lodging-bjs-central:"
            "city=上海;check_in=2026-10-16;check_out=2026-10-18",
            unknown["reason"],
        )


class AMapRateLimitRetryTests(unittest.TestCase):
    def test_retry_after_is_honored_with_a_fixed_safe_cap(self):
        self.assertEqual(0.0, _retry_delay_seconds({"Retry-After": "0"}))
        self.assertEqual(2.0, _retry_delay_seconds({"retry-after": "120"}))
        self.assertEqual(0.25, _retry_delay_seconds({}))
        self.assertEqual(0.25, _retry_delay_seconds({"Retry-After": "nan"}))

    def test_retry_after_reuses_existing_qps_gate_and_stays_visible(self):
        moments = iter((0.0, 0.0, 0.5))
        qps_waits = []
        budget = AMapCallBudget(
            max_calls=2,
            qps=2,
            monotonic=lambda: next(moments),
            sleep=qps_waits.append,
        )
        responses = iter((
            SyntheticHTTPResponse(429, {}, {"Retry-After": "0"}),
            SyntheticHTTPResponse(200, {
                "status": "1",
                "info": "OK",
                "infocode": "10000",
                "count": "1",
                "pois": [{
                    "id": "SYNTHETIC-AMAP-RETRY",
                    "name": "合成重试景点",
                    "type": "风景名胜;公园广场;公园",
                    "typecode": "110101",
                    "address": "合成大道1号",
                    "location": "121.000000,31.000000",
                    "cityname": "上海市",
                    "adcode": "310000",
                }],
            }, {}),
        ))
        resolved = resolve_credentials(
            {"AMAP_WEBSERVICE_KEY": "ctw-canary-amap-retry-not-real"},
            ROOT / ".tmp" / "amap-retry-no-file",
        )
        transport = AMapHTTPTransport(
            resolved,
            budget=budget,
            opener=lambda request_value, timeout: next(responses),
        )
        provider_request = ProviderRequest(
            request_id="amap-retry",
            capability="poi",
            parameters={"city": "上海", "keywords": "合成重试景点", "page_size": 1, "page_num": 1},
            deadline_ms=1000,
            as_of="2026-09-10",
            cache_policy="bypass",
            trace={"stage": "test"},
        )
        result = AMapAdapter().query(
            provider_request, ProviderContext(CLOCK, resolved, transport),
        )
        self.assertIsNone(result.error_class)
        self.assertEqual(2, budget.calls)
        self.assertEqual([0.5], qps_waits)
        self.assertIn("rate_limit_retry", result.warnings)
        self.assertIn("rate_limit_retries=1", result.health["reason"])


class SyntheticHTTPResponse:
    def __init__(self, status, body, headers):
        self.status = status
        self._body = json.dumps(body).encode("utf-8")
        self.headers = headers

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def geturl(self):
        return "https://restapi.amap.com/v5/place/text"

    def getcode(self):
        return self.status

    def read(self, size=-1):
        return self._body[:size] if size >= 0 else self._body


class G8FlyAITransport(FlyAISubprocessTransport):
    """Synthetic CLI fixture with deterministic per-request rate limits."""

    def __init__(self, folder, credentials, persistent_city=None):
        super().__init__(
            credentials,
            cache_dir=Path(folder) / "npm-cache",
            temp_root=Path(folder) / "flyai-home",
            command=("synthetic-flyai",),
            cwd=ROOT,
        )
        self.persistent_city = persistent_city
        self.attempts = {}
        self.max_active_runs = 0
        self._active_runs = 0
        self._fixture_lock = threading.Lock()

    def _run(self, argv, environment, deadline):
        del environment, deadline
        with self._fixture_lock:
            self.argv_history.append(argv)
            self._active_runs += 1
            self.max_active_runs = max(self.max_active_runs, self._active_runs)
        try:
            time.sleep(0.003)
            if argv[-1] == "--help":
                if len(argv) == 2:
                    return (
                        "Usage: flyai [options] [command]\n"
                        "search-hotel|search-hotels\nsearch-flight",
                        "",
                    )
                return "--dest-name --check-in-date --check-out-date", ""
            city = argv[argv.index("--dest-name") + 1]
            with self._fixture_lock:
                attempt = self.attempts.get(city, 0) + 1
                self.attempts[city] = attempt
            transient = city in {"合成城市0", "合成城市1", "合成城市2", "合成城市3"}
            if (transient and attempt == 1) or (city == self.persistent_city and attempt <= 2):
                return json.dumps({"status": 429, "message": "rate limited", "data": {}}), ""
            item_number = city[-1] if city[-1:].isdigit() else "persistent"
            return json.dumps({
                "status": 0,
                "message": "success",
                "data": {"itemList": [{
                    "shId": "synthetic-" + item_number,
                    "name": city + "合成酒店",
                    "detailUrl": "https://example.invalid/hotel/" + item_number,
                    "area": city,
                    "price": "¥100",
                }]},
            }), ""
        finally:
            with self._fixture_lock:
                self._active_runs -= 1


if __name__ == "__main__":
    unittest.main()
