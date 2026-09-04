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
from china_trip_weaver.planning import RailBackend, SUPPORTED_KEY_NAMES, _route_specs, plan_trip
from china_trip_weaver.render import validate_html
from china_trip_weaver.validate_trip import validate_trip


E2E = ROOT / "tests" / "fixtures" / "e2e"
CASES = ("beijing-shanghai-3d", "shanghai-weekend-2d", "beijing-hangzhou-4d")
CTW = PLUGIN / "scripts" / "ctw"
FIXED_NOW = "2026-09-03T12:00:00+08:00"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


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
