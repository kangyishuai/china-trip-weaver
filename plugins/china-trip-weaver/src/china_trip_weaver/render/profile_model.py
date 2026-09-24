"""Read-only, deterministic time relationships derived from a validated Trip/Journey."""
from __future__ import annotations

import datetime as dt
import hashlib
from typing import Any, Dict, List, Mapping, Optional
from urllib.parse import parse_qsl, urlsplit

from ..validate_trip import validate_trip
from ..journey import validate_journey, journey_risk_items, journey_booking_checklist
from ..contracts import canonical_json

FORBIDDEN_KEYS = {"key", "api_key", "apikey", "token", "access_token", "secret", "password", "authorization"}
ROLE = {
    "transport": "transport", "poi": "place", "meal": "meal", "rest": "rest",
    "free": "free", "checkin": "stay", "checkout": "stay", "lodging": "stay",
}
FIELD_LABEL = {
    "service_number": "车次仍待核验", "price": "费用仍待核验", "amount": "金额仍待核验",
    "coordinates": "位置仍待核验", "opening_windows": "开放时间仍待核验",
    "dining": "餐饮仍待核验", "weather": "天气仍待核验",
}
FIELD_LABEL_EN = {
    "service_number": "service number to verify", "price": "price to verify", "amount": "amount to verify",
    "coordinates": "location to verify", "opening_windows": "opening time to verify",
    "dining": "dining to verify", "weather": "weather to verify",
}


