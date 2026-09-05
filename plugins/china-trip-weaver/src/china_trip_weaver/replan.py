"""Versioned local Trip patches with lock and unaffected-day stability."""

from __future__ import annotations

import copy
from datetime import timedelta
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from .clock import Clock, isoformat_seconds
from .contracts import PatchResult, canonical_json


class ReplanError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def replan_trip(
    base_trip: Mapping[str, Any],
    event: Mapping[str, Any],
    base_revision: int,
    user_locked_refs: Sequence[str],
    clock: Clock,
) -> PatchResult:
    current_revision = int(base_trip["revision"]["number"])
    if base_revision != current_revision:
        raise ReplanError("revision_conflict", "base revision does not match the current Trip")
    event_type = event.get("type")
    if event_type not in ("closure", "weather", "delay", "user_delete"):
        raise ReplanError(
            "event_type",
            'event type must use the field "type" with one of: closure, weather, delay, user_delete',
        )
    subject_ref = event.get("subject_ref")
    if not isinstance(subject_ref, str) or not subject_ref:
        raise ReplanError(
            "event_subject",
            "event subject_ref is required and must be the target slot's slot_id, not a poi or lodging ref_id",
        )

    trip = copy.deepcopy(dict(base_trip))
    day_index, slot_index = _find_slot(trip, subject_ref)
    target_slot = trip["days"][day_index]["slots"][slot_index]
    locked_refs = _locked_refs(base_trip).union(user_locked_refs)
    if subject_ref in locked_refs and event_type != "delay":
        raise ReplanError("locked_ref", "event would modify a locked item without explicit unlock")

    before_days = [canonical_json(day) for day in base_trip["days"]]
    operations: List[Dict[str, Any]] = []
    changed_refs: Set[str] = {subject_ref}
    reverify = set(event.get("reverify_claim_ids", target_slot.get("claim_ids", ())))

    if event_type in ("closure", "weather"):
        replacement = copy.deepcopy(event.get("replacement_slot"))
        if not isinstance(replacement, dict):
            raise ReplanError("replacement_required", "closure/weather requires a replacement_slot")
        if replacement.get("locked"):
            raise ReplanError("replacement_locked", "a provider replacement cannot create a lock")
        path = "/days/%d/slots/%d" % (day_index, slot_index)
        trip["days"][day_index]["slots"][slot_index] = replacement
        operations.append({"op": "replace", "path": path, "value": copy.deepcopy(replacement)})
        if replacement.get("ref_id"):
            changed_refs.add(replacement["ref_id"])
    elif event_type == "user_delete":
        path = "/days/%d/slots/%d" % (day_index, slot_index)
        trip["days"][day_index]["slots"].pop(slot_index)
        operations.append({"op": "remove", "path": path})
    elif event_type == "delay":
        delta = int(event.get("delta_minutes", 0))
        if delta <= 0:
            raise ReplanError(
                "delay_value",
                'delay requires a positive number in the "delta_minutes" field, not "minutes"',
            )
        _shift_slots(trip, day_index, slot_index, delta, locked_refs, operations, changed_refs)
        _shift_transport_leg(trip, target_slot.get("ref_id"), delta, operations, changed_refs)

    if not operations:
        raise ReplanError("empty_patch", "replan produced no operation")
    for index, day in enumerate(trip["days"]):
        if index != day_index and canonical_json(day) != before_days[index]:
            raise ReplanError("stability_violation", "an unaffected day changed")

    target_revision = current_revision + 1
    now = isoformat_seconds(clock)
    all_refs = _all_refs(base_trip)
    preserved_refs = sorted(all_refs - changed_refs)
    eligible = max(1, len(all_refs))
    patch = {
        "patch_id": "patch-%d-%d" % (current_revision, target_revision),
        "base_revision": current_revision,
        "target_revision": target_revision,
        "created_at": now,
        "trigger": "user_edit" if event_type == "user_delete" else event_type,
        "reason": str(event.get("reason") or event_type),
        "scope": {
            "day_ids": [trip["days"][day_index]["day_id"]],
            "affected_refs": sorted(changed_refs),
            "locked_refs": sorted(locked_refs),
        },
        "operations": operations,
        "reverify_claim_ids": sorted(reverify),
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
    return PatchResult(trip=trip, patch=patch, reverify_claim_ids=tuple(sorted(reverify)))


def _find_slot(trip: Mapping[str, Any], subject_ref: str) -> Tuple[int, int]:
    for day_index, day in enumerate(trip["days"]):
        for slot_index, slot in enumerate(day["slots"]):
            if slot["slot_id"] == subject_ref or slot.get("ref_id") == subject_ref:
                return day_index, slot_index
    raise ReplanError("subject_not_found", "event subject is not scheduled")


def _locked_refs(trip: Mapping[str, Any]) -> Set[str]:
    result: Set[str] = set()
    for day in trip["days"]:
        for slot in day["slots"]:
            if slot["locked"]:
                result.add(slot["slot_id"])
                if slot.get("ref_id"):
                    result.add(slot["ref_id"])
    for group, id_key in (("transport_legs", "leg_id"), ("lodgings", "lodging_id")):
        for item in trip[group]:
            if item.get("locked"):
                result.add(item[id_key])
    return result


def _all_refs(trip: Mapping[str, Any]) -> Set[str]:
    result = {day["day_id"] for day in trip["days"]}
    for day in trip["days"]:
        for slot in day["slots"]:
            result.add(slot["slot_id"])
            if slot.get("ref_id"):
                result.add(slot["ref_id"])
    result.update(item["leg_id"] for item in trip["transport_legs"])
    result.update(item["lodging_id"] for item in trip["lodgings"])
    result.update(item["poi_id"] for item in trip["pois"])
    return result


def _shift_slots(
    trip: Dict[str, Any],
    day_index: int,
    slot_index: int,
    delta_minutes: int,
    locked_refs: Set[str],
    operations: List[Dict[str, Any]],
    changed_refs: Set[str],
) -> None:
    slots = trip["days"][day_index]["slots"]
    delta = timedelta(minutes=delta_minutes)
    previous_end: Optional[str] = None
    for index in range(slot_index, len(slots)):
        slot = slots[index]
        if index > slot_index and (slot["slot_id"] in locked_refs or slot.get("ref_id") in locked_refs):
            if previous_end and previous_end > slot["start_at"]:
                raise ReplanError("locked_overlap", "delay collides with the next locked anchor")
            break
        old_start = _dt(slot["start_at"])
        old_end = _dt(slot["end_at"])
        new_start = (old_start + delta).isoformat(timespec="seconds")
        new_end = (old_end + delta).isoformat(timespec="seconds")
        slot["start_at"] = new_start
        slot["end_at"] = new_end
        operations.extend((
            {"op": "replace", "path": "/days/%d/slots/%d/start_at" % (day_index, index), "value": new_start},
            {"op": "replace", "path": "/days/%d/slots/%d/end_at" % (day_index, index), "value": new_end},
        ))
        changed_refs.add(slot["slot_id"])
        if slot.get("ref_id"):
            changed_refs.add(slot["ref_id"])
        previous_end = new_end


def _shift_transport_leg(
    trip: Dict[str, Any],
    leg_id: Optional[str],
    delta_minutes: int,
    operations: List[Dict[str, Any]],
    changed_refs: Set[str],
) -> None:
    if not leg_id:
        return
    delta = timedelta(minutes=delta_minutes)
    for index, leg in enumerate(trip["transport_legs"]):
        if leg["leg_id"] != leg_id:
            continue
        for field in ("depart_at", "arrive_at"):
            if leg[field] is None:
                continue
            shifted = (_dt(leg[field]) + delta).isoformat(timespec="seconds")
            leg[field] = shifted
            operations.append({"op": "replace", "path": "/transport_legs/%d/%s" % (index, field), "value": shifted})
        changed_refs.add(leg_id)
        return


def _dt(value: str):
    from datetime import datetime

    return datetime.fromisoformat(value.replace("Z", "+00:00"))

