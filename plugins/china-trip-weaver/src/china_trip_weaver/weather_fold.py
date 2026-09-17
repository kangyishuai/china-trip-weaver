"""Fold an AMap weather query envelope back into an existing Trip or Journey."""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .clock import Clock, isoformat_seconds
from .contracts import PatchResult
from .journey import replace_trip_in_journey, validate_journey
from .planning import _weather_unknown
from .replan import _all_refs, _locked_refs
from .validate_trip import validate_trip
from .weather import split_city_names


def fold_weather_into_trip(
    trip: Mapping[str, Any],
    result: Mapping[str, Any],
    clock: Clock,
    reason: Optional[str] = None,
) -> Optional[PatchResult]:
    """Fold a `ctw weather --output-json` envelope into one Trip as a new patch revision.

    Matches each day against `result["forecasts"]` by (date, query == the first
    `split_city_names(day["city"])` segment); a row missing the `query` key never
    matches. A `forecast` row adds or replaces `day.weather` (the ten AMap fields
    plus `advice` and `claim_id`) and carries over the one claim in
    `result["claims"]` whose `value` is key-for-key equal to that row's
    `forecast` (date-only matching is unsafe here because one Journey-wide query
    can mix same-day forecasts from several cities). A `no_forecast` row nulls
    `day.weather` and records a `weather_no_results` unknown. `out_of_window`
    rows and days with no matching row are left untouched. Folding the same
    result twice is a no-op and returns None.
    """

    base_trip = trip
    current_revision = int(base_trip["revision"]["number"])
    forecasts = result.get("forecasts", ())
    claims_pool = result.get("claims", ())
    queried_at = result.get("queried_at")

    trip = copy.deepcopy(dict(base_trip))
    actions = _plan_day_actions(trip["days"], forecasts, claims_pool)
    changed = _changed_actions(trip, actions)
    if not changed:
        return None

    now = isoformat_seconds(clock)
    operations: List[Dict[str, Any]] = []
    _remove_stale_unknowns(trip, changed, operations)
    _remove_stale_claims(trip, changed, operations)
    changed_day_ids = _apply_day_actions(trip, changed, operations)
    _add_new_claims(trip, changed, operations)
    _fold_amap_health(trip, operations, len(changed), queried_at, now, result.get("provider_version"))

    target_revision = current_revision + 1
    all_refs = _all_refs(base_trip)
    changed_refs = set(changed_day_ids)
    preserved_refs = sorted(all_refs - changed_refs)
    eligible = max(1, len(all_refs))
    patch = {
        "patch_id": "patch-%d-%d" % (current_revision, target_revision),
        "base_revision": current_revision,
        "target_revision": target_revision,
        "created_at": now,
        "trigger": "weather",
        "reason": reason or ("weather forecast fold (%s)" % queried_at),
        "scope": {
            "day_ids": sorted(changed_day_ids),
            "affected_refs": sorted(changed_day_ids),
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
            "weather_fold_invalid_trip: " + "; ".join(item.render() for item in report.errors)
        )
    return PatchResult(trip=trip, patch=patch, reverify_claim_ids=())


def fold_weather_into_journey(
    journey: Mapping[str, Any],
    result: Mapping[str, Any],
    base_revision: int,
    clock: Clock,
    reason: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Fold the same weather envelope into every Trip of a Journey, one reassembly.

    Delegates each Trip to `fold_weather_into_trip`; a Trip that does not change
    is left alone. Every Trip that does change is swapped in with
    `replace_trip_in_journey` (its revision bump is chained when more than one
    Trip changes), and the resulting revision's `created_by` is forced back to
    `"system"`, since `replace_trip_in_journey` defaults it to `"user"` for its
    own human-triggered use case. Returns None when no Trip changed.
    """

    current_revision = int(journey["revision"]["number"])
    if base_revision != current_revision:
        raise ValueError(
            "revision_conflict: Journey is at revision %d, not %d" % (current_revision, base_revision)
        )

    working = journey
    changed_any = False
    for trip_id in [item["trip_id"] for item in journey["trips"]]:
        trip = next(item for item in working["trips"] if item["trip_id"] == trip_id)
        patch_result = fold_weather_into_trip(trip, result, clock, reason=reason)
        if patch_result is None:
            continue
        changed_any = True
        working = replace_trip_in_journey(
            working, patch_result.trip, int(working["revision"]["number"]), clock, reason=reason,
        )
        working = dict(working)
        working["revision"] = dict(working["revision"])
        working["revision"]["created_by"] = "system"

    if not changed_any:
        return None

    report = validate_journey(working)
    if not report.ok:
        raise ValueError(
            "weather_fold_invalid_journey: " + "; ".join(item.render() for item in report.errors)
        )
    return working


def _plan_day_actions(
    days: Sequence[Mapping[str, Any]],
    forecasts: Sequence[Mapping[str, Any]],
    claims_pool: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    for day_index, day in enumerate(days):
        names = split_city_names(day.get("city", ""))
        if not names:
            continue
        row = _matching_forecast_row(forecasts, day.get("date"), names[0])
        if row is None:
            continue
        if row.get("status") == "forecast":
            claim = _claim_matching_value(claims_pool, row.get("forecast"))
            if claim is None:
                raise ValueError(
                    "weather_fold_claim_missing: no claim in result[\"claims\"] matches "
                    "the forecast value for day %s" % day.get("day_id")
                )
            new_claim = copy.deepcopy(dict(claim))
            new_claim["subject_ref"] = day["day_id"]
            new_weather = copy.deepcopy(dict(claim["value"]))
            new_weather["advice"] = list(row.get("advice") or ())
            new_weather["claim_id"] = new_claim["claim_id"]
            actions.append({
                "day_index": day_index, "kind": "forecast",
                "new_weather": new_weather, "new_claim": new_claim,
            })
        elif row.get("status") == "no_forecast":
            actions.append({"day_index": day_index, "kind": "no_forecast", "new_weather": None})
        # out_of_window (or any other status) leaves the day untouched.
    return actions


def _changed_actions(trip: Mapping[str, Any], actions: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    changed: List[Dict[str, Any]] = []
    for action in actions:
        day = trip["days"][action["day_index"]]
        current_weather = day.get("weather")
        if action["kind"] == "forecast":
            if current_weather == action["new_weather"]:
                continue
        elif current_weather is None:
            existing = _unknown_index(trip["unknowns"], action["day_index"])
            if existing is not None and trip["unknowns"][existing].get("reason") == "weather_no_results":
                continue
        changed.append(dict(action))
    return changed


def _remove_stale_unknowns(
    trip: Dict[str, Any], changed: Sequence[Mapping[str, Any]], operations: List[Dict[str, Any]],
) -> None:
    changed_paths = {"/days/%d/weather" % action["day_index"] for action in changed}
    remove_indexes = sorted(
        (index for index, item in enumerate(trip["unknowns"]) if item.get("field_path") in changed_paths),
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
        current_weather = trip["days"][action["day_index"]].get("weather")
        if isinstance(current_weather, dict) and current_weather.get("claim_id"):
            old_claim_ids.add(current_weather["claim_id"])
    remove_indexes = sorted(
        (index for index, claim in enumerate(trip["claims"]) if claim.get("claim_id") in old_claim_ids),
        reverse=True,
    )
    for index in remove_indexes:
        operations.append({"op": "remove", "path": "/claims/%d" % index})
        trip["claims"].pop(index)


def _apply_day_actions(
    trip: Dict[str, Any], changed: Sequence[Mapping[str, Any]], operations: List[Dict[str, Any]],
) -> List[str]:
    changed_day_ids: List[str] = []
    for action in changed:
        day_index = action["day_index"]
        day = trip["days"][day_index]
        op = "add" if "weather" not in day else "replace"
        day["weather"] = action["new_weather"]
        operations.append({
            "op": op, "path": "/days/%d/weather" % day_index,
            "value": copy.deepcopy(action["new_weather"]),
        })
        changed_day_ids.append(day["day_id"])
        if action["kind"] == "no_forecast":
            new_unknown = _weather_unknown(day_index, "weather_no_results")
            trip["unknowns"].append(new_unknown)
            operations.append({
                "op": "add", "path": "/unknowns/%d" % (len(trip["unknowns"]) - 1),
                "value": copy.deepcopy(new_unknown),
            })
    return changed_day_ids


def _add_new_claims(
    trip: Dict[str, Any], changed: Sequence[Mapping[str, Any]], operations: List[Dict[str, Any]],
) -> None:
    for action in changed:
        if action["kind"] != "forecast":
            continue
        trip["claims"].append(action["new_claim"])
        operations.append({
            "op": "add", "path": "/claims/%d" % (len(trip["claims"]) - 1),
            "value": copy.deepcopy(action["new_claim"]),
        })


def _fold_amap_health(
    trip: Dict[str, Any],
    operations: List[Dict[str, Any]],
    day_count: int,
    queried_at: Any,
    now: str,
    provider_version: Any,
) -> None:
    note = "weather=%d days folded (%s)" % (day_count, queried_at)
    for index, entry in enumerate(trip["provider_health"]):
        if entry.get("provider") != "amap":
            continue
        updated = copy.deepcopy(entry)
        updated["reason"] = "%s; %s" % (updated["reason"], note)
        if "weather" not in updated["capabilities"]:
            updated["capabilities"] = list(updated["capabilities"]) + ["weather"]
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
        "capabilities": ["weather"],
        "reason": note,
    }
    trip["provider_health"].append(new_row)
    operations.append({
        "op": "add", "path": "/provider_health/%d" % (len(trip["provider_health"]) - 1),
        "value": copy.deepcopy(new_row),
    })


def _matching_forecast_row(
    forecasts: Sequence[Mapping[str, Any]], target_date: Any, target_name: str,
) -> Optional[Mapping[str, Any]]:
    for row in forecasts:
        if row.get("date") == target_date and row.get("query") == target_name:
            return row
    return None


def _claim_matching_value(
    claims: Sequence[Mapping[str, Any]], value: Any,
) -> Optional[Mapping[str, Any]]:
    for claim in claims:
        if claim.get("value") == value:
            return claim
    return None


def _unknown_index(unknowns: Sequence[Mapping[str, Any]], day_index: int) -> Optional[int]:
    path = "/days/%d/weather" % day_index
    for index, item in enumerate(unknowns):
        if item.get("field_path") == path:
            return index
    return None
