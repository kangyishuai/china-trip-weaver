from __future__ import annotations

import copy
import json
import sys
import unittest
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "plugins" / "china-trip-weaver" / "src"
sys.path.insert(0, str(SRC))

from china_trip_weaver import dining
from china_trip_weaver.clock import FixedClock
from china_trip_weaver.evidence import make_claim
from china_trip_weaver.geo import Point, coordinate_record


JOURNEY_DEMO = ROOT / "demo" / "journey-16d"
CLOCK = FixedClock.from_iso("2026-09-17T12:00:00+08:00")


def _load_trip():
    journey = json.loads((JOURNEY_DEMO / "journey.json").read_text(encoding="utf-8"))
    return journey["trips"][0]


def _coordinates(lng, lat):
    return coordinate_record("GCJ02", Point(lng, lat), CLOCK, accuracy_m=30)


def _slot(kind, title, start_at, end_at=None, ref_id=None):
    return {
        "slot_id": "slot-test-%s" % abs(hash((kind, title, start_at))),
        "start_at": start_at,
        "end_at": end_at or start_at,
        "kind": kind,
        "ref_id": ref_id,
        "title": title,
        "locked": False,
        "status": "scheduled",
        "claim_ids": [],
    }


def _dining_item(poi_key, name, distance_meters, business, lng=121.47, lat=31.23):
    claim = make_claim(
        subject_ref="poi-amap-%s" % poi_key,
        field_path="/provider_identity",
        value={
            "provider_poi_id": poi_key.upper(),
            "matched_name": name,
            "formatted_address": "上海市某某路%s号" % poi_key,
            "district": "黄浦区",
            "adcode": "310101",
            "type": "餐饮服务;中餐厅;中餐厅",
            "business": business,
        },
        source_url="https://restapi.amap.com/v5/place/around",
        provider="amap",
        status="verified",
        confidence=0.9,
        mode="live",
        clock=CLOCK,
    )
    item = {
        "poi_id": "poi-amap-%s" % poi_key,
        "name": name,
        "city": "上海",
        "category": "中餐厅",
        "coordinates": _coordinates(lng, lat),
        "distance_meters": distance_meters,
        "recommended_duration_minutes": None,
        "opening_windows": [],
        "price": None,
        "deep_links": [],
        "claim_ids": [claim["claim_id"]],
    }
    return item, claim


class MealSlotsTests(unittest.TestCase):
    def test_demo_first_day_has_two_meal_slots(self):
        trip = _load_trip()
        day0 = [entry for entry in dining.meal_slots(trip) if entry[0] == 0]
        self.assertEqual(day0, [(0, 1, "lunch"), (0, 5, "dinner")])

    def test_free_slot_with_dinner_wording_classifies_as_dinner(self):
        slot = _slot("free", "中秋团圆晚餐：阖家欢聚", "2026-10-01T18:00:00+08:00")
        self.assertEqual(dining.meal_type_for(slot), "dinner")

    def test_free_slot_without_meal_wording_is_none(self):
        slot = _slot("free", "午休", "2026-10-01T13:00:00+08:00")
        self.assertIsNone(dining.meal_type_for(slot))

    def test_meal_slot_without_wording_falls_back_to_start_hour(self):
        morning = _slot("meal", "自由用餐", "2026-10-01T12:30:00+08:00")
        evening = _slot("meal", "自由用餐", "2026-10-01T18:30:00+08:00")
        self.assertEqual(dining.meal_type_for(morning), "lunch")
        self.assertEqual(dining.meal_type_for(evening), "dinner")

    def test_rest_slot_with_lunch_wording_classifies_as_lunch(self):
        slot = _slot("rest", "午餐与完整午休", "2026-10-01T12:00:00+08:00")
        self.assertEqual(dining.meal_type_for(slot), "lunch")

    def test_rest_slot_without_meal_wording_is_none(self):
        slot = _slot("rest", "午休", "2026-10-01T13:00:00+08:00")
        self.assertIsNone(dining.meal_type_for(slot))


