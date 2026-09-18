from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "china-trip-weaver"
SRC = PLUGIN / "src"
sys.path.insert(0, str(SRC))

from china_trip_weaver.clock import FixedClock
from china_trip_weaver.contracts import canonical_json, write_canonical_json
from china_trip_weaver.journey import extract_trip_from_journey
from china_trip_weaver.replan import replan_trip

from tests.test_dining_fold import CLOCK as DINING_CLOCK, envelope as dining_envelope, options_row
from tests.test_locate_fold import CLOCK as LOCATE_CLOCK, envelope as locate_envelope, located_row
from tests.test_weather_fold import (
    CLOCK as WEATHER_CLOCK,
    envelope as weather_envelope,
    forecast_row,
    forecast_value,
)


CTW = PLUGIN / "scripts" / "ctw"
JOURNEY_DEMO = ROOT / "demo" / "journey-16d"
REPLAN_FIXTURES = ROOT / "tests" / "fixtures" / "scheduler" / "replan"
WEEKEND_LIVE_TRIP = ROOT / "tests" / "fixtures" / "trips" / "schema" / "valid" / "weekend-live.json"
FIXED_NOW = "2026-09-22T09:00:00+08:00"
FOLD_KINDS = ("weather", "dining", "locate")


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.write_text(canonical_json(value), encoding="utf-8")


def run_ctw(*args):
    return subprocess.run([str(CTW), *args], text=True, capture_output=True)


