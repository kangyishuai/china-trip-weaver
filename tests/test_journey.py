from __future__ import annotations

import copy
import json
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
    journey_budget_ledger,
    plan_journey,
    split_journey_inputs,
    validate_journey,
)
from china_trip_weaver.planning import RailBackend, _normalize_request, plan_trip
from china_trip_weaver.replan import replan_trip
from china_trip_weaver.validate_trip import validate_trip
from scripts.build_plan_fixtures import journey_sixteen_day_case


FIXED_NOW = "2026-09-05T09:00:00+08:00"
VALID_TRIP = ROOT / "tests" / "fixtures" / "trips" / "schema" / "valid" / "weekend-live.json"
GROUPED_TRIP = ROOT / "demo" / "grouped-departures" / "trip.json"
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
        request["origin"] = copy.deepcopy(request["destinations"][0])
        request["destinations"] = [copy.deepcopy(request["destinations"][0])]
        segments = split_journey_inputs(request, self.candidates)
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


if __name__ == "__main__":
    unittest.main()
