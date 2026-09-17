from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "plugins" / "china-trip-weaver" / "src"
sys.path.insert(0, str(SRC))

from china_trip_weaver.clock import FixedClock
from china_trip_weaver.mobility import MobilityBackend
from china_trip_weaver.planning import RailBackend, _plan_weather, plan_trip
from china_trip_weaver.providers.base import ProviderEnvelope
from china_trip_weaver.render import validate_html
from china_trip_weaver.validate_trip import validate_trip

from tests.test_amap_live import ScriptedAmapTransport, credentials as amap_credentials

FIXED_NOW = "2026-09-04T00:00:00+08:00"
SHA_E2E = ROOT / "tests" / "fixtures" / "e2e" / "shanghai-weekend-2d"
WEATHER_CASTS = ("2026-09-04", "2026-09-05", "2026-09-06", "2026-09-07")


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def weather_body(adcode: str = "310000", city: str = "示例市", forecast_count: int = 1) -> Mapping[str, Any]:
    casts = [
        {
            "date": day,
            "dayweather": "晴", "nightweather": "多云",
            "daytemp": "28", "nighttemp": "20",
            "daywind": "东", "daypower": "3-4",
            "nightwind": "东", "nightpower": "3-4",
        }
        for day in WEATHER_CASTS
    ]
    forecast = {"adcode": adcode, "city": city, "reporttime": "2026-09-04 08:00:00", "casts": casts}
    return {"api": "weather-v3", "status": "1", "info": "OK", "forecasts": [forecast] * forecast_count}


class WeatherScriptedTransport(ScriptedAmapTransport):
    """Extends the plain mobility scripted transport with a scriptable ``weather`` capability."""

    def __init__(self, weather_bodies: Mapping[str, Mapping[str, Any]]) -> None:
        super().__init__()
        self._weather_bodies = dict(weather_bodies)
        self.weather_queries: List[str] = []

    def execute(self, provider, provider_request):
        if provider_request.capability != "weather":
            return super().execute(provider, provider_request)
        if provider != "amap":
            raise AssertionError(provider)
        self.calls += 1
        key = provider_request.parameters.get("adcode") or provider_request.parameters.get("city")
        self.weather_queries.append(key)
        return ProviderEnvelope(200, self._weather_bodies[key], {})


def _request(dates: Sequence[str]) -> Dict[str, Any]:
    base = load(SHA_E2E / "request.json")
    base["start_date"] = dates[0]
    base["end_date"] = dates[-1]
    return base


def _candidates(dates: Sequence[str]) -> Dict[str, Any]:
    base = load(SHA_E2E / "candidates.json")
    bund = next(item for item in base["pois"] if item["poi_id"] == "poi-sha-bund")
    claim_template = next(item for item in base["claims"] if item["claim_id"] == "claim-sha-bund-hours")
    pois: List[Mapping[str, Any]] = []
    claims: List[Mapping[str, Any]] = []
    for index, day in enumerate(dates):
        poi_id = "poi-sha-day-%d" % index
        claim_id = "claim-sha-day-%d-hours" % index
        poi = copy.deepcopy(bund)
        poi["poi_id"] = poi_id
        poi["name"] = "外滩晨间步行 第%d天" % (index + 1)
        poi["claim_ids"] = [claim_id]
        window = poi["opening_windows"][0]
        window["start_at"] = "%sT09:00:00+08:00" % day
        window["end_at"] = "%sT12:00:00+08:00" % day
        window["claim_id"] = claim_id
        claim = copy.deepcopy(claim_template)
        claim["claim_id"] = claim_id
        claim["subject_ref"] = poi_id
        pois.append(poi)
        claims.append(claim)
    lodgings: List[Mapping[str, Any]] = []
    if len(dates) > 1:
        lodging_claim = copy.deepcopy(next(item for item in base["claims"] if item["claim_id"] == "claim-sha-lodging-price"))
        claims.append(lodging_claim)
        lodging = copy.deepcopy(base["lodgings"][0])
        lodging["check_in"] = dates[0]
        lodging["check_out"] = dates[-1]
        lodgings.append(lodging)
    return {
        "candidates_version": base["candidates_version"],
        "pois": pois,
        "lodgings": lodgings,
        "claims": claims,
        "unknowns": [],
    }


