from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "plugins" / "china-trip-weaver" / "src"
sys.path.insert(0, str(SRC))

from china_trip_weaver.clock import FixedClock
from china_trip_weaver.credentials import resolve_credentials
from china_trip_weaver.locate import locate_trips, unlocated_entities
from china_trip_weaver.mobility import MobilityBackend
from tests.test_amap_live import ScriptedAmapTransport


JOURNEY_DEMO = ROOT / "demo" / "journey-16d" / "journey.json"
CLOCK = FixedClock.from_iso("2026-09-18T12:00:00+08:00")
_FULL_COORDINATES = {
    "source_crs": "GCJ02",
    "native": {"lng": 121.0, "lat": 31.0},
    "wgs84": {"lng": 120.994, "lat": 30.991},
    "gcj02": {"lng": 121.0, "lat": 31.0},
    "conversion": {
        "status": "not-needed", "method": "identity", "version": "1",
        "derived_fields": [], "converted_at": None, "accuracy_m": None,
    },
}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def credentials(configured=True):
    environment = {"AMAP_WEBSERVICE_KEY": "ctw-canary-amap-live-not-real"} if configured else {}
    return resolve_credentials(environment, ROOT / ".tmp" / "locate-no-credentials")


class CapabilityRecordingTransport(ScriptedAmapTransport):
    """Records every capability queried so a test can assert zero `route` calls."""

    def __init__(self, forbidden=False):
        super().__init__(forbidden=forbidden)
        self.capabilities = []

    def execute(self, provider, provider_request):
        self.capabilities.append(provider_request.capability)
        return super().execute(provider, provider_request)


class LocateMethodAndModuleTests(unittest.TestCase):
    def test_demo_journey_locates_all_six_entities_with_three_calls_per_trip(self):
        journey = load(JOURNEY_DEMO)
        transport = CapabilityRecordingTransport()
        backend = MobilityBackend("live", credentials(), transport)

        envelope = locate_trips(journey["trips"], backend, CLOCK)

        self.assertEqual(6, len(envelope["entities"]))
        for row in envelope["entities"]:
            self.assertEqual("located", row["status"])
            self.assertIsNone(row["reason"])
            self.assertNotIn("poi-routine-meal-", row["ref_id"])
            point = row["coordinates"]
            self.assertIn("gcj02", point)
            self.assertIn("wgs84", point)
            self.assertIsInstance(point["gcj02"], dict)
            self.assertIsInstance(point["wgs84"], dict)
        referenced_claim_ids = {
            claim_id for row in envelope["entities"] for claim_id in row["claim_ids"]
        }
        envelope_claim_ids = {claim["claim_id"] for claim in envelope["claims"]}
        self.assertTrue(referenced_claim_ids)
        self.assertLessEqual(referenced_claim_ids, envelope_claim_ids)
        self.assertEqual(9, transport.calls)
        self.assertNotIn("route", transport.capabilities)

        for trip in journey["trips"]:
            per_trip_transport = CapabilityRecordingTransport()
            per_trip_backend = MobilityBackend("live", credentials(), per_trip_transport)
            locate_trips([trip], per_trip_backend, CLOCK)
            self.assertEqual(3, per_trip_transport.calls, trip["trip_id"])
            self.assertNotIn("route", per_trip_transport.capabilities)

    def test_trip_with_every_coordinate_already_known_makes_zero_calls(self):
        trip = copy.deepcopy(load(JOURNEY_DEMO)["trips"][0])
        for poi in trip["pois"]:
            poi["coordinates"] = copy.deepcopy(_FULL_COORDINATES)
        for lodging in trip["lodgings"]:
            lodging["coordinates"] = copy.deepcopy(_FULL_COORDINATES)
        self.assertEqual([], unlocated_entities(trip))

        transport = CapabilityRecordingTransport()
        backend = MobilityBackend("live", credentials(), transport)
        envelope = locate_trips([trip], backend, CLOCK)

        self.assertEqual([], envelope["entities"])
        self.assertEqual(0, transport.calls)

    def test_forbidden_transport_reports_every_entity_as_provider_error(self):
        trip = load(JOURNEY_DEMO)["trips"][0]
        transport = CapabilityRecordingTransport(forbidden=True)
        backend = MobilityBackend("live", credentials(), transport)

        envelope = locate_trips([trip], backend, CLOCK)

        self.assertEqual(2, len(envelope["entities"]))
        for row in envelope["entities"]:
            self.assertEqual("provider_error", row["status"])
            self.assertEqual("forbidden", row["reason"])
            self.assertIsNone(row["coordinates"])
            self.assertEqual([], row["claim_ids"])
        self.assertEqual([], envelope["claims"])

    def test_repeating_a_trip_reuses_the_cached_result_without_a_new_call(self):
        trip = load(JOURNEY_DEMO)["trips"][0]
        transport = CapabilityRecordingTransport()
        backend = MobilityBackend("live", credentials(), transport)

        envelope = locate_trips([trip, trip], backend, CLOCK)

        self.assertEqual(3, transport.calls)
        self.assertEqual(4, len(envelope["entities"]))
        for row in envelope["entities"]:
            self.assertEqual("located", row["status"])


if __name__ == "__main__":
    unittest.main()
