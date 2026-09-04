"""Validation for research-produced POI, lodging, claim, and unknown candidates."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set

from .evidence import validate_claim
from .validate_trip import (
    SchemaSubsetValidator,
    ValidationIssue,
    ValidationReport,
    load_schema,
)


CANDIDATES_VERSION = "1.0.0"
TRIP_REF_PREFIX = "trip.schema.json#/$defs/"


def default_candidates_schema_path() -> Path:
    return Path(__file__).resolve().parents[2] / "schema" / "candidates.schema.json"


def load_candidates_schema(path: Optional[Path] = None) -> Mapping[str, Any]:
    schema_path = path or default_candidates_schema_path()
    with schema_path.open("r", encoding="utf-8") as handle:
        schema = json.load(handle)
    if not isinstance(schema, dict):
        raise ValueError("candidates schema must be a JSON object")
    return schema


def resolved_candidates_schema(path: Optional[Path] = None) -> Mapping[str, Any]:
    schema = copy.deepcopy(dict(load_candidates_schema(path)))
    trip_defs = copy.deepcopy(load_schema()["$defs"])

    def resolve(value: Any) -> None:
        if isinstance(value, dict):
            reference = value.get("$ref")
            if isinstance(reference, str) and reference.startswith(TRIP_REF_PREFIX):
                value["$ref"] = "#/$defs/" + reference[len(TRIP_REF_PREFIX):]
            for child in value.values():
                resolve(child)
        elif isinstance(value, list):
            for child in value:
                resolve(child)

    resolve(schema)
    schema["$defs"] = trip_defs
    return schema


def validate_candidates(value: Mapping[str, Any], schema_path: Optional[Path] = None) -> ValidationReport:
    if not isinstance(value, dict):
        return ValidationReport((ValidationIssue("C_OBJECT", "/", "candidates must be an object"),))
    schema_issues = SchemaSubsetValidator(resolved_candidates_schema(schema_path)).validate(value)
    if schema_issues:
        return ValidationReport(tuple(sorted(set(schema_issues))))

    issues: List[ValidationIssue] = []
    entity_ids: Dict[str, str] = {}
    claim_ids: Dict[str, Mapping[str, Any]] = {}
    referenced_claim_ids: Set[str] = set()

    def add(code: str, path: str, message: str) -> None:
        issues.append(ValidationIssue(code, path, message))

    for group, id_key in (("pois", "poi_id"), ("lodgings", "lodging_id")):
        for index, entity in enumerate(value[group]):
            identifier = entity[id_key]
            path = "/%s/%d" % (group, index)
            if identifier in entity_ids:
                add("C_DUPLICATE_ID", path + "/" + id_key, "candidate entity id is duplicated")
            entity_ids[identifier] = path
            if not entity["claim_ids"]:
                add("C_ENTITY_CLAIMS", path + "/claim_ids", "every candidate entity requires evidence")
            referenced_claim_ids.update(entity["claim_ids"])
            price = entity.get("price")
            if price and price.get("claim_id") is not None:
                referenced_claim_ids.add(price["claim_id"])
            for window in entity.get("opening_windows", []):
                if window.get("claim_id") is not None:
                    referenced_claim_ids.add(window["claim_id"])

    for index, claim in enumerate(value["claims"]):
        path = "/claims/%d" % index
        try:
            validate_claim(claim)
        except ValueError as exc:
            add("C_CLAIM", path, str(exc))
        identifier = claim["claim_id"]
        if identifier in claim_ids:
            add("C_DUPLICATE_CLAIM", path + "/claim_id", "claim id is duplicated")
        claim_ids[identifier] = claim
        if claim["subject_ref"] not in entity_ids:
            add("C_CLAIM_SUBJECT", path + "/subject_ref", "claim subject is not a candidate entity")

    for identifier in sorted(referenced_claim_ids):
        if identifier not in claim_ids:
            add("C_CLAIM_REF", "/claims", "candidate references missing claim %s" % identifier)
    for identifier in sorted(set(claim_ids) - referenced_claim_ids):
        add("C_ORPHAN_CLAIM", "/claims", "claim is not referenced by a candidate: %s" % identifier)

    for index, unknown in enumerate(value["unknowns"]):
        path = "/unknowns/%d" % index
        claim_id = unknown["claim_id"]
        if claim_id is not None and claim_id not in claim_ids:
            add("C_UNKNOWN_CLAIM", path + "/claim_id", "unknown references a missing claim")
        try:
            _resolve_pointer(value, unknown["field_path"])
        except (KeyError, IndexError, ValueError):
            add("C_UNKNOWN_PATH", path + "/field_path", "unknown path does not resolve in candidates")

    return ValidationReport(tuple(sorted(set(issues))))


def validate_candidates_file(path: Path, schema_path: Optional[Path] = None) -> ValidationReport:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return ValidationReport((ValidationIssue("J_INVALID", "/", str(exc)),))
    if not isinstance(value, dict):
        return ValidationReport((ValidationIssue("C_OBJECT", "/", "candidates must be an object"),))
    return validate_candidates(value, schema_path=schema_path)


def _resolve_pointer(document: Any, pointer: str) -> Any:
    if not pointer.startswith("/"):
        raise KeyError(pointer)
    value = document
    for raw in pointer[1:].split("/"):
        part = raw.replace("~1", "/").replace("~0", "~")
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value
