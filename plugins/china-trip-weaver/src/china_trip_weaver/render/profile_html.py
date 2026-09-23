"""Version 2: a time profile above the complete, reusable v1 fact record."""

from __future__ import annotations

import base64
import hashlib
import html
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from .profile_model import build_model, clock, safe_href
from .template import embedded_json, renderer_css

VERSION = "2"
ASSETS = Path(__file__).resolve().parents[3] / "assets"
# Frozen for renderer v2. Any output-affecting asset change needs a new format.
PROFILE_ASSET_SHA256 = "64036261736a937a1fcb509ce0fb8a394ce39e7bf2318a2da7d05caf37217c30"

LABELS = {
    "zh-CN": {
        "skip": "跳到旅程剖面", "readonly": "只读行程 · 根据来源核验", "kicker": "路线、时间、决定，在同一视野",
        "days": "天", "travelers": "人", "route": "按顺序经过的城市，非地理地图", "origin": "出发地", "first": "先确认这段交通",
        "stay": "当晚落点", "budget": "预算边界", "none_transport": "没有已排跨城交通", "verify_service": "按日期复核真实车次与价格",
        "no_stay": "这一天无过夜住宿", "known_cost": "可比较金额", "unknown_total": "总额仍未知；缺价不按零计算",
        "range": "总额范围已列出", "context": "一天的上下文", "overview": "时间与城市，一眼相连",
        "overview_note": "同一刻度只画已排占用；自由时段留白。选一天，看时间与关联事实。",
        "transport": "交通", "place": "地点", "lodging": "住宿", "reference": "斜纹＝静态/待证",
        "unknown": "红框＝具体未知", "excluded": "备选／未采用不计入横带", "day": "第 %d 天", "excluded_n": "另有 %d 条未纳入图带",
        "open": "空档", "scheduled": "已排", "prev": "← 前一天", "next": "后一天 →", "view_overview": "查看全程图 ↓",
        "first_day": "旅程起点", "last_day": "旅程终点", "adjacent_prev": "前一天", "adjacent_next": "后一天",
        "related": "关联未知", "source": "查看来源 ↗", "no_slots": "尚无已排时段。", "alternatives": "备选／未采用／状态未知 · %d",
        "tentative": "备选，未纳入时间图", "skipped": "未采用", "status_unknown": "状态未知，未纳入时间图",
        "locked": " · 锁定", "claim_reference": "参考／假设", "claim_unknown": "待核验", "claim_verified": "有来源",
        "plan_only": "仅行程安排", "tonight": "当晚住宿", "no_overnight": "这一天不住店", "price_unknown": "金额未知，入住前到来源页核验",
        "checkout": "结账金额另行核验", "live": "当前报价", "reference_price": "参考价", "estimate": "估算价",
        "click_price": "来源页待核验报价", "unknown_type": "报价性质待核验", "per_night": "每晚", "per_person": "每人",
        "total": "总计", "from": "起价", "unit_unknown": "单位待核验", "currency_unknown": "币种未知",
        "scenario": "如果这段交通晚 30 分钟？", "try": "看见后果 →", "undo": "撤回试算",
        "before": "原草案", "after": "晚 30 分", "overlap": "与 %s（%s 开始）交集 %d 分钟",
        "more_overlap": "；另有 %d 处相交，全部交集覆盖 %d 分钟", "gap": "到下一条已排时段 %s（%s）仍有 %d 分钟空档",
        "no_next": "当天没有后续时段；更远影响无法推断", "already_overlap": "原草案已有 %d 分钟重叠；此处展示试算后的总交集。",
        "caveat": "只移动这段草案时间块；不代表存在另一班车，不重排后续时段，也不推断票价或实时衔接。",
        "unsupported": "这一天没有有依据的可移动交通试探。", "full": "完整行程与来源记录",
        "full_note": "展开交通、车站与余票、住宿与锁定、天气、餐饮、位置、预算、核验期限、未知项、来源和数据源状态。",
        "noscript": "脚本未启用：以下全部日程及完整记录仍可阅读；时间试探不可用。",
        "foot": "只读；不登录、提交身份、占库存、下单、支付、取消或退改。出行前复核官方来源。",
    },
    "en": {
        "skip": "Skip to journey profile", "readonly": "Read-only plan · verify sources", "kicker": "Route, time, and decisions together",
        "days": "days", "travelers": "travelers", "route": "Cities in visit order, not a geographic map", "origin": "Origin", "first": "Confirm this leg",
        "stay": "Tonight's stay", "budget": "Budget boundary", "none_transport": "No scheduled intercity leg", "verify_service": "Verify the actual service and price for this date",
        "no_stay": "No overnight stay", "known_cost": "Comparable cost", "unknown_total": "Total still unknown; missing prices are not zero",
        "range": "Total range is stated", "context": "One day's context", "overview": "Time across the route",
        "overview_note": "One scale shows scheduled occupied time; free time stays open. Select a day for its facts.",
        "transport": "Transport", "place": "Place", "lodging": "Stay", "reference": "Hatching = reference/unverified",
        "unknown": "Red outline = specific unknown", "excluded": "Alternatives and skipped items are outside the bars", "day": "Day %d",
        "excluded_n": "%d other items outside bars", "open": "open", "scheduled": "scheduled", "prev": "← Previous day",
        "next": "Next day →", "view_overview": "View whole route ↓", "first_day": "Journey start", "last_day": "Journey end",
        "adjacent_prev": "Previous", "adjacent_next": "Next", "related": "related unknowns", "source": "Open source ↗",
        "no_slots": "No scheduled slots.", "alternatives": "Alternatives / skipped / unknown · %d", "tentative": "Alternative; outside time bar",
        "skipped": "Not included", "status_unknown": "Status unknown; outside time bar", "locked": " · fixed",
        "claim_reference": "Reference / assumption", "claim_unknown": "Needs verification", "claim_verified": "Sourced",
        "plan_only": "Plan only", "tonight": "Tonight", "no_overnight": "No overnight stay",
        "price_unknown": "Amount unknown; verify at source", "checkout": "Verify checkout amount separately",
        "live": "Current quote", "reference_price": "Reference price", "estimate": "Estimate", "click_price": "Quote to verify at source",
        "unknown_type": "Quote type unverified", "per_night": "per night", "per_person": "per person", "total": "total",
        "from": "starting from", "unit_unknown": "unit unverified", "currency_unknown": "currency unverified",
        "scenario": "What if this leg starts 30 minutes later?", "try": "Show consequence →", "undo": "Undo preview",
        "before": "Original", "after": "30 min later", "overlap": "Intersects %s (starts %s) for %d min",
        "more_overlap": "; %d more intersections, %d min of total covered overlap", "gap": "%d min remain before %s (%s)",
        "no_next": "No later slot today; further effects cannot be inferred", "already_overlap": "Original plan already overlaps by %d min; this is total overlap after the preview.",
        "caveat": "Only this proposed time block moves. This does not assert another service, rearrange later slots, or infer fares or real connections.",
        "unsupported": "No supported movable transport probe for this day.", "full": "Complete itinerary and source record",
        "full_note": "Expand transport, stations and seats, stays and fixed choices, weather, dining, locations, budget, deadlines, unknowns, evidence, and provider status.",
        "noscript": "Scripts are off: every day and the complete record remain readable; the time probe is unavailable.",
        "foot": "Read-only. No login, identity submission, inventory hold, order, payment, cancellation, or changes. Verify official sources before travel.",
    },
}


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


