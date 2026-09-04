"""Shared deadlines, fixture transport, sanitization, and failure mapping."""

from __future__ import annotations

import copy
import hashlib
import html
import json
import math
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
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
MAX_RATE_LIMIT_RETRIES = 1
MAX_RETRY_DELAY_SECONDS = 2.0
DEFAULT_RETRY_DELAY_SECONDS = 0.25


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
        transport_retries = 0
        rate_limit_retries = 0
        retry_delays: List[float] = []
        attempt = 0
        while True:
            attempt += 1
            _emit_progress(
                context.transport,
                event="query",
                provider=self.provider,
                capability=request.capability,
                attempt=attempt,
            )
            try:
                envelope = context.transport.execute(self.provider, request)
                status_error = self._http_error(envelope.status_code)
                if status_error == "rate_limited":
                    last_error = status_error
                    _emit_progress(
                        context.transport,
                        event="degrade",
                        provider=self.provider,
                        capability=request.capability,
                        error_class=status_error,
                        attempt=attempt,
                    )
                    retry_enabled = bool(getattr(context.transport, "retry_rate_limits", False))
                    if retry_enabled and rate_limit_retries < MAX_RATE_LIMIT_RETRIES:
                        delay = _retry_delay_seconds(envelope.headers)
                        rate_limit_retries += 1
                        retry_delays.append(delay)
                        _emit_progress(
                            context.transport,
                            event="retry",
                            provider=self.provider,
                            capability=request.capability,
                            error_class=status_error,
                            attempt=attempt + 1,
                            delay_seconds=delay,
                        )
                        if delay:
                            time.sleep(delay)
                        continue
                    return self._failure_with_retry(
                        status_error,
                        "provider HTTP %d" % envelope.status_code,
                        request,
                        context.clock,
                        rate_limit_retries,
                        retry_delays,
                        context.transport,
                    )
                if envelope.status_code >= 500:
                    last_error = "upstream_5xx"
                    transport_retries += 1
                    if transport_retries < self.max_attempts:
                        continue
                break
            except ProviderTimeout:
                last_error = "timeout"
                transport_retries += 1
                if transport_retries >= self.max_attempts:
                    return self._failure_with_retry(
                        "timeout", "provider deadline exceeded", request, context.clock,
                        rate_limit_retries, retry_delays, context.transport,
                    )
            except ProviderNetworkError:
                last_error = "network"
                transport_retries += 1
                if transport_retries >= self.max_attempts:
                    return self._failure_with_retry(
                        "network", "provider network failure", request, context.clock,
                        rate_limit_retries, retry_delays, context.transport,
                    )
            except ProviderRateLimited:
                return self._failure_with_retry(
                    "rate_limited", "local provider call budget was exhausted", request, context.clock,
                    rate_limit_retries, retry_delays, context.transport,
                )
            except ContractMismatch as exc:
                return self._failure_with_retry(
                    "contract_mismatch", str(exc), request, context.clock,
                    rate_limit_retries, retry_delays, context.transport,
                )
        if envelope is None:
            return self._failure_with_retry(
                last_error or "internal", "provider did not return a response", request, context.clock,
                rate_limit_retries, retry_delays, context.transport,
            )

        status_error = self._http_error(envelope.status_code)
        if status_error:
            return self._failure_with_retry(
                status_error, "provider HTTP %d" % envelope.status_code, request, context.clock,
                rate_limit_retries, retry_delays, context.transport,
            )
        try:
            normalized = self.normalize(envelope.body, request, context.clock)
            for claim in normalized.claims:
                validate_claim(claim)
        except ProviderFailure as exc:
            return self._failure_with_retry(
                exc.error_class, exc.message, request, context.clock,
                rate_limit_retries, retry_delays, context.transport,
            )
        except (ContractMismatch, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            return self._failure_with_retry(
                "contract_mismatch", str(exc), request, context.clock,
                rate_limit_retries, retry_delays, context.transport,
            )

        queried_at = isoformat_seconds(context.clock)
        response_hash = "sha256:" + hashlib.sha256(canonical_json(envelope.body).encode("utf-8")).hexdigest()
        retry_reason = _retry_reason(rate_limit_retries, retry_delays)
        retry_warnings = ("rate_limit_retry",) if rate_limit_retries else ()
        if not normalized.items and not normalized.claims:
            return AdapterResult.build(
                provider=self.provider,
                provider_version=self.provider_version,
                capability=request.capability,
                mode=normalized.mode,
                queried_at=queried_at,
                normalized_items=(),
                claims=(),
                health=self._health("ready", "no_results" + retry_reason, normalized.mode, context.clock),
                warnings=normalized.warnings + ("no_results",) + retry_warnings,
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
            health=self._health(
                "ready", "contract probe and normalization passed" + retry_reason,
                normalized.mode, context.clock,
            ),
            warnings=normalized.warnings + retry_warnings,
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

    def _failure_with_retry(
        self,
        error_class: str,
        reason: str,
        request: ProviderRequest,
        clock: Clock,
        rate_limit_retries: int,
        retry_delays: Sequence[float],
        transport: ProviderTransport,
    ) -> AdapterResult:
        _emit_progress(
            transport,
            event="degrade",
            provider=self.provider,
            capability=request.capability,
            error_class=error_class,
        )
        retry_reason = _retry_reason(rate_limit_retries, retry_delays)
        result = self._failure(error_class, reason + retry_reason, request, clock)
        if not rate_limit_retries:
            return result
        return AdapterResult.build(
            provider=result.provider,
            provider_version=result.provider_version,
            capability=result.capability,
            mode=result.mode,
            queried_at=result.queried_at,
            normalized_items=result.normalized_items,
            claims=result.claims,
            health=result.health,
            warnings=result.warnings + (("rate_limit_retry",) if "rate_limit_retry" not in result.warnings else ()),
            raw_ref=result.raw_ref,
            response_hash=result.response_hash,
            error_class=result.error_class,
        )

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


def _retry_delay_seconds(headers: Mapping[str, str]) -> float:
    value = next((raw for name, raw in headers.items() if name.lower() == "retry-after"), None)
    if value is None:
        return DEFAULT_RETRY_DELAY_SECONDS
    try:
        seconds = float(value.strip())
    except (TypeError, ValueError, AttributeError):
        try:
            retry_at = parsedate_to_datetime(str(value))
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            seconds = (retry_at - datetime.now(timezone.utc)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            seconds = DEFAULT_RETRY_DELAY_SECONDS
    if not math.isfinite(seconds):
        seconds = DEFAULT_RETRY_DELAY_SECONDS
    return max(0.0, min(seconds, MAX_RETRY_DELAY_SECONDS))


def _retry_reason(retries: int, delays: Sequence[float]) -> str:
    if not retries:
        return ""
    rendered = ",".join("%g" % value for value in delays)
    return "; rate_limit_retries=%d; retry_delays_seconds=%s" % (retries, rendered)


def _emit_progress(transport: ProviderTransport, **event: Any) -> None:
    emitter = getattr(transport, "progress", None)
    if not callable(emitter):
        return
    try:
        emitter(dict(event))
    except Exception:
        # Progress is optional observability and must never change provider behavior.
        return
