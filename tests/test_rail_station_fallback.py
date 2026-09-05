from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "plugins" / "china-trip-weaver" / "src"
sys.path.insert(0, str(SRC))

from china_trip_weaver.clock import FixedClock
from china_trip_weaver.contracts import ProviderRequest
from china_trip_weaver.credentials import resolve_credentials
from china_trip_weaver.providers.base import ProviderContext, ProviderEnvelope, ProviderNetworkError
from china_trip_weaver.providers.mcp_stdio import EXPECTED_12306_TOOLS, RailMCPStdioTransport
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
    ):
        self.centre_available = centre_available
        self.fail = fail
        self.station_points = dict(station_points or {
            "多站城近站": "100.001000,20.000000",
            "多站城远站": "100.010000,20.000000",
        })
        self.station_name_overrides = dict(station_name_overrides or {})
        self.station_city = station_city
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
                    "city": "多站城市",
                    "district": "合成中心区",
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
                    "adname": "合成站区",
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
        amap = StationAMapFixtureTransport(station_city="另一座城市")
        result, diagnostics = self._query(
            "station-ambiguous", "多站城", "昆明南", self._amap_enricher(amap),
        )

        candidates = [
            item for item in result.normalized_items
            if item["resolution_for"] == "from"
        ]
        self.assertEqual(["CCX", "BBX", "AAX"], [
            item["station_code"] for item in candidates
        ])
        self.assertTrue(all("distance_meters" not in item for item in candidates))
        self.assertEqual(["geocode", "poi", "poi", "poi"], [
            request.capability for request in amap.requests
        ])
        self.assertEqual("ambiguous", result.error_class)
        self.assertEqual("ready", result.health["status"])
        self.assertNotIn("get-tickets", self._calls(diagnostics))

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


if __name__ == "__main__":
    unittest.main()