@lru_cache(maxsize=1)
def assets() -> tuple[str, str]:
    return ((ASSETS / "profile.css").read_text(encoding="utf-8"),
            (ASSETS / "profile.js").read_text(encoding="utf-8"))


def asset_digest() -> str:
    css, script = assets()
    payload = renderer_css().encode("utf-8") + b"\0" + css.encode("utf-8") + b"\0" + script.encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _percent(value: int, axis: Mapping[str, int]) -> float:
    return max(0.0, min(100.0, (value - axis["start"]) * 100 / (axis["end"] - axis["start"])))


def _route_heading(route: list[str]) -> str:
    parts = []
    for index, city in enumerate(route):
        cls = "route-city route-city-long" if len(city) > 8 else "route-city"
        city_html = '<span class="%s">%s</span>' % (cls, esc(city))
        parts.append(('<span class="route-step"><span class="route-arrow" aria-hidden="true">→</span>%s</span>' % city_html)
                     if index else '<span class="route-head-start">%s</span>' % city_html)
    return " ".join(parts)


def _quote(price: Mapping[str, Any] | None, labels: Mapping[str, str]) -> str:
    if not price or price.get("amount") is None:
        return labels["price_unknown"]
    kind = {"live": "live", "reference": "reference_price", "estimate": "estimate",
            "verify-on-click": "click_price"}.get(price.get("price_type"), "unknown_type")
    unit = price.get("unit") if price.get("unit") in {"per_night", "per_person", "total", "from"} else "unit_unknown"
    currency = "¥" if price.get("currency") == "CNY" else (price.get("currency") or labels["currency_unknown"]) + " "
    return "%s %s%s · %s" % (labels[kind], currency, price["amount"], labels[unit])


