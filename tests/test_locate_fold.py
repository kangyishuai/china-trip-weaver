from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "plugins" / "china-trip-weaver" / "src"
sys.path.insert(0, str(SRC))

from china_trip_weaver import dining
from china_trip_weaver.clock import FixedClock, isoformat_seconds
from china_trip_weaver.contracts import canonical_json
from china_trip_weaver.evidence import make_claim
from china_trip_weaver.locate_fold import fold_locations_into_journey, fold_locations_into_trip
from china_trip_weaver.render import render_journey, validate_journey_html
from china_trip_weaver.validate_trip import validate_trip


JOURNEY_DEMO = ROOT / "demo" / "journey-16d"
CLOCK = FixedClock.from_iso("2026-09-22T09:00:00+08:00")
SOURCE_URL = "https://restapi.amap.com/v3/geocode/geo"

# tests/fixtures/trips/schema/valid/weekend-live.json's poi-bund.coordinates, reused verbatim
# as the synthetic "located" value per the task brief.
BUND_COORDINATES = {
    "source_crs": "GCJ02",
    "native": {"lng": 121.4903, "lat": 31.2417},
    "wgs84": {"lng": 121.4858, "lat": 31.2436},
    "gcj02": {"lng": 121.4903, "lat": 31.2417},
    "conversion": {
        "status": "converted",
        "method": "gcj02-to-wgs84",
        "version": "ctw-1",
        "derived_fields": ["wgs84"],
        "converted_at": "2026-10-01T08:40:00+08:00",
        "accuracy_m": 10,
    },
}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def location_claim(ref_id, *, clock=CLOCK, coordinates=None):
    return make_claim(
        subject_ref=ref_id,
        field_path="/coordinates",
        value=coordinates or BUND_COORDINATES,
        source_url=SOURCE_URL,
        provider="amap",
        status="verified",
        confidence=0.9,
        mode="live",
        clock=clock,
        json_path="/geocodes/0",
    )


def located_row(trip_id, kind, ref_id, name, city, *, clock=CLOCK, coordinates=None):
    value = coordinates or BUND_COORDINATES
    claim = location_claim(ref_id, clock=clock, coordinates=value)
    row = {
        "trip_id": trip_id,
        "ref_id": ref_id,
        "kind": kind,
        "name": name,
        "city": city,
        "status": "located",
        "coordinates": value,
        "claim_ids": [claim["claim_id"]],
        "reason": None,
    }
    return row, claim


def unresolved_row(trip_id, kind, ref_id, name, city, reason):
    return {
        "trip_id": trip_id,
        "ref_id": ref_id,
        "kind": kind,
        "name": name,
        "city": city,
        "status": "unresolved",
        "coordinates": None,
        "claim_ids": [],
        "reason": reason,
    }


def provider_error_row(trip_id, kind, ref_id, name, city, reason):
    return {
        "trip_id": trip_id,
        "ref_id": ref_id,
        "kind": kind,
        "name": name,
        "city": city,
        "status": "provider_error",
        "coordinates": None,
        "claim_ids": [],
        "reason": reason,
    }


def envelope(rows, claims, *, clock=CLOCK, provider_version="locate-v1-test"):
    return {
        "queried_at": isoformat_seconds(clock),
        "provider_version": provider_version,
        "claims": list(claims),
        "entities": list(rows),
    }


