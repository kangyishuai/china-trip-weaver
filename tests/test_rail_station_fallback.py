from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "plugins" / "china-trip-weaver" / "src"
sys.path.insert(0, str(SRC))

from china_trip_weaver.clock import FixedClock
from china_trip_weaver.contracts import ProviderRequest
from china_trip_weaver.credentials import resolve_credentials
from china_trip_weaver.providers.base import ProviderContext, ProviderEnvelope, ProviderNetworkError
from china_trip_weaver.providers.mcp_stdio import (
    EXPECTED_12306_TOOLS,
    RailMCPStdioTransport,
    _resolve_rail_stations,
)
from china_trip_weaver.matrix import haversine_meters
from china_trip_weaver.providers.rail12306 import Rail12306Adapter
from china_trip_weaver.station_distance import AMapStationDistanceEnricher


SERVER = ROOT / "tests" / "fixtures" / "mcp_stdio_server.py"
MATRIX_SERVER = ROOT / "tests" / "fixtures" / "provider_matrix_mcp_server.py"
EXPECTED_TOOL_FINGERPRINT = (
    "get-current-date",
    "get-stations-code-in-city",
    "get-station-code-of-citys",
    "get-station-code-by-names",
    "get-station-by-telecode",
    "get-tickets",
    "get-interline-tickets",
    "get-train-route-stations",
)


class StationAMapFixtureTransport:
    """Synthetic AMap-shaped transport; no provider response was captured."""

    def __init__(
        self,
        *,
        centre_available=True,
        fail=False,
        station_points=None,
        station_name_overrides=None,
        station_city="多站城市",
        centre_city="多站城市",
        centre_district="合成中心区",
        station_district="合成站区",
    ):
        self.centre_available = centre_available
        self.fail = fail
        self.station_points = dict(station_points or {
            "多站城近站": "100.001000,20.000000",
            "多站城远站": "100.010000,20.000000",
        })
        self.station_name_overrides = dict(station_name_overrides or {})
        self.station_city = station_city
        self.centre_city = centre_city
        self.centre_district = centre_district
        self.station_district = station_district
        self.requests = []

    def execute(self, provider, request):
        self.requests.append(request)
        if provider != "amap":
            raise AssertionError("station fixture is restricted to amap")
        if self.fail:
            raise ProviderNetworkError("synthetic AMap outage")
        if request.capability == "geocode":
            geocodes = []
            if self.centre_available:
                geocodes.append({
                    "formatted_address": "多站城市",
                    "province": "合成省",
                    "city": self.centre_city,
                    "district": self.centre_district,
                    "adcode": "990001",
                    "location": "100.000000,20.000000",
                    "level": "市",
                })
            body = {
                "status": "1",
                "info": "OK",
                "infocode": "10000",
                "count": str(len(geocodes)),
                "api": "geocode-v3",
                "geocodes": geocodes,
            }
        elif request.capability == "poi":
            station_name = request.parameters["keywords"]
            location = self.station_points.get(station_name)
            pois = []
            if location is not None:
                amap_name = station_name[:-1] + "火车站" if station_name.endswith("站") else station_name + "站"
                pois.append({
                    "id": "SYNTHETIC-STATION-" + request.request_id[-8:],
                    "name": self.station_name_overrides.get(station_name, amap_name),
                    "location": location,
                    "pname": "合成省",
                    "cityname": self.station_city,
                    "adname": self.station_district,
                    "address": "合成铁路大道",
                    "adcode": "990001",
                    "type": "交通设施服务;火车站;火车站",
                })
            body = {
                "status": "1",
                "info": "OK",
                "infocode": "10000",
                "count": str(len(pois)),
                "api": "poi-v5",
                "page_size": request.parameters["page_size"],
                "page_num": request.parameters["page_num"],
                "pois": pois,
            }
        else:
            raise AssertionError("unexpected AMap fixture capability")
        return ProviderEnvelope(status_code=200, body=body, headers={})


class StationAMapFailureTransport(StationAMapFixtureTransport):
    """Inject one synthetic AMap failure after 12306 returns ambiguous stations."""

    def __init__(self, outcome):
        super().__init__()
        self.outcome = outcome

    def execute(self, provider, request):
        if provider != "amap":
            raise AssertionError("station fixture is restricted to amap")
        if self.outcome == "ambiguous_centre" and request.capability == "geocode":
            self.requests.append(request)
            return ProviderEnvelope(200, {
                "status": "1",
                "info": "OK",
                "infocode": "10000",
                "count": "2",
                "api": "geocode-v3",
                "geocodes": [{
                    "formatted_address": "合成多站城中心甲",
                    "province": "合成省",
                    "city": "多站城市",
                    "district": "合成中心一区",
                    "adcode": "990001",
                    "location": "0.100000,0.200000",
                }, {
                    "formatted_address": "合成多站城中心乙",
                    "province": "合成省",
                    "city": "多站城市",
                    "district": "合成中心二区",
                    "adcode": "990002",
                    "location": "0.300000,0.400000",
                }],
            }, {})
        if request.capability == "poi" and self.outcome == "rate_limited_poi":
            self.requests.append(request)
            return ProviderEnvelope(
                429, {"error": "synthetic station quota"}, {"Retry-After": "30"},
            )
        if request.capability == "poi" and self.outcome == "contract_drift_poi":
            self.requests.append(request)
            return ProviderEnvelope(200, {
                "status": "1",
                "info": "OK",
                "infocode": "10000",
                "count": "0",
                "api": "poi-v5",
                "page_size": request.parameters["page_size"],
                "page_num": request.parameters["page_num"],
                "pois": {},
            }, {})
        return super().execute(provider, request)


