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

CTW = PLUGIN / "scripts" / "ctw"
RAIL_FIXTURES = ROOT / "tests" / "fixtures" / "providers" / "rail12306"

EXPECTED_OUTPUT_KEYS = {
    "provider",
    "provider_version",
    "queried_at",
    "transport_legs",
    "claims",
    "health",
    "warnings",
    "error_class",
}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def run_rail(fixture_name, output_path, from_name="北京", to_name="上海", date="2026-09-10"):
    return subprocess.run(
        [
            str(CTW), "rail",
            "--date", date,
            "--from", from_name,
            "--to", to_name,
            "--fixture", str(RAIL_FIXTURES / fixture_name),
            "--output-json", str(output_path),
        ],
        text=True,
        capture_output=True,
    )


class RailCommandTests(unittest.TestCase):
    """End-to-end subprocess coverage for `ctw rail` (`_cmd_rail`, cli.py).

    Every case drives the real CLI entry point against a checked-in
    tests/fixtures/providers/rail12306/*.json replay fixture, the same
    style tests/test_journey.py and tests/test_renderer.py use for other
    subcommands. Before this file, no test invoked `ctw rail` at all.
    """

    def test_success_fixture_returns_ready_leg_with_expected_json_shape(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            output = Path(temporary) / "success.json"
            result = run_rail("success.json", output)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn("RAIL_COMPLETE", result.stdout)
            self.assertIn("legs=1", result.stdout)
            self.assertIn("status=ready", result.stdout)
            self.assertIn("error=none", result.stdout)
            data = load(output)
            self.assertEqual(EXPECTED_OUTPUT_KEYS, set(data.keys()))
            self.assertEqual("12306-mcp", data["provider"])
            self.assertIsNone(data["error_class"])
            self.assertEqual("ready", data["health"]["status"])
            self.assertEqual(1, len(data["transport_legs"]))
            self.assertEqual("rail", data["transport_legs"][0]["travel_mode"])
            self.assertTrue(data["claims"])

    def test_empty_fixture_returns_no_results_with_exit_code_two(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            output = Path(temporary) / "empty.json"
            result = run_rail("empty.json", output, from_name="北京", to_name="北京")
            self.assertEqual(2, result.returncode, result.stdout + result.stderr)
            self.assertIn("error=no_results", result.stdout)
            data = load(output)
            self.assertEqual(EXPECTED_OUTPUT_KEYS, set(data.keys()))
            self.assertEqual("no_results", data["error_class"])
            self.assertEqual([], data["transport_legs"])
            self.assertIn("no_results", data["warnings"])

    def test_wrong_shape_fixture_returns_contract_mismatch_with_exit_code_one(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            output = Path(temporary) / "wrong_shape.json"
            result = run_rail("wrong_shape.json", output)
            self.assertEqual(1, result.returncode, result.stdout + result.stderr)
            self.assertIn("status=contract_mismatch", result.stdout)
            data = load(output)
            self.assertEqual(EXPECTED_OUTPUT_KEYS, set(data.keys()))
            self.assertEqual("contract_mismatch", data["error_class"])
            self.assertEqual("contract_mismatch", data["health"]["status"])
            self.assertEqual([], data["transport_legs"])

    def test_transfer_fixture_returns_two_legs(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            output = Path(temporary) / "transfer.json"
            result = run_rail("transfer.json", output)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn("legs=2", result.stdout)
            data = load(output)
            self.assertEqual(EXPECTED_OUTPUT_KEYS, set(data.keys()))
            self.assertEqual(2, len(data["transport_legs"]))
            for leg in data["transport_legs"]:
                self.assertEqual("rail", leg["travel_mode"])
                self.assertIn("leg_id", leg)

    def test_missing_fixture_file_fails_with_exit_code_one(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            output = Path(temporary) / "missing.json"
            result = run_rail("does-not-exist.json", output)
            self.assertEqual(1, result.returncode, result.stdout + result.stderr)
            self.assertIn("RAIL_FAILED", result.stderr)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
