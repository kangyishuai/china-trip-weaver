from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
import urllib.parse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "plugins" / "china-trip-weaver" / "src"
sys.path.insert(0, str(SRC))

from china_trip_weaver.clock import FixedClock
from china_trip_weaver.contracts import ProviderRequest
from china_trip_weaver.credentials import resolve_credentials
from china_trip_weaver.flyai_inventory import FlyAIBackend
from china_trip_weaver.geo import Point, coordinate_record
from china_trip_weaver.mobility import MobilityBackend, apply_locations, normalize_modes
from china_trip_weaver.planning import RailBackend, _combined_amap_health, plan_trip
from china_trip_weaver.providers.amap import AMapAdapter
from china_trip_weaver.providers.amap_http import (
    AMapCallBudget,
    AMapHTTPTransport,
    AMapRequestMemo,
)
from china_trip_weaver.providers.base import (
    ProviderContext,
    ProviderEnvelope,
    ProviderRateLimited,
    ProviderTimeout,
)
from china_trip_weaver.providers.flyai_cli import FlyAISubprocessTransport
from tests.test_providers import AMAP_SCENARIOS, AMapScenarioTransport, amap_scenario_candidates


FIXED_NOW = "2026-09-03T12:00:00+08:00"
E2E = ROOT / "tests" / "fixtures" / "e2e" / "beijing-shanghai-3d"
FLYAI_SERVER = ROOT / "tests" / "fixtures" / "flyai_cli_server.py"
POI_IDENTITY_DECISIONS = (
    ROOT / "tests" / "fixtures" / "poi-identity-decision" / "dead-corners.json"
)


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def lodging_geocode_candidates():
    source = load(E2E / "candidates.json")
    poi = copy.deepcopy(source["pois"][0])
    poi["coordinates"] = coordinate_record(
        "GCJ02", Point(121.0, 31.0), FixedClock.from_iso(FIXED_NOW), accuracy_m=50,
    )
    lodging = copy.deepcopy(source["lodgings"][0])
    entity_refs = {poi["poi_id"], lodging["lodging_id"]}
    return {
        "candidates_version": source["candidates_version"],
        "pois": [poi],
        "lodgings": [lodging],
        "claims": [
            copy.deepcopy(claim) for claim in source["claims"]
            if claim["subject_ref"] in entity_refs
        ],
        "unknowns": [
            copy.deepcopy(item) for item in source["unknowns"]
            if item["field_path"].startswith("/lodgings/")
        ],
    }


def credentials(configured=True):
    environment = {"AMAP_WEBSERVICE_KEY": "ctw-canary-amap-live-not-real"} if configured else {}
    return resolve_credentials(environment, ROOT / ".tmp" / "amap-live-no-file")


def request(capability, parameters):
    return ProviderRequest(
        request_id="amap-live-test",
        capability=capability,
        parameters=parameters,
        deadline_ms=1000,
        as_of="2026-09-03",
        cache_policy="bypass",
        trace={"stage": "test"},
    )


class FakeResponse:
    def __init__(self, body, url, status=200):
        self._body = json.dumps(body).encode("utf-8")
        self._url = url
        self.status = status
        self.headers = {"Content-Type": "application/json"}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        del exc_type, exc, traceback

    def read(self, amount):
        return self._body[:amount]

    def geturl(self):
        return self._url

    def getcode(self):
        return self.status


class RecordingOpener:
    def __init__(self):
        self.requests = []

    def __call__(self, http_request, timeout):
        self.requests.append((http_request, timeout))
        return FakeResponse({"status": "1", "info": "OK"}, http_request.full_url)


class ScriptedAmapTransport:
    def __init__(self, forbidden=False):
        self.calls = 0
        self.forbidden = forbidden
        self._coordinates = {}

    def execute(self, provider, provider_request):
        if provider != "amap":
            raise AssertionError(provider)
        self.calls += 1
        capability = provider_request.capability
        if self.forbidden:
            api = {
                "poi": "poi-v5",
                "geocode": "geocode-v3",
                "route": "route-transit-v3",
            }[capability]
            return ProviderEnvelope(200, {"status": "0", "info": "INVALID_USER_KEY", "api": api}, {})
        if capability == "poi":
            ref_id = provider_request.parameters["subject_ref"]
            if ref_id not in self._coordinates:
                index = len(self._coordinates)
                self._coordinates[ref_id] = (121.0 + index * 0.1, 31.0 + index * 0.1)
            lng, lat = self._coordinates[ref_id]
            city = provider_request.parameters["city"]
            cityname = city if city.endswith("市") else city + "市"
            return ProviderEnvelope(200, {
                "status": "1",
                "info": "OK",
                "api": "poi-v5",
                "page_num": provider_request.parameters["page_num"],
                "page_size": provider_request.parameters["page_size"],
                "pois": [{
                    "id": "SYNTHETIC-" + ref_id,
                    "name": provider_request.parameters["keywords"],
                    "pname": cityname,
                    "cityname": cityname,
                    "adname": "示例区",
                    "address": "示例大道100号",
                    "adcode": "310000",
                    "type": "风景名胜;风景名胜相关;旅游景点",
                    "business": {"opentime_today": "09:00-17:00"},
                    "location": "%.7f,%.7f" % (lng, lat),
                }],
            }, {})
        if capability == "geocode":
            ref_id = provider_request.parameters["subject_ref"]
            if ref_id not in self._coordinates:
                index = len(self._coordinates)
                self._coordinates[ref_id] = (121.0 + index * 0.1, 31.0 + index * 0.1)
            lng, lat = self._coordinates[ref_id]
            return ProviderEnvelope(200, {
                "status": "1",
                "info": "OK",
                "api": "geocode-v3",
                "geocodes": [{
                    "formatted_address": provider_request.parameters["address"],
                    "city": provider_request.parameters["city"],
                    "location": "%.7f,%.7f" % (lng, lat),
                }],
            }, {})
        if capability == "route":
            mode = provider_request.parameters["travel_mode"]
            api = {
                "walk": "route-walking-v3",
                "transit": "route-transit-v3",
                "drive": "route-driving-v3",
                "ride": "route-riding-v4",
            }[mode]
            path = {"duration": "1000", "distance": "2000"}
            if mode == "ride":
                body = {"api": api, "errcode": 0, "errmsg": "OK", "data": {"paths": [path]}}
            else:
                key = "transits" if mode == "transit" else "paths"
                body = {"api": api, "status": "1", "info": "OK", "route": {key: [path]}}
            return ProviderEnvelope(200, body, {})
        raise AssertionError(capability)