def safe_href(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        return None
    if any(key.lower() in FORBIDDEN_KEYS for key, _ in parse_qsl(parsed.query, keep_blank_values=True)):
        return None
    if parsed.hostname in {"restapi.amap.com", "api.anysearch.com"}:
        return None
    return value


def minute(value: str) -> int:
    moment = dt.datetime.fromisoformat(value)
    return moment.hour * 60 + moment.minute


def relative_minute(value: str, day_date: str) -> int:
    moment = dt.datetime.fromisoformat(value)
    return (moment.date() - dt.date.fromisoformat(day_date)).days * 1440 + minute(value)


def clock(total_minutes: int) -> str:
    day_offset, within_day = divmod(total_minutes, 1440)
    label = "%02d:%02d" % divmod(within_day, 60)
    return ("+%dd " % day_offset + label) if day_offset else label


def _union_minutes(intervals: List[tuple[int, int]]) -> int:
    total = 0
    last_end = None
    for start, end in sorted(intervals):
        if last_end is None or start >= last_end:
            total += max(0, end - start)
            last_end = end
        elif end > last_end:
            total += end - last_end
            last_end = end
    return total


def _entity_for_pointer(trip: Mapping[str, Any], pointer: str) -> Optional[str]:
    parts = pointer.strip("/").split("/")
    groups = {"transport_legs": "leg_id", "lodgings": "lodging_id", "pois": "poi_id"}
    if len(parts) >= 2 and parts[0] in groups and parts[1].isdigit():
        items = trip[parts[0]]
        index = int(parts[1])
        if index < len(items):
            return items[index][groups[parts[0]]]
    if len(parts) >= 3 and parts[0] == "budget_ledger" and parts[1] == "items" and parts[2].isdigit():
        items = trip["budget_ledger"]["items"]
        index = int(parts[2])
        if index < len(items):
            return items[index].get("ref_id")
    return None


def _issue_title(pointer: str, locale: str) -> str:
    labels = FIELD_LABEL_EN if locale == "en" else FIELD_LABEL
    for part in reversed(pointer.strip("/").split("/")):
        if part in labels:
            return labels[part]
    return "Detail to verify" if locale == "en" else "此项仍待核验"


def _related_unknowns(trip: Mapping[str, Any], day_index: int, refs: set[str], names: Mapping[str, str]) -> List[Dict[str, Any]]:
    related = []
    for index, item in enumerate(trip["unknowns"]):
        pointer = item["field_path"]
        entity = _entity_for_pointer(trip, pointer)
        direct = pointer.startswith("/days/%d/" % day_index)
        if not direct and entity not in refs:
            continue
        claim = next((c for c in trip["claims"] if c["claim_id"] == item.get("claim_id")), None)
        related.append({
            "id": "%s:%d" % (trip["trip_id"], index),
            "title": (names.get(entity) or trip["days"][day_index]["date"]) + " · " + _issue_title(pointer, trip["request"]["locale"]),
            "reason": item["reason"],
            "field_path": pointer,
            "provider": item.get("provider") or ("Not supplied" if trip["request"]["locale"] == "en" else "未提供"),
            "claim_id": item.get("claim_id"),
            "claim_status": claim["status"] if claim else "unknown",
            "source_href": safe_href(claim.get("source_url")) if claim else None,
        })
    order = {"conflict": 0, "stale": 1, "unavailable": 2, "unknown": 3, "hypothesis": 4, "partial": 5, "verified": 6}
    return sorted(related, key=lambda issue: (order.get(issue["claim_status"], 7), issue["id"]))


def _claim_details(trip: Mapping[str, Any], claim_ids: List[str], names: Mapping[str, str]) -> List[Dict[str, Any]]:
    by_id = {claim["claim_id"]: claim for claim in trip["claims"]}
    result = []
    for claim_id in dict.fromkeys(claim_ids):
        claim = by_id.get(claim_id)
        if not claim:
            continue
        result.append({
            "id": claim_id,
            "subject": names.get(claim["subject_ref"], "关联事项"),
            "status": claim["status"],
            "provider": claim["provider"],
            "checked_at": claim["queried_at"],
            "source_href": safe_href(claim.get("source_url")),
            "field": claim["field_path"],
        })
    return result


def _scenario(day: Mapping[str, Any], legs: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    travel_slots = [slot for slot in day["slots"] if slot["kind"] == "transport" and slot["status"] == "scheduled"]
    if not travel_slots:
        has_candidate = any(slot["kind"] == "transport" for slot in day["slots"])
        return {"available": False, "reason": "这里只有备选或未采用的交通，不能当成已排行程试探。" if has_candidate else "这一天没有可移动的交通时段。"}
    unlocked = [slot for slot in travel_slots
                if not slot["locked"] and (legs.get(slot["ref_id"]) or {}).get("data_mode") in ("static", "mock")
                and not (legs.get(slot["ref_id"]) or {}).get("service_number")
                and not (legs.get(slot["ref_id"]) or {}).get("locked")]
    if not unlocked:
        return {"available": False, "reason": "这一天没有可移动的静态草案交通；已锁定或真实班次不参与试探。"}
    slot = unlocked[0]
    leg = legs.get(slot["ref_id"])
    start_dt, end_dt = dt.datetime.fromisoformat(slot["start_at"]), dt.datetime.fromisoformat(slot["end_at"])
    start, end = minute(slot["start_at"]), minute(slot["end_at"])
    if start_dt.date() != end_dt.date() or end <= start or end + 30 >= 24 * 60:
        return {"available": False, "reason": "延后 30 分钟会跨过当天边界；这个受限试探没有计算它。"}
    moving_groups = set((leg or {}).get("group_refs") or ())
    active_others = sorted(
        (item for item in day["slots"] if item["status"] == "scheduled" and item["kind"] != "free" and item["slot_id"] != slot["slot_id"]
         and not (item["kind"] == "transport" and moving_groups and (legs.get(item["ref_id"]) or {}).get("group_refs")
                  and moving_groups.isdisjoint((legs.get(item["ref_id"]) or {})["group_refs"]))),
        key=lambda item: (item["start_at"], item["end_at"]),
    )
    if any(dt.datetime.fromisoformat(item["start_at"]).date() != start_dt.date() or
           dt.datetime.fromisoformat(item["end_at"]).date() != start_dt.date() for item in active_others):
        return {"available": False, "reason": "相邻安排跨越日期；这个受限试探没有计算它。"}
    next_slot = next((item for item in active_others if minute(item["start_at"]) >= start), None)
    next_start = minute(next_slot["start_at"]) if next_slot else None
    baseline_gap = max(0, next_start - end) if next_start is not None else None
    after_gap = max(0, next_start - (end + 30)) if next_start is not None else None
    overlaps = []
    intervals = []
    baseline_intervals = []
    for other in active_others:
        baseline_start = max(start, minute(other["start_at"]))
        baseline_end = min(end, minute(other["end_at"]))
        if baseline_end > baseline_start:
            baseline_intervals.append((baseline_start, baseline_end))
        overlap_start = max(start + 30, minute(other["start_at"]))
        overlap_end = min(end + 30, minute(other["end_at"]))
        if overlap_end > overlap_start:
            intervals.append((overlap_start, overlap_end))
            overlaps.append({"title": other["title"], "slot_id": other["slot_id"],
                             "start": clock(minute(other["start_at"])), "minutes": overlap_end - overlap_start})
    primary = overlaps[0]["title"] if overlaps else next_slot["title"] if next_slot else None
    primary_start = overlaps[0]["start"] if overlaps else clock(next_start) if next_start is not None else None
    return {
        "available": True,
        "slot_id": slot["slot_id"],
        "title": slot["title"],
        "shift_minutes": 30,
        "baseline": {"depart": clock(start), "arrive": clock(end), "next_gap_minutes": baseline_gap,
                     "overlap_minutes": _union_minutes(baseline_intervals)},
        "preview": {"depart": clock(start + 30), "arrive": clock(end + 30),
                    "next_gap_minutes": after_gap, "overlap_minutes": _union_minutes(intervals), "overlaps": overlaps},
        "next_slot_title": primary,
        "next_slot_start": primary_start,
        "data_mode": leg["data_mode"] if leg else "unknown",
        "service_number": leg["service_number"] if leg else None,
        "price_known": bool(leg and leg["price"]["amount"] is not None),
        "caveat": "只移动这段草案时间块；备选、未采用及状态未知项不参与碰撞计算。不代表存在另一班车，不重排后续时段，也不推断票价或实时衔接。",
    }


def _normalize_trip_days(trip: Mapping[str, Any], segment_index: int, index_start: int) -> List[Dict[str, Any]]:
    lodgings = {item["lodging_id"]: item for item in trip["lodgings"]}
    legs = {item["leg_id"]: item for item in trip["transport_legs"]}
    names = {item["lodging_id"]: item["name"] for item in trip["lodgings"]}
    names.update({item["poi_id"]: item["name"] for item in trip["pois"]})
    names.update({item["leg_id"]: item["travel_mode"] for item in trip["transport_legs"]})
    claim_by_id = {item["claim_id"]: item for item in trip["claims"]}
    normalized = []
    for day_index, day in enumerate(trip["days"]):
        slots = []
        refs = {day["stay_id"]} if day.get("stay_id") else set()
        claim_ids = []
        for slot in day["slots"]:
            start, end = relative_minute(slot["start_at"], day["date"]), relative_minute(slot["end_at"], day["date"])
            effective = slot["status"] == "scheduled"
            if effective:
                refs.add(slot["ref_id"])
                claim_ids.extend(slot["claim_ids"])
            statuses = [claim_by_id[claim_id]["status"] for claim_id in slot["claim_ids"] if claim_id in claim_by_id]
            certainty = (
                "needs-check" if any(item in ("unknown", "stale", "conflict", "unavailable") for item in statuses)
                else "reference" if any(item in ("hypothesis", "partial", "mock") for item in statuses)
                else "verified" if statuses else "plan-only"
            )
            link = None
            if slot["kind"] == "transport" and slot["ref_id"] in legs:
                link = safe_href(legs[slot["ref_id"]].get("booking_url"))
            elif slot["ref_id"] in lodgings:
                link = next((safe_href(url) for url in lodgings[slot["ref_id"]]["deep_links"] if safe_href(url)), None)
            slots.append({
                "id": slot["slot_id"], "title": slot["title"], "kind": slot["kind"],
                "role": ROLE.get(slot["kind"], "other"), "status": slot["status"],
                "start_at": slot["start_at"], "end_at": slot["end_at"],
                "start": start, "end": end, "start_label": clock(start), "end_label": clock(end),
                "locked": bool(slot["locked"]), "claim_ids": slot["claim_ids"], "ref_id": slot["ref_id"],
                "href": link, "certainty": certainty, "effective": effective,
            })
        stay = lodgings.get(day.get("stay_id"))
        if stay:
            claim_ids.extend(stay["claim_ids"])
        issues = _related_unknowns(trip, day_index, refs, names)
        scheduled = [slot for slot in slots if slot["effective"] and slot["kind"] != "free"]
        occupied = _union_minutes([(slot["start"], slot["end"]) for slot in scheduled])
        first = min((slot["start"] for slot in scheduled), default=None)
        last = max((slot["end"] for slot in scheduled), default=None)
        span = (last - first) if first is not None and last is not None else 0
        normalized.append({
            "id": "%s:%s" % (trip["trip_id"], day["day_id"]), "index": index_start + day_index,
            "date": day["date"], "city": day["city"], "segment_index": segment_index,
            "stay_name": stay["name"] if stay else None,
            "stay_price": stay["price"] if stay else None,
            "stay_href": next((safe_href(url) for url in stay["deep_links"] if safe_href(url)), None) if stay else None,
            "slots": slots,
            "first": first, "last": last, "occupied_minutes": occupied,
            "span_minutes": span, "open_minutes": max(0, span - occupied),
            "inactive_count": sum(not slot["effective"] for slot in slots),
            "issues": issues,
            "claims": _claim_details(trip, claim_ids, names),
            "scenario": _scenario(day, legs),
            "data_mode": trip["mode"],
        })
    return normalized


def build_model(source: Mapping[str, Any]) -> Dict[str, Any]:
    is_journey = "trips" in source
    if is_journey:
        report = validate_journey(source)
        trips = source["trips"]
        groups = source.get("traveler_groups") or ()
        locale = trips[0]["request"]["locale"]
        origin = " / ".join(group["origin"]["name"] for group in groups) if groups else (
            source["origin"]["name"] if source.get("origin") else "Origin not supplied" if locale == "en" else "出发地未提供")
        travelers = sum(group["travelers"] for group in groups) if groups else source["travelers"]
        start, end = source["start_date"], source["end_date"]
        risks = journey_risk_items(source)
        checklist = journey_booking_checklist(source)
        risk_total = len(risks)
    else:
        report = validate_trip(source)
        trips = [source]
        request = source["request"]
        groups = request.get("traveler_groups") or ()
        locale = request["locale"]
        origin = " / ".join(group["origin"]["name"] for group in groups) if groups else (
            request["origin"]["name"] if request.get("origin") else "Origin not supplied" if locale == "en" else "出发地未提供")
        travelers = sum(group["travelers"] for group in groups) if groups else request["travelers"]
        start, end = request["start_date"], request["end_date"]
        risk_total = None
        risks = ()
        checklist = ()
    if not report.ok:
        raise ValueError("invalid source document: " + "; ".join(issue.render() for issue in report.errors))
    days = []
    route = [origin]
    providers = []
    all_unknowns = []
    all_claims = []
    for segment_index, trip in enumerate(trips):
        days.extend(_normalize_trip_days(trip, segment_index, len(days)))
        names = {item["lodging_id"]: item["name"] for item in trip["lodgings"]}
        names.update({item["poi_id"]: item["name"] for item in trip["pois"]})
        names.update({item["leg_id"]: item["travel_mode"] for item in trip["transport_legs"]})
        all_claims.extend(_claim_details(trip, [claim["claim_id"] for claim in trip["claims"]], names))
        all_unknowns.extend({"id": "%s:%d" % (trip["trip_id"], index),
                             "segment_index": segment_index, "field_path": item["field_path"],
                             "reason": item["reason"], "provider": item.get("provider") or "未提供"}
                            for index, item in enumerate(trip["unknowns"]))
        for day in trip["days"]:
            if route[-1] != day["city"]:
                route.append(day["city"])
        for health in trip["provider_health"]:
            if health["status"] != "ready":
                providers.append({"provider": health["provider"], "status": health["status"], "reason": health["reason"], "segment_index": segment_index})
    starts = [slot["start"] for day in days for slot in day["slots"] if slot["effective"] and slot["kind"] != "free"]
    ends = [slot["end"] for day in days for slot in day["slots"] if slot["effective"] and slot["kind"] != "free"]
    axis_start = min([360] + starts)
    axis_end = max([1380] + ends)
    ledger = source.get("budget_ledger") or {}
    cost_range = ledger.get("total_range_cny") or {}
    return {
        "kind": "journey" if is_journey else "trip",
        "title": " → ".join(route), "route": route,
        "start_date": start, "end_date": end,
        "travelers": travelers,
        "days": days,
        "axis": {"start": axis_start, "end": axis_end},
        "budget": {"limit": ledger.get("budget_cny"), "known": ledger.get("known_cost_cny"), "minimum": cost_range.get("minimum"),
                   "maximum": cost_range.get("maximum"), "status": ledger.get("status", "incomplete")},
        "unknown_total": sum(len(trip["unknowns"]) for trip in trips),
        "all_unknowns": all_unknowns,
        "all_claims": all_claims,
        "risk_total": risk_total,
        "risk_items": [{"id": item["item_id"], "kind": item["kind"], "segment_index": item["trip_index"],
                        "name": item["source_name"], "reason": item["reason"], "deadline": item["deadline"],
                        "status": item.get("status")} for item in risks],
        "checklist": [{"id": item["item_id"], "kind": item["kind"], "segment_index": item["trip_index"],
                       "name": item["source_name"], "reason": item["reason"], "deadline": item["deadline"],
                       "deadline_kind": item["deadline_kind"]} for item in checklist],
        "degraded_providers": providers,
        "source_sha256": hashlib.sha256(canonical_json(source).encode("utf-8")).hexdigest(),
        "model_version": 1,
    }