class AnchorForTests(unittest.TestCase):
    def test_preceding_checkin_with_lodging_coordinates_wins(self):
        trip = copy.deepcopy(_load_trip())
        trip["lodgings"][0]["coordinates"] = _coordinates(121.47, 31.23)

        anchor = dining.anchor_for(trip, 0, 5)

        self.assertEqual(anchor, {
            "ref_id": "lodging-j16-shanghai-central",
            "name": "上海合成住宿",
            "lng": 121.47,
            "lat": 31.23,
        })

    def test_no_coordinates_before_falls_back_to_next_poi(self):
        trip = copy.deepcopy(_load_trip())
        trip["pois"].append({
            "poi_id": "poi-test-anchor",
            "name": "测试打卡点",
            "city": "上海",
            "category": "poi",
            "coordinates": _coordinates(121.5, 31.24),
            "recommended_duration_minutes": 30,
            "physical_intensity": "light",
            "opening_windows": [],
            "price": None,
            "deep_links": [],
            "claim_ids": [],
        })
        trip["days"][0]["slots"].append(_slot(
            "poi", "测试打卡点", "2026-10-01T17:30:00+08:00", "2026-10-01T18:00:00+08:00",
            ref_id="poi-test-anchor",
        ))

        anchor = dining.anchor_for(trip, 0, 5)

        self.assertEqual(anchor, {
            "ref_id": "poi-test-anchor",
            "name": "测试打卡点",
            "lng": 121.5,
            "lat": 31.24,
        })

    def test_whole_day_without_coordinates_returns_none(self):
        trip = copy.deepcopy(_load_trip())

        self.assertIsNone(dining.anchor_for(trip, 0, 5))

    @staticmethod
    def _transfer_day(slots):
        """A one-day trip whose departure-city lodging and arrival-city POI both have coordinates."""

        return {
            "days": [{"slots": slots}],
            "lodgings": [
                {"lodging_id": "lodging-origin", "name": "出发城住宿", "coordinates": _coordinates(118.0, 27.6)},
                {"lodging_id": "lodging-arrival", "name": "到达城住宿", "coordinates": _coordinates(119.3, 26.1)},
            ],
            "pois": [
                {"poi_id": "poi-arrival", "name": "到达城景点", "coordinates": _coordinates(119.31, 26.09)},
            ],
        }

    def test_meal_after_a_transfer_never_anchors_on_the_departure_city(self):
        # 9/29-style day: check out, take the train, then lunch in the arrival city.
        trip = self._transfer_day([
            _slot("checkout", "退房", "2026-09-29T08:00:00+08:00", ref_id="lodging-origin"),
            _slot("transport", "铁路", "2026-09-29T10:00:00+08:00", ref_id="leg-transfer"),
            _slot("free", "寄存行李与午餐", "2026-09-29T11:43:00+08:00"),
            _slot("poi", "到达城景点", "2026-09-29T14:13:00+08:00", ref_id="poi-arrival"),
        ])

        anchor = dining.anchor_for(trip, 0, 2)

        self.assertEqual("poi-arrival", anchor["ref_id"])

    def test_meal_before_a_transfer_never_anchors_on_the_arrival_city(self):
        trip = self._transfer_day([
            _slot("free", "午餐", "2026-09-29T11:00:00+08:00"),
            _slot("transport", "铁路", "2026-09-29T12:30:00+08:00", ref_id="leg-transfer"),
            _slot("checkin", "入住", "2026-09-29T15:00:00+08:00", ref_id="lodging-arrival"),
        ])

        self.assertIsNone(dining.anchor_for(trip, 0, 0))

    @staticmethod
    def _night_stay_trip(meal_slot, trailing_slots, stay_has_coordinates):
        """退房→换乘→`meal_slot`（可选 `trailing_slots`），换乘后没有别的带坐标时段；
        `day["stay_id"]` 指向到达城的住处，`stay_has_coordinates` 控制它是否已定位。
        """

        lodgings = [
            {"lodging_id": "lodging-origin", "name": "出发城住宿", "coordinates": _coordinates(118.0, 27.6)},
            {"lodging_id": "lodging-arrival", "name": "到达城住宿"},
        ]
        if stay_has_coordinates:
            lodgings[1]["coordinates"] = _coordinates(119.3, 26.1)
        slots = [
            _slot("checkout", "退房", "2026-10-02T08:00:00+08:00", ref_id="lodging-origin"),
            _slot("transport", "轮渡", "2026-10-02T10:00:00+08:00", ref_id="leg-ferry"),
            meal_slot,
        ] + list(trailing_slots)
        return {
            "days": [{"slots": slots, "stay_id": "lodging-arrival"}],
            "lodgings": lodgings,
            "pois": [],
        }

    def test_dinner_after_transfer_with_nothing_later_anchors_on_the_night_stay(self):
        dinner = _slot("meal", "晚餐（地点待定）", "2026-10-02T18:30:00+08:00")
        trip = self._night_stay_trip(dinner, [], stay_has_coordinates=True)

        anchor = dining.anchor_for(trip, 0, 2)

        self.assertEqual(anchor, {
            "ref_id": "lodging-arrival",
            "name": "到达城住宿",
            "lng": 119.3,
            "lat": 26.1,
        })

    def test_dinner_with_a_later_transport_slot_does_not_fall_back_to_the_night_stay(self):
        dinner = _slot("meal", "晚餐（地点待定）", "2026-10-02T18:30:00+08:00")
        later_transport = _slot("transport", "轮渡", "2026-10-02T20:00:00+08:00", ref_id="leg-ferry-2")
        trip = self._night_stay_trip(dinner, [later_transport], stay_has_coordinates=True)

        self.assertIsNone(dining.anchor_for(trip, 0, 2))

    def test_dinner_falls_back_only_when_the_night_stay_has_coordinates(self):
        dinner = _slot("meal", "晚餐（地点待定）", "2026-10-02T18:30:00+08:00")
        trip = self._night_stay_trip(dinner, [], stay_has_coordinates=False)

        self.assertIsNone(dining.anchor_for(trip, 0, 2))

    def test_lunch_after_transfer_does_not_fall_back_to_the_night_stay(self):
        lunch = _slot("meal", "午餐（地点待定）", "2026-10-02T12:30:00+08:00")
        trip = self._night_stay_trip(lunch, [], stay_has_coordinates=True)

        self.assertIsNone(dining.anchor_for(trip, 0, 2))


