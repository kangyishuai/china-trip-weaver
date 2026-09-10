"""Versioned local Trip patches with lock and unaffected-day stability."""

from __future__ import annotations

import copy
from datetime import timedelta
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from .clock import Clock, isoformat_seconds
from .contracts import PatchResult, canonical_json
from .planning import _budget_ledger
from .validate_trip import MODE_RANK


class ReplanError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


VALID_EVENT_TYPES = ("closure", "weather", "delay", "user_delete", "refresh")
_TRIGGER_BY_EVENT_TYPE = {"user_delete": "user_edit", "refresh": "provider_change"}


def replan_trip(
    base_trip: Mapping[str, Any],
    event: Mapping[str, Any],
    base_revision: int,
    user_locked_refs: Sequence[str],
    clock: Clock,
    rail_result: Optional[Mapping[str, Any]] = None,
) -> PatchResult:
    current_revision = int(base_trip["revision"]["number"])
    if base_revision != current_revision:
        raise ReplanError("revision_conflict", "base revision does not match the current Trip")
    event_type = event.get("type")
    if event_type not in VALID_EVENT_TYPES:
        raise ReplanError(
            "event_type",
            'event type must use the field "type" with one of: ' + ", ".join(VALID_EVENT_TYPES),
        )
    subject_ref = event.get("subject_ref")
    if not isinstance(subject_ref, str) or not subject_ref:
        raise ReplanError(
            "event_subject",
            "event subject_ref is required; use the target slot's slot_id or the ref_id it schedules",
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
    now = isoformat_seconds(clock)

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
    elif event_type == "refresh":
        _apply_refresh(
            trip, day_index, slot_index, event, rail_result, locked_refs, operations, changed_refs, now,
        )

    if not operations:
        raise ReplanError("empty_patch", "replan produced no operation")
    for index, day in enumerate(trip["days"]):
        if index != day_index and canonical_json(day) != before_days[index]:
            raise ReplanError("stability_violation", "an unaffected day changed")

    target_revision = current_revision + 1
    all_refs = _all_refs(base_trip)
    preserved_refs = sorted(all_refs - changed_refs)
    eligible = max(1, len(all_refs))
    patch = {
        "patch_id": "patch-%d-%d" % (current_revision, target_revision),
        "base_revision": current_revision,
        "target_revision": target_revision,
        "created_at": now,
        "trigger": _TRIGGER_BY_EVENT_TYPE.get(event_type, event_type),
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


def _apply_refresh(
    trip: Dict[str, Any],
    day_index: int,
    slot_index: int,
    event: Mapping[str, Any],
    rail_result: Optional[Mapping[str, Any]],
    locked_refs: Set[str],
    operations: List[Dict[str, Any]],
    changed_refs: Set[str],
    now: str,
) -> None:
    target_slot = trip["days"][day_index]["slots"][slot_index]
    leg_index, leg = _find_rail_leg(trip, target_slot)
    if rail_result is None:
        raise ReplanError("refresh_result_required", "refresh requires a rail_result")
    travel_date = str(leg["depart_at"])[:10]
    selected = _select_refresh_service(event, rail_result, travel_date)
    if str(selected["arrive_at"])[:10] != str(selected["depart_at"])[:10]:
        raise ReplanError(
            "refresh_unsupported", "refresh does not support a service that arrives on a different day",
        )
    if slot_index > 0:
        previous_slot = trip["days"][day_index]["slots"][slot_index - 1]
        if str(selected["depart_at"]) < str(previous_slot["end_at"]):
            raise ReplanError("refresh_overlap", "refreshed service departs before the previous slot ends")

    new_leg = copy.deepcopy(dict(selected))
    for key in ("leg_id", "from_ref", "to_ref", "locked"):
        new_leg[key] = copy.deepcopy(leg[key])
    if "group_refs" in leg:
        new_leg["group_refs"] = copy.deepcopy(leg["group_refs"])
    else:
        new_leg.pop("group_refs", None)
    trip["transport_legs"][leg_index] = new_leg
    operations.append({
        "op": "replace", "path": "/transport_legs/%d" % leg_index, "value": copy.deepcopy(new_leg),
    })

    new_slot = copy.deepcopy(target_slot)
    new_slot["start_at"] = new_leg["depart_at"]
    new_slot["end_at"] = new_leg["arrive_at"]
    new_slot["claim_ids"] = list(new_leg["claim_ids"])
    trip["days"][day_index]["slots"][slot_index] = new_slot
    operations.append({
        "op": "replace", "path": "/days/%d/slots/%d" % (day_index, slot_index), "value": copy.deepcopy(new_slot),
    })
    changed_refs.add(new_slot["slot_id"])
    changed_refs.add(new_leg["leg_id"])

    old_arrive, new_arrive = leg.get("arrive_at"), new_leg.get("arrive_at")
    if isinstance(old_arrive, str) and isinstance(new_arrive, str):
        delta_minutes = int((_dt(new_arrive) - _dt(old_arrive)).total_seconds() // 60)
        if delta_minutes > 0:
            _shift_slots(trip, day_index, slot_index + 1, delta_minutes, locked_refs, operations, changed_refs)

    for claim in rail_result.get("claims", ()):
        if claim.get("subject_ref") != selected.get("leg_id"):
            continue
        copied = copy.deepcopy(dict(claim))
        copied["subject_ref"] = new_leg["leg_id"]
        trip["claims"].append(copied)
        operations.append({
            "op": "add", "path": "/claims/%d" % (len(trip["claims"]) - 1), "value": copy.deepcopy(copied),
        })

    remove_paths = {"/transport_legs/%d/service_number" % leg_index}
    if (new_leg.get("price") or {}).get("amount") is not None:
        remove_paths.add("/transport_legs/%d/price/amount" % leg_index)
    has_budget = "budget_ledger" in trip
    remove_indexes = sorted(
        (
            index for index, item in enumerate(trip["unknowns"])
            if item.get("field_path") in remove_paths
            or (has_budget and str(item.get("field_path", "")).startswith("/budget_ledger/"))
        ),
        reverse=True,
    )
    for index in remove_indexes:
        operations.append({"op": "remove", "path": "/unknowns/%d" % index})
        trip["unknowns"].pop(index)

    if has_budget:
        ledger, budget_unknowns = _budget_ledger(
            trip["request"], trip["days"], trip["transport_legs"], trip["lodgings"], trip["pois"], trip["claims"],
        )
        trip["budget_ledger"] = ledger
        operations.append({"op": "replace", "path": "/budget_ledger", "value": copy.deepcopy(ledger)})
        for item in budget_unknowns:
            trip["unknowns"].append(item)
            operations.append({
                "op": "add", "path": "/unknowns/%d" % (len(trip["unknowns"]) - 1), "value": copy.deepcopy(item),
            })

    _recompute_rail_health(trip, operations, now)
    _recompute_top_mode(trip, operations)


def _find_rail_leg(trip: Mapping[str, Any], target_slot: Mapping[str, Any]) -> Tuple[int, Mapping[str, Any]]:
    ref_id = target_slot.get("ref_id")
    if ref_id:
        for index, item in enumerate(trip["transport_legs"]):
            if item["leg_id"] == ref_id and item.get("travel_mode") == "rail":
                return index, item
    raise ReplanError("refresh_not_rail", "refresh only supports a rail transport leg")


def _select_refresh_service(
    event: Mapping[str, Any],
    rail_result: Mapping[str, Any],
    travel_date: str,
) -> Mapping[str, Any]:
    same_day = [
        item for item in rail_result.get("transport_legs", ())
        if isinstance(item.get("depart_at"), str) and item["depart_at"][:10] == travel_date
    ]
    service_number = event.get("service_number")
    if service_number:
        matches = [item for item in same_day if item.get("service_number") == service_number]
        if not matches:
            raise ReplanError(
                "refresh_service_not_found", "no rail service matches the requested service_number",
            )
        return matches[0]
    if not same_day:
        raise ReplanError("refresh_no_service", "no rail service is available for the requested date")
    return min(same_day, key=lambda item: (item["arrive_at"], item["depart_at"]))


def _recompute_rail_health(trip: Dict[str, Any], operations: List[Dict[str, Any]], now: str) -> None:
    rail_legs = [leg for leg in trip["transport_legs"] if leg.get("travel_mode") == "rail"]
    if not rail_legs:
        return
    live_count = sum(1 for leg in rail_legs if leg.get("data_mode") == "live")
    if live_count == len(rail_legs):
        mode, status = "live", "ready"
        reason = "all dated rail legs were normalized from live MCP inventory"
    else:
        mode, status = "static", "degraded"
        reason = "dated deep-link fallback used for %d of %d rail leg(s)" % (
            len(rail_legs) - live_count, len(rail_legs),
        )
    for index, entry in enumerate(trip["provider_health"]):
        if entry.get("provider") != "12306-mcp":
            continue
        if entry.get("mode") == mode and entry.get("status") == status and entry.get("reason") == reason:
            return
        updated = copy.deepcopy(entry)
        updated.update(mode=mode, status=status, reason=reason, checked_at=now)
        trip["provider_health"][index] = updated
        operations.append({
            "op": "replace", "path": "/provider_health/%d" % index, "value": copy.deepcopy(updated),
        })
        return


def _recompute_top_mode(trip: Dict[str, Any], operations: List[Dict[str, Any]]) -> None:
    component_modes = [leg["data_mode"] for leg in trip["transport_legs"]]
    component_modes.extend(claim["mode"] for claim in trip["claims"])
    component_modes.extend(health["mode"] for health in trip["provider_health"])
    if not component_modes:
        return
    conservative = max(component_modes, key=lambda mode: MODE_RANK[mode])
    if MODE_RANK[trip["mode"]] < MODE_RANK[conservative]:
        trip["mode"] = conservative
        operations.append({"op": "replace", "path": "/mode", "value": conservative})

