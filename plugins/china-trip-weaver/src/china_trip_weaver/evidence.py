"""Claim construction, deduplication, and conflict preservation."""

from __future__ import annotations

import copy
import hashlib
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlsplit

from .clock import Clock, isoformat_seconds
from .contracts import canonical_json


CLAIM_STATUSES = frozenset(("verified", "partial", "hypothesis", "unknown", "stale", "conflict", "unavailable", "mock"))
DATA_MODES = frozenset(("live", "cached", "static", "mock"))


def _safe_https_url(value: str) -> bool:
    parsed = urlsplit(value)
    return parsed.scheme == "https" and bool(parsed.netloc) and not parsed.username and not parsed.password


def make_claim(
    *,
    subject_ref: str,
    field_path: str,
    value: Any,
    source_url: str,
    provider: str,
    status: str,
    confidence: float,
    mode: str,
    clock: Clock,
    as_of: Optional[str] = None,
    raw_ref: Optional[str] = None,
    response_hash: Optional[str] = None,
    json_path: Optional[str] = None,
    claim_id: Optional[str] = None,
) -> Dict[str, Any]:
    if not subject_ref or not field_path.startswith("/") or not provider:
        raise ValueError("claim subject, field path, and provider are required")
    if not _safe_https_url(source_url):
        raise ValueError("claim source URL must be credential-free HTTPS")
    if status not in CLAIM_STATUSES or mode not in DATA_MODES:
        raise ValueError("invalid claim status or mode")
    if not 0 <= confidence <= 1:
        raise ValueError("claim confidence must be between 0 and 1")
    queried_at = isoformat_seconds(clock)
    if claim_id is None:
        digest_input = [subject_ref, field_path, value, source_url, provider, queried_at]
        claim_id = "claim-" + hashlib.sha256(canonical_json(digest_input).encode("utf-8")).hexdigest()[:16]
    return {
        "claim_id": claim_id,
        "subject_ref": subject_ref,
        "field_path": field_path,
        "value": copy.deepcopy(value),
        "source_url": source_url,
        "provider": provider,
        "queried_at": queried_at,
        "status": status,
        "confidence": confidence,
        "mode": mode,
        "as_of": as_of,
        "raw_ref": raw_ref,
        "response_hash": response_hash,
        "json_path": json_path,
    }


def validate_claim(claim: Mapping[str, Any]) -> None:
    required = {
        "claim_id", "subject_ref", "field_path", "value", "source_url", "provider",
        "queried_at", "status", "confidence", "mode", "as_of", "raw_ref",
        "response_hash", "json_path",
    }
    if set(claim) != required:
        raise ValueError("claim fields do not match the v1 contract")
    if claim["status"] not in CLAIM_STATUSES or claim["mode"] not in DATA_MODES:
        raise ValueError("invalid claim status or mode")
    if not _safe_https_url(claim["source_url"]):
        raise ValueError("claim source URL must be credential-free HTTPS")
    if not 0 <= claim["confidence"] <= 1:
        raise ValueError("invalid confidence")


class EvidenceLedger:
    def __init__(self, claims: Sequence[Mapping[str, Any]] = ()) -> None:
        self._claims: List[Dict[str, Any]] = []
        for claim in claims:
            self.add(claim)

    def add(self, claim: Mapping[str, Any]) -> str:
        validate_claim(claim)
        candidate = copy.deepcopy(dict(claim))
        for existing in self._claims:
            if existing["claim_id"] == candidate["claim_id"]:
                if canonical_json(existing) != canonical_json(candidate):
                    raise ValueError("claim_id collision")
                return existing["claim_id"]
            same_fact = (
                existing["subject_ref"] == candidate["subject_ref"]
                and existing["field_path"] == candidate["field_path"]
            )
            same_evidence = same_fact and existing["provider"] == candidate["provider"] and canonical_json(existing["value"]) == canonical_json(candidate["value"])
            if same_evidence:
                return existing["claim_id"]
            if same_fact and canonical_json(existing["value"]) != canonical_json(candidate["value"]):
                existing["status"] = "conflict"
                candidate["status"] = "conflict"
        self._claims.append(candidate)
        return candidate["claim_id"]

    def claims(self) -> Tuple[Mapping[str, Any], ...]:
        return tuple(copy.deepcopy(self._claims))

    def for_subject(self, subject_ref: str) -> Tuple[Mapping[str, Any], ...]:
        return tuple(copy.deepcopy([claim for claim in self._claims if claim["subject_ref"] == subject_ref]))

