from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "plugins" / "china-trip-weaver" / "src"
sys.path.insert(0, str(SRC))

from china_trip_weaver.clock import FixedClock, isoformat_seconds
from china_trip_weaver.contracts import canonical_json
from china_trip_weaver.evidence import make_claim
from china_trip_weaver.render import render_journey, validate_journey_html
from china_trip_weaver.validate_trip import validate_trip
from china_trip_weaver.weather import advice_for
from china_trip_weaver.weather_fold import fold_weather_into_journey, fold_weather_into_trip


JOURNEY_DEMO = ROOT / "demo" / "journey-16d"
CLOCK = FixedClock.from_iso("2026-09-22T09:00:00+08:00")
SOURCE_URL = "https://restapi.amap.com/v3/weather/weatherInfo"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def forecast_value(forecast_date, city, adcode, *, reported_at, temp_high_c=28, temp_low_c=20):
    return {
        "forecast_date": forecast_date,
        "adcode": adcode,
        "city": city,
        "day_text": "晴",
        "night_text": "多云",
        "temp_high_c": temp_high_c,
        "temp_low_c": temp_low_c,
        "wind_day": "东风 3-4 级",
        "wind_night": "东风 3-4 级",
        "reported_at": reported_at,
    }


def weather_claim(subject_ref, value, clock=CLOCK):
    return make_claim(
        subject_ref=subject_ref, field_path="/weather", value=value, source_url=SOURCE_URL,
        provider="amap", status="verified", confidence=0.7, mode="live", clock=clock,
        json_path="/forecasts/0/casts/0",
    )


def forecast_row(query, forecast_date, city, adcode, value):
    claim = weather_claim("weather-%s" % adcode, value, clock=CLOCK)
    row = {
        "date": forecast_date, "city": city, "adcode": adcode, "forecast": value,
        "advice": advice_for(value), "status": "forecast", "query": query,
    }
    return row, claim


def no_forecast_row(query, forecast_date, city):
    return {
        "date": forecast_date, "city": city, "adcode": None, "forecast": None,
        "advice": [], "status": "no_forecast", "query": query,
    }


def envelope(rows, claims, *, clock=CLOCK, provider_version="weather-v3-test"):
    return {
        "provider": "amap", "provider_version": provider_version,
        "queried_at": isoformat_seconds(clock), "forecasts": list(rows), "claims": list(claims),
    }


