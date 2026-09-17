from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "plugins" / "china-trip-weaver" / "src"
sys.path.insert(0, str(SRC))

from china_trip_weaver.cli import _NDJSONProgress, _not_run_probe, _probe_amap
from china_trip_weaver.credentials import resolve_credentials
from china_trip_weaver.providers.amap_http import AMapHTTPTransport
from china_trip_weaver.providers.base import ProviderEnvelope


AMAP_FIXTURES = ROOT / "tests" / "fixtures" / "providers" / "amap"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def fixture_body(name: str):
    return load(AMAP_FIXTURES / name)["transport"]["body"]


def credentials(configured=True):
    environment = {"AMAP_WEBSERVICE_KEY": "ctw-canary-doctor-probe-not-real"} if configured else {}
    return resolve_credentials(environment, ROOT / ".tmp" / "doctor-probe-amap-no-file")


class ScriptedCapabilityTransport:
    """Replays a fixture body per AMap capability; a listed capability can instead raise."""

    def __init__(self, bodies, *, raise_for=None):
        self.bodies = bodies
        self.raise_for = raise_for or {}
        self.calls = []

    def execute(self, provider, request):
        if provider != "amap":
            raise AssertionError(provider)
        self.calls.append(request.capability)
        if request.capability in self.raise_for:
            raise self.raise_for[request.capability]
        return ProviderEnvelope(200, self.bodies[request.capability], {})


def probe_with_transport(transport):
    with mock.patch.object(AMapHTTPTransport, "execute", transport.execute):
        return _probe_amap(credentials(), ROOT, "configured", _NDJSONProgress(None))


class DoctorProbeAmapTests(unittest.TestCase):
    def test_all_three_capabilities_pass(self):
        transport = ScriptedCapabilityTransport({
            "poi": fixture_body("success.json"),
            "weather": fixture_body("weather.json"),
            "poi_around": fixture_body("around_stations.json"),
        })
        row = probe_with_transport(transport)
        self.assertEqual(["poi", "weather", "poi_around"], transport.calls)
        self.assertEqual(
            {"poi": "passed", "weather": "passed", "poi_around": "passed"}, row["capabilities"],
        )
        self.assertEqual("passed", row["business"])
        self.assertEqual("passed", row["contract"])
        self.assertEqual("passed", row["network"])
        self.assertEqual("configured", row["credential"])
        self.assertEqual(
            {"credential", "contract", "network", "business", "capabilities"}, set(row),
        )

    def test_empty_weather_degrades_business_others_stay_passed(self):
        transport = ScriptedCapabilityTransport({
            "poi": fixture_body("success.json"),
            "weather": fixture_body("weather_empty.json"),
            "poi_around": fixture_body("around_stations.json"),
        })
        row = probe_with_transport(transport)
        self.assertEqual("degraded", row["capabilities"]["weather"])
        self.assertEqual("passed", row["capabilities"]["poi"])
        self.assertEqual("passed", row["capabilities"]["poi_around"])
        self.assertEqual("degraded", row["business"])

    def test_poi_around_exception_is_isolated_and_does_not_crash_the_probe(self):
        transport = ScriptedCapabilityTransport(
            {"poi": fixture_body("success.json"), "weather": fixture_body("weather.json")},
            raise_for={"poi_around": RuntimeError("synthetic poi_around failure")},
        )
        row = probe_with_transport(transport)
        self.assertEqual("failed", row["capabilities"]["poi_around"])
        self.assertEqual("passed", row["capabilities"]["poi"])
        self.assertEqual("passed", row["capabilities"]["weather"])
        self.assertEqual("failed", row["business"])

    def test_missing_credentials_short_circuits_to_the_original_not_run_probe(self):
        row = _probe_amap(credentials(configured=False), ROOT, "missing", _NDJSONProgress(None))
        self.assertEqual(_not_run_probe("missing"), row)
        self.assertNotIn("capabilities", row)


if __name__ == "__main__":
    unittest.main()