class SelectOptionsTests(unittest.TestCase):
    def setUp(self):
        self.no_rating_item, self.no_rating_claim = _dining_item(
            "norating", "无评分小馆", 100, {"cost": "50", "keytag": "家常菜"},
        )
        self.item1, self.claim1 = _dining_item(
            "jinjiang", "锦江福味", 800, {"rating": "4.6", "cost": "78", "keytag": "闽菜"},
        )
        self.hotpot_item, self.hotpot_claim = _dining_item(
            "laowang", "老王火锅城", 200, {"rating": "4.7", "cost": "90", "keytag": "火锅"},
        )
        self.item2, self.claim2 = _dining_item(
            "haiyang", "海阳鲜道", 300, {"rating": "4.5", "cost": "120", "keytag": "海鲜"},
        )
        self.item3, self.claim3 = _dining_item(
            "laofuzhou", "老福州小吃", 1200, {"rating": "4.3", "cost": "35", "keytag": "小吃"},
        )
        self.item4, self.claim4 = _dining_item(
            "axiang", "阿香川湘馆", 500, {"rating": "4.4", "cost": "60", "keytag": "湘菜"},
        )
        # Deliberately not sorted by distance_meters, so a passing test proves
        # selection order follows `items` order, not proximity.
        self.items = [
            self.no_rating_item, self.item1, self.hotpot_item, self.item2, self.item3, self.item4,
        ]
        self.claims = [
            self.no_rating_claim, self.claim1, self.hotpot_claim, self.claim2, self.claim3, self.claim4,
        ]

    def test_default_selection_skips_no_rating_keeps_item_order(self):
        options = dining.select_options(self.items, self.claims)

        self.assertEqual([o["name"] for o in options], ["锦江福味", "老王火锅城", "海阳鲜道"])
        self.assertTrue(all(o["rating"] for o in options))

    def test_avoid_word_skips_matching_item(self):
        options = dining.select_options(self.items, self.claims, avoid=("火锅",))

        self.assertEqual([o["name"] for o in options], ["锦江福味", "海阳鲜道", "老福州小吃"])

    def test_option_shape_and_marker_deep_link(self):
        options = dining.select_options(self.items, self.claims)
        option = options[0]

        self.assertEqual(set(option), {
            "provider_poi_id", "name", "cuisine", "tag", "rating", "cost_cny",
            "distance_m", "opentime_today", "address", "deep_links", "claim_id",
        })
        self.assertEqual(option["provider_poi_id"], "JINJIANG")
        self.assertEqual(option["cuisine"], "闽菜")
        self.assertEqual(option["cost_cny"], 78.0)
        self.assertEqual(option["distance_m"], 800)
        self.assertEqual(option["claim_id"], self.claim1["claim_id"])
        marker_link, search_link = option["deep_links"]
        self.assertIn("uri.amap.com/marker", marker_link)
        self.assertIn("name=" + urllib.parse.quote("锦江福味"), marker_link)
        self.assertEqual(search_link, "https://www.amap.com/search?id=JINJIANG")


class FormatOptionAndSearchUrlTests(unittest.TestCase):
    def test_full_option_matches_reference_string(self):
        option = {
            "name": "名", "cuisine": "菜系", "rating": "4.6", "cost_cny": 78.0,
            "distance_m": 257, "opentime_today": "17:00-02:00",
        }

        self.assertEqual(
            dining.format_option(option),
            "名 · 菜系 · 评分 4.6 · 人均 ¥78 · 距 257 m · 今日 17:00-02:00",
        )

    def test_missing_cost_drops_the_segment(self):
        option = {
            "name": "名", "cuisine": "菜系", "rating": "4.6", "cost_cny": None,
            "distance_m": 257, "opentime_today": "17:00-02:00",
        }

        result = dining.format_option(option)

        self.assertNotIn("人均", result)
        self.assertEqual(result, "名 · 菜系 · 评分 4.6 · 距 257 m · 今日 17:00-02:00")

    def test_search_url_contains_literal_keyword_and_center(self):
        anchor = {"ref_id": "x", "name": "y", "lng": 121.47, "lat": 31.23}

        url = dining.search_url(anchor)

        self.assertIn("keyword=美食", url)
        self.assertIn("center=121.470000,31.230000", url)


if __name__ == "__main__":
    unittest.main()
