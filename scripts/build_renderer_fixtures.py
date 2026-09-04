#!/usr/bin/env python3
"""Build renderer adversarial mutation fixtures and their hash manifest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, List, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "tests" / "fixtures" / "renderer"
BASE = "tests/fixtures/trips/schema/valid/weekend-live.json"


def trip_fixture(case_id: str, mutations: Sequence[Mapping[str, Any]], outcome: str, codes: Sequence[str]) -> Mapping[str, Any]:
    return {
        "fixture_version": 1,
        "case_id": case_id,
        "base_fixture": BASE,
        "mutations": list(mutations),
        "expected": {"outcome": outcome, "codes": list(codes)},
    }


def html_fixture(case_id: str, old: str, new: Any, codes: Sequence[str]) -> Mapping[str, Any]:
    replacement = {"old": old, "count": 1}
    if isinstance(new, list):
        replacement["new_parts"] = new
    else:
        replacement["new"] = new
    return {
        "fixture_version": 1,
        "case_id": case_id,
        "base_fixture": BASE,
        "replace": replacement,
        "expected": {"codes": list(codes)},
    }


def build_trip_mutations() -> List[Mapping[str, Any]]:
    return [
        trip_fixture("closing-script", [{"path": "/request/pasted_notes", "value": "</script><script>alert('x')</script>"}], "render-ok", []),
        trip_fixture("attribute-injection", [{"path": "/pois/0/name", "value": "\" onmouseover=\"alert(1) 外滩"}], "render-ok", []),
        trip_fixture("rtl-emoji-long", [{"path": "/request/pasted_notes", "value": "مرحبا 🧳 上海行程 — " + "很长的用户备注" * 80}], "render-ok", []),
        trip_fixture("ansi-provider-text", [{"path": "/days/0/slots/0/title", "value": "\u001b[31m外滩\u001b[0m <b>建筑</b>"}], "render-ok", []),
        trip_fixture("coordinates-missing", [{"path": "/lodgings/0/coordinates", "value": None}, {"path": "/pois/0/coordinates", "value": None}], "render-ok", []),
        trip_fixture("dangerous-scheme", [{"path": "/pois/0/deep_links/0", "value": "javascript:alert(1)"}], "reject-trip", ["S_PATTERN"]),
        trip_fixture("url-credentials", [{"path": "/pois/0/deep_links/0", "value": "https://user:pass@example.invalid/path"}], "reject-trip", ["S_FORMAT"]),
        trip_fixture("duplicate-day-id", [{"path": "/days/1/day_id", "value": "day-1"}], "reject-trip", ["V_DUPLICATE_ID"]),
        trip_fixture("fake-secret", [{"path": "/request/pasted_notes", "value_parts": ["gh", "p_", "000000000000000000000000000000"]}], "reject-trip", ["V_SECRET"]),
    ]


def build_html_mutations() -> List[Mapping[str, Any]]:
    return [
        html_fixture("csp-loosened", "script-src &#x27;none&#x27;", "script-src https:", ["E102"]),
        html_fixture("remote-script", "</body>", '<script src="https://example.invalid/x.js"></script></body>', ["E101"]),
        html_fixture("trip-data-mismatch", '\"travelers\":2', '\"travelers\":3', ["E002"]),
        html_fixture("missing-link-rel", 'rel="noopener noreferrer"', 'rel=""', ["E105"]),
        html_fixture("schematic-label-removed", ' data-schematic-label="true"', "", ["E203"]),
        html_fixture("transaction-form", "</main>", '<form><button>立即购买</button></form></main>', ["E101", "E204"]),
        html_fixture("viewport-removed", '<meta name="viewport" content="width=device-width, initial-scale=1">', "", ["E001"]),
        html_fixture("price-type-changed", 'data-price-type="estimate"', 'data-price-type="live"', ["E202"]),
        html_fixture("invented-train-price-facts", "</main>", ["<p>示例车次 ", "G", "1001 示例票价 ¥", "101", "</p></main>"], ["E003"]),
        html_fixture("supported-key-assignment", "</footer>", ["<p>", "AMAP_", "WEBSERVICE_KEY", " = ctw-render-canary</p></footer>"], ["E104"]),
        html_fixture("authorization-bearer", "</footer>", ["<p>", "Authorization", ":   ", "Bearer", " ctw-render-canary</p></footer>"], ["E104"]),
    ]


def write_group(name: str, fixtures: Sequence[Mapping[str, Any]], manifest: List[Mapping[str, str]]) -> None:
    directory = OUTPUT / name
    directory.mkdir(parents=True, exist_ok=True)
    for fixture in fixtures:
        relative = Path(name) / (fixture["case_id"] + ".json")
        encoded = (json.dumps(fixture, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
        (OUTPUT / relative).write_bytes(encoded)
        manifest.append({"path": relative.as_posix(), "sha256": hashlib.sha256(encoded).hexdigest()})


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    trip_mutations = build_trip_mutations()
    html_mutations = build_html_mutations()
    files: List[Mapping[str, str]] = []
    write_group("trip", trip_mutations, files)
    write_group("html", html_mutations, files)
    manifest = {
        "manifest_version": 1,
        "generated_by": "scripts/build_renderer_fixtures.py",
        "counts": {"trip": len(trip_mutations), "html": len(html_mutations)},
        "files": sorted(files, key=lambda item: item["path"]),
    }
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("wrote %d Trip and %d HTML renderer fixtures" % (len(trip_mutations), len(html_mutations)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