class RailStationFallbackTests(unittest.TestCase):
    def _query(
        self,
        mode,
        from_name,
        to_name,
        station_distance_enricher=None,
        server=SERVER,
    ):
        credentials = resolve_credentials({}, ROOT / ".tmp" / "rail-station-fallback-no-credentials")
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            transport = RailMCPStdioTransport(
                cache_dir=Path(temporary) / "npm-cache",
                credentials=credentials,
                command=(sys.executable, str(server), mode),
                cwd=ROOT,
                station_distance_enricher=station_distance_enricher,
            )
            request = ProviderRequest(
                request_id="rail-station-fallback-" + mode,
                capability="rail",
                parameters={
                    "date": "2026-09-10",
                    "from_name": from_name,
                    "to_name": to_name,
                    "from_ref": "place-from",
                    "to_ref": "place-to",
                    "train_filter_flags": "G",
                    "limited_num": 2,
                },
                deadline_ms=2000,
                as_of="2026-09-10",
                cache_policy="bypass",
                trace={"stage": "station-fallback-test"},
            )
            context = ProviderContext(
                clock=FixedClock.from_iso("2026-09-03T20:46:00+08:00"),
                credentials=credentials,
                transport=transport,
            )
            result = Rail12306Adapter().query(request, context)
            diagnostics = tuple(transport.last_stderr)
        return result, diagnostics

    @staticmethod
    def _amap_enricher(transport, *, configured=True):
        environ = {"AMAP_WEBSERVICE_KEY": "station-distance-fixture-key"} if configured else {}
        credentials = resolve_credentials(environ, ROOT / ".tmp" / "rail-station-amap-no-file")
        return AMapStationDistanceEnricher(
            credentials,
            transport=transport,
            clock=FixedClock.from_iso("2026-09-03T20:46:00+08:00"),
        )

    @staticmethod
    def _calls(diagnostics):
        return [line.split("=", 1)[1] for line in diagnostics if line.startswith("fixture-call=")]

    def _assert_exact_station_input(self, name, code):
        result, diagnostics = self._query("station-inputs", "北京南", name)
        self.assertIsNone(result.error_class)
        self.assertEqual("ready", result.health["status"])
        self.assertNotEqual("contract_mismatch", result.health["status"])
        self.assertEqual(["get-station-code-by-names", "get-tickets"], self._calls(diagnostics))
        self.assertIn("fixture-ticket-codes=BNX|" + code, diagnostics)

    def test_g5_exact_station_names_bypass_representative_error_without_false_contract_mismatch(self):
        result, diagnostics = self._query("g5-station-fallback", "北京南", "上海虹桥")
        self.assertIsNone(result.error_class)
        self.assertEqual("ready", result.health["status"])
        self.assertNotEqual("contract_mismatch", result.health["status"])
        self.assertEqual("G5", result.normalized_items[0]["service_number"])
        self.assertEqual(
            ["get-station-code-by-names", "get-tickets"],
            self._calls(diagnostics),
        )
        self.assertIn("fixture-ticket-codes=BNX|HXX", diagnostics)

    def test_all_city_stations_is_used_only_after_exact_and_representative_miss(self):
        result, diagnostics = self._query("all-stations-fallback", "武夷山", "昆明南")
        self.assertIsNone(result.error_class)
        self.assertEqual("ready", result.health["status"])
        self.assertEqual(
            [
                "get-station-code-by-names",
                "get-station-code-of-citys",
                "get-stations-code-in-city",
                "get-tickets",
            ],
            self._calls(diagnostics),
        )
        self.assertIn("fixture-ticket-codes=WYX|KMX", diagnostics)

    def test_wuyishan_north_is_classified_as_a_resolved_exact_station(self):
        self._assert_exact_station_input("武夷山北", "WYX")

    def test_nanpingshi_is_classified_as_a_resolved_exact_station(self):
        self._assert_exact_station_input("南平市", "NPX")

    def test_kunming_south_is_classified_as_a_resolved_exact_station(self):
        self._assert_exact_station_input("昆明南", "KMX")

    def test_pingtan_is_classified_as_a_resolved_exact_station(self):
        self._assert_exact_station_input("平潭", "PTX")

    def test_tool_fingerprint_drift_remains_contract_mismatch(self):
        result, diagnostics = self._query("tool-fingerprint-drift", "北京南", "武夷山北")
        self.assertEqual("contract_mismatch", result.error_class)
        self.assertEqual("contract_mismatch", result.health["status"])
        self.assertEqual((), result.normalized_items)
        self.assertEqual([], self._calls(diagnostics))
        self.assertEqual(EXPECTED_TOOL_FINGERPRINT, EXPECTED_12306_TOOLS)

    def test_representative_city_is_used_only_after_exact_name_misses(self):
        result, diagnostics = self._query("representative-fallback", "北京", "上海")
        self.assertIsNone(result.error_class)
        self.assertEqual("ready", result.health["status"])
        self.assertEqual(
            ["get-station-code-by-names", "get-station-code-of-citys", "get-tickets"],
            self._calls(diagnostics),
        )

    def test_three_empty_station_layers_are_no_results_with_ready_provider_health(self):
        result, diagnostics = self._query("station-no-results", "未知起点", "未知终点")
        self.assertEqual("no_results", result.error_class)
        self.assertEqual("ready", result.health["status"])
        self.assertIn("no_results", result.health["reason"])
        self.assertNotIn("contract_mismatch", result.health["reason"])
        self.assertEqual((), result.normalized_items)
        self.assertEqual(
            [
                "get-station-code-by-names",
                "get-station-code-of-citys",
                "get-stations-code-in-city",
                "get-stations-code-in-city",
            ],
            self._calls(diagnostics),
        )

    def test_multiple_city_stations_are_returned_sorted_and_classified_ambiguous(self):
        amap = StationAMapFixtureTransport()
        result, diagnostics = self._query(
            "station-ambiguous",
            "多站城",
            "昆明南",
            self._amap_enricher(amap),
        )
        self.assertEqual("ambiguous", result.error_class)
        self.assertEqual("ready", result.health["status"])
        self.assertIn("ambiguous", result.health["reason"])
        self.assertNotIn("contract_mismatch", result.health["reason"])
        from_candidates = [item for item in result.normalized_items if item["resolution_for"] == "from"]
        self.assertEqual(["BBX", "AAX", "CCX"], [item["station_code"] for item in from_candidates])
        self.assertEqual([104, 1045], [item["distance_meters"] for item in from_candidates[:2]])
        self.assertNotIn("distance_meters", from_candidates[2])
        self.assertEqual(3, len(from_candidates))
        self.assertEqual(["geocode", "poi", "poi", "poi"], [request.capability for request in amap.requests])
        self.assertEqual({"address": "多站城", "city": "多站城"}, amap.requests[0].parameters)
        self.assertEqual(
            {"多站城未知站", "多站城近站", "多站城远站"},
            {request.parameters["keywords"] for request in amap.requests[1:]},
        )
        self.assertTrue(all(request.parameters["city"] == "多站城" for request in amap.requests))
        self.assertTrue(all(request.parameters["page_size"] == 5 for request in amap.requests[1:]))
        self.assertTrue(all(request.parameters["page_num"] == 1 for request in amap.requests[1:]))
        self.assertNotIn("get-tickets", self._calls(diagnostics))

    def test_nonmatching_poi_does_not_guess_or_remove_the_station(self):
        amap = StationAMapFixtureTransport(
            station_points={
                "多站城近站": "100.001000,20.000000",
                "多站城远站": "100.010000,20.000000",
                "多站城未知站": "100.020000,20.000000",
            },
            station_name_overrides={"多站城未知站": "不相干合成站"},
        )
        result, _ = self._query(
            "station-ambiguous", "多站城", "昆明南", self._amap_enricher(amap),
        )
        candidates = [item for item in result.normalized_items if item["resolution_for"] == "from"]
        self.assertEqual(["BBX", "AAX", "CCX"], [item["station_code"] for item in candidates])
        self.assertNotIn("distance_meters", candidates[2])

    def test_wrong_city_station_pois_do_not_add_distance_or_remove_candidates(self):
        """Name predates the station-cross-city book's 邻市距离 rule (task 2's
        leader ruling names this test as one of the two allowed to have its
        assertions rewritten, not renamed): a same-named station reported
        under a different city is exactly the "wrong city" shape the
        nationwide fallback exists for, so it now gains a distance when it
        is within STATION_MAX_DISTANCE_METERS of the researched city's
        centre, instead of staying unknown forever.
        """
        amap = StationAMapFixtureTransport(station_city="另一座城市")
        result, diagnostics = self._query(
            "station-ambiguous", "多站城", "昆明南", self._amap_enricher(amap),
        )

        candidates = [
            item for item in result.normalized_items
            if item["resolution_for"] == "from"
        ]
        self.assertEqual(["BBX", "AAX", "CCX"], [
            item["station_code"] for item in candidates
        ])
        self.assertEqual([104, 1045], [item["distance_meters"] for item in candidates[:2]])
        self.assertNotIn("distance_meters", candidates[2])
        # Candidates are queried in their pre-distance order (多站城未知站
        # 多站城近站 多站城远站), and each candidate's nationwide retry
        # (city_limit=false) runs immediately after its own failed
        # city-limited pass rather than as a separate later batch. 多站城
        # 未知站/CCX has no POI at all in the city-limited pass, so it gets
        # no nationwide call (the "found_any_poi" gate) — a flat 3+2 calls,
        # not a wasted 3+3.
        self.assertEqual(
            [
                ("geocode", None),
                ("poi", "true"),
                ("poi", "true"),
                ("poi", "false"),
                ("poi", "true"),
                ("poi", "false"),
            ],
            [(request.capability, request.parameters.get("city_limit")) for request in amap.requests],
        )
        self.assertEqual("ambiguous", result.error_class)
        self.assertEqual("ready", result.health["status"])
        self.assertNotIn("get-tickets", self._calls(diagnostics))

    @staticmethod
    def _district_match_resolution():
        return {
            "status": "ambiguous",
            "endpoints": {
                "from": {
                    "query": "平潭",
                    "candidates": [
                        {"station_name": "多站城近站"},
                        {"station_name": "多站城远站"},
                    ],
                },
                "to": {
                    "query": "昆明南",
                    "candidates": [{"station_name": "昆明南"}],
                },
            },
        }

    @staticmethod
    def _district_match_request(request_id):
        return ProviderRequest(
            request_id=request_id,
            capability="rail",
            parameters={},
            deadline_ms=2000,
            as_of="2026-09-10",
            cache_policy="bypass",
            trace={"stage": "station-district-test"},
        )

    def test_district_name_matches_the_researched_city_and_gains_a_distance(self):
        amap = StationAMapFixtureTransport(
            centre_city="福州市", centre_district="平潭县",
            station_city="福州市", station_district="平潭县",
        )
        enricher = self._amap_enricher(amap)
        enriched = enricher.enrich(
            self._district_match_resolution(),
            self._district_match_request("station-district-match"),
        )
        from_candidates = enriched["endpoints"]["from"]["candidates"]
        self.assertEqual(2, len(from_candidates))
        self.assertTrue(all("distance_meters" in item for item in from_candidates))

    def test_unrelated_district_does_not_gain_a_distance(self):
        amap = StationAMapFixtureTransport(
            centre_city="厦门市", centre_district="思明区",
            station_city="厦门市", station_district="思明区",
        )
        enricher = self._amap_enricher(amap)
        enriched = enricher.enrich(
            self._district_match_resolution(),
            self._district_match_request("station-district-mismatch"),
        )
        from_candidates = enriched["endpoints"]["from"]["candidates"]
        self.assertEqual(2, len(from_candidates))
        self.assertTrue(all("distance_meters" not in item for item in from_candidates))

    def test_amap_network_failure_keeps_all_candidates_and_rail_health_ready(self):
        amap = StationAMapFixtureTransport(fail=True)
        result, diagnostics = self._query(
            "station-ambiguous", "多站城", "昆明南", self._amap_enricher(amap),
        )
        self.assertEqual("ready", result.health["status"])
        self.assertNotIn("degraded", result.health["reason"])
        self.assertEqual("ambiguous", result.error_class)
        candidates = [item for item in result.normalized_items if item["resolution_for"] == "from"]
        self.assertEqual(["CCX", "BBX", "AAX"], [item["station_code"] for item in candidates])
        self.assertTrue(all("distance_meters" not in item for item in candidates))
        self.assertNotIn("get-tickets", self._calls(diagnostics))
        self.assertEqual(1, len(amap.requests))

    def test_amap_ambiguous_centre_keeps_all_stations_and_rail_health_ready(self):
        amap = StationAMapFailureTransport("ambiguous_centre")
        result, diagnostics = self._query(
            "station-ambiguous-synthetic", "多站城", "合成终点", self._amap_enricher(amap),
        )

        candidates = [
            item for item in result.normalized_items
            if item["resolution_for"] == "from"
        ]
        self.assertEqual("ready", result.health["status"])
        self.assertEqual("ambiguous", result.error_class)
        self.assertEqual(["CCX", "BBX", "AAX"], [
            item["station_code"] for item in candidates
        ])
        self.assertEqual([False, False, False], [
            "distance_meters" in item for item in candidates
        ])
        self.assertEqual(["geocode"], [request.capability for request in amap.requests])
        self.assertEqual([], [
            call for call in self._calls(diagnostics) if call == "get-tickets"
        ])

    def test_amap_poi_rate_limit_keeps_all_stations_and_rail_health_ready(self):
        amap = StationAMapFailureTransport("rate_limited_poi")
        result, diagnostics = self._query(
            "station-ambiguous-synthetic", "多站城", "合成终点", self._amap_enricher(amap),
        )

        candidates = [
            item for item in result.normalized_items
            if item["resolution_for"] == "from"
        ]
        self.assertEqual("ready", result.health["status"])
        self.assertEqual("ambiguous", result.error_class)
        self.assertEqual(["CCX", "BBX", "AAX"], [
            item["station_code"] for item in candidates
        ])
        self.assertEqual([False, False, False], [
            "distance_meters" in item for item in candidates
        ])
        self.assertEqual(
            ["geocode", "poi"], [request.capability for request in amap.requests],
        )
        self.assertEqual([], [
            call for call in self._calls(diagnostics) if call == "get-tickets"
        ])

    def test_amap_poi_contract_drift_keeps_all_stations_and_rail_health_ready(self):
        amap = StationAMapFailureTransport("contract_drift_poi")
        result, diagnostics = self._query(
            "station-ambiguous-synthetic", "多站城", "合成终点", self._amap_enricher(amap),
        )

        candidates = [
            item for item in result.normalized_items
            if item["resolution_for"] == "from"
        ]
        self.assertEqual("ready", result.health["status"])
        self.assertEqual("ambiguous", result.error_class)
        self.assertEqual(["CCX", "BBX", "AAX"], [
            item["station_code"] for item in candidates
        ])
        self.assertEqual([False, False, False], [
            "distance_meters" in item for item in candidates
        ])
        self.assertEqual(
            ["geocode", "poi"], [request.capability for request in amap.requests],
        )
        self.assertEqual([], [
            call for call in self._calls(diagnostics) if call == "get-tickets"
        ])

    def test_missing_amap_key_makes_no_calls_and_keeps_unknown_distances(self):
        amap = StationAMapFixtureTransport()
        result, _ = self._query(
            "station-ambiguous",
            "多站城",
            "昆明南",
            self._amap_enricher(amap, configured=False),
        )
        candidates = [item for item in result.normalized_items if item["resolution_for"] == "from"]
        self.assertEqual(["CCX", "BBX", "AAX"], [item["station_code"] for item in candidates])
        self.assertTrue(all("distance_meters" not in item for item in candidates))
        self.assertEqual("ready", result.health["status"])
        self.assertEqual([], amap.requests)

    def test_missing_city_centre_skips_poi_calls_and_keeps_candidates(self):
        amap = StationAMapFixtureTransport(centre_available=False)
        result, _ = self._query(
            "station-ambiguous", "多站城", "昆明南", self._amap_enricher(amap),
        )
        candidates = [item for item in result.normalized_items if item["resolution_for"] == "from"]
        self.assertEqual(3, len(candidates))
        self.assertTrue(all("distance_meters" not in item for item in candidates))
        self.assertEqual(["geocode"], [request.capability for request in amap.requests])

    def test_equal_distances_use_deterministic_name_and_code_tiebreakers(self):
        amap = StationAMapFixtureTransport(station_points={
            "多站城近站": "100.001000,20.000000",
            "多站城远站": "100.001000,20.000000",
        })
        result, _ = self._query(
            "station-ambiguous", "多站城", "昆明南", self._amap_enricher(amap),
        )
        candidates = [item for item in result.normalized_items if item["resolution_for"] == "from"]
        self.assertEqual(["BBX", "AAX", "CCX"], [item["station_code"] for item in candidates])
        self.assertEqual([104, 104], [item["distance_meters"] for item in candidates[:2]])
        self.assertNotIn("distance_meters", candidates[2])

    def test_station_response_shape_drift_is_still_contract_mismatch(self):
        result, diagnostics = self._query("station-shape-drift", "北京南", "武夷山北")
        self.assertEqual("contract_mismatch", result.error_class)
        self.assertEqual("contract_mismatch", result.health["status"])
        self.assertEqual(["get-station-code-by-names"], self._calls(diagnostics))

    def test_station_capability_not_found_text_is_no_results_not_contract_mismatch(self):
        credentials = resolve_credentials({}, ROOT / ".tmp" / "rail-station-fallback-no-credentials")
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            transport = RailMCPStdioTransport(
                cache_dir=Path(temporary) / "npm-cache",
                credentials=credentials,
                command=(sys.executable, str(SERVER), "station-no-results"),
                cwd=ROOT,
            )
            request = ProviderRequest(
                request_id="station-capability-no-results",
                capability="station",
                parameters={"city": "未知城市"},
                deadline_ms=2000,
                as_of="2026-09-10",
                cache_policy="bypass",
            )
            result = Rail12306Adapter().query(
                request,
                ProviderContext(
                    clock=FixedClock.from_iso("2026-09-03T20:46:00+08:00"),
                    credentials=credentials,
                    transport=transport,
                ),
            )
        self.assertEqual("no_results", result.error_class)
        self.assertEqual("ready", result.health["status"])
        self.assertNotIn("contract_mismatch", result.health["reason"])

    def test_station_capability_rate_limit_is_not_misclassified_as_no_results(self):
        credentials = resolve_credentials(
            {}, ROOT / ".tmp" / "rail-station-rate-limit-no-credentials",
        )
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            transport = RailMCPStdioTransport(
                cache_dir=Path(temporary) / "npm-cache",
                credentials=credentials,
                command=(
                    sys.executable, str(MATRIX_SERVER), "rail-station-rate-limit",
                ),
                cwd=ROOT,
            )
            station_request = ProviderRequest(
                request_id="station-capability-rate-limit",
                capability="station",
                parameters={"city": "合成限流城"},
                deadline_ms=2000,
                as_of="2026-09-10",
                cache_policy="bypass",
            )
            result = Rail12306Adapter().query(
                station_request,
                ProviderContext(
                    clock=FixedClock.from_iso("2026-09-03T20:46:00+08:00"),
                    credentials=credentials,
                    transport=transport,
                ),
            )
            diagnostics = tuple(transport.last_stderr)

        self.assertEqual("rate_limited", result.error_class)
        self.assertEqual("rate_limited", result.health["status"])
        self.assertEqual((), result.normalized_items)
        self.assertEqual(["get-stations-code-in-city"], self._calls(diagnostics))

    def test_station_network_exit_retries_then_degrades_exact_entity(self):
        marker = '            elif name == "get-stations-code-in-city":\n'
        source = SERVER.read_text(encoding="utf-8")
        self.assertEqual(1, source.count(marker))
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            network_exit_server = Path(temporary) / "station_network_exit_server.py"
            network_exit_server.write_text(
                source.replace(
                    marker,
                    marker + "                raise SystemExit(7)\n",
                ),
                encoding="utf-8",
            )
            result, diagnostics = self._query(
                "station-no-results",
                "合成网络城",
                "合成终点",
                server=network_exit_server,
            )

        self.assertEqual("network", result.error_class)
        self.assertEqual(("network",), result.warnings)
        self.assertEqual("degraded", result.health["status"])
        self.assertEqual("network: provider network failure", result.health["reason"])
        self.assertEqual((), result.normalized_items)
        self.assertEqual((), result.claims)
        self.assertEqual(
            [
                "get-station-code-by-names",
                "get-station-code-of-citys",
                "get-stations-code-in-city",
            ],
            self._calls(diagnostics),
        )


