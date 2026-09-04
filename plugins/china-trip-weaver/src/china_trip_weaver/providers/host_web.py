"""Normalize user-visible host web results into sourced POI candidates."""

from __future__ import annotations

from typing import Any, List, Mapping

from ..clock import Clock
from ..contracts import ProviderRequest
from ..evidence import make_claim
from .base import BaseAdapter, ContractMismatch, Normalization, safe_https_url, sanitize_text, stable_id


class HostWebAdapter(BaseAdapter):
    provider = "host-web"
    provider_version = "host-runtime"
    capabilities = ("research",)

    def normalize(self, body: Any, request: ProviderRequest, clock: Clock) -> Normalization:
        if not isinstance(body, dict) or not isinstance(body.get("results"), list):
            raise ContractMismatch("host web results envelope changed")
        items: List[Mapping[str, Any]] = []
        claims: List[Mapping[str, Any]] = []
        city = sanitize_text(request.parameters.get("city", "unknown"), 80)
        for raw in body["results"]:
            if not isinstance(raw, dict):
                raise ContractMismatch("host web result is not an object")
            url = safe_https_url(raw.get("url"))
            title = sanitize_text(raw.get("title"), 160)
            poi_id = stable_id("poi-web", url, title)
            evidence = make_claim(
                subject_ref=poi_id,
                field_path="/name",
                value=title,
                source_url=url,
                provider=self.provider,
                status="verified" if raw.get("official") else "partial",
                confidence=0.9 if raw.get("official") else 0.6,
                mode="static",
                clock=clock,
                as_of=raw.get("published_at"),
            )
            items.append({
                "poi_id": poi_id,
                "name": title,
                "city": city,
                "category": sanitize_text(raw.get("category", "research"), 80),
                "coordinates": None,
                "recommended_duration_minutes": None,
                "opening_windows": [],
                "price": None,
                "deep_links": [url],
                "claim_ids": [evidence["claim_id"]],
            })
            claims.append(evidence)
        return Normalization(tuple(items), tuple(claims), mode="static")

