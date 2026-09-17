"""Pure weather-forecast helpers: visibility window, name split, advice rules."""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Dict, List, Mapping, Optional, Sequence

FORECAST_DAYS = 4

_SPLIT_SEPARATORS = ("／", "/", "、")
_RAIN_KEYWORDS = ("雨", "雷", "暴", "台风")
_SNOW_KEYWORDS = ("雪", "冰")
_HIGH_TEMP_THRESHOLD_C = 35
_LOW_TEMP_THRESHOLD_C = 5
_STRONG_WIND_MIN_LEVEL = 6
_WIND_NUMBER_RE = re.compile(r"\d+")


def forecast_available_on(travel_date: date) -> date:
    """The earliest query day whose 当天+3天 window still covers `travel_date`."""

    return travel_date - timedelta(days=FORECAST_DAYS - 1)


def split_city_names(text: str) -> List[str]:
    parts: Sequence[str] = (text,)
    for separator in _SPLIT_SEPARATORS:
        next_parts: List[str] = []
        for part in parts:
            next_parts.extend(part.split(separator))
        parts = next_parts
    return [part.strip() for part in parts if part.strip()]


def advice_for(forecast: Mapping[str, object]) -> List[str]:
    advice: List[str] = []
    weather_text = str(forecast.get("day_text", "")) + str(forecast.get("night_text", ""))
    if any(keyword in weather_text for keyword in _RAIN_KEYWORDS):
        advice.append("带雨具，户外时段准备备选")
    if any(keyword in weather_text for keyword in _SNOW_KEYWORDS):
        advice.append("路面湿滑，预留更多步行时间")
    if _as_int(forecast.get("temp_high_c")) >= _HIGH_TEMP_THRESHOLD_C:
        advice.append("高温，避开 12–15 点户外")
    if _as_int(forecast.get("temp_low_c"), default=1000) <= _LOW_TEMP_THRESHOLD_C:
        advice.append("夜间低温，注意保暖")
    wind_text = str(forecast.get("wind_day", "")) + str(forecast.get("wind_night", ""))
    if any(int(match) >= _STRONG_WIND_MIN_LEVEL for match in _WIND_NUMBER_RE.findall(wind_text)):
        advice.append("大风，轮渡/海岛航线可能停航，出发前核实")
    return advice


def _as_int(value: object, *, default: int = -1000) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return value


def location_key_vote(codes: Sequence[str]) -> Optional[str]:
    """Majority vote among a day's POI adcodes; ties break on the lexicographically smallest code."""

    if not codes:
        return None
    counts: Dict[str, int] = {}
    for code in codes:
        counts[code] = counts.get(code, 0) + 1
    top = max(counts.values())
    return min(code for code, count in counts.items() if count == top)


def result_reason(error_class: Optional[str], warnings: Sequence[str]) -> Optional[str]:
    """Map an AMap weather query outcome to a Trip unknown reason, or None when a forecast was returned."""

    if error_class is None:
        return None
    for warning in warnings:
        if warning.startswith("weather_ambiguous:"):
            return warning
    if error_class == "no_results":
        return "weather_no_results"
    return "weather_provider_error:%s" % error_class
