from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "china-trip-weaver"
SRC = PLUGIN / "src"
sys.path.insert(0, str(SRC))

from china_trip_weaver.candidates import (
    load_candidates_schema,
    validate_candidates,
)


E2E = ROOT / "tests" / "fixtures" / "e2e"
CTW = PLUGIN / "scripts" / "ctw"
VALID = sorted(E2E.glob("*/candidates.json"))
INVALID = sorted((E2E / "candidates-invalid").glob("*.json"))


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class CandidateContractTests(unittest.TestCase):
    def test_schema_reuses_frozen_trip_definitions(self):
        schema = load_candidates_schema()
        refs = {
            schema["properties"]["pois"]["items"]["$ref"],
            schema["properties"]["lodgings"]["items"]["$ref"],
            schema["properties"]["claims"]["items"]["$ref"],
            schema["properties"]["unknowns"]["items"]["$ref"],
        }
        self.assertEqual({
            "trip.schema.json#/$defs/poi",
            "trip.schema.json#/$defs/lodging",
            "trip.schema.json#/$defs/claim",
            "trip.schema.json#/$defs/unknown",
        }, refs)

    def test_at_least_three_valid_examples_pass(self):
        self.assertGreaterEqual(len(VALID), 3)
        for path in VALID:
            with self.subTest(path=path):
                report = validate_candidates(load(path))
                self.assertTrue(report.ok, [item.render() for item in report.errors])

    def test_at_least_three_single_fault_invalid_examples_fail(self):
        self.assertGreaterEqual(len(INVALID), 3)
        for path in INVALID:
            with self.subTest(path=path):
                report = validate_candidates(load(path))
                self.assertFalse(report.ok)

    def test_plan_fixture_manifest_hashes_are_exact(self):
        manifest = load(E2E / "manifest.json")
        self.assertEqual(3, manifest["case_count"])
        self.assertEqual(3, manifest["invalid_count"])
        listed = {entry["path"] for entry in manifest["files"]}
        actual = {
            path.relative_to(E2E).as_posix()
            for path in E2E.rglob("*.json")
            if path.name not in ("manifest.json", "request.json") or path.parent != E2E
        }
        self.assertEqual(listed, actual)
        for entry in manifest["files"]:
            data = (E2E / entry["path"]).read_bytes()
            self.assertEqual(entry["sha256"], hashlib.sha256(data).hexdigest())

    def test_cli_validates_candidate_files_without_provider_calls(self):
        valid = subprocess.run([str(CTW), "validate-candidates", str(VALID[0])], text=True, capture_output=True)
        invalid = subprocess.run([str(CTW), "validate-candidates", str(INVALID[0])], text=True, capture_output=True)
        self.assertEqual(0, valid.returncode, valid.stdout + valid.stderr)
        self.assertIn("CANDIDATES VALID", valid.stdout)
        self.assertEqual(1, invalid.returncode)
        self.assertIn("CANDIDATES INVALID", invalid.stderr)

    def test_packaged_candidate_reference_is_valid_and_reproducible(self):
        reference = PLUGIN / "references" / "candidates.example.json"
        source = E2E / "beijing-shanghai-3d" / "candidates.json"
        self.assertEqual(source.read_bytes(), reference.read_bytes())
        report = validate_candidates(load(reference))
        self.assertTrue(report.ok, [item.render() for item in report.errors])

    def test_pointer_error_names_expected_found_and_copyable_array_index_fix(self):
        candidates = load(PLUGIN / "references" / "candidates.example.json")
        lodging_id = candidates["lodgings"][0]["lodging_id"]
        bad_pointer = "/lodgings/%s/price/amount" % lodging_id
        candidates["unknowns"][0]["field_path"] = bad_pointer

        report = validate_candidates(candidates)

        issue = next(item for item in report.errors if item.code == "C_UNKNOWN_PATH")
        self.assertIn("expected=", issue.message)
        self.assertIn("found=%r" % bad_pointer, issue.message)
        self.assertIn("example=/lodgings/0/price/amount", issue.message)
        self.assertIn("zero-based integer, not an entity id", issue.message)


if __name__ == "__main__":
    unittest.main()
