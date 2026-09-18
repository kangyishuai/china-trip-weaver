from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "plugins" / "china-trip-weaver" / "src"
sys.path.insert(0, str(SRC))

from china_trip_weaver.clock import FixedClock, isoformat_seconds
from china_trip_weaver.contracts import canonical_json
from china_trip_weaver.dining import option_from
from china_trip_weaver.dining_fold import fold_dining_into_journey, fold_dining_into_trip
from china_trip_weaver.evidence import make_claim
from china_trip_weaver.render import render_journey, validate_journey_html
from china_trip_weaver.validate_trip import validate_trip


JOURNEY_DEMO = ROOT / "demo" / "journey-16d"
CLOCK = FixedClock.from_iso("2026-09-22T09:00:00+08:00")
SOURCE_URL = "https://restapi.amap.com/v5/place/around"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def dining_option(key, name, distance, *, clock=CLOCK, rating="4.6", cost="78"):
    claim = make_claim(
        subject_ref="poi-amap-%s" % key,
        field_path="/provider_identity",
        value={
            "provider_poi_id": key.upper(),
            "matched_name": name,
            "formatted_address": "上海市测试路%s号" % key,
            "district": "黄浦区",
            "adcode": "310101",
            "type": "餐饮服务;中餐厅;中餐厅",
            "business": {
                "rating": rating,
                "cost": cost,
                "keytag": "本帮菜",
                "tag": "朋友聚餐",
                "opentime_today": "11:00-22:00",
            },
        },
        source_url=SOURCE_URL,
        provider="amap",
        status="verified",
        confidence=0.9,
        mode="live",
        clock=clock,
        json_path="/pois/0",
    )
    item = {
        "poi_id": "poi-amap-%s" % key,
        "name": name,
        "city": "上海",
        "category": "中餐厅",
        "coordinates": {"gcj02": {"lng": 121.47, "lat": 31.23}},
        "distance_meters": distance,
        "recommended_duration_minutes": None,
        "opening_windows": [],
        "price": None,
        "deep_links": [],
        "claim_ids": [claim["claim_id"]],
    }
    return option_from(item, claim), claim


def options_row(trip, day_index, slot_index, specs, *, clock=CLOCK):
    options = []
    claims = []
    for key, name, distance in specs:
        option, claim = dining_option(key, name, distance, clock=clock)
        options.append(option)
        claims.append(claim)
    day = trip["days"][day_index]
    slot = day["slots"][slot_index]
    row = {
        "trip_id": trip["trip_id"],
        "day_id": day["day_id"],
        "date": day["date"],
        "slot_id": slot["slot_id"],
        "meal_type": "dinner",
        "anchor": {
            "ref_id": "lodging-j16-shanghai-central",
            "name": "上海合成住宿",
            "lng": 121.47,
            "lat": 31.23,
        },
        "radius_m": 1500,
        "keywords": "餐厅",
        "status": "options",
        "options": options,
        "search_url": "https://uri.amap.com/search?keyword=美食&center=121.470000,31.230000",
        "note": None,
    }
    return row, claims


def no_result_row(trip, day_index, slot_index, status):
    day = trip["days"][day_index]
    slot = day["slots"][slot_index]
    return {
        "trip_id": trip["trip_id"],
        "day_id": day["day_id"],
        "date": day["date"],
        "slot_id": slot["slot_id"],
        "meal_type": "dinner",
        "anchor": None,
        "radius_m": 1500,
        "keywords": "餐厅",
        "status": status,
        "options": [],
        "search_url": None,
        "note": status,
    }


def envelope(rows, claims, *, clock=CLOCK):
    return {
        "queried_at": isoformat_seconds(clock),
        "claims": list(claims),
        "slots": list(rows),
    }


