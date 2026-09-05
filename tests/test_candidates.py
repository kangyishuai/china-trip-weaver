from __future__ import annotations

import copy
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
    CandidateNameOption,
    _unique_candidate_name,
    add_lodging_candidate,
    add_poi_candidate,
    fix_candidate_names,
    initialize_candidates,
    load_candidates_schema,
    validate_candidates,
)
from china_trip_weaver.clock import FixedClock
from china_trip_weaver.cli import main as cli_main
from china_trip_weaver.credentials import resolve_credentials
from china_trip_weaver.journey import assemble_journey, validate_journey
from china_trip_weaver.mobility import MobilityBackend, apply_locations
from china_trip_weaver.providers.base import ProviderTimeout, stable_id
from tests.test_providers import (
    AMAP_SCENARIOS,
    AMapScenarioTransport,
    amap_scenario_candidates,
)


E2E = ROOT / "tests" / "fixtures" / "e2e"
NAME_FIX = ROOT / "tests" / "fixtures" / "candidate-name-fix"
POI_IDENTITY_DECISIONS = (
    ROOT / "tests" / "fixtures" / "poi-identity-decision" / "dead-corners.json"
)
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

    def test_fix_name_trip_and_candidate_fixtures_are_valid(self):
        trip = subprocess.run(
            [str(CTW), "validate", str(NAME_FIX / "trip.json")],
            text=True,
            capture_output=True,
        )
        candidates = subprocess.run(
            [str(CTW), "validate-candidates", str(NAME_FIX / "candidates.json")],
            text=True,
            capture_output=True,
        )

        self.assertEqual(0, trip.returncode, trip.stdout + trip.stderr)
        self.assertIn("VALID", trip.stdout)
        self.assertEqual(0, candidates.returncode, candidates.stdout + candidates.stderr)
        self.assertIn("CANDIDATES VALID", candidates.stdout)

    def test_fix_names_report_is_read_only_and_lists_auto_and_manual(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            candidates_path = Path(temporary) / "candidates.json"
            candidates_path.write_bytes((NAME_FIX / "candidates.json").read_bytes())
            before = candidates_path.read_bytes()
            before_sha256 = hashlib.sha256(before).hexdigest()
            result = subprocess.run(
                [
                    str(CTW), "candidates", "fix-names", str(candidates_path),
                    "--trip", str(NAME_FIX / "trip.json"),
                ],
                text=True,
                capture_output=True,
            )
            after = candidates_path.read_bytes()

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual("", result.stderr)
        self.assertEqual(before_sha256, hashlib.sha256(after).hexdigest())
        self.assertEqual(before, after)
        self.assertIn("CANDIDATE_NAME_AUTO", result.stdout)
        self.assertIn('"action":"would_apply"', result.stdout)
        self.assertIn('"original_name":"合成星塔旧称"', result.stdout)
        self.assertIn('"suggested_name":"合成星塔"', result.stdout)
        self.assertIn("合成甲市/合成一区", result.stdout)
        self.assertIn("CANDIDATE_NAME_MANUAL", result.stdout)
        self.assertIn("合成云廊东门", result.stdout)
        self.assertIn("合成云廊西门", result.stdout)
        self.assertIn("合成丙市/合成东区", result.stdout)
        self.assertIn("合成丙市/合成西区", result.stdout)
        self.assertNotIn("poi-fix-control", result.stdout)
        self.assertIn(
            'CANDIDATE_NAME_FIX_SUMMARY {"applied":0,"automatic":1,"manual":1,"mode":"report"}',
            result.stdout,
        )

    def test_fix_names_apply_changes_ref_id_target_only_and_remains_valid(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            candidates_path = Path(temporary) / "candidates.json"
            candidates_path.write_bytes((NAME_FIX / "candidates.json").read_bytes())
            before_bytes = candidates_path.read_bytes()
            before = load(candidates_path)
            expected = json.loads(json.dumps(before, ensure_ascii=False))
            expected["pois"][0]["name"] = "合成星塔"
            result = subprocess.run(
                [
                    str(CTW), "candidates", "fix-names", str(candidates_path),
                    "--trip", str(NAME_FIX / "trip.json"), "--apply",
                ],
                text=True,
                capture_output=True,
            )
            after_bytes = candidates_path.read_bytes()
            after = load(candidates_path)
            validation = subprocess.run(
                [str(CTW), "validate-candidates", str(candidates_path)],
                text=True,
                capture_output=True,
            )

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual("", result.stderr)
        self.assertEqual("合成星塔", after["pois"][0]["name"])
        self.assertEqual(before["pois"][1], after["pois"][1])
        self.assertEqual(before["pois"][2], after["pois"][2])
        self.assertEqual(expected, after)
        expected_bytes = before_bytes.replace(
            '"name": "合成星塔旧称"'.encode("utf-8"),
            '"name": "合成星塔"'.encode("utf-8"),
            1,
        )
        self.assertEqual(expected_bytes, after_bytes)
        self.assertIn('"action":"applied"', result.stdout)
        self.assertIn('"action":"unchanged"', result.stdout)
        self.assertIn(
            'CANDIDATE_NAME_FIX_SUMMARY {"applied":1,"automatic":1,"manual":1,"mode":"apply"}',
            result.stdout,
        )
        self.assertEqual(0, validation.returncode, validation.stdout + validation.stderr)
        self.assertIn("CANDIDATES VALID", validation.stdout)

    def test_fix_names_accepts_journey_source(self):
        trip = load(NAME_FIX / "trip.json")
        journey = assemble_journey(
            [trip],
            trip["request"],
            [],
            FixedClock.from_iso("2026-09-05T09:00:00+08:00"),
        )
        self.assertTrue(validate_journey(journey).ok)
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            candidates_path = Path(temporary) / "candidates.json"
            journey_path = Path(temporary) / "journey.json"
            candidates_path.write_bytes((NAME_FIX / "candidates.json").read_bytes())
            journey_path.write_text(json.dumps(journey, ensure_ascii=False), encoding="utf-8")
            before = candidates_path.read_bytes()
            result = subprocess.run(
                [
                    str(CTW), "candidates", "fix-names", str(candidates_path),
                    "--trip", str(journey_path),
                ],
                text=True,
                capture_output=True,
            )
            after = candidates_path.read_bytes()

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(before, after)
        self.assertIn('"automatic":1', result.stdout)
        self.assertIn('"manual":1', result.stdout)

    def test_fix_names_duplicate_suggestions_are_one_automatic_choice(self):
        trip = load(NAME_FIX / "trip.json")
        unique = next(
            item for item in trip["unknowns"]
            if "poi-fix-unique" in item["reason"]
        )
        duplicate_feedback = {
            "candidates": [{
                "administrative_area": "合成甲市/合成一区",
                "name": "合成星塔新称",
            }, {
                "administrative_area": "合成甲市/合成二区",
                "name": "合成星塔新称",
            }],
            "suggested_names": ["合成星塔新称", "合成星塔新称"],
        }
        unique["reason"] = "identity_conflict:poi-fix-unique:ambiguous_name_margin:%s" % json.dumps(
            duplicate_feedback, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        )
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            candidates_path = Path(temporary) / "candidates.json"
            trip_path = Path(temporary) / "trip.json"
            candidates_path.write_bytes((NAME_FIX / "candidates.json").read_bytes())
            trip_path.write_text(json.dumps(trip, ensure_ascii=False), encoding="utf-8")
            result = fix_candidate_names(candidates_path, trip_path, apply=True)
            updated = load(candidates_path)

        decision = next(item for item in result.decisions if item.ref_id == "poi-fix-unique")
        self.assertTrue(decision.automatic)
        self.assertEqual("unique_suggestion", decision.reason)
        self.assertEqual("合成星塔新称", decision.replacement_name)
        self.assertEqual(
            (CandidateNameOption("合成星塔新称", "合成甲市/合成一区"),),
            decision.options,
        )
        self.assertEqual(1, result.applied_count)
        self.assertEqual("合成星塔新称", updated["pois"][0]["name"])

    def test_fix_names_exact_original_first_is_automatic_confirmation(self):
        trip = load(NAME_FIX / "trip.json")
        unique = next(
            item for item in trip["unknowns"]
            if "poi-fix-unique" in item["reason"]
        )
        feedback = {
            "candidates": [{
                "administrative_area": "合成甲市/合成一区",
                "name": "合成星塔旧称",
            }, {
                "administrative_area": "合成甲市/合成二区",
                "name": "合成星塔旧称停车",
            }],
            "suggested_names": ["合成星塔旧称", "合成星塔旧称停车"],
        }
        unique["reason"] = "identity_conflict:poi-fix-unique:ambiguous_name_margin:%s" % json.dumps(
            feedback, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        )
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            candidates_path = Path(temporary) / "candidates.json"
            trip_path = Path(temporary) / "trip.json"
            candidates_path.write_bytes((NAME_FIX / "candidates.json").read_bytes())
            trip_path.write_text(json.dumps(trip, ensure_ascii=False), encoding="utf-8")
            before = candidates_path.read_bytes()
            result = subprocess.run(
                [
                    str(CTW), "candidates", "fix-names", str(candidates_path),
                    "--trip", str(trip_path), "--apply",
                ],
                text=True,
                capture_output=True,
            )
            after = candidates_path.read_bytes()

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(before, after)
        self.assertIn('"reason":"exact_original_confirmed"', result.stdout)
        self.assertIn('"suggested_name":"合成星塔旧称"', result.stdout)
        self.assertIn('"applied":1', result.stdout)
        self.assertIn('"automatic":1', result.stdout)

    def test_fix_names_and_mobility_share_poi_name_decisions(self):
        fixture = load(POI_IDENTITY_DECISIONS)
        expected_automatic = {
            "duplicate_names": True,
            "exact_original_first": True,
            "prefix_relation": False,
            "different_places": False,
        }
        candidate_credentials = resolve_credentials(
            {"AMAP_WEBSERVICE_KEY": "ctw-canary-poi-decision-not-real"},
            ROOT / ".tmp" / "poi-decision-no-file",
        )
        for case in fixture["cases"]:
            with self.subTest(case=case["case"]):
                entity = copy.deepcopy(case["entity"])
                scenario = {"entities": [entity]}
                candidates = amap_scenario_candidates(scenario)
                mobility = MobilityBackend(
                    "live", candidate_credentials, AMapScenarioTransport(scenario),
                ).resolve(
                    candidates,
                    FixedClock.from_iso("2026-09-03T12:00:00+08:00"),
                    ("walking",),
                )
                pois, _ = apply_locations(candidates["pois"], (), mobility)
                mobility_automatic = pois[0]["coordinates"] is not None
                options = tuple(
                    CandidateNameOption(
                        item["name"], "%s/%s" % (entity["city"], item["adname"]),
                    )
                    for item in entity["poi_results"]
                )
                replacement, _ = _unique_candidate_name(entity["name"], options)
                fix_names_automatic = replacement is not None

                self.assertEqual(expected_automatic[case["case"]], mobility_automatic)
                self.assertEqual(mobility_automatic, fix_names_automatic)

    def test_fix_names_prefix_and_different_candidates_require_manual_review(self):
        fixture = load(POI_IDENTITY_DECISIONS)
        cases = {item["case"]: item["entity"] for item in fixture["cases"]}
        for case_name in ("prefix_relation", "different_places"):
            with self.subTest(case=case_name):
                entity = cases[case_name]
                options = tuple(
                    CandidateNameOption(
                        item["name"], "%s/%s" % (entity["city"], item["adname"]),
                    )
                    for item in entity["poi_results"]
                )
                replacement, reason = _unique_candidate_name(entity["name"], options)

                self.assertIsNone(replacement)
                self.assertEqual("ambiguous_suggestions", reason)

    def test_fix_names_conflicting_journey_feedback_stays_unchanged(self):
        first_trip = load(NAME_FIX / "trip.json")
        second_trip = json.loads(json.dumps(first_trip, ensure_ascii=False))
        unique = next(
            item for item in second_trip["unknowns"]
            if "poi-fix-unique" in item["reason"]
        )
        feedback = {
            "candidates": [{
                "administrative_area": "合成甲市/合成二区",
                "name": "合成星塔新馆",
            }],
            "suggested_names": ["合成星塔新馆"],
        }
        unique["reason"] = "identity_conflict:poi-fix-unique:poi_admin_mismatch:%s" % json.dumps(
            feedback, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        )
        second_trip["trip_id"] = "synthetic-name-fix-trip-two"
        journey = {
            "schema_version": "1.0.0",
            "journey_id": "synthetic-name-fix-conflict-journey",
            "trips": [first_trip, second_trip],
        }
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            candidates_path = Path(temporary) / "candidates.json"
            journey_path = Path(temporary) / "journey.json"
            candidates_path.write_bytes((NAME_FIX / "candidates.json").read_bytes())
            journey_path.write_text(json.dumps(journey, ensure_ascii=False), encoding="utf-8")
            before = candidates_path.read_bytes()
            result = subprocess.run(
                [
                    str(CTW), "candidates", "fix-names", str(candidates_path),
                    "--trip", str(journey_path), "--apply",
                ],
                text=True,
                capture_output=True,
            )
            after = candidates_path.read_bytes()

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(before, after)
        self.assertIn('"reason":"conflicting_feedback"', result.stdout)
        self.assertIn('"applied":0', result.stdout)


if __name__ == "__main__":
    unittest.main()
