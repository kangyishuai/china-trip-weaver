"""Pure nearby-dining rules: meal slot classification, anchor point, and AMap option selection."""

from __future__ import annotations

import urllib.parse
from datetime import datetime
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple


_LUNCH_WORD = "午餐"
_DINNER_WORD = "晚餐"
_LUNCH_HOUR_CUTOFF = 15
_LODGING_ANCHOR_KINDS = ("checkin", "checkout", "rest", "lodging")
_DEFAULT_KEYWORDS = "餐厅"
_DINING_TYPES = "050100|050200|050400"
_PAGE_SIZE = 10
_SORTRULE = "weight"
_AVOID_FIELDS = ("tag", "keytag", "rectag")
_SEGMENT_SEPARATOR = " · "


def meal_type_for(slot: Mapping[str, Any]) -> Optional[str]:
    """Classify a slot as "lunch"/"dinner" for dining-anchor purposes, or None otherwise.

    A `meal` slot is classified by wording in its title first, falling back to
    `start_at` hour (before 15:00 is lunch) only when the title carries neither
    word. A `free` or `rest` slot is classified only when its title carries the
    wording; an unworded `free`/`rest` slot (e.g. a plain rest break) is not a
    meal. Every other kind is never a meal.
    """

    kind = slot.get("kind")
    title = str(slot.get("title", ""))
    if kind == "meal":
        worded = _worded_meal_type(title)
        if worded is not None:
            return worded
        return "lunch" if _start_hour(slot) < _LUNCH_HOUR_CUTOFF else "dinner"
    if kind in ("free", "rest"):
        return _worded_meal_type(title)
    return None


def _worded_meal_type(title: str) -> Optional[str]:
    if _DINNER_WORD in title:
        return "dinner"
    if _LUNCH_WORD in title:
        return "lunch"
    return None


def _start_hour(slot: Mapping[str, Any]) -> int:
    return datetime.fromisoformat(slot["start_at"]).hour


def meal_slots(trip: Mapping[str, Any]) -> List[Tuple[int, int, str]]:
    """Every (day_index, slot_index, meal_type) whose slot is a lunch/dinner slot."""

    results: List[Tuple[int, int, str]] = []
    for day_index, day in enumerate(trip["days"]):
        for slot_index, slot in enumerate(day["slots"]):
            meal_type = meal_type_for(slot)
            if meal_type is not None:
                results.append((day_index, slot_index, meal_type))
    return results


def anchor_for(trip: Mapping[str, Any], day_index: int, slot_index: int) -> Optional[Dict[str, Any]]:
    """The nearest same-day slot with known coordinates: backward first, then forward.

    Only a `poi` slot (via `pois[ref].coordinates`) or a `checkin`/`checkout`/
    `rest`/`lodging` slot (via `lodgings[ref].coordinates`) can anchor a meal; a
    `meal` slot's own placeholder POI is never itself an anchor. A `transport`
    slot bounds the search both ways: a meal after a transfer is eaten in the
    arrival city, so nothing before the transfer may anchor it, and a meal
    before one is eaten in the departure city. Returns None when no such slot
    with a known `gcj02` point lies on the meal's side of every transfer.
    """

    slots = trip["days"][day_index]["slots"]
    for index in _search_order(slots, slot_index):
        anchor = _anchor_from_slot(trip, slots[index])
        if anchor is not None:
            return anchor
    return None


def _search_order(slots: Sequence[Mapping[str, Any]], slot_index: int) -> Iterator[int]:
    for index in range(slot_index - 1, -1, -1):
        if slots[index].get("kind") == "transport":
            break
        yield index
    for index in range(slot_index + 1, len(slots)):
        if slots[index].get("kind") == "transport":
            break
        yield index


