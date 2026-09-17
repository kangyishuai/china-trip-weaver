from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "plugins" / "china-trip-weaver" / "src"
sys.path.insert(0, str(SRC))

from china_trip_weaver.clock import FixedClock
from china_trip_weaver.journey import plan_journey
from china_trip_weaver.planning import RailBackend, _locked_rail_candidate, plan_trip
from china_trip_weaver.render import validate_html
from china_trip_weaver.validate_trip import validate_trip


FIXED_NOW = "2026-09-03T12:00:00+08:00"
TRAVEL_DATE = "2026-09-20"


def locked_request(locked_rail_services=None, assumptions=None):
    request = {
        "origin": {"ref_id": "city-fuzhou", "name": "福州", "city": "福州"},
        "destinations": [{"ref_id": "city-wuyishan", "name": "武夷山", "city": "武夷山"}],
        "start_date": TRAVEL_DATE,
        "end_date": TRAVEL_DATE,
        "travelers": 2,
        "budget_cny": 5000,
        "interests": ["nature"],
        "pace": "balanced",
        "constraints": ["单程"],
        "assumptions": list(assumptions) if assumptions else ["synthetic locked-rail acceptance input"],
        "locale": "zh-CN",
        "pasted_notes": None,
    }
    if locked_rail_services is not None:
        request["locked_rail_services"] = locked_rail_services
    return request


def locked_candidates():
    point = {"lng": 118.017, "lat": 27.756}
    return {
        "candidates_version": "1.0.0",
        "pois": [{
            "poi_id": "poi-wuyishan-1",
            "name": "武夷山风景区",
            "city": "武夷山",
            "category": "nature",
            "coordinates": {
                "source_crs": "WGS84",
                "native": point,
                "wgs84": point,
                "gcj02": None,
                "conversion": {
                    "status": "not-needed", "method": "identity", "version": "1",
                    "derived_fields": [], "converted_at": None, "accuracy_m": None,
                },
            },
            "recommended_duration_minutes": 120,
            "opening_windows": [],
            "price": None,
            "deep_links": ["https://example.com/synthetic-locked-rail/1"],
            "claim_ids": ["claim-wuyishan-1"],
        }],
        "lodgings": [],
        "claims": [{
            "claim_id": "claim-wuyishan-1",
            "subject_ref": "poi-wuyishan-1",
            "field_path": "/name",
            "value": "synthetic locked-rail candidate",
            "source_url": "https://example.com/synthetic-locked-rail/1",
            "provider": "synthetic-e2e",
            "queried_at": FIXED_NOW,
            "status": "hypothesis",
            "confidence": 0.5,
            "mode": "static",
            "as_of": None,
            "raw_ref": None,
            "response_hash": None,
            "json_path": None,
        }],
        "unknowns": [],
    }