class WriteCanonicalJsonAtomicityTests(unittest.TestCase):
    """Task 0: write_canonical_json must never leave a half-written file behind."""

    def test_failed_replace_leaves_original_file_and_no_temp_files(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            directory = Path(temporary)
            path = directory / "trip.json"
            write_canonical_json(path, {"revision": 1})
            original_bytes = path.read_bytes()

            with mock.patch(
                "china_trip_weaver.contracts.os.replace",
                side_effect=OSError("simulated disk failure"),
            ):
                with self.assertRaises(OSError):
                    write_canonical_json(path, {"revision": 2})

            self.assertEqual(original_bytes, path.read_bytes())
            leftovers = [item.name for item in directory.iterdir() if item != path]
            self.assertEqual([], leftovers, leftovers)


def _weather_result():
    row1, claim1 = forecast_row(
        "上海", "2026-10-01", "上海", "310000",
        forecast_value("2026-10-01", "上海", "310000", reported_at=FIXED_NOW),
    )
    row2, claim2 = forecast_row(
        "上海", "2026-10-02", "上海", "310000",
        forecast_value("2026-10-02", "上海", "310000", reported_at=FIXED_NOW, temp_high_c=30),
    )
    return weather_envelope([row1, row2], [claim1, claim2], clock=WEATHER_CLOCK)


def _dining_result(journey_value):
    specs = [
        ("jinjiang", "锦江福味", 240),
        ("haiyang", "海阳鲜道", 420),
        ("laofuzhou", "老福州小吃", 680),
    ]
    row, claims = options_row(journey_value["trips"][0], 0, 5, specs, clock=DINING_CLOCK)
    return dining_envelope([row], claims, clock=DINING_CLOCK)


def _locate_result(journey_value):
    trip = journey_value["trips"][0]
    poi_row, poi_claim = located_row(
        trip["trip_id"], "poi", "poi-j16-shanghai", "上海合成建筑漫步", "上海", clock=LOCATE_CLOCK,
    )
    lodging_row, lodging_claim = located_row(
        trip["trip_id"], "lodging", "lodging-j16-shanghai-central", "上海合成住宿", "上海", clock=LOCATE_CLOCK,
    )
    return locate_envelope([poi_row, lodging_row], [poi_claim, lodging_claim], clock=LOCATE_CLOCK)


def _fold_result(kind, journey_value):
    if kind == "weather":
        return _weather_result()
    if kind == "dining":
        return _dining_result(journey_value)
    return _locate_result(journey_value)


def _fold_flag(kind):
    return "--%s-result" % kind


def _fold_complete_marker(kind):
    return "JOURNEY_%s_COMPLETE" % kind.upper()


def _fold_noop_marker(kind):
    return "JOURNEY_%s_NOOP" % kind.upper()


class JourneyFoldInPlaceTests(unittest.TestCase):
    """`ctw journey weather/dining/locate` writing --output-json back onto --journey."""

    def test_in_place_success_bumps_revision_for_all_three_folds(self):
        for kind in FOLD_KINDS:
            with self.subTest(kind=kind):
                with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
                    work = Path(temporary)
                    journey_path = work / "journey.json"
                    shutil.copyfile(JOURNEY_DEMO / "journey.json", journey_path)
                    journey_value = load(journey_path)
                    result_path = work / "result.json"
                    write_json(result_path, _fold_result(kind, journey_value))

                    command = run_ctw(
                        "journey", kind,
                        "--journey", str(journey_path),
                        _fold_flag(kind), str(result_path),
                        "--base-revision", "1",
                        "--fixed-clock", FIXED_NOW,
                        "--output-json", str(journey_path),
                    )
                    self.assertEqual(0, command.returncode, command.stdout + command.stderr)
                    self.assertIn(_fold_complete_marker(kind), command.stdout)
                    updated = load(journey_path)
                    self.assertEqual(2, updated["revision"]["number"])
                    self.assertEqual(1, updated["revision"]["parent_revision"])

                    validated = run_ctw("journey", "validate", str(journey_path))
                    self.assertEqual(0, validated.returncode, validated.stdout + validated.stderr)

    def test_stale_base_revision_fails_with_conflict_and_leaves_bytes_unchanged(self):
        for kind in FOLD_KINDS:
            with self.subTest(kind=kind):
                with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
                    work = Path(temporary)
                    journey_path = work / "journey.json"
                    shutil.copyfile(JOURNEY_DEMO / "journey.json", journey_path)
                    journey_value = load(journey_path)
                    result_path = work / "result.json"
                    write_json(result_path, _fold_result(kind, journey_value))

                    first = run_ctw(
                        "journey", kind,
                        "--journey", str(journey_path),
                        _fold_flag(kind), str(result_path),
                        "--base-revision", "1",
                        "--fixed-clock", FIXED_NOW,
                        "--output-json", str(journey_path),
                    )
                    self.assertEqual(0, first.returncode, first.stdout + first.stderr)
                    settled_bytes = journey_path.read_bytes()

                    stale = run_ctw(
                        "journey", kind,
                        "--journey", str(journey_path),
                        _fold_flag(kind), str(result_path),
                        "--base-revision", "1",
                        "--fixed-clock", FIXED_NOW,
                        "--output-json", str(journey_path),
                    )
                    self.assertEqual(1, stale.returncode, stale.stdout + stale.stderr)
                    self.assertIn("revision_conflict", stale.stderr)
                    self.assertEqual(settled_bytes, journey_path.read_bytes())

    def test_noop_fold_leaves_bytes_unchanged(self):
        for kind in FOLD_KINDS:
            with self.subTest(kind=kind):
                with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
                    work = Path(temporary)
                    journey_path = work / "journey.json"
                    shutil.copyfile(JOURNEY_DEMO / "journey.json", journey_path)
                    journey_value = load(journey_path)
                    result_path = work / "result.json"
                    write_json(result_path, _fold_result(kind, journey_value))

                    first = run_ctw(
                        "journey", kind,
                        "--journey", str(journey_path),
                        _fold_flag(kind), str(result_path),
                        "--base-revision", "1",
                        "--fixed-clock", FIXED_NOW,
                        "--output-json", str(journey_path),
                    )
                    self.assertEqual(0, first.returncode, first.stdout + first.stderr)
                    settled_bytes = journey_path.read_bytes()

                    noop = run_ctw(
                        "journey", kind,
                        "--journey", str(journey_path),
                        _fold_flag(kind), str(result_path),
                        "--base-revision", "2",
                        "--fixed-clock", FIXED_NOW,
                        "--output-json", str(journey_path),
                    )
                    self.assertEqual(2, noop.returncode, noop.stdout + noop.stderr)
                    self.assertIn(_fold_noop_marker(kind), noop.stdout)
                    self.assertEqual(settled_bytes, journey_path.read_bytes())


class JourneyAssembleReplaceTripInPlaceTests(unittest.TestCase):
    """`ctw journey assemble --replace-trip` writing --output-json back onto --journey."""

    def _replacement_trip(self, journey_value):
        trip_id = journey_value["trips"][0]["trip_id"]
        trip = extract_trip_from_journey(journey_value, trip_id)
        event = {
            "type": "delay",
            "subject_ref": "slot-poi-routine-meal-2acb635f18d4",
            "delta_minutes": 15,
            "reason": "接驳晚点 15 分钟",
        }
        result = replan_trip(trip, event, 1, [], FixedClock.from_iso(FIXED_NOW))
        return result.trip

    def test_in_place_update_bumps_revision_and_validates(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            work = Path(temporary)
            journey_path = work / "journey.json"
            shutil.copyfile(JOURNEY_DEMO / "journey.json", journey_path)
            journey_value = load(journey_path)
            replacement_path = work / "trip-r2.json"
            write_json(replacement_path, self._replacement_trip(journey_value))

            command = run_ctw(
                "journey", "assemble",
                "--journey", str(journey_path),
                "--replace-trip", str(replacement_path),
                "--base-revision", "1",
                "--fixed-clock", FIXED_NOW,
                "--output-json", str(journey_path),
            )
            self.assertEqual(0, command.returncode, command.stdout + command.stderr)
            self.assertIn("JOURNEY_ASSEMBLE_COMPLETE", command.stdout)
            updated = load(journey_path)
            self.assertEqual(2, updated["revision"]["number"])
            self.assertEqual(journey_value["journey_id"], updated["journey_id"])

            validated = run_ctw("journey", "validate", str(journey_path))
            self.assertEqual(0, validated.returncode, validated.stdout + validated.stderr)

    def test_stale_base_revision_fails_with_conflict_and_leaves_bytes_unchanged(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            work = Path(temporary)
            journey_path = work / "journey.json"
            shutil.copyfile(JOURNEY_DEMO / "journey.json", journey_path)
            journey_value = load(journey_path)
            replacement_path = work / "trip-r2.json"
            write_json(replacement_path, self._replacement_trip(journey_value))

            first = run_ctw(
                "journey", "assemble",
                "--journey", str(journey_path),
                "--replace-trip", str(replacement_path),
                "--base-revision", "1",
                "--fixed-clock", FIXED_NOW,
                "--output-json", str(journey_path),
            )
            self.assertEqual(0, first.returncode, first.stdout + first.stderr)
            settled_bytes = journey_path.read_bytes()

            stale = run_ctw(
                "journey", "assemble",
                "--journey", str(journey_path),
                "--replace-trip", str(replacement_path),
                "--base-revision", "1",
                "--fixed-clock", FIXED_NOW,
                "--output-json", str(journey_path),
            )
            self.assertEqual(1, stale.returncode, stale.stdout + stale.stderr)
            self.assertIn("revision_conflict", stale.stderr)
            self.assertEqual(settled_bytes, journey_path.read_bytes())


class ReplanInPlaceTests(unittest.TestCase):
    """`ctw replan` writing --output-json/--output-html back onto --trip's own paths."""

    def test_in_place_update_bumps_revision_and_validates(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            work = Path(temporary)
            trip_path = work / "trip.json"
            html_path = work / "trip.html"
            shutil.copyfile(WEEKEND_LIVE_TRIP, trip_path)

            command = run_ctw(
                "replan",
                "--trip", str(trip_path),
                "--event", str(REPLAN_FIXTURES / "closure.json"),
                "--base-revision", "1",
                "--output-json", str(trip_path),
                "--output-html", str(html_path),
                "--fixed-clock", FIXED_NOW,
            )
            self.assertEqual(0, command.returncode, command.stdout + command.stderr)
            self.assertIn("REPLAN_COMPLETE", command.stdout)
            updated = load(trip_path)
            self.assertEqual(2, updated["revision"]["number"])

            validated = run_ctw("validate", str(trip_path))
            self.assertEqual(0, validated.returncode, validated.stdout + validated.stderr)

    def test_stale_base_revision_fails_with_conflict_and_leaves_bytes_unchanged(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            work = Path(temporary)
            trip_path = work / "trip.json"
            html_path = work / "trip.html"
            shutil.copyfile(WEEKEND_LIVE_TRIP, trip_path)

            first = run_ctw(
                "replan",
                "--trip", str(trip_path),
                "--event", str(REPLAN_FIXTURES / "closure.json"),
                "--base-revision", "1",
                "--output-json", str(trip_path),
                "--output-html", str(html_path),
                "--fixed-clock", FIXED_NOW,
            )
            self.assertEqual(0, first.returncode, first.stdout + first.stderr)
            settled_json_bytes = trip_path.read_bytes()
            settled_html_bytes = html_path.read_bytes()

            stale = run_ctw(
                "replan",
                "--trip", str(trip_path),
                "--event", str(REPLAN_FIXTURES / "closure.json"),
                "--base-revision", "1",
                "--output-json", str(trip_path),
                "--output-html", str(html_path),
                "--fixed-clock", FIXED_NOW,
            )
            self.assertEqual(1, stale.returncode, stale.stdout + stale.stderr)
            self.assertIn("revision_conflict", stale.stderr)
            self.assertEqual(settled_json_bytes, trip_path.read_bytes())
            self.assertEqual(settled_html_bytes, html_path.read_bytes())


class JourneyRenderIdempotencyTests(unittest.TestCase):
    def test_rendering_the_same_journey_twice_to_the_same_path_is_byte_identical(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            html_path = Path(temporary) / "journey.html"
            first = run_ctw(
                "journey", "render", str(JOURNEY_DEMO / "journey.json"), "--output", str(html_path),
            )
            self.assertEqual(0, first.returncode, first.stdout + first.stderr)
            first_bytes = html_path.read_bytes()

            second = run_ctw(
                "journey", "render", str(JOURNEY_DEMO / "journey.json"), "--output", str(html_path),
            )
            self.assertEqual(0, second.returncode, second.stdout + second.stderr)
            self.assertEqual(first_bytes, html_path.read_bytes())


if __name__ == "__main__":
    unittest.main()
