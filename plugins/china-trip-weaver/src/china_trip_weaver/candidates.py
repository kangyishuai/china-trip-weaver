"""Validation for research-produced POI, lodging, claim, and unknown candidates."""

from __future__ import annotations

import copy
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

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


@dataclass(frozen=True)
class CandidateNameOption:
    """One sanitized provider name and its administrative area."""

    name: str
    administrative_area: str

    def as_dict(self) -> Mapping[str, str]:
        return {
            "name": self.name,
            "administrative_area": self.administrative_area,
        }


@dataclass(frozen=True)
class CandidateNameDecision:
    """A ref-id-bound automatic replacement or a manual-review item."""

    ref_id: str
    original_name: Optional[str]
    options: Tuple[CandidateNameOption, ...]
    replacement_name: Optional[str]
    reason: str
    source_field_path: str

    @property
    def automatic(self) -> bool:
        return self.replacement_name is not None

    def as_dict(self, *, apply: bool) -> Mapping[str, Any]:
        if self.automatic:
            action = "applied" if apply else "would_apply"
        else:
            action = "unchanged"
        return {
            "action": action,
            "administrative_areas": [item.administrative_area for item in self.options],
            "original_name": self.original_name,
            "reason": self.reason,
            "ref_id": self.ref_id,
            "source_field_path": self.source_field_path,
            "suggested_name": self.replacement_name,
            "suggested_names": [item.name for item in self.options],
        }


@dataclass(frozen=True)
class CandidateNameFixResult:
    """All decisions plus the number of names written by this invocation."""

    decisions: Tuple[CandidateNameDecision, ...]
    applied_count: int

    @property
    def automatic_count(self) -> int:
        return sum(1 for item in self.decisions if item.automatic)

    @property
    def manual_count(self) -> int:
        return len(self.decisions) - self.automatic_count


@dataclass(frozen=True)
class CandidateNameManualApplyResult:
    """Counts from one filled manual-name review list."""

    entry_count: int
    applied_count: int
    skipped_count: int


@dataclass(frozen=True)
class _CandidateNameObservation:
    ref_id: str
    identity_reason: str
    source_field_path: str
    options: Tuple[CandidateNameOption, ...]
    error: Optional[str]


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
        pointer_ok = True
        try:
            _resolve_pointer(value, unknown["field_path"])
        except CandidatePointerError as exc:
            pointer_ok = False
            add("C_UNKNOWN_PATH", path + "/field_path", str(exc))
        if pointer_ok and claim_id is not None and claim_id in claim_ids:
            subject_ref = claim_ids[claim_id]["subject_ref"]
            expected_path = entity_ids.get(subject_ref)
            actual_path = _candidate_pointer_entity_path(unknown["field_path"])
            if expected_path is not None and actual_path != expected_path:
                expected_index = expected_path.rsplit("/", 1)[1]
                add(
                    "C_UNKNOWN_SUBJECT",
                    path + "/field_path",
                    "unknown field_path targets %s but claim %s subject_ref %s is %s; "
                    "expected_index=%s; expected_prefix=%s"
                    % (
                        actual_path or "a non-candidate path",
                        claim_id,
                        subject_ref,
                        expected_path,
                        expected_index,
                        expected_path,
                    ),
                )

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


def fix_candidate_names(
    candidates_path: Path,
    trip_or_journey_path: Path,
    *,
    apply: bool = False,
) -> CandidateNameFixResult:
    """Report or apply safe candidate-name feedback from a Trip or Journey.

    Trip array indexes are deliberately retained only for user-facing provenance.
    Candidate lookup and mutation always use the ref_id embedded in the runtime
    identity-conflict reason.
    """

    destination = Path(candidates_path)
    if apply and destination.is_symlink():
        raise ValueError("candidate path must not be a symlink")
    document = read_json(destination)
    report = validate_candidates(document)
    if not report.ok:
        raise ValueError("candidate file is invalid: " + "; ".join(
            issue.render() for issue in report.errors
        ))

    source = read_json(Path(trip_or_journey_path))
    observations = _candidate_name_observations(source)
    entities = _candidate_entities(document)
    decisions = tuple(
        _candidate_name_decision(ref_id, grouped, entities)
        for ref_id, grouped in observations.items()
    )

    replacements: Dict[Tuple[Any, ...], str] = {}
    if apply:
        for decision in decisions:
            if not decision.automatic:
                continue
            group, index, entity = entities[decision.ref_id]
            replacements[(group, index, "name")] = decision.replacement_name or ""
            entity["name"] = decision.replacement_name
        if replacements:
            updated_report = validate_candidates(document)
            if not updated_report.ok:
                raise ValueError("fixed candidates are invalid: " + "; ".join(
                    issue.render() for issue in updated_report.errors
                ))
            original_bytes = destination.read_bytes()
            try:
                original_text = original_bytes.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError("candidate file must be UTF-8 JSON") from exc
            updated_text = _replace_json_string_values(original_text, replacements)
            if json.loads(updated_text) != document:
                raise ValueError("candidate file changed while names were being prepared")
            destination.write_bytes(updated_text.encode("utf-8"))

    return CandidateNameFixResult(decisions, len(replacements))


