"""Bounded standard-library HTTP transport for the AnySearch MCP endpoint."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, Mapping, Optional

from ..contracts import ProviderRequest
from ..credentials import CredentialResolution
from .base import (
    ContractMismatch,
    ProviderEnvelope,
    ProviderNetworkError,
    ProviderTimeout,
)


ANYSEARCH_ORIGIN = "https://api.anysearch.com"
ANYSEARCH_ENDPOINT = ANYSEARCH_ORIGIN + "/mcp"
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_RESULTS_DEFAULT = 10
MAX_RESULTS_CEILING = 50


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        del req, fp, code, msg, headers, newurl
        return None


class AnySearchHTTPTransport:
    """Map research ProviderRequests to the pinned AnySearch MCP JSON-RPC endpoint."""

    retry_rate_limits = True

    def __init__(
        self,
        credentials: CredentialResolution,
        *,
        opener: Optional[Callable[..., Any]] = None,
    ) -> None:
        self.credentials = credentials
        self._open = opener or urllib.request.build_opener(_NoRedirectHandler()).open

    def execute(self, provider: str, request: ProviderRequest) -> ProviderEnvelope:
        if provider != "anysearch":
            raise ContractMismatch("AnySearch HTTP transport is restricted to anysearch")
        if request.capability != "research":
            raise ContractMismatch("unsupported AnySearch capability")
        if request.deadline_ms <= 0:
            raise ContractMismatch("AnySearch deadline must be positive")
        key = self.credentials.get("ANYSEARCH_API_KEY")
        if not key:
            raise ContractMismatch("AnySearch transport requires configured credentials")
        query = _required_text(request.parameters, "query")
        max_results = _bounded_max_results(request.parameters.get("max_results", MAX_RESULTS_DEFAULT))

        payload = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "search",
                    "arguments": {"query": query, "max_results": max_results},
                },
            },
            ensure_ascii=False,
        ).encode("utf-8")
        http_request = urllib.request.Request(
            ANYSEARCH_ENDPOINT,
            data=payload,
            headers={
                "Authorization": "Bearer " + key,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "ChinaTripWeaver/0.1",
            },
            method="POST",
        )
        timeout = request.deadline_ms / 1000.0
        try:
            response = self._open(http_request, timeout=timeout)
            with response:
                final_url = response.geturl() if hasattr(response, "geturl") else ANYSEARCH_ENDPOINT
                if urllib.parse.urlsplit(final_url).hostname != "api.anysearch.com":
                    raise ProviderNetworkError("AnySearch redirected outside its pinned origin")
                status = int(getattr(response, "status", response.getcode()))
                raw = _read_bounded(response)
                headers = _safe_headers(getattr(response, "headers", {}))
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            raw = _read_bounded(exc)
            headers = _safe_headers(exc.headers or {})
        except (socket.timeout, TimeoutError) as exc:
            raise ProviderTimeout("AnySearch request deadline exceeded") from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, (socket.timeout, TimeoutError)):
                raise ProviderTimeout("AnySearch request deadline exceeded") from exc
            raise ProviderNetworkError("AnySearch network request failed") from exc
        except OSError as exc:
            raise ProviderNetworkError("AnySearch network request failed") from exc

        body: Any = {}
        if raw:
            try:
                body = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                if status < 400:
                    raise ContractMismatch("AnySearch response is not UTF-8 JSON") from exc
        if status < 400 and not isinstance(body, dict):
            raise ContractMismatch("AnySearch response root is not an object")
        return ProviderEnvelope(status_code=status, body=body, headers=headers, raw_ref=ANYSEARCH_ENDPOINT)


def _read_bounded(response: Any) -> bytes:
    raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ContractMismatch("AnySearch response exceeds 4 MiB")
    return raw


def _safe_headers(headers: Mapping[str, Any]) -> Mapping[str, str]:
    result: Dict[str, str] = {}
    for name in ("Content-Type", "Retry-After"):
        value = headers.get(name) if hasattr(headers, "get") else None
        if value is not None:
            result[name] = str(value)[:200]
    return result


def _required_text(values: Mapping[str, Any], name: str) -> str:
    value = values.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ContractMismatch("AnySearch request is missing %s" % name)
    return value.strip()


def _bounded_max_results(value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= MAX_RESULTS_CEILING:
        raise ContractMismatch("AnySearch max_results must be between 1 and %d" % MAX_RESULTS_CEILING)
    return value
