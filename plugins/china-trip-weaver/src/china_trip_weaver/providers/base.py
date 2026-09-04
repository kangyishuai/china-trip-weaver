"""Shared deadlines, fixture transport, sanitization, and failure mapping."""

from __future__ import annotations

import copy
import hashlib
import html
import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any, Callable, Dict, List, Mapping, Optional, Protocol, Sequence, Tuple
from urllib.parse import urlsplit

from ..clock import Clock, isoformat_seconds
from ..contracts import AdapterResult, ProviderRequest, canonical_json
from ..credentials import CredentialResolution
from ..errors import ERROR_POLICIES
from ..evidence import validate_claim


ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
AUTH_RE = re.compile(r"(?i)authorization\s*:\s*[^\s]+(?:\s+[^\s]+)?")
SECRET_PREFIXES = (
    re.compile("gh" + r"[pousr]_[A-Za-z0-9]{20,}"),
    re.compile("sk" + r"-[A-Za-z0-9]{20,}"),
)


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def sanitize_text(value: Any, max_length: int = 500) -> str:
    if not isinstance(value, str):
        raise ContractMismatch("text field is not a string")
    clean = ANSI_RE.sub("", value)
    parser = _TextExtractor()
    try:
        parser.feed(clean)
        clean = " ".join(parser.parts)
    except Exception as exc:
        raise ContractMismatch("malformed provider markup") from exc
    clean = AUTH_RE.sub("[REDACTED]", clean)
    for pattern in SECRET_PREFIXES:
        clean = pattern.sub("[REDACTED]", clean)
    clean = " ".join(clean.split())
    return clean[:max_length]


def safe_https_url(value: Any) -> str:
    if not isinstance(value, str):
        raise ContractMismatch("URL is not a string")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ContractMismatch("URL is not credential-free HTTPS")
    if any(key.lower() in ("key", "api_key", "token", "access_token", "secret", "password") for key in _query_keys(parsed.query)):
        raise ContractMismatch("URL contains a forbidden credential parameter")
    return value


def _query_keys(query: str) -> Sequence[str]:
    return [part.split("=", 1)[0] for part in query.split("&") if part]


def stable_id(prefix: str, *parts: Any) -> str:
    digest = hashlib.sha256(canonical_json(list(parts)).encode("utf-8")).hexdigest()[:12]
    return "%s-%s" % (prefix, digest)


class ContractMismatch(Exception):
    pass


class ProviderFailure(Exception):
    def __init__(self, error_class: str, message: str) -> None:
        self.error_class = error_class
        self.message = message
        super().__init__(message)


class ProviderTimeout(Exception):
    pass


class ProviderNetworkError(Exception):
    pass


class ProviderRateLimited(Exception):
    pass


@dataclass(frozen=True)
class ProviderEnvelope:
    status_code: int
    body: Any
    headers: Mapping[str, str]
    raw_ref: Optional[str] = None


class ProviderTransport(Protocol):
    def execute(self, provider: str, request: ProviderRequest) -> ProviderEnvelope:
        ...


class ReplayTransport:
    """Deterministic transport used by the checked-in raw fixture corpus."""

    def __init__(self, specification: Mapping[str, Any], raw_ref: Optional[str] = None) -> None:
        self.specification = copy.deepcopy(dict(specification))
        self.raw_ref = raw_ref
        self.calls = 0

    def execute(self, provider: str, request: ProviderRequest) -> ProviderEnvelope:
        del provider, request
        self.calls += 1
        kind = self.specification.get("kind", "response")
        if kind == "timeout":
            raise ProviderTimeout("fixture timeout")
        if kind == "network":
            raise ProviderNetworkError("fixture network error")
        if kind != "response":
            raise ContractMismatch("unknown fixture transport kind")
        return ProviderEnvelope(
            status_code=int(self.specification.get("status_code", 200)),
            body=copy.deepcopy(self.specification.get("body")),
            headers=copy.deepcopy(self.specification.get("headers", {})),
            raw_ref=self.raw_ref,
        )


@dataclass(frozen=True)
class ProviderContext:
    clock: Clock
    credentials: CredentialResolution
    transport: ProviderTransport


@dataclass(frozen=True)
class Normalization:
    items: Tuple[Mapping[str, Any], ...]
    claims: Tuple[Mapping[str, Any], ...]
    warnings: Tuple[str, ...] = ()
    mode: str = "live"


