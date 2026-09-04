from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "china-trip-weaver"
SRC = PLUGIN / "src"
sys.path.insert(0, str(SRC))

from china_trip_weaver import SCHEMA_VERSION, __version__
from china_trip_weaver.clock import FixedClock, SHANGHAI, isoformat_seconds
from china_trip_weaver.contracts import TripDocument, canonical_json, canonical_sha256
from china_trip_weaver.errors import CTWError, ERROR_POLICIES
from china_trip_weaver.validate_trip import SchemaSubsetValidator, load_schema, validate_trip


VALID = ROOT / "tests" / "fixtures" / "trips" / "schema" / "valid"
INVALID = ROOT / "tests" / "fixtures" / "trips" / "schema" / "invalid"
CTW = PLUGIN / "scripts" / "ctw"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class ContractTests(unittest.TestCase):
    def test_versions_are_frozen(self):
        self.assertEqual("0.3.0", __version__)
        self.assertEqual("1.0.0", SCHEMA_VERSION)

    def test_packaged_schema_is_byte_identical_to_accepted_schema(self):
        accepted = ROOT / "docs" / "design" / "schema" / "trip.schema.json"
        packaged = PLUGIN / "schema" / "trip.schema.json"
        self.assertEqual(accepted.read_bytes(), packaged.read_bytes())

    def test_accepted_examples_are_unchanged_in_test_fixtures(self):
        accepted = ROOT / "docs" / "design" / "schema" / "examples"
        copied = ROOT / "tests" / "fixtures" / "trips" / "schema"
        for source in sorted(accepted.rglob("*.json")):
            relative = source.relative_to(accepted)
            self.assertEqual(source.read_bytes(), (copied / relative).read_bytes(), str(relative))

    def test_both_valid_examples_pass_schema_and_semantics(self):
        for path in sorted(VALID.glob("*.json")):
            with self.subTest(path=path.name):
                report = validate_trip(load(path))
                self.assertTrue(report.ok, [issue.render() for issue in report.errors])

    def test_all_four_invalid_examples_fail(self):
        for path in sorted(INVALID.glob("*.json")):
            with self.subTest(path=path.name):
                report = validate_trip(load(path))
                self.assertFalse(report.ok)

    def test_schema_validator_rejects_unknown_schema_keywords(self):
        schema = copy.deepcopy(load_schema())
        schema["madeUpKeyword"] = True
        with self.assertRaisesRegex(ValueError, "madeUpKeyword"):
            SchemaSubsetValidator(schema).validate({})

    def test_canonical_json_and_hash_ignore_mapping_order(self):
        left = {"b": [2, 1], "a": "上海"}
        right = {"a": "上海", "b": [2, 1]}
        self.assertEqual('{"a":"上海","b":[2,1]}', canonical_json(left))
        self.assertEqual(canonical_sha256(left), canonical_sha256(right))

    def test_trip_document_is_defensive_and_deterministic(self):
        path = VALID / "weekend-live.json"
        document = TripDocument.from_path(path)
        copy_value = document.to_dict()
        copy_value["trip_id"] = "changed"
        self.assertNotEqual(copy_value["trip_id"], document.data["trip_id"])
        self.assertEqual(hashlib.sha256(document.canonical_json().encode()).hexdigest(), document.sha256())

    def test_semantics_reject_overlap(self):
        trip = load(VALID / "weekend-live.json")
        trip["days"][0]["slots"][1]["start_at"] = "2026-10-16T11:00:00+08:00"
        codes = {issue.code for issue in validate_trip(trip).errors}
        self.assertIn("V_SLOT_OVERLAP", codes)

    def test_semantics_reject_kind_reference_mismatch(self):
        trip = load(VALID / "weekend-live.json")
        trip["days"][0]["slots"][0]["ref_id"] = "lodging-nanjing-east"
        codes = {issue.code for issue in validate_trip(trip).errors}
        self.assertIn("V_REF_KIND", codes)

    def test_semantics_reject_coordinate_double_derivation(self):
        trip = load(VALID / "weekend-live.json")
        trip["pois"][0]["coordinates"]["conversion"]["derived_fields"].append("gcj02")
        codes = {issue.code for issue in validate_trip(trip).errors}
        self.assertIn("V_COORDINATE_NATIVE", codes)

    def test_semantics_reject_optimistic_top_mode(self):
        trip = load(VALID / "multicity-static.json")
        trip["mode"] = "live"
        codes = {issue.code for issue in validate_trip(trip).errors}
        self.assertIn("V_TOP_MODE", codes)

    def test_semantics_reject_non_whitelisted_patch_operation(self):
        trip = load(VALID / "multicity-static.json")
        trip["patches"][0]["operations"][0]["op"] = "copy"
        codes = {issue.code for issue in validate_trip(trip).errors}
        self.assertIn("V_PATCH_OP", codes)

    def test_semantics_reject_credential_shaped_content(self):
        trip = load(VALID / "weekend-live.json")
        trip["request"]["pasted_notes"] = "gh" + "p_" + "abcdefghijklmnopqrstuvwxyz123456"
        codes = {issue.code for issue in validate_trip(trip).errors}
        self.assertIn("V_SECRET", codes)

    def test_error_taxonomy_has_all_frozen_classes(self):
        expected = {
            "invalid_request", "credential_missing", "credential_expired", "forbidden",
            "rate_limited", "timeout", "network", "upstream_5xx",
            "contract_mismatch", "no_results", "policy_blocked", "internal",
        }
        self.assertEqual(expected, set(ERROR_POLICIES))
        mismatch = CTWError("contract_mismatch", "PROVIDER_SHAPE")
        self.assertFalse(mismatch.retryable)
        self.assertEqual("contract_mismatch", mismatch.health_status)

    def test_fixed_clock_normalizes_to_shanghai(self):
        clock = FixedClock.from_iso("2026-09-03T01:02:03Z")
        self.assertEqual("2026-09-03T09:02:03+08:00", isoformat_seconds(clock))
        self.assertEqual(timedelta(hours=8), clock.now().utcoffset())

    def test_fixed_clock_rejects_naive_datetime(self):
        with self.assertRaises(ValueError):
            FixedClock(datetime(2026, 9, 3, 9, 0, 0))

    def test_cli_validate_and_doctor(self):
        valid = subprocess.run([str(CTW), "validate", str(VALID / "weekend-live.json")], text=True, capture_output=True)
        invalid = subprocess.run([str(CTW), "validate", str(INVALID / "claim-missing-source.json")], text=True, capture_output=True)
        doctor = subprocess.run([str(CTW), "doctor"], text=True, capture_output=True)
        self.assertEqual(0, valid.returncode, valid.stderr)
        self.assertEqual(1, invalid.returncode, invalid.stdout + invalid.stderr)
        self.assertEqual(0, doctor.returncode, doctor.stderr)
        self.assertTrue(json.loads(doctor.stdout)["schema_exists"])


if __name__ == "__main__":
    unittest.main()