class DiningFoldTests(unittest.TestCase):
    def setUp(self):
        self.journey = load(JOURNEY_DEMO / "journey.json")
        self.original_trips = copy.deepcopy(self.journey["trips"])
        self.trip = self.journey["trips"][0]
        self.slot_index = 5
        self.specs = [
            ("jinjiang", "锦江福味", 240),
            ("haiyang", "海阳鲜道", 420),
            ("laofuzhou", "老福州小吃", 680),
        ]

    def _one_slot_result(self, *, clock=CLOCK, specs=None):
        row, claims = options_row(
            self.trip, 0, self.slot_index, specs or self.specs, clock=clock,
        )
        return envelope([row], claims, clock=clock)

    def test_options_row_adds_three_claims_and_updates_only_one_trip(self):
        result = self._one_slot_result()
        patch_result = fold_dining_into_trip(copy.deepcopy(self.trip), result, CLOCK)
        self.assertIsNotNone(patch_result)
        trip = patch_result.trip
        slot = trip["days"][0]["slots"][self.slot_index]

        self.assertEqual(2, trip["revision"]["number"])
        self.assertEqual("dining", patch_result.patch["trigger"])
        self.assertEqual(["day-1"], patch_result.patch["scope"]["day_ids"])
        self.assertEqual([slot["slot_id"]], patch_result.patch["scope"]["affected_refs"])
        self.assertEqual(3, len(slot["dining"]["options"]))
        option_claim_ids = {option["claim_id"] for option in slot["dining"]["options"]}
        copied = [claim for claim in trip["claims"] if claim["claim_id"] in option_claim_ids]
        self.assertEqual(3, len(copied))
        self.assertEqual({slot["slot_id"]}, {claim["subject_ref"] for claim in copied})
        amap_health = next(row for row in trip["provider_health"] if row["provider"] == "amap")
        self.assertIn("poi_around", amap_health["capabilities"])
        self.assertIn("dining=1 slots folded", amap_health["reason"])
        self.assertTrue(validate_trip(trip).ok, validate_trip(trip).errors)

        journey_result = fold_dining_into_journey(
            self.journey, result, self.journey["revision"]["number"], CLOCK,
        )
        self.assertIsNotNone(journey_result)
        self.assertEqual(2, journey_result["revision"]["number"])
        self.assertEqual("system", journey_result["revision"]["created_by"])
        self.assertEqual(
            canonical_json(self.original_trips[1]), canonical_json(journey_result["trips"][1]),
        )
        self.assertEqual(
            canonical_json(self.original_trips[2]), canonical_json(journey_result["trips"][2]),
        )
        rendered = render_journey(journey_result)
        html_report = validate_journey_html(rendered, journey_result)
        self.assertEqual((), html_report.errors, html_report.errors)

    def test_two_meals_sharing_one_query_result_get_their_own_claims(self):
        # ctw dining queries once per distinct anchor, so a lunch and a dinner anchored on
        # the same place share one result; each slot must still own distinct claim ids.
        lunch_row, claims = options_row(self.trip, 0, 1, self.specs)
        dinner_row = copy.deepcopy(lunch_row)
        dinner_row["slot_id"] = self.trip["days"][0]["slots"][self.slot_index]["slot_id"]
        result = envelope([lunch_row, dinner_row], claims)

        folded = fold_dining_into_trip(copy.deepcopy(self.trip), result, CLOCK)
        self.assertIsNotNone(folded)
        trip = folded.trip
        ids = [claim["claim_id"] for claim in trip["claims"]]
        self.assertEqual(len(ids), len(set(ids)))
        claims_by_id = {claim["claim_id"]: claim for claim in trip["claims"]}
        for slot_index in (1, self.slot_index):
            slot = trip["days"][0]["slots"][slot_index]
            self.assertEqual(3, len(slot["dining"]["options"]))
            for option in slot["dining"]["options"]:
                self.assertEqual(slot["slot_id"], claims_by_id[option["claim_id"]]["subject_ref"])
        self.assertTrue(validate_trip(trip).ok)

        later = FixedClock.from_iso("2026-09-23T09:00:00+08:00")
        self.assertIsNone(fold_dining_into_trip(trip, result, later))

    def test_same_envelope_folded_twice_is_noop(self):
        result = self._one_slot_result()
        first = fold_dining_into_trip(copy.deepcopy(self.trip), result, CLOCK)
        self.assertIsNotNone(first)
        self.assertIsNone(fold_dining_into_trip(first.trip, result, CLOCK))

        journey_first = fold_dining_into_journey(self.journey, result, 1, CLOCK)
        self.assertIsNotNone(journey_first)
        self.assertIsNone(fold_dining_into_journey(journey_first, result, 2, CLOCK))

    def test_new_query_replaces_options_removes_old_claims_and_keeps_claim_count(self):
        first = fold_dining_into_trip(
            copy.deepcopy(self.trip), self._one_slot_result(), CLOCK,
        )
        self.assertIsNotNone(first)
        first_slot = first.trip["days"][0]["slots"][self.slot_index]
        old_claim_ids = {option["claim_id"] for option in first_slot["dining"]["options"]}
        claim_count = len(first.trip["claims"])

        later_clock = FixedClock.from_iso("2026-09-22T15:00:00+08:00")
        later_specs = [
            ("jinjiang", "锦江福味", 240),
            ("haiyang", "海阳鲜道", 420),
            ("newplace", "新味小馆", 560),
        ]
        later = self._one_slot_result(clock=later_clock, specs=later_specs)
        second = fold_dining_into_trip(first.trip, later, later_clock)
        self.assertIsNotNone(second)
        slot = second.trip["days"][0]["slots"][self.slot_index]
        self.assertEqual(3, second.trip["revision"]["number"])
        self.assertEqual(isoformat_seconds(later_clock), slot["dining"]["queried_at"])
        self.assertEqual("新味小馆", slot["dining"]["options"][2]["name"])
        self.assertEqual(claim_count, len(second.trip["claims"]))
        self.assertFalse(old_claim_ids.intersection(
            claim["claim_id"] for claim in second.trip["claims"]
        ))
        replace_ops = [
            op for op in second.patch["operations"]
            if op["op"] == "replace" and op["path"] == "/days/0/slots/5/dining"
        ]
        self.assertEqual(1, len(replace_ops))
        self.assertTrue(validate_trip(second.trip).ok, validate_trip(second.trip).errors)

    def test_no_anchor_writes_null_and_typed_unknown(self):
        result = envelope([
            no_result_row(self.trip, 0, self.slot_index, "no_anchor"),
        ], [])
        folded = fold_dining_into_trip(copy.deepcopy(self.trip), result, CLOCK)
        self.assertIsNotNone(folded)
        slot = folded.trip["days"][0]["slots"][self.slot_index]
        self.assertIn("dining", slot)
        self.assertIsNone(slot["dining"])
        unknown = next(
            item for item in folded.trip["unknowns"]
            if item["field_path"] == "/days/0/slots/5/dining"
        )
        self.assertEqual("dining_no_anchor", unknown["reason"])
        self.assertEqual("amap", unknown["provider"])
        self.assertIsNone(unknown["claim_id"])
        report = validate_trip(folded.trip)
        self.assertTrue(report.ok, report.errors)

    def test_missing_claim_and_wrong_journey_revision_raise(self):
        result = self._one_slot_result()
        result["claims"] = result["claims"][:-1]
        with self.assertRaises(ValueError) as claim_ctx:
            fold_dining_into_trip(copy.deepcopy(self.trip), result, CLOCK)
        self.assertIn("dining_fold_claim_missing", str(claim_ctx.exception))

        with self.assertRaises(ValueError) as revision_ctx:
            fold_dining_into_journey(self.journey, self._one_slot_result(), 7, CLOCK)
        self.assertIn("revision_conflict", str(revision_ctx.exception))

    def test_two_trips_change_with_one_journey_revision_bump(self):
        row1, claims1 = options_row(self.journey["trips"][0], 0, 5, self.specs)
        second_specs = [
            ("hangzhou1", "杭城一味", 190),
            ("hangzhou2", "西湖家宴", 350),
            ("hangzhou3", "湖滨小馆", 510),
        ]
        row2, claims2 = options_row(self.journey["trips"][1], 0, 5, second_specs)
        result = envelope([row1, row2], claims1 + claims2)

        folded = fold_dining_into_journey(self.journey, result, 1, CLOCK)
        self.assertIsNotNone(folded)
        self.assertEqual(2, folded["revision"]["number"])
        self.assertEqual(1, folded["revision"]["parent_revision"])
        self.assertEqual(2, folded["trips"][0]["revision"]["number"])
        self.assertEqual(2, folded["trips"][1]["revision"]["number"])
        self.assertEqual(
            canonical_json(self.original_trips[2]), canonical_json(folded["trips"][2]),
        )


if __name__ == "__main__":
    unittest.main()
