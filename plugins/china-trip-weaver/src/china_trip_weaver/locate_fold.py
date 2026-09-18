"""Fold an AMap locate query envelope back into an existing Trip or Journey."""

from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from .clock import Clock, isoformat_seconds
from .contracts import PatchResult
from .journey import replace_trips_in_journey, validate_journey
from .replan import _all_refs, _locked_refs
from .validate_trip import validate_trip


_GROUPS: Tuple[Tuple[str, str, str], ...] = (
    ("poi", "pois", "poi_id"),
    ("lodging", "lodgings", "lodging_id"),
)


def fold_locations_into_trip(
    trip: Mapping[str, Any],
    result: Mapping[str, Any],
    clock: Clock,
    reason: Optional[str] = None,
) -> Optional[PatchResult]:
    """Fold a `ctw locate --output-json` envelope into one Trip as a new patch revision.

    Matches each `result["entities"]` row against `pois`/`lodgings` by (`trip_id`,
    `kind`, `ref_id`); a row for another Trip, or with no matching entity, is
    ignored. Only an entity whose `coordinates` is null or missing `gcj02`/`wgs84`
    is eligible — one that already carries both is never touched, even when the
    envelope disagrees with it. A `located` row on an eligible entity writes its
    `coordinates` wholesale and appends the row's `claim_ids` (deduplicated, as
    `mobility.apply_locations` does), copying in from `result["claims"]` whichever
    of those ids the Trip does not already carry (a ref'd id absent from both
    raises `locate_fold_claim_missing`). An `unresolved` row leaves `coordinates`
    untouched and records — or, if the reason changed, replaces — a typed unknown
    carrying the row's own `reason`. `provider_error` rows and entities with no
    matching row are left alone. Folding the same result twice is a no-op and
    returns None.
    """

    base_trip = trip
    current_revision = int(base_trip["revision"]["number"])
    trip_id = base_trip["trip_id"]
    queried_at = result.get("queried_at")

    trip = copy.deepcopy(dict(base_trip))
    actions = _plan_entity_actions(trip, trip_id, result.get("entities", ()), result.get("claims", ()))
    changed = _changed_actions(trip, actions)
    if not changed:
        return None

    now = isoformat_seconds(clock)
    operations: List[Dict[str, Any]] = []
    _remove_stale_unknowns(trip, changed, operations)
    changed_refs = _apply_entity_actions(trip, changed, operations)
    _fold_amap_health(trip, operations, len(changed), queried_at, now, result.get("provider_version"))

    target_revision = current_revision + 1
    all_refs = _all_refs(base_trip)
    day_ids = _referencing_day_ids(trip, changed_refs)
    preserved_refs = sorted(all_refs - changed_refs)
    eligible = max(1, len(all_refs))
    patch = {
        "patch_id": "patch-%d-%d" % (current_revision, target_revision),
        "base_revision": current_revision,
        "target_revision": target_revision,
        "created_at": now,
        "trigger": "provider_change",
        "reason": reason or ("locate fold (%s)" % queried_at),
        "scope": {
            "day_ids": sorted(day_ids),
            "affected_refs": sorted(changed_refs),
            "locked_refs": sorted(_locked_refs(base_trip)),
        },
        "operations": operations,
        "reverify_claim_ids": [],
        "stability": {
            "preserved_refs": preserved_refs,
            "changed_refs": sorted(changed_refs),
            "score": round(len(preserved_refs) / eligible, 6),
        },
    }
    trip["revision"] = {
        "number": target_revision,
        "parent_revision": current_revision,
        "created_at": now,
        "reason": patch["reason"],
        "created_by": "system",
    }
    trip["patches"].append(copy.deepcopy(patch))
    trip["generated_at"] = now

    report = validate_trip(trip)
    if not report.ok:
        raise ValueError(
            "locate_fold_invalid_trip: " + "; ".join(item.render() for item in report.errors)
        )
    return PatchResult(trip=trip, patch=patch, reverify_claim_ids=())


