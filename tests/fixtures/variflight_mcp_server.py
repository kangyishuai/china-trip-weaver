#!/usr/bin/env python3
"""Deterministic VariFlight MCP server for stdio transport tests."""

from __future__ import annotations

import json
import os
import sys


TOOLS = [
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
    print(json.dumps({"jsonrpc": "2.0", "id": identifier, "result": result}, ensure_ascii=False), flush=True)


def flight(date, depcity, arrcity):
    return {
        "FlightNo": "XX1001",
        "FlightCompany": "示例航空",
        "FlightDep": depcity,
        "FlightArr": arrcity,
        "FlightDepcode": "BEX",
        "FlightArrcode": "SHX",
        "FlightDeptimePlanDate": date + " 10:00:00",
        "FlightArrtimePlanDate": date + " 12:00:00",
        "FlightState": "计划",
        "FlightStateNum": 0,
        "OntimeRate": "88.00%",
        "ArrOntimeRate": "88.00%",
    }


def comfort(date):
    return {
        "FlightNo": "XX1001",
        "FlightDate": date,
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
        "Luggage": "示例规则",
        "Comfort": "示例良好",
    }


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "normal"
    forbidden = {
        "AMAP_WEBSERVICE_KEY", "FLYAI_API_KEY", "ANYSEARCH_API_KEY",
        "UNRELATED_TOKEN", "HOME",
    }
    if forbidden.intersection(os.environ):
        raise SystemExit("forbidden environment reached VariFlight")
    has_key = bool(os.environ.get("VARIFLIGHT_API_KEY") or os.environ.get("X_VARIFLIGHT_KEY"))
    if mode == "require-key" and not has_key:
        raise SystemExit("expected VariFlight key is missing")
    if mode == "no-key" and has_key:
        raise SystemExit("keyless probe received a key")
    if not os.path.isabs(os.environ.get("CTW_VARIFLIGHT_HOME", "")):
        raise SystemExit("isolated VariFlight home is missing")
    if "variflight_home_shim.cjs" not in os.environ.get("NODE_OPTIONS", ""):
        raise SystemExit("VariFlight home preload is missing")
    secret = os.environ.get("VARIFLIGHT_API_KEY") or os.environ.get("X_VARIFLIGHT_KEY")
    if secret:
        print("api_key=" + secret, file=sys.stderr, flush=True)

    for line in sys.stdin:
        message = json.loads(line)
        method = message.get("method")
        if method == "notifications/initialized":
            continue
        if method == "initialize":
            emit(message["id"], {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "variflight-mcp", "version": "1.0.3"},
            })
        elif method == "tools/list":
            names = TOOLS[:-1] if mode == "wrong-tools" else TOOLS
            emit(message["id"], {"tools": [{
                "name": name,
                "inputSchema": {"type": "object", "properties": {}},
            } for name in names]})
        elif method == "tools/call":
            name = message["params"]["name"]
            arguments = message["params"]["arguments"]
            if name == "searchFlightsByDepArr":
                payload = {
                    "code": 200,
                    "message": "Success",
                    "data": [flight(arguments["date"], arguments["depcity"], arguments["arrcity"])],
                    "request_id": "fixture",
                    "timestamp": 0,
                }
            elif name == "flightHappinessIndex":
                payload = {
                    "code": 200,
                    "message": "Success",
                    "data": [comfort(arguments["date"])],
                    "request_id": "fixture",
                    "timestamp": 0,
                }
            else:
                payload = {"code": 200, "message": "Success", "data": []}
            emit(message["id"], {
                "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}],
            })


if __name__ == "__main__":
    main()
