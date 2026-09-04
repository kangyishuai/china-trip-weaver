"""Journey -> deterministic, phone-first, single-file HTML overview."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

from ..journey import (
    journey_booking_checklist,
    journey_risk_items,
    validate_journey,
)
from .html import (
    PROVIDER_ATTRIBUTION,
    RendererError,
    _enum_label,
    _field_label,
    _health_reason,
    _number,
    _provider_label,
)
from .template import CSP, RENDERER_VERSION, attr, embedded_json, external_link, renderer_css, text


JOURNEY_READABILITY_CSS = """
.journey-route,
.checklist,
.risk-list,
.segment-list,
.compact-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.journey-route { counter-reset: route-stop; }
.journey-title-route,
.journey-title-dates { display: block; }
.journey-title-route {
  overflow-wrap: normal;
  word-break: keep-all;
}
.journey-title-dates {
  font-size: 0.62em;
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em;
  margin-top: 0.35rem;
}
.page-header h1 {
  font-size: clamp(2rem, 4.5vw, 3.6rem);
  max-width: none;
}
.route-stop {
  border-left: 3px solid var(--jade);
  counter-increment: route-stop;
  margin-left: 0.65rem;
  padding: 0 0 1.35rem 1.4rem;
  position: relative;
}
.route-stop:last-child { padding-bottom: 0; }
.route-stop::before {
  align-items: center;
  background: var(--vermilion);
  border: 3px solid var(--paper-raised);
  border-radius: 50%;
  color: #ffffff;
  content: counter(route-stop);
  display: flex;
  font-size: 0.72rem;
  font-weight: 800;
  height: 1.65rem;
  justify-content: center;
  left: -0.9rem;
  position: absolute;
  top: -0.1rem;
  width: 1.65rem;
}
.route-stop h3,
.checklist-item h3,
.risk-item h3,
.segment-card h3 { margin: 0; }
.route-stop p,
.checklist-item p,
.risk-item p,
.segment-card p { margin: 0.35rem 0; }
.metric-grid {
  display: grid;
  gap: 0.75rem;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.metric-card {
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 0.65rem;
  min-width: 0;
  padding: 0.8rem;
}
.metric-card strong { display: block; font-size: 1.15rem; }
.metric-card span,
.trace-note,
.deadline-note { color: var(--muted); }
.checklist-item,
.risk-item,
.segment-card {
  border-top: 1px solid var(--line);
  padding-block: 1rem;
}
.checklist-item:first-child,
.risk-item:first-child,
.segment-card:first-child { border-top: 0; }
.deadline {
  color: var(--vermilion);
  display: block;
  font-variant-numeric: tabular-nums;
  font-weight: 780;
  margin-bottom: 0.25rem;
}
.risk-item[data-risk-kind="claim_conflict"] { border-left: 4px solid var(--vermilion); padding-left: 0.8rem; }
.risk-item[data-risk-kind="provider_capability"] { border-left: 4px solid var(--gold); padding-left: 0.8rem; }
.compact-list li { margin: 0.35rem 0; }
.segment-stats { color: var(--muted); }
@media (min-width: 768px) {
  .metric-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); }
  .truth-banner { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .journey-route {
    display: grid;
    gap: 0;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    margin-top: 1.5rem;
  }
  .route-stop {
    border-left: 0;
    border-top: 3px solid var(--jade);
    margin-left: 0;
    padding: 1.4rem 1rem 0 0;
  }
  .route-stop:last-child { padding-bottom: 0; }
  .route-stop::before { left: 0; top: -0.9rem; }
  #route-overview,
  #booking-checklist,
  #risk-register,
  #segment-overview { grid-column: 1 / -1; }
}
@media (min-width: 1100px) {
  .truth-banner { grid-template-columns: repeat(4, minmax(0, 1fr)); }
}
@media (prefers-reduced-motion: reduce) {
  .journey-route { scroll-behavior: auto; }
}
@media print {
  .checklist-item,
  .risk-item,
  .segment-card,
  .route-stop { break-inside: avoid; }
}
""".strip()


JOURNEY_SECTIONS = frozenset((
    "header",
    "truth-banner",
    "journey-nav",
    "route-overview",
    "budget-summary",
    "booking-checklist",
    "risk-register",
    "segment-overview",
    "connection-overview",
    "provider-health",
    "journey-notes",
    "footer",
))


CAPABILITY_LABELS = {
    "en": {
        "rail": "rail tickets", "geocode": "place lookup", "poi": "place search",
        "route": "local routes", "flight": "flights", "weather": "weather",
        "comfort": "flight comfort", "lodging": "lodging", "research": "web research",
    },
    "zh-CN": {
        "rail": "火车票", "geocode": "地点解析", "poi": "地点搜索", "route": "市内路线",
        "flight": "航班", "weather": "天气", "comfort": "航班舒适度",
        "lodging": "住宿", "research": "网络调研",
    },
}


def render_journey(
    journey: Mapping[str, Any],
    renderer_version: str = RENDERER_VERSION,
) -> str:
    """Render one validated Journey with the shared renderer security boundary."""

    if renderer_version != RENDERER_VERSION:
        raise RendererError("unsupported renderer version")
    report = validate_journey(journey)
    if not report.ok:
        raise RendererError(
            "Journey is not validated: "
            + "; ".join(issue.render() for issue in report.errors)
        )
    try:
        return _render_journey(journey)
    except ValueError as exc:
        raise RendererError(str(exc)) from exc


def _render_journey(journey: Mapping[str, Any]) -> str:
    locale = journey["trips"][0]["request"]["locale"]
    labels = _journey_labels(locale)
    checklist = journey_booking_checklist(journey)
    risks = journey_risk_items(journey)
    route = _journey_route(journey)
    origins = _journey_origins(journey)
    route_title = _route_title(origins, route)
    title_value = "%s · %s — %s" % (
        route_title,
        journey["start_date"],
        journey["end_date"],
    )
    date_title = "%s — %s" % (journey["start_date"], journey["end_date"])
    lines = [
        "<!doctype html>",
        '<html lang="%s">' % attr(locale),
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta http-equiv="Content-Security-Policy" content="%s">' % attr(CSP),
        "<title>%s</title>" % text(title_value),
        '<style id="renderer-css">%s\n%s</style>' % (
            renderer_css(), JOURNEY_READABILITY_CSS,
        ),
        "</head>",
        "<body>",
        '<a class="skip-link" href="#main-content">%s</a>' % text(labels["skip"]),
        '<header class="page-header" data-section="header">',
        '<p class="eyebrow">China Trip Weaver · Journey · v%s</p>' % RENDERER_VERSION,
        '<h1><span class="journey-title-route">%s</span><span class="journey-title-dates">%s</span></h1>' % (
            text(route_title), text(date_title),
        ),
        '<div class="header-meta"><span>%s %d</span><span>%s %d</span><span>%s %s</span><span>%s %s</span></div>' % (
            text(labels["travelers"]), _journey_traveler_count(journey),
            text(labels["segments"]), len(journey["trips"]),
            text(labels["revision"]), text(journey["revision"]["number"]),
            text(labels["generated"]), _time(journey["generated_at"]),
        ),
        "</header>",
        _truth_banner(journey, checklist, risks, labels),
        _journey_nav(labels),
        '<main id="main-content">',
        _route_section(journey, route, origins, labels),
        _budget_section(journey, labels),
        _checklist_section(journey, checklist, labels),
        _risk_section(journey, risks, labels),
        _segments_section(journey, labels),
        _connections_section(journey, labels),
        _provider_health_section(journey, labels),
        _notes_section(journey, labels),
        "</main>",
        _footer(journey, labels),
        '<script id="journey-data" type="application/json">%s</script>' % embedded_json(journey),
        "</body>",
        "</html>",
    ]
    return "\n".join(lines) + "\n"


def _journey_labels(locale: str) -> Mapping[str, str]:
    if locale == "en":
        return {
            "locale": "en", "skip": "Skip to journey overview", "travelers": "Travelers",
            "segments": "Segments", "revision": "Revision", "generated": "Generated",
            "truth": "Truth and limits", "overview": "Whole-journey route",
            "budget": "Total budget", "checklist": "Booking and verification checklist",
            "risks": "Risks and unresolved items", "segment_overview": "Segment overview",
            "connections": "Segment handoffs", "health": "Data-source status",
            "notes": "Constraints and assumptions",
            "data_modes": "Data modes", "actions": "Actions", "risk_items": "Risk items",
            "readonly": "Read-only planning only", "boundary": "No login, identity submission, booking, payment, cancellation, or changes.",
            "footer_notice": "Confirm inventory, prices, schedules, and opening status before departure.",
            "known_cost": "Known cost", "total_range": "Total range", "budget_limit": "Budget",
            "remaining": "Known remaining", "incomplete": "Upper bound not yet known",
            "unknown": "Not yet known", "by": "Complete before", "time_unknown": "time not specified",
            "transport_action": "Confirm transport", "lodging_action": "Confirm check-in",
            "unknown_action": "Resolve unknown", "source": "Trace", "open_source": "Open source",
            "open_booking": "Open official booking page", "open_lodging": "Open lodging page",
            "segment": "Segment %d", "days": "%d days", "mode": "Data mode",
            "transport": "Transport", "lodging": "Lodging", "no_transport": "No transport leg",
            "no_lodging": "No overnight stay", "connection": "Next-segment handoff",
            "same_stay": "same stay continues", "changed_stay": "change stay after the boundary night",
            "departing_stay": "no following overnight stay", "included_transport": "boundary transport is in the next segment",
            "separate_transport": "boundary transport is separate", "no_boundary_transport": "no boundary transport required",
            "capability_risk": "%s is %s for %s", "conflict_risk": "Sources conflict for %s",
            "unknown_risk": "%s remains unresolved", "verify_detail": "Verify %s for the travel date.",
            "provider": "Provider", "field": "Detail", "route_from": "From",
            "route_to": "To", "schema": "schema", "renderer": "renderer",
            "unknown_item": "detail to verify",
            "health_reason": "Status: %s. Technical detail is preserved in the page data.",
            "capabilities": "Capabilities", "constraint": "Constraints", "assumption": "Assumptions",
            "none": "None provided", "status": "Status",
        }
    return {
        "locale": "zh-CN", "skip": "跳到全程总览", "travelers": "人数", "segments": "分段",
        "revision": "修订", "generated": "生成于", "truth": "真实性与边界",
        "overview": "全程路线", "budget": "总预算", "checklist": "预订与核验清单",
        "risks": "风险与未解决项", "segment_overview": "分段概览", "data_modes": "数据口径",
        "connections": "跨段衔接", "health": "数据源状态", "notes": "约束与假设",
        "actions": "待办", "risk_items": "风险项", "readonly": "仅提供只读规划",
        "boundary": "不登录、不实名、不代下单、不支付、不退改。",
        "footer_notice": "出发前请再次确认库存、价格、班次与开放状态。",
        "known_cost": "已知费用", "total_range": "总费用区间", "budget_limit": "预算上限",
        "remaining": "按已知费用剩余", "incomplete": "上限仍未确定", "unknown": "尚未确定",
        "by": "请在此之前完成", "time_unknown": "具体时间未提供",
        "transport_action": "确认交通", "lodging_action": "确认入住", "unknown_action": "核验未知项",
        "source": "追溯", "open_source": "查看来源", "open_booking": "打开官方购票页",
        "open_lodging": "打开住宿页", "segment": "第 %d 段", "days": "%d 天",
        "mode": "数据口径", "transport": "交通", "lodging": "住宿",
        "no_transport": "本段无交通腿", "no_lodging": "本段无过夜住宿", "connection": "下一段衔接",
        "same_stay": "同一住宿延续", "changed_stay": "边界夜后更换住宿", "departing_stay": "下一段不再过夜",
        "included_transport": "跨段交通已计入下一段", "separate_transport": "跨段交通单独安排",
        "no_boundary_transport": "无需跨段交通", "capability_risk": "%s的%s能力%s",
        "conflict_risk": "%s的来源结论冲突", "unknown_risk": "%s仍有信息未确认",
        "verify_detail": "请按出行日期核验%s。", "provider": "数据源", "field": "核验项",
        "route_from": "从", "route_to": "到", "schema": "数据结构", "renderer": "页面模板",
        "unknown_item": "待核验信息",
        "health_reason": "当前状态为“%s”；技术详情已保留在页面数据中。",
        "capabilities": "能力", "constraint": "硬约束", "assumption": "默认假设",
        "none": "无 / 未提供", "status": "状态",
    }


def _journey_route(journey: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    result: List[Mapping[str, Any]] = []
    for index, trip in enumerate(journey["trips"]):
        cities: List[str] = []
        for day in trip["days"]:
            if day["city"] not in cities:
                cities.append(day["city"])
        if not cities:
            cities = [item["name"] for item in trip["request"]["destinations"]]
        result.append({
            "trip_index": index,
            "name": " → ".join(cities),
            "start_date": trip["request"]["start_date"],
            "end_date": trip["request"]["end_date"],
            "day_count": len(trip["days"]),
        })
    return tuple(result)


def _journey_origins(journey: Mapping[str, Any]) -> Sequence[str]:
    if journey.get("traveler_groups"):
        return tuple(group["origin"]["name"] for group in journey["traveler_groups"])
    origin = journey.get("origin")
    return (origin["name"],) if origin else ()


def _route_title(
    origins: Sequence[str],
    route: Sequence[Mapping[str, Any]],
) -> str:
    destinations: List[str] = []
    for item in route:
        if not destinations or destinations[-1] != item["name"]:
            destinations.append(item["name"])
    if len(origins) > 1:
        prefix = " / ".join(origins)
        return " → ".join([prefix] + destinations)
    names = list(origins)
    for destination in destinations:
        if not names or names[-1] != destination:
            names.append(destination)
    return " → ".join(names or destinations)


def _truth_banner(
    journey: Mapping[str, Any],
    checklist: Sequence[Mapping[str, Any]],
    risks: Sequence[Mapping[str, Any]],
    labels: Mapping[str, str],
) -> str:
    modes: List[str] = []
    for trip in journey["trips"]:
        if trip["mode"] not in modes:
            modes.append(trip["mode"])
    return (
        '<aside class="truth-banner" data-section="truth-banner" aria-labelledby="truth-heading">'
        '<p><strong id="truth-heading">%s</strong><br>%s: %s</p>'
        '<p><strong>%s</strong><br>%d</p><p><strong>%s</strong><br>%d</p>'
        '<p><strong>%s</strong><br>%s</p></aside>'
    ) % (
        text(labels["truth"]), text(labels["data_modes"]),
        text(" / ".join(_enum_label(labels, "mode", item) for item in modes)),
        text(labels["actions"]), len(checklist), text(labels["risk_items"]), len(risks),
        text(labels["readonly"]), text(labels["boundary"]),
    )


def _journey_nav(labels: Mapping[str, str]) -> str:
    links = (
        ("route-overview", labels["overview"]),
        ("budget-summary", labels["budget"]),
        ("booking-checklist", labels["checklist"]),
        ("risk-register", labels["risks"]),
        ("segment-overview", labels["segment_overview"]),
        ("connection-overview", labels["connections"]),
        ("provider-health", labels["health"]),
    )
    return '<nav class="day-nav" data-section="journey-nav" aria-label="%s"><ul>%s</ul></nav>' % (
        text(labels["segment_overview"]),
        "".join('<li><a href="#%s">%s</a></li>' % (identifier, text(label)) for identifier, label in links),
    )


def _route_section(
    journey: Mapping[str, Any],
    route: Sequence[Mapping[str, Any]],
    origins: Sequence[str],
    labels: Mapping[str, str],
) -> str:
    items = []
    for item in route:
        index = item["trip_index"]
        items.append(
            '<li class="route-stop" data-route-trip-id="%s" data-route-index="%d" '
            'data-start-date="%s" data-end-date="%s"><h3><a href="#segment-%d">%s · %s</a></h3>'
            '<p>%s — %s · %s</p></li>' % (
                attr(journey["trips"][index]["trip_id"]), index,
                attr(item["start_date"]), attr(item["end_date"]), index + 1,
                text(labels["segment"] % (index + 1)), text(item["name"]),
                text(item["start_date"]), text(item["end_date"]),
                text(labels["days"] % item["day_count"]),
            )
        )
    origin_text = " / ".join(origins) if origins else labels["unknown"]
    destination_names: List[str] = []
    for item in route:
        if not destination_names or destination_names[-1] != item["name"]:
            destination_names.append(item["name"])
    destination_text = " → ".join(destination_names)
    summary = '<p><strong>%s：</strong>%s · <strong>%s：</strong>%s</p>' % (
        text(labels["route_from"]), text(origin_text),
        text(labels["route_to"]), text(destination_text),
    )
    return _section(
        "route-overview",
        labels["overview"],
        summary + '<ol class="journey-route">%s</ol>' % "".join(items),
        "panel panel-wide",
    )


def _budget_section(journey: Mapping[str, Any], labels: Mapping[str, str]) -> str:
    ledger = journey["budget_ledger"]
    total = ledger["total_range_cny"]
    minimum = total["minimum"]
    maximum = total["maximum"]
    if minimum is None or maximum is None:
        range_text = labels["incomplete"]
    else:
        range_text = "CNY %s–%s" % (_number(minimum), _number(maximum))
    budget = labels["unknown"] if ledger["budget_cny"] is None else "CNY " + _number(ledger["budget_cny"])
    remaining = labels["unknown"] if ledger["remaining_known_budget_cny"] is None else "CNY " + _number(ledger["remaining_known_budget_cny"])
    body = (
        '<div class="metric-grid" data-budget-currency="%s" data-budget-known="%s" '
        'data-budget-min="%s" data-budget-max="%s" data-budget-limit="%s" data-budget-status="%s">'
        '<div class="metric-card"><span>%s</span><strong>CNY %s</strong></div>'
        '<div class="metric-card"><span>%s</span><strong>%s</strong></div>'
        '<div class="metric-card"><span>%s</span><strong>%s</strong></div>'
        '<div class="metric-card"><span>%s</span><strong>%s</strong></div></div>'
    ) % (
        attr(ledger["currency"]), attr(_number(ledger["known_cost_cny"])),
        attr("" if minimum is None else _number(minimum)),
        attr("" if maximum is None else _number(maximum)),
        attr("" if ledger["budget_cny"] is None else _number(ledger["budget_cny"])),
        attr(ledger["status"]), text(labels["known_cost"]), text(_number(ledger["known_cost_cny"])),
        text(labels["total_range"]), text(range_text), text(labels["budget_limit"]), text(budget),
        text(labels["remaining"]), text(remaining),
    )
    return _section("budget-summary", labels["budget"], body, "panel panel-wide")


def _checklist_section(
    journey: Mapping[str, Any],
    checklist: Sequence[Mapping[str, Any]],
    labels: Mapping[str, str],
) -> str:
    items = []
    for item in checklist:
        if item["kind"] == "transport":
            heading = "%s · %s" % (labels["transport_action"], _display_source(item, labels))
        elif item["kind"] == "lodging":
            heading = "%s · %s" % (labels["lodging_action"], _display_source(item, labels))
        else:
            heading = "%s · %s" % (labels["unknown_action"], _display_source(item, labels))
        detail = _checklist_detail(journey, item, labels)
        items.append(
            '<li class="checklist-item" %s><span class="deadline">%s</span><h3>%s</h3>%s%s</li>' % (
                _trace_attributes("checklist", item), _deadline(item["deadline"], labels),
                text(heading), detail, _trace_note(item, labels),
            )
        )
    return _section("booking-checklist", labels["checklist"], '<ol class="checklist">%s</ol>' % "".join(items), "panel panel-wide")


def _risk_section(
    journey: Mapping[str, Any],
    risks: Sequence[Mapping[str, Any]],
    labels: Mapping[str, str],
) -> str:
    items = []
    for item in risks:
        if item["kind"] == "provider_capability":
            provider = _provider_label(labels, item["provider"])
            capability = CAPABILITY_LABELS[labels["locale"]].get(item["capability"], item["capability"])
            status = _enum_label(labels, "health_status", item["status"])
            heading = labels["capability_risk"] % (provider, capability, status)
            health = _health_for_risk(journey, item)
            detail = '<p>%s</p>' % text(_health_reason(health, labels))
        elif item["kind"] == "claim_conflict":
            heading = labels["conflict_risk"] % _display_source(item, labels)
            detail = '<p>%s</p>' % text(labels["verify_detail"] % _field_label(item["field_path"], labels))
        else:
            heading = labels["unknown_risk"] % _display_source(item, labels)
            detail = '<p>%s</p>' % text(labels["verify_detail"] % _field_label(item["field_path"], labels))
        items.append(
            '<li class="risk-item" %s><h3>%s</h3>%s%s%s</li>' % (
                _trace_attributes("risk", item), text(heading), detail,
                _source_link(journey, item, labels), _trace_note(item, labels),
            )
        )
    return _section("risk-register", labels["risks"], '<ol class="risk-list">%s</ol>' % "".join(items), "panel panel-wide")


def _segments_section(journey: Mapping[str, Any], labels: Mapping[str, str]) -> str:
    cards = []
    for index, trip in enumerate(journey["trips"]):
        cities = []
        for day in trip["days"]:
            if day["city"] not in cities:
                cities.append(day["city"])
        legs = []
        names = _trip_reference_names(trip)
        for leg in trip["transport_legs"]:
            service = " · %s" % leg["service_number"] if leg["service_number"] else ""
            legs.append('<li>%s%s · %s → %s · %s</li>' % (
                text(_enum_label(labels, "travel_mode", leg["travel_mode"])), text(service),
                text(names.get(leg["from_ref"], labels["unknown"])),
                text(names.get(leg["to_ref"], labels["unknown"])),
                _time_or_date(leg.get("depart_at"), labels),
            ))
        stays = [
            '<li>%s · %s — %s</li>' % (
                text(item["name"]), text(item["check_in"]), text(item["check_out"]),
            )
            for item in trip["lodgings"]
        ]
        cards.append(
            '<article class="segment-card" id="segment-%d" data-segment-index="%d" data-trip-id="%s" '
            'data-start-date="%s" data-end-date="%s" data-day-count="%d">'
            '<h3>%s · %s</h3><p class="segment-stats">%s — %s · %s · %s: %s</p>'
            '<h4>%s</h4><ul class="compact-list">%s</ul><h4>%s</h4><ul class="compact-list">%s</ul></article>' % (
                index + 1, index, attr(trip["trip_id"]), attr(trip["request"]["start_date"]),
                attr(trip["request"]["end_date"]), len(trip["days"]),
                text(labels["segment"] % (index + 1)), text(" → ".join(cities)),
                text(trip["request"]["start_date"]), text(trip["request"]["end_date"]),
                text(labels["days"] % len(trip["days"])), text(labels["mode"]),
                text(_enum_label(labels, "mode", trip["mode"])), text(labels["transport"]),
                "".join(legs) or '<li class="empty-state">%s</li>' % text(labels["no_transport"]),
                text(labels["lodging"]),
                "".join(stays) or '<li class="empty-state">%s</li>' % text(labels["no_lodging"]),
            )
        )
    return _section("segment-overview", labels["segment_overview"], '<div class="segment-list">%s</div>' % "".join(cards), "panel panel-wide")


def _connections_section(journey: Mapping[str, Any], labels: Mapping[str, str]) -> str:
    cards = []
    for index, connection in enumerate(journey["segment_connections"]):
        cards.append(
            '<article class="entity-card" data-connection-id="%s" data-connection-index="%d" '
            'data-from-trip-id="%s" data-to-trip-id="%s"><h3>%s → %s</h3>'
            '<p>%s — %s</p>%s</article>' % (
                attr(connection["connection_id"]), index,
                attr(connection["from_trip_id"]), attr(connection["to_trip_id"]),
                text(labels["segment"] % (index + 1)), text(labels["segment"] % (index + 2)),
                text(connection["from_end_date"]), text(connection["to_start_date"]),
                _connection_summary(connection, labels),
            )
        )
    return _section(
        "connection-overview",
        labels["connections"],
        "".join(cards) or '<p class="empty-state">%s</p>' % text(labels["none"]),
        "panel panel-wide",
    )


def _provider_health_section(journey: Mapping[str, Any], labels: Mapping[str, str]) -> str:
    cards = []
    for trip_index, trip in enumerate(journey["trips"]):
        for health in trip["provider_health"]:
            separator = ", " if labels["locale"] == "en" else "、"
            capabilities = separator.join(
                CAPABILITY_LABELS[labels["locale"]].get(item, item)
                for item in health["capabilities"]
            )
            cards.append(
                '<article class="health-card" data-health-trip-index="%d" data-provider="%s" '
                'data-provider-mode="%s" data-provider-status="%s"><h3>%s · %s</h3>'
                '<p>%s：%s · %s：%s</p><p>%s</p></article>' % (
                    trip_index, attr(health["provider"]), attr(health["mode"]), attr(health["status"]),
                    text(labels["segment"] % (trip_index + 1)), text(_provider_label(labels, health["provider"])),
                    text(labels["status"]), text(_enum_label(labels, "health_status", health["status"])),
                    text(labels["capabilities"]), text(capabilities), text(_health_reason(health, labels)),
                )
            )
    return _section("provider-health", labels["health"], "".join(cards), "panel panel-wide")


def _notes_section(journey: Mapping[str, Any], labels: Mapping[str, str]) -> str:
    constraints: List[str] = []
    assumptions: List[str] = []
    for trip in journey["trips"]:
        for value, target in (
            (trip["request"]["constraints"], constraints),
            (trip["request"]["assumptions"], assumptions),
        ):
            for item in value:
                if item not in target:
                    target.append(item)
    body = (
        '<h3>%s</h3><ul class="compact-list">%s</ul>'
        '<h3>%s</h3><ul class="compact-list">%s</ul>'
    ) % (
        text(labels["constraint"]),
        "".join("<li>%s</li>" % text(item) for item in constraints) or '<li class="empty-state">%s</li>' % text(labels["none"]),
        text(labels["assumption"]),
        "".join("<li>%s</li>" % text(item) for item in assumptions) or '<li class="empty-state">%s</li>' % text(labels["none"]),
    )
    return _section("journey-notes", labels["notes"], body, "panel panel-wide")


def _connection_summary(connection: Mapping[str, Any], labels: Mapping[str, str]) -> str:
    lodging = {
        "continued": labels["same_stay"],
        "changed": labels["changed_stay"],
        "departing": labels["departing_stay"],
    }[connection["lodging_continuity"]["status"]]
    transport = {
        "included_in_next_trip": labels["included_transport"],
        "separate": labels["separate_transport"],
        "not_required": labels["no_boundary_transport"],
    }[connection["cross_segment_transport"]["status"]]
    return '<p><strong>%s：</strong>%s；%s</p>' % (
        text(labels["connection"]), text(lodging), text(transport),
    )


def _checklist_detail(
    journey: Mapping[str, Any],
    item: Mapping[str, Any],
    labels: Mapping[str, str],
) -> str:
    entity = _entity_for_item(journey, item)
    if item["kind"] == "unknown":
        field = _field_label(item["field_path"], labels)
        body = '<p>%s</p>' % text(labels["verify_detail"] % field)
    elif item["kind"] == "transport" and entity is not None:
        service = entity.get("service_number") or labels["unknown"]
        body = '<p>%s · %s</p>' % (
            text(_enum_label(labels, "travel_mode", entity["travel_mode"])), text(service),
        )
    elif item["kind"] == "lodging" and entity is not None:
        body = '<p>%s — %s</p>' % (text(entity["check_in"]), text(entity["check_out"]))
    else:
        body = ""
    return body + _source_link(journey, item, labels)


def _source_link(
    journey: Mapping[str, Any],
    item: Mapping[str, Any],
    labels: Mapping[str, str],
) -> str:
    claim = _claim_for_item(journey, item)
    if claim is not None:
        return '<p>%s</p>' % external_link(claim["source_url"], labels["open_source"])
    entity = _entity_for_item(journey, item)
    if item["kind"] == "transport" and entity and entity.get("booking_url"):
        return '<p>%s</p>' % external_link(entity["booking_url"], labels["open_booking"])
    if item["kind"] == "lodging" and entity and entity.get("deep_links"):
        return '<p>%s</p>' % external_link(entity["deep_links"][0], labels["open_lodging"])
    return ""


def _trace_attributes(prefix: str, item: Mapping[str, Any]) -> str:
    values = {
        "data-%s-id" % prefix: item["item_id"],
        "data-%s-kind" % prefix: item["kind"],
        "data-trip-index": item["trip_index"],
        "data-source-kind": item["source_kind"],
        "data-source-ref": item["source_ref"],
        "data-source-claim": item.get("claim_id") or "",
        "data-source-path": item.get("field_path") or "",
        "data-deadline": item["deadline"],
    }
    if item.get("capability"):
        values["data-capability"] = item["capability"]
    if item.get("status"):
        values["data-risk-status"] = item["status"]
    return " ".join('%s="%s"' % (name, attr(value)) for name, value in values.items())


def _trace_note(item: Mapping[str, Any], labels: Mapping[str, str]) -> str:
    return '<p class="trace-note">%s：<a href="#segment-%d">%s</a> · %s</p>' % (
        text(labels["source"]), item["trip_index"] + 1,
        text(labels["segment"] % (item["trip_index"] + 1)),
        text(_display_source(item, labels)),
    )


def _display_source(item: Mapping[str, Any], labels: Mapping[str, str]) -> str:
    if item["source_kind"] == "provider_health":
        return _provider_label(labels, item["provider"])
    return item["source_name"] or labels["unknown"]


def _entity_for_item(
    journey: Mapping[str, Any],
    item: Mapping[str, Any],
) -> Optional[Mapping[str, Any]]:
    trip = journey["trips"][item["trip_index"]]
    groups = {
        "transport_leg": ("transport_legs", "leg_id"),
        "lodging": ("lodgings", "lodging_id"),
        "poi": ("pois", "poi_id"),
        "day": ("days", "day_id"),
    }
    spec = groups.get(item["source_kind"])
    if spec is None:
        return None
    collection, key = spec
    return next(
        (value for value in trip[collection] if value[key] == item["source_ref"]),
        None,
    )


def _claim_for_item(
    journey: Mapping[str, Any],
    item: Mapping[str, Any],
) -> Optional[Mapping[str, Any]]:
    claim_id = item.get("claim_id")
    if not claim_id:
        return None
    return next(
        (
            claim for claim in journey["trips"][item["trip_index"]]["claims"]
            if claim["claim_id"] == claim_id
        ),
        None,
    )


def _health_for_risk(
    journey: Mapping[str, Any],
    item: Mapping[str, Any],
) -> Mapping[str, Any]:
    return next(
        health for health in journey["trips"][item["trip_index"]]["provider_health"]
        if health["provider"] == item["provider"]
        and health["status"] == item["status"]
        and item["capability"] in health["capabilities"]
    )


def _trip_reference_names(trip: Mapping[str, Any]) -> Mapping[str, str]:
    names: Dict[str, str] = {}
    request = trip["request"]
    places: List[Mapping[str, Any]] = []
    if request.get("origin"):
        places.append(request["origin"])
    places.extend(group["origin"] for group in (request.get("traveler_groups") or ()))
    if request.get("meeting_anchor"):
        places.append(request["meeting_anchor"]["location"])
    places.extend(request["destinations"])
    for place in places:
        names[place["ref_id"]] = place["name"]
    for item, key in (
        *((value, "lodging_id") for value in trip["lodgings"]),
        *((value, "poi_id") for value in trip["pois"]),
    ):
        names[item[key]] = item["name"]
    return names


def _journey_traveler_count(journey: Mapping[str, Any]) -> int:
    if journey.get("traveler_groups"):
        return sum(int(group["travelers"]) for group in journey["traveler_groups"])
    return int(journey["travelers"])


def _deadline(value: str, labels: Mapping[str, str]) -> str:
    if len(value) >= 16:
        return '%s <time datetime="%s">%s</time>' % (
            text(labels["by"]), attr(value), text(value[:16].replace("T", " ")),
        )
    return '%s <time datetime="%s">%s</time> · <span class="deadline-note">%s</span>' % (
        text(labels["by"]), attr(value), text(value), text(labels["time_unknown"]),
    )


def _time(value: str) -> str:
    visible = value[:16].replace("T", " ") if len(value) >= 16 else value
    return '<time datetime="%s">%s</time>' % (attr(value), text(visible))


def _time_or_date(value: Optional[str], labels: Mapping[str, str]) -> str:
    return _time(value) if value else text(labels["unknown"])


def _section(identifier: str, heading: str, body: str, classes: str) -> str:
    return '<section class="%s" id="%s" data-section="%s" aria-labelledby="%s-heading"><h2 id="%s-heading">%s</h2>%s</section>' % (
        attr(classes), attr(identifier), attr(identifier), attr(identifier),
        attr(identifier), text(heading), body,
    )


def _footer(journey: Mapping[str, Any], labels: Mapping[str, str]) -> str:
    contributing = {
        health["provider"]
        for trip in journey["trips"]
        for health in trip.get("provider_health", ())
        if health.get("status") == "ready" and health.get("mode") in ("live", "cached")
    }
    attributions = [
        PROVIDER_ATTRIBUTION[provider]
        for provider in sorted(contributing)
        if provider in PROVIDER_ATTRIBUTION
    ]
    attribution = (
        '<p class="attribution" data-attribution="1">%s。</p>' % text("；".join(attributions))
        if attributions else ""
    )
    return (
        '<footer class="page-footer" data-section="footer" data-journey-id="%s">'
        '<p><strong>%s：</strong>%s %s</p>%s<p>%s %s · %s %s · %s %s</p></footer>'
    ) % (
        attr(journey["journey_id"]), text(labels["readonly"]), text(labels["footer_notice"]),
        text(labels["boundary"]), attribution, text(labels["schema"]), text(journey["schema_version"]),
        text(labels["renderer"]), RENDERER_VERSION, text(labels["revision"]),
        text(journey["revision"]["number"]),
    )