def fold_locations_into_journey(
    journey: Mapping[str, Any],
    result: Mapping[str, Any],
    base_revision: int,
    clock: Clock,
    reason: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Fold one locate envelope into every matching Trip of a Journey, one reassembly.

    Delegates each Trip to `fold_locations_into_trip`; a Trip that does not change
    is left alone. Every Trip that does change is folded into one
    `replace_trips_in_journey` call, so the Journey's `revision.number` advances
    by exactly one no matter how many Trips changed, with `created_by` forced to
    `"system"`. Returns None when no Trip changed.
    """

    current_revision = int(journey["revision"]["number"])
    if base_revision != current_revision:
        raise ValueError(
            "revision_conflict: Journey is at revision %d, not %d" % (current_revision, base_revision)
        )

    changed_trips: List[Mapping[str, Any]] = []
    for trip in journey["trips"]:
        patch_result = fold_locations_into_trip(trip, result, clock, reason=reason)
        if patch_result is not None:
            changed_trips.append(patch_result.trip)

    if not changed_trips:
        return None

    working = replace_trips_in_journey(
        journey, changed_trips, current_revision, clock, reason=reason, created_by="system",
    )
    report = validate_journey(working)
    if not report.ok:
        raise ValueError(
            "locate_fold_invalid_journey: " + "; ".join(item.render() for item in report.errors)
        )
    return working


def _needs_location(coordinates: Any) -> bool:
    if not isinstance(coordinates, Mapping):
        return True
    return coordinates.get("gcj02") is None or coordinates.get("wgs84") is None


def _entity_path(group: str, index: int, suffix: str) -> str:
    return "/%s/%d/%s" % (group, index, suffix)


def _plan_entity_actions(
    trip: Mapping[str, Any],
    trip_id: str,
    rows: Sequence[Mapping[str, Any]],
    claims_pool: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    claims_by_id = {claim.get("claim_id"): claim for claim in claims_pool}
    existing_claim_ids = {claim.get("claim_id") for claim in trip["claims"]}
    actions: List[Dict[str, Any]] = []
    for kind, group, id_key in _GROUPS:
        for index, entity in enumerate(trip[group]):
            if not _needs_location(entity.get("coordinates")):
                continue
            row = _matching_row(rows, trip_id, kind, entity[id_key])
            if row is None:
                continue
            status = row.get("status")
            if status == "located":
                row_claim_ids = list(row.get("claim_ids", ()))
                new_claim_ids = list(dict.fromkeys(list(entity["claim_ids"]) + row_claim_ids))
                new_claims = []
                for claim_id in row_claim_ids:
                    if claim_id in existing_claim_ids:
                        continue
                    claim = claims_by_id.get(claim_id)
                    if claim is None:
                        raise ValueError(
                            "locate_fold_claim_missing: no claim %s in result[\"claims\"] "
                            "for %s %s" % (claim_id, kind, entity[id_key])
                        )
                    new_claims.append(copy.deepcopy(dict(claim)))
                actions.append({
                    "group": group, "index": index, "ref_id": entity[id_key], "kind": "located",
                    "new_coordinates": copy.deepcopy(row.get("coordinates")),
                    "new_claim_ids": new_claim_ids, "new_claims": new_claims,
                })
            elif status == "unresolved":
                actions.append({
                    "group": group, "index": index, "ref_id": entity[id_key], "kind": "unresolved",
                    "reason": row.get("reason"),
                })
            # provider_error (or any other status) leaves the entity untouched.
    return actions


def _changed_actions(trip: Mapping[str, Any], actions: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    changed: List[Dict[str, Any]] = []
    for action in actions:
        entity = trip[action["group"]][action["index"]]
        if action["kind"] == "located":
            same_coordinates = entity.get("coordinates") == action["new_coordinates"]
            same_claims = list(entity["claim_ids"]) == action["new_claim_ids"]
            if same_coordinates and same_claims:
                continue
        else:
            existing = _unknown_index(trip["unknowns"], action["group"], action["index"])
            if existing is not None and trip["unknowns"][existing].get("reason") == action["reason"]:
                continue
        changed.append(dict(action))
    return changed


def _remove_stale_unknowns(
    trip: Dict[str, Any], changed: Sequence[Mapping[str, Any]], operations: List[Dict[str, Any]],
) -> None:
    changed_paths = {
        _entity_path(action["group"], action["index"], "coordinates") for action in changed
    }
    remove_indexes = sorted(
        (index for index, item in enumerate(trip["unknowns"]) if item.get("field_path") in changed_paths),
        reverse=True,
    )
    for index in remove_indexes:
        operations.append({"op": "remove", "path": "/unknowns/%d" % index})
        trip["unknowns"].pop(index)


def _apply_entity_actions(
    trip: Dict[str, Any], changed: Sequence[Mapping[str, Any]], operations: List[Dict[str, Any]],
) -> Set[str]:
    changed_refs: Set[str] = set()
    for action in changed:
        group = action["group"]
        index = action["index"]
        entity = trip[group][index]
        changed_refs.add(action["ref_id"])
        if action["kind"] == "located":
            entity["coordinates"] = copy.deepcopy(action["new_coordinates"])
            entity["claim_ids"] = list(action["new_claim_ids"])
            operations.append({
                "op": "replace", "path": _entity_path(group, index, "coordinates"),
                "value": copy.deepcopy(entity["coordinates"]),
            })
            operations.append({
                "op": "replace", "path": _entity_path(group, index, "claim_ids"),
                "value": list(entity["claim_ids"]),
            })
            for claim in action["new_claims"]:
                trip["claims"].append(claim)
                operations.append({
                    "op": "add", "path": "/claims/%d" % (len(trip["claims"]) - 1),
                    "value": copy.deepcopy(claim),
                })
        else:  # unresolved
            new_unknown = {
                "field_path": _entity_path(group, index, "coordinates"),
                "reason": action["reason"],
                "provider": "amap",
                "claim_id": None,
            }
            trip["unknowns"].append(new_unknown)
            operations.append({
                "op": "add", "path": "/unknowns/%d" % (len(trip["unknowns"]) - 1),
                "value": copy.deepcopy(new_unknown),
            })
    return changed_refs


def _fold_amap_health(
    trip: Dict[str, Any],
    operations: List[Dict[str, Any]],
    entity_count: int,
    queried_at: Any,
    now: str,
    provider_version: Any,
) -> None:
    note = "locate=%d entities folded (%s)" % (entity_count, queried_at)
    for index, entry in enumerate(trip["provider_health"]):
        if entry.get("provider") != "amap":
            continue
        updated = copy.deepcopy(entry)
        base_reason = re.sub(r"; locate=\d+ entities folded \([^)]*\)", "", updated["reason"])
        updated["reason"] = "%s; %s" % (base_reason, note)
        capabilities = list(updated["capabilities"])
        for capability in ("poi", "geocode"):
            if capability not in capabilities:
                capabilities.append(capability)
        updated["capabilities"] = capabilities
        if updated["status"] != "ready" or updated["mode"] not in ("live", "cached"):
            updated["status"] = "ready"
            updated["mode"] = "live"
        updated["checked_at"] = now
        trip["provider_health"][index] = updated
        operations.append({
            "op": "replace", "path": "/provider_health/%d" % index, "value": copy.deepcopy(updated),
        })
        return
    new_row = {
        "provider": "amap",
        "version": provider_version,
        "mode": "live",
        "status": "ready",
        "checked_at": now,
        "capabilities": ["poi", "geocode"],
        "reason": note,
    }
    trip["provider_health"].append(new_row)
    operations.append({
        "op": "add", "path": "/provider_health/%d" % (len(trip["provider_health"]) - 1),
        "value": copy.deepcopy(new_row),
    })


def _referencing_day_ids(trip: Mapping[str, Any], changed_refs: Set[str]) -> Set[str]:
    day_ids: Set[str] = set()
    for day in trip["days"]:
        for slot in day["slots"]:
            if slot.get("ref_id") in changed_refs:
                day_ids.add(day["day_id"])
    return day_ids


def _matching_row(
    rows: Sequence[Mapping[str, Any]], trip_id: str, kind: str, ref_id: str,
) -> Optional[Mapping[str, Any]]:
    for row in rows:
        if row.get("trip_id") == trip_id and row.get("kind") == kind and row.get("ref_id") == ref_id:
            return row
    return None


def _unknown_index(unknowns: Sequence[Mapping[str, Any]], group: str, index: int) -> Optional[int]:
    path = _entity_path(group, index, "coordinates")
    for position, item in enumerate(unknowns):
        if item.get("field_path") == path:
            return position
    return None