class AMapHTTPTransportTests(unittest.TestCase):
    def test_v3_v4_v5_endpoints_and_pagination_names(self):
        opener = RecordingOpener()
        budget = AMapCallBudget(max_calls=20, qps=1000000)
        transport = AMapHTTPTransport(credentials(), budget=budget, opener=opener)
        cases = (
            ("geocode", {"address": "人民大道201号", "city": "上海"}, "/v3/geocode/geo", "geocode-v3"),
            ("poi", {"keywords": "博物馆", "city": "上海", "page_size": 15, "page_num": 2}, "/v5/place/text", "poi-v5"),
            ("route", {"origin": "121.47,31.23", "destination": "121.49,31.24", "travel_mode": "walk", "city": "上海", "destination_city": "上海"}, "/v3/direction/walking", "route-walking-v3"),
            ("route", {"origin": "121.47,31.23", "destination": "121.49,31.24", "travel_mode": "transit", "city": "上海", "destination_city": "上海"}, "/v3/direction/transit/integrated", "route-transit-v3"),
            ("route", {"origin": "121.47,31.23", "destination": "121.49,31.24", "travel_mode": "drive", "city": "上海", "destination_city": "上海"}, "/v3/direction/driving", "route-driving-v3"),
            ("route", {"origin": "121.47,31.23", "destination": "121.49,31.24", "travel_mode": "ride", "city": "上海", "destination_city": "上海"}, "/v4/direction/bicycling", "route-riding-v4"),
        )
        for capability, parameters, expected_path, expected_api in cases:
            with self.subTest(expected_path=expected_path):
                envelope = transport.execute("amap", request(capability, parameters))
                http_request, timeout = opener.requests[-1]
                parsed = urllib.parse.urlsplit(http_request.full_url)
                query = urllib.parse.parse_qs(parsed.query)
                self.assertEqual(expected_path, parsed.path)
                self.assertEqual(expected_api, envelope.body["api"])
                self.assertEqual(1.0, timeout)
                self.assertIn("key", query)
                self.assertNotIn("key=", envelope.raw_ref)
                if capability == "poi":
                    self.assertEqual(["15"], query["page_size"])
                    self.assertEqual(["2"], query["page_num"])
                    self.assertEqual(["true"], query["city_limit"])
                    self.assertEqual(["business"], query["show_fields"])
                    self.assertNotIn("offset", query)
                    self.assertNotIn("page", query)

    def test_budget_spaces_starts_and_caps_calls(self):
        now = [0.0]
        sleeps = []

        def monotonic():
            return now[0]

        def sleep(seconds):
            sleeps.append(seconds)
            now[0] += seconds

        budget = AMapCallBudget(max_calls=3, qps=2, monotonic=monotonic, sleep=sleep)
        budget.acquire()
        budget.acquire()
        budget.acquire()
        self.assertEqual(3, budget.calls)
        self.assertEqual([0.5, 0.5], sleeps)
        with self.assertRaises(ProviderRateLimited):
            budget.acquire()

    def test_zero_call_budget_is_an_immediate_truthful_rate_limit(self):
        budget = AMapCallBudget(max_calls=0, qps=1000000)
        with self.assertRaisesRegex(ProviderRateLimited, "budget exhausted"):
            budget.acquire()
        self.assertEqual(0, budget.calls)

    def test_forked_budgets_have_independent_counts_and_one_qps_gate(self):
        now = [0.0]
        sleeps = []

        def monotonic():
            return now[0]

        def sleep(seconds):
            sleeps.append(seconds)
            now[0] += seconds

        template = AMapCallBudget(
            max_calls=80,
            qps=2,
            monotonic=monotonic,
            sleep=sleep,
        )
        first = template.fork(1)
        second = template.fork(1)
        first.acquire()
        second.acquire()
        self.assertEqual((1, 1, 0), (first.calls, second.calls, template.calls))
        self.assertEqual([0.5], sleeps)

    def test_request_memo_is_in_memory_and_explicitly_run_scoped(self):
        opener = RecordingOpener()
        provider_request = request("geocode", {
            "subject_ref": "poi-synthetic-memo",
            "address": "合成大道1号",
            "city": "合成甲城",
        })
        first_run = AMapHTTPTransport(
            credentials(),
            budget=AMapCallBudget(max_calls=2, qps=1000000),
            opener=opener,
            memo=AMapRequestMemo(),
        )
        self.assertEqual(
            first_run.execute("amap", provider_request),
            first_run.execute("amap", provider_request),
        )
        self.assertEqual(1, first_run.calls)
        self.assertEqual(1, len(opener.requests))

        second_run = AMapHTTPTransport(
            credentials(),
            budget=AMapCallBudget(max_calls=2, qps=1000000),
            opener=opener,
            memo=AMapRequestMemo(),
        )
        second_run.execute("amap", provider_request)
        self.assertEqual(1, second_run.calls)
        self.assertEqual(2, len(opener.requests))

    def test_same_run_timeout_is_replayed_without_a_second_http_call(self):
        calls = []

        def timeout_opener(http_request, timeout):
            calls.append((http_request, timeout))
            raise TimeoutError("synthetic timeout")

        provider_request = request("geocode", {
            "subject_ref": "poi-synthetic-timeout",
            "address": "合成大道2号",
            "city": "合成甲城",
        })
        transport = AMapHTTPTransport(
            credentials(),
            budget=AMapCallBudget(max_calls=2, qps=1000000),
            opener=timeout_opener,
            memo=AMapRequestMemo(),
        )
        for _ in range(2):
            with self.assertRaisesRegex(ProviderTimeout, "deadline exceeded"):
                transport.execute("amap", provider_request)
        self.assertEqual(1, transport.calls)
        self.assertEqual(1, len(calls))

    def test_preflight_budget_exhaustion_does_not_poison_the_next_segment_memo(self):
        opener = RecordingOpener()
        memo = AMapRequestMemo()
        provider_request = request("geocode", {
            "subject_ref": "poi-synthetic-next-segment",
            "address": "合成大道3号",
            "city": "合成乙城",
        })
        exhausted = AMapHTTPTransport(
            credentials(),
            budget=AMapCallBudget(max_calls=0, qps=1000000),
            opener=opener,
            memo=memo,
        )
        with self.assertRaises(ProviderRateLimited):
            exhausted.execute("amap", provider_request)
        available = AMapHTTPTransport(
            credentials(),
            budget=AMapCallBudget(max_calls=1, qps=1000000),
            opener=opener,
            memo=memo,
        )
        available.execute("amap", provider_request)
        self.assertEqual((0, 1), (exhausted.calls, available.calls))
        self.assertEqual(1, len(opener.requests))

    def test_run_memo_does_not_reuse_time_sensitive_route_queries(self):
        opener = RecordingOpener()
        transport = AMapHTTPTransport(
            credentials(),
            budget=AMapCallBudget(max_calls=2, qps=1000000),
            opener=opener,
            memo=AMapRequestMemo(),
        )
        provider_request = request("route", {
            "from_ref": "poi-route-a",
            "to_ref": "poi-route-b",
            "origin": "121.1000000,31.1000000",
            "destination": "121.2000000,31.2000000",
            "city": "合成甲城",
            "destination_city": "合成甲城",
            "travel_mode": "transit",
        })
        transport.execute("amap", provider_request)
        transport.execute("amap", provider_request)
        self.assertEqual(2, transport.calls)
        self.assertEqual(2, len(opener.requests))


