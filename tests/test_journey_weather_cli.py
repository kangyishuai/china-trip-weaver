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

from china_trip_weaver.clock import FixedClock, isoformat_seconds
from china_trip_weaver.contracts import canonical_json
from china_trip_weaver.evidence import make_claim
from china_trip_weaver.weather import advice_for

CTW = PLUGIN / "scripts" / "ctw"
JOURNEY_DEMO = ROOT / "demo" / "journey-16d"
FIXED_NOW = "2026-09-22T09:00:00+08:00"
SOURCE_URL = "https://restapi.amap.com/v3/weather/weatherInfo"
CLOCK = FixedClock.from_iso(FIXED_NOW)


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.write_text(canonical_json(value), encoding="utf-8")


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


def weather_claim(subject_ref, value):
    return make_claim(
        subject_ref=subject_ref, field_path="/weather", value=value, source_url=SOURCE_URL,
        provider="amap", status="verified", confidence=0.7, mode="live", clock=CLOCK,
        json_path="/forecasts/0/casts/0",
    )


def forecast_row(query, forecast_date, city, adcode, value):
    claim = weather_claim("weather-%s" % adcode, value)
    row = {
        "date": forecast_date, "city": city, "adcode": adcode, "forecast": value,
        "advice": advice_for(value), "status": "forecast", "query": query,
    }
    return row, claim


def out_of_window_row(query, forecast_date, city):
    return {
        "date": forecast_date, "city": city, "adcode": None, "forecast": None,
        "advice": [], "status": "out_of_window", "query": query, "note": "2026-09-29",
    }


def envelope(rows, claims):
    return {
        "provider": "amap", "provider_version": "weather-v3-test",
        "queried_at": isoformat_seconds(CLOCK), "forecasts": list(rows), "claims": list(claims),
    }


def run_journey_weather(*extra_args):
    return subprocess.run(
        [str(CTW), "journey", "weather", *extra_args],
        text=True, capture_output=True,
    )


class JourneyWeatherCommandTests(unittest.TestCase):
    """End-to-end subprocess coverage for `ctw journey weather` (`_cmd_journey_weather`, cli.py).

    Folds a synthetic `ctw weather --output-json`-shaped envelope into
    demo/journey-16d, whose first Trip covers 2026-10-01..05 in 上海.
    """

    def _two_day_result(self):
        row1, claim1 = forecast_row(
            "上海", "2026-10-01", "上海", "310000",
            forecast_value("2026-10-01", "上海", "310000", reported_at=FIXED_NOW),
        )
        row2, claim2 = forecast_row(
            "上海", "2026-10-02", "上海", "310000",
            forecast_value("2026-10-02", "上海", "310000", reported_at=FIXED_NOW, temp_high_c=30),
        )
        return envelope([row1, row2], [claim1, claim2])

    def test_fold_into_demo_journey_produces_valid_journey_and_html(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            output = Path(temporary)
            weather_result_path = output / "weather-result.json"
            write_json(weather_result_path, self._two_day_result())
            journey_out = output / "journey.json"

            result = run_journey_weather(
                "--journey", str(JOURNEY_DEMO / "journey.json"),
                "--weather-result", str(weather_result_path),
                "--base-revision", "1",
                "--fixed-clock", FIXED_NOW,
                "--output-json", str(journey_out),
            )
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn("JOURNEY_WEATHER_COMPLETE", result.stdout)
            updated = load(journey_out)
            self.assertEqual(2, updated["revision"]["number"])
            self.assertEqual(1, updated["revision"]["parent_revision"])
            self.assertEqual("system", updated["revision"]["created_by"])

            validated = subprocess.run(
                [str(CTW), "journey", "validate", str(journey_out)],
                text=True, capture_output=True,
            )
            self.assertEqual(0, validated.returncode, validated.stdout + validated.stderr)

            rendered_html = output / "journey.html"
            rendered = subprocess.run(
                [str(CTW), "journey", "render", str(journey_out), "--output", str(rendered_html)],
                text=True, capture_output=True,
            )
            self.assertEqual(0, rendered.returncode, rendered.stdout + rendered.stderr)

            validated_html = subprocess.run(
                [str(CTW), "journey", "validate-html", str(rendered_html), str(journey_out)],
                text=True, capture_output=True,
            )
            self.assertEqual(0, validated_html.returncode, validated_html.stdout + validated_html.stderr)
            self.assertIn("errors=0", validated_html.stdout)

    def test_all_out_of_window_envelope_is_a_noop_and_writes_nothing(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            output = Path(temporary)
            weather_result_path = output / "weather-result.json"
            write_json(weather_result_path, envelope(
                [out_of_window_row("上海", "2026-10-01", "上海")], [],
            ))
            journey_out = output / "journey.json"

            result = run_journey_weather(
                "--journey", str(JOURNEY_DEMO / "journey.json"),
                "--weather-result", str(weather_result_path),
                "--base-revision", "1",
                "--output-json", str(journey_out),
            )
            self.assertEqual(2, result.returncode, result.stdout + result.stderr)
            self.assertIn("JOURNEY_WEATHER_NOOP", result.stdout)
            self.assertFalse(journey_out.exists())

    def test_wrong_base_revision_fails_with_revision_conflict(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            output = Path(temporary)
            weather_result_path = output / "weather-result.json"
            write_json(weather_result_path, self._two_day_result())
            journey_out = output / "journey.json"

            result = run_journey_weather(
                "--journey", str(JOURNEY_DEMO / "journey.json"),
                "--weather-result", str(weather_result_path),
                "--base-revision", "7",
                "--output-json", str(journey_out),
            )
            self.assertEqual(1, result.returncode, result.stdout + result.stderr)
            self.assertIn("revision_conflict", result.stderr)
            self.assertFalse(journey_out.exists())

    def test_claim_value_mismatch_fails_with_weather_fold_claim_missing(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            output = Path(temporary)
            row, claim = forecast_row(
                "上海", "2026-10-01", "上海", "310000",
                forecast_value("2026-10-01", "上海", "310000", reported_at=FIXED_NOW),
            )
            claim = dict(claim)
            claim["value"] = dict(claim["value"])
            claim["value"]["temp_high_c"] = claim["value"]["temp_high_c"] + 1
            weather_result_path = output / "weather-result.json"
            write_json(weather_result_path, envelope([row], [claim]))
            journey_out = output / "journey.json"

            result = run_journey_weather(
                "--journey", str(JOURNEY_DEMO / "journey.json"),
                "--weather-result", str(weather_result_path),
                "--base-revision", "1",
                "--output-json", str(journey_out),
            )
            self.assertEqual(1, result.returncode, result.stdout + result.stderr)
            self.assertIn("weather_fold_claim_missing", result.stderr)
            self.assertFalse(journey_out.exists())


if __name__ == "__main__":
    unittest.main()
