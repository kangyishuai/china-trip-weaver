from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "plugins" / "china-trip-weaver" / "src"
sys.path.insert(0, str(SRC))

from china_trip_weaver.clock import FixedClock
from china_trip_weaver.evidence import make_claim


def fixed(value: str = "2026-09-03T12:00:00+08:00") -> FixedClock:
    return FixedClock.from_iso(value)


def claim(value, provider="official-web", claim_id=None):
    return make_claim(
        subject_ref="poi-1",
        field_path="/opening_windows/0",
        value=value,
        source_url="https://example.invalid/official",
        provider=provider,
        status="verified",
        confidence=0.9,
        mode="live",
        clock=fixed(),
        claim_id=claim_id,
    )


class EvidenceTests(unittest.TestCase):
    def test_claim_contains_complete_evidence_fields(self):
        item = claim("09:00-17:00", claim_id="claim-hours")
        self.assertEqual("https://example.invalid/official", item["source_url"])
        self.assertEqual("official-web", item["provider"])
        self.assertEqual("2026-09-03T12:00:00+08:00", item["queried_at"])
        self.assertEqual("verified", item["status"])
        self.assertEqual(0.9, item["confidence"])

    def test_claim_id_is_deterministic_for_fixed_clock(self):
        self.assertEqual(claim("open")["claim_id"], claim("open")["claim_id"])

    def test_credentialed_source_url_is_rejected(self):
        with self.assertRaises(ValueError):
            make_claim(
                subject_ref="poi-1", field_path="/name", value="x",
                source_url="https://user:pass@example.invalid/", provider="bad",
                status="verified", confidence=1, mode="live", clock=fixed(),
            )


if __name__ == "__main__":
    unittest.main()