class AMapMobilityTests(unittest.TestCase):
    def setUp(self):
        self.clock = FixedClock.from_iso(FIXED_NOW)
        self.candidates = load(ROOT / "demo" / "candidates.json")

    def _resolve_poi_identity_case(self, case_name):
        fixture = load(POI_IDENTITY_DECISIONS)
        selected = next(item for item in fixture["cases"] if item["case"] == case_name)
        scenario = {"entities": [copy.deepcopy(selected["entity"])]}
        candidates = amap_scenario_candidates(scenario)
        transport = AMapScenarioTransport(scenario)
        result = MobilityBackend("live", credentials(), transport).resolve(
            candidates, self.clock, ("walking",),
        )
        pois, _ = apply_locations(candidates["pois"], (), result)
        return pois[0], result, transport

    def _resolve_poi_admin_case(self, case_name, expected_city, provider_city, district):
        ref_id = "poi-admin-" + case_name
        name = "合成云岬观测点"
        scenario = {"entities": [{
            "ref_id": ref_id,
            "name": name,
            "city": expected_city,
            "poi_results": [{
                "id": "SYNTHETIC-ADMIN-" + case_name.upper(),
                "name": name,
                "pname": "合成省",
                "cityname": provider_city,
                "adname": district,
                "address": "合成大道100号",
                "adcode": "990100",
                "type": "合成测试地点",
                "business": {"opentime_today": "09:00-17:00"},
                "location": "0.120000,0.230000",
            }],
            "geocode": {
                "formatted_address": "合成省合成大道100号",
                "province": "合成省",
                "city": expected_city + "市",
                "district": district or "合成校验区",
                "adcode": "990100",
                "location": "0.120000,0.230000",
            },
        }]}
        candidates = amap_scenario_candidates(scenario)
        transport = AMapScenarioTransport(scenario)
        result = MobilityBackend("live", credentials(), transport).resolve(
            candidates, self.clock, ("walking",),
        )
        pois, _ = apply_locations(candidates["pois"], (), result)
        return ref_id, pois[0], result, transport

    def test_poi_admin_district_exact_match_resolves_coordinates(self):
        _, poi, result, transport = self._resolve_poi_admin_case(
            "district-hit", "合成星河", "合成远洋市", "合成星河县",
        )

        self.assertEqual(["poi", "geocode"], transport.capabilities)
        self.assertEqual(1, len(result.locations))
        self.assertIsNotNone(poi["coordinates"])
        self.assertFalse(any("poi_admin_mismatch" in item for item in result.warnings))

    def test_poi_admin_city_exact_match_resolves_coordinates(self):
        _, poi, result, transport = self._resolve_poi_admin_case(
            "city-hit", "合成月湾", "合成月湾市", "合成远洋区",
        )

        self.assertEqual(["poi", "geocode"], transport.capabilities)
        self.assertEqual(1, len(result.locations))
        self.assertIsNotNone(poi["coordinates"])
        self.assertFalse(any("poi_admin_mismatch" in item for item in result.warnings))

    def test_poi_admin_city_and_district_non_matches_remain_conflicts(self):
        ref_id, poi, result, transport = self._resolve_poi_admin_case(
            "neither-hit", "合成海", "合成海湾市", "合成海岛县",
        )

        self.assertEqual(["poi"], transport.capabilities)
        self.assertEqual((), result.locations)
        self.assertIsNone(poi["coordinates"])
        self.assertTrue(any(
            item.startswith("identity_conflict:%s:poi_admin_mismatch:" % ref_id)
            for item in result.warnings
        ), result.warnings)

    def test_poi_admin_empty_district_preserves_city_only_conflict(self):
        ref_id, poi, result, transport = self._resolve_poi_admin_case(
            "empty-district", "合成林野", "合成远山市", "",
        )

        self.assertEqual(["poi"], transport.capabilities)
        self.assertEqual((), result.locations)
        self.assertIsNone(poi["coordinates"])
        self.assertTrue(any(
            item.startswith("identity_conflict:%s:poi_admin_mismatch:" % ref_id)
            for item in result.warnings
        ), result.warnings)

    def _resolve_geocode_admin_case(
        self, case_name, expected_city, provider_city, district=None,
    ):
        ref_id = "poi-geocode-admin-" + case_name
        name = "合成星港观测点"
        geocode = {
            "formatted_address": "合成省合成星港区合成大道200号",
            "province": "合成省",
            "city": provider_city,
            "adcode": "990200",
            "location": "0.340000,0.450000",
        }
        if district is not None:
            geocode["district"] = district
        scenario = {"entities": [{
            "ref_id": ref_id,
            "name": name,
            "city": expected_city,
            "poi_results": [{
                "id": "SYNTHETIC-GEOCODE-ADMIN-" + case_name.upper(),
                "name": name,
                "pname": "合成省",
                "cityname": expected_city + "市",
                "adname": "合成星港区",
                "address": "合成大道200号",
                "adcode": "990200",
                "type": "合成测试地点",
                "business": {"opentime_today": "09:00-17:00"},
                "location": "0.340000,0.450000",
            }],
            "geocode": geocode,
        }]}
        candidates = amap_scenario_candidates(scenario)
        transport = AMapScenarioTransport(scenario)
        result = MobilityBackend("live", credentials(), transport).resolve(
            candidates, self.clock, ("walking",),
        )
        pois, _ = apply_locations(candidates["pois"], (), result)
        return ref_id, pois[0], result, transport

    def test_geocode_admin_district_exact_match_resolves_coordinates(self):
        _, poi, result, transport = self._resolve_geocode_admin_case(
            "district-hit", "合成星河", "合成远洋市", "合成星河县",
        )

        self.assertEqual(["poi", "geocode"], transport.capabilities)
        self.assertEqual(1, len(result.locations))
        self.assertIsNotNone(poi["coordinates"])
        self.assertFalse(any("geocode_admin_mismatch" in item for item in result.warnings))

    def test_geocode_admin_city_exact_match_resolves_coordinates(self):
        _, poi, result, transport = self._resolve_geocode_admin_case(
            "city-hit", "合成月湾", "合成月湾市", "合成远洋区",
        )

        self.assertEqual(["poi", "geocode"], transport.capabilities)
        self.assertEqual(1, len(result.locations))
        self.assertIsNotNone(poi["coordinates"])
        self.assertFalse(any("geocode_admin_mismatch" in item for item in result.warnings))

    def test_geocode_admin_city_and_district_non_matches_remain_conflicts(self):
        ref_id, poi, result, transport = self._resolve_geocode_admin_case(
            "neither-hit", "合成海", "合成海湾市", "合成海岛县",
        )

        self.assertEqual(["poi", "geocode"], transport.capabilities)
        self.assertEqual((), result.locations)
        self.assertIsNone(poi["coordinates"])
        self.assertTrue(any(
            item.startswith("identity_conflict:%s:geocode_admin_mismatch:" % ref_id)
            for item in result.warnings
        ), result.warnings)

    def test_geocode_admin_missing_or_empty_district_preserves_city_only_conflict(self):
        for suffix, district in (("missing", None), ("empty-text", ""), ("empty-list", [])):
            with self.subTest(district=suffix):
                ref_id, poi, result, transport = self._resolve_geocode_admin_case(
                    suffix, "合成林野", "合成远山市", district,
                )

                self.assertEqual(["poi", "geocode"], transport.capabilities)
                self.assertEqual((), result.locations)
                self.assertIsNone(poi["coordinates"])
                self.assertTrue(any(
                    item.startswith("identity_conflict:%s:geocode_admin_mismatch:" % ref_id)
                    for item in result.warnings
                ), result.warnings)

    def test_poi_identity_decision_fixture_is_synthetic_and_complete(self):
        fixture = load(POI_IDENTITY_DECISIONS)
        self.assertIn("locally generated synthetic", fixture["source"])
        self.assertIn("no captured provider data", fixture["source"])
        self.assertEqual({
            "duplicate_names",
            "exact_original_first",
            "prefix_relation",
            "different_places",
        }, {item["case"] for item in fixture["cases"]})
        for case in fixture["cases"]:
            entity = case["entity"]
            self.assertTrue(entity["city"].startswith("合成"))
            self.assertTrue(entity["name"].startswith("合成"))
            self.assertTrue(entity["ref_id"].startswith("poi-decision-"))
            for item in entity["poi_results"]:
                self.assertTrue(item["id"].startswith("SYNTHETIC-"))
                longitude, latitude = (float(value) for value in item["location"].split(","))
                self.assertLess(abs(longitude), 1.0)
                self.assertLess(abs(latitude), 1.0)

    def test_duplicate_candidate_names_resolve_coordinates(self):
        poi, result, transport = self._resolve_poi_identity_case("duplicate_names")

        self.assertEqual(["poi", "geocode"], transport.capabilities)
        self.assertEqual(1, len(result.locations))
        self.assertIsNotNone(poi["coordinates"])
        self.assertNotIn("identity_conflict", result.warnings)

    def test_exact_original_first_resolves_coordinates(self):
        poi, result, transport = self._resolve_poi_identity_case("exact_original_first")

        self.assertEqual(["poi", "geocode"], transport.capabilities)
        self.assertEqual(1, len(result.locations))
        self.assertIsNotNone(poi["coordinates"])
        self.assertNotIn("identity_conflict", result.warnings)

    def test_prefix_and_different_candidate_names_remain_unknown(self):
        for case_name in ("prefix_relation", "different_places"):
            with self.subTest(case=case_name):
                poi, result, transport = self._resolve_poi_identity_case(case_name)
                self.assertIsNone(poi["coordinates"])
                self.assertEqual((), result.locations)
                self.assertEqual(["poi"], transport.capabilities)
                self.assertIn("identity_conflict", result.warnings)
                self.assertTrue(any(
                    warning.startswith("identity_conflict:")
                    and ":ambiguous_name_margin:" in warning
                    for warning in result.warnings
                ))

    def test_geocode_preserves_gcj_native_and_derives_wgs84(self):
        transport = ScriptedAmapTransport()
        context = ProviderContext(self.clock, credentials(), transport)
        result = AMapAdapter().query(request("geocode", {
            "subject_ref": "poi-demo",
            "address": "上海博物馆",
            "city": "上海",
        }), context)
        self.assertIsNone(result.error_class)
        coordinates = result.claims[0]["value"]
        self.assertEqual("GCJ02", coordinates["source_crs"])
        self.assertEqual(coordinates["native"], coordinates["gcj02"])
        self.assertIsNotNone(coordinates["wgs84"])
        self.assertEqual(["wgs84"], coordinates["conversion"]["derived_fields"])

    def test_lodging_geocode_no_results_degrades_without_crashing(self):
        class EmptyGeocodeTransport:
            def __init__(self):
                self.calls = 0
                self.capabilities = []

            def execute(self, provider, provider_request):
                self.calls += 1
                self.capabilities.append(provider_request.capability)
                self.assert_request(provider, provider_request)
                return ProviderEnvelope(200, {
                    "status": "1",
                    "info": "OK",
                    "api": "geocode-v3",
                    "geocodes": [],
                }, {})

            @staticmethod
            def assert_request(provider, provider_request):
                if provider != "amap" or provider_request.capability != "geocode":
                    raise AssertionError("lodging probe must only call AMap geocode")

        transport = EmptyGeocodeTransport()
        result = MobilityBackend("live", credentials(), transport).resolve(
            lodging_geocode_candidates(), self.clock, ("walking",),
        )

        self.assertEqual(["geocode"], transport.capabilities)
        self.assertNotIn(
            "lodging-bjs-central", {item.ref_id for item in result.locations},
        )
        self.assertEqual("degraded", result.health["status"])
        self.assertIn("errors=no_results", result.health["reason"])
        self.assertTrue(any(
            item.startswith("no_results:lodging-bjs-central:geocode_lookup:")
            for item in result.warnings
        ), result.warnings)

    def test_lodging_geocode_multiple_results_remain_ambiguous(self):
        class AmbiguousGeocodeTransport:
            def __init__(self):
                self.calls = 0

            def execute(self, provider, provider_request):
                self.calls += 1
                if provider != "amap" or provider_request.capability != "geocode":
                    raise AssertionError("lodging probe must only call AMap geocode")
                return ProviderEnvelope(200, {
                    "status": "1",
                    "info": "OK",
                    "api": "geocode-v3",
                    "geocodes": [{
                        "location": "121.470000,31.230000",
                        "formatted_address": "上海市合成甲住宿",
                        "city": "上海市",
                    }, {
                        "location": "121.490000,31.250000",
                        "formatted_address": "上海市合成乙住宿",
                        "city": "上海市",
                    }],
                }, {})

        transport = AmbiguousGeocodeTransport()
        result = MobilityBackend("live", credentials(), transport).resolve(
            lodging_geocode_candidates(), self.clock, ("walking",),
        )

        self.assertEqual(1, transport.calls)
        self.assertNotIn(
            "lodging-bjs-central", {item.ref_id for item in result.locations},
        )
        self.assertEqual("degraded", result.health["status"])
        self.assertIn("errors=identity_conflict", result.health["reason"])
        self.assertTrue(any(
            item.startswith(
                "identity_conflict:lodging-bjs-central:geocode_ambiguous:"
            )
            for item in result.warnings
        ), result.warnings)

    def test_lodging_geocode_rate_limit_is_not_hidden(self):
        class RateLimitedGeocodeTransport:
            retry_rate_limits = False

            def __init__(self):
                self.calls = 0

            def execute(self, provider, provider_request):
                self.calls += 1
                if provider != "amap" or provider_request.capability != "geocode":
                    raise AssertionError("lodging probe must only call AMap geocode")
                return ProviderEnvelope(
                    429, {"error": "synthetic quota"}, {"Retry-After": "30"},
                )

        transport = RateLimitedGeocodeTransport()
        result = MobilityBackend("live", credentials(), transport).resolve(
            lodging_geocode_candidates(), self.clock, ("walking",),
        )

        self.assertEqual(1, transport.calls)
        self.assertNotIn(
            "lodging-bjs-central", {item.ref_id for item in result.locations},
        )
        self.assertEqual("rate_limited", result.health["status"])
        self.assertIn("errors=rate_limited", result.health["reason"])
        self.assertTrue(any(
            item.startswith("rate_limited:lodging-bjs-central:geocode_lookup:")
            for item in result.warnings
        ), result.warnings)

    def test_g3_ambiguous_poi_and_wrong_geocode_admin_leave_coordinates_unknown(self):
        scenario = load(AMAP_SCENARIOS / "g3_identity_conflict.json")
        candidates = amap_scenario_candidates(scenario)

        ambiguous_transport = AMapScenarioTransport(scenario)
        ambiguous = MobilityBackend("live", credentials(), ambiguous_transport).resolve(
            candidates, self.clock, ("walking",),
        )
        self.assertEqual(["poi"], ambiguous_transport.capabilities)
        self.assertIn("identity_conflict", ambiguous.warnings)
        self.assertEqual((), ambiguous.locations)
        ambiguous_pois, _ = apply_locations(candidates["pois"], (), ambiguous)
        self.assertIsNone(ambiguous_pois[0]["coordinates"])
        self.assertEqual({"conflict"}, {claim["status"] for claim in ambiguous.claims})
        self.assertEqual(
            len(ambiguous.claims), len({claim["claim_id"] for claim in ambiguous.claims}),
        )

        wrong_poi_admin_scenario = copy.deepcopy(scenario)
        wrong_poi_admin_scenario["entities"][0]["poi_results"] = [
            wrong_poi_admin_scenario["entities"][0]["poi_results"][0]
        ]
        wrong_poi_admin_scenario["entities"][0]["poi_results"][0].update({
            "pname": "北京市",
            "cityname": "北京市",
            "adname": "朝阳区",
            "adcode": "110000",
        })
        wrong_poi_admin_transport = AMapScenarioTransport(wrong_poi_admin_scenario)
        wrong_poi_admin = MobilityBackend("live", credentials(), wrong_poi_admin_transport).resolve(
            amap_scenario_candidates(wrong_poi_admin_scenario), self.clock, ("walking",),
        )
        self.assertEqual(["poi"], wrong_poi_admin_transport.capabilities)
        self.assertIn("identity_conflict", wrong_poi_admin.warnings)
        self.assertEqual((), wrong_poi_admin.locations)

        wrong_admin_scenario = copy.deepcopy(scenario)
        wrong_admin_scenario["entities"][0]["poi_results"] = [
            wrong_admin_scenario["entities"][0]["poi_results"][0]
        ]
        wrong_admin_candidates = amap_scenario_candidates(wrong_admin_scenario)
        wrong_admin_transport = AMapScenarioTransport(wrong_admin_scenario)
        wrong_admin = MobilityBackend("live", credentials(), wrong_admin_transport).resolve(
            wrong_admin_candidates, self.clock, ("walking",),
        )
        self.assertEqual(["poi", "geocode"], wrong_admin_transport.capabilities)
        self.assertIn("identity_conflict", wrong_admin.warnings)
        self.assertEqual((), wrong_admin.locations)
        wrong_pois, _ = apply_locations(wrong_admin_candidates["pois"], (), wrong_admin)
        self.assertIsNone(wrong_pois[0]["coordinates"])
        self.assertNotIn("verified", {claim["status"] for claim in wrong_admin.claims})
        geocode_warning = next(
            item for item in wrong_admin.warnings
            if item.startswith("identity_conflict:poi-g3-corridor:geocode_admin_mismatch:")
        )
        geocode_feedback = json.loads(geocode_warning.split(":", 3)[3])
        self.assertEqual("北京市", geocode_feedback["actual_administrative_area"])
        self.assertEqual([{
            "administrative_area": "珠海市/香洲区",
            "name": "海岛生态廊道甲区",
        }], geocode_feedback["candidates"])

        provider_answer_scenario = copy.deepcopy(wrong_admin_scenario)
        provider_answer_scenario["entities"][0]["geocode"].update({
            "formatted_address": "广东省珠海市香洲区海滨路100号",
            "province": "广东省",
            "city": "珠海市",
            "district": "香洲区",
            "adcode": "440400",
            "location": "113.570000,22.270000",
        })
        provider_answer_candidates = amap_scenario_candidates(provider_answer_scenario)
        provider_answer_transport = AMapScenarioTransport(provider_answer_scenario)
        provider_answer = MobilityBackend("live", credentials(), provider_answer_transport).resolve(
            provider_answer_candidates, self.clock, ("walking",),
        )
        self.assertEqual(1, len(provider_answer.locations))
        self.assertEqual("珠海市", provider_answer.locations[0].city)
        self.assertEqual("海岛生态廊道甲区", provider_answer.locations[0].name)

    def test_identity_conflict_feedback_limits_and_sanitizes_provider_candidates(self):
        scenario = load(AMAP_SCENARIOS / "g3_identity_conflict.json")
        first = scenario["entities"][0]["poi_results"][0]
        third = copy.deepcopy(first)
        third.update({
            "id": "SYNTHETIC-G3-C",
            "name": "海岛生态廊道丙区 <b>展示</b> authorization: Bearer synthetic-hidden",
            "address": "海滨路104号",
            "location": "113.590000,22.290000",
        })
        fourth = copy.deepcopy(first)
        fourth.update({
            "id": "SYNTHETIC-G3-D",
            "name": "海岛生态廊道丁区",
            "address": "海滨路106号",
            "location": "113.600000,22.300000",
        })
        scenario["entities"][0]["poi_results"].extend((third, fourth))
        candidates = amap_scenario_candidates(scenario)
        result = MobilityBackend(
            "live", credentials(), AMapScenarioTransport(scenario),
        ).resolve(candidates, self.clock, ("walking",))

        warning = next(
            item for item in result.warnings
            if item.startswith("identity_conflict:poi-g3-corridor:ambiguous_name_margin:")
        )
        feedback = json.loads(warning.split(":", 3)[3])
        self.assertEqual(3, len(feedback["candidates"]))
        self.assertEqual([
            "海岛生态廊道甲区",
            "海岛生态廊道乙区",
            "海岛生态廊道丙区 展示 [REDACTED]",
        ], feedback["suggested_names"])
        self.assertEqual(
            ["珠海市/香洲区"] * 3,
            [item["administrative_area"] for item in feedback["candidates"]],
        )
        self.assertNotIn("海岛生态廊道丁区", warning)
        self.assertNotIn("synthetic-hidden", warning)
        self.assertNotIn("海滨路", warning)
        self.assertNotIn("provider_poi_id", warning)
        pois, _ = apply_locations(candidates["pois"], (), result)
        self.assertEqual((), result.locations)
        self.assertIsNone(pois[0]["coordinates"])

    def test_poi_admin_mismatch_feedback_includes_actual_admin_and_keeps_unknown(self):
        scenario = load(AMAP_SCENARIOS / "g3_identity_conflict.json")
        scenario["entities"][0]["poi_results"] = [
            scenario["entities"][0]["poi_results"][0]
        ]
        scenario["entities"][0]["poi_results"][0].update({
            "pname": "北京市",
            "cityname": "北京市",
            "adname": "朝阳区",
            "adcode": "110000",
        })
        candidates = amap_scenario_candidates(scenario)
        result = MobilityBackend(
            "live", credentials(), AMapScenarioTransport(scenario),
        ).resolve(candidates, self.clock, ("walking",))

        warning = next(
            item for item in result.warnings
            if item.startswith("identity_conflict:poi-g3-corridor:poi_admin_mismatch:")
        )
        feedback = json.loads(warning.split(":", 3)[3])
        self.assertEqual([{
            "administrative_area": "北京市/朝阳区",
            "name": "海岛生态廊道甲区",
        }], feedback["candidates"])
        self.assertEqual(["海岛生态廊道甲区"], feedback["suggested_names"])
        pois, _ = apply_locations(candidates["pois"], (), result)
        self.assertEqual((), result.locations)
        self.assertIsNone(pois[0]["coordinates"])

    def _identity_conflict_plan(self, mobility, *, include_candidate_unknown=True):
        scenario = load(AMAP_SCENARIOS / "g3_identity_conflict.json")
        candidates = amap_scenario_candidates(scenario)
        stale_reason = "AMap is not configured; coordinates remain unverified"
        if include_candidate_unknown:
            candidates["unknowns"] = [{
                "claim_id": candidates["claims"][0]["claim_id"],
                "field_path": "/pois/0/coordinates",
                "provider": "amap",
                "reason": stale_reason,
            }]
        request_value = {
            "origin": None,
            "destinations": [{"ref_id": "city-zhuhai", "name": "珠海", "city": "珠海"}],
            "start_date": "2026-09-10",
            "end_date": "2026-09-10",
            "travelers": 1,
            "budget_cny": 2000,
            "interests": ["synthetic-test-place"],
            "pace": "balanced",
            "constraints": [],
            "assumptions": ["synthetic offline identity-conflict acceptance"],
            "locale": "zh-CN",
            "pasted_notes": None,
        }
        result = plan_trip(
            request_value,
            candidates,
            self.clock,
            RailBackend.from_spec("off", ROOT),
            mobility,
        )
        return result, stale_reason

    def test_full_plan_replaces_stale_amap_unknown_with_entity_conflict(self):
        scenario = load(AMAP_SCENARIOS / "g3_identity_conflict.json")
        transport = AMapScenarioTransport(scenario)
        result, stale_reason = self._identity_conflict_plan(
            MobilityBackend("live", credentials(), transport),
        )

        unknown = next(
            item for item in result.trip["unknowns"]
            if item["field_path"] == "/pois/0/coordinates"
        )
        self.assertEqual(1, transport.calls)
        self.assertNotEqual(stale_reason, unknown["reason"])
        self.assertEqual(
            "identity_conflict:poi-g3-corridor:ambiguous_name_margin:"
            '{"candidates":[{"administrative_area":"珠海市/香洲区",'
            '"name":"海岛生态廊道甲区"},{"administrative_area":"珠海市/香洲区",'
            '"name":"海岛生态廊道乙区"}],"suggested_names":'
            '["海岛生态廊道甲区","海岛生态廊道乙区"]}',
            unknown["reason"],
        )

    def test_full_plan_mobility_off_preserves_candidate_reason_byte_for_byte(self):
        transport = ScriptedAmapTransport()
        result, stale_reason = self._identity_conflict_plan(
            MobilityBackend("off", credentials(), transport),
        )

        unknown = next(
            item for item in result.trip["unknowns"]
            if item["field_path"] == "/pois/0/coordinates"
        )
        self.assertEqual(0, transport.calls)
        self.assertEqual(stale_reason, unknown["reason"])

    def test_full_plan_adds_missing_coordinate_unknown_for_live_identity_conflict(self):
        scenario = load(AMAP_SCENARIOS / "g3_identity_conflict.json")
        transport = AMapScenarioTransport(scenario)
        result, _ = self._identity_conflict_plan(
            MobilityBackend("live", credentials(), transport),
            include_candidate_unknown=False,
        )

        unknowns = [
            item for item in result.trip["unknowns"]
            if item["field_path"] == "/pois/0/coordinates"
        ]
        self.assertEqual(1, transport.calls)
        self.assertIsNone(result.trip["pois"][0]["coordinates"])
        self.assertEqual(1, len(unknowns))
        self.assertEqual("amap", unknowns[0]["provider"])
        self.assertIsNone(unknowns[0]["claim_id"])
        self.assertEqual(
            "identity_conflict:poi-g3-corridor:ambiguous_name_margin:"
            '{"candidates":[{"administrative_area":"珠海市/香洲区",'
            '"name":"海岛生态廊道甲区"},{"administrative_area":"珠海市/香洲区",'
            '"name":"海岛生态廊道乙区"}],"suggested_names":'
            '["海岛生态廊道甲区","海岛生态廊道乙区"]}',
            unknowns[0]["reason"],
        )

    def test_full_plan_mobility_off_does_not_invent_coordinate_unknown(self):
        transport = ScriptedAmapTransport()
        result, _ = self._identity_conflict_plan(
            MobilityBackend("off", credentials(), transport),
            include_candidate_unknown=False,
        )

        self.assertEqual(0, transport.calls)
        self.assertIsNone(result.trip["pois"][0]["coordinates"])
        self.assertFalse(any(
            item["field_path"] == "/pois/0/coordinates"
            for item in result.trip["unknowns"]
        ))

    def test_full_plan_missing_amap_key_does_not_invent_coordinate_unknown(self):
        scenario = load(AMAP_SCENARIOS / "g3_identity_conflict.json")
        transport = AMapScenarioTransport(scenario)
        result, _ = self._identity_conflict_plan(
            MobilityBackend("live", credentials(False), transport),
            include_candidate_unknown=False,
        )

        self.assertEqual(0, transport.calls)
        self.assertIsNone(result.trip["pois"][0]["coordinates"])
        self.assertFalse(any(
            item["field_path"] == "/pois/0/coordinates"
            for item in result.trip["unknowns"]
        ))

    def test_full_plan_adds_lodging_coordinate_unknown_with_runtime_feedback(self):
        settled = {
            "source_crs": "GCJ02",
            "native": {"lng": 113.57, "lat": 22.27},
            "gcj02": {"lng": 113.57, "lat": 22.27},
            "wgs84": {"lng": 113.5647, "lat": 22.2727},
            "conversion": {
                "status": "converted",
                "method": "gcj02-to-wgs84",
                "version": "ctw-1",
                "derived_fields": ["wgs84"],
                "converted_at": FIXED_NOW,
                "accuracy_m": 10,
            },
        }
        candidates = {
            "candidates_version": "1.0.0",
            "pois": [{
                "poi_id": "poi-lodging-plan-anchor",
                "name": "合成已定位景点",
                "city": "珠海",
                "category": "sight",
                "coordinates": settled,
                "recommended_duration_minutes": 60,
                "opening_windows": [],
                "price": None,
                "deep_links": ["https://example.invalid/poi-lodging-plan-anchor"],
                "claim_ids": ["claim-lodging-plan-anchor"],
            }],
            "lodgings": [{
                "lodging_id": "lodging-runtime-mismatch",
                "name": "合成住宿候选",
                "city": "珠海",
                "area": "合成片区",
                "check_in": "2026-09-10",
                "check_out": "2026-09-11",
                "coordinates": None,
                "locked": False,
                "price": None,
                "deep_links": ["https://example.invalid/lodging-runtime-mismatch"],
                "claim_ids": ["claim-lodging-runtime-mismatch"],
            }],
            "claims": [{
                "claim_id": "claim-lodging-plan-anchor",
                "subject_ref": "poi-lodging-plan-anchor",
                "field_path": "/name",
                "value": "合成已定位景点",
                "source_url": "https://example.invalid/poi-lodging-plan-anchor",
                "provider": "official-web",
                "queried_at": FIXED_NOW,
                "status": "verified",
                "confidence": 0.9,
                "mode": "static",
                "as_of": None,
                "raw_ref": None,
                "response_hash": None,
                "json_path": None,
            }, {
                "claim_id": "claim-lodging-runtime-mismatch",
                "subject_ref": "lodging-runtime-mismatch",
                "field_path": "/name",
                "value": "合成住宿候选",
                "source_url": "https://example.invalid/lodging-runtime-mismatch",
                "provider": "official-web",
                "queried_at": FIXED_NOW,
                "status": "verified",
                "confidence": 0.9,
                "mode": "static",
                "as_of": None,
                "raw_ref": None,
                "response_hash": None,
                "json_path": None,
            }],
            "unknowns": [],
        }
        scenario = {"entities": [{
            "ref_id": "lodging-runtime-mismatch",
            "poi_results": [],
            "geocode": {
                "location": "119.300000,26.080000",
                "formatted_address": "另一座城合成住宿",
                "city": "另一座城",
            },
        }]}
        request_value = {
            "origin": None,
            "destinations": [{"ref_id": "city-zhuhai", "name": "珠海", "city": "珠海"}],
            "start_date": "2026-09-10",
            "end_date": "2026-09-11",
            "travelers": 1,
            "budget_cny": 2000,
            "interests": ["sight"],
            "pace": "balanced",
            "constraints": [],
            "assumptions": ["synthetic lodging coordinate failure"],
            "locale": "zh-CN",
            "pasted_notes": None,
        }
        transport = AMapScenarioTransport(scenario)
        result = plan_trip(
            request_value,
            candidates,
            self.clock,
            RailBackend.from_spec("off", ROOT),
            MobilityBackend("live", credentials(), transport),
        )

        unknowns = [
            item for item in result.trip["unknowns"]
            if item["field_path"] == "/lodgings/0/coordinates"
        ]
        self.assertEqual(1, transport.calls)
        self.assertEqual(["geocode"], transport.capabilities)
        self.assertIsNone(result.trip["lodgings"][0]["coordinates"])
        self.assertEqual(1, len(unknowns))
        self.assertEqual("amap", unknowns[0]["provider"])
        self.assertIsNone(unknowns[0]["claim_id"])
        self.assertIn("geocode_admin_mismatch", unknowns[0]["reason"])
        self.assertIn('"actual_administrative_area":"另一座城"', unknowns[0]["reason"])
        self.assertIn('"suggested_names":[]', unknowns[0]["reason"])

    def test_demo_candidates_produce_bounded_two_mode_live_matrix(self):
        transport = ScriptedAmapTransport()
        backend = MobilityBackend("live", credentials(), transport)
        result = backend.resolve(self.candidates, self.clock, ("transit", "walking"))
        self.assertEqual(5, len(result.locations))
        self.assertEqual(40, len(result.cells))
        self.assertEqual(49, transport.calls)
        self.assertLessEqual(transport.calls, 80)
        self.assertEqual("ready", result.health["status"])
        self.assertIn("calls=49/80 qps<=2", result.health["reason"])
        self.assertEqual({"transit", "walk"}, {cell.travel_mode for cell in result.cells})
        for location in result.locations:
            self.assertIsNotNone(location.coordinates["gcj02"])
            self.assertIsNotNone(location.coordinates["wgs84"])
        for cell in result.cells:
            self.assertEqual("live", cell.mode)
            self.assertTrue(cell.claim_ids)

    def test_wrong_key_is_forbidden_with_zero_cells_and_one_call(self):
        transport = ScriptedAmapTransport(forbidden=True)
        backend = MobilityBackend("live", credentials(), transport)
        result = backend.resolve(self.candidates, self.clock, ("transit",))
        self.assertEqual(1, transport.calls)
        self.assertEqual((), result.cells)
        self.assertEqual("forbidden", result.health["status"])
        self.assertIn("calls=1/80", result.health["reason"])

    def test_combined_health_never_hides_lodging_budget_exhaustion(self):
        common = {
            "provider": "amap",
            "version": "web-service-v5-v3-route",
            "checked_at": FIXED_NOW,
        }
        mobility = dict(common, **{
            "mode": "live",
            "status": "ready",
            "capabilities": ["geocode", "poi", "route"],
            "reason": "calls=4/4 qps<=2; live_cells=1; locations=2; errors=none; warnings=none",
        })
        lodging = dict(common, **{
            "mode": "static",
            "status": "degraded",
            "capabilities": ["lodging"],
            "reason": "poi_calls=1; lodging_items=0; prices=verify-on-click; errors=rate_limited",
        })
        combined = _combined_amap_health(mobility, lodging)
        self.assertEqual("rate_limited", combined["status"])
        self.assertIn("errors=rate_limited", combined["reason"])

    def test_missing_key_makes_no_call(self):
        transport = ScriptedAmapTransport()
        backend = MobilityBackend("live", credentials(False), transport)
        result = backend.resolve(self.candidates, self.clock, ("transit",))
        self.assertEqual(0, transport.calls)
        self.assertEqual("missing", result.health["status"])
        self.assertEqual((), result.cells)

    def test_live_plan_reaches_matrix_ready_and_publishes_coordinates(self):
        rail = RailBackend.from_spec("fixture:" + str(E2E / "rail.json"), ROOT)
        transport = ScriptedAmapTransport()
        mobility = MobilityBackend("live", credentials(), transport)
        result = plan_trip(
            load(E2E / "request.json"),
            load(E2E / "candidates.json"),
            self.clock,
            rail,
            mobility,
        )
        self.assertIn("MATRIX_READY", result.stages)
        self.assertNotIn("MATRIX_DEGRADED", result.stages)
        amap = next(item for item in result.trip["provider_health"] if item["provider"] == "amap")
        self.assertEqual("ready", amap["status"])
        self.assertEqual("live", amap["mode"])
        self.assertIn("calls=29/80", amap["reason"])
        for item in result.trip["pois"] + result.trip["lodgings"]:
            self.assertIsNotNone(item["coordinates"]["gcj02"])
            self.assertIsNotNone(item["coordinates"]["wgs84"])

    def test_resolved_coordinates_drop_their_candidate_unknown(self):
        """A coordinate the provider resolved must not still be listed as unknown."""

        rail = RailBackend.from_spec("fixture:" + str(E2E / "rail.json"), ROOT)
        mobility = MobilityBackend("live", credentials(), ScriptedAmapTransport())
        candidates = load(E2E / "candidates.json")
        pending = {
            item["field_path"]
            for item in candidates["unknowns"]
            if item.get("field_path", "").endswith("/coordinates")
        }
        self.assertTrue(pending, "fixture must start with pending coordinate unknowns")

        result = plan_trip(
            load(E2E / "request.json"), candidates, self.clock, rail, mobility,
        )

        for group in ("pois", "lodgings"):
            for index, item in enumerate(result.trip[group]):
                path = "/%s/%d/coordinates" % (group, index)
                resolved = item["coordinates"] is not None
                still_unknown = any(
                    entry.get("field_path") == path for entry in result.trip["unknowns"]
                )
                self.assertNotEqual(
                    (resolved, still_unknown),
                    (True, True),
                    "%s has coordinates but is still reported unknown" % path,
                )

    def test_lodging_geocode_admin_mismatch_degrades_without_crashing(self):
        """A lodging never runs POI lookup, so the mismatch path must not read POI state."""

        class MismatchTransport:
            calls = 0

            def execute(self, provider, provider_request):
                del provider
                MismatchTransport.calls += 1
                if provider_request.capability != "geocode":
                    raise AssertionError("lodging must not trigger %s" % provider_request.capability)
                return ProviderEnvelope(
                    200,
                    {
                        "status": "1",
                        "api": "geocode-v3",
                        "geocodes": [{
                            "location": "119.300000,26.080000",
                            "formatted_address": "示例省示例市示例住宿",
                            "city": "另一座城",
                        }],
                    },
                    {},
                )

        settled = {
            "source_crs": "GCJ02",
            "native": {"lng": 119.3, "lat": 26.08},
            "gcj02": {"lng": 119.3, "lat": 26.08},
            "wgs84": {"lng": 119.2945, "lat": 26.0819},
            "conversion": {
                "status": "converted",
                "method": "gcj02-to-wgs84",
                "version": "ctw-1",
                "derived_fields": ["wgs84"],
                "converted_at": "2026-10-01T08:40:00+08:00",
                "accuracy_m": 10,
            },
        }
        candidates = {
            "candidates_version": "1.0.0",
            "pois": [{
                "poi_id": "poi-already-located",
                "name": "已定位合成景点",
                "city": "合成甲城",
                "category": "sight",
                "coordinates": settled,
                "recommended_duration_minutes": 60,
                "opening_windows": [],
                "price": None,
                "deep_links": ["https://example.invalid/poi"],
                "claim_ids": ["claim-probe"],
            }],
            "lodgings": [{
                "lodging_id": "lodging-mismatch-probe",
                "name": "合成住宿候选",
                "city": "合成甲城",
                "area": "合成片区",
                "check_in": "2026-10-16",
                "check_out": "2026-10-17",
                "coordinates": None,
                "locked": False,
                "price": None,
                "deep_links": ["https://example.invalid/lodging"],
                "claim_ids": ["claim-lodging-probe"],
            }],
            "claims": [{
                "claim_id": "claim-probe",
                "subject_ref": "poi-already-located",
                "field_path": "/name",
                "value": "已定位合成景点",
                "source_url": "https://example.invalid/poi",
                "provider": "host-web",
                "status": "partial",
                "confidence": 0.6,
                "mode": "static",
                "queried_at": "2026-10-15T00:00:00+08:00",
                "as_of": None,
                "json_path": None,
                "raw_ref": None,
                "response_hash": None,
            }, {
                "claim_id": "claim-lodging-probe",
                "subject_ref": "lodging-mismatch-probe",
                "field_path": "/name",
                "value": "合成住宿候选",
                "source_url": "https://example.invalid/lodging",
                "provider": "host-web",
                "status": "partial",
                "confidence": 0.6,
                "mode": "static",
                "queried_at": "2026-10-15T00:00:00+08:00",
                "as_of": None,
                "json_path": None,
                "raw_ref": None,
                "response_hash": None,
            }],
            "unknowns": [],
        }
        backend = MobilityBackend("live", credentials(), MismatchTransport())

        result = backend.resolve(candidates, self.clock, ("transit",))

        self.assertIn("identity_conflict", result.health["reason"])
        located = [item.ref_id for item in result.locations]
        self.assertNotIn("lodging-mismatch-probe", located)
        self.assertIn("poi-already-located", located)
        self.assertTrue(
            any("geocode_admin_mismatch" in item for item in result.warnings),
            result.warnings,
        )

    def test_live_lodging_replacement_drops_obsolete_mobility_claim_subject(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            folder = Path(temporary)
            flyai_credentials = resolve_credentials({}, folder / "missing-flyai")
            flyai_transport = FlyAISubprocessTransport(
                flyai_credentials,
                cache_dir=folder / "npm-cache",
                temp_root=folder / "flyai-home",
                command=(sys.executable, str(FLYAI_SERVER), "normal"),
                cwd=ROOT,
            )
            flyai = FlyAIBackend("live", flyai_credentials, flyai_transport)
            amap_transport = ScriptedAmapTransport()
            mobility = MobilityBackend("live", credentials(), amap_transport)
            rail = RailBackend.from_spec("fixture:" + str(E2E / "rail.json"), ROOT)
            result = plan_trip(
                load(E2E / "request.json"),
                load(E2E / "candidates.json"),
                self.clock,
                rail,
                mobility,
                flyai,
            )
        entity_ids = {
            item["lodging_id"] for item in result.trip["lodgings"]
        } | {
            item["poi_id"] for item in result.trip["pois"]
        } | {
            item["leg_id"] for item in result.trip["transport_legs"]
        }
        self.assertTrue(all(claim["subject_ref"] in entity_ids for claim in result.trip["claims"]))
        original_lodging_id = load(E2E / "candidates.json")["lodgings"][0]["lodging_id"]
        self.assertNotIn(original_lodging_id, {claim["subject_ref"] for claim in result.trip["claims"]})

    def test_cli_mode_aliases_are_stable(self):
        self.assertEqual(("transit", "walk", "drive", "ride"), normalize_modes(
            ("transit", "walking", "driving", "riding"),
        ))


if __name__ == "__main__":
    unittest.main()
