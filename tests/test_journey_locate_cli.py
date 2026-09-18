from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "china-trip-weaver"
SRC = PLUGIN / "src"
sys.path.insert(0, str(SRC))

from china_trip_weaver.contracts import canonical_json

from tests.test_locate_fold import CLOCK, envelope, located_row


CTW = PLUGIN / "scripts" / "ctw"
JOURNEY_DEMO = ROOT / "demo" / "journey-16d"
FIXED_NOW = "2026-09-22T09:00:00+08:00"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.write_text(canonical_json(value), encoding="utf-8")


def run_journey_locate(*extra_args):
    return subprocess.run(
        [str(CTW), "journey", "locate", *extra_args],
        text=True,
        capture_output=True,
    )


class JourneyLocateCommandTests(unittest.TestCase):
    def setUp(self):
        self.journey = load(JOURNEY_DEMO / "journey.json")
        trip = self.journey["trips"][0]
        poi_row, poi_claim = located_row(
            trip["trip_id"], "poi", "poi-j16-shanghai", "上海合成建筑漫步", "上海", clock=CLOCK,
        )
        lodging_row, lodging_claim = located_row(
            trip["trip_id"], "lodging", "lodging-j16-shanghai-central", "上海合成住宿", "上海", clock=CLOCK,
        )
        self.result = envelope([poi_row, lodging_row], [poi_claim, lodging_claim], clock=CLOCK)

    def test_fold_writes_revision_two_and_validates_and_renders(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            output = Path(temporary)
            locate_result_path = output / "locate-result.json"
            write_json(locate_result_path, self.result)
            journey_out = output / "journey.json"

            result = run_journey_locate(
                "--journey", str(JOURNEY_DEMO / "journey.json"),
                "--locate-result", str(locate_result_path),
                "--base-revision", "1",
                "--fixed-clock", FIXED_NOW,
                "--output-json", str(journey_out),
            )
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn("JOURNEY_LOCATE_COMPLETE", result.stdout)
            self.assertIn("revision=2", result.stdout)
            self.assertIn("trips_changed=1", result.stdout)
            updated = load(journey_out)
            self.assertEqual(2, updated["revision"]["number"])
            self.assertEqual(1, updated["revision"]["parent_revision"])
            self.assertEqual("system", updated["revision"]["created_by"])

            validated = subprocess.run(
                [str(CTW), "journey", "validate", str(journey_out)],
                text=True, capture_output=True,
            )
            self.assertEqual(0, validated.returncode, validated.stdout + validated.stderr)

            rendered_html = output / "journey.html"
            rendered = subprocess.run(
                [str(CTW), "journey", "render", str(journey_out), "--output", str(rendered_html)],
                text=True, capture_output=True,
            )
            self.assertEqual(0, rendered.returncode, rendered.stdout + rendered.stderr)

            validated_html = subprocess.run(
                [str(CTW), "journey", "validate-html", str(rendered_html), str(journey_out)],
                text=True, capture_output=True,
            )
            self.assertEqual(0, validated_html.returncode, validated_html.stdout + validated_html.stderr)
            self.assertIn("errors=0", validated_html.stdout)

    def test_already_folded_envelope_is_noop_and_writes_nothing(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            output = Path(temporary)
            locate_result_path = output / "locate-result.json"
            write_json(locate_result_path, self.result)
            first_out = output / "journey-r2.json"
            first = run_journey_locate(
                "--journey", str(JOURNEY_DEMO / "journey.json"),
                "--locate-result", str(locate_result_path),
                "--base-revision", "1",
                "--fixed-clock", FIXED_NOW,
                "--output-json", str(first_out),
            )
            self.assertEqual(0, first.returncode, first.stdout + first.stderr)

            noop_out = output / "journey-noop.json"
            second = run_journey_locate(
                "--journey", str(first_out),
                "--locate-result", str(locate_result_path),
                "--base-revision", "2",
                "--fixed-clock", FIXED_NOW,
                "--output-json", str(noop_out),
            )
            self.assertEqual(2, second.returncode, second.stdout + second.stderr)
            self.assertIn("JOURNEY_LOCATE_NOOP", second.stdout)
            self.assertFalse(noop_out.exists())

    def test_wrong_base_revision_fails_with_revision_conflict(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            output = Path(temporary)
            locate_result_path = output / "locate-result.json"
            write_json(locate_result_path, self.result)
            journey_out = output / "journey.json"

            result = run_journey_locate(
                "--journey", str(JOURNEY_DEMO / "journey.json"),
                "--locate-result", str(locate_result_path),
                "--base-revision", "7",
                "--fixed-clock", FIXED_NOW,
                "--output-json", str(journey_out),
            )
            self.assertEqual(1, result.returncode, result.stdout + result.stderr)
            self.assertIn("JOURNEY_LOCATE_FAILED", result.stderr)
            self.assertIn("revision_conflict", result.stderr)
            self.assertFalse(journey_out.exists())


if __name__ == "__main__":
    unittest.main()
