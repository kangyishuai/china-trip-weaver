"""Fold a nearby-dining result envelope back into an existing Trip or Journey."""

from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .clock import Clock, isoformat_seconds
from .contracts import PatchResult
from .journey import replace_trips_in_journey, validate_journey
from .replan import _all_refs, _locked_refs
from .validate_trip import validate_trip


def fold_dining_into_trip(
    trip: Mapping[str, Any],
    result: Mapping[str, Any],
    clock: Clock,
    reason: Optional[str] = None,
) -> Optional[PatchResult]:
    """Fold matching ``slots`` rows into one Trip as a new patch revision.

    Rows match by both ``trip_id`` and ``slot_id``. ``options`` rows replace a
    slot's dining reference and copy each option's identity claim onto that
    slot. ``no_anchor`` and ``no_results`` rows write ``dining: null`` plus a
    typed unknown. ``provider_error`` and missing rows leave the slot alone.
    Folding the same result twice is a no-op.
    """

    base_trip = trip
    current_revision = int(base_trip["revision"]["number"])
    queried_at = result.get("queried_at")
    claims_pool = result.get("claims", ())

    trip = copy.deepcopy(dict(base_trip))
    actions = _plan_slot_actions(trip, result.get("slots", ()), claims_pool, queried_at)
    changed = _changed_actions(trip, actions)
    if not changed:
        return None

    now = isoformat_seconds(clock)
    operations: List[Dict[str, Any]] = []
    _remove_stale_unknowns(trip, changed, operations)
    _remove_stale_claims(trip, changed, operations)
    changed_day_ids, changed_slot_ids = _apply_slot_actions(trip, changed, operations)
    _add_new_claims(trip, changed, operations)
    _fold_amap_health(
        trip, operations, len(changed), queried_at, now, result.get("provider_version"),
    )

    target_revision = current_revision + 1
    all_refs = _all_refs(base_trip)
    changed_refs = set(changed_slot_ids)
    preserved_refs = sorted(all_refs - changed_refs)
    eligible = max(1, len(all_refs))
    patch = {
        "patch_id": "patch-%d-%d" % (current_revision, target_revision),
        "base_revision": current_revision,
        "target_revision": target_revision,
        "created_at": now,
        "trigger": "dining",
        "reason": reason or ("dining fold (%s)" % queried_at),
        "scope": {
            "day_ids": sorted(set(changed_day_ids)),
            "affected_refs": sorted(changed_slot_ids),
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
            "dining_fold_invalid_trip: " + "; ".join(item.render() for item in report.errors)
        )
    return PatchResult(trip=trip, patch=patch, reverify_claim_ids=())


def fold_dining_into_journey(
    journey: Mapping[str, Any],
    result: Mapping[str, Any],
    base_revision: int,
    clock: Clock,
    reason: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Fold one dining envelope into all matching Trips in one reassembly."""

    current_revision = int(journey["revision"]["number"])
    if base_revision != current_revision:
        raise ValueError(
            "revision_conflict: Journey is at revision %d, not %d"
            % (current_revision, base_revision)
        )

    changed_trips: List[Mapping[str, Any]] = []
    for trip in journey["trips"]:
        patch_result = fold_dining_into_trip(trip, result, clock, reason=reason)
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
            "dining_fold_invalid_journey: " + "; ".join(item.render() for item in report.errors)
        )
    return working


def _plan_slot_actions(
    trip: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    claims_pool: Sequence[Mapping[str, Any]],
    queried_at: Any,
) -> List[Dict[str, Any]]:
    claims_by_id = {claim.get("claim_id"): claim for claim in claims_pool}
    actions: List[Dict[str, Any]] = []
    for day_index, day in enumerate(trip["days"]):
        for slot_index, slot in enumerate(day["slots"]):
            row = _matching_slot_row(rows, trip["trip_id"], slot["slot_id"])
            if row is None:
                continue
            status = row.get("status")
            if status == "options":
                anchor = row.get("anchor")
                if not isinstance(anchor, Mapping):
                    raise ValueError(
                        "dining_fold_invalid_anchor: options row for slot %s has no anchor"
                        % slot["slot_id"]
                    )
                new_claims = []
                for option in row.get("options", ()):
                    claim_id = option.get("claim_id")
                    claim = claims_by_id.get(claim_id)
                    if claim is None:
                        raise ValueError(
                            "dining_fold_claim_missing: no claim %s in result[\"claims\"] "
                            "for slot %s" % (claim_id, slot["slot_id"])
                        )
                    new_claim = copy.deepcopy(dict(claim))
                    new_claim["subject_ref"] = slot["slot_id"]
                    new_claims.append(new_claim)
                new_dining = {
                    "queried_at": queried_at,
                    "anchor_ref": anchor["ref_id"],
                    "anchor_name": anchor["name"],
                    "radius_m": row["radius_m"],
                    "search_url": row["search_url"],
                    "options": copy.deepcopy(list(row.get("options", ()))),
                }
                actions.append({
                    "day_index": day_index,
                    "slot_index": slot_index,
                    "kind": "options",
                    "new_dining": new_dining,
                    "new_claims": new_claims,
                })
            elif status in ("no_anchor", "no_results"):
                actions.append({
                    "day_index": day_index,
                    "slot_index": slot_index,
                    "kind": status,
                    "new_dining": None,
                    "new_claims": [],
                })
            # provider_error and unknown statuses leave the slot untouched.
    return actions


def _changed_actions(
    trip: Mapping[str, Any], actions: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    changed: List[Dict[str, Any]] = []
    for action in actions:
        slot = trip["days"][action["day_index"]]["slots"][action["slot_index"]]
        if action["kind"] == "options":
            if slot.get("dining") == action["new_dining"]:
                continue
        elif slot.get("dining") is None:
            reason = "dining_%s" % action["kind"]
            existing = _unknown_index(
                trip["unknowns"], action["day_index"], action["slot_index"],
            )
            if existing is not None and trip["unknowns"][existing].get("reason") == reason:
                continue
        changed.append(dict(action))
    return changed


def _dining_path(day_index: int, slot_index: int) -> str:
    return "/days/%d/slots/%d/dining" % (day_index, slot_index)


def _remove_stale_unknowns(
    trip: Dict[str, Any], changed: Sequence[Mapping[str, Any]], operations: List[Dict[str, Any]],
) -> None:
    changed_paths = {
        _dining_path(action["day_index"], action["slot_index"]) for action in changed
    }
    remove_indexes = sorted(
        (index for index, item in enumerate(trip["unknowns"])
         if item.get("field_path") in changed_paths),
        reverse=True,
    )
    for index in remove_indexes:
        operations.append({"op": "remove", "path": "/unknowns/%d" % index})
        trip["unknowns"].pop(index)


def _remove_stale_claims(
    trip: Dict[str, Any], changed: Sequence[Mapping[str, Any]], operations: List[Dict[str, Any]],
) -> None:
    old_claim_ids = set()
    for action in changed:
        slot = trip["days"][action["day_index"]]["slots"][action["slot_index"]]
        dining = slot.get("dining")
        if isinstance(dining, Mapping):
            old_claim_ids.update(
                option.get("claim_id") for option in dining.get("options", ())
                if option.get("claim_id")
            )
    remove_indexes = sorted(
        (index for index, claim in enumerate(trip["claims"])
         if claim.get("claim_id") in old_claim_ids),
        reverse=True,
    )
    for index in remove_indexes:
        operations.append({"op": "remove", "path": "/claims/%d" % index})
        trip["claims"].pop(index)


def _apply_slot_actions(
    trip: Dict[str, Any], changed: Sequence[Mapping[str, Any]], operations: List[Dict[str, Any]],
) -> tuple[List[str], List[str]]:
    changed_day_ids: List[str] = []
    changed_slot_ids: List[str] = []
    for action in changed:
        day_index = action["day_index"]
        slot_index = action["slot_index"]
        day = trip["days"][day_index]
        slot = day["slots"][slot_index]
        operation = "add" if "dining" not in slot else "replace"
        slot["dining"] = action["new_dining"]
        operations.append({
            "op": operation,
            "path": _dining_path(day_index, slot_index),
            "value": copy.deepcopy(action["new_dining"]),
        })
        changed_day_ids.append(day["day_id"])
        changed_slot_ids.append(slot["slot_id"])
        if action["kind"] in ("no_anchor", "no_results"):
            new_unknown = {
                "field_path": _dining_path(day_index, slot_index),
                "reason": "dining_%s" % action["kind"],
                "provider": "amap",
                "claim_id": None,
            }
            trip["unknowns"].append(new_unknown)
            operations.append({
                "op": "add",
                "path": "/unknowns/%d" % (len(trip["unknowns"]) - 1),
                "value": copy.deepcopy(new_unknown),
            })
    return changed_day_ids, changed_slot_ids


def _add_new_claims(
    trip: Dict[str, Any], changed: Sequence[Mapping[str, Any]], operations: List[Dict[str, Any]],
) -> None:
    for action in changed:
        for claim in action["new_claims"]:
            trip["claims"].append(claim)
            operations.append({
                "op": "add",
                "path": "/claims/%d" % (len(trip["claims"]) - 1),
                "value": copy.deepcopy(claim),
            })


def _fold_amap_health(
    trip: Dict[str, Any],
    operations: List[Dict[str, Any]],
    slot_count: int,
    queried_at: Any,
    now: str,
    provider_version: Any,
) -> None:
    note = "dining=%d slots folded (%s)" % (slot_count, queried_at)
    for index, entry in enumerate(trip["provider_health"]):
        if entry.get("provider") != "amap":
            continue
        updated = copy.deepcopy(entry)
        base_reason = re.sub(r"; dining=\d+ slots folded \([^)]*\)", "", updated["reason"])
        updated["reason"] = "%s; %s" % (base_reason, note)
        if "poi_around" not in updated["capabilities"]:
            updated["capabilities"] = list(updated["capabilities"]) + ["poi_around"]
        if updated["status"] != "ready" or updated["mode"] not in ("live", "cached"):
            updated["status"] = "ready"
            updated["mode"] = "live"
        updated["checked_at"] = now
        trip["provider_health"][index] = updated
        operations.append({
            "op": "replace", "path": "/provider_health/%d" % index,
            "value": copy.deepcopy(updated),
        })
        return
    new_row = {
        "provider": "amap",
        "version": provider_version,
        "mode": "live",
        "status": "ready",
        "checked_at": now,
        "capabilities": ["poi_around"],
        "reason": note,
    }
    trip["provider_health"].append(new_row)
    operations.append({
        "op": "add", "path": "/provider_health/%d" % (len(trip["provider_health"]) - 1),
        "value": copy.deepcopy(new_row),
    })


def _matching_slot_row(
    rows: Sequence[Mapping[str, Any]], trip_id: str, slot_id: str,
) -> Optional[Mapping[str, Any]]:
    for row in rows:
        if row.get("trip_id") == trip_id and row.get("slot_id") == slot_id:
            return row
    return None


def _unknown_index(
    unknowns: Sequence[Mapping[str, Any]], day_index: int, slot_index: int,
) -> Optional[int]:
    path = _dining_path(day_index, slot_index)
    for index, item in enumerate(unknowns):
        if item.get("field_path") == path:
            return index
    return None
