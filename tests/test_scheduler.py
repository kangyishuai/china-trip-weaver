from __future__ import annotations

import copy
import hashlib
import json
import random
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "plugins" / "china-trip-weaver" / "src"
sys.path.insert(0, str(SRC))

from china_trip_weaver.contracts import canonical_json
from china_trip_weaver.matrix import MatrixError, RouteCell, RouteMatrix, bounded_query_plan, static_estimate_cell
from china_trip_weaver.pipeline import PipelineError, PipelineRun
from china_trip_weaver.scheduler.light import PACE_PROFILES, LightScheduler
from china_trip_weaver.scheduler.ortools_bridge import ortools_available, should_use_ortools


FIXTURES = ROOT / "tests" / "fixtures" / "scheduler"
GOLDEN = FIXTURES / "golden"
NO_SOLUTION = FIXTURES / "no_solution"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def budget_day(day_id, travel_date, cost_cny, required=False):
    return {
        "day_id": day_id,
        "date": travel_date,
        "start_at": "%sT09:00:00+08:00" % travel_date,
        "end_at": "%sT20:00:00+08:00" % travel_date,
        "travel_mode": "transit",
        "buffer_minutes": 0,
        "max_optional": 8,
        "max_travel_minutes": None,
        "candidates": [{
            "ref_id": "candidate-" + day_id,
            "title": "预算候选 " + day_id,
            "kind": "poi",
            "duration_minutes": 60,
            "windows": [],
            "utility": 100,
            "required": required,
            "locked": False,
            "fixed_start": None,
            "cost_cny": cost_cny,
            "closed": False,
            "blocked_reason": None,
        }],
        "matrix": [],
    }


def compare_golden(testcase: unittest.TestCase, path: Path):
    fixture = load(path)
    actual = LightScheduler().schedule_plan(fixture["days"])
    testcase.assertEqual("SCHEDULED", actual["status"])
    testcase.assertEqual(len(fixture["expected"]["days"]), len(actual["days"]))
    for problem, expected, day_result in zip(fixture["days"], fixture["expected"]["days"], actual["days"]):
        testcase.assertEqual("SCHEDULED", day_result["status"])
        testcase.assertEqual(expected["selected_ids"], [slot["ref_id"] for slot in day_result["slots"]])
        testcase.assertEqual(expected["start_at"], [slot["start_at"] for slot in day_result["slots"]])
        testcase.assertEqual(expected["end_at"], [slot["end_at"] for slot in day_result["slots"]])
        testcase.assertEqual(expected["excluded"], day_result["excluded"])
        testcase.assertEqual(expected["objective_vector"], day_result["objective_vector"])
        testcase.assertEqual(len(day_result["slots"]), len({slot["ref_id"] for slot in day_result["slots"]}))
        for slot in day_result["slots"]:
            testcase.assertLess(datetime.fromisoformat(slot["start_at"]), datetime.fromisoformat(slot["end_at"]))
        for previous, current in zip(day_result["slots"], day_result["slots"][1:]):
            testcase.assertLessEqual(datetime.fromisoformat(previous["end_at"]), datetime.fromisoformat(current["start_at"]))
        matrix = RouteMatrix.from_mappings(problem["matrix"])
        testcase.assertEqual((), matrix.coverage(expected["selected_ids"], problem["travel_mode"]))


def compare_no_solution(testcase: unittest.TestCase, path: Path):
    fixture = load(path)
    actual = LightScheduler().schedule_plan(fixture["days"])
    testcase.assertEqual("NO_SOLUTION", actual["status"])
    testcase.assertEqual(fixture["expected"]["conflict_code"], actual["conflict"]["code"])
    failed_day = next(day for day in actual["days"] if day["status"] == "NO_SOLUTION")
    testcase.assertEqual([], failed_day["slots"])
    testcase.assertTrue(failed_day["conflict"]["message"])
    testcase.assertTrue(failed_day["relaxations"])


