from __future__ import annotations

import copy
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

CTW = PLUGIN / "scripts" / "ctw"
WEEKEND_TRIP = ROOT / "tests" / "fixtures" / "trips" / "schema" / "valid" / "weekend-live.json"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def run_locate(*extra_args, env=None):
    return subprocess.run(
        [str(CTW), "locate", *extra_args],
        text=True, capture_output=True, env=env,
    )


def _null_out_coordinates(trip):
    trip = copy.deepcopy(trip)
    for poi in trip["pois"]:
        poi["coordinates"] = None
    for lodging in trip["lodgings"]:
        lodging["coordinates"] = None
    return trip


class LocateCommandTests(unittest.TestCase):
    def test_help_exits_zero(self):
        result = run_locate("--help", env={"PATH": "/usr/bin:/bin"})
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("--journey", result.stdout)
        self.assertIn("--trip", result.stdout)

    def test_trip_with_nothing_to_locate_exits_two_with_zero_entities(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            output = Path(temporary) / "locate.json"
            result = run_locate(
                "--trip", str(WEEKEND_TRIP), "--output-json", str(output),
                env={"PATH": "/usr/bin:/bin", "HOME": str(Path(temporary))},
            )
            self.assertEqual(2, result.returncode, result.stdout + result.stderr)
            self.assertIn("entities=0", result.stdout)
            envelope = load(output)
            self.assertEqual([], envelope["entities"])

    def test_missing_credentials_reports_every_entity_as_credential_missing(self):
        trip = _null_out_coordinates(load(WEEKEND_TRIP))
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            home = Path(temporary) / "home"
            home.mkdir()
            trip_path = Path(temporary) / "trip.json"
            trip_path.write_text(json.dumps(trip), encoding="utf-8")
            output = Path(temporary) / "locate.json"
            result = run_locate(
                "--trip", str(trip_path), "--output-json", str(output),
                env={"PATH": "/usr/bin:/bin", "HOME": str(home)},
            )
            self.assertEqual(2, result.returncode, result.stdout + result.stderr)
            envelope = load(output)
            self.assertEqual(2, len(envelope["entities"]))
            for entity in envelope["entities"]:
                self.assertEqual("provider_error", entity["status"])
                self.assertEqual("credential_missing", entity["reason"])

    def test_nonexistent_trip_file_exits_one(self):
        result = run_locate(
            "--trip", str(ROOT / ".tmp" / "does-not-exist-locate.json"),
            env={"PATH": "/usr/bin:/bin"},
        )
        self.assertEqual(1, result.returncode)
        self.assertIn("LOCATE_FAILED", result.stderr)


if __name__ == "__main__":
    unittest.main()
