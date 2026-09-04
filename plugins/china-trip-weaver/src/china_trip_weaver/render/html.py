"""Trip -> deterministic, phone-first, single-file HTML."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from ..validate_trip import validate_trip
from .template import CSP, RENDERER_VERSION, attr, dom_id, embedded_json, external_link, renderer_css, text


class RendererError(ValueError):
    pass


def safe_output_name(trip_id: str) -> str:
    cleaned = re.sub(r"[^a-z0-9-]+", "-", trip_id.lower()).strip("-")
    if not cleaned:
        raise RendererError("trip_id cannot produce a safe filename")
    return cleaned[:64] + ".html"


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
    lines = [
        "<!doctype html>",
        '<html lang="%s">' % attr(locale),
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta http-equiv="Content-Security-Policy" content="%s">' % attr(CSP),
        "<title>%s</title>" % text(title_value),
        '<style id="renderer-css">%s</style>' % renderer_css(),
        "</head>",
        "<body>",
        '<a class="skip-link" href="#main-content">%s</a>' % text(labels["skip"]),
        '<header class="page-header" data-section="header">',
        '<p class="eyebrow">China Trip Weaver · v%s</p>' % RENDERER_VERSION,
        "<h1>%s</h1>" % text(title_value),
        '<div class="header-meta"><span>%s %s</span><span>%s %s</span><span>%s %s</span><span class="mode-badge" data-trip-mode="%s">%s: %s</span></div>' % (
            text(labels["travelers"]), text(trip["request"]["travelers"]),
            text(labels["revision"]), text(trip["revision"]["number"]),
            text(labels["generated"]), _time(trip["generated_at"]),
            attr(trip["mode"]), text(labels["mode"]), text(trip["mode"]),
        ),
        "</header>",
        _truth_banner(trip, labels),
        _day_nav(trip, labels),
        '<main id="main-content">',
        _request_section(trip, labels),
        _transport_section(trip, claim_map, labels),
        _lodging_section(trip, claim_map, labels),
        _days_section(trip, claim_map, labels),
        _location_section(trip, claim_map, labels),
        _unknowns_section(trip, labels),
        _evidence_section(trip, labels),
        _health_section(trip, labels),
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
            "skip": "Skip to itinerary", "travelers": "Travelers", "revision": "Revision",
            "generated": "Generated", "mode": "Data mode", "truth": "Truth and limits", "request": "Trip request",
            "transport": "Transport", "lodging": "Lodging", "days": "Daily itinerary",
            "locations": "Location overview", "unknowns": "Alternatives and unknowns",
            "evidence": "Evidence", "health": "Provider health", "none": "None provided",
            "readonly": "Read-only planning only", "source": "Open source", "price_unknown": "Price unknown",
            "origin": "Origin", "destinations": "Destinations", "dates": "Dates", "budget": "Budget",
            "interests": "Interests", "pace": "Pace", "constraints": "Constraints", "assumptions": "Assumptions",
            "provider": "Provider", "version": "Version", "status": "Status", "checked": "Checked", "reason": "Reason",
        }
    return {
        "skip": "跳到行程正文", "travelers": "人数", "revision": "修订", "generated": "生成于", "mode": "数据口径",
        "truth": "真实性与边界", "request": "行程需求", "transport": "交通摘要",
        "lodging": "住宿摘要", "days": "逐日行程", "locations": "位置概览",
        "unknowns": "备选与未知项", "evidence": "证据", "health": "Provider 健康",
        "none": "无 / 未提供", "readonly": "仅提供只读规划", "source": "查看来源",
        "price_unknown": "价格未知 / 点击核验",
        "origin": "出发地", "destinations": "目的地", "dates": "日期", "budget": "预算",
        "interests": "兴趣", "pace": "节奏", "constraints": "硬约束", "assumptions": "默认假设",
        "provider": "数据源", "version": "版本", "status": "状态", "checked": "检查时间", "reason": "原因",
    }


def _truth_banner(trip: Mapping[str, Any], labels: Mapping[str, str]) -> str:
    order = {"contract_mismatch": 8, "forbidden": 7, "expired": 6, "rate_limited": 5, "unavailable": 4, "missing": 3, "degraded": 2, "ready": 1}
    worst = max(trip["provider_health"], key=lambda item: (order.get(item["status"], 99), item["provider"]))
    notice = ""
    if trip["mode"] == "mock":
        notice = "<p><strong>Mock:</strong> %s</p>" % text(trip["mock_notice"])
    return (
        '<aside class="truth-banner" data-section="truth-banner" aria-labelledby="truth-heading">'
        '<p><strong id="truth-heading">%s</strong><br>%s %s · %s %s</p>'
        '<p><strong>%s:</strong><br>%s · %s</p>'
        '<p><strong>%s:</strong><br>%d · %s；不登录、不实名、不代下单、不支付、不退改。</p>%s'
        "</aside>"
    ) % (
        text(labels["truth"]), text(labels["mode"]), text(trip["mode"]), text(labels["generated"]), _time(trip["generated_at"]),
        text(labels["provider"]), text(worst["provider"]), text(worst["status"]), text(labels["unknowns"]), len(trip["unknowns"]),
        text(labels["readonly"]), notice,
    )


def _day_nav(trip: Mapping[str, Any], labels: Mapping[str, str]) -> str:
    items = "".join(
        '<li><a href="#%s">Day %d · %s</a></li>' % (dom_id("day", day["day_id"]), index + 1, text(day["date"]))
        for index, day in enumerate(trip["days"])
    )
    return '<nav class="day-nav" data-section="day-nav" aria-label="%s"><ul>%s</ul></nav>' % (text(labels["days"]), items)


def _request_section(trip: Mapping[str, Any], labels: Mapping[str, str]) -> str:
    request = trip["request"]
    origin = request["origin"]["name"] if request["origin"] else labels["none"]
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
        text(labels["interests"]), _list_text(request["interests"], labels), text(labels["pace"]), text(request["pace"]),
        text(labels["constraints"]), _list_text(request["constraints"], labels), text(labels["assumptions"]), _list_text(request["assumptions"], labels),
    )


def _transport_section(trip: Mapping[str, Any], claims: Mapping[str, Any], labels: Mapping[str, str]) -> str:
    cards = []
    for index, leg in enumerate(trip["transport_legs"]):
        service = leg["service_number"] or labels["none"]
        links = external_link(leg["booking_url"], "打开官方页面（只读）") if leg["booking_url"] else text(labels["none"])
        cards.append(
            '<article class="entity-card" data-entity-id="%s" data-entity-kind="transport" data-service-number="%s">'
            '<h3>%s · %s</h3><p>%s → %s</p><p>%s — %s · %s min</p>'
            '%s<p>%s</p>%s</article>' % (
                attr(leg["leg_id"]), attr(leg["service_number"] or ""), text(leg["travel_mode"]), text(service),
                text(leg["from_ref"]), text(leg["to_ref"]), _time_or_unknown(leg["depart_at"], labels),
                _time_or_unknown(leg["arrive_at"], labels), text(leg["duration_minutes"] if leg["duration_minutes"] is not None else labels["none"]),
                _price(leg["price"], leg["leg_id"], labels), links, _claim_links(leg["claim_ids"], claims),
            )
        )
    return _section("transport-summary", labels["transport"], "".join(cards) or _empty(labels), "panel")


def _lodging_section(trip: Mapping[str, Any], claims: Mapping[str, Any], labels: Mapping[str, str]) -> str:
    cards = []
    for lodging in trip["lodgings"]:
        links = " · ".join(external_link(url, "住宿深链") for url in lodging["deep_links"]) or text(labels["none"])
        cards.append(
            '<article class="entity-card" data-entity-id="%s" data-entity-kind="lodging"><h3>%s</h3>'
            '<p>%s · %s</p><p>%s — %s</p>%s<p>%s</p>%s</article>' % (
                attr(lodging["lodging_id"]), text(lodging["name"]), text(lodging["city"]), text(lodging["area"]),
                text(lodging["check_in"]), text(lodging["check_out"]), _price(lodging["price"], lodging["lodging_id"], labels),
                links, _claim_links(lodging["claim_ids"], claims),
            )
        )
    return _section("lodging-summary", labels["lodging"], "".join(cards) or _empty(labels), "panel")


def _days_section(trip: Mapping[str, Any], claims: Mapping[str, Any], labels: Mapping[str, str]) -> str:
    days = []
    for index, day in enumerate(trip["days"]):
        slots = []
        for slot in day["slots"]:
            lock = '<span class="lock-badge">locked</span>' if slot["locked"] else ""
            slots.append(
                '<li class="timeline-item" data-slot-id="%s" data-start-at="%s" data-end-at="%s">'
                '<span class="slot-time"><time datetime="%s">%s</time>–<time datetime="%s">%s</time></span>'
                '<h3>%s</h3><div class="badge-row"><span class="status-badge">%s · %s</span>%s</div>%s</li>' % (
                    attr(slot["slot_id"]), attr(slot["start_at"]), attr(slot["end_at"]),
                    attr(slot["start_at"]), _clock(slot["start_at"]), attr(slot["end_at"]), _clock(slot["end_at"]),
                    text(slot["title"]), text(slot["kind"]), text(slot["status"]), lock,
                    _claim_links(slot["claim_ids"], claims),
                )
            )
        body = '<article class="day-block" id="%s" data-day-id="%s"><h3>Day %d · %s · %s</h3><ol class="timeline">%s</ol></article>' % (
            dom_id("day", day["day_id"]), attr(day["day_id"]), index + 1, text(day["date"]), text(day["city"]),
            "".join(slots) or '<li class="empty-state">%s</li>' % text(labels["none"]),
        )
        days.append(body)
    return _section("days", labels["days"], "".join(days), "panel panel-wide")


def _location_section(trip: Mapping[str, Any], claims: Mapping[str, Any], labels: Mapping[str, str]) -> str:
    entities = [("lodging", item, "lodging_id") for item in trip["lodgings"]] + [("poi", item, "poi_id") for item in trip["pois"]]
    point_candidates = [(kind, item, key) for kind, item, key in entities if item["coordinates"]]
    crs = "WGS84" if point_candidates and all(item["coordinates"]["wgs84"] for _, item, _ in point_candidates) else "GCJ02"
    field = "wgs84" if crs == "WGS84" else "gcj02"
    plotted = [(kind, item, key, item["coordinates"][field]) for kind, item, key in point_candidates if item["coordinates"][field]]
    svg = _location_svg(plotted, crs, labels) if plotted else '<p class="empty-state">位置未核验；未放置默认点。</p>'
    cards = []
    for kind, item, key in entities:
        identifier = item[key]
        links = item.get("deep_links", [])
        link_html = " · ".join(external_link(url, labels["source"]) for url in links) or text(labels["none"])
        coordinate = item["coordinates"]
        coordinate_text = "位置未核验" if not coordinate or not coordinate.get(field) else "%s %.6f, %.6f" % (crs, coordinate[field]["lng"], coordinate[field]["lat"])
        price_html = _price(item.get("price"), identifier, labels) if kind == "poi" else ""
        identity_attrs = 'data-entity-id="%s" data-entity-kind="poi"' % attr(identifier) if kind == "poi" else 'data-location-ref="%s"' % attr(identifier)
        cards.append(
            '<article class="entity-card" %s><h3>%s</h3><p>%s</p>%s<p>%s</p>%s</article>' % (
                identity_attrs, text(item["name"]), text(coordinate_text), price_html, link_html, _claim_links(item["claim_ids"], claims),
            )
        )
    return _section("location-overview", labels["locations"], svg + "".join(cards), "panel panel-wide")


def _location_svg(plotted: Sequence[Tuple[str, Mapping[str, Any], str, Mapping[str, float]]], crs: str, labels: Mapping[str, str]) -> str:
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
    note = '<p class="schematic-note" data-schematic-label="true">日程顺序示意，非道路路线；%s 坐标仅用于相对位置。</p>' % text(crs)
    return (
        '<svg class="location-svg" data-crs="%s" viewBox="0 0 100 100" role="img" aria-labelledby="location-map-title location-map-desc">'
        '<title id="location-map-title">位置顺序示意</title><desc id="location-map-desc">非真实道路路线；编号对应下方地点。</desc>%s%s</svg>%s'
    ) % (attr(crs), line, "".join(markers), note)


def _unknowns_section(trip: Mapping[str, Any], labels: Mapping[str, str]) -> str:
    cards = []
    for index, unknown in enumerate(trip["unknowns"]):
        cards.append(
            '<article class="unknown-card" data-unknown-index="%d" data-unknown-path="%s" data-unknown-reason="%s">'
            '<h3>%s</h3><p>%s</p><p>provider: %s · claim: %s</p></article>' % (
                index, attr(unknown["field_path"]), attr(unknown["reason"]), text(unknown["field_path"]),
                text(unknown["reason"]), text(unknown["provider"] or labels["none"]), text(unknown["claim_id"] or labels["none"]),
            )
        )
    return _section("alternatives-and-unknowns", labels["unknowns"], "".join(cards) or _empty(labels), "panel")


def _evidence_section(trip: Mapping[str, Any], labels: Mapping[str, str]) -> str:
    items = []
    for claim in trip["claims"]:
        items.append(
            '<li class="entity-card" id="%s" data-claim-id="%s"><h3>%s · %s</h3>'
            '<p>%s · confidence %s · mode %s</p><p>%s</p><p>%s</p></li>' % (
                dom_id("claim", claim["claim_id"]), attr(claim["claim_id"]), text(claim["provider"]), text(claim["status"]),
                text(claim["field_path"]), text(claim["confidence"]), text(claim["mode"]),
                _time(claim["queried_at"]), external_link(claim["source_url"], labels["source"]),
            )
        )
    return _section("evidence", labels["evidence"], '<ol>%s</ol>' % ("".join(items) or '<li>%s</li>' % text(labels["none"])), "panel panel-wide")


def _health_section(trip: Mapping[str, Any], labels: Mapping[str, str]) -> str:
    rows = []
    for health in trip["provider_health"]:
        rows.append(
            '<tr data-provider="%s"><th scope="row">%s</th><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' % (
                attr(health["provider"]), text(health["provider"]), text(health["version"]), text(health["mode"]),
                text(health["status"]), _time(health["checked_at"]), text(health["reason"]),
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
        '<footer class="page-footer" data-section="footer"><p><strong>%s：</strong>本页只做查询、比较和官方深链；不保证库存、价格、准点或开放状态，不执行登录、实名、代下单、支付、取消或改签。</p>'
        '%s<p>schema %s · renderer %s · trip %s</p></footer>'
    ) % (text(labels["readonly"]), _attribution(trip), text(trip["schema_version"]), RENDERER_VERSION, text(trip["trip_id"]))


def _section(identifier: str, heading: str, body: str, classes: str) -> str:
    return '<section class="%s" id="%s" data-section="%s" aria-labelledby="%s-heading"><h2 id="%s-heading">%s</h2>%s</section>' % (
        attr(classes), attr(identifier), attr(identifier), attr(identifier), attr(identifier), text(heading), body,
    )


def _claim_links(claim_ids: Sequence[str], claims: Mapping[str, Any]) -> str:
    links = []
    for claim_id in claim_ids:
        claim = claims[claim_id]
        links.append('<a class="claim-badge" data-claim-link="%s" href="#%s">%s</a>' % (attr(claim_id), dom_id("claim", claim_id), text(claim["status"])))
    return '<div class="claim-links" aria-label="claim evidence">%s</div>' % ("".join(links) or '<span class="empty-state">无 claim</span>')


def _price(price: Optional[Mapping[str, Any]], owner: str, labels: Mapping[str, str]) -> str:
    if price is None:
        return '<p data-price-owner="%s" data-price-type="none" data-price-amount="">%s</p>' % (attr(owner), text(labels["price_unknown"]))
    amount = labels["price_unknown"] if price["amount"] is None else "%s %s" % (price["currency"], _number(price["amount"]))
    return '<p data-price-owner="%s" data-price-type="%s" data-price-amount="%s"><strong>%s</strong> <span class="price-type">%s · %s</span> · queried %s</p>' % (
        attr(owner), attr(price["price_type"]), attr("" if price["amount"] is None else _number(price["amount"])), text(amount),
        text(price["price_type"]), text(price["unit"]), _time_or_unknown(price["queried_at"], labels),
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