def _link(url: str | None, label: str) -> str:
    href = safe_href(url)
    return '<a href="%s" rel="noopener noreferrer" target="_blank">%s</a>' % (esc(href), esc(label)) if href else ""


def _bar(day: Mapping[str, Any], axis: Mapping[str, int]) -> str:
    spans = []
    for slot in day["slots"]:
        if not slot["effective"] or slot["kind"] == "free":
            continue
        left = _percent(slot["start"], axis)
        width = max(.2, _percent(slot["end"], axis) - left)
        scenario_source = ' data-scenario-source="true"' if day["scenario"].get("slot_id") == slot["id"] else ''
        spans.append('<span class="bar" data-role="%s" data-certainty="%s"%s style="left:%.3f%%;width:%.3f%%" title="%s %s–%s"></span>' %
                     (esc(slot["role"]), esc(slot["certainty"]), scenario_source, left, width,
                      esc(slot["title"]), esc(slot["start_label"]), esc(slot["end_label"])))
    scenario = day["scenario"]
    if scenario["available"]:
        moved = next(slot for slot in day["slots"] if slot["id"] == scenario["slot_id"])
        left = _percent(moved["start"] + 30, axis)
        width = max(.2, _percent(moved["end"] + 30, axis) - left)
        spans.append('<span class="preview-bar" aria-hidden="true" style="left:%.3f%%;width:%.3f%%"></span>' % (left, width))
    return '<span class="track" aria-hidden="true">%s</span>' % "".join(spans)


