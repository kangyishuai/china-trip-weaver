from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "plugins" / "china-trip-weaver" / "src"
sys.path.insert(0, str(SRC))

from china_trip_weaver.clock import FixedClock
from china_trip_weaver.mobility import MobilityBackend
from china_trip_weaver.planning import RailBackend, plan_trip
from china_trip_weaver.providers.amap_http import AMapBudgetedTransport, AMapCallBudget, AMapRequestMemo

from tests.test_amap_live import E2E, FIXED_NOW, ScriptedAmapTransport, credentials, load

_CALLS_PATTERN = re.compile(r"calls=(\d+)/\d+")
SHA_E2E = ROOT / "tests" / "fixtures" / "e2e" / "shanghai-weekend-2d"
DEMO = ROOT / "demo"


class PlannerAmapCallsHealthLineTests(unittest.TestCase):
    """The amap health line's calls=<n>/<limit> must count the whole plan_trip run,
    not just the mobility-resolve phase that runs before weather/dining."""

    def setUp(self) -> None:
        self.clock = FixedClock.from_iso(FIXED_NOW)
        self.rail = RailBackend.from_spec("fixture:" + str(E2E / "rail.json"), ROOT)

    def test_reported_calls_match_transport_calls_after_full_plan(self):
        transport = ScriptedAmapTransport()
        mobility = MobilityBackend("live", credentials(), transport)
        result = plan_trip(
            load(E2E / "request.json"),
            load(E2E / "candidates.json"),
            self.clock,
            self.rail,
            mobility,
        )
        amap = next(item for item in result.trip["provider_health"] if item["provider"] == "amap")
        match = _CALLS_PATTERN.search(amap["reason"])
        self.assertIsNotNone(match, amap["reason"])
        reported = int(match.group(1))
        self.assertEqual(
            transport.calls,
            reported,
            "health line reports calls=%d but the transport actually made %d calls (reason=%r)" % (
                reported, transport.calls, amap["reason"],
            ),
        )

    def test_mobility_off_health_line_is_byte_identical(self):
        rail = RailBackend.from_spec(
            "fixture:" + str(ROOT / "tests" / "fixtures" / "providers" / "rail12306" / "empty.json"),
            ROOT,
        )
        result = plan_trip(
            load(DEMO / "request.json"),
            load(DEMO / "candidates.json"),
            FixedClock.from_iso("2026-09-04T00:00:00+08:00"),
            rail,
            MobilityBackend.from_spec("off", ROOT),
        )
        amap = next(item for item in result.trip["provider_health"] if item["provider"] == "amap")
        self.assertEqual(
            "AMap mobility is off; calls=0/80 qps<=2; route matrix uses static estimates",
            amap["reason"],
        )


class PlannerAmapCallsJourneyScopedTransportTests(unittest.TestCase):
    """A Journey segment wraps the shared raw transport in its own
    AMapBudgetedTransport (journey.py's _scoped_mobility_backend); the health
    line must report that segment's own budget count, never the shared
    transport's running total across other segments."""

    def test_segment_reports_only_its_own_scoped_budget_count(self):
        shared_transport = ScriptedAmapTransport()
        memo = AMapRequestMemo()

        # Segment 1: spends real calls on the shared transport via its own budget,
        # simulating an earlier Journey segment that already ran.
        segment_one_budget = AMapCallBudget(max_calls=999, qps=1_000_000)
        segment_one_mobility = MobilityBackend(
            "live", credentials(),
            AMapBudgetedTransport(shared_transport, segment_one_budget, memo),
        )
        plan_trip(
            load(E2E / "request.json"),
            load(E2E / "candidates.json"),
            FixedClock.from_iso(FIXED_NOW),
            RailBackend.from_spec("off", ROOT),
            segment_one_mobility,
        )
        self.assertGreater(shared_transport.calls, 0)
        calls_before_segment_two = shared_transport.calls

        # Segment 2: a fresh budget over the SAME shared transport and memo, exactly
        # as journey.py forks a new AMapCallBudget per segment while reusing both.
        segment_two_budget = AMapCallBudget(max_calls=999, qps=1_000_000)
        segment_two_mobility = MobilityBackend(
            "live", credentials(),
            AMapBudgetedTransport(shared_transport, segment_two_budget, memo),
        )
        result = plan_trip(
            load(SHA_E2E / "request.json"),
            load(SHA_E2E / "candidates.json"),
            FixedClock.from_iso("2026-09-04T00:00:00+08:00"),
            RailBackend.from_spec("off", ROOT),
            segment_two_mobility,
        )
        amap = next(item for item in result.trip["provider_health"] if item["provider"] == "amap")
        match = _CALLS_PATTERN.search(amap["reason"])
        self.assertIsNotNone(match, amap["reason"])
        reported = int(match.group(1))

        self.assertEqual(segment_two_budget.calls, reported)
        self.assertGreater(reported, 0)
        # The defect this book fixes: reading the shared transport's cumulative
        # total instead of the segment's own scoped budget would over-count by
        # everything segment 1 already spent.
        self.assertNotEqual(shared_transport.calls, reported)
        self.assertEqual(shared_transport.calls, calls_before_segment_two + segment_two_budget.calls)


if __name__ == "__main__":
    unittest.main()
