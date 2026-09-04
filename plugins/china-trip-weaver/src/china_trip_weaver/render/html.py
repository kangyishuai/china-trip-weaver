"""Trip -> deterministic, phone-first, single-file HTML."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from ..validate_trip import validate_trip
from .template import CSP, RENDERER_VERSION, attr, dom_id, embedded_json, external_link, renderer_css, text


class RendererError(ValueError):
    pass


ENUM_LABELS: Mapping[str, Mapping[str, Mapping[str, str]]] = {
    "en": {
        "mode": {"live": "Live query", "cached": "Saved query", "static": "Reference material", "mock": "Demo data"},
        "pace": {"slow": "Relaxed", "balanced": "Balanced", "full": "Full"},
        "kind": {
            "poi": "Place", "meal": "Meal", "lodging": "Stay", "transport": "Transport",
            "rest": "Rest", "free": "Open time", "checkin": "Check-in", "checkout": "Check-out",
        },
        "slot_status": {"scheduled": "Selected", "tentative": "Alternative", "skipped": "Not included", "unknown": "Unknown"},
        "selection": {"selected": "Selected", "alternative": "Alternative", "skipped": "Not included", "unknown": "Unknown"},
        "travel_mode": {
            "rail": "Train", "flight": "Flight", "walk": "Walk", "transit": "Public transit",
            "drive": "Drive", "ride": "Cycling", "taxi": "Taxi", "bus": "Bus", "ferry": "Ferry",
        },
        "claim_status": {
            "verified": "Verified", "partial": "Partially verified", "hypothesis": "Working assumption",
            "unknown": "Unknown", "stale": "Needs refresh", "conflict": "Sources conflict",
            "unavailable": "Unavailable", "mock": "Demo only",
        },
        "health_status": {
            "ready": "Available", "missing": "Not configured", "expired": "Expired",
            "forbidden": "Access denied", "rate_limited": "Rate limited", "degraded": "Limited",
            "unavailable": "Unavailable", "contract_mismatch": "Interface changed",
        },
        "price_type": {
            "live": "Current quote", "reference": "Reference price", "estimate": "Estimate",
            "verify-on-click": "Verify on official page", "unknown": "Unknown price",
        },
        "price_unit": {
            "total": "total", "per_person": "per person", "per_night": "per night", "from": "starting from",
        },
    },
    "zh-CN": {
        "mode": {"live": "实时查询", "cached": "已缓存查询", "static": "静态参考资料", "mock": "演示数据"},
        "pace": {"slow": "舒缓", "balanced": "适中", "full": "充实"},
        "kind": {
            "poi": "景点", "meal": "用餐", "lodging": "住宿", "transport": "交通",
            "rest": "休息", "free": "自由安排", "checkin": "办理入住", "checkout": "办理退房",
        },
        "slot_status": {"scheduled": "已选", "tentative": "备选", "skipped": "未采用", "unknown": "未知"},
        "selection": {"selected": "已选", "alternative": "备选", "skipped": "未采用", "unknown": "未知"},
        "travel_mode": {
            "rail": "铁路", "flight": "航班", "walk": "步行", "transit": "公共交通",
            "drive": "驾车", "ride": "骑行", "taxi": "出租车", "bus": "巴士", "ferry": "轮渡",
        },
        "claim_status": {
            "verified": "已核验", "partial": "部分核验", "hypothesis": "待证假设", "unknown": "未知",
            "stale": "需要更新", "conflict": "来源冲突", "unavailable": "暂不可用", "mock": "仅演示",
        },
        "health_status": {
            "ready": "可用", "missing": "未配置", "expired": "已过期", "forbidden": "无访问权限",
            "rate_limited": "已限流", "degraded": "能力受限", "unavailable": "暂不可用",
            "contract_mismatch": "接口已变化",
        },
        "price_type": {
            "live": "当前报价", "reference": "参考价", "estimate": "估算价",
            "verify-on-click": "请在官方页面核验", "unknown": "价格未知",
        },
        "price_unit": {"total": "总计", "per_person": "每人", "per_night": "每晚", "from": "起价"},
    },
}


PROVIDER_LABELS: Mapping[str, Mapping[str, str]] = {
    "en": {
        "amap": "Amap", "flyai": "Fliggy", "variflight": "VariFlight", "12306-mcp": "China Railway 12306",
        "12306-deep-link": "China Railway 12306 official page", "flyai-deep-link": "Fliggy official page",
        "official-web": "Official website", "host-web": "Host web search", "anysearch": "AnySearch",
        "user-pasted-only": "User-provided material",
    },
    "zh-CN": {
        "amap": "高德地图", "flyai": "飞猪", "variflight": "飞常准", "12306-mcp": "中国铁路 12306",
        "12306-deep-link": "中国铁路 12306 官方页面", "flyai-deep-link": "飞猪官方页面",
        "official-web": "官方网站", "host-web": "宿主网络搜索", "anysearch": "AnySearch",
        "user-pasted-only": "用户提供的资料",
    },
}


HEALTH_RISK_ORDER = {
    "contract_mismatch": 8, "forbidden": 7, "expired": 6, "rate_limited": 5,
    "unavailable": 4, "missing": 3, "degraded": 2, "ready": 1,
}

CLAIM_RISK_ORDER = {
    "conflict": 8, "unavailable": 7, "unknown": 6, "stale": 5,
    "hypothesis": 4, "partial": 3, "mock": 2, "verified": 1,
}

READABILITY_CSS = """
.evidence-card > summary {
  align-items: center;
  cursor: pointer;
  display: flex;
  min-height: 44px;
  padding-block: 0.45rem;
}
.location-group + .location-group { margin-top: 1.5rem; }
.location-group h4 { font-size: 1.05rem; line-height: 1.2; margin: 0; }
@media print {
  details:not([open]) > :not(summary) { display: block; }
}
""".strip()

HEALTH_REASON_LABELS = {
    "zh-CN": {
        "contract probe passed": "接口检查通过",
        "property deep links available; room total unverified": "可提供住宿链接；房间总价尚未核验",
        "network unavailable; emitted official deep link only": "网络不可用；仅提供官方页面链接",
        "AMAP_WEBSERVICE_KEY is not configured": "未配置高德地图查询能力",
    },
}


def safe_output_name(trip_id: str) -> str:
    cleaned = re.sub(r"[^a-z0-9-]+", "-", trip_id.lower()).strip("-")
    if not cleaned:
        raise RendererError("trip_id cannot produce a safe filename")
    return cleaned[:64] + ".html"


def _request_traveler_count(request: Mapping[str, Any]) -> int:
    groups = request.get("traveler_groups")
    if groups:
        return sum(int(group["travelers"]) for group in groups)
    return int(request["travelers"])


def _request_origin_summary(request: Mapping[str, Any], labels: Mapping[str, str]) -> str:
    groups = request.get("traveler_groups")
    if groups:
        if labels["locale"] == "zh-CN":
            return "、".join(
                "%s（%d 人）" % (group["origin"]["name"], group["travelers"])
                for group in groups
            )
        return ", ".join(
            "%s (%d %s)" % (
                group["origin"]["name"],
                group["travelers"],
                "traveler" if group["travelers"] == 1 else "travelers",
            )
            for group in groups
        )
    origin = request.get("origin")
    return origin["name"] if origin else labels["none"]


def _request_places(request: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    places: List[Mapping[str, Any]] = []
    if request.get("origin"):
        places.append(request["origin"])
    places.extend(group["origin"] for group in (request.get("traveler_groups") or ()))
    if request.get("meeting_anchor"):
        places.append(request["meeting_anchor"]["location"])
    places.extend(request["destinations"])
    return places


def render_trip(trip: Mapping[str, Any], renderer_version: str = RENDERER_VERSION) -> str:
    if renderer_version != RENDERER_VERSION:
        raise RendererError("unsupported renderer version")
    report = validate_trip(trip)
    if not report.ok:
        raise RendererError("Trip is not validated: " + "; ".join(issue.render() for issue in report.errors))
    try:
        return _render(trip)
    except ValueError as exc:
        raise RendererError(str(exc)) from exc


def _render(trip: Mapping[str, Any]) -> str:
    locale = trip["request"]["locale"]
    labels = _labels(locale)
    destinations = " → ".join(item["name"] for item in trip["request"]["destinations"])
    title_value = "%s · %s — %s" % (destinations, trip["request"]["start_date"], trip["request"]["end_date"])
    claim_map = {claim["claim_id"]: claim for claim in trip["claims"]}
    reference_names = _reference_names(trip, labels)
    selection_states = _selection_states(trip)
    unknown_refs = _unknown_refs(trip)
    lines = [
        "<!doctype html>",
        '<html lang="%s">' % attr(locale),
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta http-equiv="Content-Security-Policy" content="%s">' % attr(CSP),
        "<title>%s</title>" % text(title_value),
        '<style id="renderer-css">%s\n%s</style>' % (renderer_css(), READABILITY_CSS),
        "</head>",
        "<body>",
        '<a class="skip-link" href="#main-content">%s</a>' % text(labels["skip"]),
        '<header class="page-header" data-section="header">',
        '<p class="eyebrow">China Trip Weaver · v%s</p>' % RENDERER_VERSION,
        "<h1>%s</h1>" % text(title_value),
        '<div class="header-meta"><span>%s %s</span><span>%s %s</span><span>%s %s</span><span class="mode-badge" data-trip-mode="%s">%s: %s</span></div>' % (
            text(labels["travelers"]), text(_request_traveler_count(trip["request"])),
            text(labels["revision"]), text(trip["revision"]["number"]),
            text(labels["generated"]), _time(trip["generated_at"]),
            attr(trip["mode"]), text(labels["mode"]), text(_enum_label(labels, "mode", trip["mode"])),
        ),
        "</header>",
        _truth_banner(trip, labels),
        _day_nav(trip, labels),
        '<main id="main-content">',
        _unknowns_section(trip, reference_names, labels),
        _request_section(trip, labels),
        _health_section(trip, labels),
        _transport_section(trip, claim_map, reference_names, selection_states, unknown_refs, labels),
        _lodging_section(trip, claim_map, selection_states, unknown_refs, labels),
        _days_section(trip, claim_map, labels),
        _location_section(trip, claim_map, selection_states, unknown_refs, labels),
        _evidence_section(trip, reference_names, labels),
        "</main>",
        _footer(trip, labels),
        '<script id="trip-data" type="application/json">%s</script>' % embedded_json(trip),
        "</body>",
        "</html>",
    ]
    return "\n".join(lines) + "\n"


def _labels(locale: str) -> Mapping[str, str]:
    if locale == "en":
        return {
            "locale": "en",
            "skip": "Skip to itinerary", "travelers": "Travelers", "revision": "Revision",
            "generated": "Generated", "mode": "Data mode", "truth": "Truth and limits", "request": "Trip request",
            "transport": "Transport", "lodging": "Lodging", "days": "Daily itinerary",
            "locations": "Location overview", "unknowns": "Alternatives and unknowns",
            "evidence": "Evidence", "health": "Data-source status", "none": "None provided",
            "readonly": "Read-only planning only", "source": "Open source", "price_unknown": "Price unknown",
            "origin": "Origin", "destinations": "Destinations", "dates": "Dates", "budget": "Budget",
            "interests": "Interests", "pace": "Pace", "constraints": "Constraints", "assumptions": "Assumptions",
            "provider": "Provider", "version": "Version", "status": "Status", "checked": "Checked", "reason": "Reason",
            "minutes": "min", "official_page": "Open official page (read-only)", "lodging_link": "Open stay page",
            "locked": "Kept fixed", "selection": "Itinerary choice", "has_unknown": "Has unknown details",
            "unknown_place": "Unresolved place", "location_unverified": "Location not verified; no default point was added.",
            "location_note": "Visit-order sketch, not a road route; %s coordinates show relative position only.",
            "location_title": "Location sequence for %s", "location_desc": "Not a real road route; numbers match the places below.",
            "unknown_item": "Detail to verify", "claim_evidence": "Supporting evidence", "no_claim": "No linked evidence",
            "confidence": "Confidence", "queried": "Checked", "field": "Detail", "mock": "Demo",
            "boundary": "No login, identity submission, booking, payment, cancellation, or changes.",
            "schema": "schema", "renderer": "renderer", "current_revision": "revision",
            "day_label": "Day %d", "footer_notice": "This page only compares information and links to official pages; inventory, prices, punctuality, and opening status are not guaranteed.",
            "unknown_reason": "Available evidence does not confirm %s; verify it for the trip dates on the official page.",
            "health_reason": "Status: %s. Technical detail is preserved in the page data.",
        }
    return {
        "locale": "zh-CN",
        "skip": "跳到行程正文", "travelers": "人数", "revision": "修订", "generated": "生成于", "mode": "数据口径",
        "truth": "真实性与边界", "request": "行程需求", "transport": "交通摘要",
        "lodging": "住宿摘要", "days": "逐日行程", "locations": "位置概览",
        "unknowns": "备选与未知项", "evidence": "证据", "health": "数据源状态",
        "none": "无 / 未提供", "readonly": "仅提供只读规划", "source": "查看来源",
        "price_unknown": "价格未知 / 点击核验",
        "origin": "出发地", "destinations": "目的地", "dates": "日期", "budget": "预算",
        "interests": "兴趣", "pace": "节奏", "constraints": "硬约束", "assumptions": "默认假设",
        "provider": "数据源", "version": "版本", "status": "状态", "checked": "检查时间", "reason": "原因",
        "minutes": "分钟", "official_page": "打开官方页面（只读）", "lodging_link": "打开住宿页面",
        "locked": "保持不变", "selection": "行程选择", "has_unknown": "含待核验信息",
        "unknown_place": "地点尚未解析", "location_unverified": "位置未核验；未放置默认点。",
        "location_note": "游览顺序示意，非道路路线；%s 坐标仅用于相对位置。",
        "location_title": "%s位置顺序示意", "location_desc": "非真实道路路线；编号对应下方地点。",
        "unknown_item": "待核验信息", "claim_evidence": "关联证据", "no_claim": "无关联证据",
        "confidence": "可信度", "queried": "查询于", "field": "核验项", "mock": "演示",
        "boundary": "不登录、不实名、不代下单、不支付、不退改。",
        "schema": "数据结构", "renderer": "页面模板", "current_revision": "当前修订",
        "day_label": "第 %d 天", "footer_notice": "本页只做查询、比较和官方深链；不保证库存、价格、准点或开放状态。",
        "unknown_reason": "现有资料不足以确认“%s”；请按行程日期在官方页面复核。",
        "health_reason": "当前状态为“%s”；技术详情已保留在页面数据中。",
    }


def _enum_label(labels: Mapping[str, str], group: str, value: str) -> str:
    localized = ENUM_LABELS[labels["locale"]].get(group, {})
    return localized.get(value, value.replace("_", " "))


def _provider_label(labels: Mapping[str, str], provider: Optional[str]) -> str:
    if not provider:
        return labels["none"]
    return PROVIDER_LABELS[labels["locale"]].get(provider, provider)


def _health_reason(health: Mapping[str, Any], labels: Mapping[str, str]) -> str:
    reason = health["reason"]
    if labels["locale"] == "en" and not re.search(r"[\u3400-\u9fff]", reason):
        return reason
    if labels["locale"] == "zh-CN" and re.search(r"[\u3400-\u9fff]", reason):
        return reason
    known = HEALTH_REASON_LABELS.get(labels["locale"], {}).get(reason)
    if known:
        return known
    return labels["health_reason"] % _enum_label(labels, "health_status", health["status"])


def _reference_names(trip: Mapping[str, Any], labels: Mapping[str, str]) -> Mapping[str, str]:
    names: Dict[str, str] = {}
    request = trip["request"]
    for place in _request_places(request):
        names[place["ref_id"]] = place["name"]
    for lodging in trip["lodgings"]:
        names[lodging["lodging_id"]] = lodging["name"]
    for poi in trip["pois"]:
        names[poi["poi_id"]] = poi["name"]
    for leg in trip["transport_legs"]:
        origin = names.get(leg["from_ref"], labels["unknown_place"])
        destination = names.get(leg["to_ref"], labels["unknown_place"])
        names[leg["leg_id"]] = "%s → %s" % (origin, destination)
    return names


def _reference_name(reference: str, names: Mapping[str, str], labels: Mapping[str, str]) -> str:
    return names.get(reference, labels["unknown_place"])


def _selection_states(trip: Mapping[str, Any]) -> Mapping[str, str]:
    states: Dict[str, str] = {}
    priority = {"skipped": 1, "alternative": 2, "unknown": 3, "selected": 4}

    def assign(reference: Optional[str], state: str) -> None:
        if reference and priority[state] > priority.get(states.get(reference, ""), 0):
            states[reference] = state

    for group, key in ((trip["transport_legs"], "leg_id"), (trip["lodgings"], "lodging_id"), (trip["pois"], "poi_id")):
        for item in group:
            assign(item[key], "alternative")
    for lodging in trip["lodgings"]:
        if lodging.get("selection_status") == "selected":
            assign(lodging["lodging_id"], "selected")
    slot_states = {"scheduled": "selected", "tentative": "alternative", "skipped": "skipped", "unknown": "unknown"}
    for day in trip["days"]:
        assign(day.get("stay_id"), "selected")
        for slot in day["slots"]:
            assign(slot["ref_id"], slot_states[slot["status"]])
    return states


def _unknown_refs(trip: Mapping[str, Any]) -> Set[str]:
    result: Set[str] = set()
    groups = {
        "transport_legs": (trip["transport_legs"], "leg_id"),
        "lodgings": (trip["lodgings"], "lodging_id"),
        "pois": (trip["pois"], "poi_id"),
    }
    for unknown in trip["unknowns"]:
        parts = _pointer_parts(unknown["field_path"])
        if len(parts) < 2 or parts[0] not in groups or not parts[1].isdigit():
            continue
        items, key = groups[parts[0]]
        index = int(parts[1])
        if index < len(items):
            result.add(items[index][key])
    return result


def _pointer_parts(pointer: str) -> List[str]:
    return [part.replace("~1", "/").replace("~0", "~") for part in pointer.lstrip("/").split("/") if part]


FIELD_LABELS = {
    "en": {
        "price": "Price", "amount": "Amount", "service_number": "Service number",
        "depart_at": "Departure time", "arrive_at": "Arrival time", "duration_minutes": "Travel time",
        "coordinates": "Location", "opening_windows": "Opening hours", "status": "Status",
        "check_in": "Check-in", "check_out": "Check-out", "selection_status": "Selection",
    },
    "zh-CN": {
        "price": "价格", "amount": "金额", "service_number": "车次或航班号",
        "depart_at": "出发时间", "arrive_at": "到达时间", "duration_minutes": "行程时长",
        "coordinates": "位置", "opening_windows": "开放时间", "status": "状态",
        "check_in": "入住日期", "check_out": "退房日期", "selection_status": "选择状态",
    },
}


def _field_label(pointer: str, labels: Mapping[str, str]) -> str:
    fields = FIELD_LABELS[labels["locale"]]
    parts = [part for part in _pointer_parts(pointer) if not part.isdigit()]
    translated = [fields[part] for part in parts if part in fields]
    if translated:
        return " / ".join(translated)
    return labels["unknown_item"]


def _unknown_label(unknown: Mapping[str, Any], trip: Mapping[str, Any], names: Mapping[str, str], labels: Mapping[str, str]) -> str:
    parts = _pointer_parts(unknown["field_path"])
    groups = {
        "transport_legs": (trip["transport_legs"], "leg_id"),
        "lodgings": (trip["lodgings"], "lodging_id"),
        "pois": (trip["pois"], "poi_id"),
    }
    if len(parts) >= 2 and parts[0] in groups and parts[1].isdigit():
        items, key = groups[parts[0]]
        index = int(parts[1])
        if index < len(items):
            entity = items[index]
            return "%s · %s" % (_reference_name(entity[key], names, labels), _field_label("/".join(parts[2:]), labels))
    if len(parts) >= 2 and parts[0] == "days" and parts[1].isdigit():
        day_index = int(parts[1])
        if day_index < len(trip["days"]):
            return "%s · %s" % (trip["days"][day_index]["date"], _field_label("/".join(parts[2:]), labels))
    return labels["unknown_item"]


def _selection_badge(state: str, labels: Mapping[str, str]) -> str:
    return '<span class="status-badge" data-selection-state="%s">%s</span>' % (
        attr(state), text(_enum_label(labels, "selection", state)),
    )


def _entity_badges(reference: str, states: Mapping[str, str], unknown_refs: Set[str], labels: Mapping[str, str]) -> str:
    badges = [_selection_badge(states.get(reference, "alternative"), labels)]
    if reference in unknown_refs:
        badges.append('<span class="lock-badge" data-unknown-state="true">%s</span>' % text(labels["has_unknown"]))
    return '<div class="badge-row" aria-label="%s">%s</div>' % (text(labels["selection"]), "".join(badges))


def _truth_banner(trip: Mapping[str, Any], labels: Mapping[str, str]) -> str:
    worst = max(trip["provider_health"], key=lambda item: (HEALTH_RISK_ORDER.get(item["status"], 99), item["provider"]))
    notice = ""
    if trip["mode"] == "mock":
        notice = "<p><strong>%s:</strong> %s</p>" % (text(labels["mock"]), text(trip["mock_notice"]))
    return (
        '<aside class="truth-banner" data-section="truth-banner" aria-labelledby="truth-heading">'
        '<p><strong id="truth-heading">%s</strong><br>%s %s · %s %s</p>'
        '<p data-worst-provider="%s" data-health-status="%s"><strong>%s:</strong><br>%s · %s</p>'
        '<p><strong>%s:</strong><br>%d · %s</p>%s'
        "</aside>"
    ) % (
        text(labels["truth"]), text(labels["mode"]), text(_enum_label(labels, "mode", trip["mode"])), text(labels["generated"]), _time(trip["generated_at"]),
        attr(worst["provider"]), attr(worst["status"]), text(labels["provider"]), text(_provider_label(labels, worst["provider"])),
        text(_enum_label(labels, "health_status", worst["status"])), text(labels["unknowns"]), len(trip["unknowns"]),
        text(labels["boundary"]), notice,
    )


def _day_nav(trip: Mapping[str, Any], labels: Mapping[str, str]) -> str:
    items = "".join(
        '<li><a href="#%s">%s · %s</a></li>' % (
            dom_id("day", day["day_id"]), text(labels["day_label"] % (index + 1)), text(day["date"]),
        )
        for index, day in enumerate(trip["days"])
    )
    return '<nav class="day-nav" data-section="day-nav" aria-label="%s"><ul>%s</ul></nav>' % (text(labels["days"]), items)


def _request_section(trip: Mapping[str, Any], labels: Mapping[str, str]) -> str:
    request = trip["request"]
    origin = _request_origin_summary(request, labels)
    budget = ("CNY " + _number(request["budget_cny"])) if request["budget_cny"] is not None else labels["price_unknown"]
    return (
        '<section class="panel" id="request-summary" data-section="request-summary" aria-labelledby="request-heading">'
        '<h2 id="request-heading">%s</h2><dl>'
        '<dt>%s</dt><dd>%s</dd><dt>%s</dt><dd>%s</dd>'
        '<dt>%s</dt><dd>%s — %s</dd><dt>%s</dt><dd>%s</dd>'
        '<dt>%s</dt><dd>%s</dd><dt>%s</dt><dd>%s</dd>'
        '<dt>%s</dt><dd>%s</dd><dt>%s</dt><dd>%s</dd>'
        "</dl></section>"
    ) % (
        text(labels["request"]), text(labels["origin"]), text(origin), text(labels["destinations"]), text("、".join(item["name"] for item in request["destinations"])),
        text(labels["dates"]), text(request["start_date"]), text(request["end_date"]), text(labels["budget"]), text(budget),
        text(labels["interests"]), _list_text(request["interests"], labels), text(labels["pace"]), text(_enum_label(labels, "pace", request["pace"])),
        text(labels["constraints"]), _list_text(request["constraints"], labels), text(labels["assumptions"]), _list_text(request["assumptions"], labels),
    )


def _transport_section(
    trip: Mapping[str, Any],
    claims: Mapping[str, Any],
    names: Mapping[str, str],
    states: Mapping[str, str],
    unknown_refs: Set[str],
    labels: Mapping[str, str],
) -> str:
    cards = []
    for leg in trip["transport_legs"]:
        service = leg["service_number"] or labels["none"]
        links = external_link(leg["booking_url"], labels["official_page"]) if leg["booking_url"] else text(labels["none"])
        cards.append(
            '<article class="entity-card" data-entity-id="%s" data-entity-kind="transport" data-travel-mode="%s" '
            'data-service-number="%s" data-from-ref="%s" data-to-ref="%s">'
            '<h3>%s · %s</h3>%s<p>%s → %s</p><p>%s — %s · %s %s</p>'
            '%s<p>%s</p>%s</article>' % (
                attr(leg["leg_id"]), attr(leg["travel_mode"]), attr(leg["service_number"] or ""),
                attr(leg["from_ref"]), attr(leg["to_ref"]),
                text(_enum_label(labels, "travel_mode", leg["travel_mode"])), text(service),
                _entity_badges(leg["leg_id"], states, unknown_refs, labels),
                text(_reference_name(leg["from_ref"], names, labels)), text(_reference_name(leg["to_ref"], names, labels)),
                _time_or_unknown(leg["depart_at"], labels), _time_or_unknown(leg["arrive_at"], labels),
                text(leg["duration_minutes"] if leg["duration_minutes"] is not None else labels["none"]), text(labels["minutes"]),
                _price(leg["price"], leg["leg_id"], labels), links, _claim_links(leg["claim_ids"], claims, labels),
            )
        )
    return _section("transport-summary", labels["transport"], "".join(cards) or _empty(labels), "panel")


def _lodging_section(
    trip: Mapping[str, Any],
    claims: Mapping[str, Any],
    states: Mapping[str, str],
    unknown_refs: Set[str],
    labels: Mapping[str, str],
) -> str:
    cards = []
    for lodging in trip["lodgings"]:
        links = " · ".join(external_link(url, labels["lodging_link"]) for url in lodging["deep_links"]) or text(labels["none"])
        cards.append(
            '<article class="entity-card" data-entity-id="%s" data-entity-kind="lodging"><h3>%s</h3>'
            '%s<p>%s · %s</p><p>%s — %s</p>%s<p>%s</p>%s</article>' % (
                attr(lodging["lodging_id"]), text(lodging["name"]),
                _entity_badges(lodging["lodging_id"], states, unknown_refs, labels), text(lodging["city"]), text(lodging["area"]),
                text(lodging["check_in"]), text(lodging["check_out"]), _price(lodging["price"], lodging["lodging_id"], labels),
                links, _claim_links(lodging["claim_ids"], claims, labels),
            )
        )
    return _section("lodging-summary", labels["lodging"], "".join(cards) or _empty(labels), "panel")


def _days_section(trip: Mapping[str, Any], claims: Mapping[str, Any], labels: Mapping[str, str]) -> str:
    days = []
    for index, day in enumerate(trip["days"]):
        slots = []
        for slot in day["slots"]:
            lock = '<span class="lock-badge" data-locked="true">%s</span>' % text(labels["locked"]) if slot["locked"] else ""
            state = {"scheduled": "selected", "tentative": "alternative", "skipped": "skipped", "unknown": "unknown"}[slot["status"]]
            slots.append(
                '<li class="timeline-item" data-slot-id="%s" data-ref-id="%s" data-slot-kind="%s" data-slot-status="%s" '
                'data-start-at="%s" data-end-at="%s">'
                '<span class="slot-time"><time datetime="%s">%s</time>–<time datetime="%s">%s</time></span>'
                '<h3>%s</h3><div class="badge-row"><span class="status-badge" data-kind="%s">%s</span>%s%s</div>%s</li>' % (
                    attr(slot["slot_id"]), attr(slot["ref_id"] or ""), attr(slot["kind"]), attr(slot["status"]),
                    attr(slot["start_at"]), attr(slot["end_at"]),
                    attr(slot["start_at"]), _clock(slot["start_at"]), attr(slot["end_at"]), _clock(slot["end_at"]),
                    text(slot["title"]), attr(slot["kind"]), text(_enum_label(labels, "kind", slot["kind"])),
                    _selection_badge(state, labels), lock, _claim_links(slot["claim_ids"], claims, labels),
                )
            )
        body = '<article class="day-block" id="%s" data-day-id="%s"><h3>%s · %s · %s</h3><ol class="timeline">%s</ol></article>' % (
            dom_id("day", day["day_id"]), attr(day["day_id"]), text(labels["day_label"] % (index + 1)), text(day["date"]), text(day["city"]),
            "".join(slots) or '<li class="empty-state">%s</li>' % text(labels["none"]),
        )
        days.append(body)
    return _section("days", labels["days"], "".join(days), "panel panel-wide")


def _location_section(
    trip: Mapping[str, Any],
    claims: Mapping[str, Any],
    states: Mapping[str, str],
    unknown_refs: Set[str],
    labels: Mapping[str, str],
) -> str:
    entities = [("lodging", item, "lodging_id") for item in trip["lodgings"]] + [("poi", item, "poi_id") for item in trip["pois"]]
    cities: List[str] = []
    for city in [day["city"] for day in trip["days"]] + [item["city"] for _, item, _ in entities]:
        if city not in cities:
            cities.append(city)
    groups = []
    date_separator = ", " if labels["locale"] == "en" else "、"
    for group_index, city in enumerate(cities):
        city_entities = [(kind, item, key) for kind, item, key in entities if item["city"] == city]
        point_candidates = [(kind, item, key) for kind, item, key in city_entities if item["coordinates"]]
        crs = "WGS84" if point_candidates and all(item["coordinates"]["wgs84"] for _, item, _ in point_candidates) else "GCJ02"
        field = "wgs84" if crs == "WGS84" else "gcj02"
        plotted = [(kind, item, key, item["coordinates"][field]) for kind, item, key in point_candidates if item["coordinates"][field]]
        visual = _location_svg(plotted, crs, city, group_index, labels) if plotted else '<p class="empty-state">%s</p>' % text(labels["location_unverified"])
        cards = []
        for kind, item, key in city_entities:
            identifier = item[key]
            links = item.get("deep_links", [])
            link_html = " · ".join(external_link(url, labels["source"]) for url in links) or text(labels["none"])
            coordinate = item["coordinates"]
            coordinate_text = labels["location_unverified"] if not coordinate or not coordinate.get(field) else "%s %.6f, %.6f" % (crs, coordinate[field]["lng"], coordinate[field]["lat"])
            price_html = _price(item.get("price"), identifier, labels) if kind == "poi" else ""
            identity_attrs = 'data-entity-id="%s" data-entity-kind="poi"' % attr(identifier) if kind == "poi" else 'data-location-ref="%s"' % attr(identifier)
            cards.append(
                '<article class="entity-card" %s><h4>%s</h4>%s<p>%s</p>%s<p>%s</p>%s</article>' % (
                    identity_attrs, text(item["name"]), _entity_badges(identifier, states, unknown_refs, labels),
                    text(coordinate_text), price_html, link_html, _claim_links(item["claim_ids"], claims, labels),
                )
            )
        dates = [day["date"] for day in trip["days"] if day["city"] == city]
        heading = "%s · %s" % (city, date_separator.join(dates)) if dates else city
        groups.append(
            '<section class="location-group" data-location-group="%s"><h3>%s</h3>%s%s</section>' % (
                attr(city), text(heading), visual, "".join(cards),
            )
        )
    return _section("location-overview", labels["locations"], "".join(groups), "panel panel-wide")


def _location_svg(
    plotted: Sequence[Tuple[str, Mapping[str, Any], str, Mapping[str, float]]],
    crs: str,
    city: str,
    group_index: int,
    labels: Mapping[str, str],
) -> str:
    lngs = [point[3]["lng"] for point in plotted]
    lats = [point[3]["lat"] for point in plotted]
    min_lng, max_lng = min(lngs), max(lngs)
    min_lat, max_lat = min(lats), max(lats)
    points = []
    markers = []
    for index, (_, item, key, point) in enumerate(plotted, start=1):
        x = 50.0 if max_lng == min_lng else 10 + (point["lng"] - min_lng) / (max_lng - min_lng) * 80
        y = 50.0 if max_lat == min_lat else 90 - (point["lat"] - min_lat) / (max_lat - min_lat) * 80
        points.append("%.3f,%.3f" % (x, y))
        markers.append('<g data-coordinate-ref="%s"><circle cx="%.3f" cy="%.3f" r="3.5"></circle><text x="%.3f" y="%.3f">%d</text></g>' % (attr(item[key]), x, y, x + 4.5, y + 1.5, index))
    line = '<polyline class="route-line" points="%s"></polyline>' % " ".join(points) if len(points) > 1 else ""
    title_id = dom_id("location-map-title", "%s-%d" % (city, group_index))
    desc_id = dom_id("location-map-desc", "%s-%d" % (city, group_index))
    note = '<p class="schematic-note" data-schematic-label="true">%s</p>' % text(labels["location_note"] % crs)
    return (
        '<svg class="location-svg" data-crs="%s" viewBox="0 0 100 100" role="img" aria-labelledby="%s %s">'
        '<title id="%s">%s</title><desc id="%s">%s</desc>%s%s</svg>%s'
    ) % (
        attr(crs), attr(title_id), attr(desc_id), attr(title_id), text(labels["location_title"] % city),
        attr(desc_id), text(labels["location_desc"]), line, "".join(markers), note,
    )


def _unknowns_section(
    trip: Mapping[str, Any],
    names: Mapping[str, str],
    labels: Mapping[str, str],
) -> str:
    cards = []
    for index, unknown in enumerate(trip["unknowns"]):
        field_label = _unknown_label(unknown, trip, names, labels)
        cards.append(
            '<article class="unknown-card" data-unknown-index="%d" data-unknown-path="%s" data-unknown-reason="%s" data-unknown-claim="%s">'
            '<h3>%s</h3><div class="badge-row">%s</div><p>%s</p><p>%s: %s</p></article>' % (
                index, attr(unknown["field_path"]), attr(unknown["reason"]), attr(unknown["claim_id"] or ""),
                text(field_label), _selection_badge("unknown", labels),
                text(labels["unknown_reason"] % field_label), text(labels["provider"]), text(_provider_label(labels, unknown["provider"])),
            )
        )
    return _section("alternatives-and-unknowns", labels["unknowns"], "".join(cards) or _empty(labels), "panel")


def _evidence_section(trip: Mapping[str, Any], names: Mapping[str, str], labels: Mapping[str, str]) -> str:
    items = []
    indexed_claims = enumerate(trip["claims"])
    ordered_claims = sorted(indexed_claims, key=lambda pair: (-CLAIM_RISK_ORDER.get(pair[1]["status"], 99), pair[0]))
    for _, claim in ordered_claims:
        items.append(
            '<details class="entity-card evidence-card" id="%s" data-claim-id="%s" data-subject-ref="%s" '
            'data-claim-status="%s" data-claim-mode="%s"><summary><strong>%s</strong> · %s · %s · %s</summary>'
            '<p>%s %s · %s %d%% · %s %s</p><p>%s</p></details>' % (
                dom_id("claim", claim["claim_id"]), attr(claim["claim_id"]), attr(claim["subject_ref"]),
                attr(claim["status"]), attr(claim["mode"]), text(_provider_label(labels, claim["provider"])),
                text(_enum_label(labels, "claim_status", claim["status"])),
                text(_reference_name(claim["subject_ref"], names, labels)), text(_field_label(claim["field_path"], labels)),
                text(labels["queried"]), _time(claim["queried_at"]), text(labels["confidence"]), int(round(claim["confidence"] * 100)),
                text(labels["mode"]), text(_enum_label(labels, "mode", claim["mode"])),
                external_link(claim["source_url"], labels["source"]),
            )
        )
    return _section("evidence", labels["evidence"], "".join(items) or _empty(labels), "panel panel-wide")


def _health_section(trip: Mapping[str, Any], labels: Mapping[str, str]) -> str:
    rows = []
    ordered_health = sorted(
        enumerate(trip["provider_health"]),
        key=lambda pair: (-HEALTH_RISK_ORDER.get(pair[1]["status"], 99), pair[0]),
    )
    for _, health in ordered_health:
        rows.append(
            '<tr data-provider="%s" data-provider-mode="%s" data-provider-status="%s" data-provider-reason="%s"><th scope="row">%s</th>'
            '<td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' % (
                attr(health["provider"]), attr(health["mode"]), attr(health["status"]), attr(health["reason"]),
                text(_provider_label(labels, health["provider"])),
                text(health["version"]), text(_enum_label(labels, "mode", health["mode"])),
                text(_enum_label(labels, "health_status", health["status"])), _time(health["checked_at"]), text(_health_reason(health, labels)),
            )
        )
    table = '<div class="health-table-wrap"><table><thead><tr><th>%s</th><th>%s</th><th>%s</th><th>%s</th><th>%s</th><th>%s</th></tr></thead><tbody>%s</tbody></table></div>' % (
        text(labels["provider"]), text(labels["version"]), text(labels["mode"]), text(labels["status"]), text(labels["checked"]), text(labels["reason"]), "".join(rows),
    )
    return _section("provider-health", labels["health"], table, "panel panel-wide")


# Attribution required by each provider's terms when its data is displayed.
# AMap terms 7.7 require naming 高德地图 as the source; VariFlight's terms of use
# carry an attribution mandate for permitted non-commercial sharing.
PROVIDER_ATTRIBUTION = {
    "amap": "地图与路线数据来源于高德地图",
    "variflight": "航班状态与舒适度数据来源于飞常准 VariFlight",
    "12306-mcp": "铁路班次与票价来源于中国铁路 12306 公开查询",
    "flyai": "住宿与航班候选来源于飞猪 Fliggy",
}


def _attribution(trip: Mapping[str, Any]) -> str:
    """Name every provider that actually contributed data to this Trip."""
    contributing = {
        health["provider"]
        for health in trip.get("provider_health", ())
        if health.get("status") == "ready" and health.get("mode") in ("live", "cached")
    }
    names = [PROVIDER_ATTRIBUTION[provider] for provider in sorted(contributing) if provider in PROVIDER_ATTRIBUTION]
    if not names:
        return ""
    return '<p class="attribution" data-attribution="1">%s。</p>' % text("；".join(names))


def _footer(trip: Mapping[str, Any], labels: Mapping[str, str]) -> str:
    return (
        '<footer class="page-footer" data-section="footer" data-trip-id="%s"><p><strong>%s：</strong>'
        '%s%s</p>'
        '%s<p>%s %s · %s %s · %s %s</p></footer>'
    ) % (
        attr(trip["trip_id"]), text(labels["readonly"]), text(labels["footer_notice"]), text(labels["boundary"]), _attribution(trip),
        text(labels["schema"]), text(trip["schema_version"]), text(labels["renderer"]), RENDERER_VERSION,
        text(labels["current_revision"]), text(trip["revision"]["number"]),
    )


def _section(identifier: str, heading: str, body: str, classes: str) -> str:
    return '<section class="%s" id="%s" data-section="%s" aria-labelledby="%s-heading"><h2 id="%s-heading">%s</h2>%s</section>' % (
        attr(classes), attr(identifier), attr(identifier), attr(identifier), attr(identifier), text(heading), body,
    )


def _claim_links(claim_ids: Sequence[str], claims: Mapping[str, Any], labels: Mapping[str, str]) -> str:
    links = []
    for claim_id in claim_ids:
        claim = claims[claim_id]
        links.append('<a class="claim-badge" data-claim-link="%s" href="#%s">%s</a>' % (
            attr(claim_id), dom_id("claim", claim_id), text(_enum_label(labels, "claim_status", claim["status"])),
        ))
    return '<div class="claim-links" aria-label="%s">%s</div>' % (
        text(labels["claim_evidence"]), "".join(links) or '<span class="empty-state">%s</span>' % text(labels["no_claim"]),
    )


def _price(price: Optional[Mapping[str, Any]], owner: str, labels: Mapping[str, str]) -> str:
    if price is None:
        return '<p data-price-owner="%s" data-price-type="none" data-price-amount="">%s</p>' % (attr(owner), text(labels["price_unknown"]))
    amount = labels["price_unknown"] if price["amount"] is None else "%s %s" % (price["currency"], _number(price["amount"]))
    return '<p data-price-owner="%s" data-price-type="%s" data-price-amount="%s"><strong>%s</strong> <span class="price-type">%s · %s</span> · %s %s</p>' % (
        attr(owner), attr(price["price_type"]), attr("" if price["amount"] is None else _number(price["amount"])), text(amount),
        text(_enum_label(labels, "price_type", price["price_type"])), text(_enum_label(labels, "price_unit", price["unit"])),
        text(labels["queried"]), _time_or_unknown(price["queried_at"], labels),
    )


def _list_text(values: Sequence[str], labels: Mapping[str, str]) -> str:
    return text("、".join(values) if values else labels["none"])


def _empty(labels: Mapping[str, str]) -> str:
    return '<p class="empty-state">%s</p>' % text(labels["none"])


def _clock(value: str) -> str:
    return text(value[11:16])


def _time(value: str) -> str:
    visible = value[:16].replace("T", " ") if len(value) >= 16 else value
    return '<time datetime="%s">%s</time>' % (attr(value), text(visible))


def _time_or_unknown(value: Optional[str], labels: Mapping[str, str]) -> str:
    return _time(value) if value else text(labels["none"])


def _number(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)
