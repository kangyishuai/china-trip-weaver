#!/usr/bin/env python3
"""Build renderer adversarial mutation fixtures and their hash manifest."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, List, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "tests" / "fixtures" / "renderer"
BASE = "tests/fixtures/trips/schema/valid/weekend-live.json"
JOURNEY_DEMO = ROOT / "demo" / "journey-16d"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "plugins" / "china-trip-weaver" / "src"))

from china_trip_weaver.clock import FixedClock
from china_trip_weaver.journey import plan_journey
from china_trip_weaver.planning import RailBackend
from china_trip_weaver.render import render_journey, validate_journey_html
from scripts.build_plan_fixtures import journey_sixteen_day_case


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


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build_journey_demo() -> Mapping[str, Any]:
    """Generate the fifth demo entirely from the repository's synthetic fixture."""

    # This script exclusively owns demo/journey-16d. Its fixed clock intentionally
    # differs from the other four demos; do not hand-run the fifth demo separately.
    case = journey_sixteen_day_case()
    result = plan_journey(
        case["request"],
        case["candidates"],
        FixedClock.from_iso("2026-09-05T09:00:00+08:00"),
        RailBackend.from_spec("off", ROOT),
    )
    rendered = render_journey(result.journey)
    report = validate_journey_html(rendered, result.journey)
    if not report.ok:
        raise RuntimeError(
            "generated Journey demo HTML is invalid: "
            + "; ".join(item.render() for item in report.errors)
        )
    write_json(JOURNEY_DEMO / "request.json", case["request"])
    write_json(JOURNEY_DEMO / "candidates.json", case["candidates"])
    write_json(JOURNEY_DEMO / "journey.json", result.journey)
    (JOURNEY_DEMO / "journey.html").write_text(rendered, encoding="utf-8")
    return {
        "trips": len(result.journey["trips"]),
        "days": sum(len(item["days"]) for item in result.journey["trips"]),
        "journey_sha256": result.journey_sha256,
        "html_sha256": hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
    }


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
    journey_demo = build_journey_demo()
    print(
        "wrote %d Trip and %d HTML renderer fixtures; Journey demo trips=%d days=%d journey_sha256=%s html_sha256=%s"
        % (
            len(trip_mutations),
            len(html_mutations),
            journey_demo["trips"],
            journey_demo["days"],
            journey_demo["journey_sha256"],
            journey_demo["html_sha256"],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
