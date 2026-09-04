"""Optional authenticated AnySearch adapter; anonymous auto-registration is blocked."""

from __future__ import annotations

from typing import Any, List, Mapping

from ..clock import Clock
from ..contracts import ProviderRequest
from ..evidence import make_claim
from .base import BaseAdapter, ContractMismatch, Normalization, ProviderFailure, safe_https_url, sanitize_text, stable_id


class AnySearchAdapter(BaseAdapter):
    provider = "anysearch"
    provider_version = "runtime-probe-v1"
    capabilities = ("research",)
    required_secret_names = ("ANYSEARCH_API_KEY",)
    allow_keyless = False

    def normalize(self, body: Any, request: ProviderRequest, clock: Clock) -> Normalization:
        if not isinstance(body, dict):
            raise ContractMismatch("AnySearch response is not an object")
        if body.get("auto_registered"):
            raise ProviderFailure("policy_blocked", "anonymous auto-registration is forbidden")
        data = body.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("results"), list) or not isinstance(body.get("usage"), dict):
            raise ContractMismatch("AnySearch structured response or usage fields changed")
        city = sanitize_text(request.parameters["city"], 80)
        items: List[Mapping[str, Any]] = []
        claims: List[Mapping[str, Any]] = []
        for raw in data["results"]:
            url = safe_https_url(raw["url"])
            title = sanitize_text(raw["title"], 160)
            poi_id = stable_id("poi-anysearch", url, title)
            evidence = make_claim(
                subject_ref=poi_id, field_path="/name", value=title,
                source_url=url, provider=self.provider,
                status="partial", confidence=0.65, mode="static", clock=clock,
            )
            items.append({
                "poi_id": poi_id, "name": title, "city": city,
                "category": "search-result", "coordinates": None,
                "recommended_duration_minutes": None, "opening_windows": [],
                "price": None, "deep_links": [url],
                "claim_ids": [evidence["claim_id"]],
            })
            claims.append(evidence)
        return Normalization(tuple(items), tuple(claims), mode="static")
