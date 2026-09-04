from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "china-trip-weaver"
SRC = PLUGIN / "src"
sys.path.insert(0, str(SRC))

from china_trip_weaver.clock import FixedClock
from china_trip_weaver.contracts import canonical_json
from china_trip_weaver.credentials import resolve_credentials
from china_trip_weaver.flyai_inventory import AMapLodgingBackend, FlyAIBackend
from china_trip_weaver.planning import RailBackend, SUPPORTED_KEY_NAMES, _route_specs, plan_trip
from china_trip_weaver.providers.base import ProviderTimeout, ReplayTransport
from china_trip_weaver.providers.variflight_mcp import VariFlightMCPTransport
from china_trip_weaver.render import validate_html
from china_trip_weaver.validate_trip import validate_trip
from china_trip_weaver.variflight_enrichment import VariFlightBackend


E2E = ROOT / "tests" / "fixtures" / "e2e"
CASES = ("beijing-shanghai-3d", "shanghai-weekend-2d", "beijing-hangzhou-4d")
CTW = PLUGIN / "scripts" / "ctw"
FIXED_NOW = "2026-09-03T12:00:00+08:00"
VARIFLIGHT_SERVER = ROOT / "tests" / "fixtures" / "variflight_mcp_server.py"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def run_flyai_total_failure_plan():
    class TotalFailureTransport:
        def __init__(self):
            self.calls = 0

        def execute(self, provider, request):
            del provider, request
            self.calls += 1
            raise ProviderTimeout("synthetic total FlyAI outage")

    folder = E2E / "beijing-shanghai-3d"
    fallback_fixture = load(
        ROOT / "tests" / "fixtures" / "providers" / "variflight" / "g2" / "flyai_total_failure.json"
    )
    request_value = load(folder / "request.json")
    request_value.update(fallback_fixture["request_overrides"])
    with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
        temporary_path = Path(temporary)
        flyai_credentials = resolve_credentials({}, temporary_path / "no-flyai-key")
        flyai_transport = TotalFailureTransport()
        flyai = FlyAIBackend("live", flyai_credentials, flyai_transport)
        variflight_credentials = resolve_credentials(
            {"VARIFLIGHT_API_KEY": "ctw-canary-variflight-fallback-not-real"},
            temporary_path / "no-variflight-file",
        )
        variflight_transport = VariFlightMCPTransport(
            variflight_credentials,
            cache_dir=temporary_path / "npm-cache",
            temp_root=temporary_path / "variflight-home",
            command=(sys.executable, str(VARIFLIGHT_SERVER), "require-key"),
            cwd=ROOT,
        )
        variflight = VariFlightBackend("auto", variflight_credentials, variflight_transport)
        amap_credentials = resolve_credentials(
            {"AMAP_WEBSERVICE_KEY": "ctw-canary-amap-fallback-not-real"},
            temporary_path / "no-amap-file",
        )
        amap = AMapLodgingBackend(
            "auto",
            amap_credentials,
            ReplayTransport({
                "kind": "response",
                "status_code": 200,
                "body": fallback_fixture["amap_response"],
            }),
        )
        rail = RailBackend.from_spec("fixture:" + str(folder / "rail.json"), ROOT)
        result = plan_trip(
            request_value,
            load(folder / "candidates.json"),
            FixedClock.from_iso(FIXED_NOW),
            rail,
            flyai_backend=flyai,
            variflight_backend=variflight,
            amap_lodging_backend=amap,
        )
    return result