class _StubStationClient:
    """Fake 12306 client so the suffix-retry logic can be tested without a subprocess.

    `_resolve_rail_stations`/its private helper only need an object with a
    `call_tool(name, arguments)` method; they never construct `MCPStdioClient`
    themselves. `tests/fixtures/` is off limits for this book, so these tests
    exercise the resolver directly instead of adding a new fixture-server mode
    (same approach as the direct `AMapStationDistanceEnricher.enrich()` calls
    above).
    """

    def __init__(self, handler):
        self.calls: List[Dict[str, Any]] = []
        self._handler = handler

    def call_tool(self, name, arguments):
        self.calls.append({"name": name, "arguments": dict(arguments)})
        return self._handler(name, dict(arguments))


def _stub_tool_result(payload):
    return {"isError": False, "content": [{"type": "text", "text": json.dumps(payload)}]}


def _stub_station(code, name):
    return {"station_code": code, "station_name": name}


class RailStationSuffixRetryTests(unittest.TestCase):
    """`_resolve_rail_stations` retries once with the administrative suffix stripped."""

    def test_suffixed_city_empty_after_three_layers_retries_stripped_name_and_resolves(self):
        def handler(name, arguments):
            if name == "get-station-code-by-names":
                if arguments["stationNames"] == "厦门|武夷山市":
                    return _stub_tool_result({"厦门": _stub_station("XMX", "厦门")})
                if arguments["stationNames"] == "武夷山":
                    return _stub_tool_result({"武夷山": _stub_station("WYX", "武夷山")})
            elif name == "get-station-code-of-citys" and arguments["citys"] == "武夷山市":
                return _stub_tool_result({})
            elif name == "get-stations-code-in-city" and arguments["city"] == "武夷山市":
                return _stub_tool_result([])
            raise AssertionError("unexpected tool call %s %r" % (name, arguments))

        client = _StubStationClient(handler)
        body: Dict[str, Any] = {"calls": []}
        resolution = _resolve_rail_stations(client, body, "厦门", "武夷山市")

        self.assertEqual("resolved", resolution["status"])
        # The reported query stays the caller's original "武夷山市": it is
        # checked verbatim against the request in rail12306.py's contract
        # guard (`query != request.parameters.get(parameter_name)`), so only
        # the candidates come from the stripped-name retry, not the label.
        self.assertEqual("武夷山市", resolution["endpoints"]["to"]["query"])
        self.assertEqual(
            [{"station_code": "WYX", "station_name": "武夷山"}],
            resolution["endpoints"]["to"]["candidates"],
        )
        self.assertEqual("厦门", resolution["endpoints"]["from"]["query"])
        self.assertEqual(
            [
                "get-station-code-by-names",
                "get-station-code-of-citys",
                "get-stations-code-in-city",
                "get-station-code-by-names",
            ],
            [call["name"] for call in client.calls],
        )
        self.assertEqual("武夷山", client.calls[3]["arguments"]["stationNames"])

    def test_suffixed_city_still_empty_after_stripped_retry_is_no_results_with_six_calls(self):
        def handler(name, arguments):
            if name == "get-station-code-by-names":
                if arguments["stationNames"] == "厦门|武夷山市":
                    return _stub_tool_result({"厦门": _stub_station("XMX", "厦门")})
                if arguments["stationNames"] == "武夷山":
                    return _stub_tool_result({})
            elif name == "get-station-code-of-citys" and arguments["citys"] in ("武夷山市", "武夷山"):
                return _stub_tool_result({})
            elif name == "get-stations-code-in-city" and arguments["city"] in ("武夷山市", "武夷山"):
                return _stub_tool_result([])
            raise AssertionError("unexpected tool call %s %r" % (name, arguments))

        client = _StubStationClient(handler)
        body: Dict[str, Any] = {"calls": []}
        resolution = _resolve_rail_stations(client, body, "厦门", "武夷山市")

        self.assertEqual("no_results", resolution["status"])
        self.assertEqual((), tuple(resolution["endpoints"]["to"]["candidates"]))
        self.assertEqual("武夷山市", resolution["endpoints"]["to"]["query"])
        self.assertEqual(6, len(client.calls))
        self.assertEqual(
            [
                "get-station-code-by-names",
                "get-station-code-of-citys",
                "get-stations-code-in-city",
                "get-station-code-by-names",
                "get-station-code-of-citys",
                "get-stations-code-in-city",
            ],
            [call["name"] for call in client.calls],
        )

    def test_names_without_administrative_suffix_do_not_retry_and_keep_call_count(self):
        def handler(name, arguments):
            if name == "get-station-code-by-names" and arguments["stationNames"] == "未知甲地|未知乙地":
                return _stub_tool_result({})
            if name == "get-station-code-of-citys" and arguments["citys"] == "未知甲地|未知乙地":
                return _stub_tool_result({})
            if name == "get-stations-code-in-city" and arguments["city"] in ("未知甲地", "未知乙地"):
                return _stub_tool_result([])
            raise AssertionError("unexpected tool call %s %r" % (name, arguments))

        client = _StubStationClient(handler)
        body: Dict[str, Any] = {"calls": []}
        resolution = _resolve_rail_stations(client, body, "未知甲地", "未知乙地")

        self.assertEqual("no_results", resolution["status"])
        self.assertEqual("未知甲地", resolution["endpoints"]["from"]["query"])
        self.assertEqual("未知乙地", resolution["endpoints"]["to"]["query"])
        self.assertEqual(4, len(client.calls))
        self.assertEqual(
            [
                "get-station-code-by-names",
                "get-station-code-of-citys",
                "get-stations-code-in-city",
                "get-stations-code-in-city",
            ],
            [call["name"] for call in client.calls],
        )


