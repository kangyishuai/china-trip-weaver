from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "china-trip-weaver"
SRC = PLUGIN / "src"
sys.path.insert(0, str(SRC))

from china_trip_weaver.clock import FixedClock
from china_trip_weaver.journey import (
    assemble_journey,
    journey_booking_checklist,
    journey_budget_ledger,
    journey_risk_items,
    plan_journey,
    split_journey_inputs,
    validate_journey,
)
from china_trip_weaver.planning import RailBackend, _normalize_request, plan_trip
from china_trip_weaver.render import render_journey, validate_journey_html
from china_trip_weaver.render.validate_html import AuditParser
from china_trip_weaver.replan import replan_trip
from china_trip_weaver.validate_trip import validate_trip
from scripts.build_plan_fixtures import (
    journey_six_city_lodging_chain_case,
    journey_sixteen_day_case,
)


FIXED_NOW = "2026-09-05T09:00:00+08:00"
VALID_TRIP = ROOT / "tests" / "fixtures" / "trips" / "schema" / "valid" / "weekend-live.json"
GROUPED_TRIP = ROOT / "demo" / "grouped-departures" / "trip.json"
JOURNEY_DEMO = ROOT / "demo" / "journey-16d"
LODGING_CHAIN_FIXTURE = ROOT / "tests" / "fixtures" / "journey" / "synthetic-six-city-16d.json"
CTW = PLUGIN / "scripts" / "ctw"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class JourneyModelTests(unittest.TestCase):
    def make_single_trip_journey(self):
        trip = load(VALID_TRIP)
        return assemble_journey(
            [trip],
            trip["request"],
            [],
            FixedClock.from_iso(FIXED_NOW),
        )

    def test_journey_embeds_a_complete_valid_and_independently_replanable_trip(self):
        journey = self.make_single_trip_journey()
        self.assertTrue(validate_journey(journey).ok)
        child = journey["trips"][0]
        child_report = validate_trip(child)
        self.assertTrue(child_report.ok, [item.render() for item in child_report.errors])
        replanned = replan_trip(
            child,
            {"type": "user_delete", "subject_ref": "slot-3", "reason": "synthetic Journey test"},
            base_revision=child["revision"]["number"],
            user_locked_refs=[],
            clock=FixedClock.from_iso(FIXED_NOW),
        )
        self.assertTrue(validate_trip(replanned.trip).ok)
        self.assertEqual(2, replanned.trip["revision"]["number"])

    def test_reduced_trip_projection_is_rejected(self):
        journey = self.make_single_trip_journey()
        journey["trips"][0] = {
            "schema_version": "1.0.0",
            "trip_id": journey["trips"][0]["trip_id"],
        }
        report = validate_journey(journey)
        self.assertFalse(report.ok)
        self.assertIn("S_REQUIRED", {item.code for item in report.errors})

    def test_grouped_travelers_are_shared_at_journey_scope(self):
        trip = load(GROUPED_TRIP)
        journey = assemble_journey(
            [trip],
            trip["request"],
            [],
            FixedClock.from_iso(FIXED_NOW),
        )
        self.assertNotIn("origin", journey)
        self.assertNotIn("travelers", journey)
        self.assertEqual(trip["request"]["traveler_groups"], journey["traveler_groups"])
        self.assertEqual(trip["request"]["meeting_anchor"], journey["meeting_anchor"])
        self.assertTrue(validate_journey(journey).ok)


