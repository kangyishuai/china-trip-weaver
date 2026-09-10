"""Optional authenticated AnySearch MCP adapter; anonymous auto-registration is blocked."""

from __future__ import annotations

import re
from typing import Any, List, Mapping

from ..clock import Clock
from ..contracts import ProviderRequest
from ..evidence import make_claim
from .base import BaseAdapter, ContractMismatch, Normalization, safe_https_url, sanitize_text, stable_id


_HEADER_RE = re.compile(r"^## Search Results \((\d+) results, \d+ms\)", re.MULTILINE)
_ITEM_RE = re.compile(
    r"^### \d+\. (?P<title>[^\n]+)\n- \*\*URL\*\*: (?P<url>[^\n]+)\n- (?P<summary>[^\n]+)$",
    re.MULTILINE,
)


class AnySearchAdapter(BaseAdapter):
    provider = "anysearch"
    provider_version = "mcp-search-v1"
    capabilities = ("research",)
    required_secret_names = ("ANYSEARCH_API_KEY",)
    allow_keyless = False

    def normalize(self, body: Any, request: ProviderRequest, clock: Clock) -> Normalization:
        if not isinstance(body, dict) or body.get("jsonrpc") != "2.0":
            raise ContractMismatch("AnySearch response is not a JSON-RPC 2.0 envelope")
        result = body.get("result")
        if not isinstance(result, dict):
            raise ContractMismatch("AnySearch response is missing a result")
        content = result.get("content")
        if not isinstance(content, list) or len(content) != 1:
            raise ContractMismatch("AnySearch result content is not a single block")
        block = content[0]
        if not isinstance(block, dict) or block.get("type") != "text" or not isinstance(block.get("text"), str):
            raise ContractMismatch("AnySearch result content is not a text block")

        text = block["text"]
        header = _HEADER_RE.search(text)
        if header is None:
            raise ContractMismatch("AnySearch results header is missing or malformed")
        declared_count = int(header.group(1))
        matches = list(_ITEM_RE.finditer(text))
        if len(matches) != declared_count:
            raise ContractMismatch("AnySearch declared result count does not match parsed entries")

        city = sanitize_text(request.parameters["city"], 80)
        items: List[Mapping[str, Any]] = []
        claims: List[Mapping[str, Any]] = []
        for match in matches:
            title = sanitize_text(match.group("title"), 160)
            url = safe_https_url(match.group("url").strip())
            summary = sanitize_text(match.group("summary"), 300)
            poi_id = stable_id("poi-anysearch", url, title)
            evidence = make_claim(
                subject_ref=poi_id, field_path="/name", value={"name": title, "summary": summary},
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