class PlanWeatherLiveTripTests(unittest.TestCase):
    """Full plan_trip() runs: a live AMap mobility backend feeds the new weather stage."""

    def setUp(self) -> None:
        self.clock = FixedClock.from_iso(FIXED_NOW)
        self.rail = RailBackend.from_spec("off", ROOT)

    def _plan(self, dates: Sequence[str], weather_bodies: Mapping[str, Mapping[str, Any]], *, live: bool = True):
        request = _request(dates)
        candidates = _candidates(dates)
        if live:
            transport = WeatherScriptedTransport(weather_bodies)
            backend = MobilityBackend("live", amap_credentials(), transport)
        else:
            transport = None
            backend = MobilityBackend.from_spec("off", ROOT)
        result = plan_trip(request, candidates, self.clock, self.rail, backend)
        return result, transport

    def _assert_trip_is_valid(self, result) -> None:
        report = validate_trip(result.trip)
        self.assertTrue(report.ok, [item.render() for item in report.errors])
        html_report = validate_html(result.html, result.trip)
        self.assertTrue(html_report.ok, [item.render() for item in html_report.errors])

    def test_near_day_gets_forecast_within_horizon(self):
        result, transport = self._plan(["2026-09-05"], {"310000": weather_body()})
        day = result.trip["days"][0]
        self.assertIsNotNone(day["weather"])
        expected_keys = {
            "forecast_date", "adcode", "city", "day_text", "night_text",
            "temp_high_c", "temp_low_c", "wind_day", "wind_night", "reported_at",
            "advice", "claim_id",
        }
        self.assertEqual(expected_keys, set(day["weather"]))
        self.assertEqual("2026-09-05", day["weather"]["forecast_date"])
        self.assertIsNotNone(day["weather"]["claim_id"])
        weather_claims = [c for c in result.trip["claims"] if c["field_path"] == "/weather"]
        self.assertEqual(1, len(weather_claims))
        self.assertEqual(day["day_id"], weather_claims[0]["subject_ref"])
        self.assertEqual(day["weather"]["claim_id"], weather_claims[0]["claim_id"])
        self.assertEqual(["310000"], transport.weather_queries)
        self._assert_trip_is_valid(result)

    def test_far_day_beyond_forecast_horizon_is_a_typed_unknown(self):
        result, transport = self._plan(["2026-09-10"], {})
        day = result.trip["days"][0]
        self.assertIsNone(day["weather"])
        self.assertEqual([], transport.weather_queries)
        unknown = next(item for item in result.trip["unknowns"] if item["field_path"] == "/days/0/weather")
        self.assertTrue(unknown["reason"].startswith("weather_forecast_horizon:2026-09-07"))
        self.assertEqual("amap", unknown["provider"])
        self.assertIsNone(unknown["claim_id"])
        self._assert_trip_is_valid(result)

    def test_ambiguous_forecast_marks_every_sharing_day_unknown(self):
        dates = ["2026-09-05", "2026-09-06"]
        result, transport = self._plan(dates, {"310000": weather_body(forecast_count=2)})
        for index in range(2):
            day = result.trip["days"][index]
            self.assertIsNone(day["weather"])
            unknown = next(item for item in result.trip["unknowns"] if item["field_path"] == "/days/%d/weather" % index)
            self.assertEqual("weather_ambiguous:2", unknown["reason"])
        self.assertEqual(["310000"], transport.weather_queries)
        self._assert_trip_is_valid(result)

    def test_mobility_off_adds_no_weather_key_and_no_unknown(self):
        result, transport = self._plan(["2026-09-05"], {}, live=False)
        self.assertIsNone(transport)
        day = result.trip["days"][0]
        self.assertNotIn("weather", day)
        self.assertFalse(any(item["field_path"].endswith("/weather") for item in result.trip["unknowns"]))
        self._assert_trip_is_valid(result)

    def test_health_line_reports_weather_capability_and_dedupes_shared_key(self):
        dates = ["2026-09-05", "2026-09-06"]
        result, transport = self._plan(dates, {"310000": weather_body()})
        self.assertIsNotNone(result.trip["days"][0]["weather"])
        self.assertIsNotNone(result.trip["days"][1]["weather"])
        self.assertEqual(["310000"], transport.weather_queries)
        amap_health = next(item for item in result.trip["provider_health"] if item["provider"] == "amap")
        self.assertIn("weather", amap_health["capabilities"])
        self.assertIn("; weather=1 queried, 0 unknown", amap_health["reason"])
        self.assertIn("weather@adcode:310000:date=2026-09-04", result.business_calls)
        self._assert_trip_is_valid(result)


