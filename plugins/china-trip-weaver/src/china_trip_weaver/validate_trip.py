"""Dependency-free schema subset and release-critical Trip semantics."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple
from urllib.parse import urlsplit

from .contracts import canonical_json


MODE_RANK = {"live": 0, "cached": 1, "static": 2, "mock": 3}
SUPPORTED_KEYWORDS = {
    "$schema", "$id", "$defs", "$ref", "title", "description",
    "type", "additionalProperties", "required", "properties", "allOf",
    "if", "then", "oneOf", "const", "enum", "pattern", "format",
    "minimum", "maximum", "minLength", "maxLength", "minItems",
    "maxItems", "items", "uniqueItems",
}
SECRET_PATTERNS = (
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)


@dataclass(frozen=True, order=True)
class ValidationIssue:
    code: str
    path: str
    message: str

    def render(self) -> str:
        return "%s %s %s" % (self.code, self.path, self.message)


@dataclass(frozen=True)
class ValidationReport:
    errors: Tuple[ValidationIssue, ...]
    warnings: Tuple[ValidationIssue, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.errors


def default_schema_path() -> Path:
    return Path(__file__).resolve().parents[2] / "schema" / "trip.schema.json"


def _pointer(path: str, part: Any) -> str:
    escaped = str(part).replace("~", "~0").replace("/", "~1")
    return path + "/" + escaped if path else "/" + escaped


def _json_type_matches(expected: str, value: Any) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return False


class SchemaSubsetValidator:
    """Validate every keyword used by the frozen v1 schema, failing on new ones."""

    def __init__(self, schema: Mapping[str, Any]) -> None:
        self.schema = schema
        unsupported = self._check_keywords(schema)
        if unsupported:
            raise ValueError("unsupported schema keyword(s): %s" % ", ".join(sorted(unsupported)))

    def _check_keywords(self, schema: Any, parent_key: Optional[str] = None) -> Set[str]:
        found: Set[str] = set()
        if isinstance(schema, dict):
            for key, child in schema.items():
                if parent_key not in ("properties", "$defs") and key not in SUPPORTED_KEYWORDS:
                    found.add(key)
                found.update(self._check_keywords(child, key))
        elif isinstance(schema, list):
            for child in schema:
                found.update(self._check_keywords(child, parent_key))
        return found

    def validate(self, value: Any) -> List[ValidationIssue]:
        unsupported = self._check_keywords(self.schema)
        if unsupported:
            raise ValueError("unsupported schema keyword(s): %s" % ", ".join(sorted(unsupported)))
        issues: List[ValidationIssue] = []
        self._validate(self.schema, value, "", issues)
        return issues

    def validate_fragment(self, reference: str, value: Any) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        self._validate({"$ref": reference}, value, "", issues)
        return issues

    def _resolve(self, reference: str) -> Mapping[str, Any]:
        if not reference.startswith("#/"):
            raise ValueError("only local schema references are supported")
        value: Any = self.schema
        for part in reference[2:].split("/"):
            value = value[part.replace("~1", "/").replace("~0", "~")]
        if not isinstance(value, dict):
            raise ValueError("schema reference does not resolve to an object")
        return value

    def _matches(self, schema: Mapping[str, Any], value: Any, path: str) -> bool:
        issues: List[ValidationIssue] = []
        self._validate(schema, value, path, issues)
        return not issues

    def _validate(
        self,
        schema: Mapping[str, Any],
        value: Any,
        path: str,
        issues: List[ValidationIssue],
    ) -> None:
        if "$ref" in schema:
            self._validate(self._resolve(schema["$ref"]), value, path, issues)
            return

        if "oneOf" in schema:
            matches = sum(1 for candidate in schema["oneOf"] if self._matches(candidate, value, path))
            if matches != 1:
                issues.append(ValidationIssue("S_ONE_OF", path or "/", "must match exactly one allowed shape"))
                return

        expected = schema.get("type")
        if expected is not None:
            expected_types = [expected] if isinstance(expected, str) else list(expected)
            if not any(_json_type_matches(item, value) for item in expected_types):
                issues.append(ValidationIssue("S_TYPE", path or "/", "expected %s" % " or ".join(expected_types)))
                return

        if "const" in schema and value != schema["const"]:
            issues.append(ValidationIssue("S_CONST", path or "/", "must equal %r" % schema["const"]))
        if "enum" in schema and value not in schema["enum"]:
            issues.append(ValidationIssue("S_ENUM", path or "/", "value is not in the allowed set"))

        if isinstance(value, dict):
            required = schema.get("required", [])
            for key in required:
                if key not in value:
                    issues.append(ValidationIssue("S_REQUIRED", _pointer(path, key), "required property is missing"))
            properties = schema.get("properties", {})
            if schema.get("additionalProperties") is False:
                for key in value:
                    if key not in properties:
                        issues.append(ValidationIssue("S_ADDITIONAL", _pointer(path, key), "additional property is not allowed"))
            for key, child_schema in properties.items():
                if key in value:
                    self._validate(child_schema, value[key], _pointer(path, key), issues)

        if isinstance(value, list):
            if "minItems" in schema and len(value) < schema["minItems"]:
                issues.append(ValidationIssue("S_MIN_ITEMS", path or "/", "contains too few items"))
            if "maxItems" in schema and len(value) > schema["maxItems"]:
                issues.append(ValidationIssue("S_MAX_ITEMS", path or "/", "contains too many items"))
            if schema.get("uniqueItems"):
                encoded = [canonical_json(item) for item in value]
                if len(encoded) != len(set(encoded)):
                    issues.append(ValidationIssue("S_UNIQUE", path or "/", "items must be unique"))
            if "items" in schema:
                for index, item in enumerate(value):
                    self._validate(schema["items"], item, _pointer(path, index), issues)

        if isinstance(value, str):
            if "minLength" in schema and len(value) < schema["minLength"]:
                issues.append(ValidationIssue("S_MIN_LENGTH", path or "/", "string is too short"))
            if "maxLength" in schema and len(value) > schema["maxLength"]:
                issues.append(ValidationIssue("S_MAX_LENGTH", path or "/", "string is too long"))
            if "pattern" in schema and re.search(schema["pattern"], value) is None:
                issues.append(ValidationIssue("S_PATTERN", path or "/", "string does not match the required pattern"))
            if "format" in schema and not _format_valid(schema["format"], value):
                issues.append(ValidationIssue("S_FORMAT", path or "/", "invalid %s" % schema["format"]))

        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if "minimum" in schema and value < schema["minimum"]:
                issues.append(ValidationIssue("S_MINIMUM", path or "/", "number is below the minimum"))
            if "maximum" in schema and value > schema["maximum"]:
                issues.append(ValidationIssue("S_MAXIMUM", path or "/", "number is above the maximum"))

        for child in schema.get("allOf", []):
            self._validate(child, value, path, issues)
        if "if" in schema and self._matches(schema["if"], value, path) and "then" in schema:
            self._validate(schema["then"], value, path, issues)


def _format_valid(name: str, value: str) -> bool:
    try:
        if name == "date":
            date.fromisoformat(value)
            return True
        if name == "date-time":
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.tzinfo is not None
        if name == "uri":
            parsed = urlsplit(value)
            return bool(parsed.scheme and parsed.netloc and not parsed.username and not parsed.password)
    except ValueError:
        return False
    return False


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _add(issues: List[ValidationIssue], code: str, path: str, message: str) -> None:
    issues.append(ValidationIssue(code, path, message))


def _id_map(items: Sequence[Mapping[str, Any]], key: str, base_path: str, issues: List[ValidationIssue]) -> Dict[str, Mapping[str, Any]]:
    result: Dict[str, Mapping[str, Any]] = {}
    for index, item in enumerate(items):
        identifier = item[key]
        if identifier in result:
            _add(issues, "V_DUPLICATE_ID", "%s/%d/%s" % (base_path, index, key), "duplicate id %s" % identifier)
        result[identifier] = item
    return result


def _iter_claim_ids(trip: Mapping[str, Any]) -> Iterable[Tuple[str, str]]:
    for group in ("transport_legs", "lodgings", "pois"):
        for index, item in enumerate(trip[group]):
            for claim_index, claim_id in enumerate(item["claim_ids"]):
                yield "/%s/%d/claim_ids/%d" % (group, index, claim_index), claim_id
            price = item.get("price")
            if price and price.get("claim_id") is not None:
                yield "/%s/%d/price/claim_id" % (group, index), price["claim_id"]
            for window_index, window in enumerate(item.get("opening_windows", [])):
                if window.get("claim_id") is not None:
                    yield "/%s/%d/opening_windows/%d/claim_id" % (group, index, window_index), window["claim_id"]
    for day_index, day_item in enumerate(trip["days"]):
        for slot_index, slot in enumerate(day_item["slots"]):
            for claim_index, claim_id in enumerate(slot["claim_ids"]):
                yield "/days/%d/slots/%d/claim_ids/%d" % (day_index, slot_index, claim_index), claim_id


def _walk(value: Any, path: str = "") -> Iterable[Tuple[str, Any]]:
    yield path or "/", value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _walk(child, _pointer(path, key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, _pointer(path, index))


def _resolve_pointer(document: Any, pointer: str) -> Any:
    if not pointer.startswith("/"):
        raise KeyError(pointer)
    value = document
    for raw in pointer[1:].split("/"):
        part = raw.replace("~1", "/").replace("~0", "~")
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def semantic_issues(trip: Mapping[str, Any]) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    day_map = _id_map(trip["days"], "day_id", "/days", issues)
    leg_map = _id_map(trip["transport_legs"], "leg_id", "/transport_legs", issues)
    lodging_map = _id_map(trip["lodgings"], "lodging_id", "/lodgings", issues)
    poi_map = _id_map(trip["pois"], "poi_id", "/pois", issues)
    claim_map = _id_map(trip["claims"], "claim_id", "/claims", issues)
    health_map = _id_map(trip["provider_health"], "provider", "/provider_health", issues)
    del health_map

    slot_ids: Set[str] = set()
    all_refs: Set[str] = {trip["trip_id"], "request"}
    all_refs.update(day_map)
    all_refs.update(leg_map)
    all_refs.update(lodging_map)
    all_refs.update(poi_map)
    request = trip["request"]
    origins = [
        group["origin"]
        for group in (request.get("traveler_groups") or ())
    ]
    if request.get("origin"):
        origins.append(request["origin"])
    all_refs.update(origin["ref_id"] for origin in origins)
    meeting_anchor = request.get("meeting_anchor")
    if meeting_anchor:
        all_refs.add(meeting_anchor["location"]["ref_id"])
    all_refs.update(place["ref_id"] for place in request["destinations"])

    start_date = date.fromisoformat(request["start_date"])
    end_date = date.fromisoformat(request["end_date"])
    if end_date < start_date:
        _add(issues, "V_DATE_RANGE", "/request/end_date", "end_date precedes start_date")
    expected_dates = []
    if end_date >= start_date:
        expected_dates = [(start_date + timedelta(days=index)).isoformat() for index in range((end_date - start_date).days + 1)]
        if len(expected_dates) != len(trip["days"]):
            _add(issues, "V_DAY_COUNT", "/days", "days must cover the inclusive request date range")
    actual_dates = [item["date"] for item in trip["days"]]
    if expected_dates and actual_dates != expected_dates:
        _add(issues, "V_DAY_DATES", "/days", "day dates must be ordered and match the request")
    if (len(request["destinations"]) > 1 or any(leg["travel_mode"] in ("rail", "flight") for leg in trip["transport_legs"])) and not origins:
        _add(issues, "V_ORIGIN_REQUIRED", "/request/origin", "cross-city travel requires an origin")

    for day_index, day_item in enumerate(trip["days"]):
        previous_end: Optional[datetime] = None
        for slot_index, slot in enumerate(day_item["slots"]):
            slot_path = "/days/%d/slots/%d" % (day_index, slot_index)
            if slot["slot_id"] in slot_ids:
                _add(issues, "V_DUPLICATE_ID", slot_path + "/slot_id", "duplicate slot id")
            slot_ids.add(slot["slot_id"])
            all_refs.add(slot["slot_id"])
            start = _parse_datetime(slot["start_at"])
            end = _parse_datetime(slot["end_at"])
            if end <= start:
                _add(issues, "V_SLOT_ORDER", slot_path, "slot end must be after start")
            if start.date().isoformat() != day_item["date"]:
                _add(issues, "V_SLOT_DATE", slot_path + "/start_at", "slot must start on its day")
            if start.utcoffset() != timedelta(hours=8) or end.utcoffset() != timedelta(hours=8):
                _add(issues, "V_TIMEZONE", slot_path, "slot timestamps must use Asia/Shanghai offset")
            if previous_end is not None and start < previous_end:
                _add(issues, "V_SLOT_OVERLAP", slot_path, "slots must be sorted and non-overlapping")
            previous_end = max(previous_end, end) if previous_end is not None else end

            ref_id = slot["ref_id"]
            kind = slot["kind"]
            compatible = True
            if kind in ("poi", "meal"):
                compatible = ref_id in poi_map
            elif kind == "transport":
                compatible = ref_id in leg_map
            elif kind in ("lodging", "checkin", "checkout"):
                compatible = ref_id in lodging_map
            elif kind in ("rest", "free"):
                compatible = ref_id is None
            if not compatible:
                _add(issues, "V_REF_KIND", slot_path + "/ref_id", "ref_id is incompatible with slot kind")

            if kind == "transport" and ref_id in leg_map:
                leg = leg_map[ref_id]
                if leg["depart_at"] is not None and start > _parse_datetime(leg["depart_at"]):
                    _add(issues, "V_TRANSPORT_COVERAGE", slot_path, "transport slot starts after departure")
                if leg["arrive_at"] is not None and end < _parse_datetime(leg["arrive_at"]):
                    _add(issues, "V_TRANSPORT_COVERAGE", slot_path, "transport slot ends before arrival")
            if kind in ("poi", "meal") and ref_id in poi_map and slot["status"] == "scheduled":
                windows = [window for window in poi_map[ref_id]["opening_windows"] if window["status"] in ("verified", "tentative")]
                if windows and not any(_parse_datetime(window["start_at"]) <= start and end <= _parse_datetime(window["end_at"]) for window in windows):
                    _add(issues, "V_OPENING_WINDOW", slot_path, "scheduled visit is outside every usable opening window")

    for path, claim_id in _iter_claim_ids(trip):
        if claim_id not in claim_map:
            _add(issues, "V_CLAIM_REF", path, "claim_id does not exist")

    for index, claim in enumerate(trip["claims"]):
        if claim["subject_ref"] not in all_refs:
            _add(issues, "V_CLAIM_SUBJECT", "/claims/%d/subject_ref" % index, "claim subject does not exist")

    for index, leg in enumerate(trip["transport_legs"]):
        path = "/transport_legs/%d" % index
        if leg["from_ref"] not in all_refs:
            _add(issues, "V_ENDPOINT_REF", path + "/from_ref", "transport endpoint does not exist")
        if leg["to_ref"] not in all_refs:
            _add(issues, "V_ENDPOINT_REF", path + "/to_ref", "transport endpoint does not exist")
        if leg["depart_at"] is not None and leg["arrive_at"] is not None:
            depart = _parse_datetime(leg["depart_at"])
            arrive = _parse_datetime(leg["arrive_at"])
            if arrive <= depart:
                _add(issues, "V_TRANSPORT_ORDER", path, "arrival must be after departure")
            elif leg["duration_minutes"] is not None and int((arrive - depart).total_seconds() // 60) != leg["duration_minutes"]:
                _add(issues, "V_DURATION", path + "/duration_minutes", "duration does not match timestamps")

    for group in ("transport_legs", "lodgings", "pois"):
        for index, item in enumerate(trip[group]):
            price = item.get("price")
            if price:
                price_path = "/%s/%d/price" % (group, index)
                if price["price_type"] == "unknown" and price["amount"] is not None:
                    _add(issues, "V_UNKNOWN_PRICE", price_path + "/amount", "unknown price must have null amount")
                if price["claim_id"] is not None:
                    claim = claim_map.get(price["claim_id"])
                    item_id = item.get("leg_id") or item.get("lodging_id") or item.get("poi_id")
                    if claim and claim["subject_ref"] != item_id:
                        _add(issues, "V_PRICE_CLAIM", price_path + "/claim_id", "price claim belongs to another subject")

    for group in ("lodgings", "pois"):
        for index, item in enumerate(trip[group]):
            coordinates = item["coordinates"]
            if not coordinates:
                continue
            path = "/%s/%d/coordinates" % (group, index)
            source = coordinates["source_crs"]
            native = coordinates["native"]
            derived = set(coordinates["conversion"]["derived_fields"])
            if source == "WGS84":
                if coordinates["wgs84"] != native or "wgs84" in derived:
                    _add(issues, "V_COORDINATE_NATIVE", path, "WGS84 native point must be preserved")
            elif source == "GCJ02":
                if coordinates["gcj02"] != native or "gcj02" in derived:
                    _add(issues, "V_COORDINATE_NATIVE", path, "GCJ02 native point must be preserved")
            elif source == "BD09":
                if derived != {"wgs84", "gcj02"}:
                    _add(issues, "V_COORDINATE_DERIVED", path, "BD09 must derive both WGS84 and GCJ02")
            elif source == "provider-unknown":
                if coordinates["wgs84"] is not None or coordinates["gcj02"] is not None or derived:
                    _add(issues, "V_COORDINATE_UNKNOWN", path, "unknown CRS must not be converted")
            if coordinates["conversion"]["status"] == "converted" and not derived:
                _add(issues, "V_COORDINATE_DERIVED", path + "/conversion/derived_fields", "converted coordinates must name a derived field")

    component_modes: List[str] = []
    component_modes.extend(leg["data_mode"] for leg in trip["transport_legs"])
    component_modes.extend(claim["mode"] for claim in trip["claims"])
    component_modes.extend(health["mode"] for health in trip["provider_health"])
    if component_modes and MODE_RANK[trip["mode"]] < max(MODE_RANK[mode] for mode in component_modes):
        _add(issues, "V_TOP_MODE", "/mode", "top mode is less conservative than a component mode")

    revision = trip["revision"]
    patches = trip["patches"]
    if revision["number"] == 1:
        if revision["parent_revision"] is not None or patches:
            _add(issues, "V_REVISION_INITIAL", "/revision", "revision 1 must have no parent or patches")
    else:
        if revision["parent_revision"] != revision["number"] - 1:
            _add(issues, "V_REVISION_PARENT", "/revision/parent_revision", "parent revision must be current minus one")
        if not patches or patches[-1]["target_revision"] != revision["number"]:
            _add(issues, "V_PATCH_CURRENT", "/patches", "last patch must produce the current revision")
    expected_base = 1
    for index, patch in enumerate(patches):
        path = "/patches/%d" % index
        if patch["base_revision"] != expected_base or patch["target_revision"] != expected_base + 1:
            _add(issues, "V_PATCH_SEQUENCE", path, "patch revisions must be contiguous")
        expected_base = patch["target_revision"]
        for op_index, operation in enumerate(patch["operations"]):
            if operation["op"] not in ("add", "remove", "replace", "move"):
                _add(issues, "V_PATCH_OP", "%s/operations/%d/op" % (path, op_index), "operation is outside the v1 whitelist")
            if operation["op"] == "move" and "from" not in operation:
                _add(issues, "V_PATCH_FROM", "%s/operations/%d" % (path, op_index), "move requires from")

    for index, unknown in enumerate(trip["unknowns"]):
        path = "/unknowns/%d" % index
        if unknown["claim_id"] is not None and unknown["claim_id"] not in claim_map:
            _add(issues, "V_UNKNOWN_CLAIM", path + "/claim_id", "unknown references a missing claim")
        try:
            _resolve_pointer(trip, unknown["field_path"])
        except (KeyError, IndexError, ValueError):
            _add(issues, "V_UNKNOWN_PATH", path + "/field_path", "unknown path does not resolve")

    for path, value in _walk(trip):
        if isinstance(value, str):
            for pattern in SECRET_PATTERNS:
                if pattern.search(value):
                    _add(issues, "V_SECRET", path, "credential-shaped value is forbidden")
                    break
            parsed = urlsplit(value) if value.startswith(("http://", "https://")) else None
            if parsed and (parsed.username or parsed.password):
                _add(issues, "V_URL_CREDENTIAL", path, "URL credentials are forbidden")

    return sorted(set(issues))


def load_schema(path: Optional[Path] = None) -> Mapping[str, Any]:
    schema_path = path or default_schema_path()
    with schema_path.open("r", encoding="utf-8") as handle:
        schema = json.load(handle)
    if not isinstance(schema, dict):
        raise ValueError("Trip schema must be a JSON object")
    return schema


def validate_trip(
    trip: Mapping[str, Any],
    schema_path: Optional[Path] = None,
    semantic: bool = True,
) -> ValidationReport:
    validator = SchemaSubsetValidator(load_schema(schema_path))
    schema_errors = validator.validate(trip)
    if schema_errors:
        return ValidationReport(tuple(sorted(set(schema_errors))))
    semantic_errors = semantic_issues(trip) if semantic else []
    return ValidationReport(tuple(semantic_errors))


def validate_file(path: Path, schema_path: Optional[Path] = None, semantic: bool = True) -> ValidationReport:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return ValidationReport((ValidationIssue("J_INVALID", "/", str(exc)),))
    if not isinstance(value, dict):
        return ValidationReport((ValidationIssue("J_OBJECT", "/", "Trip must be a JSON object"),))
    return validate_trip(value, schema_path=schema_path, semantic=semantic)
