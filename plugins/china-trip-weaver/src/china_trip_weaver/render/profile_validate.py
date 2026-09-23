"""Canonical v2 gate; executable bytes are anchored in the installed plugin asset."""

from __future__ import annotations

import json
from html.parser import HTMLParser
from typing import Any, Mapping

from ..contracts import canonical_json
from .profile_html import PROFILE_ASSET_SHA256, asset_digest, assets, render_profile
from .validate_html import AuditParser, HTMLIssue, HTMLValidationReport


def is_profile_document(html_text: str) -> bool:
    """Inspect version attributes, never source text that may quote a marker."""
    class VersionProbe(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.version = False

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            values = dict(attrs)
            if tag == "html" and values.get("data-renderer-version") == "2":
                self.version = True
            if tag == "meta" and values.get("name") == "ctw-renderer" and values.get("content") == "2":
                self.version = True

    parser = VersionProbe()
    try:
        parser.feed(html_text.partition("</head>")[0])
        parser.close()
    except Exception:
        return False
    return parser.version


def _expected_hero(source: Mapping[str, Any]) -> str:
    if "trips" in source:
        locale = source["trips"][0]["request"]["locale"]
        start, end = source["start_date"], source["end_date"]
        day_count = sum(len(trip["days"]) for trip in source["trips"])
        groups = source.get("traveler_groups") or ()
        travelers = sum(group["travelers"] for group in groups) if groups else source["travelers"]
    else:
        request = source["request"]
        locale = request["locale"]
        start, end = request["start_date"], request["end_date"]
        day_count = len(source["days"])
        groups = request.get("traveler_groups") or ()
        travelers = sum(group["travelers"] for group in groups) if groups else request["travelers"]
    if locale == "en":
        person_unit = "traveler" if travelers == 1 else "travelers"
        day_unit = "day" if day_count == 1 else "days"
    else:
        person_unit, day_unit = "人", "天"
    return "%s — %s · %s %s · %s %s" % (start, end, travelers, person_unit, day_count, day_unit)


class _HeroParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.texts: list[str] = []
        self._parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "p" and "hero-sub" in (dict(attrs).get("class") or "").split():
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._parts is not None:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "p" and self._parts is not None:
            self.texts.append("".join(self._parts).strip())
            self._parts = None


def validate_profile(html_text: str, source: Mapping[str, Any], legacy_html: str) -> HTMLValidationReport:
    issues = []
    parser = AuditParser()
    try:
        parser.feed(html_text)
        parser.close()
    except Exception as exc:
        return HTMLValidationReport((HTMLIssue("V201", "v2 HTML parse failed: %s" % exc),))
    html_attrs = next((attrs for tag, attrs in parser.all_attrs if tag == "html"), {})
    marker = [m for m in parser.metas if m.get("name") == "ctw-renderer"]
    if html_attrs.get("data-renderer-version") != "2" or len(marker) != 1 or marker[0].get("content") != "2":
        issues.append(HTMLIssue("V201", "v2 renderer marker differs"))
    installed_digest = asset_digest()
    asset_markers = [m for m in parser.metas if m.get("name") == "ctw-profile-assets"]
    if installed_digest != PROFILE_ASSET_SHA256:
        issues.append(HTMLIssue("V207", "installed v2 assets changed; upgrade renderer format before generating or validating"))
        return HTMLValidationReport(tuple(sorted(set(issues))))
    if len(asset_markers) != 1 or asset_markers[0].get("content") != PROFILE_ASSET_SHA256:
        issues.append(HTMLIssue("V207", "v2 page assets differ; use its matching plugin build or regenerate from source JSON"))
    hero = _HeroParser()
    hero.feed(html_text)
    hero.close()
    if hero.texts != [_expected_hero(source)]:
        issues.append(HTMLIssue("V206", "v2 visible dates, traveler count, or day count differ from source"))
    embedded = [s for s in parser.scripts if s["attrs"].get("id") == "source-document"]
    if len(embedded) != 1 or embedded[0]["attrs"].get("type") != "application/json":
        issues.append(HTMLIssue("V202", "v2 source document is missing or executable"))
    else:
        try:
            if canonical_json(json.loads(embedded[0]["content"])) != canonical_json(source):
                issues.append(HTMLIssue("V202", "v2 source document differs from input"))
        except (ValueError, TypeError):
            issues.append(HTMLIssue("V202", "v2 source document is invalid"))
    executable = [s for s in parser.scripts if s["attrs"].get("type", "") not in ("application/json",)]
    if len(executable) != 1 or executable[0]["content"] != assets()[1] or executable[0]["attrs"].get("src"):
        issues.append(HTMLIssue("V203", "v2 executable script differs from trusted version asset"))
    try:
        expected = render_profile(source, legacy_html)
    except (ValueError, KeyError, TypeError) as exc:
        return HTMLValidationReport((HTMLIssue("V204", "cannot derive v2 document: %s" % exc),))
    if html_text != expected:
        issues.append(HTMLIssue("V205", "v2 page differs from canonical renderer output"))
    return HTMLValidationReport(tuple(sorted(set(issues))))
