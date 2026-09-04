"""Validation for research-produced POI, lodging, claim, and unknown candidates."""

from __future__ import annotations

import copy
import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set

from .clock import Clock
from .contracts import read_json, write_canonical_json
from .evidence import make_claim, validate_claim
from .providers.base import safe_https_url, stable_id
from .validate_trip import (
    SchemaSubsetValidator,
    ValidationIssue,
    ValidationReport,
    load_schema,
)


CANDIDATES_VERSION = "1.0.0"
TRIP_REF_PREFIX = "trip.schema.json#/$defs/"
POINTER_EXPECTED = "a resolvable JSON Pointer using zero-based array indexes"
POINTER_EXAMPLE = "/lodgings/0/price/amount"
EXPECTED_DOCUMENT_KEYS = frozenset(("candidates_version", "pois", "lodgings", "claims", "unknowns"))


class CandidatePointerError(ValueError):
    """A user-correctable candidate JSON Pointer failure."""

    def __init__(self, pointer: str, detail: str) -> None:
        self.expected = POINTER_EXPECTED
        self.found = pointer
        self.example = POINTER_EXAMPLE
        self.detail = detail
        super().__init__(
            "expected=%s; found=%r; example=%s; detail=%s"
            % (self.expected, self.found, self.example, self.detail)
        )


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
        except CandidatePointerError as exc:
            add("C_UNKNOWN_PATH", path + "/field_path", str(exc))

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


def initialize_candidates(path: Path, *, overwrite: bool = False) -> Mapping[str, Any]:
    destination = Path(path)
    if destination.is_symlink():
        raise ValueError("candidate path must not be a symlink")
    if destination.exists() and not overwrite:
        raise ValueError("candidate file already exists; pass --force to replace it")
    destination.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "candidates_version": CANDIDATES_VERSION,
        "pois": [],
        "lodgings": [],
        "claims": [],
        "unknowns": [],
    }
    write_canonical_json(destination, document)
    return copy.deepcopy(document)


def add_poi_candidate(
    path: Path,
    *,
    name: str,
    city: str,
    category: str,
    source_url: str,
    provider: str,
    clock: Clock,
    confidence: float = 0.55,
    duration_minutes: Optional[int] = None,
    opens_at: Optional[str] = None,
    closes_at: Optional[str] = None,
    opening_status: str = "tentative",
    price_amount: Optional[float] = None,
) -> Mapping[str, Any]:
    document = _editable_candidates(path)
    index = len(document["pois"])
    entity_name = _candidate_text(name, "POI name")
    entity_city = _candidate_text(city, "POI city")
    entity_category = _candidate_text(category, "POI category")
    provider_name = _candidate_text(provider, "provider")
    source = safe_https_url(source_url)
    if duration_minutes is not None and (
        not isinstance(duration_minutes, int) or isinstance(duration_minutes, bool) or duration_minutes < 0
    ):
        raise ValueError("POI duration must be a non-negative integer")
    if price_amount is not None and (
        isinstance(price_amount, bool) or not isinstance(price_amount, (int, float)) or price_amount < 0
    ):
        raise ValueError("POI price must be a non-negative number")
    if (opens_at is None) != (closes_at is None):
        raise ValueError("--opens-at and --closes-at must be supplied together")

    poi_id = stable_id("poi", entity_city, entity_name, entity_category)
    _ensure_new_entity_id(document, poi_id)
    claims: List[Mapping[str, Any]] = []
    unknowns: List[Mapping[str, Any]] = []
    name_claim = _generated_claim(
        poi_id, "/name", entity_name, source, provider_name,
        "hypothesis", confidence, clock,
    )
    claims.append(name_claim)
    claim_ids = [name_claim["claim_id"]]

    opening_windows = []
    if opens_at is not None and closes_at is not None:
        window_value = {"start_at": opens_at, "end_at": closes_at, "status": opening_status}
        opening_claim = _generated_claim(
            poi_id, "/opening_windows/0", window_value, source, provider_name,
            "hypothesis", confidence, clock,
        )
        claims.append(opening_claim)
        claim_ids.append(opening_claim["claim_id"])
        opening_windows.append({
            "start_at": opens_at,
            "end_at": closes_at,
            "status": opening_status,
            "claim_id": opening_claim["claim_id"],
        })
    else:
        _append_unknown(
            claims, unknowns, poi_id, "/opening_windows",
            "/pois/%d/opening_windows" % index, source, provider_name,
            "opening hours are not researched yet", clock,
        )
        claim_ids.append(claims[-1]["claim_id"])

    price = None
    if price_amount is not None:
        price_claim = _generated_claim(
            poi_id, "/price", float(price_amount), source, provider_name,
            "partial", confidence, clock,
        )
        claims.append(price_claim)
        claim_ids.append(price_claim["claim_id"])
        price = {
            "amount": float(price_amount),
            "currency": "CNY",
            "price_type": "reference",
            "unit": "per_person",
            "includes_taxes": None,
            "queried_at": price_claim["queried_at"],
            "claim_id": price_claim["claim_id"],
        }
    else:
        _append_unknown(
            claims, unknowns, poi_id, "/price", "/pois/%d/price" % index,
            source, provider_name, "admission price is not researched yet", clock,
        )
        claim_ids.append(claims[-1]["claim_id"])

    _append_unknown(
        claims, unknowns, poi_id, "/coordinates", "/pois/%d/coordinates" % index,
        source, provider_name, "coordinates are not verified yet", clock,
    )
    claim_ids.append(claims[-1]["claim_id"])
    if duration_minutes is None:
        _append_unknown(
            claims, unknowns, poi_id, "/recommended_duration_minutes",
            "/pois/%d/recommended_duration_minutes" % index,
            source, provider_name, "recommended duration is not researched yet", clock,
        )
        claim_ids.append(claims[-1]["claim_id"])

    document["pois"].append({
        "poi_id": poi_id,
        "name": entity_name,
        "city": entity_city,
        "category": entity_category,
        "coordinates": None,
        "recommended_duration_minutes": duration_minutes,
        "opening_windows": opening_windows,
        "price": price,
        "deep_links": [source],
        "claim_ids": claim_ids,
    })
    document["claims"].extend(claims)
    document["unknowns"].extend(unknowns)
    _write_valid_when_complete(path, document)
    return copy.deepcopy(document["pois"][-1])