class JourneySplitTests(unittest.TestCase):
    def setUp(self):
        case = journey_sixteen_day_case()
        self.request = case["request"]
        self.candidates = case["candidates"]

    def test_sixteen_days_split_at_cross_city_days_into_three_compliant_requests(self):
        segments = split_journey_inputs(self.request, self.candidates)
        self.assertEqual(3, len(segments))
        self.assertEqual(
            [
                ("2026-10-01", "2026-10-05", ["上海"]),
                ("2026-10-06", "2026-10-10", ["杭州"]),
                ("2026-10-11", "2026-10-16", ["苏州"]),
            ],
            [
                (
                    item.request["start_date"],
                    item.request["end_date"],
                    [destination["city"] for destination in item.request["destinations"]],
                )
                for item in segments
            ],
        )
        for segment in segments:
            normalized = _normalize_request(segment.request)
            days = (
                date.fromisoformat(normalized["end_date"])
                - date.fromisoformat(normalized["start_date"])
            ).days + 1
            self.assertLessEqual(days, 7)

    def test_single_city_long_request_uses_seven_seven_two_hard_splits(self):
        request = copy.deepcopy(self.request)
        candidates = copy.deepcopy(self.candidates)
        request["origin"] = copy.deepcopy(request["destinations"][0])
        request["destinations"] = [copy.deepcopy(request["destinations"][0])]
        candidates["lodgings"][0]["check_out"] = request["end_date"]
        segments = split_journey_inputs(request, candidates)
        self.assertEqual(
            [
                ("2026-10-01", "2026-10-07"),
                ("2026-10-08", "2026-10-14"),
                ("2026-10-15", "2026-10-16"),
            ],
            [(item.request["start_date"], item.request["end_date"]) for item in segments],
        )

    def test_every_split_can_be_planned_as_a_standalone_valid_trip(self):
        backend = RailBackend.from_spec("off", ROOT)
        for segment in split_journey_inputs(self.request, self.candidates):
            with self.subTest(start=segment.request["start_date"]):
                result = plan_trip(
                    segment.request,
                    segment.candidates,
                    FixedClock.from_iso(FIXED_NOW),
                    backend,
                )
                report = validate_trip(result.trip)
                self.assertTrue(report.ok, [item.render() for item in report.errors])
                self.assertLessEqual(len(result.trip["days"]), 7)

    def test_six_city_uses_the_minimum_lodging_aligned_segment_count(self):
        case = journey_six_city_lodging_chain_case()
        segments = split_journey_inputs(case["request"], case["candidates"])
        self.assertEqual(3, len(segments))
        self.assertEqual(
            [
                ("2026-09-25", "2026-09-29", ["合成甲城", "合成乙城", "合成甲城"]),
                ("2026-09-30", "2026-10-05", ["合成丙城", "合成丁城"]),
                ("2026-10-06", "2026-10-10", ["合成戊城", "合成己城", "合成戊城"]),
            ],
            [
                (
                    item.request["start_date"],
                    item.request["end_date"],
                    [destination["city"] for destination in item.request["destinations"]],
                )
                for item in segments
            ],
        )
        self.assertEqual(
            [5, 6, 5],
            [
                (
                    date.fromisoformat(item.request["end_date"])
                    - date.fromisoformat(item.request["start_date"])
                ).days + 1
                for item in segments
            ],
        )

    def test_expected_segment_days_five_changes_the_partition(self):
        case = journey_six_city_lodging_chain_case()
        default_segments = split_journey_inputs(case["request"], case["candidates"])
        preferred_segments = split_journey_inputs(
            case["request"],
            case["candidates"],
            expected_segment_days=5,
        )
        self.assertEqual(3, len(default_segments))
        self.assertEqual(4, len(preferred_segments))
        self.assertEqual(
            [4, 4, 5, 3],
            [
                (
                    date.fromisoformat(item.request["end_date"])
                    - date.fromisoformat(item.request["start_date"])
                ).days + 1
                for item in preferred_segments
            ],
        )
        self.assertTrue(all(
            (
                date.fromisoformat(item.request["end_date"])
                - date.fromisoformat(item.request["start_date"])
            ).days + 1 <= 7
            for item in preferred_segments
        ))

    def test_expected_segment_days_rejects_values_outside_one_to_seven(self):
        case = journey_six_city_lodging_chain_case()
        for value in (0, 8, True, 5.0):
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                    ValueError,
                    "expected_segment_days must be an integer between one and seven inclusive",
                ):
                    split_journey_inputs(
                        case["request"],
                        case["candidates"],
                        expected_segment_days=value,
                    )

    def test_expected_segment_days_preserves_lodging_chain_and_records_actual_lengths(self):
        case = journey_six_city_lodging_chain_case()
        result = plan_journey(
            case["request"],
            case["candidates"],
            FixedClock.from_iso(FIXED_NOW),
            RailBackend.from_spec("off", ROOT),
            expected_segment_days=5,
        )
        journey = result.journey
        self.assertTrue(validate_journey(journey).ok)
        self.assertEqual(
            {
                "expected_segment_days": 5,
                "maximum_segment_days": 7,
                "actual_segment_days": [4, 4, 5, 3],
                "strategy": "expected_length",
                "assumptions": [
                    "JOURNEY_SEGMENTATION expected_days=5 actual_days=4,4,5,3; actual lengths may differ "
                    "because whole days are distributed around lodging-city changes while maximum_days=7 remains hard",
                ],
            },
            journey["segmentation"],
        )
        assumption = journey["segmentation"]["assumptions"][0]
        self.assertTrue(all(
            assumption in trip["request"]["assumptions"]
            for trip in journey["trips"]
        ))
        days = {
            day_item["date"]: day_item
            for trip in journey["trips"]
            for day_item in trip["days"]
        }
        start = date.fromisoformat(case["request"]["start_date"])
        for offset in range(15):
            night = (start + timedelta(days=offset)).isoformat()
            lodging_cities = {
                item["city"] for item in case["candidates"]["lodgings"]
                if item["check_in"] <= night < item["check_out"]
            }
            self.assertEqual({days[night]["city"]}, lodging_cities, night)

    def test_journey_validator_rejects_tampered_actual_segment_lengths(self):
        case = journey_six_city_lodging_chain_case()
        journey = copy.deepcopy(plan_journey(
            case["request"],
            case["candidates"],
            FixedClock.from_iso(FIXED_NOW),
            RailBackend.from_spec("off", ROOT),
        ).journey)
        journey["segmentation"]["actual_segment_days"] = [7, 7, 2]
        self.assertIn(
            "J_SEGMENT_LENGTHS",
            {item.code for item in validate_journey(journey).errors},
        )

    def test_six_city_fixture_is_reproducible_and_strictly_synthetic(self):
        fixture = load(LODGING_CHAIN_FIXTURE)
        self.assertEqual(journey_six_city_lodging_chain_case(), fixture)
        self.assertEqual(3, fixture["request"]["travelers"])
        self.assertEqual(8, len(fixture["request"]["destinations"]))
        self.assertEqual(6, len({item["city"] for item in fixture["request"]["destinations"]}))
        self.assertEqual(9, len(fixture["candidates"]["lodgings"]))
        self.assertEqual(6, len(fixture["candidates"]["pois"]))
        entities = fixture["candidates"]["lodgings"] + fixture["candidates"]["pois"]
        self.assertTrue(all("合成" in item["name"] and "合成" in item["city"] for item in entities))
        urls = [url for item in entities for url in item["deep_links"]]
        urls.extend(item["source_url"] for item in fixture["candidates"]["claims"])
        self.assertTrue(all(url.startswith("https://example.invalid/") for url in urls))
        self.assertTrue(all(item["price"]["amount"] is None for item in fixture["candidates"]["lodgings"]))

    def test_six_city_journey_nights_match_candidate_lodging_city_and_dates(self):
        case = journey_six_city_lodging_chain_case()
        result = plan_journey(
            case["request"],
            case["candidates"],
            FixedClock.from_iso(FIXED_NOW),
            RailBackend.from_spec("off", ROOT),
        )
        report = validate_journey(result.journey)
        self.assertTrue(report.ok, [item.render() for item in report.errors])

        days = {
            day_item["date"]: (trip, day_item)
            for trip in result.journey["trips"]
            for day_item in trip["days"]
        }
        for offset in range(15):
            night = (date.fromisoformat(case["request"]["start_date"]) + timedelta(days=offset)).isoformat()
            candidates = [
                item for item in case["candidates"]["lodgings"]
                if item["check_in"] <= night < item["check_out"]
            ]
            self.assertGreaterEqual(len(candidates), 1, night)
            self.assertEqual(1, len({item["city"] for item in candidates}), night)
            trip, day_item = days[night]
            self.assertEqual(candidates[0]["city"], day_item["city"], night)
            selected = next(
                item for item in trip["lodgings"]
                if item["lodging_id"] == day_item["stay_id"]
            )
            self.assertIn(selected["candidate_ref"], {item["lodging_id"] for item in candidates}, night)
            self.assertIn(night, selected["selected_nights"])

    def test_lodging_chain_gap_reports_date_city_and_nearest_candidate(self):
        case = journey_six_city_lodging_chain_case()
        case["candidates"]["lodgings"][1]["check_out"] = "2026-09-28"
        with self.assertRaises(ValueError) as raised:
            plan_journey(
                case["request"],
                case["candidates"],
                FixedClock.from_iso(FIXED_NOW),
                RailBackend.from_spec("off", ROOT),
            )
        message = str(raised.exception)
        payload = json.loads(message[message.index("{"):])
        self.assertEqual("NO_STAY_FOR_NIGHT", payload["code"])
        self.assertEqual("2026-09-28", payload["date"])
        self.assertEqual("合成乙城", payload["city"])
        self.assertEqual(1, payload["nearest_lodging"]["candidate_index"])
        self.assertEqual("合成乙城合成住宿2", payload["nearest_lodging"]["name"])
        self.assertEqual("2026-09-28", payload["nearest_lodging"]["check_out"])
        self.assertEqual(1, payload["nearest_lodging"]["distance_nights"])
        self.assertTrue(payload["nearest_lodging"]["same_city"])

    def test_six_city_fixture_runs_through_journey_plan_and_validate_cli(self):
        fixture = load(LODGING_CHAIN_FIXTURE)
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            output = Path(temporary)
            request_path = output / "request.json"
            candidates_path = output / "candidates.json"
            journey_path = output / "journey.json"
            request_path.write_text(
                json.dumps(fixture["request"], ensure_ascii=False),
                encoding="utf-8",
            )
            candidates_path.write_text(
                json.dumps(fixture["candidates"], ensure_ascii=False),
                encoding="utf-8",
            )
            planned = subprocess.run(
                [
                    str(CTW), "journey", "plan",
                    "--request", str(request_path),
                    "--candidates", str(candidates_path),
                    "--rail", "off",
                    "--offline-fixture",
                    "--fixed-clock", FIXED_NOW,
                    "--output-json", str(journey_path),
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(0, planned.returncode, planned.stdout + planned.stderr)
            self.assertIn("trips=3 days=16 max_trip_days=6", planned.stdout)
            validated = subprocess.run(
                [str(CTW), "journey", "validate", str(journey_path)],
                text=True,
                capture_output=True,
            )
            self.assertEqual(0, validated.returncode, validated.stdout + validated.stderr)
            self.assertIn("JOURNEY VALID", validated.stdout)


class JourneyContinuityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = journey_sixteen_day_case()
        cls.result = plan_journey(
            cls.case["request"],
            cls.case["candidates"],
            FixedClock.from_iso(FIXED_NOW),
            RailBackend.from_spec("off", ROOT),
        )

    def assertJourneyItemTraceable(self, journey, item):
        trip = journey["trips"][item["trip_index"]]
        refs = {
            "trip": {trip["trip_id"]},
            "transport_leg": {value["leg_id"] for value in trip["transport_legs"]},
            "lodging": {value["lodging_id"] for value in trip["lodgings"]},
            "poi": {value["poi_id"] for value in trip["pois"]},
            "day": {value["day_id"] for value in trip["days"]},
            "provider_health": {value["provider"] for value in trip["provider_health"]},
        }
        self.assertIn(item["source_kind"], refs)
        self.assertIn(item["source_ref"], refs[item["source_kind"]])
        if item["claim_id"]:
            self.assertIn(item["claim_id"], {value["claim_id"] for value in trip["claims"]})

    def test_g7_sixteen_day_journey_is_contiguous_budgeted_and_replanable(self):
        journey = self.result.journey
        report = validate_journey(journey)
        self.assertTrue(report.ok, [item.render() for item in report.errors])
        self.assertEqual(3, len(journey["trips"]))
        self.assertEqual([5, 5, 6], [len(item["days"]) for item in journey["trips"]])
        self.assertTrue(journey["journey_id"])
        self.assertTrue(all("journey_id" not in item for item in journey["trips"]))

        for left, right in zip(journey["trips"], journey["trips"][1:]):
            expected = date.fromisoformat(left["request"]["end_date"]) + timedelta(days=1)
            self.assertEqual(expected, date.fromisoformat(right["request"]["start_date"]))
        self.assertEqual(2, len(journey["segment_connections"]))
        for connection in journey["segment_connections"]:
            self.assertEqual("changed", connection["lodging_continuity"]["status"])
            self.assertIsNotNone(connection["lodging_continuity"]["from_lodging_id"])
            self.assertIsNotNone(connection["lodging_continuity"]["to_lodging_id"])
            self.assertEqual(
                "included_in_next_trip",
                connection["cross_segment_transport"]["status"],
            )

        covered_nights = sorted(
            night
            for trip in journey["trips"]
            for lodging in trip["lodgings"]
            for night in lodging["selected_nights"]
        )
        expected_nights = [
            (date.fromisoformat(journey["start_date"]) + timedelta(days=index)).isoformat()
            for index in range(15)
        ]
        self.assertEqual(expected_nights, covered_nights)
        child_known = sum(item["budget_ledger"]["known_cost_cny"] for item in journey["trips"])
        additional_transport = sum(
            item["amount_max_cny"]
            for item in journey["budget_ledger"]["items"]
            if item["category"] == "cross_segment_transport"
            and item["amount_max_cny"] is not None
        )
        self.assertEqual(
            child_known + additional_transport,
            journey["budget_ledger"]["known_cost_cny"],
        )
        self.assertEqual(
            {"minimum": None, "maximum": None},
            journey["budget_ledger"]["total_range_cny"],
        )

        for child in journey["trips"]:
            child_report = validate_trip(child)
            self.assertTrue(child_report.ok, [item.render() for item in child_report.errors])
            subject = child["days"][-1]["slots"][-1]["slot_id"]
            replanned = replan_trip(
                child,
                {"type": "user_delete", "subject_ref": subject, "reason": "synthetic G7 replan"},
                base_revision=child["revision"]["number"],
                user_locked_refs=[],
                clock=FixedClock.from_iso(FIXED_NOW),
            )
            self.assertTrue(validate_trip(replanned.trip).ok)

    def test_gap_between_trips_is_a_structured_error(self):
        journey = copy.deepcopy(self.result.journey)
        journey["trips"][1]["request"]["start_date"] = "2026-10-07"
        report = validate_journey(journey)
        self.assertIn("J_DATE_GAP", {item.code for item in report.errors})

    def test_overlap_between_trips_is_a_structured_error(self):
        journey = copy.deepcopy(self.result.journey)
        journey["trips"][1]["request"]["start_date"] = "2026-10-05"
        report = validate_journey(journey)
        self.assertIn("J_DATE_OVERLAP", {item.code for item in report.errors})

    def test_budget_tampering_is_rejected(self):
        journey = copy.deepcopy(self.result.journey)
        journey["budget_ledger"]["known_cost_cny"] += 1
        report = validate_journey(journey)
        self.assertIn("J_BUDGET_MISMATCH", {item.code for item in report.errors})

    def test_separate_cross_segment_transport_is_added_to_trip_totals(self):
        journey = copy.deepcopy(self.result.journey)
        transport = journey["segment_connections"][0]["cross_segment_transport"]
        transport.update({
            "status": "separate",
            "leg_id": "external-boundary-transfer",
            "included_in_trip_id": None,
            "price_type": "reference",
            "amount_min_cny": 120,
            "amount_max_cny": 120,
            "reason": "synthetic separately priced boundary transfer",
        })
        journey["budget_ledger"] = journey_budget_ledger(
            journey["trips"],
            journey["segment_connections"],
            journey["budget_ledger"]["budget_cny"],
        )
        child_known = sum(item["budget_ledger"]["known_cost_cny"] for item in journey["trips"])
        self.assertEqual(child_known + 120, journey["budget_ledger"]["known_cost_cny"])
        report = validate_journey(journey)
        self.assertTrue(report.ok, [item.render() for item in report.errors])

    def test_grouped_long_journey_meets_once_then_continues_the_same_stay(self):
        case = journey_sixteen_day_case()
        request = case["request"]
        anchor = copy.deepcopy(request["destinations"][0])
        request.pop("origin")
        request.pop("travelers")
        request["destinations"] = [anchor]
        request["traveler_groups"] = [
            {
                "group_id": "north",
                "travelers": 2,
                "origin": {"ref_id": "city-beijing", "name": "北京", "city": "北京"},
            },
            {
                "group_id": "south",
                "travelers": 1,
                "origin": {"ref_id": "city-guangzhou", "name": "广州", "city": "广州"},
            },
        ]
        request["meeting_anchor"] = {
            "location": anchor,
            "meet_by": "2026-10-01T14:30:00+08:00",
            "buffer_minutes": 60,
        }
        request["rooms"] = 2
        case["candidates"]["lodgings"][0]["check_out"] = "2026-10-16"
        result = plan_journey(
            request,
            case["candidates"],
            FixedClock.from_iso(FIXED_NOW),
            RailBackend.from_spec("off", ROOT),
        )
        journey = result.journey
        self.assertTrue(validate_journey(journey).ok)
        self.assertEqual([7, 7, 2], [len(item["days"]) for item in journey["trips"]])
        self.assertEqual(["north", "south"], [item["group_id"] for item in journey["traveler_groups"]])
        self.assertIn("traveler_groups", journey["trips"][0]["request"])
        self.assertEqual([3, 3], [item["request"]["travelers"] for item in journey["trips"][1:]])
        self.assertEqual(
            [("continued", "not_required"), ("continued", "not_required")],
            [
                (
                    item["lodging_continuity"]["status"],
                    item["cross_segment_transport"]["status"],
                )
                for item in journey["segment_connections"]
            ],
        )
        rendered = render_journey(journey)
        parser = AuditParser()
        parser.feed(rendered)
        parser.close()
        visible = " ".join(parser.visible_text)
        self.assertIn("北京 / 广州 → 上海", visible)
        self.assertNotIn("北京 → 广州", visible)
        self.assertTrue(validate_journey_html(rendered, journey).ok)

    def test_cli_expected_segment_days_reaches_the_planner(self):
        """The CLI flag must actually change the partition and reject out-of-range values."""

        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            output = Path(temporary)
            request_path = output / "request.json"
            candidates_path = output / "candidates.json"
            request_path.write_text(json.dumps(self.case["request"], ensure_ascii=False), encoding="utf-8")
            candidates_path.write_text(json.dumps(self.case["candidates"], ensure_ascii=False), encoding="utf-8")

            def plan(extra, name):
                return subprocess.run(
                    [
                        str(CTW), "journey", "plan",
                        "--request", str(request_path),
                        "--candidates", str(candidates_path),
                        "--rail", "off", "--offline-fixture",
                        "--fixed-clock", FIXED_NOW,
                        "--output-json", str(output / name),
                    ] + extra,
                    text=True,
                    capture_output=True,
                )

            default = plan([], "default.json")
            self.assertEqual(0, default.returncode, default.stdout + default.stderr)
            five = plan(["--expected-segment-days", "5"], "five.json")
            self.assertEqual(0, five.returncode, five.stdout + five.stderr)

            baseline = json.loads((output / "default.json").read_text(encoding="utf-8"))
            shaped = json.loads((output / "five.json").read_text(encoding="utf-8"))
            self.assertIsNone(baseline["segmentation"]["expected_segment_days"])
            self.assertEqual(5, shaped["segmentation"]["expected_segment_days"])
            self.assertNotEqual(
                baseline["segmentation"]["actual_segment_days"],
                shaped["segmentation"]["actual_segment_days"],
            )
            for journey in (baseline, shaped):
                self.assertTrue(all(days <= 7 for days in journey["segmentation"]["actual_segment_days"]))

            rejected = plan(["--expected-segment-days", "9"], "nine.json")
            self.assertNotEqual(0, rejected.returncode)
            self.assertIn("between one and seven", rejected.stdout + rejected.stderr)

    def test_cli_plans_and_validates_the_sixteen_day_journey(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            output = Path(temporary)
            request_path = output / "request.json"
            candidates_path = output / "candidates.json"
            journey_path = output / "journey.json"
            request_path.write_text(json.dumps(self.case["request"], ensure_ascii=False), encoding="utf-8")
            candidates_path.write_text(json.dumps(self.case["candidates"], ensure_ascii=False), encoding="utf-8")
            planned = subprocess.run(
                [
                    str(CTW), "journey", "plan",
                    "--request", str(request_path),
                    "--candidates", str(candidates_path),
                    "--rail", "off",
                    "--offline-fixture",
                    "--fixed-clock", FIXED_NOW,
                    "--output-json", str(journey_path),
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(0, planned.returncode, planned.stdout + planned.stderr)
            self.assertIn("JOURNEY_PLAN_COMPLETE", planned.stdout)
            self.assertIn("trips=3 days=16 max_trip_days=6", planned.stdout)
            validated = subprocess.run(
                [str(CTW), "journey", "validate", str(journey_path)],
                text=True,
                capture_output=True,
            )
            self.assertEqual(0, validated.returncode, validated.stdout + validated.stderr)
            self.assertIn("JOURNEY VALID", validated.stdout)
            self.assertEqual(3, len(load(journey_path)["trips"]))

    def test_booking_checklist_covers_every_leg_stay_and_unknown_in_deadline_order(self):
        journey = self.result.journey
        checklist = journey_booking_checklist(journey)

        expected_legs = {
            (trip_index, item["leg_id"])
            for trip_index, trip in enumerate(journey["trips"])
            for item in trip["transport_legs"]
        }
        expected_stays = {
            (trip_index, item["lodging_id"])
            for trip_index, trip in enumerate(journey["trips"])
            for item in trip["lodgings"]
        }
        expected_unknowns = sorted(
            (trip_index, item["field_path"])
            for trip_index, trip in enumerate(journey["trips"])
            for item in trip["unknowns"]
        )
        self.assertEqual(
            expected_legs,
            {
                (item["trip_index"], item["source_ref"])
                for item in checklist if item["kind"] == "transport"
            },
        )
        self.assertEqual(
            expected_stays,
            {
                (item["trip_index"], item["source_ref"])
                for item in checklist if item["kind"] == "lodging"
            },
        )
        self.assertEqual(
            expected_unknowns,
            sorted(
                (item["trip_index"], item["field_path"])
                for item in checklist if item["kind"] == "unknown"
            ),
        )
        deadline_keys = [
            (item["deadline"][:10], 0 if len(item["deadline"]) == 10 else 1, item["deadline"])
            for item in checklist
        ]
        self.assertEqual(sorted(deadline_keys), deadline_keys)
        for item in checklist:
            self.assertJourneyItemTraceable(journey, item)

    def test_risks_cover_every_missing_or_degraded_capability_conflict_and_unknown(self):
        journey = copy.deepcopy(self.result.journey)
        journey["trips"][0]["provider_health"][0]["status"] = "degraded"
        journey["trips"][0]["claims"][0]["status"] = "conflict"
        risks = journey_risk_items(journey)
        journey_report = validate_journey(journey)
        self.assertTrue(journey_report.ok, [item.render() for item in journey_report.errors])

        expected_capabilities = {
            (trip_index, health["provider"], capability, health["status"])
            for trip_index, trip in enumerate(journey["trips"])
            for health in trip["provider_health"]
            if health["status"] in ("degraded", "missing")
            for capability in health["capabilities"]
        }
        actual_capabilities = {
            (item["trip_index"], item["provider"], item["capability"], item["status"])
            for item in risks if item["kind"] == "provider_capability"
        }
        self.assertEqual(expected_capabilities, actual_capabilities)
        self.assertEqual(
            {(0, journey["trips"][0]["claims"][0]["claim_id"])},
            {
                (item["trip_index"], item["claim_id"])
                for item in risks if item["kind"] == "claim_conflict"
            },
        )
        self.assertEqual(
            sum(len(trip["unknowns"]) for trip in journey["trips"]),
            sum(item["kind"] == "unresolved_unknown" for item in risks),
        )
        for item in risks:
            self.assertJourneyItemTraceable(journey, item)
        rendered = render_journey(journey)
        html_report = validate_journey_html(rendered, journey)
        self.assertTrue(html_report.ok, [item.render() for item in html_report.errors])

    def test_journey_overview_is_deterministic_valid_and_hides_internal_ids(self):
        journey = self.result.journey
        first = render_journey(journey)
        second = render_journey(copy.deepcopy(journey))
        self.assertEqual(first.encode("utf-8"), second.encode("utf-8"))
        self.assertEqual(
            hashlib.sha256(first.encode("utf-8")).hexdigest(),
            hashlib.sha256(second.encode("utf-8")).hexdigest(),
        )
        report = validate_journey_html(first, journey)
        self.assertTrue(report.ok, [item.render() for item in report.errors])
        parser = AuditParser()
        parser.feed(first)
        parser.close()
        visible = " ".join(parser.visible_text)
        for expected in ("全程路线", "预订与核验清单", "风险与未解决项", "CNY 4200", "北京", "上海", "杭州", "苏州"):
            self.assertIn(expected, visible)
        internal_ids = [journey["journey_id"]] + [trip["trip_id"] for trip in journey["trips"]]
        internal_ids.extend(
            leg["leg_id"] for trip in journey["trips"] for leg in trip["transport_legs"]
        )
        self.assertTrue(all(identifier not in visible for identifier in internal_ids))

    def test_journey_overview_budget_route_and_segment_facts_match_source(self):
        journey = self.result.journey
        rendered = render_journey(journey)
        parser = AuditParser()
        parser.feed(rendered)
        parser.close()
        budget = next(attrs for _, attrs in parser.all_attrs if "data-budget-currency" in attrs)
        self.assertEqual("4200", budget["data-budget-known"])
        self.assertEqual("", budget["data-budget-min"])
        self.assertEqual("", budget["data-budget-max"])
        self.assertEqual("incomplete", budget["data-budget-status"])
        self.assertEqual(3, sum("data-route-index" in attrs for _, attrs in parser.all_attrs))
        self.assertEqual(3, sum("data-segment-index" in attrs for _, attrs in parser.all_attrs))

    def test_journey_html_rejects_loosened_csp(self):
        journey = self.result.journey
        rendered = render_journey(journey)
        mutated = rendered.replace("script-src &#x27;none&#x27;", "script-src https:", 1)
        self.assertNotEqual(rendered, mutated)
        codes = {item.code for item in validate_journey_html(mutated, journey).errors}
        self.assertIn("JH102", codes)

    def test_journey_html_rejects_missing_checklist_item(self):
        journey = self.result.journey
        rendered = render_journey(journey)
        mutated = re.sub(
            r'<li class="checklist-item".*?</li>',
            "",
            rendered,
            count=1,
            flags=re.DOTALL,
        )
        self.assertNotEqual(rendered, mutated)
        codes = {item.code for item in validate_journey_html(mutated, journey).errors}
        self.assertIn("JH202", codes)

    def test_journey_html_rejects_missing_risk_item(self):
        journey = self.result.journey
        rendered = render_journey(journey)
        mutated = re.sub(
            r'<li class="risk-item".*?</li>',
            "",
            rendered,
            count=1,
            flags=re.DOTALL,
        )
        self.assertNotEqual(rendered, mutated)
        codes = {item.code for item in validate_journey_html(mutated, journey).errors}
        self.assertIn("JH203", codes)

    def test_journey_html_rejects_visible_internal_id(self):
        journey = self.result.journey
        rendered = render_journey(journey)
        mutated = rendered.replace(
            "</footer>",
            "<p>%s</p></footer>" % journey["journey_id"],
            1,
        )
        codes = {item.code for item in validate_journey_html(mutated, journey).errors}
        self.assertIn("JH205", codes)

    def test_cli_renders_and_validates_the_journey_overview(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            output = Path(temporary)
            journey_path = output / "journey.json"
            html_path = output / "journey.html"
            journey_path.write_text(
                json.dumps(self.result.journey, ensure_ascii=False),
                encoding="utf-8",
            )
            rendered = subprocess.run(
                [str(CTW), "journey", "render", str(journey_path), "--output", str(html_path)],
                text=True,
                capture_output=True,
            )
            checked = subprocess.run(
                [str(CTW), "journey", "validate-html", str(html_path), str(journey_path)],
                text=True,
                capture_output=True,
            )
            self.assertEqual(0, rendered.returncode, rendered.stdout + rendered.stderr)
            self.assertIn("JOURNEY_RENDERED", rendered.stdout)
            self.assertIn("errors=0", rendered.stdout)
            self.assertEqual(0, checked.returncode, checked.stdout + checked.stderr)
            self.assertIn("JOURNEY HTML VALID", checked.stdout)

    def test_checked_in_sixteen_day_demo_matches_the_deterministic_renderer(self):
        journey = load(JOURNEY_DEMO / "journey.json")
        rendered = (JOURNEY_DEMO / "journey.html").read_text(encoding="utf-8")
        self.assertEqual(16, sum(len(item["days"]) for item in journey["trips"]))
        self.assertEqual(render_journey(journey), rendered)
        report = validate_journey_html(rendered, journey)
        self.assertTrue(report.ok, [item.render() for item in report.errors])


if __name__ == "__main__":
    unittest.main()
