from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "plugins" / "china-trip-weaver" / "src"
sys.path.insert(0, str(SRC))

from china_trip_weaver.clock import FixedClock
from china_trip_weaver.contracts import ProviderRequest, canonical_json
from china_trip_weaver.credentials import resolve_credentials
from china_trip_weaver.evidence import EvidenceLedger, make_claim, validate_claim
from china_trip_weaver.mobility import MobilityBackend
from china_trip_weaver.providers import (
    AMapAdapter,
    AnySearchAdapter,
    FlyAIAdapter,
    HostWebAdapter,
    Rail12306Adapter,
    VariFlightAdapter,
)
from china_trip_weaver.providers.base import ProviderContext, ProviderEnvelope, ReplayTransport
from china_trip_weaver.providers.rail12306 import EXPECTED_TOOLS as RAIL_TOOLS
from china_trip_weaver.providers.variflight import EXPECTED_TOOLS as VARIFLIGHT_TOOLS
from china_trip_weaver.validate_trip import SchemaSubsetValidator, load_schema


FIXTURES = ROOT / "tests" / "fixtures" / "providers"
AMAP_SCENARIOS = FIXTURES / "amap" / "scenarios"
COMMON_CASES = {"success", "empty", "auth", "rate_limit", "timeout", "wrong_shape", "malicious"}
ADAPTERS = {
    "host_web": HostWebAdapter,
    "rail12306": Rail12306Adapter,
    "flyai": FlyAIAdapter,
    "amap": AMapAdapter,
    "variflight": VariFlightAdapter,
    "anysearch": AnySearchAdapter,
}
PROVIDER_ENV = {
    "flyai": {"FLYAI_API_KEY": "ctw-canary-flyai-not-real"},
    "amap": {"AMAP_WEBSERVICE_KEY": "ctw-canary-amap-not-real"},
    "variflight": {"VARIFLIGHT_API_KEY": "ctw-canary-variflight-not-real"},
    "anysearch": {"ANYSEARCH_API_KEY": "ctw-canary-anysearch-not-real"},
}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def fixture_paths():
    return sorted(path for path in FIXTURES.glob("*/*.json") if path.name != "manifest.json")


def run_fixture(testcase: unittest.TestCase, path: Path):
    fixture = load(path)
    adapter = ADAPTERS[fixture["provider"]]()
    request = ProviderRequest(**fixture["request"])
    environment = PROVIDER_ENV.get(fixture["provider"], {}) if fixture["credential_state"] == "configured" else {}
    credentials = resolve_credentials(environment, ROOT / ".tmp" / "provider-fixture-no-file")
    transport = ReplayTransport(fixture["transport"], raw_ref=path.relative_to(ROOT).as_posix())
    context = ProviderContext(
        clock=FixedClock.from_iso(fixture["captured_at"]),
        credentials=credentials,
        transport=transport,
    )
    result = adapter.query(request, context)
    expected = fixture["expected"]

    testcase.assertEqual(fixture["provider_version"], result.provider_version)
    testcase.assertEqual(expected["health_status"], result.health["status"])
    testcase.assertEqual(expected["error_class"], result.error_class)
    testcase.assertEqual(expected["item_count"], len(result.normalized_items))
    testcase.assertEqual(expected["transport_calls"], transport.calls)
    testcase.assertEqual(fixture["request"]["capability"], result.capability)
    testcase.assertNotIn("ctw-canary", canonical_json(result.health))

    validator = SchemaSubsetValidator(load_schema())
    refs = expected["schema_refs"]
    testcase.assertEqual(len(refs), len(result.normalized_items))
    claim_ids = {claim["claim_id"] for claim in result.claims}
    for claim in result.claims:
        validate_claim(claim)
        testcase.assertTrue(claim["source_url"].startswith("https://"))
        testcase.assertIn("queried_at", claim)
        testcase.assertIn("status", claim)
        testcase.assertIn("confidence", claim)
    for item, reference in zip(result.normalized_items, refs):
        errors = validator.validate_fragment(reference, item)
        testcase.assertEqual([], [issue.render() for issue in errors])
        testcase.assertTrue(set(item.get("claim_ids", ())).issubset(claim_ids))
        if item.get("price"):
            testcase.assertIn(item["price"]["price_type"], {"live", "reference", "estimate", "verify-on-click", "unknown"})
            testcase.assertIn(item["price"]["claim_id"], claim_ids)
    if expected["sanitized"]:
        encoded = canonical_json({"items": result.normalized_items, "claims": result.claims, "health": result.health})
        testcase.assertNotIn("<script", encoded.lower())
        testcase.assertNotIn("\u001b", encoded)
        testcase.assertNotIn("Authorization:", encoded)
        testcase.assertIn("[REDACTED]", encoded)
    if result.error_class not in (None, "no_results"):
        testcase.assertEqual((), result.normalized_items)
        testcase.assertEqual((), result.claims)


