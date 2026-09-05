"""AMap-backed candidate geocoding and bounded live route matrices."""

from __future__ import annotations

import copy
import difflib
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from .candidates import validate_candidates
from .clock import Clock, isoformat_seconds
from .contracts import ProviderRequest, canonical_json
from .credentials import CredentialResolution, resolve_credentials
from .evidence import make_claim
from .matrix import RouteCell, bounded_query_plan, haversine_meters
from .providers.amap import AMapAdapter
from .providers.amap_http import AMapCallBudget, AMapHTTPTransport, MAX_CALLS_PER_RUN, MAX_QPS
from .providers.base import ProviderContext, ProviderTransport, sanitize_text, stable_id


MODE_ALIASES = {
    "transit": "transit",
    "walking": "walk",
    "walk": "walk",
    "driving": "drive",
    "drive": "drive",
    "riding": "ride",
    "ride": "ride",
}
FATAL_ERRORS = frozenset(("credential_missing", "forbidden", "rate_limited", "contract_mismatch"))
POI_NAME_SIMILARITY_MARGIN = 0.15
SEMANTIC_OUTLIER_DISTANCE_METERS = 50_000.0


@dataclass(frozen=True)
class MobilityLocation:
    ref_id: str
    name: str
    city: str
    coordinates: Mapping[str, Any]
    claim_ids: Tuple[str, ...]

    def as_dict(self) -> Mapping[str, Any]:
        return {
            "ref_id": self.ref_id,
            "name": self.name,
            "city": self.city,
            "coordinates": copy.deepcopy(dict(self.coordinates)),
            "claim_ids": list(self.claim_ids),
        }


