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


def emit(identifier, result):
    print(json.dumps({"jsonrpc": "2.0", "id": identifier, "result": result}, ensure_ascii=False), flush=True)


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
            emit(message["id"], {"tools": [{"name": name, "inputSchema": {"type": "object"}} for name in TOOLS]})
        elif method == "tools/call":
            name = message["params"]["name"]
            if name == "get-station-code-of-citys":
                payload = {
                    "北京": {"station_code": "BEX", "station_name": "北京示例站"},
                    "上海": {"station_code": "SHX", "station_name": "上海示例站"},
                }
            elif name == "get-stations-code-in-city":
                payload = [{"station_code": "BEX", "station_name": "北京示例站"}]
            else:
                arguments = message["params"]["arguments"]
                if mode == "assert-time-bounds" and (
                    arguments.get("earliestStartTime") != 15
                    or arguments.get("latestStartTime") != 21
                ):
                    emit(message["id"], {
                        "content": [{"type": "text", "text": "time bounds missing"}],
                        "isError": True,
                    })
                    continue
                payload = [{
                    "train_no": "SYNTHETIC-G1001",
                    "start_date": "2026-09-10",
                    "arrive_date": "2026-09-10",
                    "start_train_code": "G1001",
                    "start_time": "16:00",
                    "arrive_time": "20:00",
                    "lishi": "04:00",
                    "from_station": "北京示例站",
                    "to_station": "上海示例站",
                    "from_station_telecode": "BEX",
                    "to_station_telecode": "SHX",
                    "prices": [{"seat_name": "二等座", "num": "有", "price": 300}],
                    "dw_flag": ["示例编组"],
                }]
            emit(message["id"], {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}]})
    if mode == "hang-after-eof":
        print("fixture-received-stdin-eof", file=sys.stderr, flush=True)
        while True:
            time.sleep(60)


if __name__ == "__main__":
    main()