class ConfigurableStationPoiTransport:
    """Synthetic AMap transport with per-keyword control of both POI passes.

    `stations` maps a station keyword to an optional `"city_pass"` entry
    (`{"location": "lng,lat", "cityname": str}`, used for the AMap
    `city_limit=true` call; omit to mean "AMap found nothing at all for this
    keyword in-city") and an optional `"nationwide_pass"` list of `"lng,lat"`
    strings (used for the `city_limit=false` call; 0, 1, or 2+ entries to
    exercise "not found", "found and within range", and "ambiguous").
    A keyword absent from `stations` behaves as if both passes found
    nothing. Only used by the station-cross-city book's task 2 (邻市距离)
    tests below, which need city-pass/nationwide-pass results to differ per
    candidate in ways `StationAMapFixtureTransport` does not support.
    """

    def __init__(self, *, centre_city, stations):
        self.centre_city = centre_city
        self.stations = stations
        self.requests = []

    def execute(self, provider, request):
        self.requests.append(request)
        if provider != "amap":
            raise AssertionError("station fixture is restricted to amap")
        if request.capability == "geocode":
            body = {
                "status": "1",
                "info": "OK",
                "infocode": "10000",
                "count": "1",
                "api": "geocode-v3",
                "geocodes": [{
                    "formatted_address": self.centre_city,
                    "province": "合成省",
                    "city": self.centre_city,
                    "district": "合成中心区",
                    "adcode": "990001",
                    "location": "100.000000,20.000000",
                }],
            }
            return ProviderEnvelope(200, body, {})
        if request.capability != "poi":
            raise AssertionError("unexpected AMap fixture capability")
        keyword = request.parameters["keywords"]
        spec = self.stations.get(keyword, {})
        pois = []
        if request.parameters.get("city_limit") == "true":
            entry = spec.get("city_pass")
            if entry is not None:
                pois.append(self._poi(keyword, 0, entry["location"], entry["cityname"], "合成区"))
        else:
            for index, location in enumerate(spec.get("nationwide_pass") or ()):
                pois.append(self._poi(keyword, index, location, "异地城市", "异地区"))
        body = {
            "status": "1",
            "info": "OK",
            "infocode": "10000",
            "count": str(len(pois)),
            "api": "poi-v5",
            "page_size": request.parameters["page_size"],
            "page_num": request.parameters["page_num"],
            "pois": pois,
        }
        return ProviderEnvelope(200, body, {})

    @staticmethod
    def _poi(keyword, suffix, location, cityname, adname):
        amap_name = keyword[:-1] + "火车站" if keyword.endswith("站") else keyword + "站"
        return {
            "id": "SYNTHETIC-%s-%d" % (keyword, suffix),
            "name": amap_name,
            "location": location,
            "pname": "合成省",
            "cityname": cityname,
            "adname": adname,
            "address": "合成铁路大道",
            "adcode": "990001",
            "type": "交通设施服务;火车站;火车站",
        }


