"""Post-render DOM, security, fact, and accessibility gate (E001-E204)."""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlsplit

from ..contracts import canonical_json
from ..credentials import SUPPORTED_KEY_NAMES
from .template import CSP, FORBIDDEN_QUERY_KEYS


REQUIRED_SECTIONS = frozenset((
    "header", "truth-banner", "day-nav", "request-summary", "transport-summary",
    "lodging-summary", "days", "location-overview", "alternatives-and-unknowns",
    "evidence", "provider-health", "footer",
))
DISALLOWED_TAGS = frozenset(("iframe", "object", "embed", "form", "input", "button", "textarea", "select", "base", "video", "audio"))
SECRET_PATTERNS = (
    re.compile("gh" + r"[pousr]_[A-Za-z0-9]{20,}"),
    re.compile("sk" + r"-[A-Za-z0-9]{20,}"),
    re.compile("AK" + r"IA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)(?:api[_-]?key|token|secret|password|authorization)=[^&\s\"']+"),
) + tuple(
    re.compile(r"(?i)\b%s\b\s*[:=]\s*['\"]?[^\s<>'\"]+" % re.escape(name))
    for name in SUPPORTED_KEY_NAMES
) + (
    re.compile(r"(?i)Authorization\s*:\s*Bearer(?:\s+[^\s<]+)?"),
)
TRAIN_FACT_RE = re.compile(r"(?<![A-Z0-9])[GDCKTZ]\d{1,4}(?!\d)")
PRICE_FACT_RE = re.compile(r"¥(\d+)")
USER_TEXT_ATTRIBUTES = frozenset(("aria-label", "title", "alt", "placeholder", "value"))


@dataclass(frozen=True, order=True)
class HTMLIssue:
    code: str
    message: str

    def render(self) -> str:
        return "%s %s" % (self.code, self.message)


