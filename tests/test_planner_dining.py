from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "plugins" / "china-trip-weaver" / "src"
sys.path.insert(0, str(SRC))

from china_trip_weaver.clock import FixedClock
from china_trip_weaver.mobility import MobilityBackend
from china_trip_weaver.planning import _apply_dining_health, _plan_dining, plan_trip, RailBackend
from china_trip_weaver.providers.base import ProviderEnvelope
from china_trip_weaver.render import validate_html
from china_trip_weaver.validate_trip import validate_trip

from tests.test_amap_live import ScriptedAmapTransport, credentials as amap_credentials
from tests.test_planner_weather import _candidates, _request

FIXED_NOW = "2026-09-04T00:00:00+08:00"
DINING_FIXTURE = ROOT / "tests" / "fixtures" / "providers" / "amap" / "around_dining.json"
# Far outside the weather forecast horizon (today+3d), so _plan_weather never touches the
# transport and only _plan_dining's poi_around calls need to be scripted.
FAR_DATES = ("2026-12-05", "2026-12-06")


def dining_body(pois: Any = None) -> Mapping[str, Any]:
    base = json.loads(DINING_FIXTURE.read_text(encoding="utf-8"))
    body = copy.deepcopy(base["transport"]["body"])
    if pois is not None:
        body["pois"] = pois
        body["count"] = str(len(pois))
    return body


def empty_dining_body() -> Mapping[str, Any]:
    return {"api": "around-v5", "status": "1", "info": "OK", "count": "0", "page_num": 1, "page_size": 10, "pois": []}


def rejected_dining_body() -> Mapping[str, Any]:
    return {"api": "around-v5", "status": "0", "info": "SYNTHETIC_REJECTED", "page_num": 1, "page_size": 10, "pois": []}


class DiningScriptedTransport(ScriptedAmapTransport):
    """Extends the plain mobility scripted transport with a scriptable ``poi_around`` capability."""

    def __init__(self, body: Mapping[str, Any]) -> None:
        super().__init__()
        self._body = body
        self.dining_calls = 0
        self.dining_locations: List[str] = []
        self.dining_keywords: List[str] = []

    def execute(self, provider, provider_request):
        if provider_request.capability != "poi_around":
            return super().execute(provider, provider_request)
        if provider != "amap":
            raise AssertionError(provider)
        self.calls += 1
        self.dining_calls += 1
        self.dining_locations.append(provider_request.parameters["location"])
        self.dining_keywords.append(provider_request.parameters["keywords"])
        return ProviderEnvelope(200, self._body, {})


def _poi(poi_id: str, name: str, lng: float, lat: float) -> Dict[str, Any]:
    return {"poi_id": poi_id, "name": name, "coordinates": {"gcj02": {"lng": lng, "lat": lat}}}


def _poi_no_coordinates(poi_id: str, name: str) -> Dict[str, Any]:
    return {"poi_id": poi_id, "name": name, "coordinates": None}


def _lodging(lodging_id: str, name: str, lng: float, lat: float) -> Dict[str, Any]:
    return {"lodging_id": lodging_id, "name": name, "coordinates": {"gcj02": {"lng": lng, "lat": lat}}}


def _meal_slot(slot_id: str, meal_type: str, ref_id: str) -> Dict[str, Any]:
    title = {"lunch": "午餐（地点待定）", "dinner": "晚餐（地点待定）"}[meal_type]
    return {"slot_id": slot_id, "kind": "meal", "title": title, "ref_id": ref_id, "start_at": "2026-09-05T12:00:00+08:00"}


def _poi_slot(slot_id: str, ref_id: str) -> Dict[str, Any]:
    return {"slot_id": slot_id, "kind": "poi", "title": "占位游览", "ref_id": ref_id, "start_at": "2026-09-05T09:00:00+08:00"}