def _overview(model: Mapping[str, Any], labels: Mapping[str, str]) -> str:
    axis = model["axis"]
    ticks = [axis["start"]] + list(range((axis["start"] // 360 + 1) * 360, axis["end"], 360)) + [axis["end"]]
    marks = ''.join('<span class="axis-tick%s" style="left:%.3f%%">%s</span>' %
                    (' edge-start' if i == 0 else ' edge-end' if i == len(ticks)-1 else '', _percent(tick, axis), clock(tick))
                    for i, tick in enumerate(ticks))
    rows = []
    for day in model["days"]:
        side = labels["excluded_n"] % day["inactive_count"] if day["inactive_count"] else ""
        rows.append('<li><a class="day-index" href="#focus-day-%d" data-select-day="%d"%s>'
                    '<span class="day-label"><strong>%s · %s</strong><small>%s %s</small></span>%s'
                    '<span class="day-meter"><strong>%dm</strong><span>%s %dm</span></span></a></li>' %
                    (day["index"], day["index"], ' aria-current="date"' if day["index"] == 0 else '',
                     esc(day["date"]), esc(day["city"]), esc(labels["day"] % (day["index"]+1)), esc(side),
                     _bar(day, axis), day["occupied_minutes"], esc(labels["open"]), day["open_minutes"]))
    legend = ''.join('<span><i class="%s"></i>%s</span>' % (cls, esc(labels[key])) for cls, key in
                     (("", "transport"), ("place", "place"), ("stay", "lodging"), ("uncertain", "reference"), ("alert", "unknown")))
    return ('<section class="overview" aria-labelledby="overview-title"><div class="overview-head"><span class="section-id">WHOLE ROUTE</span>'
            '<h2 id="overview-title">%s</h2><p class="section-note">%s</p></div>'
            '<div class="axis-row"><span class="axis-spacer"></span><div class="axis-track">%s</div><span class="axis-spacer"></span></div>'
            '<div class="legend">%s<span class="legend-exception">%s</span></div><ol class="day-list">%s</ol></section>' %
            (esc(labels["overview"]), esc(labels["overview_note"]), marks, legend, esc(labels["excluded"]), ''.join(rows)))


def _scenario(day: Mapping[str, Any], labels: Mapping[str, str]) -> str:
    scenario = day["scenario"]
    if not scenario["available"]:
        return '<section class="try"><h4>%s</h4><p>%s</p></section>' % (esc(labels["scenario"]), esc(labels["unsupported"]))
    original, preview = scenario["baseline"], scenario["preview"]
    overlaps = preview["overlaps"]
    if overlaps:
        first = overlaps[0]
        impact = labels["overlap"] % (first["title"], first["start"], first["minutes"])
        if len(overlaps) > 1:
            impact += labels["more_overlap"] % (len(overlaps)-1, preview["overlap_minutes"])
    elif scenario["next_slot_title"]:
        if labels is LABELS["en"]:
            impact = labels["gap"] % (preview["next_gap_minutes"], scenario["next_slot_title"], scenario["next_slot_start"])
        else:
            impact = labels["gap"] % (scenario["next_slot_title"], scenario["next_slot_start"], preview["next_gap_minutes"])
    else:
        impact = labels["no_next"]
    baseline = (labels["already_overlap"] % original["overlap_minutes"]) if original["overlap_minutes"] else ""
    return ('<section class="try" data-scenario-slot="%s"><h4>%s</h4><p>%s · %s–%s</p>'
            '<button type="button" class="try-action" data-try="true">%s</button>'
            '<div class="try-result" data-try-result="true" hidden><p class="impact">%s</p><p>%s–%s</p>'
            '<p>%s</p><p class="caveat">%s</p><button type="button" class="undo" data-undo="true">%s</button></div></section>' %
            (esc(scenario["slot_id"]), esc(labels["scenario"]), esc(labels["before"]), original["depart"], original["arrive"],
             esc(labels["try"]), esc(impact), preview["depart"], preview["arrive"], esc(baseline), esc(labels["caveat"]), esc(labels["undo"])))


def _day(day: Mapping[str, Any], model: Mapping[str, Any], labels: Mapping[str, str]) -> str:
    scheduled, inactive = [], []
    scenario_id = day["scenario"].get("slot_id")
    for slot in day["slots"]:
        if not slot["effective"]:
            status = {"tentative": "tentative", "skipped": "skipped", "unknown": "status_unknown"}[slot["status"]]
            inactive.append('<li>%s · %s–%s · %s</li>' % (esc(slot["title"]), slot["start_label"], slot["end_label"], esc(labels[status])))
            continue
        original = ('<span data-original-time="true"><time datetime="%s">%s</time><small>–%s</small></span>' %
                    (esc(slot["start_at"]), slot["start_label"], slot["end_label"]))
        shifted = ''
        if slot["id"] == scenario_id:
            shifted = ('<span data-shifted-time="true" hidden><time datetime="%sT%s:00+08:00">%s</time><small>–%s</small></span>' %
                       (esc(day["date"]), day["scenario"]["preview"]["depart"],
                        day["scenario"]["preview"]["depart"], day["scenario"]["preview"]["arrive"]))
        certainty = {"needs-check": "claim_unknown", "reference": "claim_reference", "verified": "claim_verified", "plan-only": "plan_only"}[slot["certainty"]]
        scheduled.append('<li data-role="%s" data-slot-id="%s"><div class="slot-clock">%s%s</div>'
                         '<div><strong>%s</strong><span class="slot-meta">%s%s</span>%s</div></li>' %
                         (esc(slot["role"]), esc(slot["id"]), original, shifted, esc(slot["title"]),
                          esc(labels[certainty]), esc(labels["locked"] if slot["locked"] else ""), _link(slot["href"], labels["source"])))
    alternatives = ('<details class="inactive-slots"><summary>%s</summary><ul class="global-list">%s</ul></details>' %
                    (esc(labels["alternatives"] % len(inactive)), ''.join(inactive))) if inactive else ''
    issues = day["issues"]
    related = '<section class="issues"><h4>%d %s</h4><ul class="issue-list">%s</ul></section>' % (
        len(issues), esc(labels["related"]), ''.join('<li><strong>%s</strong><small>%s · %s</small>%s</li>' %
        (esc(item["title"]), esc(item["provider"]), esc(item["reason"]), _link(item["source_href"], labels["source"])) for item in issues)) if issues else ''
    price = _quote(day["stay_price"], labels) + "; " + labels["checkout"] if day["stay_name"] else labels["no_overnight"]
    known_cost = ('¥%s' % model["budget"]["known"]) if model["budget"]["known"] is not None else labels["price_unknown"]
    return ('<article class="day-detail" id="focus-day-%d" data-day-detail="%d"><div class="day-identity">'
            '<span class="number">%02d</span><div><h3>%s</h3><p>%s</p></div></div>'
            '<div class="focus-metrics"><span><strong>%dm</strong> %s</span><span><strong>%dm</strong> %s</span>'
            '<span><strong>%d</strong> %s</span></div><ol class="agenda">%s</ol>%s'
            '<div class="context"><div class="context-item"><span class="section-id">%s</span><strong>%s</strong><small>%s %s</small></div>'
            '<div class="context-item unknown"><span class="section-id">%s</span><strong>%s</strong><small>%s</small></div></div>%s%s</article>' %
            (day["index"], day["index"], day["index"]+1, esc(day["city"]), esc(day["date"]),
             day["occupied_minutes"], esc(labels["scheduled"]), day["open_minutes"], esc(labels["open"]),
             len(issues), esc(labels["related"]), ''.join(scheduled) or '<li>%s</li>' % esc(labels["no_slots"]), alternatives,
             esc(labels["tonight"]), esc(day["stay_name"] or labels["no_overnight"]), esc(price), _link(day["stay_href"], labels["source"]),
             esc(labels["budget"]), esc(known_cost), esc(labels["unknown_total"] if model["budget"]["status"] == "incomplete" else labels["range"]),
             related, _scenario(day, labels)))


def _legacy_record(legacy_html: str) -> str:
    """Reuse v1's complete visible facts without copying its rendering logic."""
    body = legacy_html.split('<body>', 1)[1].split('</body>', 1)[0]
    body = re.sub(r'^\s*<a class="skip-link"[^>]*>.*?</a>\s*', '', body, count=1, flags=re.S)
    body = body.split('<script id="trip-data"', 1)[0].split('<script id="journey-data"', 1)[0]
    body = body.replace('<main id="main-content">', '<div id="full-main">', 1).replace('</main>', '</div>', 1)
    body = body.replace('<h1>', '<h2>', 1).replace('</h1>', '</h2>', 1)
    return body


def render_profile(source: Mapping[str, Any], legacy_html: str) -> str:
    if asset_digest() != PROFILE_ASSET_SHA256:
        raise ValueError("renderer v2 assets changed without a format upgrade")
    model = build_model(source)
    locale = source["trips"][0]["request"]["locale"] if model["kind"] == "journey" else source["request"]["locale"]
    labels = LABELS[locale]
    css, script = assets()
    digest = base64.b64encode(hashlib.sha256(script.encode("utf-8")).digest()).decode("ascii")
    csp = ("default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'sha256-%s'; "
           "font-src data:; connect-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'") % digest
    first = model["days"][0]
    leg = next((slot for slot in first["slots"] if slot["effective"] and slot["kind"] == "transport"), None)
    known_cost = ('¥%s' % model["budget"]["known"]) if model["budget"]["known"] is not None else labels["price_unknown"]
    decisions = ((labels["first"], leg["title"] if leg else labels["none_transport"], labels["verify_service"]),
                 (labels["stay"], first["stay_name"] or labels["no_stay"], _quote(first["stay_price"], labels) + "; " + labels["checkout"]),
                 (labels["budget"], labels["known_cost"] + " " + known_cost,
                  labels["unknown_total"] if model["budget"]["status"] == "incomplete" else labels["range"]))
    decision_html = ''.join('<div><span>%s</span><strong>%s</strong><small>%s</small></div>' %
                            (esc(label), esc(value), esc(note)) for label, value, note in decisions)
    runs = []
    for day in model["days"]:
        if not runs or runs[-1][0] != day["city"]:
            runs.append([day["city"], day["date"], day["date"]])
        else:
            runs[-1][2] = day["date"]
    origin_only = bool(runs and model["route"][0] != runs[0][0])
    route_parts = []
    for index, city in enumerate(model["route"]):
        run_index = index - int(origin_only)
        dates = runs[run_index][1:] if run_index >= 0 and run_index < len(runs) else None
        label = dates[0] + "–" + dates[1] if dates else labels["origin"]
        route_parts.append('<li><span class="route-name">%s</span><span class="route-date">%s</span></li>' %
                           (esc(city), esc(label)))
    route_html = ''.join(route_parts)
    details = ''.join(_day(day, model, labels) for day in model["days"])
    return ('<!doctype html>\n<html lang="%s" data-renderer-version="2"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<meta name="ctw-renderer" content="2"><meta name="ctw-profile-assets" content="%s">'
            '<meta http-equiv="Content-Security-Policy" content="%s">'
            '<title>%s</title><style id="renderer-css">%s\n%s</style></head><body>'
            '<div class="topline"></div><div class="shell"><a class="skip" href="#experience">%s</a>'
            '<header class="site-head"><span class="brand">China Trip Weaver</span><span class="dataset">%s · v2</span></header>'
            '<main id="experience"><section class="hero" aria-labelledby="title"><p class="kicker">%s</p>'
            '<h1 id="title" aria-label="%s">%s</h1><p class="hero-sub">%s — %s · %s %s · %s %s</p>'
            '<ol class="route" aria-label="%s">%s</ol><div class="decision-strip">%s</div></section>'
            '<noscript><p class="noscript">%s</p></noscript><div class="workspace">'
            '<section class="focus" id="focus-column" aria-labelledby="focus-title"><div class="focus-head">'
            '<span class="section-id">SELECTED DAY</span><h2 id="focus-title">%s</h2></div>'
            '<nav class="focus-nav" aria-label="%s"><button type="button" data-prev-day="true" disabled>%s</button>'
            '<span data-day-position="true">1 / %d</span><button type="button" data-next-day="true">%s</button>'
            '<a href="#overview-title">%s</a></nav>%s</section>%s</div>'
            '<section class="record"><details id="full-record"><summary>%s</summary><p>%s</p>%s</details></section>'
            '</main><footer class="footer">%s</footer></div>'
            '<div class="live-note" id="selection-announcement" aria-live="polite"></div>'
            '<script id="prototype-model" type="application/json">%s</script>'
            '<script id="source-document" type="application/json">%s</script><script>%s</script></body></html>\n' %
            (esc(locale), PROFILE_ASSET_SHA256, esc(csp), esc(model["title"]), renderer_css(), css,
             esc(labels["skip"]), esc(labels["readonly"]),
             esc(labels["kicker"]), esc(model["title"]), _route_heading(model["route"]), esc(model["start_date"]),
             esc(model["end_date"]), esc(model["travelers"]),
             esc("traveler" if locale == "en" and model["travelers"] == 1 else labels["travelers"]),
             esc(len(model["days"])), esc("day" if locale == "en" and len(model["days"]) == 1 else labels["days"]),
             esc(labels["route"]), route_html,
             decision_html, esc(labels["noscript"]), esc(labels["context"]), esc(labels["context"]), esc(labels["prev"]),
             len(model["days"]), esc(labels["next"]), esc(labels["view_overview"]), details, _overview(model, labels),
             esc(labels["full"]), esc(labels["full_note"]), _legacy_record(legacy_html), esc(labels["foot"]),
             embedded_json(model), embedded_json(source), script))
