"""Lodging must clear the same POI-identity check as a POI before geocoding.

Geocoding a bare "city+name" string does not recognize a hotel brand name;
AMap silently returns the city center or the wrong branch. These tests pin
the lodging path to the POI path: search first, confirm identity, then
geocode by the confirmed formatted address -- never a bare guess.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "plugins" / "china-trip-weaver" / "src"
sys.path.insert(0, str(SRC))

from china_trip_weaver.clock import FixedClock
from china_trip_weaver.mobility import MobilityBackend
from china_trip_weaver.providers.base import ProviderEnvelope
from tests.test_amap_live import FIXED_NOW, credentials, lodging_geocode_candidates
from tests.test_providers import AMapScenarioTransport


class RecordingLodgingTransport:
    """Answers one POI candidate then one geocode candidate, recording requests."""

    def __init__(self, poi_item, geocode_item):
        self.calls = 0
        self.capabilities = []
        self.requests = []
        self._poi_item = poi_item
        self._geocode_item = geocode_item

    def execute(self, provider, provider_request):
        if provider != "amap":
            raise AssertionError(provider)
        self.calls += 1
        self.capabilities.append(provider_request.capability)
        self.requests.append(provider_request)
        if provider_request.capability == "poi":
            return ProviderEnvelope(200, {
                "status": "1",
                "info": "OK",
                "infocode": "10000",
                "api": "poi-v5",
                "page_num": provider_request.parameters["page_num"],
                "page_size": provider_request.parameters["page_size"],
                "count": "1",
                "pois": [self._poi_item],
            }, {})
        if provider_request.capability == "geocode":
            return ProviderEnvelope(200, {
                "status": "1",
                "info": "OK",
                "infocode": "10000",
                "api": "geocode-v3",
                "count": "1",
                "geocodes": [self._geocode_item],
            }, {})
        if provider_request.capability == "route":
            return ProviderEnvelope(200, {
                "api": "route-transit-v3",
                "status": "1",
                "info": "OK",
                "route": {"transits": [{"duration": "1000", "distance": "2000"}]},
            }, {})
        raise AssertionError(provider_request.capability)


def _ambiguous_lodging_scenario():
    """Same-brand, near-named, 800 m apart -- mirrors the POI cluster fixture
    in test_amap_live.py's ``_synthetic_ambiguous_cluster(800)``, retargeted
    at a lodging entity so the two paths are judged by one shared standard."""

    candidates = lodging_geocode_candidates()
    lodging = candidates["lodgings"][0]
    lodging["name"] = "合成星庭入口"
    lodging["city"] = "合成星港"
    ref_id = lodging["lodging_id"]
    second_lng = 0.1 + 800.0 / 111_195.0
    scenario = {"entities": [{
        "ref_id": ref_id,
        "name": "合成星庭入口",
        "city": "合成星港",
        "poi_results": [
            {
                "id": "SYNTHETIC-LODGING-CLUSTER-A",
                "name": "合成星庭东入口",
                "pname": "合成省",
                "cityname": "合成星港市",
                "adname": "合成中心区",
                "address": "合成路一号",
                "adcode": "990300",
                "type": "住宿服务;宾馆酒店;快捷酒店",
                "business": {"opentime_today": "00:00-24:00"},
                "location": "0.100000000,0.100000000",
            },
            {
                "id": "SYNTHETIC-LODGING-CLUSTER-B",
                "name": "合成星庭西入口",
                "pname": "合成省",
                "cityname": "合成星港市",
                "adname": "合成中心区",
                "address": "合成路二号",
                "adcode": "990300",
                "type": "住宿服务;宾馆酒店;快捷酒店",
                "business": {"opentime_today": "00:00-24:00"},
                "location": "%.9f,0.100000000" % second_lng,
            },
        ],
        "geocode": {
            "formatted_address": "合成省合成星港市合成中心区合成路一号",
            "province": "合成省",
            "city": "合成星港市",
            "district": "合成中心区",
            "adcode": "990300",
            "location": "0.100000000,0.100000000",
        },
    }]}
    return ref_id, candidates, scenario


class LodgingIdentityTests(unittest.TestCase):
    """Task 0 pin: lodging must run the same POI-identity gate a POI does."""

    def setUp(self):
        self.clock = FixedClock.from_iso(FIXED_NOW)

    def test_ambiguous_same_brand_branches_block_lodging_before_geocode(self):
        ref_id, candidates, scenario = _ambiguous_lodging_scenario()
        transport = AMapScenarioTransport(scenario)

        result = MobilityBackend("live", credentials(), transport).resolve(
            candidates, self.clock, ("walking",),
        )

        self.assertNotIn(ref_id, {item.ref_id for item in result.locations})
        self.assertTrue(any(
            warning.startswith("identity_conflict:%s:ambiguous_name_margin:" % ref_id)
            for warning in result.warnings
        ), result.warnings)
        self.assertEqual(["poi"], transport.capabilities)
        self.assertEqual(0, sum(1 for item in transport.capabilities if item == "geocode"))

    def test_unique_lodging_identity_geocodes_by_its_formatted_address(self):
        candidates = lodging_geocode_candidates()
        ref_id = candidates["lodgings"][0]["lodging_id"]
        poi_item = {
            "id": "SYNTHETIC-LODGING-UNIQUE",
            "name": "如家酒店南京东路步行街店",
            "pname": "上海市",
            "cityname": "上海市",
            "adname": "黄浦区",
            "address": "南京东路999号",
            "adcode": "310101",
            "type": "住宿服务;宾馆酒店;快捷酒店",
            "business": {"opentime_today": "00:00-24:00"},
            "location": "121.480000,31.240000",
        }
        geocode_item = {
            "formatted_address": "上海市黄浦区南京东路999号如家酒店",
            "city": "上海市",
            "location": "121.480500,31.240500",
        }
        transport = RecordingLodgingTransport(poi_item, geocode_item)

        result = MobilityBackend("live", credentials(), transport).resolve(
            candidates, self.clock, ("walking",),
        )

        self.assertEqual(["poi", "geocode"], transport.capabilities[:2])
        self.assertIn(ref_id, {item.ref_id for item in result.locations})
        geocode_requests = [
            item for item in transport.requests if item.capability == "geocode"
        ]
        self.assertEqual(1, len(geocode_requests))
        self.assertEqual(
            "上海市黄浦区南京东路999号",
            geocode_requests[0].parameters["address"],
        )


if __name__ == "__main__":
    unittest.main()
