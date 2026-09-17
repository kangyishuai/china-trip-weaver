from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "plugins" / "china-trip-weaver" / "src"
sys.path.insert(0, str(SRC))

from china_trip_weaver.weather import advice_for, forecast_available_on, split_city_names


def _forecast(**overrides):
    base = {
        "day_text": "晴", "night_text": "晴",
        "temp_high_c": 25, "temp_low_c": 15,
        "wind_day": "东1-3级", "wind_night": "东1-3级",
    }
    base.update(overrides)
    return base


class WeatherAdviceTests(unittest.TestCase):
    def test_rain_thunder_storm_or_typhoon_advises_bringing_rain_gear(self):
        advice = advice_for(_forecast(day_text="小雨", night_text="晴"))
        self.assertEqual(["带雨具，户外时段准备备选"], advice)

    def test_snow_or_ice_advises_extra_walking_time(self):
        advice = advice_for(_forecast(day_text="小雪", night_text="晴"))
        self.assertEqual(["路面湿滑，预留更多步行时间"], advice)

    def test_high_temperature_advises_avoiding_midday_outdoors(self):
        advice = advice_for(_forecast(temp_high_c=35))
        self.assertEqual(["高温，避开 12–15 点户外"], advice)

    def test_low_temperature_advises_keeping_warm_at_night(self):
        advice = advice_for(_forecast(temp_low_c=5))
        self.assertEqual(["夜间低温，注意保暖"], advice)

    def test_strong_wind_advises_checking_ferry_and_island_routes(self):
        advice = advice_for(_forecast(wind_day="北6-7级", wind_night="北6-7级"))
        self.assertEqual(["大风，轮渡/海岛航线可能停航，出发前核实"], advice)

    def test_mild_forecast_has_no_advice(self):
        self.assertEqual([], advice_for(_forecast()))


class WeatherHelperTests(unittest.TestCase):
    def test_split_city_names_splits_on_slash_and_dun_separators(self):
        self.assertEqual(["福州", "平潭"], split_city_names("福州／平潭"))
        self.assertEqual(["福州", "平潭"], split_city_names("福州/平潭"))
        self.assertEqual(["福州", "平潭", "厦门"], split_city_names("福州、平潭、厦门"))

    def test_forecast_available_on_is_travel_date_minus_three_days(self):
        self.assertEqual(date(2026, 9, 17), forecast_available_on(date(2026, 9, 20)))


if __name__ == "__main__":
    unittest.main()
