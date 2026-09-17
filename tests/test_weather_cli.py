from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "china-trip-weaver"
SRC = PLUGIN / "src"
sys.path.insert(0, str(SRC))

from china_trip_weaver.contracts import ProviderRequest
from china_trip_weaver.providers import amap_http
from china_trip_weaver.providers.base import ContractMismatch

CTW = PLUGIN / "scripts" / "ctw"
AMAP_FIXTURES = ROOT / "tests" / "fixtures" / "providers" / "amap"
WEEKEND_TRIP = ROOT / "tests" / "fixtures" / "trips" / "schema" / "valid" / "weekend-live.json"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def run_weather(*extra_args, env=None):
    return subprocess.run(
        [str(CTW), "weather", *extra_args],
        text=True, capture_output=True, env=env,
    )


def _weather_request(parameters):
    return ProviderRequest(
        request_id="req-weather-contract",
        capability="weather",
        parameters=parameters,
        deadline_ms=5000,
        as_of="2026-09-04",
    )


class WeatherCommandTests(unittest.TestCase):
    """End-to-end subprocess coverage for `ctw weather` (`_cmd_weather`, cli.py).

    Every fixture-driven case replays a checked-in
    tests/fixtures/providers/amap/*.json response, the same style
    tests/test_rail_cli.py uses for `ctw rail`. Before this file, no test
    invoked `ctw weather` at all.
    """

    def test_city_fixture_with_matching_clock_returns_four_forecast_rows(self):
        result = run_weather(
            "--fixture", str(AMAP_FIXTURES / "weather.json"),
            "--fixed-clock", "2026-09-04T00:00:00+08:00",
            "--city", "示例市",
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        self.assertEqual(4, len(lines), result.stdout)
        for line in lines:
            self.assertIn("示例市", line)
        self.assertNotIn("预报未开放", result.stdout)
        self.assertNotIn("无预报", result.stdout)

    def test_empty_fixture_returns_no_forecast_and_exit_two(self):
        result = run_weather(
            "--fixture", str(AMAP_FIXTURES / "weather_empty.json"),
            "--fixed-clock", "2026-09-04T00:00:00+08:00",
            "--city", "示例市",
        )
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("无预报", result.stdout)

    def test_ambiguous_fixture_reports_no_forecast_with_ambiguous_note(self):
        result = run_weather(
            "--fixture", str(AMAP_FIXTURES / "weather_ambiguous.json"),
            "--fixed-clock", "2026-09-04T00:00:00+08:00",
            "--city", "示例区",
        )
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("无预报", result.stdout)
        self.assertIn("同名", result.stdout)

    def test_city_fixture_with_earlier_clock_marks_whole_batch_out_of_window(self):
        result = run_weather(
            "--fixture", str(AMAP_FIXTURES / "weather.json"),
            "--fixed-clock", "2026-09-01T00:00:00+08:00",
            "--city", "示例市",
        )
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        self.assertEqual(4, len(lines), result.stdout)
        for line in lines:
            self.assertIn("预报未开放", line)
            self.assertIn("可查日期", line)
        self.assertIn("可查日期 2026-09-01", result.stdout)
        self.assertIn("可查日期 2026-09-04", result.stdout)

    def test_trip_day_far_beyond_horizon_skips_query_and_reports_out_of_window(self):
        result = run_weather(
            "--fixture", str(AMAP_FIXTURES / "weather.json"),
            "--fixed-clock", "2026-09-04T00:00:00+08:00",
            "--trip", str(WEEKEND_TRIP),
        )
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        self.assertEqual(2, len(lines), result.stdout)
        self.assertIn("2026-10-16 上海 预报未开放，可查日期 2026-10-13", result.stdout)
        self.assertIn("2026-10-17 上海 预报未开放，可查日期 2026-10-14", result.stdout)

    def test_journey_flattens_and_sorts_trip_days_with_compound_city_split(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            journey_path = Path(temporary) / "journey.json"
            journey_path.write_text(json.dumps({
                "trips": [
                    {"days": [
                        {"date": "2026-10-01", "city": "上海"},
                        {"date": "2026-10-02", "city": "上海／苏州"},
                    ]},
                    {"days": [
                        {"date": "2026-09-30", "city": "北京"},
                    ]},
                ],
            }), encoding="utf-8")
            result = run_weather(
                "--fixture", str(AMAP_FIXTURES / "weather.json"),
                "--fixed-clock", "2026-09-04T00:00:00+08:00",
                "--journey", str(journey_path),
            )
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        self.assertEqual(4, len(lines), result.stdout)
        self.assertTrue(lines[0].startswith("2026-09-30 北京"), lines)
        self.assertTrue(lines[1].startswith("2026-10-01 上海"), lines)
        self.assertTrue(lines[2].startswith("2026-10-02 上海"), lines)
        self.assertTrue(lines[3].startswith("2026-10-02 苏州"), lines)
        for line in lines:
            self.assertIn("预报未开放，可查日期", line)

    def test_output_json_envelope_matches_rail_style_with_forecasts_array(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            output = Path(temporary) / "weather.json"
            result = run_weather(
                "--fixture", str(AMAP_FIXTURES / "weather.json"),
                "--fixed-clock", "2026-09-04T00:00:00+08:00",
                "--city", "示例市",
                "--output-json", str(output),
            )
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn("WEATHER_COMPLETE", result.stdout)
            data = load(output)
        expected_keys = {
            "provider", "provider_version", "queried_at", "transport_legs",
            "claims", "health", "warnings", "error_class", "forecasts",
        }
        self.assertEqual(expected_keys, set(data.keys()))
        self.assertEqual("amap", data["provider"])
        self.assertIsNone(data["error_class"])
        self.assertEqual(4, len(data["forecasts"]))
        for entry in data["forecasts"]:
            self.assertEqual(
                {"date", "city", "adcode", "query", "forecast", "advice", "status"}, set(entry.keys()),
            )
            self.assertEqual("forecast", entry["status"])
            self.assertEqual("990100", entry["adcode"])

    def test_output_json_forecast_rows_carry_the_query_display_name(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            output = Path(temporary) / "weather.json"
            result = run_weather(
                "--fixture", str(AMAP_FIXTURES / "weather.json"),
                "--fixed-clock", "2026-09-04T00:00:00+08:00",
                "--city", "示例市",
                "--output-json", str(output),
            )
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            data = load(output)
        self.assertEqual(4, len(data["forecasts"]))
        for entry in data["forecasts"]:
            self.assertEqual("示例市", entry["query"])

    def test_city_and_trip_targets_are_mutually_exclusive(self):
        result = run_weather("--city", "福州", "--trip", str(WEEKEND_TRIP))
        self.assertNotEqual(0, result.returncode)
        self.assertIn("not allowed with argument", result.stderr)

    def test_missing_credentials_reports_no_forecast_and_exits_two(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            home = Path(temporary) / "home"
            home.mkdir()
            result = run_weather(
                "--city", "福州",
                env={"PATH": "/usr/bin:/bin", "HOME": str(home)},
            )
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("无预报", result.stdout)
        self.assertIn("凭据缺失", result.stdout)


class WeatherRequestContractTests(unittest.TestCase):
    """Transport-layer coverage for the `weather` branch of amap_http._request_contract.

    Before this file, no test exercised this branch's request shape directly
    (it was only reached indirectly through a full adapter.query() call).
    """

    def test_request_contract_builds_weather_v3_request_for_adcode(self):
        endpoint, parameters, api = amap_http._request_contract(_weather_request({"adcode": "350100"}))
        self.assertEqual("https://restapi.amap.com/v3/weather/weatherInfo", endpoint)
        self.assertEqual({"city": "350100", "extensions": "all", "output": "JSON"}, parameters)
        self.assertEqual("weather-v3", api)

    def test_request_contract_builds_weather_v3_request_for_city_name(self):
        endpoint, parameters, api = amap_http._request_contract(_weather_request({"city": "福州"}))
        self.assertEqual("https://restapi.amap.com/v3/weather/weatherInfo", endpoint)
        self.assertEqual({"city": "福州", "extensions": "all", "output": "JSON"}, parameters)
        self.assertEqual("weather-v3", api)

    def test_request_contract_rejects_when_both_or_neither_adcode_and_city_given(self):
        with self.assertRaises(ContractMismatch):
            amap_http._request_contract(_weather_request({}))
        with self.assertRaises(ContractMismatch):
            amap_http._request_contract(_weather_request({"adcode": "350100", "city": "福州"}))


if __name__ == "__main__":
    unittest.main()