def add_lodging_candidate(
    path: Path,
    *,
    name: str,
    city: str,
    area: Optional[str],
    check_in: str,
    check_out: str,
    source_url: str,
    provider: str,
    clock: Clock,
    confidence: float = 0.55,
    nightly_price: Optional[float] = None,
    includes_taxes: Optional[bool] = None,
    locked: bool = False,
) -> Mapping[str, Any]:
    document = _editable_candidates(path)
    index = len(document["lodgings"])
    entity_name = _candidate_text(name, "lodging name")
    entity_city = _candidate_text(city, "lodging city")
    entity_area = _candidate_text(area or city, "lodging area")
    provider_name = _candidate_text(provider, "provider")
    source = safe_https_url(source_url)
    try:
        start = date.fromisoformat(check_in)
        end = date.fromisoformat(check_out)
    except (TypeError, ValueError) as exc:
        raise ValueError("lodging dates must be YYYY-MM-DD") from exc
    if end <= start:
        raise ValueError("lodging check-out must be after check-in")
    if nightly_price is not None and (
        isinstance(nightly_price, bool) or not isinstance(nightly_price, (int, float)) or nightly_price < 0
    ):
        raise ValueError("nightly price must be a non-negative number")
    if includes_taxes is not None and not isinstance(includes_taxes, bool):
        raise ValueError("includes_taxes must be boolean or unknown")

    lodging_id = stable_id("lodging", entity_city, entity_name, check_in, check_out)
    _ensure_new_entity_id(document, lodging_id)
    name_claim = _generated_claim(
        lodging_id, "/name", entity_name, source, provider_name,
        "hypothesis", confidence, clock,
    )
    price_claim = _generated_claim(
        lodging_id, "/price", None if nightly_price is None else float(nightly_price),
        source, provider_name, "unknown" if nightly_price is None else "partial",
        0 if nightly_price is None else confidence, clock,
    )
    claims: List[Mapping[str, Any]] = [name_claim, price_claim]
    unknowns: List[Mapping[str, Any]] = []
    claim_ids = [name_claim["claim_id"], price_claim["claim_id"]]
    if nightly_price is None:
        unknowns.append({
            "field_path": "/lodgings/%d/price/amount" % index,
            "reason": "nightly price is not researched yet",
            "provider": provider_name,
            "claim_id": price_claim["claim_id"],
        })
    if includes_taxes is None:
        unknowns.append({
            "field_path": "/lodgings/%d/price/includes_taxes" % index,
            "reason": "tax inclusion is not researched yet",
            "provider": provider_name,
            "claim_id": price_claim["claim_id"],
        })
    _append_unknown(
        claims, unknowns, lodging_id, "/coordinates",
        "/lodgings/%d/coordinates" % index, source, provider_name,
        "coordinates are not verified yet", clock,
    )
    claim_ids.append(claims[-1]["claim_id"])
    document["lodgings"].append({
        "lodging_id": lodging_id,
        "name": entity_name,
        "city": entity_city,
        "area": entity_area,
        "check_in": check_in,
        "check_out": check_out,
        "coordinates": None,
        "price": {
            "amount": None if nightly_price is None else float(nightly_price),
            "currency": "CNY",
            "price_type": "verify-on-click" if nightly_price is None else "reference",
            "unit": "per_night",
            "includes_taxes": includes_taxes,
            "queried_at": price_claim["queried_at"],
            "claim_id": price_claim["claim_id"],
        },
        "deep_links": [source],
        "claim_ids": claim_ids,
        "locked": bool(locked),
    })
    document["claims"].extend(claims)
    document["unknowns"].extend(unknowns)
    _write_valid_when_complete(path, document)
    return copy.deepcopy(document["lodgings"][-1])


