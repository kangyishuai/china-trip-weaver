"""AMap infocode/errcode classification: one bad request must not stop the run.

lbs.amap.com/api/webservice/guide/tools/info documents ``status=0`` responses
with an ``infocode`` (``errcode`` for the v4 riding endpoint) that distinguish
Key/permission failures from a single request's own parameters or content
being rejected, and from the AMap engine itself failing. Only the Key/
permission bucket is fatal to a multi-entity run.
"""

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
from china_trip_weaver.mobility import MobilityBackend
from china_trip_weaver.providers.amap import AMapAdapter
from china_trip_weaver.providers.base import ProviderContext, ProviderEnvelope, ReplayTransport

from tests.test_amap_live import ScriptedAmapTransport, credentials, request as amap_request


FIXED_NOW = "2026-09-03T12:00:00+08:00"
E2E = ROOT / "tests" / "fixtures" / "e2e" / "beijing-shanghai-3d"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def two_poi_geocode_candidates():
    """Two of the e2e demo's real POI entities, both still missing coordinates.

    Reuses ``tests/fixtures/e2e/beijing-shanghai-3d/candidates.json`` (already
    proven, via ``test_live_plan_reaches_matrix_ready_and_publishes_coordinates``
    in test_amap_live.py, to resolve cleanly under ``ScriptedAmapTransport``)
    instead of hand-building a new candidates document from scratch.
    """

    source = load(E2E / "candidates.json")
    by_id = {poi["poi_id"]: copy.deepcopy(poi) for poi in source["pois"]}
    # "poi-bjs-bund" sorts before "poi-bjs-museum" in MobilityBackend's
    # ref_id-ordered entity walk, so making it the failing one exercises the
    # "does a failure on the FIRST entity still let a LATER one resolve" path.
    failing = by_id["poi-bjs-bund"]
    succeeding = by_id["poi-bjs-museum"]
    entity_refs = {failing["poi_id"], succeeding["poi_id"]}
    return {
        "candidates_version": source["candidates_version"],
        "pois": [failing, succeeding],
        "lodgings": [],
        "claims": [
            copy.deepcopy(claim) for claim in source["claims"]
            if claim["subject_ref"] in entity_refs
        ],
        "unknowns": [
            copy.deepcopy(item) for item in source["unknowns"]
            if item["field_path"] in ("/pois/0/coordinates", "/pois/1/coordinates")
        ],
    }


class _EngineErrorOnOneGeocodeTransport:
    """Delegates to ``ScriptedAmapTransport``, except one ref_id's geocode call
    returns AMap's real single-request engine failure (infocode 30001,
    ``ENGINE_RESPONSE_DATA_ERROR``) instead of a normal coordinate."""

    def __init__(self, failing_ref_id: str) -> None:
        self._inner = ScriptedAmapTransport()
        self._failing_ref_id = failing_ref_id
        self.calls = 0

    def execute(self, provider, provider_request):
        self.calls += 1
        if (
            provider == "amap"
            and provider_request.capability == "geocode"
            and provider_request.parameters.get("subject_ref") == self._failing_ref_id
        ):
            return ProviderEnvelope(200, {
                "status": "0",
                "info": "ENGINE_RESPONSE_DATA_ERROR",
                "infocode": "30001",
                "api": "geocode-v3",
            }, {})
        return self._inner.execute(provider, provider_request)


class EngineErrorDoesNotStopOtherEntitiesTests(unittest.TestCase):
    """Task 0's red->green test: a single-request engine error on one entity's
    geocode call must not stop the rest of the run, and must not be reported
    as ``forbidden`` (AMap's real production observation: a 30001 on one real
    lodging's geocode call left every later entity in the same Trip unqueried,
    2026-09-18)."""

    def test_engine_error_on_one_geocode_does_not_block_the_other_entity(self):
        candidates = two_poi_geocode_candidates()
        transport = _EngineErrorOnOneGeocodeTransport("poi-bjs-bund")
        result = MobilityBackend("live", credentials(), transport).resolve(
            candidates, FixedClock.from_iso(FIXED_NOW), ("walking",),
        )

        self.assertEqual(
            ("poi-bjs-museum",), tuple(item.ref_id for item in result.locations),
        )
        self.assertTrue(any(
            warning.startswith("invalid_request:poi-bjs-bund:geocode_lookup:")
            for warning in result.warnings
        ), result.warnings)
        self.assertNotEqual("forbidden", result.health["status"])


def _status_failure_body(api: str, infocode, info: str):
    body = {"status": "0", "info": info, "api": api}
    if infocode is not None:
        body["infocode"] = infocode
    return body


def _riding_failure_body(errcode, errmsg: str):
    return {"api": "route-riding-v4", "errcode": errcode, "errmsg": errmsg}


