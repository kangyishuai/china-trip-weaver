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
PROFILE_ASSET_SHA256 = "d1ab44cdae4f27908671d41135746128bb35bbd177622cb89238144564e663a4"

LABELS = {
    "zh-CN": {
        "locale": "zh-CN",
        "skip": "跳到当天安排", "readonly": "只读行程", "kicker": "路线、时间、决定，在同一视野",
        "days": "天", "travelers": "人", "route": "按顺序经过的城市，非地理地图", "origin": "出发地", "first": "先确认这段交通",
        "stay": "当晚落点", "budget": "预算边界", "none_transport": "没有已排跨城交通", "verify_service": "按日期复核实际交通服务与价格",
        "no_stay": "这一天无过夜住宿", "known_cost": "可比较金额", "unknown_total": "总额仍未知；缺价不按零计算",
        "range": "总额范围已列出", "context": "当天安排", "overview": "全程时间图",
        "overview_note": "同一刻度展示已排占用；留白是未安排时间。选一天看具体安排。",
        "transport": "交通", "place": "地点", "lodging": "住宿", "meal": "用餐", "rest": "休息", "open_legend": "留白＝未安排",
        "reference": "斜纹＝静态/待证",
        "unknown": "红框＝具体未知", "excluded": "备选／未采用不计入横带", "day": "第 %d 天", "excluded_n": "另有 %d 条未纳入图带",
        "print_reference": "虚线＝静态/待证", "print_unknown": "双框＝具体未知",
        "print_legend_note": "每行下方重复刻度，并列出原时刻、类别与依据状态。",
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
        "noscript": "脚本未启用：以下全部日程及完整记录仍可阅读；时间试探不可用。若浏览器打印时未自动展开来源，请先手动展开再打印。",
        "foot": "只读；不登录、提交身份、占库存、下单、支付、取消或退改。出行前复核官方来源。",
        "first_action": "先核对", "other_decisions": "住宿与预算", "route_details": "城市与停留日期",
        "no_leg_action": "查看当天安排与未定事项",
        "budget_pending": "总额待核验", "budget_empty": "尚无可比较报价；已知部分 ¥0，缺价不按零计算",
        "budget_unavailable": "可比较金额尚待核对；总费用不能按零计算",
        "budget_zero_quoted": "已有 %d 项零元可比报价；已知部分 ¥0，其他费用仍待核验",
        "budget_partial": "已可比较 ¥%s；仍有缺价，不能当作总额", "budget_final": "已知总额 ¥%s",
        "budget_complete_range": "总额区间 ¥%s–¥%s",
        "issue_heading": "出发前要核对", "issue_all": "查看全部 %d 条原始记录与来源",
        "issue_jump": "查看 %d 条核验依据 ↓", "issue_none": "当天没有关联的未知记录",
        "issue_more": "其他主题还有 %d 条", "issue_urgent": "其中 %d 条来源冲突、失效或不可用",
        "topic_service": "交通服务信息", "topic_transport": "交通费用与衔接",
        "topic_stay": "住宿报价与条件", "topic_budget": "预算缺价",
        "topic_place": "地点与用餐信息", "topic_other": "其他未定信息",
        "issue_origin": "原始记录", "page_format": "页面格式 v2",
    },
    "en": {
        "locale": "en",
        "skip": "Skip to today's plan", "readonly": "Read-only plan", "kicker": "Route, time, and decisions together",
        "days": "days", "travelers": "travelers", "route": "Cities in visit order, not a geographic map", "origin": "Origin", "first": "Confirm this leg",
        "stay": "Tonight's stay", "budget": "Budget boundary", "none_transport": "No scheduled intercity leg", "verify_service": "Verify dated transport service and price",
        "no_stay": "No overnight stay", "known_cost": "Comparable cost", "unknown_total": "Total still unknown; missing prices are not zero",
        "range": "Total range is stated", "context": "Today's plan", "overview": "Whole-route time",
        "overview_note": "One scale shows scheduled occupied time; blank space is unplanned. Select a day for details.",
        "transport": "Transport", "place": "Place", "lodging": "Stay", "meal": "Meal", "rest": "Rest", "open_legend": "Blank = unplanned",
        "reference": "Hatching = reference/unverified",
        "unknown": "Red outline = specific unknown", "excluded": "Alternatives and skipped items are outside the bars", "day": "Day %d",
        "print_reference": "Dashed outline = reference/unverified", "print_unknown": "Double outline = specific unknown",
        "print_legend_note": "Each row repeats the scale and lists original times, categories, and evidence status.",
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
        "noscript": "Scripts are off: every day and the complete record remain readable; the time probe is unavailable. If your browser does not expand sources for print, open them before printing.",
        "foot": "Read-only. No login, identity submission, inventory hold, order, payment, cancellation, or changes. Verify official sources before travel.",
        "first_action": "Confirm first", "other_decisions": "Stay and budget", "route_details": "Cities and stay dates",
        "no_leg_action": "Review this day's plan and open details",
        "budget_pending": "Total to verify", "budget_empty": "No comparable quote yet; known part ¥0, missing prices are not zero",
        "budget_unavailable": "Comparable amount needs checking; the total cannot be treated as zero",
        "budget_zero_quoted": "%d comparable zero-priced %s; known part ¥0, other costs remain unverified",
        "budget_partial": "Comparable part ¥%s; missing prices prevent a total", "budget_final": "Known total ¥%s",
        "budget_complete_range": "Total range ¥%s–¥%s",
        "issue_heading": "Check before travel", "issue_all": "View all %d source records",
        "issue_jump": "View %d source records ↓", "issue_none": "No related unknown records for this day",
        "issue_more": "%d more records in other topics", "issue_urgent": "%d conflicting, stale, or unavailable sources",
        "topic_service": "Transport service details", "topic_transport": "Transport cost and connection",
        "topic_stay": "Stay price and terms", "topic_budget": "Budget price gaps",
        "topic_place": "Place and dining details", "topic_other": "Other open details",
        "issue_origin": "Raw record", "page_format": "Page format v2",
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


def _duration(minutes: int, locale: str, compact: bool = False) -> str:
    hours, rest = divmod(minutes, 60)
    if locale == 'zh-CN':
        if hours:
            return ('%d时%d分' if compact else '%d小时%d分钟') % (hours, rest) if rest else '%d小时' % hours
        return ('%d分' if compact else '%d分钟') % rest
    if hours:
        return '%dh %dm' % (hours, rest) if rest else '%dh' % hours
    return '%dm' % rest


def _budget_summary(model: Mapping[str, Any], labels: Mapping[str, str]) -> tuple[str, str]:
    budget = model['budget']
    known = budget['known']
    minimum, maximum = budget['minimum'], budget['maximum']
    if minimum is None or maximum is None:
        comparable_count = budget.get('comparable_count')
        if known is None:
            detail = labels['budget_unavailable']
        elif known == 0:
            if comparable_count is None:
                detail = labels['budget_unavailable']
            elif comparable_count:
                detail = (labels['budget_zero_quoted'] % comparable_count) if labels['locale'] == 'zh-CN' else (
                    labels['budget_zero_quoted'] % (comparable_count, 'item' if comparable_count == 1 else 'items'))
            else:
                detail = labels['budget_empty']
        else:
            detail = labels['budget_partial'] % known
        return labels['budget_pending'], detail
    if minimum != maximum:
        return labels['range'], labels['budget_complete_range'] % (minimum, maximum)
    return labels['budget_final'] % maximum, labels['range']


def _link(url: str | None, label: str) -> str:
    href = safe_href(url)
    return '<a href="%s" rel="noopener noreferrer" target="_blank">%s</a>' % (esc(href), esc(label)) if href else ""


def _bar(day: Mapping[str, Any], axis: Mapping[str, int]) -> str:
    spans = []
    for slot in _charted_slots(day):
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


def _charted_slots(day: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [slot for slot in day["slots"] if slot["effective"] and slot["kind"] != "free"]


def _print_intervals(day: Mapping[str, Any], labels: Mapping[str, str]) -> str:
    certainty_labels = {"needs-check": "claim_unknown", "reference": "claim_reference",
                        "verified": "claim_verified", "plan-only": "plan_only"}
    spans = []
    for slot in _charted_slots(day):
        role = "lodging" if slot["role"] == "stay" else slot["role"]
        spans.append('<span class="print-interval" data-slot-id="%s" data-role="%s" data-certainty="%s">%s–%s · %s · %s</span>' % (
            esc(slot["id"]), esc(slot["role"]), esc(slot["certainty"]),
            esc(slot["start_label"]), esc(slot["end_label"]),
            esc(labels.get(role, slot["role"])), esc(labels[certainty_labels[slot["certainty"]]])))
    return '<span class="print-intervals">%s</span>' % ''.join(spans)


def _overview(model: Mapping[str, Any], labels: Mapping[str, str], route_html: str) -> str:
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
                    '<span class="print-row-axis" aria-hidden="true">%s</span>%s'
                    '<span class="day-meter"><strong>%s</strong><span>%s %s</span></span></a></li>' %
                    (day["index"], day["index"], ' aria-current="date"' if day["index"] == 0 else '',
                     esc(day["date"]), esc(day["city"]), esc(labels["day"] % (day["index"]+1)), esc(side),
                     _bar(day, axis), marks, _print_intervals(day, labels),
                     esc(_duration(day["occupied_minutes"], labels["locale"], True)),
                     esc(labels["open"]), esc(_duration(day["open_minutes"], labels["locale"], True))))
    legend = ''.join('<span><i class="%s"></i>%s</span>' % (
        cls, ('<span class="screen-legend">%s</span><span class="print-only">%s</span>' % (
            esc(labels[key]), esc(labels['print_' + key])) if key in ('reference', 'unknown') else esc(labels[key])))
        for cls, key in (("", "transport"), ("place", "place"), ("stay", "lodging"), ("meal", "meal"),
                         ("rest", "rest"), ("uncertain", "reference"), ("alert", "unknown")))
    return ('<section class="overview" aria-labelledby="overview-title"><div class="overview-head">'
            '<h2 id="overview-title">%s</h2><p class="section-note">%s</p></div>'
            '<details class="route-details"><summary>%s</summary>%s</details>'
            '<div class="axis-row"><span class="axis-spacer"></span><div class="axis-track">%s</div><span class="axis-spacer"></span></div>'
            '<div class="legend">%s<span class="legend-exception">%s · %s</span>'
            '<span class="print-legend-note">%s</span></div><ol class="day-list">%s</ol></section>' %
            (esc(labels["overview"]), esc(labels["overview_note"]), esc(labels["route_details"]), route_html,
             marks, legend, esc(labels["open_legend"]), esc(labels["excluded"]),
             esc(labels["print_legend_note"]), ''.join(rows)))


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


def _issue_topic(item: Mapping[str, Any]) -> str:
    path = item['field_path']
    if '/transport_legs/' in path:
        return 'service' if path.endswith(('/service_number', '/availability')) else 'transport'
    if '/lodgings/' in path:
        return 'stay'
    if '/budget_ledger/' in path:
        return 'budget'
    if '/pois/' in path:
        return 'place'
    return 'other'


def _issue_count(value: int, locale: str, full: bool = False) -> str:
    if locale == 'zh-CN':
        return '%d 条%s' % (value, '原始记录' if full else '')
    return '%d %s%s' % (value, 'source ' if full else '', 'record' if value == 1 else 'records')


def _issues(day: Mapping[str, Any], labels: Mapping[str, str]) -> tuple[str, str]:
    issues = day['issues']
    heading = '%s · %s' % (day['date'], day['city'])
    support_start = '<article class="issue-support" id="support-day-%d" data-day-support="%d"><h2>%s</h2>' % (
        day['index'], day['index'], esc(heading))
    if not issues:
        return '', support_start + '<p>%s</p></article>' % esc(labels['issue_none'])
    ordered = ('service', 'stay', 'transport', 'budget', 'place', 'other')
    groups = {topic: [item for item in issues if _issue_topic(item) == topic] for topic in ordered}
    present = [topic for topic in ordered if groups[topic]]
    highlights = ''.join('<li><span>%s</span><small>%s</small></li>' % (
        esc(labels['topic_' + topic]), esc(_issue_count(len(groups[topic]), labels['locale'])))
        for topic in present[:3])
    remaining = len(issues) - sum(len(groups[topic]) for topic in present[:3])
    remaining_text = ('<p class="issue-remaining">%s</p>' % esc(labels['issue_more'] % remaining)) if remaining else ''
    urgent = sum(item['claim_status'] in ('conflict', 'stale', 'unavailable') for item in issues)
    urgent_text = ('<p class="issue-urgent">%s</p>' % esc(labels['issue_urgent'] % urgent)) if urgent else ''
    sections = []
    for topic in present:
        rows = []
        for item in groups[topic]:
            trace = ' · '.join(str(value) for value in (item['id'], item['field_path'], item['claim_id'], item['claim_status']) if value)
            source = _link(item['source_href'], labels['source'])
            rows.append('<li data-issue-id="%s" data-claim-status="%s"><strong>%s</strong>'
                        '<small class="issue-provider">%s</small><p class="issue-reason">%s</p>'
                        '<code class="issue-trace">%s</code>%s</li>' % (
                            esc(item['id']), esc(item['claim_status']), esc(item['title']),
                            esc(item['provider']), esc(item['reason']), esc(trace),
                            '<div class="issue-source">%s</div>' % source if source else ''))
        sections.append('<section class="issue-group" data-issue-topic="%s"><h3>%s · %d</h3>'
                        '<ol class="issue-list">%s</ol></section>' % (
                            esc(topic), esc(labels['topic_' + topic]), len(groups[topic]), ''.join(rows)))
    summary = ('<section class="issues" aria-label="%s"><div class="issues-head"><h4>%s</h4>'
            '<span>%s</span></div><ul class="issue-highlights">%s</ul>%s%s'
            '<a class="issue-jump" href="#support-day-%d">%s</a></section>' % (
                esc(labels['issue_heading']), esc(labels['issue_heading']),
                esc(_issue_count(len(issues), labels['locale'], True)), highlights,
                remaining_text, urgent_text, day['index'], esc(labels['issue_jump'] % len(issues))))
    evidence = support_start + ('<details class="issue-details"><summary>%s</summary>'
                                '<div class="issue-groups">%s</div></details></article>' % (
                                    esc(labels['issue_all'] % len(issues)), ''.join(sections)))
    return summary, evidence


def _day(day: Mapping[str, Any], model: Mapping[str, Any], labels: Mapping[str, str]) -> str:
    scheduled, inactive = [], []
    scenario_id = day["scenario"].get("slot_id")
    for slot in day["slots"]:
        if not slot["effective"]:
            status = {"tentative": "tentative", "skipped": "skipped", "unknown": "status_unknown"}[slot["status"]]
            inactive.append('<li>%s · %s–%s · %s</li>' % (esc(slot["title"]), slot["start_label"], slot["end_label"], esc(labels[status])))
            continue
        moving = slot["id"] == scenario_id
        original = ('<span data-original-time="true"%s><time datetime="%s">%s</time><small>–%s</small></span>' %
                    (' data-scenario-original="true"' if moving else '',
                     esc(slot["start_at"]), slot["start_label"], slot["end_label"]))
        shifted = ''
        if moving:
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
    related, _ = _issues(day, labels)
    separator = '；' if labels['locale'] == 'zh-CN' else '; '
    price = _quote(day["stay_price"], labels) + separator + labels["checkout"] if day["stay_name"] else labels["no_overnight"]
    budget_title, budget_detail = _budget_summary(model, labels)
    return ('<article class="day-detail" id="focus-day-%d" data-day-detail="%d"><div class="day-identity">'
            '<span class="number">%02d</span><div><h3 tabindex="-1">%s</h3><p>%s</p></div></div>'
            '<div class="focus-metrics"><span><strong>%s</strong> %s</span><span><strong>%s</strong> %s</span>'
            '<span><strong>%d</strong> %s</span></div><ol class="agenda">%s</ol>%s'
            '<div class="context"><div class="context-item"><span class="section-id">%s</span><strong>%s</strong><small>%s %s</small></div>'
            '<div class="context-item unknown"><span class="section-id">%s</span><strong>%s</strong><small>%s</small></div></div>%s%s</article>' %
            (day["index"], day["index"], day["index"]+1, esc(day["city"]), esc(day["date"]),
             esc(_duration(day["occupied_minutes"], labels['locale'])), esc(labels["scheduled"]),
             esc(_duration(day["open_minutes"], labels['locale'])), esc(labels["open"]),
             len(issues), esc(labels["related"]), ''.join(scheduled) or '<li>%s</li>' % esc(labels["no_slots"]), alternatives,
             esc(labels["tonight"]), esc(day["stay_name"] or labels["no_overnight"]), esc(price), _link(day["stay_href"], labels["source"]),
             esc(labels["budget"]), esc(budget_title), esc(budget_detail),
             related, _scenario(day, labels)))


def _legacy_record(legacy_html: str) -> str:
    """Reuse v1's complete visible facts without copying its rendering logic."""
    body = legacy_html.split('<body>', 1)[1].split('</body>', 1)[0]
    body = re.sub(r'^\s*<a class="skip-link"[^>]*>.*?</a>\s*', '', body, count=1, flags=re.S)
    body = body.split('<script id="trip-data"', 1)[0].split('<script id="journey-data"', 1)[0]
    for pattern in (r'<header class="page-header" data-section="header">.*?</header>\s*',
                    r'<aside class="truth-banner" data-section="truth-banner"[^>]*>.*?</aside>\s*'):
        body, removed = re.subn(pattern, '', body, count=1, flags=re.S)
        if removed != 1:
            raise ValueError('v1 record shell cannot be reduced safely')
    body = body.replace('<main id="main-content">', '<div id="full-main">', 1).replace('</main>', '</div>', 1)
    return body


def _record_context(source: Mapping[str, Any], model: Mapping[str, Any], locale: str) -> str:
    """Keep the unique v1 header/banner facts readable before the retained record."""
    from .html import HEALTH_RISK_ORDER, _enum_label, _labels, _provider_label, _time

    labels = _labels(locale)
    copy = {
        'zh-CN': ('记录范围与真实性', '记录', '人', '天', '段', '修订', '生成于', '数据口径',
                  '未知记录', '当前最弱数据源', '预订与核验清单', '风险记录', '演示数据提示'),
        'en': ('Record scope and source limits', 'Record', 'traveler', 'day', 'segment', 'Revision',
               'Generated', 'Data modes', 'unresolved records', 'Most limited source',
               'booking/verification entries', 'risk records', 'Demo notice'),
    }[locale]
    (heading, record, person, day, segment, revision, generated, mode,
     unknown, weakest, checklist, risk, mock) = copy
    travelers, day_count = model['travelers'], len(model['days'])
    person_unit = person + ('s' if locale == 'en' and travelers != 1 else '')
    day_unit = day + ('s' if locale == 'en' and day_count != 1 else '')
    if locale == 'zh-CN':
        scope = '记录：%s · %s — %s · %d 人／%d 天' % (
            model['title'], model['start_date'], model['end_date'], travelers, day_count)
    else:
        scope = '%s: %s · %s — %s · %d %s / %d %s' % (
            record, model['title'], model['start_date'], model['end_date'],
            travelers, person_unit, day_count, day_unit)
    if model['kind'] == 'journey':
        count = len(source['trips'])
        segment_unit = segment + ('s' if locale == 'en' and count != 1 else '')
        scope += ('／%d 段' % count) if locale == 'zh-CN' else (' / %d %s' % (count, segment_unit))
        modes = list(dict.fromkeys(trip['mode'] for trip in source['trips']))
        mode_text = ' / '.join(_enum_label(labels, 'mode', item) for item in modes)
        exception = ('预订与核验清单 %d 条；风险记录 %d 条' %
                     (len(model['checklist']), len(model['risk_items']))) if locale == 'zh-CN' else (
                     '%d %s; %d %s' % (len(model['checklist']), checklist, len(model['risk_items']), risk))
    else:
        mode_text = _enum_label(labels, 'mode', source['mode'])
        if locale == 'en':
            mode = 'Data mode'
        worst = max(source['provider_health'], key=lambda item: (
            HEALTH_RISK_ORDER.get(item['status'], 99), item['provider']))
        provider = _provider_label(labels, worst['provider'])
        status = _enum_label(labels, 'health_status', worst['status'])
        exception = ('未知记录 %d 条；当前最弱数据源：%s（%s）' %
                     (len(source['unknowns']), provider, status)) if locale == 'zh-CN' else (
                     '%d %s; %s: %s (%s)' % (len(source['unknowns']), unknown, weakest, provider, status))
    notice = ('<p data-mock-notice="true"><strong>%s:</strong> %s</p>' %
              (esc(mock), esc(source['mock_notice']))) if model['kind'] == 'trip' and source['mode'] == 'mock' else ''
    metadata = ('%s %s · %s %s · %s%s %s' % (
        revision, source['revision']['number'], generated, _time(source['generated_at']),
        mode, '：' if locale == 'zh-CN' else ':', esc(mode_text)))
    return ('<section class="record-context" data-section="record-context" aria-labelledby="truth-heading">'
            '<h2 id="truth-heading">%s</h2><p>%s</p>'
            '<p>%s</p><p>%s</p>%s</section>' % (
                esc(heading), esc(scope), metadata, esc(exception), notice))


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
    budget_title, budget_detail = _budget_summary(model, labels)
    separator = '；' if locale == 'zh-CN' else '; '
    decisions = ((labels["stay"], first["stay_name"] or labels["no_stay"],
                  _quote(first["stay_price"], labels) + separator + labels["checkout"]),
                 (labels["budget"], budget_title, budget_detail))
    decision_html = ('<div class="primary-decision"><span>%s</span><strong>%s</strong><small>%s</small></div>'
                     '<details class="decision-details"><summary>%s</summary><div class="decision-strip">%s</div></details>' % (
                         esc(labels["first_action"]), esc(leg["title"] if leg else labels["none_transport"]),
                         esc(labels["verify_service"] if leg else labels["no_leg_action"]),
                         esc(labels["other_decisions"]),
                         ''.join('<div><span>%s</span><strong>%s</strong><small>%s</small></div>' %
                                 (esc(label), esc(value), esc(note)) for label, value, note in decisions)))
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
    supports = ''.join(_issues(day, labels)[1] for day in model['days'])
    route_size = 'short' if len(model['days']) <= 5 else 'long'
    return ('<!doctype html>\n<html lang="%s" data-renderer-version="2"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<meta name="ctw-renderer" content="2"><meta name="ctw-profile-assets" content="%s">'
            '<meta http-equiv="Content-Security-Policy" content="%s">'
            '<title>%s</title><style id="renderer-css">%s\n%s</style></head><body>'
            '<div class="topline"></div><div class="shell"><a class="skip" href="#experience">%s</a>'
            '<header class="site-head"><span class="brand">China Trip Weaver</span><span class="dataset">%s</span></header>'
            '<main id="experience" data-route-size="%s"><section class="hero" aria-labelledby="title">'
            '<h1 id="title" aria-label="%s">%s</h1><p class="hero-sub">%s — %s · %s %s · %s %s</p>'
            '%s</section><noscript><p class="noscript">%s</p></noscript><div class="workspace" data-route-size="%s">'
            '<section class="focus" id="focus-column" aria-labelledby="focus-title"><div class="focus-head">'
            '<h2 id="focus-title">%s</h2></div>'
            '<nav class="focus-nav" aria-label="%s"><button type="button" data-prev-day="true" disabled>%s</button>'
            '<span data-day-position="true">1 / %d</span><button type="button" data-next-day="true">%s</button>'
            '<a href="#overview-title">%s</a></nav>%s</section>%s</div>'
            '<section class="support-collection" aria-label="%s">%s</section>'
            '<section class="record"><details id="full-record"><summary>%s</summary><p>%s</p>%s%s</details></section>'
            '</main><footer class="footer">%s <small>%s</small></footer></div>'
            '<div class="live-note" id="selection-announcement" aria-live="polite"></div>'
            '<script id="prototype-model" type="application/json">%s</script>'
            '<script id="source-document" type="application/json">%s</script><script>%s</script></body></html>\n' %
            (esc(locale), PROFILE_ASSET_SHA256, esc(csp), esc(model["title"]), renderer_css(), css,
             esc(labels["skip"]), esc(labels["readonly"]), route_size,
             esc(model["title"]), _route_heading(model["route"]), esc(model["start_date"]),
             esc(model["end_date"]), esc(model["travelers"]),
             esc("traveler" if locale == "en" and model["travelers"] == 1 else labels["travelers"]),
             esc(len(model["days"])), esc("day" if locale == "en" and len(model["days"]) == 1 else labels["days"]),
             decision_html, esc(labels["noscript"]), route_size,
             esc(labels["context"]), esc(labels["context"]), esc(labels["prev"]),
             len(model["days"]), esc(labels["next"]), esc(labels["view_overview"]), details,
             _overview(model, labels, '<ol class="route" aria-label="%s">%s</ol>' % (esc(labels["route"]), route_html)),
             esc(labels['issue_heading']), supports,
             esc(labels["full"]), esc(labels["full_note"]), _record_context(source, model, locale),
             _legacy_record(legacy_html), esc(labels["foot"]), esc(labels["page_format"]),
             embedded_json(model), embedded_json(source), script))
