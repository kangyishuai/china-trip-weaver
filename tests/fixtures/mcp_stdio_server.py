#!/usr/bin/env python3
"""Deterministic subprocess fixture for exercising the real stdio client."""

from __future__ import annotations

import json
import os
import signal
import sys
import time


TOOLS = [
    "get-current-date",
    "get-stations-code-in-city",
    "get-station-code-of-citys",
    "get-station-code-by-names",
    "get-station-by-telecode",
    "get-tickets",
    "get-interline-tickets",
    "get-train-route-stations",
]
STATIONS = {
    "北京": {"station_code": "BEX", "station_name": "北京示例站"},
    "北京南": {"station_code": "BNX", "station_name": "北京南示例站"},
    "上海": {"station_code": "SHX", "station_name": "上海示例站"},
    "上海虹桥": {"station_code": "HXX", "station_name": "上海虹桥示例站"},
    "武夷山北": {"station_code": "WYX", "station_name": "武夷山北示例站"},
    "南平市": {"station_code": "NPX", "station_name": "南平市示例站"},
    "昆明南": {"station_code": "KMX", "station_name": "昆明南示例站"},
    "平潭": {"station_code": "PTX", "station_name": "平潭示例站"},
}
TRACE_MODES = {
    "g5-station-fallback",
    "all-stations-fallback",
    "station-inputs",
    "representative-fallback",
    "station-no-results",
    "station-ambiguous",
    "station-shape-drift",
    "tool-fingerprint-drift",
}


def emit(identifier, result):
    print(json.dumps({"jsonrpc": "2.0", "id": identifier, "result": result}, ensure_ascii=False), flush=True)


def text_result(value, is_error=False):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    result = {"content": [{"type": "text", "text": text}]}
    if is_error:
        result["isError"] = True
    return result


def errors_for(value):
    return {name: {"error": "未检索到城市。"} for name in value.split("|")}


def exact_station_payload(mode, station_names):
    names = station_names.split("|")
    if mode == "station-shape-drift":
        return []
    if mode in ("station-no-results", "station-ambiguous", "representative-fallback", "all-stations-fallback"):
        if mode == "station-ambiguous":
            return {
                name: STATIONS[name] if name == "昆明南" else {"error": "未检索到城市。"}
                for name in names
            }
        if mode == "all-stations-fallback":
            return {
                name: STATIONS[name] if name == "昆明南" else {"error": "未检索到城市。"}
                for name in names
            }
        return errors_for(station_names)
    if mode == "g5-station-fallback":
        return {
            name: STATIONS[name] if name in STATIONS else {"error": "未检索到城市。"}
            for name in names
        }
    return {
        name: STATIONS[name] if name in STATIONS else {"error": "未检索到城市。"}
        for name in names
    }


def representative_station_payload(mode, citys):
    if mode == "representative-fallback":
        return {
            name: STATIONS[name] if name in STATIONS else {"error": "未检索到城市。"}
            for name in citys.split("|")
        }
    if mode in ("g5-station-fallback", "all-stations-fallback", "station-no-results", "station-ambiguous"):
        return errors_for(citys)
    return {
        name: STATIONS[name] if name in STATIONS else {"error": "未检索到城市。"}
        for name in citys.split("|")
    }


def city_station_payload(mode, city):
    if mode == "all-stations-fallback" and city == "武夷山":
        return [{"station_code": "WYX", "station_name": "武夷山北示例站"}]
    if mode == "station-ambiguous" and city == "多站城":
        return [
            {"station_code": "AAX", "station_name": "多站城远站", "distance_meters": 8000},
            {"station_code": "BBX", "station_name": "多站城近站", "distance_meters": 1000},
        ]
    if mode == "station-no-results" or mode in ("g5-station-fallback", "all-stations-fallback", "station-ambiguous"):
        return "Error: City not found. "
    if city == "北京":
        return [{"station_code": "BEX", "station_name": "北京示例站"}]
    return "Error: City not found. "