def export_candidate_name_review(
    candidates_path: Path,
    trip_or_journey_path: Path,
    review_path: Path,
) -> Tuple[CandidateNameFixResult, int]:
    """Write every manual decision as a human-fillable, read-only review list."""

    source_path = Path(candidates_path)
    destination = Path(review_path)
    if _paths_refer_to_same_file(source_path, destination):
        raise ValueError("manual name review output must not be the candidate file")
    result = fix_candidate_names(source_path, trip_or_journey_path, apply=False)
    entries = []
    for decision in result.decisions:
        if decision.automatic:
            continue
        entries.append({
            "administrative_areas": [
                option.administrative_area for option in decision.options
            ],
            "chosen": "",
            "original_name": decision.original_name,
            "ref_id": decision.ref_id,
            "suggested_names": [option.name for option in decision.options],
        })
    destination.write_text(
        json.dumps(
            entries,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    return result, len(entries)


def apply_candidate_name_review(
    candidates_path: Path,
    trip_or_journey_path: Path,
    review_path: Path,
) -> Tuple[CandidateNameFixResult, CandidateNameManualApplyResult]:
    """Apply exact, currently suggested manual choices and preserve all other bytes."""

    destination = Path(candidates_path)
    if destination.is_symlink():
        raise ValueError("candidate path must not be a symlink")
    result = fix_candidate_names(destination, trip_or_journey_path, apply=False)
    review = _read_candidate_name_review(Path(review_path))

    original_bytes = destination.read_bytes()
    try:
        original_text = original_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("candidate file must be UTF-8 JSON") from exc
    document = json.loads(original_text)
    if not isinstance(document, dict):
        raise ValueError("candidate file must be a JSON object")
    report = validate_candidates(document)
    if not report.ok:
        raise ValueError("candidate file is invalid: " + "; ".join(
            issue.render() for issue in report.errors
        ))

    entities = _candidate_entities(document)
    current_decisions = {
        decision.ref_id: decision
        for decision in result.decisions
    }
    prepared: List[Tuple[str, int, str]] = []
    seen_ref_ids: Set[str] = set()
    skipped_count = 0
    for index, entry in enumerate(review):
        if not isinstance(entry, Mapping):
            raise ValueError("manual name review entry %d must be an object" % index)
        ref_id = entry.get("ref_id")
        if not isinstance(ref_id, str) or not ref_id:
            raise ValueError("manual name review entry %d has an invalid ref_id" % index)
        if ref_id in seen_ref_ids:
            raise ValueError("manual name review has duplicate ref_id %r" % ref_id)
        seen_ref_ids.add(ref_id)
        entity_entry = entities.get(ref_id)
        if entity_entry is None:
            raise ValueError(
                "manual name review ref_id %r is not in the candidate file" % ref_id
            )

        chosen = entry.get("chosen")
        if chosen is None or chosen == "":
            skipped_count += 1
            continue
        if not isinstance(chosen, str):
            raise ValueError(
                "manual name review chosen for ref_id %r must be a string" % ref_id
            )

        decision = current_decisions.get(ref_id)
        if decision is None:
            raise ValueError(
                "manual name review ref_id %r has no current name suggestions" % ref_id
            )
        current_suggestions = [option.name for option in decision.options]
        listed_suggestions = entry.get("suggested_names")
        if listed_suggestions != current_suggestions:
            raise ValueError(
                "manual name review suggested_names for ref_id %r do not exactly "
                "match the current suggestions" % ref_id
            )
        if chosen not in current_suggestions:
            raise ValueError(
                "manual name review chosen for ref_id %r must exactly match one of "
                "suggested_names" % ref_id
            )
        group, entity_index, entity = entity_entry
        if (
            entry.get("original_name") != entity["name"]
            or decision.original_name != entity["name"]
        ):
            raise ValueError(
                "manual name review original_name for ref_id %r no longer matches "
                "the candidate file" % ref_id
            )
        prepared.append((group, entity_index, chosen))

    replacements: Dict[Tuple[Any, ...], str] = {}
    for group, entity_index, chosen in prepared:
        replacements[(group, entity_index, "name")] = chosen
        document[group][entity_index]["name"] = chosen
    if replacements:
        updated_report = validate_candidates(document)
        if not updated_report.ok:
            raise ValueError("manually fixed candidates are invalid: " + "; ".join(
                issue.render() for issue in updated_report.errors
            ))
        updated_text = _replace_json_string_values(original_text, replacements)
        if json.loads(updated_text) != document:
            raise ValueError("candidate file changed while manual names were being prepared")
        _replace_candidate_bytes_atomically(
            destination,
            original_bytes,
            updated_text.encode("utf-8"),
        )

    return result, CandidateNameManualApplyResult(
        entry_count=len(review),
        applied_count=len(replacements),
        skipped_count=skipped_count,
    )


def _read_candidate_name_review(path: Path) -> List[Any]:
    with path.open("r", encoding="utf-8") as handle:
        review = json.load(handle)
    if not isinstance(review, list):
        raise ValueError("manual name review must be a JSON array")
    return review


def _paths_refer_to_same_file(left: Path, right: Path) -> bool:
    try:
        return left.samefile(right)
    except OSError:
        return left.resolve() == right.resolve()


def _candidate_entities(
    document: Mapping[str, Any],
) -> Dict[str, Tuple[str, int, Dict[str, Any]]]:
    entities: Dict[str, Tuple[str, int, Dict[str, Any]]] = {}
    for group, id_key in (("pois", "poi_id"), ("lodgings", "lodging_id")):
        for index, entity in enumerate(document[group]):
            entities[entity[id_key]] = (group, index, entity)
    return entities


def _candidate_name_observations(
    source: Mapping[str, Any],
) -> Dict[str, List[_CandidateNameObservation]]:
    if isinstance(source.get("trip_id"), str):
        trips: Sequence[Any] = (source,)
    elif isinstance(source.get("journey_id"), str):
        trips_value = source.get("trips")
        if not isinstance(trips_value, list) or not trips_value:
            raise ValueError("Journey must contain at least one Trip")
        trips = trips_value
    else:
        raise ValueError("name feedback source must be a Trip or Journey JSON document")

    grouped: Dict[str, List[_CandidateNameObservation]] = {}
    for trip in trips:
        if not isinstance(trip, Mapping) or not isinstance(trip.get("trip_id"), str):
            raise ValueError("Journey trips must be complete Trip JSON documents")
        unknowns = trip.get("unknowns")
        if not isinstance(unknowns, list):
            raise ValueError("Trip unknowns must be an array")
        for unknown in unknowns:
            observation = _candidate_name_observation(unknown)
            if observation is not None:
                grouped.setdefault(observation.ref_id, []).append(observation)
    return grouped


def _candidate_name_observation(unknown: Any) -> Optional[_CandidateNameObservation]:
    if not isinstance(unknown, Mapping) or unknown.get("provider") != "amap":
        return None
    field_path = unknown.get("field_path")
    if not isinstance(field_path, str):
        return None
    pointer_parts = field_path.split("/")
    if (
        len(pointer_parts) != 4
        or pointer_parts[0] != ""
        or pointer_parts[1] not in ("pois", "lodgings")
        or not pointer_parts[2].isdigit()
        or pointer_parts[3] not in ("coordinates", "name")
    ):
        return None
    reason = unknown.get("reason")
    if not isinstance(reason, str):
        return None
    parts = reason.split(":", 3)
    if len(parts) != 4 or parts[0] not in (
        "identity_conflict", "incomplete_address",
    ):
        return None
    ref_id = parts[1].strip()
    identity_reason = parts[2].strip()
    if not ref_id or not identity_reason:
        raise ValueError("identity-conflict feedback must include ref_id and reason")
    try:
        feedback = json.loads(parts[3])
    except json.JSONDecodeError:
        return _CandidateNameObservation(
            ref_id, identity_reason, field_path, (), "invalid_feedback_json",
        )
    options, error = _candidate_name_options(feedback)
    return _CandidateNameObservation(
        ref_id, identity_reason, field_path, options, error,
    )


def _candidate_name_options(
    feedback: Any,
) -> Tuple[Tuple[CandidateNameOption, ...], Optional[str]]:
    if not isinstance(feedback, Mapping):
        return (), "invalid_feedback_object"
    suggestions = feedback.get("suggested_names")
    projected = feedback.get("candidates")
    if (
        not isinstance(suggestions, list)
        or not suggestions
        or any(not isinstance(name, str) or not name.strip() for name in suggestions)
    ):
        return (), "invalid_suggested_names"
    if not isinstance(projected, list) or not projected:
        return (), "invalid_feedback_candidates"
    options: List[CandidateNameOption] = []
    for item in projected:
        if not isinstance(item, Mapping):
            return tuple(options), "invalid_feedback_candidates"
        name = item.get("name")
        administrative_area = item.get("administrative_area")
        if (
            not isinstance(name, str)
            or not name.strip()
            or not isinstance(administrative_area, str)
            or not administrative_area.strip()
        ):
            return tuple(options), "invalid_feedback_candidates"
        options.append(CandidateNameOption(name, administrative_area))
    if [item.name for item in options] != suggestions:
        return tuple(options), "feedback_name_mismatch"
    return _deduplicate_name_options(options), None


def _deduplicate_name_options(
    options: Sequence[CandidateNameOption],
) -> Tuple[CandidateNameOption, ...]:
    deduplicated = []
    seen_names = []
    for option in options:
        if option.name in seen_names:
            continue
        seen_names.append(option.name)
        deduplicated.append(option)
    return tuple(deduplicated)


def _candidate_name_decision(
    ref_id: str,
    observations: Sequence[_CandidateNameObservation],
    entities: Mapping[str, Tuple[str, int, Dict[str, Any]]],
) -> CandidateNameDecision:
    first = observations[0]
    combined_options: List[CandidateNameOption] = []
    for observation in observations:
        for option in observation.options:
            if option not in combined_options:
                combined_options.append(option)
    entity_entry = entities.get(ref_id)
    original_name = entity_entry[2]["name"] if entity_entry is not None else None
    signatures = {
        (observation.identity_reason, observation.options, observation.error)
        for observation in observations
    }
    if len(signatures) != 1:
        return CandidateNameDecision(
            ref_id, original_name, tuple(combined_options), None,
            "conflicting_feedback", first.source_field_path,
        )
    if first.error is not None:
        return CandidateNameDecision(
            ref_id, original_name, first.options, None,
            first.error, first.source_field_path,
        )
    if entity_entry is None:
        return CandidateNameDecision(
            ref_id, None, first.options, None,
            "ref_id_not_found", first.source_field_path,
        )

    replacement, reason = _unique_candidate_name(original_name, first.options)
    return CandidateNameDecision(
        ref_id, original_name, first.options, replacement, reason,
        first.source_field_path,
    )


def _unique_candidate_name(
    original_name: str,
    options: Sequence[CandidateNameOption],
) -> Tuple[Optional[str], str]:
    deduplicated = _deduplicate_name_options(options)
    if not deduplicated:
        return None, "no_suggested_name"

    # Import lazily because mobility imports validate_candidates from this module.
    # Reusing this exact decision keeps name selection aligned with mobility
    # without changing or copying its similarity threshold here.
    from .mobility import _poi_name_is_ambiguous

    preferred = deduplicated[0].name
    if preferred == original_name:
        return preferred, "exact_original_confirmed"
    if _poi_name_is_ambiguous(
        original_name,
        tuple({"name": option.name} for option in deduplicated),
    ):
        return None, "ambiguous_suggestions"
    return preferred, "unique_suggestion"


def _replace_json_string_values(
    source: str,
    replacements: Mapping[Tuple[Any, ...], str],
) -> str:
    """Replace selected JSON string values while preserving every other byte."""

    decoder = json.JSONDecoder()
    spans: Dict[Tuple[Any, ...], Tuple[int, int]] = {}

    def skip_space(index: int) -> int:
        while index < len(source) and source[index] in " \t\r\n":
            index += 1
        return index

    def walk(index: int, path: Tuple[Any, ...]) -> int:
        index = skip_space(index)
        if index >= len(source):
            raise ValueError("candidate JSON ended unexpectedly")
        if source[index] == "{":
            index = skip_space(index + 1)
            if index < len(source) and source[index] == "}":
                return index + 1
            while True:
                key, key_end = decoder.raw_decode(source, index)
                if not isinstance(key, str):
                    raise ValueError("candidate JSON object key must be text")
                index = skip_space(key_end)
                if index >= len(source) or source[index] != ":":
                    raise ValueError("candidate JSON object is missing ':'")
                index = walk(index + 1, path + (key,))
                index = skip_space(index)
                if index < len(source) and source[index] == "}":
                    return index + 1
                if index >= len(source) or source[index] != ",":
                    raise ValueError("candidate JSON object is missing ','")
                index = skip_space(index + 1)
        if source[index] == "[":
            index = skip_space(index + 1)
            if index < len(source) and source[index] == "]":
                return index + 1
            item_index = 0
            while True:
                index = walk(index, path + (item_index,))
                item_index += 1
                index = skip_space(index)
                if index < len(source) and source[index] == "]":
                    return index + 1
                if index >= len(source) or source[index] != ",":
                    raise ValueError("candidate JSON array is missing ','")
                index = skip_space(index + 1)

        value_start = index
        value, value_end = decoder.raw_decode(source, index)
        if path in replacements:
            if not isinstance(value, str) or path in spans:
                raise ValueError("candidate name path is not one unique JSON string")
            spans[path] = (value_start, value_end)
        return value_end

    end = skip_space(walk(0, ()))
    if end != len(source):
        raise ValueError("candidate JSON has trailing non-whitespace data")
    missing = set(replacements) - set(spans)
    if missing:
        raise ValueError("candidate name path is missing from JSON")

    updated = source
    ordered = sorted(
        ((spans[path][0], spans[path][1], value) for path, value in replacements.items()),
        reverse=True,
    )
    for start, finish, value in ordered:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
        updated = updated[:start] + encoded + updated[finish:]
    return updated


def _replace_candidate_bytes_atomically(
    destination: Path,
    original_bytes: bytes,
    updated_bytes: bytes,
) -> None:
    """Atomically install validated bytes and restore the exact original on failure."""

    mode = destination.stat().st_mode & 0o7777
    updated_path: Optional[Path] = None
    backup_path: Optional[Path] = None
    try:
        updated_path = _stage_bytes(destination, updated_bytes, mode, "updated")
        staged_report = validate_candidates_file(updated_path)
        if not staged_report.ok:
            raise ValueError("manually fixed candidates are invalid before write: " + "; ".join(
                issue.render() for issue in staged_report.errors
            ))
        backup_path = _stage_bytes(destination, original_bytes, mode, "backup")
        if destination.read_bytes() != original_bytes:
            raise ValueError("candidate file changed while manual names were being prepared")

        os.replace(str(updated_path), str(destination))
        updated_path = None
        try:
            written_report = validate_candidates_file(destination)
            if not written_report.ok:
                raise ValueError("manually fixed candidates failed post-write validation: " + "; ".join(
                    issue.render() for issue in written_report.errors
                ))
        except Exception:
            try:
                os.replace(str(backup_path), str(destination))
                backup_path = None
            except OSError as rollback_error:
                raise RuntimeError(
                    "manual candidate-name write failed and rollback could not be completed"
                ) from rollback_error
            if destination.read_bytes() != original_bytes:
                raise RuntimeError(
                    "manual candidate-name write rollback did not restore the original bytes"
                )
            raise
    finally:
        for temporary_path in (updated_path, backup_path):
            if temporary_path is not None:
                try:
                    temporary_path.unlink()
                except FileNotFoundError:
                    pass


def _stage_bytes(
    destination: Path,
    payload: bytes,
    mode: int,
    label: str,
) -> Path:
    descriptor, raw_path = tempfile.mkstemp(
        prefix=".%s.%s." % (destination.name, label),
        suffix=".tmp",
        dir=str(destination.parent),
    )
    temporary_path = Path(raw_path)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass
        raise
    return temporary_path


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


def _candidate_pointer_entity_path(pointer: str) -> Optional[str]:
    parts = pointer[1:].split("/") if pointer.startswith("/") else []
    if len(parts) < 2:
        return None
    group = parts[0].replace("~1", "/").replace("~0", "~")
    index = parts[1].replace("~1", "/").replace("~0", "~")
    if group not in ("pois", "lodgings") or not index.isdigit():
        return None
    return "/%s/%d" % (group, int(index))