def _row(service, from_station, to_station, start_time, arrive_time, price=128.5):
    start_h, start_m = (int(part) for part in start_time.split(":"))
    arrive_h, arrive_m = (int(part) for part in arrive_time.split(":"))
    minutes = (arrive_h * 60 + arrive_m) - (start_h * 60 + start_m)
    return {
        "arrive_date": TRAVEL_DATE, "arrive_time": arrive_time,
        "dw_flag": [], "from_station": from_station, "from_station_telecode": "SRC",
        "lishi": "%02d:%02d" % (minutes // 60, minutes % 60),
        "prices": [{
            "discount": 100, "num": "有", "price": price,
            "seat_name": "二等座", "seat_type_code": "O", "short": "ze",
        }],
        "start_date": TRAVEL_DATE, "start_time": start_time, "start_train_code": service,
        "to_station": to_station, "to_station_telecode": "DST", "train_no": "SYNTH-" + service,
    }


# G1901 arrives earliest (08:50); G1902 is the traveler's locked, already-purchased
# service (07:50 departure from 福州南站, matching the real-world "G1902 已购并锁定"
# fixture that motivated this feature) and also appears a second time departing from
# the other in-city station 福州站, mirroring the real 12306 same-city two-station
# response shape this task must disambiguate with depart_time.
ROWS = (
    _row("G1901", "福州南站", "武夷山北站", "07:00", "08:50"),
    _row("G1902", "福州南站", "武夷山北站", "07:50", "09:30"),
    _row("G1902", "福州站", "武夷山北站", "08:12", "09:30"),
)

# G5023 mirrors the real-world 9/29 武夷山->福州 return leg (see BLOCKED.md's "AN4"
# entry): both rows depart 武夷山北站 at the same 10:00, but arrive at two different
# same-city Fuzhou stations (福州站 11:13, 福州南站 11:32) -- the mirror image of
# ROWS's G1902 clash above (which shares one arrival time across two departures).
# depart_time cannot disambiguate this shape; only arrive_time can.
G5023_ROWS = (
    _row("G5023", "武夷山北站", "福州站", "10:00", "11:13"),
    _row("G5023", "武夷山北站", "福州南站", "10:00", "11:32"),
)


def rail_fixture(rows):
    return {
        "provider": "rail12306",
        "transport": {
            "body": {
                "calls": [
                    {
                        "arguments": {"citys": "福州|武夷山"},
                        "name": "get-station-code-of-citys",
                        "result": {"content": [{"type": "text", "text": json.dumps({
                            "福州": {"station_code": "FZX", "station_name": "福州示例站"},
                            "武夷山": {"station_code": "WYX", "station_name": "武夷山示例站"},
                        }, ensure_ascii=False)}]},
                    },
                    {
                        "arguments": {
                            "date": TRAVEL_DATE, "format": "json", "fromStation": "FZX",
                            "limitedNum": 30, "toStation": "WYX", "trainFilterFlags": "GD",
                        },
                        "name": "get-tickets",
                        "result": {"content": [{"type": "text", "text": json.dumps(rows, ensure_ascii=False)}]},
                    },
                ],
                "protocol_version": "2025-06-18",
                "server_info": {"name": "12306-mcp", "version": "0.3.10"},
                "tools": [
                    "get-current-date", "get-stations-code-in-city", "get-station-code-of-citys",
                    "get-station-code-by-names", "get-station-by-telecode", "get-tickets",
                    "get-interline-tickets", "get-train-route-stations",
                ],
            },
            "headers": {},
            "kind": "response",
            "status_code": 200,
        },
    }


def return_leg_request(locked_rail_services=None, assumptions=None):
    # Mirrors locked_request() but for the return-direction route (武夷山 -> 福州)
    # that G5023_ROWS's stations belong to; _filter_direct_rows would drop every
    # G5023 row if queried in locked_request()'s outbound 福州 -> 武夷山 direction.
    request = {
        "origin": {"ref_id": "city-wuyishan", "name": "武夷山", "city": "武夷山"},
        "destinations": [{"ref_id": "city-fuzhou", "name": "福州", "city": "福州"}],
        "start_date": TRAVEL_DATE,
        "end_date": TRAVEL_DATE,
        "travelers": 2,
        "budget_cny": 5000,
        "interests": ["culture"],
        "pace": "balanced",
        "constraints": ["单程"],
        "assumptions": list(assumptions) if assumptions else ["synthetic locked-rail return-leg acceptance input"],
        "locale": "zh-CN",
        "pasted_notes": None,
    }
    if locked_rail_services is not None:
        request["locked_rail_services"] = locked_rail_services
    return request


def return_leg_candidates():
    point = {"lng": 119.306, "lat": 26.075}
    return {
        "candidates_version": "1.0.0",
        "pois": [{
            "poi_id": "poi-fuzhou-1",
            "name": "三坊七巷",
            "city": "福州",
            "category": "culture",
            "coordinates": {
                "source_crs": "WGS84",
                "native": point,
                "wgs84": point,
                "gcj02": None,
                "conversion": {
                    "status": "not-needed", "method": "identity", "version": "1",
                    "derived_fields": [], "converted_at": None, "accuracy_m": None,
                },
            },
            "recommended_duration_minutes": 90,
            "opening_windows": [],
            "price": None,
            "deep_links": ["https://example.com/synthetic-locked-rail/fuzhou-poi-1"],
            "claim_ids": ["claim-fuzhou-poi-1"],
        }],
        "lodgings": [],
        "claims": [{
            "claim_id": "claim-fuzhou-poi-1",
            "subject_ref": "poi-fuzhou-1",
            "field_path": "/name",
            "value": "synthetic locked-rail candidate",
            "source_url": "https://example.com/synthetic-locked-rail/1",
            "provider": "synthetic-e2e",
            "queried_at": FIXED_NOW,
            "status": "hypothesis",
            "confidence": 0.5,
            "mode": "static",
            "as_of": None,
            "raw_ref": None,
            "response_hash": None,
            "json_path": None,
        }],
        "unknowns": [],
    }


def _synthetic_point(lng, lat):
    return {"lng": lng, "lat": lat}


def _synthetic_coordinates(lng, lat):
    point = _synthetic_point(lng, lat)
    return {
        "source_crs": "WGS84",
        "native": point,
        "wgs84": point,
        "gcj02": None,
        "conversion": {
            "status": "not-needed", "method": "identity", "version": "1",
            "derived_fields": [], "converted_at": None, "accuracy_m": None,
        },
    }


def _synthetic_claim(claim_id, subject_ref):
    return {
        "claim_id": claim_id,
        "subject_ref": subject_ref,
        "field_path": "/name",
        "value": "synthetic locked-rail candidate",
        "source_url": "https://example.com/synthetic-locked-rail/1",
        "provider": "synthetic-e2e",
        "queried_at": FIXED_NOW,
        "status": "hypothesis",
        "confidence": 0.5,
        "mode": "static",
        "as_of": None,
        "raw_ref": None,
        "response_hash": None,
        "json_path": None,
    }


def journey_two_city_request(locked_rail_services=None, assumptions=None):
    # A two-city, three-calendar-day journey (福州 the night of 9/19, 武夷山 the
    # night of 9/20 through the 9/21 departure day) that ctw journey plan's
    # lodging-boundary segmentation always hard-splits into two atomic Trips: a
    # railless [9/19 福州] Trip and a [9/20-21 武夷山] Trip carrying the 福州 ->
    # 武夷山 rail leg dated TRAVEL_DATE -- mirroring the real 16-day fujian
    # request's 福州 -> 武夷山 -> 福州 lodging chain that produced AN4's
    # cross-atomic-Trip E003 false positive.
    request = {
        "origin": {"ref_id": "city-fuzhou", "name": "福州", "city": "福州"},
        "destinations": [
            {"ref_id": "city-fuzhou", "name": "福州", "city": "福州"},
            {"ref_id": "city-wuyishan", "name": "武夷山", "city": "武夷山"},
        ],
        "start_date": "2026-09-19",
        "end_date": "2026-09-21",
        "travelers": 2,
        "budget_cny": 8000,
        "interests": ["nature"],
        "pace": "balanced",
        "constraints": ["单程"],
        "assumptions": list(assumptions) if assumptions else ["synthetic locked-rail journey acceptance input"],
        "locale": "zh-CN",
        "pasted_notes": None,
    }
    if locked_rail_services is not None:
        request["locked_rail_services"] = locked_rail_services
    return request


def journey_two_city_candidates():
    # Expands locked_candidates() with a matching 福州 POI plus one lodging per
    # city (福州 the night of 9/19, 武夷山 the night of 9/20), giving
    # _lodging_city_by_date a real overnight-stay chain to split the journey on.
    base = locked_candidates()
    fuzhou_poi = {
        "poi_id": "poi-fuzhou-1",
        "name": "三坊七巷",
        "city": "福州",
        "category": "culture",
        "coordinates": _synthetic_coordinates(119.29, 26.08),
        "recommended_duration_minutes": 90,
        "opening_windows": [],
        "price": None,
        "deep_links": ["https://example.com/synthetic-locked-rail/fuzhou-1"],
        "claim_ids": ["claim-fuzhou-poi-1"],
    }
    lodgings = [
        {
            "lodging_id": "lodging-fuzhou-1",
            "name": "福州住宿",
            "city": "福州",
            "area": "鼓楼区",
            "check_in": "2026-09-19",
            "check_out": "2026-09-20",
            "coordinates": _synthetic_coordinates(119.30, 26.09),
            "price": None,
            "deep_links": ["https://example.com/synthetic-locked-rail/fuzhou-lodging-1"],
            "claim_ids": ["claim-fuzhou-lodging-1"],
            "locked": False,
        },
        {
            "lodging_id": "lodging-wuyishan-1",
            "name": "武夷山住宿",
            "city": "武夷山",
            "area": "武夷山风景区",
            "check_in": "2026-09-20",
            "check_out": "2026-09-21",
            "coordinates": _synthetic_coordinates(118.02, 27.76),
            "price": None,
            "deep_links": ["https://example.com/synthetic-locked-rail/wuyishan-lodging-1"],
            "claim_ids": ["claim-wuyishan-lodging-1"],
            "locked": False,
        },
    ]
    return {
        "candidates_version": base["candidates_version"],
        "pois": base["pois"] + [fuzhou_poi],
        "lodgings": lodgings,
        "claims": base["claims"] + [
            _synthetic_claim("claim-fuzhou-poi-1", "poi-fuzhou-1"),
            _synthetic_claim("claim-fuzhou-lodging-1", "lodging-fuzhou-1"),
            _synthetic_claim("claim-wuyishan-lodging-1", "lodging-wuyishan-1"),
        ],
        "unknowns": [],
    }


class LockedRailServiceTests(unittest.TestCase):
    def plan(self, locked_rail_services=None, assumptions=None, rows=ROWS):
        request = locked_request(locked_rail_services, assumptions)
        rail_backend = RailBackend("fixture", ROOT, fixture=rail_fixture(rows))
        return plan_trip(request, locked_candidates(), FixedClock.from_iso(FIXED_NOW), rail_backend)

    def test_locked_service_is_selected_even_when_not_earliest_arrival(self):
        # G1901 (08:50) arrives before the locked G1902 (09:30); without a lock the
        # planner's earliest-arrival default would pick G1901.
        result = self.plan(locked_rail_services=[
            {"service_number": "G1902", "travel_date": TRAVEL_DATE, "depart_time": "07:50"},
        ])
        legs = result.trip["transport_legs"]
        self.assertEqual(1, len(legs))
        self.assertEqual("G1902", legs[0]["service_number"])
        self.assertEqual("2026-09-20T07:50:00+08:00", legs[0]["depart_at"])
        self.assertTrue(legs[0]["locked"], "a leg selected via a locked service must itself be marked locked")
        trip_report = validate_trip(result.trip)
        self.assertEqual([], [item.render() for item in trip_report.errors])

    def test_locked_service_not_found_falls_back_to_placeholder_leg_with_a_specific_reason(self):
        # G9999 never appears in the day's results; the plan must still be produced,
        # with a placeholder leg whose reason names the missing locked service and date.
        result = self.plan(locked_rail_services=[
            {"service_number": "G9999", "travel_date": TRAVEL_DATE},
        ])
        legs = result.trip["transport_legs"]
        self.assertEqual(1, len(legs))
        placeholder = legs[0]
        self.assertIsNone(placeholder["service_number"])
        self.assertEqual("12306-deep-link", placeholder["provider"])
        self.assertFalse(placeholder["locked"])

        service_number_unknown = next(
            item for item in result.trip["unknowns"]
            if item["field_path"] == "/transport_legs/0/service_number"
        )
        reason = service_number_unknown["reason"]
        self.assertIn("locked_service_not_found", reason)
        self.assertIn("G9999", reason, "the reason must name which locked service went missing")
        self.assertIn(TRAVEL_DATE, reason, "the reason must name which date it was missing on")

    def test_locked_service_same_city_two_stations_disambiguated_by_depart_time(self):
        # G1902 resolves to two rows on this date (福州南站 07:50 and 福州站 08:12,
        # both arriving 09:30) exactly like the real 12306 same-city response; only
        # depart_time can tell them apart.
        result = self.plan(locked_rail_services=[
            {"service_number": "G1902", "travel_date": TRAVEL_DATE, "depart_time": "08:12"},
        ])
        leg = result.trip["transport_legs"][0]
        self.assertEqual("G1902", leg["service_number"])
        self.assertEqual("2026-09-20T08:12:00+08:00", leg["depart_at"])
        self.assertTrue(leg["locked"])

    def test_locked_service_ambiguous_without_depart_time_falls_back_to_a_placeholder(self):
        # Same two-row clash as above, but with no depart_time to disambiguate: the
        # planner must not guess which physical row the traveler meant.
        result = self.plan(locked_rail_services=[
            {"service_number": "G1902", "travel_date": TRAVEL_DATE},
        ])
        leg = result.trip["transport_legs"][0]
        self.assertIsNone(leg["service_number"])
        self.assertEqual("12306-deep-link", leg["provider"])
        reason = next(
            item for item in result.trip["unknowns"]
            if item["field_path"] == "/transport_legs/0/service_number"
        )["reason"]
        self.assertIn("locked_service_ambiguous", reason)
        self.assertIn("G1902", reason)

    def test_locked_service_rendered_in_assumptions_no_longer_trips_e003(self):
        mention = "G1902车票已购并锁定：9月20日07:50出发"

        # Without a lock, the planner's earliest-arrival default selects G1901, so the
        # free-text mention of G1902 in assumptions is a train fact the Trip cannot
        # back up: plan_trip itself must refuse to hand back an HTML page (E003).
        with self.assertRaises(ValueError) as raised:
            self.plan(assumptions=[mention])
        self.assertIn("E003", str(raised.exception))
        self.assertIn("G1902", str(raised.exception))

        # With G1902 locked, the planner selects it, so the same rendered mention is
        # now backed by a real Trip fact and E003 must not fire.
        result = self.plan(
            locked_rail_services=[
                {"service_number": "G1902", "travel_date": TRAVEL_DATE, "depart_time": "07:50"},
            ],
            assumptions=[mention],
        )
        self.assertEqual("G1902", result.trip["transport_legs"][0]["service_number"])
        html_report = validate_html(result.html, result.trip)
        self.assertTrue(html_report.ok, [item.render() for item in html_report.errors])

    def test_locked_service_not_found_with_assumption_mention_does_not_trip_e003(self):
        # G1902 never runs this day (rows is G1901-only), so the lock falls back to
        # a placeholder leg -- but the free-text assumption mentioning G1902 is
        # itself a declared, structured fact (request.locked_rail_services), not an
        # unbacked rendered claim, so E003 must not fire over it either.
        mention = "G1902车票已购并锁定：9月20日07:50出发"
        result = self.plan(
            locked_rail_services=[
                {"service_number": "G1902", "travel_date": TRAVEL_DATE, "depart_time": "07:50"},
            ],
            assumptions=[mention],
            rows=(ROWS[0],),
        )
        leg = result.trip["transport_legs"][0]
        self.assertIsNone(leg["service_number"])
        self.assertFalse(leg["locked"])
        reason = next(
            item for item in result.trip["unknowns"]
            if item["field_path"] == "/transport_legs/0/service_number"
        )["reason"]
        self.assertIn("locked_service_not_found", reason)
        self.assertIn("G1902", reason)
        html_report = validate_html(result.html, result.trip)
        self.assertTrue(html_report.ok, [item.render() for item in html_report.errors])


class LockedRailServiceJourneyTests(unittest.TestCase):
    """Covers a defect the single-Trip cases above cannot reach: a real ctw journey
    plan splits a multi-city request into several atomic Trips (journey.py's
    _segment_request deep-copies the whole request -- including assumptions and
    locked_rail_services -- into every one of them), and the leg a locked service
    actually resolves to can land in a *different* atomic Trip than the one whose
    free-text assumption mentions it. AN4's real 16-day fujian journey hit exactly
    this: the railless [9/25 福州] atomic Trip tripped E003 over a mention of
    G1902, the service only the following [9/26 武夷山] atomic Trip actually
    carries (see BLOCKED.md's "AN4" entry).
    """

    def test_locked_service_mention_in_a_railless_atomic_trip_no_longer_trips_e003(self):
        mention = "G1902车票已购并锁定：9月20日07:50出发"
        request = journey_two_city_request(
            locked_rail_services=[
                {"service_number": "G1902", "travel_date": TRAVEL_DATE, "depart_time": "07:50"},
            ],
            assumptions=[mention],
        )
        rail_backend = RailBackend("fixture", ROOT, fixture=rail_fixture(ROWS))
        result = plan_journey(request, journey_two_city_candidates(), FixedClock.from_iso(FIXED_NOW), rail_backend)
        wuyishan_trip = next(
            trip for trip in result.journey["trips"]
            if any(leg["service_number"] == "G1902" for leg in trip["transport_legs"])
        )
        leg = wuyishan_trip["transport_legs"][0]
        self.assertEqual("G1902", leg["service_number"])
        self.assertEqual("2026-09-20T07:50:00+08:00", leg["depart_at"])
        self.assertTrue(leg["locked"])


class LockedRailArriveTimeTests(unittest.TestCase):
    """G5023_ROWS mirrors the real 9/29 武夷山 -> 福州 return leg: both rows depart
    武夷山北站 at the same 10:00 but arrive at two different same-city Fuzhou
    stations, the mirror image of ROWS's G1902 clash (shared arrival, different
    departures) above. depart_time cannot disambiguate this shape; only
    arrive_time can.
    """

    def plan(self, locked_rail_services=None, rows=G5023_ROWS):
        request = return_leg_request(locked_rail_services)
        rail_backend = RailBackend("fixture", ROOT, fixture=rail_fixture(rows))
        return plan_trip(request, return_leg_candidates(), FixedClock.from_iso(FIXED_NOW), rail_backend)

    def test_locked_service_same_city_two_stations_disambiguated_by_arrive_time(self):
        result = self.plan(locked_rail_services=[
            {"service_number": "G5023", "travel_date": TRAVEL_DATE, "arrive_time": "11:13"},
        ])
        leg = result.trip["transport_legs"][0]
        self.assertEqual("G5023", leg["service_number"])
        self.assertEqual("2026-09-20T11:13:00+08:00", leg["arrive_at"])
        self.assertTrue(leg["locked"], "a leg selected via arrive_time disambiguation must itself be marked locked")

    def test_locked_service_ambiguous_same_depart_without_arrive_time_falls_back_to_a_placeholder(self):
        # Same two-row clash as above, but with neither depart_time nor arrive_time
        # to disambiguate: the planner must not guess which physical row the
        # traveler meant, exactly mirroring
        # test_locked_service_ambiguous_without_depart_time_falls_back_to_a_placeholder.
        result = self.plan(locked_rail_services=[
            {"service_number": "G5023", "travel_date": TRAVEL_DATE},
        ])
        leg = result.trip["transport_legs"][0]
        self.assertIsNone(leg["service_number"])
        self.assertFalse(leg["locked"])
        reason = next(
            item for item in result.trip["unknowns"]
            if item["field_path"] == "/transport_legs/0/service_number"
        )["reason"]
        self.assertIn("locked_service_ambiguous", reason)
        self.assertIn("G5023", reason)

    def test_locked_service_arrive_time_pattern_is_enforced_by_schema(self):
        with self.assertRaises(ValueError) as raised:
            self.plan(locked_rail_services=[
                {"service_number": "G5023", "travel_date": TRAVEL_DATE, "arrive_time": "9:5"},
            ])
        self.assertIn("S_PATTERN", str(raised.exception))
        self.assertIn("arrive_time", str(raised.exception))


class LockedRailCandidateUnitTests(unittest.TestCase):
    """Direct coverage of the matching helper for a case the four end-to-end
    scenarios above do not exercise: two locked entries sharing one date but
    naming services that belong to two different routes' own candidate rows.
    """

    def test_multiple_same_date_locks_each_resolve_against_their_own_route_candidates(self):
        candidates = [
            {"service_number": "G1902", "depart_at": "2026-09-20T07:50:00+08:00", "arrive_at": "2026-09-20T09:30:00+08:00"},
            {"service_number": "G1901", "depart_at": "2026-09-20T07:00:00+08:00", "arrive_at": "2026-09-20T08:50:00+08:00"},
        ]
        same_date_locks = [
            {"service_number": "G1902", "travel_date": TRAVEL_DATE},
            {"service_number": "D9999", "travel_date": TRAVEL_DATE},
        ]
        selected, service_names, failure = _locked_rail_candidate(candidates, same_date_locks)
        self.assertIsNone(failure)
        self.assertEqual("G1902", service_names)
        self.assertEqual("G1902", selected["service_number"])

    def test_no_locks_share_the_route_date_returns_a_pure_noop(self):
        selected, service_names, failure = _locked_rail_candidate([], [])
        self.assertIsNone(selected)
        self.assertIsNone(service_names)
        self.assertIsNone(failure)


if __name__ == "__main__":
    unittest.main()