class PlanWeatherLocationKeyTests(unittest.TestCase):
    """Unit-level coverage of ``_plan_weather``'s adcode majority vote, independent of the full pipeline."""

    def setUp(self) -> None:
        self.clock = FixedClock.from_iso(FIXED_NOW)

    @staticmethod
    def _day(date: str, refs: Sequence[str]) -> Dict[str, Any]:
        return {
            "day_id": "day-1",
            "date": date,
            "city": "示例市",
            "slots": [{"ref_id": ref} for ref in refs],
        }

    def test_majority_vote_breaks_a_tie_on_the_smallest_adcode(self):
        days = [self._day("2026-09-05", ["poi-a", "poi-b"])]
        pois = [{"poi_id": "poi-a"}, {"poi_id": "poi-b"}]
        claims = [
            {"field_path": "/provider_identity", "subject_ref": "poi-a", "value": {"adcode": "320000"}},
            {"field_path": "/provider_identity", "subject_ref": "poi-b", "value": {"adcode": "310000"}},
        ]
        transport = WeatherScriptedTransport({"310000": weather_body(adcode="310000")})
        backend = MobilityBackend("live", amap_credentials(), transport)
        weather_claims, unknowns, business_calls, health = _plan_weather(
            days, pois, claims, backend, self.clock, FIXED_NOW,
        )
        self.assertEqual(("weather@adcode:310000:date=2026-09-04",), business_calls)
        self.assertEqual([], unknowns)
        self.assertEqual(1, len(weather_claims))
        self.assertEqual("day-1", weather_claims[0]["subject_ref"])
        self.assertEqual({"queried": 1, "unknown": 0}, health)

    def test_majority_vote_prefers_the_more_frequent_adcode(self):
        days = [self._day("2026-09-05", ["poi-a", "poi-b", "poi-c"])]
        pois = [{"poi_id": "poi-a"}, {"poi_id": "poi-b"}, {"poi_id": "poi-c"}]
        claims = [
            {"field_path": "/provider_identity", "subject_ref": "poi-a", "value": {"adcode": "320000"}},
            {"field_path": "/provider_identity", "subject_ref": "poi-b", "value": {"adcode": "310000"}},
            {"field_path": "/provider_identity", "subject_ref": "poi-c", "value": {"adcode": "310000"}},
        ]
        transport = WeatherScriptedTransport({"310000": weather_body(adcode="310000")})
        backend = MobilityBackend("live", amap_credentials(), transport)
        _, _, business_calls, _ = _plan_weather(days, pois, claims, backend, self.clock, FIXED_NOW)
        self.assertEqual(("weather@adcode:310000:date=2026-09-04",), business_calls)

    def test_no_poi_adcode_falls_back_to_city_name(self):
        days = [self._day("2026-09-05", [])]
        days[0]["city"] = "福州／平潭"
        transport = WeatherScriptedTransport({"福州": weather_body(adcode="350100", city="福州")})
        backend = MobilityBackend("live", amap_credentials(), transport)
        weather_claims, unknowns, business_calls, health = _plan_weather(
            days, [], [], backend, self.clock, FIXED_NOW,
        )
        self.assertEqual(("weather@city:福州:date=2026-09-04",), business_calls)
        self.assertEqual(1, len(weather_claims))


if __name__ == "__main__":
    unittest.main()
