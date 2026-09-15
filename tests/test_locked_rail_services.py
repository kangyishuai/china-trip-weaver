from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "plugins" / "china-trip-weaver" / "src"
sys.path.insert(0, str(SRC))

from china_trip_weaver.clock import FixedClock
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