def _anchor_from_slot(trip: Mapping[str, Any], slot: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    ref_id = slot.get("ref_id")
    if not ref_id:
        return None
    kind = slot.get("kind")
    if kind == "poi":
        entity = _find_by_id(trip["pois"], "poi_id", ref_id)
    elif kind in _LODGING_ANCHOR_KINDS:
        entity = _find_by_id(trip["lodgings"], "lodging_id", ref_id)
    else:
        return None
    if entity is None:
        return None
    point = _gcj02_point(entity.get("coordinates"))
    if point is None:
        return None
    return {"ref_id": ref_id, "name": entity["name"], "lng": point["lng"], "lat": point["lat"]}


def _find_by_id(entities: Sequence[Mapping[str, Any]], id_key: str, ref_id: str) -> Optional[Mapping[str, Any]]:
    for entity in entities:
        if entity.get(id_key) == ref_id:
            return entity
    return None


def _gcj02_point(coordinates: Optional[Mapping[str, Any]]) -> Optional[Mapping[str, float]]:
    if not coordinates:
        return None
    return coordinates.get("gcj02")


def query_parameters(
    anchor: Mapping[str, Any], radius_m: int = 1500, cuisine: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "location": _format_point(anchor["lng"], anchor["lat"]),
        "keywords": cuisine or _DEFAULT_KEYWORDS,
        "types": _DINING_TYPES,
        "radius": radius_m,
        "page_size": _PAGE_SIZE,
        "sortrule": _SORTRULE,
    }


def select_options(
    items: Sequence[Mapping[str, Any]],
    claims: Sequence[Mapping[str, Any]],
    avoid: Sequence[str] = (),
    limit: int = 3,
) -> List[Dict[str, Any]]:
    """The first `limit` rated, non-avoided items, in `items` order.

    `claims` supplies each item's `/provider_identity` claim (matched via the
    item's own `claim_ids`); `claim["value"]["business"]` is the commercial
    info an item is judged on. An item without a `rating`, or whose name/tag/
    keytag/rectag contains any `avoid` word, is skipped without counting
    against `limit`.
    """

    identity_by_claim_id = {
        claim["claim_id"]: claim for claim in claims if claim.get("field_path") == "/provider_identity"
    }
    options: List[Dict[str, Any]] = []
    for item in items:
        if len(options) >= limit:
            break
        identity_claim = _identity_claim_for(item, identity_by_claim_id)
        if identity_claim is None:
            continue
        business = identity_claim["value"].get("business") or {}
        if not business.get("rating"):
            continue
        if _matches_avoid(item["name"], business, avoid):
            continue
        options.append(option_from(item, identity_claim))
    return options


def _identity_claim_for(
    item: Mapping[str, Any], identity_by_claim_id: Mapping[str, Mapping[str, Any]],
) -> Optional[Mapping[str, Any]]:
    for claim_id in item.get("claim_ids", ()):
        claim = identity_by_claim_id.get(claim_id)
        if claim is not None:
            return claim
    return None


def _matches_avoid(name: str, business: Mapping[str, Any], avoid: Sequence[str]) -> bool:
    if not avoid:
        return False
    texts = [name]
    for field in _AVOID_FIELDS:
        value = business.get(field)
        if value:
            texts.append(str(value))
    haystack = " ".join(texts)
    return any(word in haystack for word in avoid)


def option_from(item: Mapping[str, Any], identity_claim: Mapping[str, Any]) -> Dict[str, Any]:
    identity = identity_claim["value"]
    business = identity.get("business") or {}
    provider_poi_id = identity["provider_poi_id"]
    return {
        "provider_poi_id": provider_poi_id,
        "name": item["name"],
        "cuisine": business.get("keytag") or None,
        "tag": business.get("tag") or None,
        "rating": business.get("rating"),
        "cost_cny": _cost_cny(business),
        "distance_m": int(round(float(item["distance_meters"]))),
        "opentime_today": business.get("opentime_today") or None,
        "address": identity.get("formatted_address") or None,
        "deep_links": [_marker_deep_link(item), _amap_poi_link(provider_poi_id)],
        "claim_id": identity_claim["claim_id"],
    }


def _cost_cny(business: Mapping[str, Any]) -> Optional[float]:
    raw = business.get("cost")
    if raw in (None, ""):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _marker_deep_link(item: Mapping[str, Any]) -> str:
    point = item["coordinates"]["gcj02"]
    position = _format_point(point["lng"], point["lat"])
    name = urllib.parse.quote(item["name"])
    return (
        "https://uri.amap.com/marker?position=%s&name=%s&src=china-trip-weaver"
        "&coordinate=gaode&callnative=1" % (position, name)
    )


def _amap_poi_link(provider_poi_id: str) -> str:
    return "https://www.amap.com/search?" + urllib.parse.urlencode({"id": provider_poi_id})


def _format_point(lng: float, lat: float) -> str:
    return "%.6f,%.6f" % (lng, lat)


def search_url(anchor: Mapping[str, Any]) -> str:
    center = _format_point(anchor["lng"], anchor["lat"])
    return (
        "https://uri.amap.com/search?keyword=美食&center=%s&view=list"
        "&src=china-trip-weaver&callnative=1" % center
    )


def format_option(option: Mapping[str, Any]) -> str:
    segments = [option["name"]]
    if option.get("cuisine"):
        segments.append(option["cuisine"])
    if option.get("rating"):
        segments.append("评分 %s" % option["rating"])
    if option.get("cost_cny") is not None:
        segments.append("人均 ¥%s" % ("%g" % option["cost_cny"]))
    if option.get("distance_m") is not None:
        segments.append("距 %d m" % option["distance_m"])
    if option.get("opentime_today"):
        segments.append("今日 %s" % option["opentime_today"])
    return _SEGMENT_SEPARATOR.join(segments)