class SchedulerCorpusTests(unittest.TestCase):
    def test_pace_profiles_match_daily_limits(self):
        self.assertEqual(
            {
                "slow": ("09:00", "20:00", 3, 1.5, 90),
                "balanced": ("08:30", "21:30", 5, 2.5, 60),
                "full": ("08:00", "22:30", 7, 4.0, 30),
            },
            {
                name: (
                    profile.start_time,
                    profile.end_time,
                    profile.max_pois,
                    profile.max_walking_segment_km,
                    profile.lunch_rest_minutes,
                )
                for name, profile in PACE_PROFILES.items()
            },
        )

    def test_trip_budget_reserves_later_required_cost_before_optional_fill(self):
        days = [
            budget_day("day-1", "2026-10-16", 70, required=False),
            budget_day("day-2", "2026-10-17", 60, required=True),
        ]
        result = LightScheduler().schedule_plan(days, budget_cny=100)
        self.assertEqual("SCHEDULED", result["status"])
        self.assertEqual([], result["days"][0]["slots"])
        self.assertEqual(["candidate-day-2"], [item["ref_id"] for item in result["days"][1]["slots"]])
        self.assertEqual(60, result["budget_ledger"]["known_cost_cny"])
        self.assertEqual(40, result["budget_ledger"]["remaining_known_cny"])
        self.assertEqual("within_budget", result["budget_ledger"]["status"])

    def test_trip_budget_returns_structured_no_solution_when_required_total_exceeds_it(self):
        days = [
            budget_day("day-1", "2026-10-16", 60, required=True),
            budget_day("day-2", "2026-10-17", 50, required=True),
        ]
        result = LightScheduler().schedule_plan(days, budget_cny=100)
        self.assertEqual("NO_SOLUTION", result["status"])
        self.assertEqual("budget", result["conflict"]["code"])
        self.assertEqual("over_budget", result["budget_ledger"]["status"])
        self.assertEqual(110, result["budget_ledger"]["known_cost_cny"])

    def test_unknown_candidate_cost_is_reported_instead_of_coerced_to_zero(self):
        result = LightScheduler().schedule_plan(
            [budget_day("day-1", "2026-10-16", None)],
            budget_cny=100,
        )
        self.assertEqual("SCHEDULED", result["status"])
        self.assertEqual("incomplete", result["budget_ledger"]["status"])
        self.assertEqual(["candidate-day-1"], result["budget_ledger"]["unknown_cost_refs"])
        self.assertEqual(
            ["candidate-day-1"],
            result["days"][0]["objective_vector"]["unknown_cost_refs"],
        )

    def test_senior_heavy_candidates_require_a_recovery_between_them(self):
        problem = {
            "day_id": "senior-day",
            "date": "2026-10-16",
            "pace": "balanced",
            "travel_mode": "transit",
            "buffer_minutes": 0,
            "max_optional": 8,
            "requires_senior_recovery": True,
            "candidates": [
                {
                    "ref_id": "heavy-a", "title": "重体力 A", "kind": "poi",
                    "duration_minutes": 60, "windows": [], "utility": 100,
                    "required": True, "locked": False, "fixed_start": None,
                    "cost_cny": 0, "physical_intensity": "heavy",
                    "closed": False, "blocked_reason": None,
                },
                {
                    "ref_id": "recovery", "public_ref_id": None, "title": "恢复",
                    "kind": "rest", "duration_minutes": 30, "windows": [],
                    "utility": 0, "required": True, "locked": False,
                    "fixed_start": None, "cost_cny": 0, "locationless": True,
                    "recovery": True, "closed": False, "blocked_reason": None,
                },
                {
                    "ref_id": "heavy-b", "title": "重体力 B", "kind": "poi",
                    "duration_minutes": 60, "windows": [], "utility": 90,
                    "required": True, "locked": False, "fixed_start": None,
                    "cost_cny": 0, "physical_intensity": "heavy",
                    "closed": False, "blocked_reason": None,
                },
            ],
            "matrix": [
                {
                    "from_ref": left, "to_ref": right, "travel_mode": "transit",
                    "duration_minutes": 10, "distance_meters": 500,
                    "provider": "synthetic-recovery", "provider_version": "1",
                    "mode": "static", "queried_at": None, "claim_ids": [],
                    "reachable": True, "degradation_rung": "R3",
                    "estimate_method": "synthetic", "fare": None, "geometry_ref": None,
                }
                for left, right in (("heavy-a", "heavy-b"), ("heavy-b", "heavy-a"))
            ],
        }
        result = LightScheduler().schedule_day(problem)
        self.assertEqual("SCHEDULED", result.status)
        kinds = [item["kind"] for item in result.slots]
        heavy_positions = [index for index, item in enumerate(result.slots) if item["ref_id"] in ("heavy-a", "heavy-b")]
        self.assertIn("rest", kinds[heavy_positions[0] + 1:heavy_positions[1]])

        without_recovery = copy.deepcopy(problem)
        without_recovery["candidates"] = [
            item for item in without_recovery["candidates"] if item["ref_id"] != "recovery"
        ]
        failed = LightScheduler().schedule_day(without_recovery)
        self.assertEqual("NO_SOLUTION", failed.status)
        self.assertEqual("senior-recovery-required", failed.conflict["code"])

    def test_manifest_hashes_counts_and_coverage(self):
        manifest = load(FIXTURES / "manifest.json")
        self.assertEqual({"golden": 20, "no_solution": 8, "replan": 4}, manifest["counts"])
        for entry in manifest["files"]:
            data = (FIXTURES / entry["path"]).read_bytes()
            self.assertEqual(entry["sha256"], hashlib.sha256(data).hexdigest(), entry["path"])
        tags = set()
        for path in GOLDEN.glob("*.json"):
            tags.update(load(path)["tags"])
        self.assertTrue({"1-day", "2-day", "cross-city", "moving-day", "opening-window", "budget", "walking-limit", "unreachable", "tie", "candidate>8"}.issubset(tags))

    def test_determinism_twenty_runs(self):
        fixture = load(GOLDEN / "candidate-prune-threshold.json")
        outputs = [canonical_json(LightScheduler().schedule_plan(fixture["days"])) for _ in range(20)]
        self.assertEqual(1, len(set(outputs)))

    def test_increasing_travel_time_never_selects_more(self):
        fixture = load(GOLDEN / "weekend-1-basic.json")
        baseline = LightScheduler().schedule_day(fixture["days"][0])
        slower = copy.deepcopy(fixture["days"][0])
        for cell in slower["matrix"]:
            if cell["duration_minutes"] is not None:
                cell["duration_minutes"] += 180
        changed = LightScheduler().schedule_day(slower)
        self.assertLessEqual(len(changed.slots), len(baseline.slots))

    def test_deleting_optional_candidate_preserves_hard_feasibility(self):
        fixture = load(GOLDEN / "weekend-1-meal.json")
        problem = copy.deepcopy(fixture["days"][0])
        problem["candidates"] = [item for item in problem["candidates"] if item["ref_id"] != "meal-z"]
        problem["matrix"] = [cell for cell in problem["matrix"] if cell["from_ref"] != "meal-z" and cell["to_ref"] != "meal-z"]
        result = LightScheduler().schedule_day(problem)
        self.assertEqual("SCHEDULED", result.status)
        self.assertIn("meal-m", [slot["ref_id"] for slot in result.slots])

    def test_fixed_seed_generated_invariants(self):
        rng = random.Random(20260903)
        for case_index in range(20):
            count = rng.randint(2, 5)
            refs = ["prop-%d-%d" % (case_index, index) for index in range(count)]
            candidates = [{
                "ref_id": ref,
                "title": ref,
                "kind": "poi",
                "duration_minutes": rng.randint(20, 60),
                "windows": [],
                "utility": rng.randint(10, 100),
                "required": index == 0,
                "locked": False,
                "fixed_start": None,
                "cost_cny": 0,
                "closed": False,
                "blocked_reason": None,
            } for index, ref in enumerate(refs)]
            cells = []
            for left in refs:
                for right in refs:
                    if left == right:
                        continue
                    duration = rng.randint(5, 25)
                    cells.append({
                        "from_ref": left, "to_ref": right, "travel_mode": "transit",
                        "duration_minutes": duration, "distance_meters": duration * 400,
                        "provider": "property-fixture", "provider_version": "1",
                        "mode": "live", "queried_at": "2026-09-03T12:00:00+08:00",
                        "claim_ids": ["claim-%s-%s" % (left, right)],
                        "reachable": True, "degradation_rung": "R0",
                        "estimate_method": None, "fare": None, "geometry_ref": None,
                    })
            problem = {
                "day_id": "property-day", "date": "2026-12-20",
                "start_at": "2026-12-20T09:00:00+08:00",
                "end_at": "2026-12-20T20:00:00+08:00",
                "travel_mode": "transit", "buffer_minutes": 5,
                "budget_cny": None, "max_optional": 8, "max_travel_minutes": None,
                "candidates": candidates, "matrix": cells,
            }
            result = LightScheduler().schedule_day(problem)
            self.assertEqual("SCHEDULED", result.status)
            self.assertEqual(len(result.slots), len({slot["ref_id"] for slot in result.slots}))
            matrix = RouteMatrix.from_mappings(cells)
            for previous, current in zip(result.slots, result.slots[1:]):
                previous_end = datetime.fromisoformat(previous["end_at"])
                current_start = datetime.fromisoformat(current["start_at"])
                required_gap = matrix.duration(previous["ref_id"], current["ref_id"], "transit") + 5
                self.assertGreaterEqual((current_start - previous_end).total_seconds() / 60, required_gap)

    def test_matrix_rejects_false_reachable_shapes(self):
        with self.assertRaises(MatrixError):
            RouteCell(
                from_ref="a", to_ref="b", travel_mode="walk",
                duration_minutes=12, distance_meters=500,
                provider="fixture", provider_version="1", mode="static",
                queried_at=None, claim_ids=(), reachable=False,
                degradation_rung="R4", estimate_method=None,
            ).validate()

    def test_static_estimate_is_labeled_and_bounded_query_plan_is_small(self):
        cell = static_estimate_cell("a", "b", "walk", 2000, 4.0, 10)
        self.assertEqual("static", cell.mode)
        self.assertEqual("R3", cell.degradation_rung)
        self.assertTrue(cell.estimate_method)
        plan = bounded_query_plan(
            ["a", "b", "c", "d", "e", "f", "g"],
            locked_refs=["a"], lodging_refs=["b"],
            cluster_neighbors={"c": ["a", "b", "d", "e", "f", "g"]},
        )
        self.assertIn(("a", "b"), plan)
        self.assertIn(("b", "a"), plan)
        self.assertEqual(5, len([pair for pair in plan if pair[0] == "c"]))

    def test_ortools_is_never_imported_without_explicit_flag(self):
        with mock.patch("importlib.util.find_spec") as find_spec:
            self.assertFalse(ortools_available({}))
            self.assertFalse(should_use_ortools([99], [99], 99, True, 1, {}))
            find_spec.assert_not_called()

    def test_ortools_thresholds_apply_only_after_probe(self):
        with mock.patch("importlib.util.find_spec", return_value=object()):
            self.assertTrue(should_use_ortools([9], [0], 0, False, 0, {"CTW_ENABLE_ORTOOLS": "1"}))
            self.assertFalse(should_use_ortools([8], [3], 1, False, 21, {"CTW_ENABLE_ORTOOLS": "1"}))