def _editable_candidates(path: Path) -> Dict[str, Any]:
    candidate_path = Path(path)
    if candidate_path.is_symlink():
        raise ValueError("candidate path must not be a symlink")
    value = read_json(candidate_path)
    if set(value) != EXPECTED_DOCUMENT_KEYS or value.get("candidates_version") != CANDIDATES_VERSION:
        raise ValueError("candidate file is not a v1 five-key skeleton")
    for name in ("pois", "lodgings", "claims", "unknowns"):
        if not isinstance(value[name], list):
            raise ValueError("candidate file field %s must be an array" % name)
    return value


def _write_valid_when_complete(path: Path, document: Mapping[str, Any]) -> None:
    if document["pois"]:
        report = validate_candidates(document)
        if not report.ok:
            raise ValueError("generated candidates are invalid: " + "; ".join(
                issue.render() for issue in report.errors
            ))
    write_canonical_json(Path(path), document)


def _candidate_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 500:
        raise ValueError("%s must be non-empty text" % label)
    return value.strip()


def _ensure_new_entity_id(document: Mapping[str, Any], identifier: str) -> None:
    existing = {
        entity[key]
        for group, key in (("pois", "poi_id"), ("lodgings", "lodging_id"))
        for entity in document[group]
        if isinstance(entity, dict) and isinstance(entity.get(key), str)
    }
    if identifier in existing:
        raise ValueError("candidate already exists: %s" % identifier)


def _generated_claim(
    subject_ref: str,
    field_path: str,
    value: Any,
    source_url: str,
    provider: str,
    status: str,
    confidence: float,
    clock: Clock,
) -> Mapping[str, Any]:
    return make_claim(
        subject_ref=subject_ref,
        field_path=field_path,
        value=value,
        source_url=source_url,
        provider=provider,
        status=status,
        confidence=confidence,
        mode="static",
        clock=clock,
        claim_id=stable_id("claim", subject_ref, field_path, source_url, provider),
    )


def _append_unknown(
    claims: List[Mapping[str, Any]],
    unknowns: List[Mapping[str, Any]],
    subject_ref: str,
    claim_field_path: str,
    document_pointer: str,
    source_url: str,
    provider: str,
    reason: str,
    clock: Clock,
) -> None:
    claim = _generated_claim(
        subject_ref, claim_field_path, None, source_url, provider,
        "unknown", 0, clock,
    )
    claims.append(claim)
    unknowns.append({
        "field_path": document_pointer,
        "reason": reason,
        "provider": provider,
        "claim_id": claim["claim_id"],
    })


def _resolve_pointer(document: Any, pointer: str) -> Any:
    if not pointer.startswith("/"):
        raise CandidatePointerError(pointer, "pointer must start with '/'")
    value = document
    traversed: List[str] = []
    for raw in pointer[1:].split("/"):
        part = raw.replace("~1", "/").replace("~0", "~")
        location = "/" + "/".join(traversed) if traversed else "/"
        if isinstance(value, list):
            if not part.isdigit():
                raise CandidatePointerError(
                    pointer,
                    "array segment %r at %s must be a zero-based integer, not an entity id"
                    % (part, location),
                )
            index = int(part)
            if index >= len(value):
                expected = "0..%d" % (len(value) - 1) if value else "no index (the array is empty)"
                raise CandidatePointerError(
                    pointer,
                    "array index %s at %s is out of range; expected %s" % (part, location, expected),
                )
            value = value[index]
        elif isinstance(value, Mapping):
            if part not in value:
                raise CandidatePointerError(
                    pointer,
                    "object key %r does not exist at %s" % (part, location),
                )
            value = value[part]
        else:
            raise CandidatePointerError(
                pointer,
                "cannot traverse segment %r at %s because the current value is %s"
                % (part, location, type(value).__name__),
            )
        traversed.append(raw)
    return value
