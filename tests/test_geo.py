from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "plugins" / "china-trip-weaver" / "src"
sys.path.insert(0, str(SRC))

from china_trip_weaver.clock import FixedClock
from china_trip_weaver.geo import Point, bd09_to_gcj02, coordinate_record, gcj02_to_wgs84, outside_mainland_china, wgs84_to_gcj02


def meters(left: Point, right: Point) -> float:
    lat_scale = 111320.0
    lng_scale = lat_scale * math.cos(math.radians((left.lat + right.lat) / 2))
    return math.hypot((left.lng - right.lng) * lng_scale, (left.lat - right.lat) * lat_scale)


class GeoTests(unittest.TestCase):
    def setUp(self):
        self.clock = FixedClock.from_iso("2026-09-03T12:00:00+08:00")

    def test_known_beijing_wgs84_to_gcj02(self):
        converted = wgs84_to_gcj02(Point(116.397389, 39.908722))
        expected = Point(116.403632, 39.910125)
        self.assertLess(meters(converted, expected), 5)

    def test_round_trip_error_is_bounded(self):
        original = Point(121.4737, 31.2304)
        restored = gcj02_to_wgs84(wgs84_to_gcj02(original))
        self.assertLess(meters(original, restored), 0.5)

    def test_outside_mainland_is_identity(self):
        paris = Point(2.3522, 48.8566)
        self.assertTrue(outside_mainland_china(paris))
        self.assertEqual(paris, wgs84_to_gcj02(paris))
        record = coordinate_record("WGS84", paris, self.clock)
        self.assertEqual("not-needed", record["conversion"]["status"])
        self.assertEqual([], record["conversion"]["derived_fields"])

    def test_wgs_record_preserves_native_and_marks_one_derived_field(self):
        point = Point(116.397389, 39.908722)
        record = coordinate_record("WGS84", point, self.clock, accuracy_m=10)
        self.assertEqual(record["native"], record["wgs84"])
        self.assertEqual(["gcj02"], record["conversion"]["derived_fields"])
        self.assertEqual("wgs84-to-gcj02", record["conversion"]["method"])

    def test_gcj_record_preserves_native(self):
        point = Point(116.403632, 39.910125)
        record = coordinate_record("GCJ02", point, self.clock)
        self.assertEqual(record["native"], record["gcj02"])
        self.assertEqual(["wgs84"], record["conversion"]["derived_fields"])

    def test_unknown_crs_is_never_converted(self):
        record = coordinate_record("provider-unknown", Point(120, 30), self.clock)
        self.assertIsNone(record["wgs84"])
        self.assertIsNone(record["gcj02"])
        self.assertEqual("unavailable", record["conversion"]["status"])

    def test_bd09_record_preserves_native_and_derives_both_consumers(self):
        native = Point(116.416627, 39.916027)
        record = coordinate_record("BD09", native, self.clock)
        self.assertEqual(native.as_dict(), record["native"])
        self.assertEqual(["wgs84", "gcj02"], record["conversion"]["derived_fields"])
        self.assertLess(meters(bd09_to_gcj02(native), Point(**record["gcj02"])), 0.1)

    def test_unsupported_crs_fails_closed(self):
        with self.assertRaises(ValueError):
            coordinate_record("EPSG3857", Point(116, 39), self.clock)


if __name__ == "__main__":
    unittest.main()