class PipelineTests(unittest.TestCase):
    def test_valid_pipeline_and_resume(self):
        normalized = {"city": "上海", "date": "2026-10-16", "travelers": 2}
        run = PipelineRun(normalized)
        run.advance("INTAKE", {"request": normalized}, "trip-1", 1)
        run.advance("RESEARCHED", {"claims": []}, "trip-1", 1, {"host-web": "runtime"})
        checkpoint = run.advance("CANDIDATES_READY", {"candidates": []}, "trip-1", 1, {"host-web": "runtime"})
        self.assertEqual(checkpoint, run.resume(normalized, {"host-web": "runtime"}))

    def test_pipeline_rejects_stage_skips(self):
        run = PipelineRun({"city": "上海"})
        with self.assertRaises(PipelineError) as raised:
            run.advance("RESEARCHED", {}, "trip-1", 1)
        self.assertEqual("stage_order", raised.exception.code)

    def test_pipeline_input_or_provider_change_invalidates_resume(self):
        run = PipelineRun({"city": "上海"})
        run.advance("INTAKE", {}, "trip-1", 1, {"p": "1"})
        self.assertIsNone(run.resume({"city": "北京"}, {"p": "1"}))
        self.assertIsNone(run.resume({"city": "上海"}, {"p": "2"}))

    def test_pipeline_invalidation_removes_downstream(self):
        run = PipelineRun({"city": "上海"})
        run.advance("INTAKE", {}, "trip-1", 1)
        run.advance("RESEARCHED", {}, "trip-1", 1)
        run.advance("CANDIDATES_READY", {}, "trip-1", 1)
        run.invalidate_from("RESEARCHED")
        self.assertEqual(["INTAKE"], [item.stage for item in run.checkpoints()])

    def test_pipeline_checkpoint_rejects_secret_fields(self):
        run = PipelineRun({"city": "上海"})
        with self.assertRaises(PipelineError) as raised:
            run.advance("INTAKE", {"api_key": "not-stored"}, "trip-1", 1)
        self.assertEqual("checkpoint_secret", raised.exception.code)


def _make_golden(path: Path):
    def test(self):
        compare_golden(self, path)
    return test


def _make_no_solution(path: Path):
    def test(self):
        compare_no_solution(self, path)
    return test


for _path in sorted(GOLDEN.glob("*.json")):
    setattr(SchedulerCorpusTests, "test_golden_" + _path.stem.replace("-", "_"), _make_golden(_path))
for _path in sorted(NO_SOLUTION.glob("*.json")):
    setattr(SchedulerCorpusTests, "test_no_solution_" + _path.stem.replace("-", "_"), _make_no_solution(_path))


if __name__ == "__main__":
    unittest.main()