class ProviderCorpusTests(unittest.TestCase):
    def test_manifest_hashes_and_file_set_are_exact(self):
        manifest = load(FIXTURES / "manifest.json")
        listed = {entry["path"] for entry in manifest["files"]}
        actual = {path.relative_to(FIXTURES).as_posix() for path in fixture_paths()}
        self.assertEqual(79, manifest["fixture_count"])
        self.assertEqual(listed, actual)
        for entry in manifest["files"]:
            data = (FIXTURES / entry["path"]).read_bytes()
            self.assertEqual(entry["sha256"], hashlib.sha256(data).hexdigest(), entry["path"])

    def test_every_provider_has_common_failure_matrix(self):
        by_provider = {provider: set() for provider in ADAPTERS}
        for path in fixture_paths():
            fixture = load(path)
            by_provider[fixture["provider"]].add(fixture["case"])
            self.assertFalse(fixture["redacted"])
            self.assertFalse(fixture["contains_personal_data"])
        for provider, cases in by_provider.items():
            self.assertTrue(COMMON_CASES.issubset(cases), "%s missing %s" % (provider, sorted(COMMON_CASES - cases)))
            self.assertGreaterEqual(len(cases), 7)

    def test_fixture_transports_are_not_copy_renames(self):
        by_provider = {provider: {} for provider in ADAPTERS}
        for path in fixture_paths():
            fixture = load(path)
            digest = hashlib.sha256(canonical_json(fixture["transport"]).encode("utf-8")).hexdigest()
            previous = by_provider[fixture["provider"]].get(digest)
            self.assertIsNone(previous, "%s duplicates %s" % (path, previous))
            by_provider[fixture["provider"]][digest] = path

    def test_locked_tool_fingerprints_are_exact(self):
        self.assertEqual(8, len(RAIL_TOOLS))
        self.assertEqual(9, len(VARIFLIGHT_TOOLS))
        self.assertIn("get-station-code-of-citys", RAIL_TOOLS)
        self.assertIn("getTodayDate", VARIFLIGHT_TOOLS)

    def test_rail_success_fixture_preserves_raw_mcp_array_shape(self):
        fixture = load(FIXTURES / "rail12306" / "success.json")
        body = fixture["transport"]["body"]
        self.assertEqual("2025-06-18", body["protocol_version"])
        self.assertEqual(list(RAIL_TOOLS), body["tools"])
        self.assertEqual(["get-station-code-of-citys", "get-tickets"], [call["name"] for call in body["calls"]])
        payload = json.loads(body["calls"][-1]["result"]["content"][0]["text"])
        self.assertIsInstance(payload, list)
        self.assertEqual("G1001", payload[0]["start_train_code"])
        self.assertIn("price", payload[0]["prices"][0])
        self.assertNotIn("kind", body)
        self.assertNotIn("items", body)
        self.assertIn("synthetic 12306 MCP response", fixture["source"])

    def test_rail_non_array_ticket_text_fails_closed(self):
        fixture = load(FIXTURES / "rail12306" / "success.json")
        fixture["transport"]["body"]["calls"][-1]["result"]["content"][0]["text"] = "{}"
        adapter = Rail12306Adapter()
        request = ProviderRequest(**fixture["request"])
        context = ProviderContext(
            clock=FixedClock.from_iso(fixture["captured_at"]),
            credentials=resolve_credentials({}, ROOT / ".tmp" / "provider-fixture-no-file"),
            transport=ReplayTransport(fixture["transport"]),
        )
        result = adapter.query(request, context)
        self.assertEqual("contract_mismatch", result.error_class)
        self.assertEqual("contract_mismatch", result.health["status"])
        self.assertEqual((), result.normalized_items)

    def test_rail_live_price_and_availability_are_claimed(self):
        fixture = load(FIXTURES / "rail12306" / "success.json")
        adapter = Rail12306Adapter()
        request = ProviderRequest(**fixture["request"])
        context = ProviderContext(
            clock=FixedClock.from_iso(fixture["captured_at"]),
            credentials=resolve_credentials({}, ROOT / ".tmp" / "provider-fixture-no-file"),
            transport=ReplayTransport(fixture["transport"]),
        )
        result = adapter.query(request, context)
        self.assertIsNone(result.error_class)
        self.assertEqual(300, result.normalized_items[0]["price"]["amount"])
        self.assertEqual("live", result.normalized_items[0]["price"]["price_type"])
        availability = [claim for claim in result.claims if claim["field_path"] == "/availability"]
        self.assertEqual(1, len(availability))
        self.assertTrue(any(seat["available"] for seat in availability[0]["value"]))

    def test_amap_synthetic_responses_cover_v3_v4_v5_without_credentials(self):
        synthetic_cases = (
            "success", "pagination_page2", "geocode", "walking", "transit",
            "driving", "riding", "api_forbidden",
        )
        for case in synthetic_cases:
            with self.subTest(case=case):
                fixture = load(FIXTURES / "amap" / (case + ".json"))
                self.assertIn("synthetic AMap-shaped response", fixture["source"])
                encoded = canonical_json(fixture)
                self.assertNotIn("AMAP_WEBSERVICE_KEY", encoded)
                self.assertNotIn("?key=", encoded)
        success = load(FIXTURES / "amap" / "success.json")
        self.assertIn("page_size", success["request"]["parameters"])
        self.assertIn("page_num", success["request"]["parameters"])
        self.assertNotIn("offset", success["request"]["parameters"])
        self.assertNotIn("page", success["request"]["parameters"])
        riding = load(FIXTURES / "amap" / "riding.json")["transport"]["body"]
        self.assertEqual(0, riding["errcode"])
        self.assertIsInstance(riding["data"]["paths"][0]["duration"], int)

    def test_flyai_synthetic_responses_distinguish_trial_masks_and_exact_prices(self):
        for case in ("success", "hotel", "version_help"):
            with self.subTest(case=case):
                fixture = load(FIXTURES / "flyai" / (case + ".json"))
                self.assertIn("synthetic keyless FlyAI-shaped response", fixture["source"])
                body = fixture["transport"]["body"]
                self.assertEqual(0, body["status"])
                self.assertEqual(["search-hotel", "search-flight"], body["commands"])
                self.assertIn(body["probe"]["command"], body["commands"])
                encoded = canonical_json(fixture)
                self.assertNotIn("FLYAI_API_KEY", encoded)
                self.assertNotIn("ctw-canary", encoded)
        keyed = load(FIXTURES / "flyai" / "hotel_exact_price.json")
        self.assertIn("synthetic configured-key FlyAI-shaped response", keyed["source"])
        self.assertNotIn("FLYAI_API_KEY", canonical_json(keyed))
        trial = run_fixture_value(FIXTURES / "flyai" / "hotel.json")
        exact = run_fixture_value(FIXTURES / "flyai" / "hotel_exact_price.json")
        self.assertIsNone(trial.normalized_items[0]["price"]["amount"])
        self.assertEqual("verify-on-click", trial.normalized_items[0]["price"]["price_type"])
        self.assertEqual(101.0, exact.normalized_items[0]["price"]["amount"])
        self.assertEqual("live", exact.normalized_items[0]["price"]["price_type"])

    def test_variflight_synthetic_responses_emit_status_and_comfort_claims(self):
        for case, tool in (("success", "searchFlightsByDepArr"), ("comfort", "flightHappinessIndex")):
            with self.subTest(case=case):
                fixture = load(FIXTURES / "variflight" / (case + ".json"))
                self.assertIn("synthetic VariFlight-shaped response", fixture["source"])
                self.assertEqual(tool, fixture["transport"]["body"]["tool"])
                payload = json.loads(fixture["transport"]["body"]["content"][0]["text"])
                self.assertEqual(200, payload["code"])
                self.assertIsInstance(payload["data"], list)
                encoded = canonical_json(fixture)
                self.assertNotIn("VARIFLIGHT_API_KEY", encoded)
                self.assertNotIn("X_VARIFLIGHT_KEY", encoded)
        status = run_fixture_value(FIXTURES / "variflight" / "success.json")
        comfort = run_fixture_value(FIXTURES / "variflight" / "comfort.json")
        self.assertEqual(["/status"], [item["field_path"] for item in status.claims])
        self.assertEqual(["/comfort"], [item["field_path"] for item in comfort.claims])