class LocateFoldTests(unittest.TestCase):
    def setUp(self):
        self.journey = load(JOURNEY_DEMO / "journey.json")
        self.original_trips = copy.deepcopy(self.journey["trips"])
        self.trip = self.journey["trips"][0]

    def _poi_lodging_result(self, *, clock=CLOCK):
        poi_row, poi_claim = located_row(
            self.trip["trip_id"], "poi", "poi-j16-shanghai", "上海合成建筑漫步", "上海", clock=clock,
        )
        lodging_row, lodging_claim = located_row(
            self.trip["trip_id"], "lodging", "lodging-j16-shanghai-central", "上海合成住宿", "上海", clock=clock,
        )
        return envelope([poi_row, lodging_row], [poi_claim, lodging_claim], clock=clock)

    def test_located_rows_write_coordinates_and_render_valid(self):
        result = self._poi_lodging_result()
        self.assertIsNone(dining.anchor_for(self.trip, 0, 5))

        patch_result = fold_locations_into_trip(copy.deepcopy(self.trip), result, CLOCK)
        self.assertIsNotNone(patch_result)
        trip = patch_result.trip
        patch = patch_result.patch

        self.assertEqual(2, trip["revision"]["number"])
        self.assertEqual("provider_change", patch["trigger"])
        poi = next(item for item in trip["pois"] if item["poi_id"] == "poi-j16-shanghai")
        lodging = next(
            item for item in trip["lodgings"] if item["lodging_id"] == "lodging-j16-shanghai-central"
        )
        self.assertEqual(BUND_COORDINATES, poi["coordinates"])
        self.assertEqual(BUND_COORDINATES, lodging["coordinates"])

        poi_claim_id = result["entities"][0]["claim_ids"][0]
        lodging_claim_id = result["entities"][1]["claim_ids"][0]
        self.assertIn(poi_claim_id, poi["claim_ids"])
        self.assertIn(lodging_claim_id, lodging["claim_ids"])
        self.assertIn("claim-j16-shanghai-hours", poi["claim_ids"])  # pre-existing id preserved
        self.assertTrue(any(c["claim_id"] == poi_claim_id for c in trip["claims"]))
        self.assertTrue(any(c["claim_id"] == lodging_claim_id for c in trip["claims"]))

        self.assertEqual({"day-1", "day-2"}, set(patch["scope"]["day_ids"]))
        self.assertEqual(
            {"poi-j16-shanghai", "lodging-j16-shanghai-central"}, set(patch["scope"]["affected_refs"]),
        )

        amap_health = next(row for row in trip["provider_health"] if row["provider"] == "amap")
        self.assertIn("poi", amap_health["capabilities"])
        self.assertIn("geocode", amap_health["capabilities"])
        self.assertEqual("ready", amap_health["status"])
        self.assertEqual("live", amap_health["mode"])
        self.assertIn("locate=2 entities folded", amap_health["reason"])

        self.assertIsNone(
            next((u for u in trip["unknowns"] if u["field_path"] == "/pois/0/coordinates"), None)
        )

        report = validate_trip(trip)
        self.assertTrue(report.ok, report.errors)

        anchor = dining.anchor_for(trip, 0, 5)
        self.assertIsNotNone(anchor)
        self.assertEqual("lodging-j16-shanghai-central", anchor["ref_id"])

        journey_result = fold_locations_into_journey(
            self.journey, result, self.journey["revision"]["number"], CLOCK,
        )
        self.assertIsNotNone(journey_result)
        self.assertEqual(2, journey_result["revision"]["number"])
        self.assertEqual(1, journey_result["revision"]["parent_revision"])
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

    def test_same_result_folded_twice_is_noop(self):
        result = self._poi_lodging_result()
        first = fold_locations_into_trip(copy.deepcopy(self.trip), result, CLOCK)
        self.assertIsNotNone(first)
        self.assertIsNone(fold_locations_into_trip(first.trip, result, CLOCK))

        journey_first = fold_locations_into_journey(self.journey, result, 1, CLOCK)
        self.assertIsNotNone(journey_first)
        self.assertIsNone(fold_locations_into_journey(journey_first, result, 2, CLOCK))

    def test_entity_with_existing_full_coordinates_is_never_overwritten(self):
        trip = copy.deepcopy(self.trip)
        trip["pois"][0]["coordinates"] = copy.deepcopy(BUND_COORDINATES)
        different_coordinates = copy.deepcopy(BUND_COORDINATES)
        different_coordinates["gcj02"] = {"lng": 120.0, "lat": 30.0}
        different_coordinates["native"] = {"lng": 120.0, "lat": 30.0}
        row, claim = located_row(
            trip["trip_id"], "poi", "poi-j16-shanghai", "上海合成建筑漫步", "上海",
            coordinates=different_coordinates,
        )
        result = envelope([row], [claim])

        folded = fold_locations_into_trip(copy.deepcopy(trip), result, CLOCK)
        self.assertIsNone(folded)
        self.assertEqual(BUND_COORDINATES, trip["pois"][0]["coordinates"])

    def test_unresolved_row_records_reason_then_second_fold_is_noop(self):
        trip = copy.deepcopy(self.trip)
        row = unresolved_row(
            trip["trip_id"], "lodging", "lodging-j16-shanghai-central", "上海合成住宿", "上海",
            "ambiguous_name_margin",
        )
        result = envelope([row], [])

        folded = fold_locations_into_trip(copy.deepcopy(trip), result, CLOCK)
        self.assertIsNotNone(folded)
        lodging = folded.trip["lodgings"][0]
        self.assertIsNone(lodging["coordinates"])
        unknown = next(
            item for item in folded.trip["unknowns"] if item["field_path"] == "/lodgings/0/coordinates"
        )
        self.assertEqual("ambiguous_name_margin", unknown["reason"])
        self.assertEqual("amap", unknown["provider"])
        self.assertIsNone(unknown["claim_id"])
        report = validate_trip(folded.trip)
        self.assertTrue(report.ok, report.errors)

        self.assertIsNone(fold_locations_into_trip(folded.trip, result, CLOCK))

        # A later query with a *different* reason replaces the unknown instead of duplicating it.
        later_clock = FixedClock.from_iso("2026-09-22T15:00:00+08:00")
        changed_row = unresolved_row(
            trip["trip_id"], "lodging", "lodging-j16-shanghai-central", "上海合成住宿", "上海",
            "geocode_ambiguous",
        )
        changed_result = envelope([changed_row], [], clock=later_clock)
        second = fold_locations_into_trip(folded.trip, changed_result, later_clock)
        self.assertIsNotNone(second)
        self.assertEqual(3, second.trip["revision"]["number"])
        matching = [
            item for item in second.trip["unknowns"] if item["field_path"] == "/lodgings/0/coordinates"
        ]
        self.assertEqual(1, len(matching))
        self.assertEqual("geocode_ambiguous", matching[0]["reason"])

    def test_provider_error_row_leaves_entity_untouched(self):
        trip = copy.deepcopy(self.trip)
        row = provider_error_row(
            trip["trip_id"], "poi", "poi-j16-shanghai", "上海合成建筑漫步", "上海", "amap_unavailable",
        )
        result = envelope([row], [])
        self.assertIsNone(fold_locations_into_trip(copy.deepcopy(trip), result, CLOCK))
        self.assertIsNone(trip["pois"][0]["coordinates"])
        self.assertEqual(
            1, len([u for u in trip["unknowns"] if u["field_path"] == "/pois/0/coordinates"]),
        )

    def test_missing_claim_and_wrong_journey_revision_raise(self):
        result = self._poi_lodging_result()
        result["claims"] = []
        with self.assertRaises(ValueError) as claim_ctx:
            fold_locations_into_trip(copy.deepcopy(self.trip), result, CLOCK)
        self.assertIn("locate_fold_claim_missing", str(claim_ctx.exception))

        with self.assertRaises(ValueError) as revision_ctx:
            fold_locations_into_journey(self.journey, self._poi_lodging_result(), 99, CLOCK)
        self.assertIn("revision_conflict", str(revision_ctx.exception))

    def test_two_trips_each_change_one_entity_bumps_journey_revision_once(self):
        poi_row, poi_claim = located_row(
            self.journey["trips"][0]["trip_id"], "poi", "poi-j16-shanghai", "上海合成建筑漫步", "上海",
        )
        hangzhou_row, hangzhou_claim = located_row(
            self.journey["trips"][1]["trip_id"], "poi", "poi-j16-hangzhou", "杭州合成景点", "杭州",
        )
        result = envelope([poi_row, hangzhou_row], [poi_claim, hangzhou_claim])

        folded = fold_locations_into_journey(self.journey, result, self.journey["revision"]["number"], CLOCK)
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
