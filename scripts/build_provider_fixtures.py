#!/usr/bin/env python3
"""Build the frozen, unmistakably synthetic provider fixture corpus."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "tests" / "fixtures" / "providers"
CAPTURED_AT = "2026-09-04T00:00:00+08:00"
RAIL_CAPTURED_AT = CAPTURED_AT
RAIL_SOURCE = "locally generated synthetic 12306 MCP response; contains no captured provider data"
AMAP_CAPTURED_AT = CAPTURED_AT
AMAP_SOURCE = "locally generated synthetic AMap-shaped response; contains no captured provider data"
AMAP_MUTATION_SOURCE = AMAP_SOURCE + "; failure case is a labeled synthetic mutation"
FLYAI_CAPTURED_AT = CAPTURED_AT
FLYAI_SOURCE = "locally generated synthetic keyless FlyAI-shaped response; contains no captured provider data"
FLYAI_MUTATION_SOURCE = FLYAI_SOURCE + "; failure case is a labeled synthetic mutation"
FLYAI_KEYED_SOURCE = "locally generated synthetic configured-key FlyAI-shaped response; contains no captured provider data"
VARIFLIGHT_CAPTURED_AT = CAPTURED_AT
VARIFLIGHT_SOURCE = "locally generated synthetic VariFlight-shaped response; contains no captured provider data"
VARIFLIGHT_MUTATION_SOURCE = VARIFLIGHT_SOURCE + "; failure case is a labeled synthetic mutation"
RAIL_TOOLS = [
    "get-current-date", "get-stations-code-in-city", "get-station-code-of-citys",
    "get-station-code-by-names", "get-station-by-telecode", "get-tickets",
    "get-interline-tickets", "get-train-route-stations",
]
VARIFLIGHT_TOOLS = [
    "searchFlightsByDepArr", "searchFlightsByNumber", "getFlightTransferInfo",
    "flightHappinessIndex", "getRealtimeLocationByAnum", "getTodayDate",
    "getFutureWeatherByAirport", "searchFlightItineraries", "getFlightPriceByCities",
]
PINS = {
    "host_web": "host-runtime",
    "rail12306": "0.3.10",
    "flyai": "1.0.16",
    "amap": "web-service-v5-v3-route",
    "variflight": "1.0.3",
    "anysearch": "runtime-probe-v1",
}
SCHEMA_REFS = {
    "poi": "#/$defs/poi",
    "leg": "#/$defs/transportLeg",
    "lodging": "#/$defs/lodging",
    "place": "#/$defs/placeRef",
}


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))


def request(capability: str, parameters: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "request_id": "fixture-request",
        "capability": capability,
        "parameters": dict(parameters),
        "deadline_ms": 1000,
        "as_of": "2026-10-16",
        "cache_policy": "bypass",
        "trace": {"stage": "provider-fixture"},
    }


def response(body: Any, status: int = 200, headers: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
    return {"kind": "response", "status_code": status, "headers": dict(headers or {}), "body": body}


def fixture(
    provider: str,
    case: str,
    req: Mapping[str, Any],
    transport: Mapping[str, Any],
    *,
    credential_state: str = "configured",
    health: str = "ready",
    error_class: Optional[str] = None,
    item_count: int = 0,
    schema_refs: Sequence[str] = (),
    calls: int = 1,
    sanitized: bool = False,
    source: str = "locally generated synthetic contract response; never captured from a provider",
    captured_at: str = CAPTURED_AT,
) -> Dict[str, Any]:
    return {
        "fixture_version": 1,
        "provider": provider,
        "provider_version": PINS[provider],
        "case": case,
        "captured_at": captured_at,
        "source": source,
        "redacted": False,
        "contains_personal_data": False,
        "credential_state": credential_state,
        "request": dict(req),
        "transport": dict(transport),
        "expected": {
            "health_status": health,
            "error_class": error_class,
            "item_count": item_count,
            "schema_refs": list(schema_refs),
            "transport_calls": calls,
            "sanitized": sanitized,
        },
    }


def error_matrix(provider: str, req: Mapping[str, Any], wrong_body: Any, malicious_body: Any, *, auth_missing: bool = False) -> List[Dict[str, Any]]:
    auth = fixture(
        provider, "auth", req, response({"error": "auth"}, 403),
        credential_state="missing" if auth_missing else "configured",
        health="missing" if auth_missing else "forbidden",
        error_class="credential_missing" if auth_missing else "forbidden",
        calls=0 if auth_missing else 1,
    )
    return [
        auth,
        fixture(provider, "rate_limit", req, response({"error": "quota"}, 429, {"Retry-After": "30"}), health="rate_limited", error_class="rate_limited"),
        fixture(provider, "timeout", req, {"kind": "timeout"}, health="degraded", error_class="timeout", calls=2),
        fixture(provider, "wrong_shape", req, response(wrong_body), health="contract_mismatch", error_class="contract_mismatch"),
        fixture(provider, "malicious", req, response(malicious_body), item_count=1, schema_refs=[SCHEMA_REFS["poi"] if provider in ("host_web", "amap", "anysearch") else SCHEMA_REFS["leg"]], sanitized=True),
    ]


def host_body(results: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    return {"results": list(results)}


def web_result(title: str, suffix: str = "museum", official: bool = True) -> Mapping[str, Any]:
    return {
        "title": title,
        "url": "https://www.shanghai.gov.cn/" + suffix,
        "snippet": "dated official information",
        "published_at": "2026-09-01T09:00:00+08:00",
        "city": "上海",
        "category": "museum",
        "official": official,
    }


RAIL_STATIONS = {
    "北京": {"station_code": "BEX", "station_name": "北京示例站"},
    "上海": {"station_code": "SHX", "station_name": "上海示例站"},
}
RAIL_TICKET = {
    "train_no": "SYNTHETIC-G1001",
    "start_date": "2026-09-10",
    "arrive_date": "2026-09-10",
    "start_train_code": "G1001",
    "start_time": "08:00",
    "arrive_time": "12:00",
    "lishi": "04:00",
    "from_station": "北京示例站",
    "to_station": "上海示例站",
    "from_station_telecode": "BEX",
    "to_station_telecode": "SHX",
    "prices": [
        {"seat_name": "商务座", "short": "swz", "seat_type_code": "9", "num": "2", "price": 1000, "discount": 100},
        {"seat_name": "一等座", "short": "zy", "seat_type_code": "M", "num": "有", "price": 500, "discount": 100},
        {"seat_name": "二等座", "short": "ze", "seat_type_code": "O", "num": "有", "price": 300, "discount": 100},
        {"seat_name": "无座", "short": "wz", "seat_type_code": "W", "num": "无", "price": 300, "discount": 100},
    ],
    "dw_flag": ["示例编组", "示例静音车厢"],
}
RAIL_INTERLINE = [{
    "lishi": "03:30",
    "start_time": "13:00",
    "start_date": "2026-09-10",
    "middle_date": "2026-09-10",
    "arrive_date": "2026-09-10",
    "arrive_time": "16:30",
    "from_station_code": "BEX",
    "from_station_name": "北京示例站",
    "middle_station_code": "NAX",
    "middle_station_name": "南京示例站",
    "end_station_code": "SHX",
    "end_station_name": "上海示例站",
    "start_train_code": "G1002",
    "first_train_no": "SYNTHETIC-G1002",
    "second_train_no": "SYNTHETIC-G1003",
    "train_count": 2,
    "ticketList": [
        {
            "train_no": "SYNTHETIC-G1002", "start_train_code": "G1002",
            "start_date": "2026-09-10", "arrive_date": "2026-09-10",
            "start_time": "13:00", "arrive_time": "15:00", "lishi": "02:00",
            "from_station": "北京示例站", "to_station": "南京示例站",
            "from_station_telecode": "BEX", "to_station_telecode": "NAX",
            "prices": [
                {"seat_name": "商务座", "short": "swz", "seat_type_code": "9", "num": "3", "price": 900, "discount": 100},
                {"seat_name": "一等座", "short": "zy", "seat_type_code": "M", "num": "有", "price": 450, "discount": 100},
                {"seat_name": "二等座", "short": "ze", "seat_type_code": "O", "num": "有", "price": 270, "discount": 100},
                {"seat_name": "优选一等座", "short": "zy", "seat_type_code": "D", "num": "有", "price": 600, "discount": 100},
                {"seat_name": "无座", "short": "wz", "seat_type_code": "W", "num": "无", "price": 270, "discount": 100},
            ],
            "dw_flag": ["示例编组"],
        },
        {
            "train_no": "SYNTHETIC-G1003", "start_train_code": "G1003",
            "start_date": "2026-09-10", "arrive_date": "2026-09-10",
            "start_time": "15:30", "arrive_time": "16:30", "lishi": "01:00",
            "from_station": "南京示例站", "to_station": "上海示例站",
            "from_station_telecode": "NAX", "to_station_telecode": "SHX",
            "prices": [
                {"seat_name": "商务座", "short": "swz", "seat_type_code": "9", "num": "1", "price": 600, "discount": 100},
                {"seat_name": "一等座", "short": "zy", "seat_type_code": "M", "num": "有", "price": 300, "discount": 100},
                {"seat_name": "二等座", "short": "ze", "seat_type_code": "O", "num": "有", "price": 180, "discount": 100},
                {"seat_name": "优选一等座", "short": "zy", "seat_type_code": "D", "num": "有", "price": 400, "discount": 100},
                {"seat_name": "无座", "short": "wz", "seat_type_code": "W", "num": "无", "price": 180, "discount": 100},
            ],
            "dw_flag": ["示例编组"],
        },
    ],
    "same_station": True,
    "same_train": False,
    "wait_time": "30分钟",
}]


def mcp_text_result(value: Any, *, is_error: bool = False) -> Mapping[str, Any]:
    result: Dict[str, Any] = {"content": [{"type": "text", "text": canonical(value) if not isinstance(value, str) else value}]}
    if is_error:
        result["isError"] = True
    return result


def rail_recording(
    payload: Any,
    *,
    date: str = "2026-09-10",
    from_city: str = "北京",
    to_city: str = "上海",
    tool_name: str = "get-tickets",
    tools: Sequence[str] = RAIL_TOOLS,
    result: Optional[Mapping[str, Any]] = None,
) -> Mapping[str, Any]:
    station_map = {city: copy.deepcopy(RAIL_STATIONS[city]) for city in dict.fromkeys((from_city, to_city))}
    calls = [{
        "name": "get-station-code-of-citys",
        "arguments": {"citys": "%s|%s" % (from_city, to_city)},
        "result": mcp_text_result(station_map),
    }]
    arguments: Dict[str, Any] = {
        "date": date,
        "fromStation": station_map[from_city]["station_code"],
        "toStation": station_map[to_city]["station_code"],
        "trainFilterFlags": "GD",
        "format": "json",
    }
    if tool_name == "get-tickets":
        arguments["limitedNum"] = 1
    else:
        arguments["limitedNum"] = 1
    calls.append({"name": tool_name, "arguments": arguments, "result": dict(result or mcp_text_result(payload))})
    return {
        "protocol_version": "2025-06-18",
        "server_info": {"name": "12306-mcp", "version": "0.3.10"},
        "tools": list(tools),
        "calls": calls,
    }


def rail_station_recording() -> Mapping[str, Any]:
    return {
        "protocol_version": "2025-06-18",
        "server_info": {"name": "12306-mcp", "version": "0.3.10"},
        "tools": list(RAIL_TOOLS),
        "calls": [{
            "name": "get-station-code-of-citys",
            "arguments": {"citys": "北京"},
            "result": mcp_text_result({"北京": copy.deepcopy(RAIL_STATIONS["北京"])}),
        }],
    }


def fly_body(items: Sequence[Mapping[str, Any]], command: str = "search-flight") -> Mapping[str, Any]:
    flags = {
        "search-flight": ["--origin", "--destination", "--dep-date", "--journey-type"],
        "search-hotel": ["--dest-name", "--check-in-date", "--check-out-date"],
    }[command]
    return {
        "cliVersion": "1.0.16", "commands": ["search-hotel", "search-flight"],
        "probe": {"command": command, "flags": flags},
        "status": 0, "message": "success",
        "systemMessage": "synthetic fixture; no provider request was made",
        "data": {"itemList": list(items)},
    }


def fly_empty_body() -> Mapping[str, Any]:
    body = dict(fly_body([]))
    body["status"] = 1
    body["message"] = "示例结果为空"
    body["data"] = None
    return body


def flight_item(number: str = "XX1001", price: Any = "1001.00") -> Mapping[str, Any]:
    return {
        "ticketPrice": price,
        "totalDuration": "120",
        "jumpUrl": "https://www.fliggy.com/flight/search",
        "journeys": [{"segments": [{
            "marketingTransportNo": number,
            "marketingTransportName": "示例航空",
            "depCityName": "北京",
            "arrCityName": "上海",
            "depStationName": "北京示例机场",
            "arrStationName": "上海示例机场",
            "depDateTime": "2026-09-10 10:00:00",
            "arrDateTime": "2026-09-10 12:00:00",
            "duration": "120",
            "seatClassName": "经济舱",
        }], "totalDuration": "120", "journeyType": "直达"}],
    }


def hotel_item(name: str = "示例酒店·人民广场店", price: Any = "¥1xx") -> Mapping[str, Any]:
    return {
        "shId": "SYNTHETIC-HOTEL-1001", "name": name, "address": "示例路100号",
        "interestsPoi": "近示例地标", "star": "示例型",
        "price": price,
        "detailUrl": "https://www.fliggy.com/hotel/search",
        "longitude": "121.000000", "latitude": "31.000000",
    }


def amap_poi(name: str = "上海博物馆(人民广场馆)", identifier: str = "SYNTHETIC-POI-1001", location: str = "121.000000,31.000000", city: str = "上海市") -> Mapping[str, Any]:
    return {
        "id": identifier,
        "name": name,
        "location": location,
        "cityname": city,
        "type": "科教文化服务;博物馆;博物馆",
        "typecode": "140100",
        "address": "示例大道100号",
        "adcode": "310000",
    }


def amap_poi_body(items: Sequence[Mapping[str, Any]], page_num: int = 1) -> Mapping[str, Any]:
    return {
        "status": "1", "info": "OK", "infocode": "10000", "count": str(len(items)),
        "api": "poi-v5", "page_num": page_num, "page_size": 1, "pois": list(items),
    }


def amap_route_body(api: str, duration: int, distance: int, key: str = "paths") -> Mapping[str, Any]:
    return {
        "status": "1", "info": "OK", "infocode": "10000", "count": "1", "api": api,
        "route": {key: [{"duration": str(duration), "distance": str(distance)}]},
    }


def amap_riding_body() -> Mapping[str, Any]:
    return {
        "api": "route-riding-v4",
        "errcode": 0,
        "errmsg": "OK",
        "data": {"paths": [{"duration": 800, "distance": 1800}]},
    }


def vari_body(kind: str, payload: Mapping[str, Any], tools: Sequence[str] = VARIFLIGHT_TOOLS) -> Mapping[str, Any]:
    body = {"kind": kind}
    body.update(payload)
    return {"tools": list(tools), "content": [{"type": "text", "text": canonical(body)}]}


def vari_live_body(tool: str, rows: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    payload = {
        "code": 200,
        "message": "Success",
        "data": list(rows),
        "request_id": "synthetic",
        "timestamp": 0,
    }
    return {
        "tools": list(VARIFLIGHT_TOOLS),
        "tool": tool,
        "content": [{"type": "text", "text": canonical(payload)}],
        "isError": False,
    }


def vari_live_flight() -> Mapping[str, Any]:
    return {
        "FlightNo": "XX1001",
        "FlightCompany": "示例航空",
        "FlightDep": "北京",
        "FlightArr": "上海",
        "FlightDepcode": "BEX",
        "FlightArrcode": "SHX",
        "FlightDeptimePlanDate": "2026-09-10 10:00:00",
        "FlightArrtimePlanDate": "2026-09-10 12:00:00",
        "FlightState": "计划",
        "FlightStateNum": 0,
        "OntimeRate": "88.00%",
        "ArrOntimeRate": "88.00%",
    }


def vari_live_comfort() -> Mapping[str, Any]:
    return {
        "FlightNo": "XX1001",
        "FlightDate": "2026-09-10",
        "GenericNew": "示例机型-100",
        "FlightYear": "10.0",
        "OntimeRate": "88%",
        "ArrOntimeRate": "88%",
        "SeatWidth": "示例舒适",
        "SeatSpace": "示例舒适",
        "SeatTilt": "示例标准",
        "Seatlayout": "3-3",
        "Food": "示例餐食",
        "WiFi": "示例无",
        "Socket": "示例有",
        "Luggage": {"carry_on": ["synthetic allowance"]},
    }


def vari_flight(number: str = "XX1002", price: Any = 1002.0) -> Mapping[str, Any]:
    return {
        "flight_no": number,
        "depart_at": "2026-10-16T08:00:00+08:00",
        "arrive_at": "2026-10-16T10:20:00+08:00",
        "duration_minutes": 140,
        "price": price,
    }


def any_body(results: Sequence[Mapping[str, Any]], *, requests: int = 1, auto_registered: bool = False) -> Mapping[str, Any]:
    return {
        "data": {"results": list(results)},
        "usage": {"requests": requests, "remaining": 999},
        "auto_registered": auto_registered,
    }


def any_result(title: str = "上海博物馆开放信息", suffix: str = "museum") -> Mapping[str, Any]:
    return {"title": title, "url": "https://www.shanghai.gov.cn/" + suffix, "snippet": "official result"}


def build() -> List[Dict[str, Any]]:
    fixtures: List[Dict[str, Any]] = []

    host_req = request("research", {"city": "上海", "dates": ["2026-10-16"]})
    fixtures.extend([
        fixture("host_web", "success", host_req, response(host_body([web_result("上海博物馆开放公告")])) , item_count=1, schema_refs=[SCHEMA_REFS["poi"]]),
        fixture("host_web", "empty", host_req, response(host_body([])), error_class="no_results"),
    ])
    fixtures.extend(error_matrix(
        "host_web", host_req, {"items": []},
        host_body([web_result("<script>bad()</script> 上海馆 \u001b[31m Authorization: Bearer canary", "malicious")]),
    ))
    fixtures.extend([
        fixture("host_web", "conflict", host_req, response(host_body([web_result("场馆周五开放", "open"), web_result("场馆周五闭馆", "closed")])), item_count=2, schema_refs=[SCHEMA_REFS["poi"], SCHEMA_REFS["poi"]]),
        fixture("host_web", "not_found", host_req, response({"error": "not found"}, 404), health="degraded", error_class="invalid_request"),
    ])

    rail_req = request("rail", {
        "from_ref": "city-beijing", "to_ref": "city-shanghai",
        "from_name": "北京", "to_name": "上海", "date": "2026-09-10",
    })
    empty_req = request("rail", {
        "from_ref": "city-beijing", "to_ref": "city-beijing",
        "from_name": "北京", "to_name": "北京", "date": "2026-09-10",
    })
    outside_req = request("rail", {
        "from_ref": "city-beijing", "to_ref": "city-shanghai",
        "from_name": "北京", "to_name": "上海", "date": "2026-10-16",
    })
    malicious_ticket = copy.deepcopy(RAIL_TICKET)
    malicious_ticket["start_train_code"] = "<b>G1001</b> \u001b[31m Authorization: Bearer canary"
    no_seat_ticket = copy.deepcopy(RAIL_TICKET)
    for seat in no_seat_ticket["prices"]:
        seat["num"] = "无"
    waitlist_ticket = copy.deepcopy(RAIL_TICKET)
    for seat in waitlist_ticket["prices"]:
        seat["num"] = "候补"
    cross_day_ticket = copy.deepcopy(RAIL_TICKET)
    cross_day_ticket.update({
        "train_no": "SYNTHETIC-G1004", "start_train_code": "G1004",
        "start_time": "23:00", "arrive_time": "07:00",
        "arrive_date": "2026-09-11", "lishi": "08:00",
    })
    rail_common = {"source": RAIL_SOURCE, "captured_at": RAIL_CAPTURED_AT}
    fixtures.extend([
        fixture("rail12306", "success", rail_req, response(rail_recording([RAIL_TICKET])), item_count=1, schema_refs=[SCHEMA_REFS["leg"]], **rail_common),
        fixture("rail12306", "empty", empty_req, response(rail_recording([], from_city="北京", to_city="北京")), error_class="no_results", **rail_common),
        fixture("rail12306", "auth", rail_req, response({"error": "auth"}, 403), health="forbidden", error_class="forbidden", **rail_common),
        fixture("rail12306", "rate_limit", rail_req, response({"error": "quota"}, 429, {"Retry-After": "30"}), health="rate_limited", error_class="rate_limited", **rail_common),
        fixture("rail12306", "timeout", rail_req, {"kind": "timeout"}, health="degraded", error_class="timeout", calls=2, **rail_common),
        fixture("rail12306", "wrong_shape", rail_req, response(rail_recording({})), health="contract_mismatch", error_class="contract_mismatch", **rail_common),
        fixture("rail12306", "malicious", rail_req, response(rail_recording([malicious_ticket])), item_count=1, schema_refs=[SCHEMA_REFS["leg"]], sanitized=True, **rail_common),
    ])
    station_req = request("station", {"city": "北京"})
    outside_result = mcp_text_result("synthetic fixture upstream error", is_error=True)
    fixtures.extend([
        fixture("rail12306", "station", station_req, response(rail_station_recording()), item_count=1, schema_refs=[SCHEMA_REFS["place"]], **rail_common),
        fixture("rail12306", "no_seat", rail_req, response(rail_recording([no_seat_ticket])), item_count=1, schema_refs=[SCHEMA_REFS["leg"]], **rail_common),
        fixture("rail12306", "waitlist", rail_req, response(rail_recording([waitlist_ticket])), item_count=1, schema_refs=[SCHEMA_REFS["leg"]], **rail_common),
        fixture("rail12306", "transfer", rail_req, response(rail_recording(RAIL_INTERLINE, tool_name="get-interline-tickets")), item_count=2, schema_refs=[SCHEMA_REFS["leg"], SCHEMA_REFS["leg"]], **rail_common),
        fixture("rail12306", "cross_day", rail_req, response(rail_recording([cross_day_ticket])), item_count=1, schema_refs=[SCHEMA_REFS["leg"]], **rail_common),
        fixture("rail12306", "pipe_drift", rail_req, response(rail_recording([], result=mcp_text_result("train|missing|columns"))), health="contract_mismatch", error_class="contract_mismatch", **rail_common),
        fixture("rail12306", "outside_presale", outside_req, response(rail_recording([], date="2026-10-16", result=outside_result)), health="degraded", error_class="no_results", **rail_common),
    ])

    fly_req = request("flight", {"from_ref": "city-beijing", "to_ref": "city-shanghai", "origin": "北京", "destination": "上海", "date": "2026-09-10"})
    fixtures.extend([
        fixture("flyai", "success", fly_req, response(fly_body([flight_item()])), credential_state="missing", item_count=1, schema_refs=[SCHEMA_REFS["leg"]], source=FLYAI_SOURCE, captured_at=FLYAI_CAPTURED_AT),
        fixture("flyai", "empty", fly_req, response(fly_empty_body()), error_class="no_results", source=FLYAI_KEYED_SOURCE + "; synthetic no-result envelope", captured_at=FLYAI_CAPTURED_AT),
    ])
    fixtures.extend(error_matrix(
        "flyai", fly_req, "not-json",
        fly_body([flight_item("<b>XX1002</b> \u001b[31m Authorization: Bearer canary")]),
    ))
    lodging_req = request("lodging", {"city": "上海", "check_in": "2026-09-10", "check_out": "2026-09-11", "travelers": 2})
    fixtures.extend([
        fixture("flyai", "hotel", lodging_req, response(fly_body([hotel_item()], "search-hotel")), credential_state="missing", item_count=1, schema_refs=[SCHEMA_REFS["lodging"]], source=FLYAI_SOURCE, captured_at=FLYAI_CAPTURED_AT),
        fixture("flyai", "hotel_exact_price", lodging_req, response(fly_body([hotel_item(price="¥101")], "search-hotel")), item_count=1, schema_refs=[SCHEMA_REFS["lodging"]], source=FLYAI_KEYED_SOURCE, captured_at=FLYAI_CAPTURED_AT),
        fixture("flyai", "version_help", fly_req, response(dict(fly_body([]), helpFingerprint="Usage: flyai [options] [command]")), credential_state="missing", error_class="no_results", source=FLYAI_SOURCE, captured_at=FLYAI_CAPTURED_AT),
        fixture("flyai", "trial_limit", fly_req, response({"error": "trial limit"}, 429), health="rate_limited", error_class="rate_limited"),
        fixture("flyai", "stderr_error", fly_req, {"kind": "network"}, health="degraded", error_class="network", calls=2),
        fixture("flyai", "non_json", fly_req, response("{broken"), health="contract_mismatch", error_class="contract_mismatch"),
        fixture("flyai", "price_missing", fly_req, response(fly_body([flight_item(price=None)])), health="contract_mismatch", error_class="contract_mismatch", source=FLYAI_MUTATION_SOURCE, captured_at=FLYAI_CAPTURED_AT),
    ])

    amap_req = request("poi", {"city": "上海", "keywords": "上海博物馆", "page_size": 1, "page_num": 1})
    fixtures.extend([
        fixture("amap", "success", amap_req, response(amap_poi_body([amap_poi()])), item_count=1, schema_refs=[SCHEMA_REFS["poi"]], source=AMAP_SOURCE, captured_at=AMAP_CAPTURED_AT),
        fixture("amap", "empty", amap_req, response(amap_poi_body([])), error_class="no_results", source=AMAP_MUTATION_SOURCE, captured_at=AMAP_CAPTURED_AT),
    ])
    fixtures.extend(error_matrix(
        "amap", amap_req, {"status": "1", "api": "place-v4", "pois": []},
        amap_poi_body([amap_poi("<script>bad()</script> 上海馆 \u001b[31m Authorization: Bearer canary", "B009")]),
        auth_missing=True,
    ))
    geocode_req = request("geocode", {"city": "上海", "address": "上海博物馆", "subject_ref": "poi-a"})
    route_base = {
        "from_ref": "poi-a", "to_ref": "poi-b",
        "origin": "121.0000000,31.0000000", "destination": "121.1000000,31.1000000",
        "city": "上海", "destination_city": "上海",
    }
    fixtures.extend([
        fixture("amap", "geocode", geocode_req, response({"status": "1", "info": "OK", "infocode": "10000", "count": "1", "api": "geocode-v3", "geocodes": [{"formatted_address": "上海市示例区示例点", "city": "上海市", "district": "示例区", "adcode": "310000", "location": "121.100000,31.100000", "level": "兴趣点"}]}), item_count=1, schema_refs=[SCHEMA_REFS["place"]], source=AMAP_SOURCE, captured_at=AMAP_CAPTURED_AT),
        fixture("amap", "walking", request("route", dict(route_base, travel_mode="walk")), response(amap_route_body("route-walking-v3", 1000, 2000)), item_count=1, schema_refs=[SCHEMA_REFS["leg"]], source=AMAP_SOURCE, captured_at=AMAP_CAPTURED_AT),
        fixture("amap", "transit", request("route", dict(route_base, travel_mode="transit")), response(amap_route_body("route-transit-v3", 1200, 3000, "transits")), item_count=1, schema_refs=[SCHEMA_REFS["leg"]], source=AMAP_SOURCE, captured_at=AMAP_CAPTURED_AT),
        fixture("amap", "driving", request("route", dict(route_base, travel_mode="drive")), response(amap_route_body("route-driving-v3", 600, 1500)), item_count=1, schema_refs=[SCHEMA_REFS["leg"]], source=AMAP_SOURCE, captured_at=AMAP_CAPTURED_AT),
        fixture("amap", "riding", request("route", dict(route_base, travel_mode="ride")), response(amap_riding_body()), item_count=1, schema_refs=[SCHEMA_REFS["leg"]], source=AMAP_SOURCE, captured_at=AMAP_CAPTURED_AT),
        fixture("amap", "unreachable", request("route", dict(route_base, travel_mode="walk")), response({"status": "1", "info": "OK", "infocode": "10000", "api": "route-walking-v3", "route": {"paths": []}}), error_class="no_results", source=AMAP_MUTATION_SOURCE, captured_at=AMAP_CAPTURED_AT),
        fixture("amap", "api_forbidden", geocode_req, response({"status": "0", "info": "INVALID_USER_KEY", "infocode": "10001", "api": "geocode-v3"}), health="forbidden", error_class="forbidden", source=AMAP_SOURCE + "; response used an intentionally invalid canary credential", captured_at=AMAP_CAPTURED_AT),
        fixture("amap", "http_unauthorized", amap_req, response({"error": "unauthorized"}, 401), health="forbidden", error_class="forbidden", source=AMAP_MUTATION_SOURCE, captured_at=AMAP_CAPTURED_AT),
        fixture("amap", "http_forbidden", amap_req, response({"error": "forbidden"}, 403), health="forbidden", error_class="forbidden", source=AMAP_MUTATION_SOURCE, captured_at=AMAP_CAPTURED_AT),
        fixture("amap", "schema_v3_drift", amap_req, response({"status": "1", "info": "OK", "api": "poi-v5", "page": 1, "offset": 20, "pois": [amap_poi()]}), health="contract_mismatch", error_class="contract_mismatch"),
        fixture("amap", "boundary_hk", amap_req, response(amap_poi_body([amap_poi("香港边界测试点", "SYNTHETIC-HK-1001", "114.000000,22.000000", "香港")])), item_count=1, schema_refs=[SCHEMA_REFS["poi"]]),
        fixture("amap", "pagination_page2", request("poi", {"city": "上海", "keywords": "博物馆", "page_size": 1, "page_num": 2}), response(amap_poi_body([amap_poi("上海自然博物馆", "SYNTHETIC-POI-1002", "121.200000,31.200000", "上海市")], page_num=2)), item_count=1, schema_refs=[SCHEMA_REFS["poi"]], source=AMAP_SOURCE, captured_at=AMAP_CAPTURED_AT),
    ])

    vari_req = request("flight", {
        "action": "search",
        "dep_city": "BJS",
        "arr_city": "SHA",
        "date": "2026-09-10",
        "from_ref": "airport-pek",
        "to_ref": "airport-sha",
        "subject_ref": "leg-flight",
        "subject_refs_by_service": {"XX1001": "leg-flight"},
    })
    fixtures.extend([
        fixture("variflight", "success", vari_req, response(vari_live_body("searchFlightsByDepArr", [vari_live_flight()])), source=VARIFLIGHT_SOURCE, captured_at=VARIFLIGHT_CAPTURED_AT),
        fixture("variflight", "empty", vari_req, response(vari_live_body("searchFlightsByDepArr", [])), error_class="no_results", source=VARIFLIGHT_MUTATION_SOURCE, captured_at=VARIFLIGHT_CAPTURED_AT),
    ])
    fixtures.extend(error_matrix(
        "variflight", vari_req, vari_body("flights", {"items": [vari_flight()]}, tools=VARIFLIGHT_TOOLS[:-1]),
        vari_body("flights", {"items": [vari_flight("<b>XX1002</b> \u001b[31m Authorization: Bearer canary")]}),
        auth_missing=True,
    ))
    weather_req = request("weather", {"subject_ref": "leg-flight", "airport": "SHA"})
    fixtures.extend([
        fixture("variflight", "tools_fingerprint", vari_req, response(dict(vari_body("flights", {"items": []}), probe={"tool_count": 9})), error_class="no_results"),
        fixture("variflight", "weather", weather_req, response(vari_body("weather", {"summary": "小雨，18°C"})), item_count=0),
        fixture("variflight", "comfort", request("flight", {"action": "comfort", "flight_no": "XX1001", "date": "2026-09-10", "subject_ref": "leg-flight"}), response(vari_live_body("flightHappinessIndex", [vari_live_comfort()])), source=VARIFLIGHT_SOURCE, captured_at=VARIFLIGHT_CAPTURED_AT),
        fixture("variflight", "raw_price", vari_req, response(vari_body("raw_price", {"items": [vari_flight("XX1003", 1003.0)]})), item_count=1, schema_refs=[SCHEMA_REFS["leg"]]),
        fixture("variflight", "forbidden", vari_req, response({"error": "balance disabled"}, 403), health="forbidden", error_class="forbidden"),
        fixture("variflight", "any_wrong_shape", vari_req, response({"tools": VARIFLIGHT_TOOLS, "content": [{"type": "text", "text": "[]"}]}), health="contract_mismatch", error_class="contract_mismatch"),
    ])

    any_req = request("research", {"city": "上海", "query": "2026-10-16 博物馆 开放"})
    fixtures.extend([
        fixture("anysearch", "success", any_req, response(any_body([any_result()])), item_count=1, schema_refs=[SCHEMA_REFS["poi"]]),
        fixture("anysearch", "empty", any_req, response(any_body([])), error_class="no_results"),
    ])
    fixtures.extend(error_matrix(
        "anysearch", any_req, {"results": []},
        any_body([any_result("<script>bad()</script> 上海馆 \u001b[31m Authorization: Bearer canary", "malicious")]),
        auth_missing=True,
    ))
    fixtures.extend([
        fixture("anysearch", "auto_register", any_req, response(any_body([], auto_registered=True)), health="unavailable", error_class="policy_blocked"),
        fixture("anysearch", "usage", any_req, response(any_body([any_result("上海当期活动", "events")], requests=3)), item_count=1, schema_refs=[SCHEMA_REFS["poi"]]),
        fixture("anysearch", "payment_required", any_req, response({"error": "anonymous daily quota"}, 402), health="rate_limited", error_class="rate_limited"),
    ])
    return fixtures


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    fixtures = build()
    manifest_files = []
    for item in fixtures:
        directory = OUTPUT / item["provider"]
        directory.mkdir(parents=True, exist_ok=True)
        relative = Path(item["provider"]) / (item["case"] + ".json")
        encoded = (json.dumps(item, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
        (OUTPUT / relative).write_bytes(encoded)
        manifest_files.append({"path": relative.as_posix(), "sha256": hashlib.sha256(encoded).hexdigest()})
    manifest = {
        "manifest_version": 1,
        "generated_by": "scripts/build_provider_fixtures.py",
        "fixture_count": len(manifest_files),
        "files": sorted(manifest_files, key=lambda item: item["path"]),
    }
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("wrote %d provider fixtures" % len(manifest_files))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
