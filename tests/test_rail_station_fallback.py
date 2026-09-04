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
from china_trip_weaver.providers.base import ProviderContext
from china_trip_weaver.providers.mcp_stdio import EXPECTED_12306_TOOLS, RailMCPStdioTransport
from china_trip_weaver.providers.rail12306 import Rail12306Adapter


SERVER = ROOT / "tests" / "fixtures" / "mcp_stdio_server.py"
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


class RailStationFallbackTests(unittest.TestCase):
    def _query(self, mode, from_name, to_name):
        credentials = resolve_credentials({}, ROOT / ".tmp" / "rail-station-fallback-no-credentials")
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            transport = RailMCPStdioTransport(
                cache_dir=Path(temporary) / "npm-cache",
                credentials=credentials,
                command=(sys.executable, str(SERVER), mode),
                cwd=ROOT,
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
        result, diagnostics = self._query("station-ambiguous", "多站城", "昆明南")
        self.assertEqual("ambiguous", result.error_class)
        self.assertEqual("ready", result.health["status"])
        self.assertIn("ambiguous", result.health["reason"])
        self.assertNotIn("contract_mismatch", result.health["reason"])
        from_candidates = [item for item in result.normalized_items if item["resolution_for"] == "from"]
        self.assertEqual(["BBX", "AAX"], [item["station_code"] for item in from_candidates])
        self.assertEqual([1000, 8000], [item["distance_meters"] for item in from_candidates])
        self.assertNotIn("get-tickets", self._calls(diagnostics))

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


if __name__ == "__main__":
    unittest.main()