class WeatherFoldTests(unittest.TestCase):
    def setUp(self):
        self.journey = load(JOURNEY_DEMO / "journey.json")
        self.original_trips = copy.deepcopy(self.journey["trips"])

    def _first_two_days_result(self):
        row1, claim1 = forecast_row(
            "上海", "2026-10-01", "上海", "310000",
            forecast_value("2026-10-01", "上海", "310000", reported_at="2026-09-22T09:00:00+08:00"),
        )
        row2, claim2 = forecast_row(
            "上海", "2026-10-02", "上海", "310000",
            forecast_value("2026-10-02", "上海", "310000", reported_at="2026-09-22T09:00:00+08:00", temp_high_c=30),
        )
        return envelope([row1, row2], [claim1, claim2])

    def test_forecast_rows_add_weather_and_claims_other_trips_untouched(self):
        trip1 = copy.deepcopy(self.journey["trips"][0])
        result = self._first_two_days_result()

        patch_result = fold_weather_into_trip(trip1, result, CLOCK)
        self.assertIsNotNone(patch_result)
        trip = patch_result.trip
        patch = patch_result.patch

        self.assertEqual(trip["revision"]["number"], 2)
        self.assertEqual(patch["trigger"], "weather")
        add_ops = [
            op for op in patch["operations"]
            if op["op"] == "add" and op["path"].startswith("/days/") and op["path"].endswith("/weather")
        ]
        self.assertEqual(len(add_ops), 2)

        self.assertIsNotNone(trip["days"][0]["weather"])
        self.assertIsNotNone(trip["days"][1]["weather"])
        for untouched_index in (2, 3, 4):
            self.assertNotIn("weather", trip["days"][untouched_index])

        new_claims = {c["subject_ref"]: c for c in trip["claims"] if c["subject_ref"] in ("day-1", "day-2")}
        self.assertEqual(set(new_claims), {"day-1", "day-2"})
        self.assertEqual(trip["days"][0]["weather"]["claim_id"], new_claims["day-1"]["claim_id"])
        self.assertEqual(trip["days"][1]["weather"]["claim_id"], new_claims["day-2"]["claim_id"])

        amap_health = next(h for h in trip["provider_health"] if h["provider"] == "amap")
        self.assertIn("weather", amap_health["capabilities"])
        self.assertEqual(amap_health["status"], "ready")
        self.assertEqual(amap_health["mode"], "live")

        report = validate_trip(trip)
        self.assertTrue(report.ok, report.errors)

        self.assertEqual(canonical_json(self.journey["trips"][1]), canonical_json(self.original_trips[1]))
        self.assertEqual(canonical_json(self.journey["trips"][2]), canonical_json(self.original_trips[2]))

        journey_result = fold_weather_into_journey(self.journey, result, self.journey["revision"]["number"], CLOCK)
        self.assertIsNotNone(journey_result)
        self.assertEqual(journey_result["revision"]["number"], 2)
        self.assertEqual(journey_result["revision"]["created_by"], "system")
        self.assertEqual(canonical_json(journey_result["trips"][1]), canonical_json(self.original_trips[1]))
        self.assertEqual(canonical_json(journey_result["trips"][2]), canonical_json(self.original_trips[2]))

        rendered = render_journey(journey_result)
        html_report = validate_journey_html(rendered, journey_result)
        self.assertEqual(html_report.errors, (), html_report.errors)
        self.assertEqual(rendered.count('<p class="day-weather"'), 16)
        self.assertEqual(rendered.count("data-weather-date="), 2)

    def test_same_result_folded_twice_is_noop(self):
        trip1 = copy.deepcopy(self.journey["trips"][0])
        result = self._first_two_days_result()

        first = fold_weather_into_trip(trip1, result, CLOCK)
        self.assertIsNotNone(first)
        second = fold_weather_into_trip(first.trip, result, CLOCK)
        self.assertIsNone(second)

        journey_first = fold_weather_into_journey(self.journey, result, self.journey["revision"]["number"], CLOCK)
        self.assertIsNotNone(journey_first)
        journey_second = fold_weather_into_journey(
            journey_first, result, journey_first["revision"]["number"], CLOCK,
        )
        self.assertIsNone(journey_second)

    def test_reported_at_update_replaces_weather_and_claim_count_stays(self):
        trip1 = copy.deepcopy(self.journey["trips"][0])
        first = fold_weather_into_trip(trip1, self._first_two_days_result(), CLOCK)
        claims_after_first = len(first.trip["claims"])
        old_claim_id = first.trip["days"][0]["weather"]["claim_id"]

        later_clock = FixedClock.from_iso("2026-09-22T15:00:00+08:00")
        row1, claim1 = forecast_row(
            "上海", "2026-10-01", "上海", "310000",
            forecast_value("2026-10-01", "上海", "310000", reported_at="2026-09-22T14:00:00+08:00"),
        )
        second_result = envelope([row1], [claim1], clock=later_clock)

        second = fold_weather_into_trip(first.trip, second_result, later_clock)
        self.assertIsNotNone(second)
        trip = second.trip
        self.assertEqual(trip["revision"]["number"], 3)
        replace_ops = [
            op for op in second.patch["operations"]
            if op["op"] == "replace" and op["path"] == "/days/0/weather"
        ]
        self.assertEqual(len(replace_ops), 1)
        self.assertNotEqual(trip["days"][0]["weather"]["claim_id"], old_claim_id)
        self.assertEqual(len(trip["claims"]), claims_after_first)
        self.assertFalse(any(c["claim_id"] == old_claim_id for c in trip["claims"]))

        report = validate_trip(trip)
        self.assertTrue(report.ok, report.errors)

    def test_health_reason_keeps_only_one_weather_fold_note_after_two_folds(self):
        trip1 = copy.deepcopy(self.journey["trips"][0])
        row1, claim1 = forecast_row(
            "上海", "2026-10-01", "上海", "310000",
            forecast_value("2026-10-01", "上海", "310000", reported_at="2026-09-22T09:00:00+08:00"),
        )
        first_result = envelope([row1], [claim1])
        first = fold_weather_into_trip(trip1, first_result, CLOCK)
        self.assertIsNotNone(first)

        later_clock = FixedClock.from_iso("2026-09-22T15:00:00+08:00")
        row2, claim2 = forecast_row(
            "上海", "2026-10-01", "上海", "310000",
            forecast_value("2026-10-01", "上海", "310000", reported_at="2026-09-22T14:00:00+08:00"),
        )
        second_result = envelope([row2], [claim2], clock=later_clock)
        second = fold_weather_into_trip(first.trip, second_result, later_clock)
        self.assertIsNotNone(second)

        amap_health = next(h for h in second.trip["provider_health"] if h["provider"] == "amap")
        self.assertEqual(1, amap_health["reason"].count("days folded"))
        self.assertIn(second_result["queried_at"], amap_health["reason"])
        self.assertNotIn(first_result["queried_at"], amap_health["reason"])

        report = validate_trip(second.trip)
        self.assertTrue(report.ok, report.errors)

    def test_revision_conflict_and_missing_claim_raise(self):
        wrong_revision = self.journey["revision"]["number"] + 5
        with self.assertRaises(ValueError) as journey_ctx:
            fold_weather_into_journey(self.journey, self._first_two_days_result(), wrong_revision, CLOCK)
        self.assertIn("revision_conflict", str(journey_ctx.exception))

        trip1 = copy.deepcopy(self.journey["trips"][0])
        row, _claim = forecast_row(
            "上海", "2026-10-01", "上海", "310000",
            forecast_value("2026-10-01", "上海", "310000", reported_at="2026-09-22T09:00:00+08:00"),
        )
        mismatched_result = envelope([row], [])
        with self.assertRaises(ValueError) as trip_ctx:
            fold_weather_into_trip(trip1, mismatched_result, CLOCK)
        self.assertIn("weather_fold_claim_missing", str(trip_ctx.exception))

    def test_no_forecast_row_nulls_weather_with_unknown(self):
        trip1 = copy.deepcopy(self.journey["trips"][0])
        result = envelope([no_forecast_row("上海", "2026-10-04", "上海")], [])

        patch_result = fold_weather_into_trip(trip1, result, CLOCK)
        self.assertIsNotNone(patch_result)
        trip = patch_result.trip
        self.assertIn("weather", trip["days"][3])
        self.assertIsNone(trip["days"][3]["weather"])
        unknown = next(item for item in trip["unknowns"] if item["field_path"] == "/days/3/weather")
        self.assertEqual(unknown["reason"], "weather_no_results")

        report = validate_trip(trip)
        self.assertTrue(report.ok, report.errors)

    def test_query_disambiguates_compound_city_name(self):
        trip1 = copy.deepcopy(self.journey["trips"][0])
        trip1["days"][2]["city"] = "平潭／泉州"  # day-3, 2026-10-03; split -> ["平潭", "泉州"], target is "平潭"

        pingtan_value = forecast_value(
            "2026-10-03", "平潭县", "350128", reported_at="2026-09-22T09:00:00+08:00", temp_high_c=24,
        )
        quanzhou_value = forecast_value(
            "2026-10-03", "泉州市", "350500", reported_at="2026-09-22T09:00:00+08:00", temp_high_c=31,
        )
        row1, claim1 = forecast_row("平潭", "2026-10-03", "平潭县", "350128", pingtan_value)
        row2, claim2 = forecast_row("泉州", "2026-10-03", "泉州市", "350500", quanzhou_value)
        result = envelope([row1, row2], [claim1, claim2])

        patch_result = fold_weather_into_trip(trip1, result, CLOCK)
        self.assertIsNotNone(patch_result)
        trip = patch_result.trip
        self.assertEqual(trip["days"][2]["weather"]["temp_high_c"], 24)
        self.assertEqual(trip["days"][2]["weather"]["city"], "平潭县")

        report = validate_trip(trip)
        self.assertTrue(report.ok, report.errors)

    def test_fold_across_two_trips_bumps_journey_revision_once(self):
        row1, claim1 = forecast_row(
            "上海", "2026-10-05", "上海", "310000",
            forecast_value("2026-10-05", "上海", "310000", reported_at="2026-09-22T09:00:00+08:00"),
        )
        row2, claim2 = forecast_row(
            "杭州", "2026-10-06", "杭州", "330100",
            forecast_value("2026-10-06", "杭州", "330100", reported_at="2026-09-22T09:00:00+08:00", temp_high_c=27),
        )
        result = envelope([row1, row2], [claim1, claim2])

        journey_result = fold_weather_into_journey(self.journey, result, self.journey["revision"]["number"], CLOCK)
        self.assertIsNotNone(journey_result)
        self.assertEqual(journey_result["revision"]["number"], 2)
        self.assertEqual(journey_result["revision"]["parent_revision"], 1)
        self.assertEqual(journey_result["trips"][0]["revision"]["number"], 2)
        self.assertEqual(journey_result["trips"][1]["revision"]["number"], 2)
        self.assertEqual(canonical_json(journey_result["trips"][2]), canonical_json(self.original_trips[2]))


if __name__ == "__main__":
    unittest.main()