class BaseAdapter:
    provider = "base"
    provider_version = "0"
    capabilities: Tuple[str, ...] = ()
    required_secret_names: Tuple[str, ...] = ()
    allow_keyless = True
    max_attempts = 2

    def normalize(self, body: Any, request: ProviderRequest, clock: Clock) -> Normalization:
        raise NotImplementedError

    def query(self, request: ProviderRequest, context: ProviderContext) -> AdapterResult:
        if request.capability not in self.capabilities:
            return self._failure("invalid_request", "capability is not supported", request, context.clock)
        if request.deadline_ms <= 0:
            return self._failure("invalid_request", "deadline must be positive", request, context.clock)
        if self.required_secret_names and not self.allow_keyless:
            if not any(context.credentials.get(name) for name in self.required_secret_names):
                return self._failure("credential_missing", "required provider credential is missing", request, context.clock)

        envelope: Optional[ProviderEnvelope] = None
        last_error: Optional[str] = None
        for attempt in range(self.max_attempts):
            try:
                envelope = context.transport.execute(self.provider, request)
                if envelope.status_code >= 500:
                    last_error = "upstream_5xx"
                    if attempt + 1 < self.max_attempts:
                        continue
                break
            except ProviderTimeout:
                last_error = "timeout"
                if attempt + 1 >= self.max_attempts:
                    return self._failure("timeout", "provider deadline exceeded", request, context.clock)
            except ProviderNetworkError:
                last_error = "network"
                if attempt + 1 >= self.max_attempts:
                    return self._failure("network", "provider network failure", request, context.clock)
            except ProviderRateLimited:
                return self._failure("rate_limited", "local provider call budget was exhausted", request, context.clock)
            except ContractMismatch as exc:
                return self._failure("contract_mismatch", str(exc), request, context.clock)
        if envelope is None:
            return self._failure(last_error or "internal", "provider did not return a response", request, context.clock)

        status_error = self._http_error(envelope.status_code)
        if status_error:
            return self._failure(status_error, "provider HTTP %d" % envelope.status_code, request, context.clock)
        try:
            normalized = self.normalize(envelope.body, request, context.clock)
            for claim in normalized.claims:
                validate_claim(claim)
        except ProviderFailure as exc:
            return self._failure(exc.error_class, exc.message, request, context.clock)
        except (ContractMismatch, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            return self._failure("contract_mismatch", str(exc), request, context.clock)

        queried_at = isoformat_seconds(context.clock)
        response_hash = "sha256:" + hashlib.sha256(canonical_json(envelope.body).encode("utf-8")).hexdigest()
        if not normalized.items and not normalized.claims:
            return AdapterResult.build(
                provider=self.provider,
                provider_version=self.provider_version,
                capability=request.capability,
                mode=normalized.mode,
                queried_at=queried_at,
                normalized_items=(),
                claims=(),
                health=self._health("ready", "no_results", normalized.mode, context.clock),
                warnings=normalized.warnings + ("no_results",),
                raw_ref=envelope.raw_ref,
                response_hash=response_hash,
                error_class="no_results",
            )
        return AdapterResult.build(
            provider=self.provider,
            provider_version=self.provider_version,
            capability=request.capability,
            mode=normalized.mode,
            queried_at=queried_at,
            normalized_items=normalized.items,
            claims=normalized.claims,
            health=self._health("ready", "contract probe and normalization passed", normalized.mode, context.clock),
            warnings=normalized.warnings,
            raw_ref=envelope.raw_ref,
            response_hash=response_hash,
        )

    @staticmethod
    def _http_error(status: int) -> Optional[str]:
        if status in (401, 403):
            return "forbidden"
        if status in (402, 429):
            return "rate_limited"
        if status >= 500:
            return "upstream_5xx"
        if status >= 400:
            return "invalid_request"
        return None

    def _health(self, status: str, reason: str, mode: str, clock: Clock) -> Mapping[str, Any]:
        return {
            "provider": self.provider,
            "version": self.provider_version,
            "mode": mode,
            "status": status,
            "checked_at": isoformat_seconds(clock),
            "capabilities": list(self.capabilities),
            "reason": sanitize_text(reason),
        }

    def _failure(self, error_class: str, reason: str, request: ProviderRequest, clock: Clock) -> AdapterResult:
        policy = ERROR_POLICIES[error_class]
        return AdapterResult.build(
            provider=self.provider,
            provider_version=self.provider_version,
            capability=request.capability,
            mode="static",
            queried_at=isoformat_seconds(clock),
            normalized_items=(),
            claims=(),
            health=self._health(policy.health_status, "%s: %s" % (error_class, reason), "static", clock),
            warnings=(error_class,),
            error_class=error_class,
        )