def _make_fixture_test(path: Path):
    def test(self):
        run_fixture(self, path)
    return test


def run_fixture_value(path: Path):
    fixture = load(path)
    adapter = ADAPTERS[fixture["provider"]]()
    request = ProviderRequest(**fixture["request"])
    environment = PROVIDER_ENV.get(fixture["provider"], {}) if fixture["credential_state"] == "configured" else {}
    credentials = resolve_credentials(environment, ROOT / ".tmp" / "provider-fixture-no-file")
    return adapter.query(
        request,
        ProviderContext(
            clock=FixedClock.from_iso(fixture["captured_at"]),
            credentials=credentials,
            transport=ReplayTransport(fixture["transport"]),
        ),
    )


class AMapScenarioTransport:
    """Replay the multi-call AMap responses stored in a synthetic scenario."""

    def __init__(self, scenario):
        self.entities = {item["ref_id"]: item for item in scenario["entities"]}
        self.calls = 0
        self.capabilities = []

    def execute(self, provider, provider_request):
        if provider != "amap":
            raise AssertionError(provider)
        self.calls += 1
        self.capabilities.append(provider_request.capability)
        if provider_request.capability == "poi":
            entity = self.entities[provider_request.parameters["subject_ref"]]
            return ProviderEnvelope(200, {
                "status": "1",
                "info": "OK",
                "infocode": "10000",
                "api": "poi-v5",
                "page_num": provider_request.parameters["page_num"],
                "page_size": provider_request.parameters["page_size"],
                "count": str(len(entity["poi_results"])),
                "pois": entity["poi_results"],
            }, {})
        if provider_request.capability == "geocode":
            entity = self.entities[provider_request.parameters["subject_ref"]]
            return ProviderEnvelope(200, {
                "status": "1",
                "info": "OK",
                "infocode": "10000",
                "api": "geocode-v3",
                "count": "1",
                "geocodes": [entity["geocode"]],
            }, {})
        if provider_request.capability == "route":
            mode = provider_request.parameters["travel_mode"]
            api = {
                "walk": "route-walking-v3",
                "transit": "route-transit-v3",
                "drive": "route-driving-v3",
                "ride": "route-riding-v4",
            }[mode]
            path = {"duration": "1800", "distance": "12000"}
            if mode == "ride":
                return ProviderEnvelope(200, {
                    "api": api,
                    "errcode": 0,
                    "errmsg": "OK",
                    "data": {"paths": [path]},
                }, {})
            return ProviderEnvelope(200, {
                "api": api,
                "status": "1",
                "info": "OK",
                "route": {"transits" if mode == "transit" else "paths": [path]},
            }, {})
        raise AssertionError(provider_request.capability)