class KeylessE2ETests(unittest.TestCase):
    def run_direct(self, case="beijing-shanghai-3d"):
        folder = E2E / case
        clock = FixedClock.from_iso(FIXED_NOW)
        backend = RailBackend.from_spec("fixture:" + str(folder / "rail.json"), ROOT)
        return plan_trip(load(folder / "request.json"), load(folder / "candidates.json"), clock, backend)

    def test_complete_p0_p6_is_schema_html_and_truth_valid(self):
        result = self.run_direct()
        self.assertEqual(
            ("INTAKE", "RESEARCHED", "CANDIDATES_READY", "MATRIX_DEGRADED", "SCHEDULED", "VALIDATED", "RENDERED"),
            result.stages,
        )
        trip_report = validate_trip(result.trip)
        html_report = validate_html(result.html, result.trip)
        self.assertTrue(trip_report.ok, [item.render() for item in trip_report.errors])
        self.assertTrue(html_report.ok, [item.render() for item in html_report.errors])
        self.assertEqual("static", result.trip["mode"])
        self.assertNotIn("mock_notice", result.trip)
        self.assertEqual(3, len(result.trip["days"]))
        self.assertGreaterEqual(sum(len(day["slots"]) for day in result.trip["days"]), 7)
        self.assertEqual(2, len([leg for leg in result.trip["transport_legs"] if leg["travel_mode"] == "rail"]))
        self.assertEqual(1, len(result.trip["lodgings"]))
        self.assertGreaterEqual(len(result.trip["pois"]), 4)
        self.assertIn("food", {poi["category"] for poi in result.trip["pois"]})
        self.assertGreaterEqual(len(result.trip["unknowns"]), 9)

    def test_every_dynamic_entity_fact_and_price_is_typed(self):
        trip = self.run_direct().trip
        claim_ids = {claim["claim_id"] for claim in trip["claims"]}
        for claim in trip["claims"]:
            for field in ("source_url", "provider", "queried_at", "status", "confidence"):
                self.assertIn(field, claim)
        for group in ("transport_legs", "lodgings", "pois"):
            for item in trip[group]:
                self.assertTrue(item["claim_ids"])
                self.assertTrue(set(item["claim_ids"]).issubset(claim_ids))
                if item.get("price") is not None:
                    self.assertIn(item["price"]["price_type"], {"live", "reference", "estimate", "verify-on-click", "unknown"})
                    self.assertIn(item["price"]["claim_id"], claim_ids)
        for unknown in trip["unknowns"]:
            self.assertTrue(unknown["reason"])
            if unknown["claim_id"]:
                self.assertIn(unknown["claim_id"], claim_ids)

    def test_provider_health_and_business_calls_match_candidate_contract(self):
        result = self.run_direct()
        self.assertEqual(
            (
                "rail12306.fixture:2026-10-16:北京:上海",
                "rail12306.fixture:2026-10-18:上海:北京",
            ),
            result.business_calls,
        )
        health = {item["provider"]: item for item in result.trip["provider_health"]}
        self.assertEqual({"12306-mcp", "host-web", "flyai", "amap", "variflight", "anysearch"}, set(health))
        self.assertEqual("degraded", health["12306-mcp"]["status"])
        self.assertIn("deep-link fallback", health["12306-mcp"]["reason"])
        self.assertEqual("ready", health["host-web"]["status"])
        self.assertEqual("ready", health["flyai"]["status"])
        self.assertEqual("missing", health["amap"]["status"])
        self.assertIn("static estimates", health["amap"]["reason"])
        self.assertIn("no business call was made", health["variflight"]["reason"])
        self.assertIn("no auto-registration or business call was made", health["anysearch"]["reason"])

    def test_flyai_total_failure_uses_price_less_variflight_and_amap_candidates(self):
        result = run_flyai_total_failure_plan()
        health = {item["provider"]: item for item in result.trip["provider_health"]}
        self.assertNotEqual("ready", health["flyai"]["status"])
        self.assertIn("timeout", health["flyai"]["reason"])
        self.assertEqual("ready", health["variflight"]["status"])
        self.assertEqual("ready", health["amap"]["status"])
        flights = [
            item for item in result.trip["transport_legs"]
            if item.get("provider") == "variflight"
        ]
        lodgings = [
            item for item in result.trip["lodgings"]
            if item["candidate_ref"].startswith("poi-amap-")
        ]
        self.assertGreaterEqual(len(flights), 1)
        self.assertGreaterEqual(len(lodgings), 1)
        for item in flights + lodgings:
            self.assertIsNone(item["price"]["amount"])
            self.assertEqual("verify-on-click", item["price"]["price_type"])
        lodging_unknowns = [
            item for item in result.trip["unknowns"]
            if item["field_path"] == "/lodgings/0/price/amount"
        ]
        unknown_reasons = "\n".join(item["reason"] for item in lodging_unknowns)
        self.assertIn("occupancy", unknown_reasons)
        self.assertIn("rooms", unknown_reasons)
        self.assertIn("cancellation_policy", unknown_reasons)
        self.assertTrue(validate_trip(result.trip).ok)

    def test_two_direct_runs_are_canonical_and_byte_deterministic(self):
        first = self.run_direct()
        second = self.run_direct()
        self.assertEqual(canonical_json(first.trip), canonical_json(second.trip))
        self.assertEqual(first.html.encode("utf-8"), second.html.encode("utf-8"))
        self.assertEqual(first.trip_sha256, second.trip_sha256)
        self.assertEqual(first.html_sha256, second.html_sha256)
        self.assertEqual(first.trip_sha256, hashlib.sha256(canonical_json(first.trip).encode()).hexdigest())
        self.assertEqual(first.html_sha256, hashlib.sha256(first.html.encode()).hexdigest())

    def test_three_distinct_cli_requests_each_run_twice_byte_identically(self):
        environment = os.environ.copy()
        canaries = {}
        for index, name in enumerate(SUPPORTED_KEY_NAMES):
            canaries[name] = "ctw-runtime-canary-%d-not-real" % index
            environment.pop(name, None)
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            root = Path(temporary)
            for case in CASES:
                folder = E2E / case
                outputs = []
                for run_number in (1, 2):
                    json_path = root / ("%s-%d.json" % (case, run_number))
                    html_path = root / ("%s-%d.html" % (case, run_number))
                    result = subprocess.run(
                        [
                            str(CTW), "plan",
                            "--request", str(folder / "request.json"),
                            "--candidates", str(folder / "candidates.json"),
                            "--rail", "fixture:" + str(folder / "rail.json"),
                            "--offline-fixture", "--fixed-clock", FIXED_NOW,
                            "--output-json", str(json_path), "--output-html", str(html_path),
                        ],
                        env=environment,
                        text=True,
                        capture_output=True,
                    )
                    self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                    self.assertIn("errors=0", result.stdout)
                    outputs.append((json_path.read_bytes(), html_path.read_bytes()))
                self.assertEqual(outputs[0], outputs[1], case)
                for value in canaries.values():
                    self.assertNotIn(value.encode(), outputs[0][0] + outputs[0][1])

            scan_targets = [str(path) for path in sorted(root.glob("*.json")) + sorted(root.glob("*.html"))]
            scan = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "scan_secrets.py")] + scan_targets,
                text=True,
                capture_output=True,
            )
            self.assertEqual(0, scan.returncode, scan.stdout + scan.stderr)

    def test_shanghai_local_plan_has_no_cross_city_leg_or_rail_call(self):
        result = self.run_direct("shanghai-weekend-2d")
        self.assertEqual((), result.business_calls)
        self.assertEqual([], result.trip["transport_legs"])
        rail_health = next(item for item in result.trip["provider_health"] if item["provider"] == "12306-mcp")
        self.assertEqual("ready", rail_health["status"])
        self.assertIn("not called", rail_health["reason"])
        self.assertEqual(2, len(result.trip["days"]))

    def test_beijing_hangzhou_plan_covers_four_days(self):
        result = self.run_direct("beijing-hangzhou-4d")
        self.assertEqual(4, len(result.trip["days"]))
        self.assertEqual(2, len(result.trip["transport_legs"]))
        self.assertEqual("杭州", result.trip["days"][0]["city"])
        self.assertGreaterEqual(sum(len(day["slots"]) for day in result.trip["days"]), 10)

    def test_explicit_same_day_round_trip_builds_outbound_and_return_routes(self):
        request = load(ROOT / "demo" / "guangzhou-shenzhen" / "request.json")
        routes = _route_specs(request)
        self.assertEqual(2, len(routes))
        self.assertFalse(routes[0].return_leg)
        self.assertTrue(routes[1].return_leg)
        self.assertEqual(request["start_date"], routes[0].travel_date)
        self.assertEqual(request["end_date"], routes[1].travel_date)

    def test_g1_multicity_cli_builds_ordered_one_way_transport_legs(self):
        folder = ROOT / "demo" / "multicity-5d"
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            output = Path(temporary)
            json_path = output / "trip.json"
            html_path = output / "trip.html"
            command = subprocess.run(
                [
                    str(CTW), "plan",
                    "--request", str(folder / "request.json"),
                    "--candidates", str(folder / "candidates.json"),
                    "--rail", "off", "--mobility", "off", "--lodging", "off",
                    "--aviation", "off", "--offline-fixture", "--fixed-clock", FIXED_NOW,
                    "--output-json", str(json_path), "--output-html", str(html_path),
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(0, command.returncode, command.stdout + command.stderr)
            self.assertIn("PLAN_COMPLETE", command.stdout)
            trip = load(json_path)
            self.assertEqual(
                [
                    ("city-beijing", "city-shanghai"),
                    ("city-shanghai", "city-hangzhou"),
                    ("city-hangzhou", "city-suzhou"),
                ],
                [(leg["from_ref"], leg["to_ref"]) for leg in trip["transport_legs"]],
            )
            self.assertNotIn(
                ("city-suzhou", "city-beijing"),
                [(leg["from_ref"], leg["to_ref"]) for leg in trip["transport_legs"]],
            )
            self.assertEqual(
                ["上海", "杭州", "杭州", "苏州", "苏州"],
                [day["city"] for day in trip["days"]],
            )
            self.assertEqual(
                [
                    ("上海", "2026-10-16", "2026-10-17"),
                    ("杭州", "2026-10-17", "2026-10-19"),
                    ("苏州", "2026-10-19", "2026-10-20"),
                ],
                [(stay["city"], stay["check_in"], stay["check_out"]) for stay in trip["lodgings"]],
            )
            for day in trip["days"][:-1]:
                covering = [
                    stay for stay in trip["lodgings"]
                    if stay["check_in"] <= day["date"] < stay["check_out"]
                ]
                self.assertEqual(1, len(covering), day)
                self.assertEqual(day["city"], covering[0]["city"])
                self.assertEqual(covering[0]["lodging_id"], day["stay_id"])
                self.assertIn(day["date"], covering[0]["selected_nights"])
                self.assertEqual("selected", covering[0]["selection_status"])
            self.assertIsNone(trip["days"][-1]["stay_id"])
            self.assertTrue(validate_trip(trip).ok)
            self.assertTrue(validate_html(html_path.read_text(encoding="utf-8"), trip).ok)
            mixed = json.loads(json.dumps(trip, ensure_ascii=False))
            mixed["lodgings"][0] = load(folder / "candidates.json")["lodgings"][0]
            self.assertFalse(validate_trip(mixed).ok)

    def test_multicity_missing_overnight_candidate_is_structured_no_solution(self):
        folder = ROOT / "demo" / "multicity-5d"
        candidates = load(folder / "candidates.json")
        removed_ids = {
            item["lodging_id"] for item in candidates["lodgings"] if item["city"] == "苏州"
        }
        candidates["lodgings"] = [
            item for item in candidates["lodgings"] if item["lodging_id"] not in removed_ids
        ]
        candidates["claims"] = [
            item for item in candidates["claims"] if item["subject_ref"] not in removed_ids
        ]
        candidates["unknowns"] = [
            item for item in candidates["unknowns"] if not item["field_path"].startswith("/lodgings/2/")
        ]
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            output = Path(temporary)
            candidates_path = output / "candidates.json"
            json_path = output / "trip.json"
            html_path = output / "trip.html"
            candidates_path.write_text(
                json.dumps(candidates, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            command = subprocess.run(
                [
                    str(CTW), "plan",
                    "--request", str(folder / "request.json"),
                    "--candidates", str(candidates_path),
                    "--rail", "off", "--mobility", "off", "--lodging", "off",
                    "--aviation", "off", "--offline-fixture", "--fixed-clock", FIXED_NOW,
                    "--output-json", str(json_path), "--output-html", str(html_path),
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(1, command.returncode, command.stdout + command.stderr)
            self.assertIn("NO_STAY_FOR_NIGHT", command.stderr)
            self.assertFalse(json_path.exists())
            self.assertFalse(html_path.exists())

    def test_multicity_return_is_explicit_or_already_present_in_destinations(self):
        request = load(ROOT / "demo" / "multicity-5d" / "request.json")
        explicit = json.loads(json.dumps(request, ensure_ascii=False))
        explicit["constraints"].append("往返")
        explicit_routes = _route_specs(explicit)
        self.assertEqual(4, len(explicit_routes))
        self.assertEqual(
            ("city-suzhou", "city-beijing", explicit["end_date"]),
            (
                explicit_routes[-1].from_place["ref_id"],
                explicit_routes[-1].to_place["ref_id"],
                explicit_routes[-1].travel_date,
            ),
        )

        closed = json.loads(json.dumps(request, ensure_ascii=False))
        closed["destinations"][-1] = closed["origin"]
        closed_routes = _route_specs(closed)
        self.assertEqual(3, len(closed_routes))
        self.assertEqual("city-beijing", closed_routes[-1].to_place["ref_id"])
        self.assertEqual(1, sum(route.to_place["ref_id"] == "city-beijing" for route in closed_routes))

        negated = json.loads(json.dumps(request, ensure_ascii=False))
        negated["constraints"].append("不需要往返")
        self.assertEqual(3, len(_route_specs(negated)))

    def test_missing_poi_claim_is_rejected_before_planning(self):
        folder = E2E / "beijing-shanghai-3d"
        invalid = E2E / "candidates-invalid" / "missing-poi-claim.json"
        result = subprocess.run(
            [
                str(CTW), "plan",
                "--request", str(folder / "request.json"),
                "--candidates", str(invalid),
                "--rail", "fixture:" + str(folder / "rail.json"),
                "--offline-fixture", "--fixed-clock", FIXED_NOW,
                "--output-json", str(ROOT / ".tmp" / "invalid-trip.json"),
                "--output-html", str(ROOT / ".tmp" / "invalid-trip.html"),
            ],
            text=True,
            capture_output=True,
        )
        self.assertEqual(1, result.returncode)
        self.assertIn("C_CLAIM_REF", result.stderr)
        self.assertNotIn("PLAN_COMPLETE", result.stdout)

    def test_synthetic_plan_rail_fixtures_keep_raw_mcp_results(self):
        for case in CASES:
            fixture = load(E2E / case / "rail.json")
            self.assertIn("synthetic 12306 MCP response", fixture["source"])
            body = fixture["transport"]["body"]
            self.assertEqual(8, len(body["tools"]))
            for call in body["calls"]:
                result = call["result"]
                self.assertIn("content", result)
                self.assertIsInstance(result["content"][0]["text"], str)

    def test_keyless_html_opens_offline_with_no_remote_requests(self):
        result = self.run_direct()
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            folder = Path(temporary)
            html_path = folder / "trip.html"
            html_path.write_text(result.html, encoding="utf-8")
            qa = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "qa_renderer_browser.py"), str(html_path), "--output", str(folder / "qa"), "--viewports", "375x812,1440x900"],
                text=True,
                capture_output=True,
                timeout=60,
            )
            self.assertEqual(0, qa.returncode, qa.stdout + qa.stderr)
            report = load(folder / "qa" / "qa-report.json")
            self.assertEqual([], report["failures"])
            for viewport in report["viewports"]:
                self.assertEqual([], viewport["resourceRequests"])

    def test_html_has_no_transaction_controls(self):
        html = self.run_direct().html.lower()
        for fragment in ("<form", "<button", "<input", "javascript:", "立即购买", "提交订单"):
            self.assertNotIn(fragment, html)


if __name__ == "__main__":
    unittest.main()
