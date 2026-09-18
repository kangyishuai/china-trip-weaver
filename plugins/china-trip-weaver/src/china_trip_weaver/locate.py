"""Query AMap coordinates for a Trip/Journey's unlocated POIs and lodgings.

This never writes a Trip; it only produces a result envelope (mirroring the
`weather`/`dining` commands' own envelopes) that a separate fold step can
later apply. Locating never invents a coordinate: an entity that cannot be
resolved is reported with a `reason`, never a guessed point.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set

from .candidates import CANDIDATES_VERSION
from .clock import Clock, isoformat_seconds
from .mobility import MobilityBackend, MobilityResult, _usable_coordinates
from .providers.amap import AMapAdapter


_MEAL_PLACEHOLDER_PREFIX = "poi-routine-meal-"
_LODGING_FIELDS = (
    "lodging_id", "name", "city", "area", "check_in", "check_out",
    "coordinates", "price", "deep_links", "claim_ids", "locked",
)


def unlocated_entities(trip: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """POIs and lodgings in `trip` missing a usable `gcj02`/`wgs84` coordinate.

    A meal-placeholder POI (`poi_id` starting with `poi-routine-meal-`) is
    never a locate candidate. A lodging is projected onto the plain
    `#/$defs/lodging` field set because a current Trip's `lodgings[]` items
    may carry the richer `#/$defs/stay` shape (`candidate_ref`,
    `selection_status`, `selected_nights`), which the candidates schema's
    `lodging` reference has no room for.
    """

    results: List[Dict[str, Any]] = []
    for poi in trip["pois"]:
        if str(poi.get("poi_id", "")).startswith(_MEAL_PLACEHOLDER_PREFIX):
            continue
        if _usable_coordinates(poi.get("coordinates")) is not None:
            continue
        results.append({
            "kind": "poi",
            "ref_id": poi["poi_id"],
            "name": poi["name"],
            "city": poi["city"],
            "entity": copy.deepcopy(dict(poi)),
        })
    for lodging in trip["lodgings"]:
        if _usable_coordinates(lodging.get("coordinates")) is not None:
            continue
        results.append({
            "kind": "lodging",
            "ref_id": lodging["lodging_id"],
            "name": lodging["name"],
            "city": lodging["city"],
            "entity": _project_lodging(lodging),
        })
    return results


def locate_trips(
    trips: Sequence[Mapping[str, Any]],
    backend: MobilityBackend,
    clock: Clock,
) -> Dict[str, Any]:
    """Locate every unlocated POI/lodging across `trips` into one envelope.

    Trips are processed in order and each builds its own candidates document
    (so a meal-placeholder POI or an already-located entity never reaches
    AMap). An entity `ref_id` already resolved earlier in this same call is
    reused and never queried again.
    """

    queried_at = isoformat_seconds(clock)
    resolved: Dict[str, Dict[str, Any]] = {}
    entities: List[Dict[str, Any]] = []
    claims_by_id: Dict[str, Mapping[str, Any]] = {}
    warnings: List[str] = []
    health: Optional[Dict[str, Any]] = None

    for trip in trips:
        trip_id = trip["trip_id"]
        pending_items = unlocated_entities(trip)
        new_items = [item for item in pending_items if item["ref_id"] not in resolved]
        if new_items:
            result = backend.locate(_candidates_document(trip, new_items), clock)
            health = {
                "provider": result.health["provider"],
                "status": result.health["status"],
                "checked_at": result.health["checked_at"],
            }
            rows = _entity_rows(new_items, result)
            for row in rows:
                resolved[row["ref_id"]] = row
            located_claim_ids = {
                claim_id
                for row in rows if row["status"] == "located"
                for claim_id in row["claim_ids"]
            }
            for claim in result.claims:
                if claim["claim_id"] in located_claim_ids:
                    claims_by_id[claim["claim_id"]] = copy.deepcopy(dict(claim))
            for warning in result.warnings:
                if warning not in warnings:
                    warnings.append(warning)
        for item in pending_items:
            entities.append(dict(resolved[item["ref_id"]], trip_id=trip_id))

    if health is None:
        health = {"provider": "amap", "status": "degraded", "checked_at": queried_at}
    if not any(entity["status"] == "provider_error" for entity in entities):
        health = dict(health, status="ready")

    return {
        "provider": "amap",
        "provider_version": AMapAdapter.provider_version,
        "queried_at": queried_at,
        "health": health,
        "warnings": warnings,
        "claims": list(claims_by_id.values()),
        "entities": entities,
    }


def _entity_rows(
    pending: Sequence[Mapping[str, Any]],
    result: MobilityResult,
) -> List[Dict[str, Any]]:
    locations_by_ref = {location.ref_id: location for location in result.locations}
    call_refs = {call.split(":", 1)[1] for call in result.business_calls if ":" in call}
    health_status = result.health["status"]
    healthy = health_status in ("ready", "degraded")

    rows: List[Dict[str, Any]] = []
    for item in pending:
        ref_id = item["ref_id"]
        row: Dict[str, Any] = {
            "ref_id": ref_id,
            "kind": item["kind"],
            "name": item["name"],
            "city": item["city"],
        }
        location = locations_by_ref.get(ref_id)
        if location is not None:
            row.update(
                status="located",
                coordinates=copy.deepcopy(dict(location.coordinates)),
                claim_ids=list(location.claim_ids),
                reason=None,
            )
        elif not healthy:
            row.update(
                status="provider_error",
                coordinates=None,
                claim_ids=[],
                reason="credential_missing" if health_status == "missing" else health_status,
            )
        elif ref_id in call_refs:
            row.update(
                status="unresolved",
                coordinates=None,
                claim_ids=[],
                reason=_first_matching_warning(result.warnings, ref_id) or "locate_no_result",
            )
        else:
            row.update(
                status="provider_error",
                coordinates=None,
                claim_ids=[],
                reason="not_attempted",
            )
        rows.append(row)
    return rows


def _first_matching_warning(warnings: Sequence[str], ref_id: str) -> Optional[str]:
    """The warning a planner run would record as this entity's coordinate unknown.

    Mirrors `planning._add_runtime_coordinate_unknowns`: only three-part
    `kind:ref_id:detail` warnings count, the non-blocking
    `identity_conflict:<ref>:nearby_name_candidates:…` note is skipped, and one
    carrying `"suggested_names":` wins over the first match.
    """

    matches = []
    for warning in warnings:
        parts = warning.split(":", 2)
        if len(parts) != 3 or not all(parts) or parts[1] != ref_id:
            continue
        if parts[0] == "identity_conflict" and parts[2].startswith("nearby_name_candidates:"):
            continue
        matches.append(warning)
    return next(
        (warning for warning in matches if '"suggested_names":' in warning),
        matches[0] if matches else None,
    )


def _candidates_document(
    trip: Mapping[str, Any],
    pending: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    pois = [item["entity"] for item in pending if item["kind"] == "poi"]
    lodgings = [item["entity"] for item in pending if item["kind"] == "lodging"]
    if not pois:
        context = _context_poi(trip)
        if context is not None:
            pois = [context]
    referenced: Set[str] = set()
    for entity in pois + lodgings:
        referenced |= _referenced_claim_ids(entity)
    claims_by_id = {claim["claim_id"]: claim for claim in trip["claims"]}
    claims = [copy.deepcopy(dict(claims_by_id[cid])) for cid in sorted(referenced)]
    return {
        "candidates_version": CANDIDATES_VERSION,
        "pois": pois,
        "lodgings": lodgings,
        "claims": claims,
        "unknowns": [],
    }


def _context_poi(trip: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """An already-located POI that keeps a lodging-only candidates document valid.

    The candidates schema requires at least one POI, but a hand-finished Trip
    usually has every POI located and only its lodgings missing. An entity with
    usable coordinates is never sent to AMap (`MobilityBackend._resolve_locations`
    keeps it as-is), and only pending entities become envelope rows, so this POI
    costs no call and never shows up in the result. Its own claims must all be
    about it, or the candidates validator would reject the document.
    """

    claims_by_id = {claim["claim_id"]: claim for claim in trip["claims"]}
    for poi in trip["pois"]:
        if str(poi.get("poi_id", "")).startswith(_MEAL_PLACEHOLDER_PREFIX):
            continue
        if _usable_coordinates(poi.get("coordinates")) is None or not poi.get("claim_ids"):
            continue
        if all(
            claims_by_id.get(claim_id, {}).get("subject_ref") == poi["poi_id"]
            for claim_id in _referenced_claim_ids(poi)
        ):
            return copy.deepcopy(dict(poi))
    return None


def _referenced_claim_ids(entity: Mapping[str, Any]) -> Set[str]:
    referenced: Set[str] = set(entity.get("claim_ids") or ())
    price = entity.get("price")
    if price and price.get("claim_id") is not None:
        referenced.add(price["claim_id"])
    for window in entity.get("opening_windows") or ():
        if window.get("claim_id") is not None:
            referenced.add(window["claim_id"])
    return referenced


def _project_lodging(lodging: Mapping[str, Any]) -> Dict[str, Any]:
    return {field: copy.deepcopy(lodging[field]) for field in _LODGING_FIELDS}