class RailStationNationwideDistanceTests(unittest.TestCase):
    """`AMapStationDistanceEnricher`'s second, `city_limit=false` POI pass.

    A candidate whose first (city-limited) pass found some POI for its exact
    keyword but rejected it on the city/district check gets one more,
    nationwide try — accepted only within `STATION_MAX_DISTANCE_METERS` of
    the researched city's centre and only when it resolves to one coordinate.
    """

    @staticmethod
    def _resolution(candidate_names):
        return {
            "status": "ambiguous",
            "endpoints": {
                "from": {
                    "query": "邻城",
                    "candidates": [{"station_name": name} for name in candidate_names],
                },
                "to": {
                    "query": "昆明南",
                    "candidates": [{"station_name": "昆明南"}],
                },
            },
        }

    @staticmethod
    def _request(request_id):
        return ProviderRequest(
            request_id=request_id,
            capability="rail",
            parameters={},
            deadline_ms=2000,
            as_of="2026-09-10",
            cache_policy="bypass",
            trace={"stage": "station-nationwide-test"},
        )

    def _from_candidates(self, amap, candidate_names, request_id):
        enricher = RailStationFallbackTests._amap_enricher(amap)
        enriched = enricher.enrich(self._resolution(candidate_names), self._request(request_id))
        candidates = enriched["endpoints"]["from"]["candidates"]
        return {candidate["station_name"]: candidate for candidate in candidates}

    def _nationwide_requests(self, amap, keyword=None):
        return [
            call for call in amap.requests
            if call.capability == "poi"
            and call.parameters.get("city_limit") == "false"
            and (keyword is None or call.parameters.get("keywords") == keyword)
        ]

    def test_same_named_neighboring_station_within_threshold_gains_a_distance(self):
        near_location = "100.200000,20.000000"
        amap = ConfigurableStationPoiTransport(
            centre_city="邻城市",
            stations={
                "邻城甲站": {
                    "city_pass": {"location": "100.001000,20.000000", "cityname": "别处市"},
                    "nationwide_pass": [near_location],
                },
            },
        )
        by_name = self._from_candidates(amap, ["邻城甲站", "邻城乙站"], "nationwide-near")

        expected_distance = haversine_meters(100.0, 20.0, 100.2, 20.0)
        self.assertLess(expected_distance, 80_000)
        self.assertEqual(expected_distance, by_name["邻城甲站"]["distance_meters"])
        self.assertNotIn("distance_meters", by_name["邻城乙站"])
        nationwide = self._nationwide_requests(amap, "邻城甲站")
        self.assertEqual(1, len(nationwide))
        self.assertEqual("false", nationwide[0].parameters["city_limit"])

    def test_same_named_neighboring_station_beyond_threshold_stays_unknown(self):
        far_location = "101.000000,20.000000"
        amap = ConfigurableStationPoiTransport(
            centre_city="邻城市",
            stations={
                "邻城甲站": {
                    "city_pass": {"location": "100.001000,20.000000", "cityname": "别处市"},
                    "nationwide_pass": [far_location],
                },
            },
        )
        by_name = self._from_candidates(amap, ["邻城甲站", "邻城乙站"], "nationwide-far")

        actual_distance = haversine_meters(100.0, 20.0, 101.0, 20.0)
        self.assertGreater(actual_distance, 80_000)
        self.assertNotIn("distance_meters", by_name["邻城甲站"])
        self.assertNotIn("distance_meters", by_name["邻城乙站"])
        self.assertEqual(1, len(self._nationwide_requests(amap, "邻城甲站")))

    def test_nationwide_pass_with_two_distinct_coordinates_stays_unknown(self):
        amap = ConfigurableStationPoiTransport(
            centre_city="邻城市",
            stations={
                "邻城甲站": {
                    "city_pass": {"location": "100.001000,20.000000", "cityname": "别处市"},
                    "nationwide_pass": ["100.100000,20.000000", "100.150000,20.000000"],
                },
            },
        )
        by_name = self._from_candidates(amap, ["邻城甲站", "邻城乙站"], "nationwide-ambiguous")

        self.assertNotIn("distance_meters", by_name["邻城甲站"])
        self.assertEqual(1, len(self._nationwide_requests(amap, "邻城甲站")))

    def test_candidate_resolved_by_first_pass_does_not_trigger_a_nationwide_call(self):
        amap = ConfigurableStationPoiTransport(
            centre_city="邻城市",
            stations={
                "邻城本地站": {
                    "city_pass": {"location": "100.001000,20.000000", "cityname": "邻城市"},
                },
                "邻城异地站": {
                    "city_pass": {"location": "100.002000,20.000000", "cityname": "别处市"},
                    "nationwide_pass": ["100.200000,20.000000"],
                },
            },
        )
        by_name = self._from_candidates(amap, ["邻城本地站", "邻城异地站"], "nationwide-skip-resolved")

        self.assertIn("distance_meters", by_name["邻城本地站"])
        self.assertIn("distance_meters", by_name["邻城异地站"])
        self.assertEqual(0, len(self._nationwide_requests(amap, "邻城本地站")))
        self.assertEqual(1, len(self._nationwide_requests(amap, "邻城异地站")))


if __name__ == "__main__":
    unittest.main()
