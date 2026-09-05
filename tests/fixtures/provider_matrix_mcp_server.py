#!/usr/bin/env python3
"""Synthetic MCP failures used only by the Book 23 provider matrix tests."""

from __future__ import annotations

import json
import os
import sys


RAIL_TOOLS = [
    "get-current-date",
    "get-stations-code-in-city",
    "get-station-code-of-citys",
    "get-station-code-by-names",
    "get-station-by-telecode",
    "get-tickets",
    "get-interline-tickets",
    "get-train-route-stations",
]
VARIFLIGHT_TOOLS = [
    "searchFlightsByDepArr",
    "searchFlightsByNumber",
    "getFlightTransferInfo",
    "flightHappinessIndex",
    "getRealtimeLocationByAnum",
    "getTodayDate",
    "getFutureWeatherByAirport",
    "searchFlightItineraries",
    "getFlightPriceByCities",
]


def emit(identifier, result):
    print(json.dumps(
        {"jsonrpc": "2.0", "id": identifier, "result": result},
        ensure_ascii=False,
    ), flush=True)


def text_result(value, *, is_error=False):
    text = value if isinstance(value, str) else json.dumps(
        value, ensure_ascii=False, separators=(",", ":"),
    )
    result = {"content": [{"type": "text", "text": text}]}
    if is_error:
        result["isError"] = True
    return result


def flight(date, dep_city, arr_city):
    return {
        "FlightNo": "XX1001",
        "FlightCompany": "示例航空",
        "FlightDep": dep_city,
        "FlightArr": arr_city,
        "FlightDepcode": "BEX",
        "FlightArrcode": "SHX",
        "FlightDeptimePlanDate": date + " 10:00:00",
        "FlightArrtimePlanDate": date + " 12:00:00",
        "FlightState": "计划",
        "FlightStateNum": 0,
        "OntimeRate": "88.00%",
        "ArrOntimeRate": "88.00%",
    }


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "rail-station-rate-limit":
        tools = RAIL_TOOLS
        server = {"name": "12306-mcp", "version": "0.3.10"}
    elif mode == "variflight-comfort-network":
        tools = VARIFLIGHT_TOOLS
        server = {"name": "variflight-mcp", "version": "1.0.3"}
        secret = os.environ.get("VARIFLIGHT_API_KEY") or os.environ.get("X_VARIFLIGHT_KEY")
        if secret:
            print("api_key=" + secret, file=sys.stderr, flush=True)
    else:
        raise SystemExit("unsupported synthetic matrix mode")

    for line in sys.stdin:
        message = json.loads(line)
        method = message.get("method")
        if method == "notifications/initialized":
            continue
        if method == "initialize":
            emit(message["id"], {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {}},
                "serverInfo": server,
            })
            continue
        if method == "tools/list":
            emit(message["id"], {"tools": [
                {"name": name, "inputSchema": {"type": "object", "properties": {}}}
                for name in tools
            ]})
            continue
        if method != "tools/call":
            continue

        name = message["params"]["name"]
        arguments = message["params"]["arguments"]
        if mode == "rail-station-rate-limit":
            if name != "get-stations-code-in-city":
                raise SystemExit("unexpected rail tool")
            print("fixture-call=" + name, file=sys.stderr, flush=True)
            emit(message["id"], text_result(
                "Error 429: synthetic station lookup rate limit",
                is_error=True,
            ))
            continue

        if name == "searchFlightsByDepArr":
            payload = {
                "code": 200,
                "message": "Success",
                "data": [flight(
                    arguments["date"], arguments["depcity"], arguments["arrcity"],
                )],
                "request_id": "synthetic-matrix",
                "timestamp": 0,
            }
            emit(message["id"], text_result(payload))
        elif name == "flightHappinessIndex":
            raise SystemExit(7)
        else:
            raise SystemExit("unexpected VariFlight tool")


if __name__ == "__main__":
    main()