def amap_scenario_candidates(scenario):
    clock = FixedClock.from_iso("2026-09-04T00:00:00+08:00")
    claims = []
    pois = []
    for entity in scenario["entities"]:
        opening_date = entity.get("opening_date")
        field_path = "/opening_windows/0" if opening_date else "/name"
        claim = make_claim(
            subject_ref=entity["ref_id"],
            field_path=field_path,
            value="official dated opening information" if opening_date else entity["name"],
            source_url="https://example.invalid/official/" + entity["ref_id"],
            provider="official-web",
            status="verified",
            confidence=0.9,
            mode="static",
            clock=clock,
        )
        windows = []
        if opening_date:
            windows.append({
                "start_at": opening_date + "T09:00:00+08:00",
                "end_at": opening_date + "T17:00:00+08:00",
                "status": "verified",
                "claim_id": claim["claim_id"],
            })
        claims.append(claim)
        pois.append({
            "poi_id": entity["ref_id"],
            "name": entity["name"],
            "city": entity["city"],
            "category": "synthetic-test-place",
            "coordinates": None,
            "recommended_duration_minutes": 60,
            "opening_windows": windows,
            "price": None,
            "deep_links": ["https://example.invalid/place/" + entity["ref_id"]],
            "claim_ids": [claim["claim_id"]],
        })
    return {
        "candidates_version": "1.0.0",
        "pois": pois,
        "lodgings": [],
        "claims": claims,
        "unknowns": [],
    }


