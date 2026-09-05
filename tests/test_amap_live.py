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
from china_trip_weaver.mobility import MobilityBackend, apply_locations, normalize_modes
from china_trip_weaver.planning import RailBackend, plan_trip
from china_trip_weaver.providers.amap import AMapAdapter
from china_trip_weaver.providers.amap_http import AMapCallBudget, AMapHTTPTransport
from china_trip_weaver.providers.base import ProviderContext, ProviderEnvelope, ProviderRateLimited
from china_trip_weaver.providers.flyai_cli import FlyAISubprocessTransport
from tests.test_providers import AMAP_SCENARIOS, AMapScenarioTransport, amap_scenario_candidates


FIXED_NOW = "2026-09-03T12:00:00+08:00"
E2E = ROOT / "tests" / "fixtures" / "e2e" / "beijing-shanghai-3d"
FLYAI_SERVER = ROOT / "tests" / "fixtures" / "flyai_cli_server.py"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


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


class AMapMobilityTests(unittest.TestCase):
    def setUp(self):
        self.clock = FixedClock.from_iso(FIXED_NOW)
        self.candidates = load(ROOT / "demo" / "candidates.json")

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

    def _identity_conflict_plan(self, mobility):
        scenario = load(AMAP_SCENARIOS / "g3_identity_conflict.json")
        candidates = amap_scenario_candidates(scenario)
        stale_reason = "AMap is not configured; coordinates remain unverified"
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
            "identity_conflict:poi-g3-corridor:ambiguous_name_margin",
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
