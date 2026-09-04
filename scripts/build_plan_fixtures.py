#!/usr/bin/env python3
"""Build deterministic request, candidate, and synthetic rail fixtures."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "tests" / "fixtures" / "e2e"
JOURNEY_LODGING_CHAIN_FIXTURE = (
    ROOT / "tests" / "fixtures" / "journey" / "synthetic-six-city-16d.json"
)
QUERIED_AT = "2026-09-03T12:00:00+08:00"
RAIL_CAPTURED_AT = "2026-09-04T00:00:00+08:00"
RAIL_TOOLS = [
    "get-current-date", "get-stations-code-in-city", "get-station-code-of-citys",
    "get-station-code-by-names", "get-station-by-telecode", "get-tickets",
    "get-interline-tickets", "get-train-route-stations",
]
STATIONS = {
    "北京": {"station_code": "BEX", "station_name": "北京示例站"},
    "上海": {"station_code": "SHX", "station_name": "上海示例站"},
    "杭州": {"station_code": "HZX", "station_name": "杭州示例站"},
}


def request(origin: Optional[Mapping[str, str]], destination: Mapping[str, str], start: str, end: str, travelers: int, interests: Sequence[str]) -> Mapping[str, Any]:
    return {
        "origin": dict(origin) if origin else None,
        "destinations": [dict(destination)],
        "start_date": start,
        "end_date": end,
        "travelers": travelers,
        "budget_cny": 6000,
        "interests": list(interests),
        "pace": "balanced",
        "constraints": ["不执行任何交易动作"],
        "assumptions": ["无地图 Key 时使用保守静态路线估算"],
        "locale": "zh-CN",
        "pasted_notes": None,
    }


def claim(identifier: str, subject: str, field_path: str, value: Any, url: str, status: str, confidence: float) -> Mapping[str, Any]:
    return {
        "claim_id": identifier,
        "subject_ref": subject,
        "field_path": field_path,
        "value": value,
        "source_url": url,
        "provider": "official-web" if status != "unknown" else "deep-link",
        "queried_at": QUERIED_AT,
        "status": status,
        "confidence": confidence,
        "mode": "static",
        "as_of": None,
        "raw_ref": None,
        "response_hash": None,
        "json_path": None,
    }


def poi(case: str, slug: str, name: str, city: str, category: str, start_at: str, end_at: str, duration: int, url: str) -> Tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    identifier = "poi-%s-%s" % (case, slug)
    claim_id = "claim-%s-%s-hours" % (case, slug)
    evidence = claim(claim_id, identifier, "/opening_windows/0", "date-specific candidate window", url, "hypothesis", 0.55)
    entity = {
        "poi_id": identifier,
        "name": name,
        "city": city,
        "category": category,
        "coordinates": None,
        "recommended_duration_minutes": duration,
        "opening_windows": [{
            "start_at": start_at,
            "end_at": end_at,
            "status": "tentative",
            "claim_id": claim_id,
        }],
        "price": None,
        "deep_links": [url],
        "claim_ids": [claim_id],
    }
    unknown = {
        "field_path": "/pois/{index}/coordinates",
        "reason": "AMap is not configured; coordinates remain unverified",
        "provider": "amap",
        "claim_id": claim_id,
    }
    return entity, evidence, unknown


def lodging(case: str, name: str, city: str, area: str, check_in: str, check_out: str) -> Tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    identifier = "lodging-%s-central" % case
    claim_id = "claim-%s-lodging-price" % case
    url = "https://www.fliggy.com/hotel/search"
    evidence = claim(claim_id, identifier, "/price", None, url, "unknown", 0)
    entity = {
        "lodging_id": identifier,
        "name": name,
        "city": city,
        "area": area,
        "check_in": check_in,
        "check_out": check_out,
        "coordinates": None,
        "price": {
            "amount": None,
            "currency": "CNY",
            "price_type": "verify-on-click",
            "unit": "per_night",
            "includes_taxes": None,
            "queried_at": QUERIED_AT,
            "claim_id": claim_id,
        },
        "deep_links": [url],
        "claim_ids": [claim_id],
        "locked": False,
    }
    unknown = {
        "field_path": "/lodgings/0/price/amount",
        "reason": "room total and cancellation terms must be verified on click",
        "provider": "flyai",
        "claim_id": claim_id,
    }
    return entity, evidence, unknown


def candidates(case: str, lodging_spec: Tuple[str, str, str, str, str], poi_specs: Sequence[Tuple[str, str, str, str, str, int, str]]) -> Mapping[str, Any]:
    lodging_entity, lodging_claim, lodging_unknown = lodging(case, *lodging_spec)
    pois: List[Mapping[str, Any]] = []
    claims: List[Mapping[str, Any]] = [lodging_claim]
    unknowns: List[Mapping[str, Any]] = [lodging_unknown]
    for index, spec in enumerate(poi_specs):
        entity, evidence, unknown = poi(case, *spec)
        pois.append(entity)
        claims.append(evidence)
        unknown = dict(unknown)
        unknown["field_path"] = unknown["field_path"].format(index=index)
        unknowns.append(unknown)
    return {
        "candidates_version": "1.0.0",
        "pois": pois,
        "lodgings": [lodging_entity],
        "claims": claims,
        "unknowns": unknowns,
    }


def multicity_candidates(
    case: str,
    lodging_specs: Sequence[Tuple[str, str, str, str, str, str]],
    poi_specs: Sequence[Tuple[str, str, str, str, str, int, str]],
) -> Mapping[str, Any]:
    lodgings: List[Mapping[str, Any]] = []
    claims: List[Mapping[str, Any]] = []
    unknowns: List[Mapping[str, Any]] = []
    for index, (slug, name, city, area, check_in, check_out) in enumerate(lodging_specs):
        entity, evidence, unknown = lodging(case + "-" + slug, name, city, area, check_in, check_out)
        lodgings.append(entity)
        claims.append(evidence)
        unknown = dict(unknown)
        unknown["field_path"] = "/lodgings/%d/price/amount" % index
        unknowns.append(unknown)
    pois: List[Mapping[str, Any]] = []
    for index, spec in enumerate(poi_specs):
        entity, evidence, unknown = poi(case, *spec)
        pois.append(entity)
        claims.append(evidence)
        unknown = dict(unknown)
        unknown["field_path"] = unknown["field_path"].format(index=index)
        unknowns.append(unknown)
    return {
        "candidates_version": "1.0.0",
        "pois": pois,
        "lodgings": lodgings,
        "claims": claims,
        "unknowns": unknowns,
    }


def multicity_demo() -> Mapping[str, Any]:
    request_value = {
        "origin": {"ref_id": "city-beijing", "name": "北京", "city": "北京"},
        "destinations": [
            {"ref_id": "city-shanghai", "name": "上海", "city": "上海"},
            {"ref_id": "city-hangzhou", "name": "杭州", "city": "杭州"},
            {"ref_id": "city-suzhou", "name": "苏州", "city": "苏州"},
        ],
        "start_date": "2026-10-16",
        "end_date": "2026-10-20",
        "travelers": 2,
        "budget_cny": 8000,
        "interests": ["建筑", "园林", "美食"],
        "pace": "balanced",
        "constraints": ["不执行任何交易动作"],
        "assumptions": ["无地图 Key 时使用保守静态路线估算"],
        "locale": "zh-CN",
        "pasted_notes": None,
    }
    candidates_value = multicity_candidates("g1", [
        ("shanghai", "上海示例住宿", "上海", "上海示例片区", "2026-10-16", "2026-10-17"),
        ("hangzhou", "杭州示例住宿", "杭州", "杭州示例片区", "2026-10-17", "2026-10-19"),
        ("suzhou", "苏州示例住宿", "苏州", "苏州示例片区", "2026-10-19", "2026-10-20"),
    ], [
        ("shanghai", "上海示例建筑漫步", "上海", "architecture", "2026-10-16T16:00:00+08:00", "2026-10-16T18:00:00+08:00", 90, "https://example.com/shanghai"),
        ("hangzhou-arrival", "杭州示例湖滨漫步", "杭州", "scenic", "2026-10-17T16:00:00+08:00", "2026-10-17T18:00:00+08:00", 90, "https://example.com/hangzhou"),
        ("hangzhou", "杭州示例文化场馆", "杭州", "museum", "2026-10-18T09:00:00+08:00", "2026-10-18T12:00:00+08:00", 90, "https://example.com/hangzhou"),
        ("suzhou-arrival", "苏州示例园林", "苏州", "garden", "2026-10-19T16:00:00+08:00", "2026-10-19T18:00:00+08:00", 90, "https://example.com/suzhou"),
        ("suzhou", "苏州示例街区", "苏州", "architecture", "2026-10-20T09:00:00+08:00", "2026-10-20T12:00:00+08:00", 90, "https://example.com/suzhou"),
    ])
    return {"request": request_value, "candidates": candidates_value}


def journey_sixteen_day_case() -> Mapping[str, Any]:
    """Return a synthetic long request used without adding generated fixture files."""

    request_value = {
        "origin": {"ref_id": "city-beijing", "name": "北京", "city": "北京"},
        "destinations": [
            {"ref_id": "city-shanghai", "name": "上海", "city": "上海"},
            {"ref_id": "city-hangzhou", "name": "杭州", "city": "杭州"},
            {"ref_id": "city-suzhou", "name": "苏州", "city": "苏州"},
        ],
        "start_date": "2026-10-01",
        "end_date": "2026-10-16",
        "travelers": 2,
        "rooms": 1,
        "budget_cny": 20000,
        "interests": ["architecture", "garden"],
        "pace": "balanced",
        "constraints": ["不执行任何交易动作"],
        "assumptions": ["synthetic 16-day Journey acceptance input"],
        "locale": "zh-CN",
        "pasted_notes": None,
    }
    candidates_value = multicity_candidates("j16", [
        ("shanghai", "上海合成住宿", "上海", "上海合成片区", "2026-10-01", "2026-10-06"),
        ("hangzhou", "杭州合成住宿", "杭州", "杭州合成片区", "2026-10-06", "2026-10-11"),
        ("suzhou", "苏州合成住宿", "苏州", "苏州合成片区", "2026-10-11", "2026-10-16"),
    ], [
        ("shanghai", "上海合成建筑漫步", "上海", "architecture", "2026-10-02T09:00:00+08:00", "2026-10-02T12:00:00+08:00", 90, "https://example.com/synthetic-journey/shanghai"),
        ("hangzhou", "杭州合成湖滨漫步", "杭州", "scenic", "2026-10-07T09:00:00+08:00", "2026-10-07T12:00:00+08:00", 90, "https://example.com/synthetic-journey/hangzhou"),
        ("suzhou", "苏州合成园林漫步", "苏州", "garden", "2026-10-12T09:00:00+08:00", "2026-10-12T12:00:00+08:00", 90, "https://example.com/synthetic-journey/suzhou"),
    ])
    nightly_prices = (300, 280, 260)
    lodging_ids = {item["lodging_id"] for item in candidates_value["lodgings"]}
    for lodging_item, amount in zip(candidates_value["lodgings"], nightly_prices):
        lodging_item["price"]["amount"] = amount
        lodging_item["price"]["price_type"] = "reference"
        lodging_item["price"]["includes_taxes"] = True
        claim_id = lodging_item["price"]["claim_id"]
        price_claim = next(item for item in candidates_value["claims"] if item["claim_id"] == claim_id)
        price_claim["value"] = amount
        price_claim["status"] = "partial"
        price_claim["confidence"] = 0.8
    candidates_value["unknowns"] = [
        item for item in candidates_value["unknowns"]
        if not (
            item["field_path"].startswith("/lodgings/")
            and item.get("claim_id") in {
                claim["claim_id"] for claim in candidates_value["claims"]
                if claim["subject_ref"] in lodging_ids
            }
        )
    ]
    return {"request": request_value, "candidates": candidates_value}


def journey_six_city_lodging_chain_case() -> Mapping[str, Any]:
    """Return the all-synthetic 16-day lodging-chain regression input."""

    places = {
        "a": "合成甲城",
        "b": "合成乙城",
        "c": "合成丙城",
        "d": "合成丁城",
        "e": "合成戊城",
        "f": "合成己城",
    }
    destination_sequence = ("a", "b", "a", "c", "d", "e", "f", "e")
    stays = (
        ("a-first", "a", "2026-09-25", "2026-09-26"),
        ("b", "b", "2026-09-26", "2026-09-29"),
        ("a-return", "a", "2026-09-29", "2026-09-30"),
        ("c", "c", "2026-09-30", "2026-10-03"),
        ("d-long", "d", "2026-10-03", "2026-10-06"),
        ("d-overlap", "d", "2026-10-05", "2026-10-06"),
        ("e-first", "e", "2026-10-06", "2026-10-08"),
        ("f", "f", "2026-10-08", "2026-10-09"),
        ("e-return", "e", "2026-10-09", "2026-10-10"),
    )
    visits = (
        ("a", "2026-09-29"),
        ("b", "2026-09-27"),
        ("c", "2026-10-01"),
        ("d", "2026-10-04"),
        ("e", "2026-10-07"),
        ("f", "2026-10-08"),
    )
    request_value = {
        "origin": {
            "ref_id": "city-synthetic-a",
            "name": places["a"],
            "city": places["a"],
        },
        "destinations": [
            {
                "ref_id": "city-synthetic-" + slug,
                "name": places[slug],
                "city": places[slug],
            }
            for slug in destination_sequence
        ],
        "start_date": "2026-09-25",
        "end_date": "2026-10-10",
        "travelers": 3,
        "rooms": 2,
        "budget_cny": 24000,
        "interests": ["synthetic architecture", "synthetic coast"],
        "pace": "balanced",
        "constraints": ["不执行任何交易动作"],
        "assumptions": ["all entity identities are synthetic; dates mirror the regression shape"],
        "locale": "zh-CN",
        "pasted_notes": None,
    }
    candidates_value = multicity_candidates(
        "j16-six-city-synthetic",
        [
            (
                slug,
                places[city_ref] + "合成住宿" + str(index + 1),
                places[city_ref],
                places[city_ref] + "合成片区",
                check_in,
                check_out,
            )
            for index, (slug, city_ref, check_in, check_out) in enumerate(stays)
        ],
        [
            (
                city_ref,
                places[city_ref] + "合成漫步",
                places[city_ref],
                "synthetic-sight",
                visit_date + "T09:00:00+08:00",
                visit_date + "T12:00:00+08:00",
                90,
                "https://example.invalid/synthetic/poi/" + slug,
            )
            for slug, (city_ref, visit_date) in zip(places, visits)
        ],
    )
    entity_urls = {
        item["lodging_id"]: "https://example.invalid/synthetic/lodging/%d" % index
        for index, item in enumerate(candidates_value["lodgings"])
    }
    entity_urls.update({
        item["poi_id"]: "https://example.invalid/synthetic/poi/%d" % index
        for index, item in enumerate(candidates_value["pois"])
    })
    for entity in list(candidates_value["lodgings"]) + list(candidates_value["pois"]):
        identifier = entity.get("lodging_id") or entity["poi_id"]
        entity["deep_links"] = [entity_urls[identifier]]
    for claim_item in candidates_value["claims"]:
        claim_item["source_url"] = entity_urls[claim_item["subject_ref"]]
        claim_item["provider"] = "synthetic-fixture"
    for unknown_item in candidates_value["unknowns"]:
        unknown_item["provider"] = "synthetic-fixture"
        unknown_item["reason"] = "synthetic value intentionally left for verification"
    return {"request": request_value, "candidates": candidates_value}


def write_journey_lodging_chain_fixture() -> Path:
    value = journey_six_city_lodging_chain_case()
    JOURNEY_LODGING_CHAIN_FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    JOURNEY_LODGING_CHAIN_FIXTURE.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return JOURNEY_LODGING_CHAIN_FIXTURE


def grouped_departures_demo() -> Mapping[str, Any]:
    request_value = {
        "traveler_groups": [
            {
                "group_id": "family-beijing",
                "travelers": 2,
                "origin": {"ref_id": "city-beijing", "name": "北京", "city": "北京"},
            },
            {
                "group_id": "family-guangzhou",
                "travelers": 1,
                "origin": {"ref_id": "city-guangzhou", "name": "广州", "city": "广州"},
            },
        ],
        "meeting_anchor": {
            "location": {
                "ref_id": "airport-shanghai",
                "name": "上海虹桥国际机场",
                "city": "上海",
            },
            "meet_by": "2026-09-10T13:00:00+08:00",
            "buffer_minutes": 60,
        },
        "destinations": [
            {"ref_id": "city-shanghai", "name": "上海", "city": "上海"},
        ],
        "start_date": "2026-09-10",
        "end_date": "2026-09-10",
        "budget_cny": 5000,
        "interests": ["建筑", "滨水空间"],
        "pace": "balanced",
        "constraints": ["不执行任何交易动作"],
        "assumptions": ["分组交通使用仓库内全合成铁路夹具"],
        "locale": "zh-CN",
        "pasted_notes": None,
    }
    pois: List[Mapping[str, Any]] = []
    claims: List[Mapping[str, Any]] = []
    for index, (name, category) in enumerate((
        ("上海示例建筑漫步", "architecture"),
        ("上海示例滨水公园", "park"),
    ), start=1):
        poi_id = "poi-grouped-%d" % index
        claim_id = "claim-grouped-%d" % index
        point = {"lng": 121.470 + index * 0.001, "lat": 31.230}
        pois.append({
            "poi_id": poi_id,
            "name": name,
            "city": "上海",
            "category": category,
            "coordinates": {
                "source_crs": "WGS84",
                "native": point,
                "wgs84": point,
                "gcj02": None,
                "conversion": {
                    "status": "not-needed",
                    "method": "identity",
                    "version": "1",
                    "derived_fields": [],
                    "converted_at": None,
                    "accuracy_m": None,
                },
            },
            "recommended_duration_minutes": 45,
            "opening_windows": [],
            "price": None,
            "deep_links": ["https://example.com/grouped-departures/%d" % index],
            "claim_ids": [claim_id],
        })
        claims.append(claim(
            claim_id,
            poi_id,
            "/name",
            "synthetic grouped-departure candidate",
            "https://example.com/grouped-departures/%d" % index,
            "hypothesis",
            0.5,
        ))
    return {
        "request": request_value,
        "candidates": {
            "candidates_version": "1.0.0",
            "pois": pois,
            "lodgings": [],
            "claims": claims,
            "unknowns": [],
        },
    }


def rail_transcript(from_city: str, to_city: str, travel_date: str) -> Mapping[str, Any]:
    station_map = {from_city: STATIONS[from_city], to_city: STATIONS[to_city]}
    error_result = {
        "content": [{"type": "text", "text": "synthetic fixture upstream error"}],
        "isError": True,
    }
    return {
        "protocol_version": "2025-06-18",
        "server_info": {"name": "12306-mcp", "version": "0.3.10"},
        "tools": list(RAIL_TOOLS),
        "calls": [
            {
                "name": "get-station-code-of-citys",
                "arguments": {"citys": "%s|%s" % (from_city, to_city)},
                "result": {"content": [{"type": "text", "text": compact(station_map)}]},
            },
            {
                "name": "get-tickets",
                "arguments": {
                    "date": travel_date,
                    "fromStation": STATIONS[from_city]["station_code"],
                    "toStation": STATIONS[to_city]["station_code"],
                    "trainFilterFlags": "GD",
                    "format": "json",
                },
                "result": error_result,
            },
        ],
    }


def station_transcript(city: str) -> Mapping[str, Any]:
    return {
        "protocol_version": "2025-06-18",
        "server_info": {"name": "12306-mcp", "version": "0.3.10"},
        "tools": list(RAIL_TOOLS),
        "calls": [{
            "name": "get-station-code-of-citys",
            "arguments": {"citys": city},
            "result": {"content": [{"type": "text", "text": compact({city: STATIONS[city]})}]},
        }],
    }


def rail_fixture(case: str, body: Mapping[str, Any], capability: str, parameters: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "fixture_version": 1,
        "provider": "rail12306",
        "provider_version": "0.3.10",
        "case": case,
        "captured_at": RAIL_CAPTURED_AT,
        "source": "locally generated synthetic 12306 MCP response; contains no captured provider data",
        "redacted": False,
        "contains_personal_data": False,
        "credential_state": "configured",
        "request": {
            "request_id": "plan-fixture-%s" % case,
            "capability": capability,
            "parameters": dict(parameters),
            "deadline_ms": 1000,
            "as_of": parameters.get("date", "2026-09-03"),
            "cache_policy": "bypass",
            "trace": {"stage": "plan-fixture"},
        },
        "transport": {"kind": "response", "status_code": 200, "headers": {}, "body": body},
    }


def compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))


def write(path: Path, value: Any) -> Mapping[str, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(encoded)
    return {"path": path.relative_to(OUTPUT).as_posix(), "sha256": hashlib.sha256(encoded).hexdigest()}


def build() -> Sequence[Mapping[str, Any]]:
    beijing = {"ref_id": "city-beijing", "name": "北京", "city": "北京"}
    shanghai = {"ref_id": "city-shanghai", "name": "上海", "city": "上海"}
    hangzhou = {"ref_id": "city-hangzhou", "name": "杭州", "city": "杭州"}
    return [
        {
            "case": "beijing-shanghai-3d",
            "request": request(beijing, shanghai, "2026-10-16", "2026-10-18", 2, ["建筑", "博物馆", "本帮菜"]),
            "candidates": candidates("bjs", ("人民广场片区候选", "上海", "人民广场", "2026-10-16", "2026-10-18"), [
                ("bund", "外滩建筑步行", "上海", "architecture", "2026-10-16T16:00:00+08:00", "2026-10-16T19:00:00+08:00", 120, "https://www.shanghai.gov.cn/"),
                ("museum", "上海博物馆", "上海", "museum", "2026-10-17T09:30:00+08:00", "2026-10-17T12:30:00+08:00", 120, "https://www.shanghaimuseum.net/"),
                ("food", "本帮菜午餐", "上海", "food", "2026-10-17T12:30:00+08:00", "2026-10-17T14:00:00+08:00", 60, "https://www.shanghai.gov.cn/"),
                ("xuhui", "徐汇历史建筑", "上海", "architecture", "2026-10-18T09:30:00+08:00", "2026-10-18T12:30:00+08:00", 120, "https://www.shanghai.gov.cn/"),
            ]),
            "rail": rail_fixture("beijing-shanghai-outside-presale", rail_transcript("北京", "上海", "2026-10-16"), "rail", {"date": "2026-10-16"}),
        },
        {
            "case": "shanghai-weekend-2d",
            "request": request(None, shanghai, "2026-10-16", "2026-10-17", 1, ["建筑", "园林", "美食"]),
            "candidates": candidates("sha", ("南京东路片区候选", "上海", "南京东路", "2026-10-16", "2026-10-18"), [
                ("bund", "外滩晨间步行", "上海", "architecture", "2026-10-16T09:00:00+08:00", "2026-10-16T12:00:00+08:00", 120, "https://www.shanghai.gov.cn/"),
                ("food", "本帮菜午餐", "上海", "food", "2026-10-16T12:30:00+08:00", "2026-10-16T14:00:00+08:00", 60, "https://www.shanghai.gov.cn/"),
                ("museum", "上海博物馆", "上海", "museum", "2026-10-17T09:00:00+08:00", "2026-10-17T12:00:00+08:00", 120, "https://www.shanghaimuseum.net/"),
                ("garden", "古典园林候选", "上海", "garden", "2026-10-17T14:00:00+08:00", "2026-10-17T17:00:00+08:00", 120, "https://www.shanghai.gov.cn/"),
            ]),
            "rail": rail_fixture("shanghai-local-unused-recording", station_transcript("上海"), "station", {"city": "上海"}),
        },
        {
            "case": "beijing-hangzhou-4d",
            "request": request(beijing, hangzhou, "2026-10-16", "2026-10-19", 2, ["湖景", "博物馆", "茶文化", "杭帮菜"]),
            "candidates": candidates("bjh", ("湖滨片区候选", "杭州", "湖滨", "2026-10-16", "2026-10-19"), [
                ("west-lake", "西湖湖滨步行", "杭州", "scenic", "2026-10-16T16:00:00+08:00", "2026-10-16T19:00:00+08:00", 120, "https://www.hangzhou.gov.cn/"),
                ("museum", "浙江省博物馆候选", "杭州", "museum", "2026-10-17T09:00:00+08:00", "2026-10-17T12:00:00+08:00", 120, "https://www.zhejiangmuseum.com/"),
                ("food", "杭帮菜午餐", "杭州", "food", "2026-10-17T12:30:00+08:00", "2026-10-17T14:00:00+08:00", 60, "https://www.hangzhou.gov.cn/"),
                ("tea", "龙井茶文化候选", "杭州", "tea", "2026-10-17T15:00:00+08:00", "2026-10-17T18:00:00+08:00", 120, "https://www.hangzhou.gov.cn/"),
                ("temple", "灵隐文化候选", "杭州", "culture", "2026-10-18T09:00:00+08:00", "2026-10-18T12:00:00+08:00", 120, "https://www.hangzhou.gov.cn/"),
                ("canal", "京杭大运河候选", "杭州", "history", "2026-10-18T15:00:00+08:00", "2026-10-18T18:00:00+08:00", 120, "https://www.hangzhou.gov.cn/"),
                ("market", "杭州城市漫步", "杭州", "architecture", "2026-10-19T09:00:00+08:00", "2026-10-19T12:00:00+08:00", 120, "https://www.hangzhou.gov.cn/"),
            ]),
            "rail": rail_fixture("beijing-hangzhou-outside-presale", rail_transcript("北京", "杭州", "2026-10-16"), "rail", {"date": "2026-10-16"}),
        },
    ]


def main() -> int:
    files: List[Mapping[str, str]] = []
    cases = build()
    for item in cases:
        folder = OUTPUT / item["case"]
        files.append(write(folder / "request.json", item["request"]))
        files.append(write(folder / "candidates.json", item["candidates"]))
        files.append(write(folder / "rail.json", item["rail"]))

    example_encoded = (json.dumps(cases[0]["candidates"], ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    reference_path = ROOT / "plugins" / "china-trip-weaver" / "references" / "candidates.example.json"
    if reference_path.read_bytes() != example_encoded:
        raise RuntimeError("packaged candidate reference differs from its generated source")
    demo_path = ROOT / "demo" / "candidates.json"
    demo_path.parent.mkdir(parents=True, exist_ok=True)
    demo_path.write_bytes(example_encoded)
    (ROOT / "demo" / "request.json").write_text(
        json.dumps(cases[0]["request"], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    multicity = multicity_demo()
    multicity_root = ROOT / "demo" / "multicity-5d"
    multicity_root.mkdir(parents=True, exist_ok=True)
    for name in ("request", "candidates"):
        (multicity_root / (name + ".json")).write_text(
            json.dumps(multicity[name], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    grouped = grouped_departures_demo()
    grouped_root = ROOT / "demo" / "grouped-departures"
    grouped_root.mkdir(parents=True, exist_ok=True)
    for name in ("request", "candidates"):
        (grouped_root / (name + ".json")).write_text(
            json.dumps(grouped[name], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    invalid_root = OUTPUT / "candidates-invalid"
    base = copy.deepcopy(cases[0]["candidates"])
    missing_claim = copy.deepcopy(base)
    missing_id = missing_claim["pois"][0]["claim_ids"][0]
    missing_claim["claims"] = [item for item in missing_claim["claims"] if item["claim_id"] != missing_id]
    files.append(write(invalid_root / "missing-poi-claim.json", missing_claim))
    additional = copy.deepcopy(base)
    additional["transport_legs"] = []
    files.append(write(invalid_root / "additional-property.json", additional))
    unknown_ref = copy.deepcopy(base)
    unknown_ref["unknowns"][0]["claim_id"] = "claim-does-not-exist"
    files.append(write(invalid_root / "unknown-claim-ref.json", unknown_ref))

    manifest = {
        "manifest_version": 1,
        "generated_by": "scripts/build_plan_fixtures.py",
        "case_count": len(cases),
        "invalid_count": 3,
        "files": sorted(files, key=lambda item: item["path"]),
    }
    write(OUTPUT / "manifest.json", manifest)
    write_journey_lodging_chain_fixture()
    print("wrote %d plan cases, 3 invalid candidates, one Journey lodging-chain fixture, and single/multi-city/grouped demo inputs; packaged reference verified" % len(cases))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