def _amap_result(capability: str, parameters, body):
    transport = ReplayTransport({"kind": "response", "status_code": 200, "body": body, "headers": {}})
    context = ProviderContext(FixedClock.from_iso(FIXED_NOW), credentials(), transport)
    return AMapAdapter().query(amap_request(capability, parameters), context)


GEOCODE_PARAMETERS = {"subject_ref": "case-x", "address": "上海市示例区示例地址100号", "city": "上海"}
POI_PARAMETERS = {"subject_ref": "case-x", "keywords": "示例", "city": "上海", "page_size": 1, "page_num": 1}
ROUTE_PARAMETERS = {
    "from_ref": "poi-a", "to_ref": "poi-b",
    "origin": "121.000000,31.000000", "destination": "121.100000,31.100000",
    "city": "上海", "destination_city": "上海", "travel_mode": "walk",
}
RIDING_PARAMETERS = dict(ROUTE_PARAMETERS, travel_mode="ride")


class StatusInfocodeClassificationTests(unittest.TestCase):
    """``status=0`` + ``infocode`` (poi-v5/around-v5/geocode-v3/route-*-v3)."""

    CASES = (
        # (case, api, parameters, infocode, info, expected_error_class)
        ("engine_error_30001", "geocode-v3", GEOCODE_PARAMETERS, "30001", "ENGINE_RESPONSE_DATA_ERROR", "invalid_request"),
        ("engine_error_32000_other_3_prefix", "geocode-v3", GEOCODE_PARAMETERS, "32000", "ENGINE_OTHER_ERROR", "invalid_request"),
        ("invalid_params_20000", "poi-v5", POI_PARAMETERS, "20000", "INVALID_PARAMS", "invalid_request"),
        ("invalid_params_20800", "poi-v5", POI_PARAMETERS, "20800", "GEOCODE_ENGINE_ERROR", "invalid_request"),
        ("access_too_frequent_10004", "geocode-v3", GEOCODE_PARAMETERS, "10004", "ACCESS_TOO_FREQUENT", "rate_limited"),
        ("daily_query_over_limit_40003", "geocode-v3", GEOCODE_PARAMETERS, "40003", "IP_DAILY_QUERY_OVER_LIMIT", "rate_limited"),
        ("server_busy_10016", "route-walking-v3", ROUTE_PARAMETERS, "10016", "SERVER_IS_BUSY", "upstream_5xx"),
        ("gateway_timeout_10017", "route-walking-v3", ROUTE_PARAMETERS, "10017", "GATEWAY_TIMEOUT", "upstream_5xx"),
        ("legacy_forbidden_10001", "geocode-v3", GEOCODE_PARAMETERS, "10001", "INVALID_USER_KEY", "forbidden"),
        ("legacy_forbidden_10002_just_below_rate_limited_cluster", "geocode-v3", GEOCODE_PARAMETERS, "10002", "SERVICE_NOT_AVAILABLE", "forbidden"),
        ("legacy_forbidden_40002_just_below_rate_limited_cluster", "geocode-v3", GEOCODE_PARAMETERS, "40002", "SOME_OTHER_ADJACENT_CODE", "forbidden"),
        ("missing_infocode_defaults_forbidden", "geocode-v3", GEOCODE_PARAMETERS, None, "UNKNOWN_ERROR", "forbidden"),
        ("missing_infocode_but_info_says_limit", "geocode-v3", GEOCODE_PARAMETERS, None, "DAILY_QUERY_OVER_LIMIT", "rate_limited"),
    )

    def test_infocode_is_classified_per_case(self):
        for case, api, parameters, infocode, info, expected in self.CASES:
            with self.subTest(case=case):
                capability = {"poi-v5": "poi", "geocode-v3": "geocode", "route-walking-v3": "route"}[api]
                result = _amap_result(capability, parameters, _status_failure_body(api, infocode, info))
                self.assertEqual(expected, result.error_class)


class RidingErrcodeClassificationTests(unittest.TestCase):
    """The v4 riding endpoint reports failures via ``errcode``, not ``infocode``,
    but must be classified through the same code table."""

    CASES = (
        ("riding_engine_error_30001", 30001, "ENGINE_RESPONSE_DATA_ERROR", "invalid_request"),
        ("riding_access_too_frequent_10004", 10004, "ACCESS_TOO_FREQUENT", "rate_limited"),
        ("riding_server_busy_10016", 10016, "SERVER_IS_BUSY", "upstream_5xx"),
        ("riding_legacy_forbidden_10001", 10001, "INVALID_USER_KEY", "forbidden"),
    )

    def test_errcode_is_classified_per_case(self):
        for case, errcode, errmsg, expected in self.CASES:
            with self.subTest(case=case):
                result = _amap_result("route", RIDING_PARAMETERS, _riding_failure_body(errcode, errmsg))
                self.assertEqual(expected, result.error_class)


if __name__ == "__main__":
    unittest.main()
