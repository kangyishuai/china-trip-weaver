from __future__ import annotations

import hashlib
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

from china_trip_weaver.candidates import (
    add_lodging_candidate,
    add_poi_candidate,
    initialize_candidates,
    load_candidates_schema,
    validate_candidates,
)
from china_trip_weaver.clock import FixedClock


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

    def test_cli_generator_output_validates_without_manual_edits(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            path = Path(temporary) / "generated-candidates.json"
            commands = (
                [str(CTW), "candidates", "init", str(path)],
                [
                    str(CTW), "candidates", "add-poi", str(path),
                    "--name", "合成博物馆", "--city", "上海", "--category", "museum",
                    "--source-url", "https://example.invalid/poi", "--provider", "official-web",
                    "--duration-minutes", "120", "--price", "80",
                    "--opens-at", "2026-09-10T09:00:00+08:00",
                    "--closes-at", "2026-09-10T17:00:00+08:00",
                    "--queried-at", "2026-09-04T12:00:00+08:00",
                ],
                [
                    str(CTW), "candidates", "add-lodging", str(path),
                    "--name", "合成酒店", "--city", "上海", "--area", "人民广场",
                    "--check-in", "2026-09-10", "--check-out", "2026-09-11",
                    "--source-url", "https://example.invalid/lodging",
                    "--queried-at", "2026-09-04T12:00:00+08:00",
                ],
                [str(CTW), "validate-candidates", str(path)],
            )
            results = [subprocess.run(command, text=True, capture_output=True) for command in commands]
            for result in results:
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            value = load(path)
        self.assertIn("CANDIDATES VALID", results[-1].stdout)
        self.assertTrue(value["pois"][0]["poi_id"].startswith("poi-"))
        self.assertTrue(value["lodgings"][0]["lodging_id"].startswith("lodging-"))
        self.assertTrue(all(claim["claim_id"].startswith("claim-") for claim in value["claims"]))
        claim_ids = {claim["claim_id"] for claim in value["claims"]}
        self.assertTrue(all(item["claim_id"] in claim_ids for item in value["unknowns"]))
        pointers = {item["field_path"] for item in value["unknowns"]}
        self.assertIn("/pois/0/coordinates", pointers)
        self.assertIn("/lodgings/0/price/amount", pointers)
        self.assertIn("/lodgings/0/price/includes_taxes", pointers)

    def test_generator_uses_actual_zero_based_index_for_every_append(self):
        clock = FixedClock.from_iso("2026-09-04T12:00:00+08:00")
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            path = Path(temporary) / "indexed-candidates.json"
            initialize_candidates(path)
            for index in range(2):
                add_poi_candidate(
                    path,
                    name="合成景点%d" % index,
                    city="杭州",
                    category="park",
                    source_url="https://example.invalid/poi/%d" % index,
                    provider="host-web",
                    clock=clock,
                )
                add_lodging_candidate(
                    path,
                    name="合成住宿%d" % index,
                    city="杭州",
                    area="西湖",
                    check_in="2026-09-10",
                    check_out="2026-09-11",
                    source_url="https://example.invalid/lodging/%d" % index,
                    provider="host-web",
                    clock=clock,
                )
            value = load(path)
        self.assertTrue(validate_candidates(value).ok)
        pointers = {item["field_path"] for item in value["unknowns"]}
        for index in range(2):
            self.assertIn("/pois/%d/coordinates" % index, pointers)
            self.assertIn("/pois/%d/opening_windows" % index, pointers)
            self.assertIn("/lodgings/%d/price/amount" % index, pointers)
            self.assertIn("/lodgings/%d/coordinates" % index, pointers)
        self.assertFalse(any("poi-" in pointer or "lodging-" in pointer for pointer in pointers))

    def test_generator_refuses_overwrite_and_duplicate_without_changing_file(self):
        clock = FixedClock.from_iso("2026-09-04T12:00:00+08:00")
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            path = Path(temporary) / "preserved-candidates.json"
            initialize_candidates(path)
            initial = path.read_bytes()
            with self.assertRaises(ValueError):
                initialize_candidates(path)
            self.assertEqual(initial, path.read_bytes())
            arguments = {
                "name": "唯一景点",
                "city": "苏州",
                "category": "garden",
                "source_url": "https://example.invalid/garden",
                "provider": "official-web",
                "clock": clock,
            }
            add_poi_candidate(path, **arguments)
            populated = path.read_bytes()
            with self.assertRaises(ValueError):
                add_poi_candidate(path, **arguments)
            self.assertEqual(populated, path.read_bytes())


if __name__ == "__main__":
    unittest.main()
