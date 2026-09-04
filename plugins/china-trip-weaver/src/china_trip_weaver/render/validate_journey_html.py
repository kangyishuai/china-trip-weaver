"""Post-render gate for the deterministic Journey overview page."""

from __future__ import annotations

import json
import re
from typing import Any, List, Mapping, Sequence
from urllib.parse import urlsplit

from ..contracts import canonical_json
from ..journey import journey_booking_checklist, journey_risk_items
from .journey_html import JOURNEY_SECTIONS
from .template import CSP, FORBIDDEN_QUERY_KEYS
from .validate_html import (
    AuditParser,
    DISALLOWED_TAGS,
    HTMLIssue,
    HTMLValidationReport,
    SECRET_PATTERNS,
    _csp,
    _css_contract,
    _number,
)


def validate_journey_html(
    html_text: str,
    journey: Mapping[str, Any],
) -> HTMLValidationReport:
    """Validate a Journey page against its source and the shared offline shell."""

    parser = AuditParser()
    try:
        parser.feed(html_text)
        parser.close()
    except Exception as exc:
        return HTMLValidationReport((HTMLIssue("JH001", "HTML parse failed: %s" % exc),))

    locale = journey["trips"][0]["request"]["locale"]
    issues: List[HTMLIssue] = list(_shared_document_issues(
        parser,
        html_text,
        embedded_id="journey-data",
        embedded_value=journey,
        locale=locale,
        required_sections=JOURNEY_SECTIONS,
    ))

    def add(code: str, message: str) -> None:
        issues.append(HTMLIssue(code, message))

    expected_segments = list(journey["trips"])
    segment_nodes = [
        attrs for _, attrs in parser.all_attrs
        if "data-segment-index" in attrs
    ]
    route_nodes = [
        attrs for _, attrs in parser.all_attrs
        if "data-route-index" in attrs
    ]
    if len(segment_nodes) != len(expected_segments) or len(route_nodes) != len(expected_segments):
        add("JH201", "route and segment coverage differs from Journey Trips")
    else:
        for index, trip in enumerate(expected_segments):
            expected = {
                "data-trip-id": str(trip["trip_id"]),
                "data-start-date": str(trip["request"]["start_date"]),
                "data-end-date": str(trip["request"]["end_date"]),
            }
            route_expected = dict(expected)
            route_expected["data-route-trip-id"] = route_expected.pop("data-trip-id")
            route_expected["data-route-index"] = str(index)
            segment_expected = dict(expected)
            segment_expected["data-segment-index"] = str(index)
            segment_expected["data-day-count"] = str(len(trip["days"]))
            if any(route_nodes[index].get(key) != value for key, value in route_expected.items()):
                add("JH201", "route facts differ from Journey Trip %d" % index)
            if any(segment_nodes[index].get(key) != value for key, value in segment_expected.items()):
                add("JH201", "segment facts differ from Journey Trip %d" % index)

    connection_nodes = [
        attrs for _, attrs in parser.all_attrs
        if "data-connection-index" in attrs
    ]
    if len(connection_nodes) != len(journey["segment_connections"]):
        add("JH201", "connection coverage differs from Journey")
    else:
        for index, connection in enumerate(journey["segment_connections"]):
            expected = {
                "data-connection-index": str(index),
                "data-connection-id": connection["connection_id"],
                "data-from-trip-id": connection["from_trip_id"],
                "data-to-trip-id": connection["to_trip_id"],
            }
            if any(connection_nodes[index].get(key) != value for key, value in expected.items()):
                add("JH201", "connection facts differ at index %d" % index)

    health_nodes = [
        attrs for _, attrs in parser.all_attrs
        if "data-health-trip-index" in attrs
    ]
    expected_health = [
        (trip_index, health)
        for trip_index, trip in enumerate(journey["trips"])
        for health in trip["provider_health"]
    ]
    if len(health_nodes) != len(expected_health):
        add("JH201", "provider health coverage differs from Journey Trips")
    else:
        for index, (trip_index, health) in enumerate(expected_health):
            expected = {
                "data-health-trip-index": str(trip_index),
                "data-provider": health["provider"],
                "data-provider-mode": health["mode"],
                "data-provider-status": health["status"],
            }
            if any(health_nodes[index].get(key) != value for key, value in expected.items()):
                add("JH201", "provider health facts differ at index %d" % index)

    checklist = journey_booking_checklist(journey)
    checklist_nodes = [
        attrs for _, attrs in parser.all_attrs
        if attrs.get("data-checklist-id")
    ]
    _validate_trace_nodes(
        checklist_nodes,
        checklist,
        "checklist",
        "JH202",
        add,
    )

    risks = journey_risk_items(journey)
    risk_nodes = [
        attrs for _, attrs in parser.all_attrs
        if attrs.get("data-risk-id")
    ]
    _validate_trace_nodes(risk_nodes, risks, "risk", "JH203", add)

    budget_nodes = [
        attrs for _, attrs in parser.all_attrs
        if "data-budget-currency" in attrs
    ]
    ledger = journey["budget_ledger"]
    total = ledger["total_range_cny"]
    expected_budget = {
        "data-budget-currency": ledger["currency"],
        "data-budget-known": _number(ledger["known_cost_cny"]),
        "data-budget-min": "" if total["minimum"] is None else _number(total["minimum"]),
        "data-budget-max": "" if total["maximum"] is None else _number(total["maximum"]),
        "data-budget-limit": "" if ledger["budget_cny"] is None else _number(ledger["budget_cny"]),
        "data-budget-status": ledger["status"],
    }
    if len(budget_nodes) != 1 or any(
        budget_nodes[0].get(key) != str(value)
        for key, value in expected_budget.items()
    ):
        add("JH204", "rendered total budget facts differ from Journey ledger")

    visible = " ".join(parser.visible_text)
    route_cities = {
        day["city"] for trip in journey["trips"] for day in trip["days"]
    }
    if any(city not in visible for city in route_cities):
        add("JH201", "a Journey route city is absent from visible text")
    origin_names = (
        [group["origin"]["name"] for group in journey["traveler_groups"]]
        if journey.get("traveler_groups")
        else [journey["origin"]["name"]] if journey.get("origin") else []
    )
    if any(name not in visible for name in origin_names):
        add("JH201", "a Journey origin is absent from visible text")

    internal_ids = {
        journey["journey_id"],
        *(connection["connection_id"] for connection in journey["segment_connections"]),
        *(item["item_id"] for item in checklist),
        *(item["item_id"] for item in risks),
    }
    for trip in journey["trips"]:
        internal_ids.add(trip["trip_id"])
        internal_ids.update(day["day_id"] for day in trip["days"])
        internal_ids.update(
            slot["slot_id"] for day in trip["days"] for slot in day["slots"]
        )
        internal_ids.update(item["leg_id"] for item in trip["transport_legs"])
        internal_ids.update(item["lodging_id"] for item in trip["lodgings"])
        internal_ids.update(item["poi_id"] for item in trip["pois"])
        internal_ids.update(item["claim_id"] for item in trip["claims"])
    leaked = sorted(identifier for identifier in internal_ids if identifier and identifier in visible)
    raw_states = sorted(set(re.findall(
        r"(?<![A-Za-z0-9_-])(scheduled|tentative)(?![A-Za-z0-9_-])",
        visible,
        re.IGNORECASE,
    )))
    if leaked or raw_states:
        detail = leaked[0] if leaked else raw_states[0]
        add("JH205", "visible text exposes an internal id or raw state: %s" % detail)

    return HTMLValidationReport(tuple(sorted(set(issues))))


