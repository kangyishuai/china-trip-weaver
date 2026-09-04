#!/usr/bin/env python3
"""Deterministic FlyAI CLI subprocess used by transport contract tests."""

from __future__ import annotations

import json
import os
import sys
import time


ROOT_HELP = """Usage: flyai [options] [command]
Commands:
  search-hotel|search-hotels [options]
  search-flight [options]
"""
HOTEL_HELP = """Usage: flyai search-hotel [options]
  --dest-name <NAME>
  --check-in-date <YYYY-MM-DD>
  --check-out-date <YYYY-MM-DD>
"""
FLIGHT_HELP = """Usage: flyai search-flight [options]
  --origin <CITY>
  --destination <CITY>
  --dep-date <YYYY-MM-DD>
  --journey-type <1|2>
"""


def hotel_item():
    return {
        "address": "示例路100号",
        "detailUrl": "https://www.fliggy.com/hotel/search",
        "interestsPoi": "近示例地标",
        "latitude": "31.000000",
        "longitude": "121.000000",
        "name": "示例酒店·人民广场店",
        "price": "¥1xx",
        "shId": "SYNTHETIC-HOTEL-1001",
        "star": "示例型",
    }


def flight_item(travel_date="2026-09-10"):
    return {
        "journeys": [{
            "journeyType": "直达",
            "segments": [{
                "arrDateTime": travel_date + " 12:00:00",
                "arrStationName": "上海示例机场",
                "depDateTime": travel_date + " 10:00:00",
                "depStationName": "北京示例机场",
                "duration": "120",
                "marketingTransportName": "示例航空",
                "marketingTransportNo": "XX1001",
                "seatClassName": "经济舱",
            }],
            "totalDuration": "120",
        }],
        "jumpUrl": "https://www.fliggy.com/flight/search",
        "ticketPrice": "1001.00",
        "totalDuration": "120",
    }


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "normal"
    args = sys.argv[2:]
    forbidden = {
        "AMAP_WEBSERVICE_KEY", "VARIFLIGHT_API_KEY", "X_VARIFLIGHT_KEY",
        "ANYSEARCH_API_KEY", "UNRELATED_TOKEN", "HOME",
    }
    if forbidden.intersection(os.environ):
        raise SystemExit("forbidden environment reached FlyAI")
    if mode == "require-key" and "FLYAI_API_KEY" not in os.environ:
        raise SystemExit("expected FlyAI key is missing")
    if not os.path.isabs(os.environ.get("CTW_FLYAI_HOME", "")):
        raise SystemExit("isolated FlyAI home is missing")
    if "flyai_home_shim.cjs" not in os.environ.get("NODE_OPTIONS", ""):
        raise SystemExit("FlyAI home preload is missing")
    if os.environ.get("FLYAI_API_KEY"):
        print("api_key=" + os.environ["FLYAI_API_KEY"], file=sys.stderr)

    if args == ["--help"]:
        print("wrong root help" if mode == "bad-root-help" else ROOT_HELP)
        return
    if len(args) == 2 and args[1] == "--help":
        if mode == "bad-command-help":
            print("wrong command help")
        elif args[0] == "search-hotel":
            print(HOTEL_HELP)
        elif args[0] == "search-flight":
            print(FLIGHT_HELP)
        else:
            raise SystemExit("unexpected help command")
        return
    if mode == "slow":
        time.sleep(2)
    command = args[0]
    if command == "search-hotel":
        payload = {"data": {"itemList": [hotel_item()]}, "message": "success", "status": 0, "systemMessage": "synthetic fixture"}
    elif command == "search-flight":
        date_index = args.index("--dep-date") + 1
        payload = {"data": {"itemList": [flight_item(args[date_index])]}, "message": "success", "status": 0, "systemMessage": "synthetic fixture"}
    else:
        raise SystemExit("unexpected business command")
    if mode == "wrong-shape":
        payload["data"]["itemList"] = {}
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
