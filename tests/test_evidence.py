from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "plugins" / "china-trip-weaver" / "src"
sys.path.insert(0, str(SRC))

from china_trip_weaver.cache import CacheContext, NormalizedCache
from china_trip_weaver.clock import FixedClock
from china_trip_weaver.evidence import EvidenceLedger, make_claim


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

    def test_same_evidence_deduplicates(self):
        ledger = EvidenceLedger()
        first = claim("open", claim_id="claim-a")
        second = claim("open", claim_id="claim-b")
        self.assertEqual("claim-a", ledger.add(first))
        self.assertEqual("claim-a", ledger.add(second))
        self.assertEqual(1, len(ledger.claims()))

    def test_conflicting_values_are_both_preserved_and_marked(self):
        ledger = EvidenceLedger()
        ledger.add(claim("open", provider="source-a", claim_id="claim-a"))
        ledger.add(claim("closed", provider="source-b", claim_id="claim-b"))
        items = ledger.claims()
        self.assertEqual(2, len(items))
        self.assertEqual({"conflict"}, {item["status"] for item in items})
        self.assertEqual({"open", "closed"}, {item["value"] for item in items})

    def test_credentialed_source_url_is_rejected(self):
        with self.assertRaises(ValueError):
            make_claim(
                subject_ref="poi-1", field_path="/name", value="x",
                source_url="https://user:pass@example.invalid/", provider="bad",
                status="verified", confidence=1, mode="live", clock=fixed(),
            )


class CacheTests(unittest.TestCase):
    def context(self, travelers=2):
        return CacheContext(
            provider="amap",
            provider_version="probe-v1",
            capability="route",
            parameters={"from": "poi-a", "to": "poi-b", "mode": "transit"},
            as_of="2026-10-16",
            party={"travelers": travelers},
        )

    def test_context_key_includes_party(self):
        self.assertNotEqual(self.context(1).key(), self.context(2).key())

    def test_cache_round_trip_marks_claim_cached_and_uses_0600(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            root = Path(temporary) / "cache"
            cache = NormalizedCache(root, fixed())
            evidence = claim(35, provider="amap", claim_id="claim-route")
            self.assertTrue(cache.put(self.context(), [{"duration_minutes": 35}], [evidence]))
            hit = cache.get(self.context())
            self.assertIsNotNone(hit)
            self.assertEqual("cached", hit.mode)
            self.assertEqual("cached", hit.claims[0]["mode"])
            if os.name == "posix":
                stored = next(root.glob("*.json"))
                self.assertEqual(0o600, stat.S_IMODE(stored.stat().st_mode))
                self.assertEqual(0o700, stat.S_IMODE(root.stat().st_mode))

    def test_expired_cache_is_not_returned(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            root = Path(temporary) / "cache"
            cache = NormalizedCache(root, fixed())
            cache.put(self.context(), [{"duration_minutes": 35}], [claim(35)], ttl_seconds=1)
            later = NormalizedCache(root, fixed("2026-09-03T12:00:02+08:00"))
            self.assertIsNone(later.get(self.context()))

    def test_disabled_cache_never_writes(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            root = Path(temporary) / "cache"
            cache = NormalizedCache(root, fixed(), enabled=False)
            self.assertFalse(cache.put(self.context(), [], [], ttl_seconds=1))
            self.assertFalse(root.exists())

    def test_cache_rejects_credentials_and_personal_fields(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            cache = NormalizedCache(Path(temporary) / "cache", fixed())
            with self.assertRaises(ValueError):
                cache.put(self.context(), [{"password": "not-a-real-value"}], [], ttl_seconds=1)


if __name__ == "__main__":
    unittest.main()