def ticket_payload(arguments, service_number):
    from_code = arguments["fromStation"]
    to_code = arguments["toStation"]
    return [{
        "train_no": "SYNTHETIC-" + service_number,
        "start_date": "2026-09-10",
        "arrive_date": "2026-09-10",
        "start_train_code": service_number,
        "start_time": "16:00",
        "arrive_time": "20:00",
        "lishi": "04:00",
        "from_station": "合成出发站",
        "to_station": "合成到达站",
        "from_station_telecode": from_code,
        "to_station_telecode": to_code,
        "prices": [{"seat_name": "二等座", "num": "有", "price": 300}],
        "dw_flag": ["示例编组"],
    }]


def record_and_ignore_sigterm(signum, frame):
    del signum, frame
    print("fixture-received-sigterm", file=sys.stderr, flush=True)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "normal"
    if mode == "hang-after-eof":
        signal.signal(signal.SIGTERM, record_and_ignore_sigterm)
    if mode == "assert-minimal-env":
        forbidden = {
            "AMAP_WEBSERVICE_KEY",
            "FLYAI_API_KEY",
            "VARIFLIGHT_API_KEY",
            "X_VARIFLIGHT_KEY",
            "ANYSEARCH_API_KEY",
            "UNRELATED_TOKEN",
            "HOME",
        }
        if forbidden.intersection(os.environ):
            raise SystemExit("provider subprocess received a forbidden environment variable")
        if not os.path.isabs(os.environ.get("CTW_RAIL_HOME", "")):
            raise SystemExit("isolated rail home is missing")
        if "rail_home_shim.cjs" not in os.environ.get("NODE_OPTIONS", ""):
            raise SystemExit("rail home preload is missing")
    print("api" + "_key=" + "ctw-stdio-canary", file=sys.stderr, flush=True)
    for line in sys.stdin:
        message = json.loads(line)
        method = message.get("method")
        if method == "notifications/initialized":
            continue
        if method == "initialize":
            if mode == "slow":
                time.sleep(0.5)
            if mode == "invalid-json":
                print("not-json", flush=True)
                continue
            emit(message["id"], {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {"listChanged": True}},
                "serverInfo": {"name": "12306-mcp", "version": "0.3.10"},
            })
        elif method == "tools/list":
            tool_names = TOOLS[:-1] if mode == "tool-fingerprint-drift" else TOOLS
            emit(message["id"], {"tools": [{"name": name, "inputSchema": {"type": "object"}} for name in tool_names]})
        elif method == "tools/call":
            name = message["params"]["name"]
            arguments = message["params"]["arguments"]
            if mode in TRACE_MODES:
                print("fixture-call=" + name, file=sys.stderr, flush=True)
            if name == "get-station-code-by-names":
                payload = exact_station_payload(mode, arguments["stationNames"])
            elif name == "get-station-code-of-citys":
                payload = representative_station_payload(mode, arguments["citys"])
            elif name == "get-stations-code-in-city":
                payload = city_station_payload(mode, arguments["city"])
            else:
                if mode == "assert-time-bounds" and (
                    arguments.get("earliestStartTime") != 15
                    or arguments.get("latestStartTime") != 21
                ):
                    emit(message["id"], text_result("time bounds missing", is_error=True))
                    continue
                if mode == "g5-station-fallback" and (
                    arguments.get("fromStation") != "BNX"
                    or arguments.get("toStation") != "HXX"
                ):
                    emit(message["id"], text_result("station codes were not resolved", is_error=True))
                    continue
                if mode == "all-stations-fallback" and (
                    arguments.get("fromStation") != "WYX"
                    or arguments.get("toStation") != "KMX"
                ):
                    emit(message["id"], text_result("station codes were not resolved", is_error=True))
                    continue
                service_number = "G5" if mode == "g5-station-fallback" else "G1001"
                payload = ticket_payload(arguments, service_number)
                if mode in TRACE_MODES:
                    print(
                        "fixture-ticket-codes=%s|%s"
                        % (arguments.get("fromStation"), arguments.get("toStation")),
                        file=sys.stderr,
                        flush=True,
                    )
            emit(message["id"], text_result(payload))
    if mode == "hang-after-eof":
        print("fixture-received-stdin-eof", file=sys.stderr, flush=True)
        while True:
            time.sleep(60)


if __name__ == "__main__":
    main()