def run_amap_scenario(case):
    scenario = load(AMAP_SCENARIOS / (case + ".json"))
    candidates = amap_scenario_candidates(scenario)
    transport = AMapScenarioTransport(scenario)
    backend = MobilityBackend(
        "live",
        resolve_credentials(PROVIDER_ENV["amap"], ROOT / ".tmp" / "provider-fixture-no-file"),
        transport,
    )
    result = backend.resolve(
        candidates,
        FixedClock.from_iso("2026-09-04T00:00:00+08:00"),
        ("walking",),
    )
    return scenario, candidates, result


class AMapIdentityAndSemanticTests(unittest.TestCase):
    def test_amap_scenario_manifest_locks_five_synthetic_fixtures(self):
        manifest = load(AMAP_SCENARIOS / "manifest.json")
        actual = {
            path.name for path in AMAP_SCENARIOS.glob("*.json")
            if path.name != "manifest.json"
        }
        self.assertEqual(5, manifest["fixture_count"])
        self.assertEqual({entry["path"] for entry in manifest["files"]}, actual)
        for entry in manifest["files"]:
            data = (AMAP_SCENARIOS / entry["path"]).read_bytes()
            self.assertEqual(entry["sha256"], hashlib.sha256(data).hexdigest())
            fixture = json.loads(data)
            self.assertIn("locally generated synthetic AMap-shaped response", fixture["source"])
            self.assertNotIn("AMAP_WEBSERVICE_KEY", canonical_json(fixture))

    def test_g4_business_and_official_claims_both_survive_as_conflict(self):
        scenario = load(AMAP_SCENARIOS / "g4_business_conflict.json")
        entity = scenario["entities"][0]
        result = AMapAdapter().query(
            ProviderRequest(
                request_id="g4-business-conflict",
                capability="poi",
                parameters={
                    "subject_ref": entity["ref_id"],
                    "city": entity["city"],
                    "keywords": entity["name"],
                    "page_size": 2,
                    "page_num": 1,
                },
                deadline_ms=1000,
                as_of="2026-09-04",
                cache_policy="bypass",
                trace={"stage": "g4"},
            ),
            ProviderContext(
                FixedClock.from_iso("2026-09-04T00:00:00+08:00"),
                resolve_credentials(PROVIDER_ENV["amap"], ROOT / ".tmp" / "provider-fixture-no-file"),
                ReplayTransport({
                    "kind": "response",
                    "status_code": 200,
                    "headers": {},
                    "body": {
                        "status": "1",
                        "info": "OK",
                        "api": "poi-v5",
                        "page_num": 1,
                        "page_size": 2,
                        "pois": entity["poi_results"],
                    },
                }),
            ),
        )
        identity = next(claim for claim in result.claims if claim["field_path"] == "/provider_identity")
        self.assertEqual({
            "provider_poi_id", "matched_name", "formatted_address", "district",
            "adcode", "type", "business",
        }, set(identity["value"]))
        self.assertIsNone(result.normalized_items[0]["coordinates"])
        business = next(claim for claim in result.claims if claim["field_path"] == "/business")
        official = make_claim(
            subject_ref=entity["ref_id"],
            field_path="/business",
            value=scenario["official_business"],
            source_url="https://example.invalid/official/g4",
            provider="official-web",
            status="verified",
            confidence=0.9,
            mode="static",
            clock=FixedClock.from_iso("2026-09-04T00:00:00+08:00"),
        )
        ledger = EvidenceLedger((official, business))
        conflicts = ledger.claims()
        self.assertEqual(2, len(conflicts))
        self.assertEqual({"conflict"}, {claim["status"] for claim in conflicts})

        mobility_transport = AMapScenarioTransport(scenario)
        mobility = MobilityBackend(
            "live",
            resolve_credentials(PROVIDER_ENV["amap"], ROOT / ".tmp" / "provider-fixture-no-file"),
            mobility_transport,
        ).resolve(
            amap_scenario_candidates(scenario),
            FixedClock.from_iso("2026-09-04T00:00:00+08:00"),
            ("walking",),
        )
        mobility_business = next(
            claim for claim in mobility.claims if claim["field_path"] == "/business"
        )
        self.assertEqual("conflict", mobility_business["status"])
        self.assertIn("business_conflict", mobility.warnings)

    def test_same_city_isolated_coordinate_downgrades_its_claims(self):
        _, _, result = run_amap_scenario("semantic_same_city_outlier")
        self.assertIn("semantic_outlier", result.warnings)
        self.assertEqual("ready", result.health["status"])
        self.assertTrue(result.cells)
        self.assertTrue(any("semantic_outlier:same_city:poi-outlier" == item for item in result.warnings))
        outlier = next(item for item in result.locations if item.ref_id == "poi-outlier")
        statuses = {
            claim["status"] for claim in result.claims
            if claim["claim_id"] in outlier.claim_ids
        }
        self.assertNotIn("verified", statuses)
        self.assertIn("partial", statuses)

    def test_distinct_entities_at_identical_coordinate_are_conflicts(self):
        _, _, result = run_amap_scenario("semantic_duplicate_coordinates")
        self.assertIn("semantic_outlier", result.warnings)
        self.assertEqual("ready", result.health["status"])
        self.assertTrue(result.cells)
        self.assertTrue(any("semantic_outlier:duplicate_coordinates:" in item for item in result.warnings))
        implicated = {
            claim_id for location in result.locations for claim_id in location.claim_ids
        }
        self.assertEqual(
            {"conflict"},
            {claim["status"] for claim in result.claims if claim["claim_id"] in implicated},
        )

    def test_same_day_adjacent_pois_over_fifty_km_emit_warning_and_downgrade(self):
        _, _, result = run_amap_scenario("semantic_same_day_far")
        self.assertIn("semantic_outlier", result.warnings)
        self.assertEqual("ready", result.health["status"])
        self.assertTrue(result.cells)
        self.assertTrue(any("semantic_outlier:same_day_adjacent:" in item for item in result.warnings))
        implicated = {
            claim_id for location in result.locations for claim_id in location.claim_ids
        }
        self.assertNotIn(
            "verified",
            {claim["status"] for claim in result.claims if claim["claim_id"] in implicated},
        )


for _path in fixture_paths():
    _fixture = load(_path)
    _name = "test_fixture_%s_%s" % (_fixture["provider"], _fixture["case"])
    setattr(ProviderCorpusTests, _name, _make_fixture_test(_path))


if __name__ == "__main__":
    unittest.main()
