from __future__ import annotations

import contextlib
import io
import json
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

from china_trip_weaver import dining as dining_module
from china_trip_weaver.cli import main as cli_main
from china_trip_weaver.clock import FixedClock
from china_trip_weaver.geo import Point, coordinate_record
from china_trip_weaver.providers import base as providers_base

CTW = PLUGIN / "scripts" / "ctw"
AMAP_FIXTURES = ROOT / "tests" / "fixtures" / "providers" / "amap"
DEMO_JOURNEY = ROOT / "demo" / "journey-16d" / "journey.json"
CLOCK = FixedClock.from_iso("2026-09-04T00:00:00+08:00")


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def run_dining(*extra_args, env=None):
    return subprocess.run(
        [str(CTW), "dining", *extra_args],
        text=True, capture_output=True, env=env,
    )


def _write_json(directory, name: str, value) -> Path:
    path = Path(directory) / name
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _trip_with_lodging_coordinates():
    """The demo's first Trip (5 days, 10 meal slots) with its one lodging
    given coordinates. The lunch and dinner slots on day 0 both anchor to
    that same checkin, via anchor_for's backward/forward search; every other
    day has no coordinate-bearing slot at all, so their meals stay unanchored.
    """

    trip = load(DEMO_JOURNEY)["trips"][0]
    trip["lodgings"][0]["coordinates"] = coordinate_record(
        "GCJ02", Point(121.47, 31.23), CLOCK, accuracy_m=30,
    )
    return trip


class DiningCommandTests(unittest.TestCase):
    """End-to-end subprocess coverage for `ctw dining` (`_cmd_dining`, cli.py).

    Every fixture-driven case replays the checked-in
    tests/fixtures/providers/amap/around_dining.json response, the same
    style tests/test_weather_cli.py uses for `ctw weather`. Before this
    file, no test invoked `ctw dining` at all.
    """

    def test_anchored_slots_return_three_rated_options_with_int_distance_and_matching_claims(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            trip_path = _write_json(temporary, "trip.json", _trip_with_lodging_coordinates())
            output_path = Path(temporary) / "dining.json"
            result = run_dining(
                "--trip", str(trip_path),
                "--fixture", str(AMAP_FIXTURES / "around_dining.json"),
                "--fixed-clock", "2026-09-04T00:00:00+08:00",
                "--output-json", str(output_path),
            )
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn("DINING_COMPLETE", result.stdout)
            data = load(output_path)

        anchored = [slot for slot in data["slots"] if slot["anchor"] is not None]
        self.assertEqual(2, len(anchored))
        claim_ids = {claim["claim_id"] for claim in data["claims"]}
        for slot in anchored:
            self.assertEqual("options", slot["status"])
            self.assertEqual(3, len(slot["options"]))
            for option in slot["options"]:
                self.assertIsInstance(option["distance_m"], int)
                self.assertIn(option["claim_id"], claim_ids)
        # The lunch and dinner slots share the lodging's coordinates, so the
        # (location, keywords) dedup should fire the AMap query only once:
        # 6 fixture POIs x 2 claims (identity + business) = 12, not 24.
        self.assertEqual(12, len(data["claims"]))

    def test_avoid_word_excludes_matching_restaurant_from_every_anchored_slot(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            trip_path = _write_json(temporary, "trip.json", _trip_with_lodging_coordinates())
            output_path = Path(temporary) / "dining.json"
            result = run_dining(
                "--trip", str(trip_path),
                "--fixture", str(AMAP_FIXTURES / "around_dining.json"),
                "--fixed-clock", "2026-09-04T00:00:00+08:00",
                "--avoid", "火锅",
                "--output-json", str(output_path),
            )
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            data = load(output_path)

        anchored = [slot for slot in data["slots"] if slot["anchor"] is not None]
        self.assertEqual(2, len(anchored))
        for slot in anchored:
            self.assertEqual(3, len(slot["options"]))
            for option in slot["options"]:
                self.assertNotIn("火锅", option["name"])
                self.assertNotIn("火锅", option.get("tag") or "")
                self.assertNotIn("火锅", option.get("cuisine") or "")

    def test_journey_without_coordinates_reports_no_anchor_and_exits_two(self):
        result = run_dining(
            "--journey", str(DEMO_JOURNEY),
            "--fixture", str(AMAP_FIXTURES / "around_dining.json"),
            "--fixed-clock", "2026-09-04T00:00:00+08:00",
        )
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        self.assertTrue(lines)
        self.assertTrue(all("无锚点" in line for line in lines))

        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            output_path = Path(temporary) / "dining.json"
            result = run_dining(
                "--journey", str(DEMO_JOURNEY),
                "--fixture", str(AMAP_FIXTURES / "around_dining.json"),
                "--fixed-clock", "2026-09-04T00:00:00+08:00",
                "--output-json", str(output_path),
            )
            self.assertEqual(2, result.returncode, result.stdout + result.stderr)
            self.assertIn("with_options=0", result.stdout)
            data = load(output_path)
        self.assertTrue(data["slots"])
        self.assertTrue(all(slot["status"] == "no_anchor" for slot in data["slots"]))

    def test_text_mode_prints_one_line_per_slot_with_arrow_marker(self):
        trip = _trip_with_lodging_coordinates()
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            trip_path = _write_json(temporary, "trip.json", trip)
            result = run_dining(
                "--trip", str(trip_path),
                "--fixture", str(AMAP_FIXTURES / "around_dining.json"),
                "--fixed-clock", "2026-09-04T00:00:00+08:00",
            )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        self.assertEqual(len(dining_module.meal_slots(trip)), len(lines))
        anchored_lines = [line for line in lines if "无锚点" not in line]
        self.assertTrue(anchored_lines)
        self.assertTrue(all("←" in line for line in anchored_lines))

    def test_shared_anchor_dedupes_the_amap_query_to_one_call(self):
        """Guards the (location, keywords) cache: without it, this in-process
        run's lunch and dinner slots (same lodging anchor, day 0) would each
        fire their own AMap call instead of sharing one.
        """

        original_execute = providers_base.ReplayTransport.execute
        calls = []

        def counting_execute(self, provider, request):
            calls.append(request.parameters)
            return original_execute(self, provider, request)

        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            trip_path = _write_json(temporary, "trip.json", _trip_with_lodging_coordinates())
            output_path = Path(temporary) / "dining.json"
            with mock.patch.object(providers_base.ReplayTransport, "execute", counting_execute):
                with contextlib.redirect_stdout(io.StringIO()):
                    status = cli_main([
                        "dining", "--trip", str(trip_path),
                        "--fixture", str(AMAP_FIXTURES / "around_dining.json"),
                        "--fixed-clock", "2026-09-04T00:00:00+08:00",
                        "--output-json", str(output_path),
                    ])
            self.assertEqual(0, status)
        self.assertEqual(1, len(calls))


if __name__ == "__main__":
    unittest.main()