def _day(date: str, slots: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    return {"day_id": "day-1", "date": date, "city": "示例市", "slots": list(slots)}


def _live_backend(body: Mapping[str, Any]) -> Any:
    transport = DiningScriptedTransport(body)
    return MobilityBackend("live", amap_credentials(), transport), transport


class PlanDiningLiveTripTests(unittest.TestCase):
    """Full plan_trip() runs: a live AMap mobility backend feeds the new dining stage."""

    def setUp(self) -> None:
        self.clock = FixedClock.from_iso(FIXED_NOW)
        self.rail = RailBackend.from_spec("off", ROOT)

    def _plan(self, request: Mapping[str, Any], candidates: Mapping[str, Any], body: Mapping[str, Any]):
        backend, transport = _live_backend(body)
        result = plan_trip(request, candidates, self.clock, self.rail, backend)
        return result, transport

    def test_full_plan_attaches_three_dining_options_per_meal_slot(self):
        request = _request(FAR_DATES)
        candidates = _candidates(FAR_DATES)
        result, transport = self._plan(request, candidates, body=dining_body())

        meal_slots = [
            slot for day in result.trip["days"] for slot in day["slots"] if slot["kind"] == "meal"
        ]
        self.assertEqual(4, len(meal_slots))
        for slot in meal_slots:
            self.assertIsNotNone(slot["dining"])
            self.assertEqual(3, len(slot["dining"]["options"]))
            expected_keys = {"queried_at", "anchor_ref", "anchor_name", "radius_m", "search_url", "options"}
            self.assertEqual(expected_keys, set(slot["dining"]))
            self.assertEqual(1500, slot["dining"]["radius_m"])

        # Day 2's lunch and dinner both anchor to the day's only POI: same cache key, one query.
        self.assertEqual(3, transport.dining_calls)
        dining_business_calls = [item for item in result.business_calls if item.startswith("dining@")]
        self.assertEqual(3, len(dining_business_calls))

        dining_claims = [
            claim for claim in result.trip["claims"]
            if claim["field_path"] == "/provider_identity" and claim["subject_ref"] in {s["slot_id"] for s in meal_slots}
        ]
        self.assertEqual(12, len(dining_claims))
        self.assertEqual(len({claim["claim_id"] for claim in result.trip["claims"]}), len(result.trip["claims"]))

        report = validate_trip(result.trip)
        self.assertTrue(report.ok, [item.render() for item in report.errors])
        html_report = validate_html(result.html, result.trip)
        self.assertTrue(html_report.ok, [item.render() for item in html_report.errors])

        amap_health = next(item for item in result.trip["provider_health"] if item["provider"] == "amap")
        self.assertIn("poi_around", amap_health["capabilities"])
        self.assertIn("; dining=3 queried, 0 unknown", amap_health["reason"])

    def test_avoid_preference_filters_out_matching_options(self):
        request = _request(FAR_DATES)
        request["dining_preferences"] = {"cuisine": None, "avoid": ["火锅"]}
        candidates = _candidates(FAR_DATES)
        result, _transport = self._plan(request, candidates, body=dining_body())

        meal_slots = [slot for day in result.trip["days"] for slot in day["slots"] if slot["kind"] == "meal"]
        for slot in meal_slots:
            for option in slot["dining"]["options"]:
                haystack = " ".join(filter(None, [option["name"], option["cuisine"], option["tag"]]))
                self.assertNotIn("火锅", haystack)


class PlanDiningUnitTests(unittest.TestCase):
    """Unit-level coverage of ``_plan_dining``, independent of the full scheduling pipeline."""

    def setUp(self) -> None:
        self.clock = FixedClock.from_iso(FIXED_NOW)

    def test_avoid_preference_reverse_verification_without_filter_includes_the_avoided_place(self):
        """Sanity check for the avoid-filter test above: without ``avoid``, 火锅 IS selected."""

        day = _day("2026-09-05", [_poi_slot("slot-poi-1", "poi-1"), _meal_slot("slot-dinner", "dinner", None)])
        pois = [_poi("poi-1", "外滩", 121.0, 31.0)]
        backend, _transport = _live_backend(dining_body())
        _claims, unknowns, _calls, _health = _plan_dining(
            [day], pois, [], {}, backend, self.clock, FIXED_NOW,
        )
        self.assertEqual([], unknowns)
        names_and_tags = " ".join(
            " ".join(filter(None, [o["name"], o["cuisine"], o["tag"]])) for o in day["slots"][1]["dining"]["options"]
        )
        self.assertIn("火锅", names_and_tags)

    def test_mobility_off_adds_no_dining_key_and_no_unknown(self):
        day = _day("2026-09-05", [_poi_slot("slot-poi-1", "poi-1"), _meal_slot("slot-dinner", "dinner", None)])
        pois = [_poi("poi-1", "外滩", 121.0, 31.0)]
        backend = MobilityBackend.from_spec("off", ROOT)
        claims, unknowns, business_calls, health = _plan_dining(
            [day], pois, [], {}, backend, self.clock, FIXED_NOW,
        )
        self.assertEqual([], claims)
        self.assertEqual([], unknowns)
        self.assertEqual((), business_calls)
        self.assertEqual({"queried": 0, "unknown": 0}, health)
        self.assertNotIn("dining", day["slots"][1])

    def test_no_coordinates_anywhere_is_a_typed_unknown(self):
        day = _day("2026-09-05", [_poi_slot("slot-poi-1", "poi-1"), _meal_slot("slot-dinner", "dinner", None)])
        pois = [_poi_no_coordinates("poi-1", "外滩")]
        backend, transport = _live_backend(dining_body())
        claims, unknowns, business_calls, health = _plan_dining(
            [day], pois, [], {}, backend, self.clock, FIXED_NOW,
        )
        self.assertEqual([], claims)
        self.assertEqual(0, transport.dining_calls)
        self.assertEqual((), business_calls)
        self.assertEqual({"queried": 0, "unknown": 1}, health)
        self.assertIsNone(day["slots"][1]["dining"])
        self.assertEqual(1, len(unknowns))
        self.assertEqual("/days/0/slots/1/dining", unknowns[0]["field_path"])
        self.assertEqual("dining_no_anchor", unknowns[0]["reason"])
        self.assertEqual("amap", unknowns[0]["provider"])
        self.assertIsNone(unknowns[0]["claim_id"])

    def test_two_meals_sharing_an_anchor_query_once_and_health_reports_it(self):
        # A meal slot is never its own anchor (dining.py never treats "meal" kind as anchorable),
        # so both meals share the one POI slot placed ahead of them as their nearest backward anchor.
        anchor_slot = _poi_slot("slot-poi-1", "poi-1")
        lunch = _meal_slot("slot-lunch", "lunch", None)
        dinner = _meal_slot("slot-dinner", "dinner", None)
        day = _day("2026-09-05", [anchor_slot, lunch, dinner])
        pois = [_poi("poi-1", "外滩", 121.0, 31.0)]
        backend, transport = _live_backend(dining_body())
        claims, unknowns, business_calls, health = _plan_dining(
            [day], pois, [], {}, backend, self.clock, FIXED_NOW,
        )
        self.assertEqual(1, transport.dining_calls)
        self.assertEqual(("dining@slot-lunch",), business_calls)
        self.assertEqual({"queried": 1, "unknown": 0}, health)
        self.assertEqual([], unknowns)
        # Both slots got the same 3 restaurants, but each slot's claims are its own (no duplicate ids).
        self.assertEqual(6, len(claims))
        self.assertEqual(len({c["claim_id"] for c in claims}), len(claims))
        lunch_subjects = {c["subject_ref"] for c in claims if c["subject_ref"] == "slot-lunch"}
        dinner_subjects = {c["subject_ref"] for c in claims if c["subject_ref"] == "slot-dinner"}
        self.assertEqual({"slot-lunch"}, lunch_subjects)
        self.assertEqual({"slot-dinner"}, dinner_subjects)
        self.assertEqual(
            [o["name"] for o in day["slots"][1]["dining"]["options"]],
            [o["name"] for o in day["slots"][2]["dining"]["options"]],
        )
        self.assertNotEqual(
            [o["claim_id"] for o in day["slots"][1]["dining"]["options"]],
            [o["claim_id"] for o in day["slots"][2]["dining"]["options"]],
        )

    def test_no_results_is_a_typed_unknown(self):
        day = _day("2026-09-05", [_poi_slot("slot-poi-1", "poi-1"), _meal_slot("slot-dinner", "dinner", None)])
        pois = [_poi("poi-1", "外滩", 121.0, 31.0)]
        backend, _transport = _live_backend(empty_dining_body())
        claims, unknowns, _calls, health = _plan_dining(
            [day], pois, [], {}, backend, self.clock, FIXED_NOW,
        )
        self.assertEqual([], claims)
        self.assertEqual({"queried": 1, "unknown": 1}, health)
        self.assertIsNone(day["slots"][1]["dining"])
        self.assertEqual("dining_no_results", unknowns[0]["reason"])

    def test_provider_error_is_a_typed_unknown(self):
        day = _day("2026-09-05", [_poi_slot("slot-poi-1", "poi-1"), _meal_slot("slot-dinner", "dinner", None)])
        pois = [_poi("poi-1", "外滩", 121.0, 31.0)]
        backend, _transport = _live_backend(rejected_dining_body())
        claims, unknowns, _calls, health = _plan_dining(
            [day], pois, [], {}, backend, self.clock, FIXED_NOW,
        )
        self.assertEqual([], claims)
        self.assertEqual({"queried": 1, "unknown": 1}, health)
        self.assertIsNone(day["slots"][1]["dining"])
        self.assertEqual("dining_provider_error:forbidden", unknowns[0]["reason"])

    def test_cuisine_preference_is_forwarded_as_the_search_keyword(self):
        day = _day("2026-09-05", [_poi_slot("slot-poi-1", "poi-1"), _meal_slot("slot-dinner", "dinner", None)])
        pois = [_poi("poi-1", "外滩", 121.0, 31.0)]
        backend, transport = _live_backend(dining_body())
        request = {"dining_preferences": {"cuisine": "闽菜", "avoid": []}}
        _plan_dining([day], pois, [], request, backend, self.clock, FIXED_NOW)
        self.assertEqual(["闽菜"], transport.dining_keywords)

    def test_lodging_anchor_is_used_when_no_poi_slot_is_nearer(self):
        dinner = _meal_slot("slot-dinner", "dinner", None)
        day = _day("2026-09-05", [dinner])
        lodgings = [_lodging("lodging-1", "示例酒店", 121.0, 31.0)]
        backend, transport = _live_backend(dining_body())
        # anchor_for needs a checkin/checkout/rest/lodging-kind slot to find the lodging by ref_id.
        checkin = {"slot_id": "slot-checkin", "kind": "checkin", "title": "入住", "ref_id": "lodging-1", "start_at": "2026-09-05T15:00:00+08:00"}
        day["slots"] = [checkin, dinner]
        claims, unknowns, _calls, _health = _plan_dining(
            [day], [], lodgings, {}, backend, self.clock, FIXED_NOW,
        )
        self.assertEqual([], unknowns)
        self.assertEqual("lodging-1", day["slots"][1]["dining"]["anchor_ref"])
        self.assertEqual("示例酒店", day["slots"][1]["dining"]["anchor_name"])
        self.assertEqual(1, transport.dining_calls)
        self.assertEqual(3, len(claims))


class ApplyDiningHealthTests(unittest.TestCase):
    """Direct coverage of the ``_apply_dining_health`` reason/capabilities formatting."""

    def test_no_op_when_nothing_was_queried(self):
        combined = {"capabilities": ["poi"], "reason": "base"}
        result = _apply_dining_health(combined, {"queried": 0, "unknown": 0})
        self.assertIs(combined, result)
        self.assertEqual(["poi"], result["capabilities"])
        self.assertEqual("base", result["reason"])

    def test_adds_capability_and_reason_suffix(self):
        combined = {"capabilities": ["poi"], "reason": "base"}
        result = _apply_dining_health(combined, {"queried": 2, "unknown": 1})
        self.assertEqual(["poi", "poi_around"], result["capabilities"])
        self.assertEqual("base; dining=2 queried, 1 unknown", result["reason"])

    def test_none_dining_health_is_a_no_op(self):
        combined = {"capabilities": [], "reason": "base"}
        result = _apply_dining_health(combined, None)
        self.assertEqual("base", result["reason"])


if __name__ == "__main__":
    unittest.main()
