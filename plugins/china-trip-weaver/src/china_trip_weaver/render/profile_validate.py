"""Canonical v2 gate; executable bytes are anchored in the installed plugin asset."""

from __future__ import annotations

import json
from typing import Any, Mapping

from ..contracts import canonical_json
from .profile_html import assets, render_profile
from .validate_html import AuditParser, HTMLIssue, HTMLValidationReport


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