def _validate_trace_nodes(
    nodes: Sequence[Mapping[str, str]],
    expected_items: Sequence[Mapping[str, Any]],
    prefix: str,
    code: str,
    add: Any,
) -> None:
    if len(nodes) != len(expected_items):
        add(code, "%s coverage differs from derived Journey items" % prefix)
        return
    for index, (node, item) in enumerate(zip(nodes, expected_items)):
        expected = {
            "data-%s-id" % prefix: item["item_id"],
            "data-%s-kind" % prefix: item["kind"],
            "data-trip-index": str(item["trip_index"]),
            "data-source-kind": item["source_kind"],
            "data-source-ref": item["source_ref"],
            "data-source-claim": item.get("claim_id") or "",
            "data-source-path": item.get("field_path") or "",
            "data-deadline": item["deadline"],
        }
        if item.get("capability"):
            expected["data-capability"] = item["capability"]
        if item.get("status"):
            expected["data-risk-status"] = item["status"]
        if any(node.get(key) != str(value) for key, value in expected.items()):
            add(code, "%s trace or ordering differs at index %d" % (prefix, index))
        if not item.get("source_ref") and not item.get("claim_id"):
            add(code, "%s item is not traceable at index %d" % (prefix, index))


def _shared_document_issues(
    parser: AuditParser,
    html_text: str,
    *,
    embedded_id: str,
    embedded_value: Mapping[str, Any],
    locale: str,
    required_sections: Sequence[str],
) -> Sequence[HTMLIssue]:
    """Apply the Trip renderer's exact shell, CSP, URL, and secret policy."""

    issues: List[HTMLIssue] = []

    def add(code: str, message: str) -> None:
        issues.append(HTMLIssue(code, message))

    html_attrs = next((attrs for tag, attrs in parser.all_attrs if tag == "html"), {})
    charset = any(meta.get("charset", "").lower() == "utf-8" for meta in parser.metas)
    viewport = any(
        meta.get("name", "").lower() == "viewport"
        and meta.get("content") == "width=device-width, initial-scale=1"
        for meta in parser.metas
    )
    if (
        not parser.doctype
        or not charset
        or not viewport
        or html_attrs.get("lang") != locale
        or parser.tags["main"] != 1
        or parser.tags["h1"] != 1
    ):
        add("JH001", "doctype/charset/viewport/lang/unique main+h1 contract failed")

    data_scripts = [
        item for item in parser.scripts
        if item["attrs"].get("id") == embedded_id
    ]
    if len(data_scripts) != 1 or len(parser.scripts) != 1:
        add("JH002", "%s must be the only script element" % embedded_id)
    else:
        script = data_scripts[0]
        if script["attrs"].get("type") != "application/json" or script["attrs"].get("src"):
            add("JH002", "%s MIME/src is invalid" % embedded_id)
        try:
            embedded = json.loads(script["content"])
            if canonical_json(embedded) != canonical_json(embedded_value):
                add("JH002", "embedded Journey is not canonical-equal to input")
        except json.JSONDecodeError:
            add("JH002", "embedded Journey cannot be parsed")
        if "</script" in script["content"].lower():
            add("JH103", "embedded JSON can close the script element")

    if any(count != 1 for count in parser.ids.values()):
        add("JH004", "duplicate DOM id")
    for attrs in parser.links:
        href = attrs.get("href", "")
        if href.startswith("#") and href[1:] not in parser.ids:
            add("JH004", "broken internal anchor: %s" % href)
    previous = 0
    for level in parser.headings:
        if previous and level > previous + 1:
            add("JH004", "heading level jumps from h%d to h%d" % (previous, level))
            break
        previous = level
    if set(parser.sections) != set(required_sections) or any(
        count != 1 for count in parser.sections.values()
    ):
        add("JH005", "required Journey information architecture is incomplete")

    for tag, attrs in parser.all_attrs:
        if tag in DISALLOWED_TAGS or any(name.lower().startswith("on") for name in attrs):
            add("JH101", "executable/interactive element or event handler is forbidden")
            break
        if tag == "script" and attrs.get("id") != embedded_id:
            add("JH101", "executable script is forbidden")
        if tag == "link" and attrs.get("rel", "").lower() == "stylesheet":
            add("JH101", "remote/external stylesheet is forbidden")
        if tag == "img" and attrs.get("src") and not attrs["src"].startswith("data:"):
            add("JH101", "remote image is forbidden")
        if attrs.get("contenteditable") not in (None, "", "false"):
            add("JH101", "contenteditable is forbidden")
    css = "\n".join(parser.styles)
    if re.search(
        r"(?i)@import|url\s*\(\s*['\"]?(?:https?:)?//|fetch\s*\(|xmlhttprequest|serviceworker|websocket",
        css + html_text[:2000],
    ):
        add("JH101", "remote resource or fetch hook detected")

    csp_values = [
        meta.get("content", "") for meta in parser.metas
        if meta.get("http-equiv", "").lower() == "content-security-policy"
    ]
    if len(csp_values) != 1 or _csp(csp_values[0]) != _csp(CSP):
        add("JH102", "CSP is missing or wider than the renderer contract")

    for attrs in parser.links:
        href = attrs.get("href", "")
        if href.startswith("#"):
            continue
        parsed = urlsplit(href)
        keys = [
            part.split("=", 1)[0].lower()
            for part in parsed.query.split("&")
            if part
        ]
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username
            or parsed.password
            or any(key in FORBIDDEN_QUERY_KEYS for key in keys)
        ):
            add("JH103", "dangerous or credentialed external URL")
        rel = set(attrs.get("rel", "").split())
        if not {"noopener", "noreferrer"}.issubset(rel):
            add("JH105", "external link is missing noopener/noreferrer")

    for pattern in SECRET_PATTERNS:
        if pattern.search(html_text):
            add("JH104", "credential-shaped content detected")
            break

    visible = " ".join(parser.visible_text)
    forbidden_actions = (
        "立即购买", "立即支付", "提交订单", "登录后购买", "取消订单", "申请改签",
    )
    if any(phrase in visible for phrase in forbidden_actions) or parser.tags["form"] or parser.tags["button"]:
        add("JH204", "transaction action was rendered")

    if not _css_contract(css):
        add("JH001", "mobile/focus/print/reduced-motion CSS contract is incomplete")
    navs = [attrs for tag, attrs in parser.all_attrs if tag == "nav"]
    if not navs or not all(attrs.get("aria-label") for attrs in navs):
        add("JH001", "navigation lacks an accessible name")
    for tag, attrs in parser.all_attrs:
        if tag == "svg" and (
            attrs.get("role") != "img" or not attrs.get("aria-labelledby")
        ):
            add("JH001", "SVG lacks accessible title/description relation")

    return tuple(sorted(set(issues)))