@dataclass(frozen=True)
class MobilityResult:
    locations: Tuple[MobilityLocation, ...]
    cells: Tuple[RouteCell, ...]
    claims: Tuple[Mapping[str, Any], ...]
    health: Mapping[str, Any]
    business_calls: Tuple[str, ...]
    warnings: Tuple[str, ...] = ()

    def as_dict(self) -> Mapping[str, Any]:
        return {
            "provider": "amap",
            "provider_version": AMapAdapter.provider_version,
            "locations": [item.as_dict() for item in self.locations],
            "matrix_cells": [item.as_dict() for item in self.cells],
            "claims": [copy.deepcopy(dict(item)) for item in self.claims],
            "health": copy.deepcopy(dict(self.health)),
            "business_calls": list(self.business_calls),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class POINameCheck:
    status: str
    reasons: Tuple[str, ...]
    feedback: Optional[str] = None

    def render(self) -> str:
        reason = ",".join(self.reasons) if self.reasons else "none"
        detail = " details=%s" % self.feedback if self.feedback is not None else ""
        return "POI_NAME_CHECK status=%s reason=%s%s" % (
            self.status, reason, detail,
        )


class MobilityBackend:
    def __init__(
        self,
        mode: str,
        credentials: CredentialResolution,
        transport: Optional[ProviderTransport],
        *,
        deadline_seconds: float = 12.0,
    ) -> None:
        if mode not in ("live", "off") or deadline_seconds <= 0:
            raise ValueError("mobility mode must be live/off with a positive deadline")
        self.mode = mode
        self.credentials = credentials
        self.transport = transport
        self.deadline_seconds = float(deadline_seconds)

    @classmethod
    def from_spec(cls, spec: str, repo_root: Path, deadline_seconds: float = 12.0) -> "MobilityBackend":
        if spec == "off":
            credentials = resolve_credentials({}, Path(repo_root) / ".tmp" / "mobility-no-credentials")
            return cls("off", credentials, None, deadline_seconds=deadline_seconds)
        if spec != "live":
            raise ValueError("--mobility must be live or off")
        credentials = resolve_credentials()
        budget = AMapCallBudget(max_calls=MAX_CALLS_PER_RUN, qps=MAX_QPS)
        return cls(
            "live",
            credentials,
            AMapHTTPTransport(credentials, budget=budget),
            deadline_seconds=deadline_seconds,
        )

    def resolve(
        self,
        candidates: Mapping[str, Any],
        clock: Clock,
        modes: Sequence[str] = ("transit",),
    ) -> MobilityResult:
        report = validate_candidates(candidates)
        if not report.ok:
            raise ValueError("invalid candidates: " + "; ".join(item.render() for item in report.errors))
        normalized_modes = normalize_modes(modes)
        now = isoformat_seconds(clock)
        if self.mode == "off":
            return MobilityResult((), (), (), _health(
                "static", "missing", now,
                "AMap mobility is off; calls=0/80 qps<=2; route matrix uses static estimates",
            ), ())
        if not self.credentials.get("AMAP_WEBSERVICE_KEY"):
            return MobilityResult((), (), (), _health(
                "static", "missing", now,
                "AMap credential is missing; calls=0/80 qps<=2; route matrix uses static estimates",
            ), ())
        if self.transport is None:
            raise ValueError("live mobility requires an AMap transport")

        adapter = AMapAdapter()
        context = ProviderContext(clock=clock, credentials=self.credentials, transport=self.transport)
        source_entities = _candidate_entities(candidates)
        locations: Dict[str, MobilityLocation] = {}
        claims: List[Mapping[str, Any]] = []
        calls: List[str] = []
        errors: List[str] = []
        warnings: List[str] = []
        fatal_status: Optional[str] = None

        for entity in source_entities:
            existing = _usable_coordinates(entity["coordinates"])
            if existing is not None:
                locations[entity["ref_id"]] = MobilityLocation(
                    entity["ref_id"], entity["name"], entity["city"], existing, (),
                )
                continue
            identity_claims: List[Mapping[str, Any]] = []
            identity_candidates: Sequence[Mapping[str, Any]] = ()
            identity_candidate_claims: Sequence[Mapping[str, Any]] = ()
            selected: Optional[Mapping[str, Any]] = None
            provider_name: Optional[str] = None
            geocode_address = "%s%s" % (entity["city"], entity["name"])
            if not entity["lodging"]:
                poi_request = ProviderRequest(
                    request_id=stable_id("amap-poi", entity["ref_id"], entity["name"], entity["city"]),
                    capability="poi",
                    parameters={
                        "subject_ref": entity["ref_id"],
                        "keywords": entity["name"],
                        "city": entity["city"],
                        "page_size": 2,
                        "page_num": 1,
                    },
                    deadline_ms=int(min(self.deadline_seconds, 8.0) * 1000),
                    as_of=now[:10],
                    cache_policy="bypass",
                    trace={"stage": "mobility-poi-identity"},
                )
                calls_before = _transport_calls(self.transport)
                poi_result = adapter.query(poi_request, context)
                if _transport_calls(self.transport) > calls_before:
                    calls.append("amap.poi:%s" % entity["ref_id"])
                identity_candidates = poi_result.normalized_items
                identity_candidate_claims = poi_result.claims
                if not poi_result.normalized_items:
                    error = poi_result.error_class or "no_results"
                    errors.append(error)
                    warnings.append(
                        "%s:%s:poi_identity_lookup:%s" % (
                            error,
                            entity["ref_id"],
                            poi_identity_feedback(
                                identity_candidates, identity_candidate_claims,
                            ),
                        )
                    )
                    if error in FATAL_ERRORS:
                        fatal_status = poi_result.health["status"]
                        break
                    continue
                selected = poi_result.normalized_items[0]
                conflict_reasons = _poi_identity_conflicts(
                    entity, poi_result.normalized_items, poi_result.claims,
                )
                if conflict_reasons:
                    claims.extend(_claims_with_status(poi_result.claims, "conflict"))
                    errors.append("identity_conflict")
                    feedback = poi_identity_feedback(
                        identity_candidates,
                        identity_candidate_claims,
                    )
                    warnings.extend(("identity_conflict",) + tuple(
                        "identity_conflict:%s:%s:%s" % (
                            entity["ref_id"], reason, feedback,
                        )
                        for reason in conflict_reasons
                    ))
                    continue
                selected_ids = set(selected.get("claim_ids", ()))
                identity_claims = [
                    copy.deepcopy(claim) for claim in poi_result.claims
                    if claim["claim_id"] in selected_ids
                ]
                identity = next(
                    (claim["value"] for claim in identity_claims if claim["field_path"] == "/provider_identity"),
                    None,
                )
                if not _complete_poi_address(identity):
                    claims.extend(_claims_with_status(identity_claims, "unknown"))
                    errors.append("incomplete_address")
                    warnings.extend((
                        "incomplete_address",
                        "incomplete_address:%s" % entity["ref_id"],
                        "incomplete_address:%s:poi_address_missing_admin_detail:%s" % (
                            entity["ref_id"],
                            poi_identity_feedback(
                                identity_candidates, identity_candidate_claims,
                            ),
                        ),
                    ))
                    continue
                if _business_conflict(entity, candidates, identity_claims):
                    identity_claims = _business_claims_with_conflict(identity_claims)
                    warnings.extend((
                        "business_conflict",
                        "business_conflict:%s" % entity["ref_id"],
                        "business_conflict:%s:provider_identity_disagrees_with_candidate" % entity["ref_id"],
                    ))
                provider_name = selected["name"]
                geocode_address = identity["formatted_address"]

            request = ProviderRequest(
                request_id=stable_id("amap-geocode", entity["ref_id"], geocode_address, entity["city"]),
                capability="geocode",
                parameters={
                    "subject_ref": entity["ref_id"],
                    "address": geocode_address,
                    "city": entity["city"],
                },
                deadline_ms=int(min(self.deadline_seconds, 8.0) * 1000),
                as_of=now[:10],
                cache_policy="bypass",
                trace={"stage": "mobility-geocode"},
            )
            calls_before = _transport_calls(self.transport)
            result = adapter.query(request, context)
            if _transport_calls(self.transport) > calls_before:
                calls.append("amap.geocode:%s" % entity["ref_id"])
            if result.normalized_items and result.claims:
                if len(result.normalized_items) != 1:
                    claims.extend(_claims_with_status(
                        identity_claims + list(result.claims), "conflict",
                    ))
                    errors.append("identity_conflict")
                    warnings.extend((
                        "identity_conflict",
                        "identity_conflict:%s:geocode_ambiguous:%s" % (
                            entity["ref_id"],
                            poi_identity_feedback(
                                result.normalized_items, result.claims,
                            ),
                        ),
                    ))
                    continue
                provider_place = result.normalized_items[0]
                coordinate_claim = result.claims[0] if result.claims[0]["field_path"] == "/coordinates" else None
                if coordinate_claim is None or not isinstance(coordinate_claim.get("value"), dict):
                    errors.append("contract_mismatch")
                    warnings.append(
                        "contract_mismatch:%s:geocode_coordinates:%s" % (
                            entity["ref_id"],
                            poi_identity_feedback(
                                identity_candidates, identity_candidate_claims,
                            ),
                        )
                    )
                    fatal_status = "contract_mismatch"
                    break
                if not _poi_admin_matches(entity, provider_place, result.claims):
                    claims.extend(_claims_with_status(identity_claims + list(result.claims), "conflict"))
                    errors.append("identity_conflict")
                    warnings.extend((
                        "identity_conflict",
                        "identity_conflict:%s:geocode_admin_mismatch:%s" % (
                            entity["ref_id"],
                            poi_identity_feedback(
                                identity_candidates,
                                identity_candidate_claims,
                                actual_administrative_area=provider_place.get("city"),
                            ),
                        ),
                    ))
                    continue
                claims.extend(identity_claims)
                claims.append(copy.deepcopy(coordinate_claim))
                location_claim_ids = tuple(
                    claim["claim_id"] for claim in identity_claims
                ) + (coordinate_claim["claim_id"],)
                locations[entity["ref_id"]] = MobilityLocation(
                    entity["ref_id"], provider_name or provider_place["name"], provider_place["city"],
                    coordinate_claim["value"], location_claim_ids,
                )
            else:
                claims.extend(identity_claims)
                error = result.error_class or "no_results"
                errors.append(error)
                warnings.append(
                    "%s:%s:geocode_lookup:%s" % (
                        error,
                        entity["ref_id"],
                        poi_identity_feedback(
                            identity_candidates, identity_candidate_claims,
                        ),
                    )
                )
                if error in FATAL_ERRORS:
                    fatal_status = result.health["status"]
                    break

        claims, semantic_warnings = _semantic_location_checks(locations, claims, candidates)
        warnings.extend(semantic_warnings)

        cells: List[RouteCell] = []
        if fatal_status is None and len(locations) >= 2:
            pairs = _bounded_pairs(tuple(locations.values()), candidates, normalized_modes, _transport_calls(self.transport))
            for left_ref, right_ref in pairs:
                left = locations[left_ref]
                right = locations[right_ref]
                if not _city_matches(left.city, right.city):
                    continue
                for mode in normalized_modes:
                    left_point = left.coordinates["gcj02"]
                    right_point = right.coordinates["gcj02"]
                    request = ProviderRequest(
                        request_id=stable_id("amap-route", left_ref, right_ref, mode),
                        capability="route",
                        parameters={
                            "from_ref": left_ref,
                            "to_ref": right_ref,
                            "origin": _point_text(left_point),
                            "destination": _point_text(right_point),
                            "city": left.city,
                            "destination_city": right.city,
                            "travel_mode": mode,
                        },
                        deadline_ms=int(self.deadline_seconds * 1000),
                        as_of=now[:10],
                        cache_policy="bypass",
                        trace={"stage": "mobility-route"},
                    )
                    calls_before = _transport_calls(self.transport)
                    result = adapter.query(request, context)
                    if _transport_calls(self.transport) > calls_before:
                        calls.append("amap.route:%s:%s:%s" % (mode, left_ref, right_ref))
                    if result.normalized_items:
                        leg = result.normalized_items[0]
                        distance = next(
                            (item["value"] for item in result.claims if item["field_path"] == "/distance_meters"),
                            None,
                        )
                        cell = RouteCell(
                            from_ref=left_ref,
                            to_ref=right_ref,
                            travel_mode=mode,
                            duration_minutes=leg["duration_minutes"],
                            distance_meters=distance,
                            provider="amap",
                            provider_version=adapter.provider_version,
                            mode="live",
                            queried_at=result.queried_at,
                            claim_ids=tuple(leg["claim_ids"]),
                            reachable=True,
                            degradation_rung="R0",
                        )
                        cell.validate()
                        cells.append(cell)
                        claims.extend(result.claims)
                        continue
                    error = result.error_class or "no_results"
                    errors.append(error)
                    if error == "no_results":
                        leg_id = stable_id("leg-amap", left_ref, right_ref, mode)
                        unreachable_claim = make_claim(
                            subject_ref=leg_id,
                            field_path="/reachable",
                            value=False,
                            source_url=_route_source(mode),
                            provider="amap",
                            status="verified",
                            confidence=0.9,
                            mode="live",
                            clock=clock,
                        )
                        cell = RouteCell(
                            from_ref=left_ref,
                            to_ref=right_ref,
                            travel_mode=mode,
                            duration_minutes=None,
                            distance_meters=None,
                            provider="amap",
                            provider_version=adapter.provider_version,
                            mode="live",
                            queried_at=result.queried_at,
                            claim_ids=(unreachable_claim["claim_id"],),
                            reachable=False,
                            degradation_rung="R0",
                        )
                        cell.validate()
                        cells.append(cell)
                        claims.append(unreachable_claim)
                    if error in FATAL_ERRORS:
                        fatal_status = result.health["status"]
                        break
                if fatal_status is not None:
                    break

        call_count = _transport_calls(self.transport)
        call_limit = _transport_max_calls(self.transport)
        live_cells = sum(1 for item in cells if item.mode == "live")
        if fatal_status is not None:
            status = fatal_status
        elif "identity_conflict" in warnings or "incomplete_address" in warnings:
            status = "degraded"
        elif live_cells:
            status = "ready"
        else:
            status = "degraded"
        error_summary = ",".join(sorted(set(errors))) if errors else "none"
        health = _health(
            "live" if live_cells else "static",
            status,
            now,
            "calls=%d/%d qps<=2; live_cells=%d; locations=%d; errors=%s; warnings=%s" % (
                call_count, call_limit, live_cells, len(locations), error_summary,
                ",".join(sorted(set(item.split(":", 1)[0] for item in warnings))) if warnings else "none",
            ),
        )
        return MobilityResult(
            tuple(locations[key] for key in sorted(locations)),
            tuple(sorted(cells, key=lambda item: (item.from_ref, item.to_ref, item.travel_mode))),
            tuple(claims),
            health,
            tuple(calls),
            tuple(dict.fromkeys(warnings)),
        )


def check_poi_name_identity(
    name: str,
    city: str,
    clock: Clock,
    credentials: CredentialResolution,
    transport: Optional[ProviderTransport],
    *,
    deadline_seconds: float = 8.0,
) -> POINameCheck:
    """Check one prospective POI name without writing coordinates or candidates."""

    if not credentials.get("AMAP_WEBSERVICE_KEY"):
        return POINameCheck("unavailable", ("credential_missing",))
    if transport is None:
        return POINameCheck("unavailable", ("transport_unavailable",))
    if deadline_seconds <= 0:
        return POINameCheck("unavailable", ("invalid_deadline",))
    entity = {
        "ref_id": stable_id("poi-name-check", city, name),
        "name": name,
        "city": city,
    }
    request = ProviderRequest(
        request_id=stable_id("amap-poi-name-check", name, city),
        capability="poi",
        parameters={
            "subject_ref": entity["ref_id"],
            "keywords": name,
            "city": city,
            "page_size": 3,
            "page_num": 1,
        },
        deadline_ms=int(min(deadline_seconds, 8.0) * 1000),
        as_of=isoformat_seconds(clock)[:10],
        cache_policy="bypass",
        trace={"stage": "candidate-poi-name-check"},
    )
    result = AMapAdapter().query(
        request,
        ProviderContext(clock=clock, credentials=credentials, transport=transport),
    )
    if not result.normalized_items:
        reason = result.error_class or "no_results"
        status = "ambiguous" if reason == "no_results" else "unavailable"
        feedback = poi_identity_feedback((), ()) if status == "ambiguous" else None
        return POINameCheck(status, (reason,), feedback)
    feedback = poi_identity_feedback(result.normalized_items, result.claims)
    conflicts = _poi_identity_conflicts(
        entity, result.normalized_items, result.claims,
    )
    if conflicts:
        return POINameCheck("ambiguous", conflicts, feedback)
    selected_ids = set(result.normalized_items[0].get("claim_ids", ()))
    identity = next((
        claim.get("value") for claim in result.claims
        if claim.get("claim_id") in selected_ids
        and claim.get("field_path") == "/provider_identity"
    ), None)
    if not _complete_poi_address(identity):
        return POINameCheck(
            "ambiguous", ("poi_address_missing_admin_detail",), feedback,
        )
    return POINameCheck("unique", (), feedback)


def normalize_modes(modes: Sequence[str]) -> Tuple[str, ...]:
    normalized = []
    for raw in modes:
        key = raw.strip().lower()
        if key not in MODE_ALIASES:
            raise ValueError("unsupported mobility mode: %s" % raw)
        value = MODE_ALIASES[key]
        if value not in normalized:
            normalized.append(value)
    if not normalized:
        raise ValueError("at least one mobility mode is required")
    return tuple(normalized)


def _poi_identity_conflicts(
    entity: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
    claims: Sequence[Mapping[str, Any]],
) -> Tuple[str, ...]:
    first = candidates[0]
    reasons = []
    if not _poi_admin_matches(entity, first, claims):
        reasons.append("poi_admin_mismatch")
    if _poi_name_is_ambiguous(entity["name"], candidates):
        reasons.append("ambiguous_name_margin")
    return tuple(reasons)


def _poi_admin_matches(
    entity: Mapping[str, Any],
    candidate: Mapping[str, Any],
    claims: Sequence[Mapping[str, Any]],
) -> bool:
    administrative_areas = [candidate.get("city")]
    district = candidate.get("district")
    if isinstance(district, str) and district.strip():
        administrative_areas.append(district)
    else:
        selected_claim_ids = set(candidate.get("claim_ids", ()))
        for claim in claims:
            if (
                claim.get("claim_id") in selected_claim_ids
                and claim.get("subject_ref") == entity.get("ref_id")
                and claim.get("field_path") == "/provider_identity"
            ):
                identity = claim.get("value")
                if isinstance(identity, dict):
                    administrative_areas.append(identity.get("district"))
                break
    return any(
        _city_matches(entity.get("city"), actual)
        for actual in administrative_areas
    )


def _poi_name_is_ambiguous(
    expected: Any,
    candidates: Sequence[Mapping[str, Any]],
) -> bool:
    candidate_names = []
    for candidate in candidates:
        name = candidate.get("name")
        if name not in candidate_names:
            candidate_names.append(name)
    if not candidate_names or candidate_names[0] == expected:
        return False
    if len(candidate_names) == 1:
        return False
    first_score = _name_similarity(expected, candidate_names[0])
    nearest_alternative = max(
        _name_similarity(expected, name) for name in candidate_names[1:]
    )
    return first_score - nearest_alternative < POI_NAME_SIMILARITY_MARGIN


def poi_identity_feedback(
    candidates: Sequence[Mapping[str, Any]],
    claims: Sequence[Mapping[str, Any]],
    *,
    limit: int = 3,
    actual_administrative_area: Optional[Any] = None,
) -> str:
    """Render a bounded, sanitized projection of provider identity candidates."""

    if limit < 1:
        raise ValueError("POI identity feedback limit must be positive")
    claims_by_id = {
        claim.get("claim_id"): claim
        for claim in claims
        if isinstance(claim, Mapping) and isinstance(claim.get("claim_id"), str)
    }
    projected = []
    for candidate in candidates[:limit]:
        claim_ids = candidate.get("claim_ids", ())
        identity = next((
            claims_by_id[claim_id].get("value")
            for claim_id in claim_ids
            if claim_id in claims_by_id
            and claims_by_id[claim_id].get("field_path") == "/provider_identity"
            and isinstance(claims_by_id[claim_id].get("value"), dict)
        ), {}) if isinstance(claim_ids, (list, tuple)) else {}
        name = _feedback_text(candidate.get("name"), 160, "unknown")
        city = _feedback_text(candidate.get("city"), 80, "unknown")
        district = _feedback_text(identity.get("district"), 80, "")
        admin_parts = [city]
        if district and district not in admin_parts:
            admin_parts.append(district)
        projected.append({
            "administrative_area": "/".join(admin_parts),
            "name": name,
        })
    feedback: Dict[str, Any] = {
        "candidates": projected,
        "suggested_names": [item["name"] for item in projected],
    }
    if actual_administrative_area is not None:
        feedback["actual_administrative_area"] = _feedback_text(
            actual_administrative_area, 80, "unknown",
        )
    return canonical_json(feedback)


def _feedback_text(value: Any, max_length: int, fallback: str) -> str:
    if not isinstance(value, str):
        return fallback
    clean = sanitize_text(value, max_length)
    return clean or fallback


def _name_similarity(expected: Any, actual: Any) -> float:
    left = _normalized_name(expected)
    right = _normalized_name(actual)
    if not left or not right:
        return 0.0
    return difflib.SequenceMatcher(None, left, right, autojunk=False).ratio()


def _normalized_name(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    folded = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in folded if character.isalnum())


def _city_matches(expected: Any, actual: Any) -> bool:
    left = _city_key(expected)
    right = _city_key(actual)
    return bool(left and right and left == right)


def _city_key(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    result = "".join(
        character for character in unicodedata.normalize("NFKC", value).casefold()
        if character.isalnum()
    )
    for suffix in ("特别行政区", "自治州", "自治县", "地区", "市", "县", "区", "盟"):
        if result.endswith(suffix) and len(result) > len(suffix):
            result = result[:-len(suffix)]
            break
    return result


def _complete_poi_address(identity: Any) -> bool:
    return bool(
        isinstance(identity, dict)
        and isinstance(identity.get("formatted_address"), str)
        and identity["formatted_address"].strip()
        and isinstance(identity.get("district"), str)
        and identity["district"].strip()
        and isinstance(identity.get("adcode"), str)
        and identity["adcode"].strip()
    )


def _claims_with_status(
    claims: Sequence[Mapping[str, Any]],
    status: str,
) -> List[Mapping[str, Any]]:
    output = copy.deepcopy(list(claims))
    for claim in output:
        claim["status"] = status
        if status == "unknown":
            claim["confidence"] = 0.0
    return output


def _business_claims_with_conflict(
    claims: Sequence[Mapping[str, Any]],
) -> List[Mapping[str, Any]]:
    output = copy.deepcopy(list(claims))
    for claim in output:
        if claim["field_path"] in ("/provider_identity", "/business"):
            claim["status"] = "conflict"
    return output


def _business_conflict(
    entity: Mapping[str, Any],
    candidates: Mapping[str, Any],
    claims: Sequence[Mapping[str, Any]],
) -> bool:
    business = next(
        (claim["value"] for claim in claims if claim["field_path"] == "/business"),
        None,
    )
    if not _mentions_closure(business):
        return False
    entity_claim_ids = set(entity.get("claim_ids", ()))
    official_claims = [
        claim for claim in candidates["claims"]
        if claim["claim_id"] in entity_claim_ids
        and claim["provider"] in ("official-web", "official")
        and claim["status"] not in ("conflict", "unavailable", "unknown")
    ]
    return bool(official_claims) and not any(_mentions_closure(claim["value"]) for claim in official_claims)


def _mentions_closure(value: Any) -> bool:
    text = str(value).casefold()
    return any(marker in text for marker in (
        "暂停营业", "暂停开放", "停止营业", "停止开放", "暂时关闭", "永久关闭",
        "闭馆", "歇业", "closed", "suspended", "not open",
    ))


def _semantic_location_checks(
    locations: Mapping[str, MobilityLocation],
    claims: Sequence[Mapping[str, Any]],
    candidates: Mapping[str, Any],
) -> Tuple[List[Mapping[str, Any]], Tuple[str, ...]]:
    partial_claim_ids: Set[str] = set()
    conflict_claim_ids: Set[str] = set()
    details: Set[str] = set()

    coordinate_buckets: Dict[Tuple[float, float], List[MobilityLocation]] = {}
    for location in locations.values():
        point = _location_point(location)
        if point is not None:
            coordinate_buckets.setdefault(point, []).append(location)
    for duplicate_locations in coordinate_buckets.values():
        if len(duplicate_locations) < 2:
            continue
        refs = tuple(sorted(item.ref_id for item in duplicate_locations))
        for location in duplicate_locations:
            conflict_claim_ids.update(location.claim_ids)
        details.add("semantic_outlier:duplicate_coordinates:%s" % ",".join(refs))

    by_city: Dict[str, List[MobilityLocation]] = {}
    for location in locations.values():
        by_city.setdefault(_city_key(location.city), []).append(location)
    for city_locations in by_city.values():
        if len(city_locations) < 3:
            continue
        for location in city_locations:
            point = _location_point(location)
            if point is None:
                continue
            distances = [
                haversine_meters(point[0], point[1], other_point[0], other_point[1])
                for other in city_locations if other.ref_id != location.ref_id
                for other_point in (_location_point(other),) if other_point is not None
            ]
            if distances and min(distances) > SEMANTIC_OUTLIER_DISTANCE_METERS:
                partial_claim_ids.update(location.claim_ids)
                details.add("semantic_outlier:same_city:%s" % location.ref_id)

    for left_entity, right_entity in zip(candidates["pois"], candidates["pois"][1:]):
        left = locations.get(left_entity["poi_id"])
        right = locations.get(right_entity["poi_id"])
        if left is None or right is None or not _city_matches(left.city, right.city):
            continue
        if not (_opening_dates(left_entity) & _opening_dates(right_entity)):
            continue
        left_point = _location_point(left)
        right_point = _location_point(right)
        if left_point is None or right_point is None:
            continue
        distance = haversine_meters(left_point[0], left_point[1], right_point[0], right_point[1])
        if distance > SEMANTIC_OUTLIER_DISTANCE_METERS:
            partial_claim_ids.update(left.claim_ids)
            partial_claim_ids.update(right.claim_ids)
            details.add(
                "semantic_outlier:same_day_adjacent:%s:%s:%dm"
                % (left.ref_id, right.ref_id, round(distance))
            )

    output = copy.deepcopy(list(claims))
    for claim in output:
        if claim["claim_id"] in conflict_claim_ids:
            claim["status"] = "conflict"
        elif claim["claim_id"] in partial_claim_ids and claim["status"] == "verified":
            claim["status"] = "partial"
    if not details:
        return output, ()
    return output, tuple(["semantic_outlier"] + sorted(details))


def _location_point(location: MobilityLocation) -> Optional[Tuple[float, float]]:
    point = location.coordinates.get("gcj02")
    if not isinstance(point, dict):
        return None
    return float(point["lng"]), float(point["lat"])


def _opening_dates(entity: Mapping[str, Any]) -> Set[str]:
    return {
        window["start_at"][:10]
        for window in entity.get("opening_windows", ())
        if isinstance(window.get("start_at"), str) and len(window["start_at"]) >= 10
    }


def apply_locations(
    pois: Sequence[Mapping[str, Any]],
    lodgings: Sequence[Mapping[str, Any]],
    result: MobilityResult,
) -> Tuple[List[Mapping[str, Any]], List[Mapping[str, Any]]]:
    by_ref = {item.ref_id: item for item in result.locations}

    def update(items: Sequence[Mapping[str, Any]], id_key: str) -> List[Mapping[str, Any]]:
        output = copy.deepcopy(list(items))
        for item in output:
            location = by_ref.get(item[id_key])
            if location is None:
                continue
            item["coordinates"] = copy.deepcopy(dict(location.coordinates))
            item["claim_ids"] = list(dict.fromkeys(list(item["claim_ids"]) + list(location.claim_ids)))
        return output

    return update(pois, "poi_id"), update(lodgings, "lodging_id")


def _candidate_entities(candidates: Mapping[str, Any]) -> Tuple[Mapping[str, Any], ...]:
    entities = []
    for item in candidates["lodgings"]:
        entities.append({
            "ref_id": item["lodging_id"], "name": item["name"], "city": item["city"],
            "coordinates": item["coordinates"], "claim_ids": item["claim_ids"], "lodging": True,
        })
    for item in candidates["pois"][:12]:
        entities.append({
            "ref_id": item["poi_id"], "name": item["name"], "city": item["city"],
            "coordinates": item["coordinates"], "claim_ids": item["claim_ids"], "lodging": False,
        })
    return tuple(sorted(entities, key=lambda item: item["ref_id"]))


def _usable_coordinates(value: Any) -> Optional[Mapping[str, Any]]:
    if not isinstance(value, dict) or not isinstance(value.get("gcj02"), dict) or not isinstance(value.get("wgs84"), dict):
        return None
    return copy.deepcopy(value)


def _bounded_pairs(
    locations: Sequence[MobilityLocation],
    candidates: Mapping[str, Any],
    modes: Sequence[str],
    calls_used: int,
) -> Tuple[Tuple[str, str], ...]:
    by_ref = {item.ref_id: item for item in locations}
    neighbors: Dict[str, Sequence[str]] = {}
    for left in locations:
        left_point = left.coordinates["gcj02"]
        ranked = []
        for right in locations:
            if left.ref_id == right.ref_id or not _city_matches(left.city, right.city):
                continue
            right_point = right.coordinates["gcj02"]
            distance = haversine_meters(
                float(left_point["lng"]), float(left_point["lat"]),
                float(right_point["lng"]), float(right_point["lat"]),
            )
            ranked.append((distance, right.ref_id))
        neighbors[left.ref_id] = tuple(ref for _, ref in sorted(ranked)[:5])
    lodging_refs = tuple(
        item["lodging_id"] for item in candidates["lodgings"] if item["lodging_id"] in by_ref
    )
    pairs = bounded_query_plan(tuple(by_ref), lodging_refs=lodging_refs, cluster_neighbors=neighbors)
    ordered = sorted(pairs, key=lambda pair: (not (pair[0] in lodging_refs or pair[1] in lodging_refs), pair))
    remaining = max(0, MAX_CALLS_PER_RUN - calls_used)
    return tuple(ordered[: remaining // len(modes)])


def _point_text(point: Mapping[str, Any]) -> str:
    return "%.7f,%.7f" % (float(point["lng"]), float(point["lat"]))


def _route_source(mode: str) -> str:
    paths = {
        "walk": "/v3/direction/walking",
        "transit": "/v3/direction/transit/integrated",
        "drive": "/v3/direction/driving",
        "ride": "/v4/direction/bicycling",
    }
    return "https://restapi.amap.com" + paths[mode]


def _transport_calls(transport: ProviderTransport) -> int:
    value = getattr(transport, "calls", 0)
    return int(value) if isinstance(value, int) else 0


def _transport_max_calls(transport: ProviderTransport) -> int:
    value = getattr(transport, "max_calls", MAX_CALLS_PER_RUN)
    return int(value) if isinstance(value, int) and value >= 0 else MAX_CALLS_PER_RUN


def _health(mode: str, status: str, checked_at: str, reason: str) -> Mapping[str, Any]:
    return {
        "provider": "amap",
        "version": AMapAdapter.provider_version,
        "mode": mode,
        "status": status,
        "checked_at": checked_at,
        "capabilities": ["geocode", "poi", "route"],
        "reason": reason,
    }