@dataclass(frozen=True)
class HTMLValidationReport:
    errors: Tuple[HTMLIssue, ...]
    warnings: Tuple[HTMLIssue, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> Mapping[str, Any]:
        return {
            "errors": [{"code": item.code, "message": item.message} for item in self.errors],
            "warnings": [{"code": item.code, "message": item.message} for item in self.warnings],
        }


class AuditParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.doctype = False
        self.tags: Counter[str] = Counter()
        self.ids: Counter[str] = Counter()
        self.metas: List[Mapping[str, str]] = []
        self.links: List[Mapping[str, str]] = []
        self.scripts: List[Dict[str, Any]] = []
        self.styles: List[str] = []
        self.sections: Counter[str] = Counter()
        self.headings: List[int] = []
        self.day_ids: Counter[str] = Counter()
        self.slot_nodes: List[Mapping[str, str]] = []
        self.entity_ids: Counter[str] = Counter()
        self.claim_ids: Counter[str] = Counter()
        self.claim_links: Counter[str] = Counter()
        self.providers: Counter[str] = Counter()
        self.unknown_nodes: List[Mapping[str, str]] = []
        self.price_nodes: List[Mapping[str, str]] = []
        self.coordinate_ids: Counter[str] = Counter()
        self.all_attrs: List[Tuple[str, Mapping[str, str]]] = []
        self.visible_text: List[str] = []
        self._capture: Optional[str] = None
        self._capture_buffer: List[str] = []

    def handle_decl(self, decl: str) -> None:
        if decl.strip().lower() == "doctype html":
            self.doctype = True

    def handle_starttag(self, tag: str, attrs: Sequence[Tuple[str, Optional[str]]]) -> None:
        values = {name: value or "" for name, value in attrs}
        self.tags[tag] += 1
        self.all_attrs.append((tag, values))
        if values.get("id"):
            self.ids[values["id"]] += 1
        if tag == "meta":
            self.metas.append(values)
        if tag == "a":
            self.links.append(values)
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.headings.append(int(tag[1]))
        if values.get("data-section"):
            self.sections[values["data-section"]] += 1
        if values.get("data-day-id"):
            self.day_ids[values["data-day-id"]] += 1
        if values.get("data-slot-id"):
            self.slot_nodes.append(values)
        if values.get("data-entity-id"):
            self.entity_ids[values["data-entity-id"]] += 1
        if values.get("data-claim-id"):
            self.claim_ids[values["data-claim-id"]] += 1
        if values.get("data-claim-link"):
            self.claim_links[values["data-claim-link"]] += 1
        if values.get("data-provider"):
            self.providers[values["data-provider"]] += 1
        if "data-unknown-index" in values:
            self.unknown_nodes.append(values)
        if values.get("data-price-owner"):
            self.price_nodes.append(values)
        if values.get("data-coordinate-ref"):
            self.coordinate_ids[values["data-coordinate-ref"]] += 1
        if tag in ("script", "style"):
            self._capture = tag
            self._capture_buffer = []
            if tag == "script":
                self.scripts.append({"attrs": values, "content": ""})

    def handle_endtag(self, tag: str) -> None:
        if tag == self._capture:
            content = "".join(self._capture_buffer)
            if tag == "script":
                self.scripts[-1]["content"] = content
            else:
                self.styles.append(content)
            self._capture = None
            self._capture_buffer = []

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._capture_buffer.append(data)
        elif data.strip():
            self.visible_text.append(data)


def validate_html(html_text: str, trip: Mapping[str, Any]) -> HTMLValidationReport:
    issues: List[HTMLIssue] = []
    parser = AuditParser()
    try:
        parser.feed(html_text)
        parser.close()
    except Exception as exc:
        return HTMLValidationReport((HTMLIssue("E001", "HTML parse failed: %s" % exc),))

    def add(code: str, message: str) -> None:
        issues.append(HTMLIssue(code, message))

    html_attrs = next((attrs for tag, attrs in parser.all_attrs if tag == "html"), {})
    charset = any(meta.get("charset", "").lower() == "utf-8" for meta in parser.metas)
    viewport = any(meta.get("name", "").lower() == "viewport" and meta.get("content") == "width=device-width, initial-scale=1" for meta in parser.metas)
    if not parser.doctype or not charset or not viewport or html_attrs.get("lang") != trip["request"]["locale"] or parser.tags["main"] != 1 or parser.tags["h1"] != 1:
        add("E001", "doctype/charset/viewport/lang/unique main+h1 contract failed")

    trip_scripts = [item for item in parser.scripts if item["attrs"].get("id") == "trip-data"]
    if len(trip_scripts) != 1 or len(parser.scripts) != 1:
        add("E002", "trip-data must be the only script element")
    else:
        script = trip_scripts[0]
        if script["attrs"].get("type") != "application/json" or script["attrs"].get("src"):
            add("E002", "trip-data MIME/src is invalid")
        try:
            embedded = json.loads(script["content"])
            if canonical_json(embedded) != canonical_json(trip):
                add("E002", "embedded Trip is not canonical-equal to input")
        except json.JSONDecodeError:
            add("E002", "embedded Trip cannot be parsed")

    expected_days = Counter(day["day_id"] for day in trip["days"])
    expected_slots = {slot["slot_id"]: slot for day in trip["days"] for slot in day["slots"]}
    expected_entities = Counter(
        [item["leg_id"] for item in trip["transport_legs"]]
        + [item["lodging_id"] for item in trip["lodgings"]]
        + [item["poi_id"] for item in trip["pois"]]
    )
    expected_claims = Counter(item["claim_id"] for item in trip["claims"])
    expected_providers = Counter(item["provider"] for item in trip["provider_health"])
    actual_slots = Counter(item["data-slot-id"] for item in parser.slot_nodes)
    if parser.day_ids != expected_days or actual_slots != Counter(expected_slots.keys()) or parser.entity_ids != expected_entities or parser.claim_ids != expected_claims:
        add("E003", "day/slot/entity/claim render counts differ from Trip")
    if parser.providers != expected_providers:
        add("E003", "provider health row counts differ from Trip")
    for node in parser.slot_nodes:
        slot = expected_slots.get(node["data-slot-id"])
        if slot and (node.get("data-start-at") != slot["start_at"] or node.get("data-end-at") != slot["end_at"]):
            add("E003", "slot timestamp differs from Trip: %s" % slot["slot_id"])
    service_nodes = {attrs.get("data-entity-id"): attrs for tag, attrs in parser.all_attrs if attrs.get("data-entity-kind") == "transport"}
    for leg in trip["transport_legs"]:
        if service_nodes.get(leg["leg_id"], {}).get("data-service-number") != (leg["service_number"] or ""):
            add("E003", "transport service number differs from Trip: %s" % leg["leg_id"])
    user_fact_text = " ".join(parser.visible_text + [
        value
        for _, attrs in parser.all_attrs
        for name, value in attrs.items()
        if name in USER_TEXT_ATTRIBUTES and not name.startswith("data-")
    ])
    known_services = {leg["service_number"] for leg in trip["transport_legs"] if leg["service_number"]}
    unexpected_services = sorted(set(TRAIN_FACT_RE.findall(user_fact_text)) - known_services)
    if unexpected_services:
        add("E003", "rendered train fact is absent from Trip: %s" % unexpected_services[0])
    known_prices = {
        _number(item["price"]["amount"])
        for group in ("transport_legs", "lodgings", "pois")
        for item in trip[group]
        if item.get("price") and item["price"]["amount"] is not None
    }
    unexpected_prices = sorted(set(PRICE_FACT_RE.findall(user_fact_text)) - known_prices)
    if unexpected_prices:
        add("E003", "rendered CNY fact is absent from Trip: ¥%s" % unexpected_prices[0])

    if any(count != 1 for count in parser.ids.values()):
        add("E004", "duplicate DOM id")
    for attrs in parser.links:
        href = attrs.get("href", "")
        if href.startswith("#") and href[1:] not in parser.ids:
            add("E004", "broken internal anchor: %s" % href)
    previous = 0
    for level in parser.headings:
        if previous and level > previous + 1:
            add("E004", "heading level jumps from h%d to h%d" % (previous, level))
            break
        previous = level
    if set(parser.sections) != REQUIRED_SECTIONS or any(count != 1 for count in parser.sections.values()):
        add("E005", "required 12-section information architecture is incomplete")

    for tag, attrs in parser.all_attrs:
        if tag in DISALLOWED_TAGS or any(name.lower().startswith("on") for name in attrs):
            add("E101", "executable/interactive element or event handler is forbidden")
            break
        if tag == "script" and attrs.get("id") != "trip-data":
            add("E101", "executable script is forbidden")
        if tag == "link" and attrs.get("rel", "").lower() == "stylesheet":
            add("E101", "remote/external stylesheet is forbidden")
        if tag == "img" and attrs.get("src") and not attrs["src"].startswith("data:"):
            add("E101", "remote image is forbidden")
        if attrs.get("contenteditable") not in (None, "", "false"):
            add("E101", "contenteditable is forbidden")
    css = "\n".join(parser.styles)
    if re.search(r"(?i)@import|url\s*\(\s*['\"]?(?:https?:)?//|fetch\s*\(|xmlhttprequest|serviceworker|websocket", css + html_text[:2000]):
        add("E101", "remote resource or fetch hook detected")

    csp_values = [meta.get("content", "") for meta in parser.metas if meta.get("http-equiv", "").lower() == "content-security-policy"]
    if len(csp_values) != 1 or _csp(csp_values[0]) != _csp(CSP):
        add("E102", "CSP is missing or wider than the renderer contract")

    for attrs in parser.links:
        href = attrs.get("href", "")
        if href.startswith("#"):
            continue
        parsed = urlsplit(href)
        keys = [part.split("=", 1)[0].lower() for part in parsed.query.split("&") if part]
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or any(key in FORBIDDEN_QUERY_KEYS for key in keys):
            add("E103", "dangerous or credentialed external URL")
        rel = set(attrs.get("rel", "").split())
        if not {"noopener", "noreferrer"}.issubset(rel):
            add("E105", "external link is missing noopener/noreferrer")
    if "</script" in (trip_scripts[0]["content"].lower() if trip_scripts else ""):
        add("E103", "embedded JSON can close the script element")

    for pattern in SECRET_PATTERNS:
        if pattern.search(html_text):
            add("E104", "credential-shaped content detected")
            break

    mode_nodes = [attrs for tag, attrs in parser.all_attrs if "data-trip-mode" in attrs]
    if len(mode_nodes) != 1 or mode_nodes[0]["data-trip-mode"] != trip["mode"]:
        add("E201", "rendered mode badge differs from Trip")
    visible = " ".join(parser.visible_text)
    if trip["mode"] == "mock" and trip.get("mock_notice", "") not in visible:
        add("E201", "mock notice is not visible")
    if trip["mode"] in ("cached", "static") and any(phrase in visible for phrase in ("实时可用", "实时路线", "实时总价", "已验证路线", "可购买总价")):
        add("E201", "degraded/static data is presented as live")

    referenced_claims = [claim_id for day in trip["days"] for slot in day["slots"] for claim_id in slot["claim_ids"]]
    for group in ("transport_legs", "lodgings", "pois"):
        for item in trip[group]:
            referenced_claims.extend(item["claim_ids"])
    if any(parser.claim_links[claim_id] < 1 for claim_id in referenced_claims):
        add("E202", "dynamic fact is missing an inline claim link")
    expected_prices: Dict[str, Optional[Mapping[str, Any]]] = {}
    expected_prices.update((item["leg_id"], item["price"]) for item in trip["transport_legs"])
    expected_prices.update((item["lodging_id"], item["price"]) for item in trip["lodgings"])
    expected_prices.update((item["poi_id"], item["price"]) for item in trip["pois"])
    actual_prices = {item["data-price-owner"]: item for item in parser.price_nodes}
    if set(actual_prices) != set(expected_prices):
        add("E202", "price render coverage differs from Trip entities")
    else:
        for owner, price in expected_prices.items():
            expected_type = "none" if price is None else price["price_type"]
            expected_amount = "" if price is None or price["amount"] is None else _number(price["amount"])
            if actual_prices[owner].get("data-price-type") != expected_type or actual_prices[owner].get("data-price-amount") != expected_amount:
                add("E202", "price type/amount differs from Trip: %s" % owner)
    if len(parser.unknown_nodes) != len(trip["unknowns"]):
        add("E202", "unknown count differs from Trip")
    else:
        for node, unknown in zip(parser.unknown_nodes, trip["unknowns"]):
            if node.get("data-unknown-path") != unknown["field_path"] or node.get("data-unknown-reason") != unknown["reason"]:
                add("E202", "unknown path/reason differs from Trip")

    null_coordinate_ids = {
        item[key]
        for group, key in ((trip["lodgings"], "lodging_id"), (trip["pois"], "poi_id"))
        for item in group if item["coordinates"] is None
    }
    if any(parser.coordinate_ids[item] for item in null_coordinate_ids):
        add("E203", "unknown coordinate received a marker")
    has_line = parser.tags["polyline"] > 0
    schematic_labels = [attrs for tag, attrs in parser.all_attrs if attrs.get("data-schematic-label") == "true"]
    if has_line and not schematic_labels:
        add("E203", "schematic connection lacks non-route label")

    forbidden_actions = ("立即购买", "立即支付", "提交订单", "登录后购买", "取消订单", "申请改签")
    if any(phrase in visible for phrase in forbidden_actions) or parser.tags["form"] or parser.tags["button"]:
        add("E204", "transaction action was rendered")

    if not _css_contract(css):
        add("E001", "mobile/focus/print/reduced-motion CSS contract is incomplete")
    navs = [attrs for tag, attrs in parser.all_attrs if tag == "nav"]
    if not navs or not all(attrs.get("aria-label") for attrs in navs):
        add("E001", "navigation lacks an accessible name")
    for tag, attrs in parser.all_attrs:
        if tag == "svg" and (attrs.get("role") != "img" or not attrs.get("aria-labelledby")):
            add("E001", "SVG lacks accessible title/description relation")

    return HTMLValidationReport(tuple(sorted(set(issues))))


def _csp(value: str) -> Mapping[str, Tuple[str, ...]]:
    result = {}
    for directive in value.split(";"):
        parts = directive.strip().split()
        if parts:
            result[parts[0]] = tuple(parts[1:])
    return result


def _css_contract(css: str) -> bool:
    required = (
        "font-size: 16px", "line-height: 1.55", "overflow-x: hidden",
        "min-height: 44px", ":focus-visible", "@media (min-width: 768px)",
        "@media (prefers-reduced-motion: reduce)", "@media print",
    )
    return all(fragment in css for fragment in required)


def _number(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)
