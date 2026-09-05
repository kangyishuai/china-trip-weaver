from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
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

from china_trip_weaver.candidates import (
    add_lodging_candidate,
    add_poi_candidate,
    initialize_candidates,
    load_candidates_schema,
    validate_candidates,
)
from china_trip_weaver.clock import FixedClock
from china_trip_weaver.cli import main as cli_main
from china_trip_weaver.providers.base import ProviderTimeout, stable_id
from tests.test_providers import AMAP_SCENARIOS, AMapScenarioTransport


E2E = ROOT / "tests" / "fixtures" / "e2e"
CTW = PLUGIN / "scripts" / "ctw"
VALID = sorted(E2E.glob("*/candidates.json"))
INVALID = sorted((E2E / "candidates-invalid").glob("*.json"))


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class CandidateContractTests(unittest.TestCase):
    def _run_verified_poi_add(self, path, credential_path, transport):
        stdout = io.StringIO()
        stderr = io.StringIO()
        arguments = [
            "candidates", "add-poi", str(path),
            "--name", "海岛生态廊道", "--city", "珠海",
            "--category", "synthetic-test-place",
            "--source-url", "https://example.invalid/poi-name-check",
            "--queried-at", "2026-09-04T12:00:00+08:00",
            "--verify-name",
        ]
        with mock.patch.dict(os.environ, {}, clear=True):
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                return_code = cli_main(
                    arguments,
                    credential_path=credential_path,
                    poi_name_transport=transport,
                )
        return return_code, stdout.getvalue(), stderr.getvalue()

    @staticmethod
    def _configured_amap_file(directory):
        credential_path = Path(directory) / "credentials.env"
        key_name = "AMAP_" + "WEBSERVICE_KEY"
        credential_path.write_text(
            key_name + "=ctw-canary-candidate-name-check-not-real\n",
            encoding="utf-8",
        )
        credential_path.chmod(0o600)
        return credential_path

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

    def test_unknown_array_index_must_target_its_claim_subject(self):
        candidates = load(PLUGIN / "references" / "candidates.example.json")
        claims = {item["claim_id"]: item for item in candidates["claims"]}
        first_poi_id = candidates["pois"][0]["poi_id"]
        unknown_index, unknown = next(
            (index, item) for index, item in enumerate(candidates["unknowns"])
            if claims[item["claim_id"]]["subject_ref"] == first_poi_id
        )
        unknown["field_path"] = "/pois/1/coordinates"

        report = validate_candidates(candidates)

        issue = next(item for item in report.errors if item.code == "C_UNKNOWN_SUBJECT")
        self.assertEqual("/unknowns/%d/field_path" % unknown_index, issue.path)
        self.assertIn("targets /pois/1", issue.message)
        self.assertIn("expected_index=0", issue.message)
        self.assertIn("expected_prefix=/pois/0", issue.message)

    def test_cli_rejects_unknown_index_mismatch_with_expected_index(self):
        candidates = load(PLUGIN / "references" / "candidates.example.json")
        claims = {item["claim_id"]: item for item in candidates["claims"]}
        first_poi_id = candidates["pois"][0]["poi_id"]
        unknown = next(
            item for item in candidates["unknowns"]
            if claims[item["claim_id"]]["subject_ref"] == first_poi_id
        )
        unknown["field_path"] = "/pois/1/coordinates"
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            path = Path(temporary) / "misindexed-candidates.json"
            path.write_text(json.dumps(candidates, ensure_ascii=False), encoding="utf-8")
            result = subprocess.run(
                [str(CTW), "validate-candidates", str(path)],
                text=True,
                capture_output=True,
            )
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("CANDIDATES INVALID", result.stderr)
        self.assertIn("C_UNKNOWN_SUBJECT", result.stderr)
        self.assertIn("expected_index=0", result.stderr)

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

    def test_cli_add_poi_name_check_reports_unique_and_writes_candidate(self):
        scenario = load(AMAP_SCENARIOS / "g3_identity_conflict.json")
        scenario["entities"][0]["ref_id"] = stable_id(
            "poi-name-check", "珠海", "海岛生态廊道",
        )
        scenario["entities"][0]["poi_results"] = [
            scenario["entities"][0]["poi_results"][0]
        ]
        transport = AMapScenarioTransport(scenario)
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            path = Path(temporary) / "candidates.json"
            initialize_candidates(path)
            credential_path = self._configured_amap_file(temporary)
            return_code, stdout, stderr = self._run_verified_poi_add(
                path, credential_path, transport,
            )
            value = load(path)

        self.assertEqual(0, return_code, stdout + stderr)
        self.assertEqual("", stderr)
        self.assertEqual(1, transport.calls)
        self.assertEqual(["poi"], transport.capabilities)
        self.assertIn("POI_NAME_CHECK status=unique reason=none", stdout)
        self.assertIn('"administrative_area":"珠海市/香洲区"', stdout)
        self.assertIn('"suggested_names":["海岛生态廊道甲区"]', stdout)
        self.assertIn("CANDIDATE_POI_ADDED", stdout)
        self.assertIsNone(value["pois"][0]["coordinates"])
        self.assertTrue(validate_candidates(value).ok)

    def test_cli_add_poi_name_check_reports_ambiguous_and_still_writes(self):
        scenario = load(AMAP_SCENARIOS / "g3_identity_conflict.json")
        scenario["entities"][0]["ref_id"] = stable_id(
            "poi-name-check", "珠海", "海岛生态廊道",
        )
        transport = AMapScenarioTransport(scenario)
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            path = Path(temporary) / "candidates.json"
            initialize_candidates(path)
            credential_path = self._configured_amap_file(temporary)
            return_code, stdout, stderr = self._run_verified_poi_add(
                path, credential_path, transport,
            )
            value = load(path)

        self.assertEqual(0, return_code, stdout + stderr)
        self.assertEqual("", stderr)
        self.assertEqual(1, transport.calls)
        self.assertIn(
            "POI_NAME_CHECK status=ambiguous reason=ambiguous_name_margin",
            stdout,
        )
        self.assertIn("海岛生态廊道甲区", stdout)
        self.assertIn("海岛生态廊道乙区", stdout)
        self.assertIn("CANDIDATE_POI_ADDED", stdout)
        self.assertIsNone(value["pois"][0]["coordinates"])
        self.assertTrue(validate_candidates(value).ok)

    def test_cli_add_poi_name_check_missing_key_is_non_blocking(self):
        scenario = load(AMAP_SCENARIOS / "g3_identity_conflict.json")
        transport = AMapScenarioTransport(scenario)
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            path = Path(temporary) / "candidates.json"
            initialize_candidates(path)
            return_code, stdout, stderr = self._run_verified_poi_add(
                path, Path(temporary) / "missing.env", transport,
            )
            value = load(path)

        self.assertEqual(0, return_code, stdout + stderr)
        self.assertEqual("", stderr)
        self.assertEqual(0, transport.calls)
        self.assertIn(
            "POI_NAME_CHECK status=unavailable reason=credential_missing",
            stdout,
        )
        self.assertIn("CANDIDATE_POI_ADDED", stdout)
        self.assertIsNone(value["pois"][0]["coordinates"])
        self.assertTrue(validate_candidates(value).ok)

    def test_cli_add_poi_name_check_provider_failure_is_non_blocking(self):
        class TimeoutTransport:
            def __init__(self):
                self.calls = 0

            def execute(self, provider, request):
                del provider, request
                self.calls += 1
                raise ProviderTimeout("synthetic candidate-name timeout")

        transport = TimeoutTransport()
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            path = Path(temporary) / "candidates.json"
            initialize_candidates(path)
            credential_path = self._configured_amap_file(temporary)
            return_code, stdout, stderr = self._run_verified_poi_add(
                path, credential_path, transport,
            )
            value = load(path)

        self.assertEqual(0, return_code, stdout + stderr)
        self.assertEqual("", stderr)
        self.assertEqual(2, transport.calls)
        self.assertIn("POI_NAME_CHECK status=unavailable reason=timeout", stdout)
        self.assertIn("CANDIDATE_POI_ADDED", stdout)
        self.assertIsNone(value["pois"][0]["coordinates"])
        self.assertTrue(validate_candidates(value).ok)


if __name__ == "__main__":
    unittest.main()
