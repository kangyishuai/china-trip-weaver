"""Stable public error taxonomy and retry policy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional


@dataclass(frozen=True)
class ErrorPolicy:
    health_status: str
    retryable: bool
    public_message: str


ERROR_POLICIES: Mapping[str, ErrorPolicy] = {
    "invalid_request": ErrorPolicy("degraded", False, "The request does not satisfy the provider contract."),
    "credential_missing": ErrorPolicy("missing", False, "This provider is not configured; a keyless fallback will be used."),
    "credential_expired": ErrorPolicy("expired", False, "The provider credential has expired; no credential was requested in chat."),
    "forbidden": ErrorPolicy("forbidden", False, "The provider refused this read-only request."),
    "rate_limited": ErrorPolicy("rate_limited", True, "The provider rate limit was reached."),
    "timeout": ErrorPolicy("degraded", True, "The provider exceeded its deadline."),
    "network": ErrorPolicy("degraded", True, "The provider could not be reached."),
    "upstream_5xx": ErrorPolicy("degraded", True, "The provider reported a temporary failure."),
    "contract_mismatch": ErrorPolicy("contract_mismatch", False, "The provider response contract changed; parsing stopped safely."),
    "no_results": ErrorPolicy("ready", False, "The provider returned no matching results."),
    "policy_blocked": ErrorPolicy("unavailable", False, "The requested action crosses the read-only boundary."),
    "internal": ErrorPolicy("degraded", False, "China Trip Weaver could not complete this provider step."),
}


class CTWError(Exception):
    """Error safe to carry across adapters without exposing raw provider data."""

    def __init__(
        self,
        error_class: str,
        code: str,
        message: Optional[str] = None,
        details: Optional[Mapping[str, Any]] = None,
    ) -> None:
        if error_class not in ERROR_POLICIES:
            raise ValueError("unknown error class: %s" % error_class)
        self.error_class = error_class
        self.code = code
        self.policy = ERROR_POLICIES[error_class]
        self.public_message = message or self.policy.public_message
        self.details: Dict[str, Any] = dict(details or {})
        super().__init__("%s: %s" % (code, self.public_message))

    @property
    def retryable(self) -> bool:
        return self.policy.retryable

    @property
    def health_status(self) -> str:
        return self.policy.health_status


class ValidationFailure(CTWError):
    def __init__(self, message: str = "Trip validation failed.") -> None:
        super().__init__("invalid_request", "TRIP_INVALID", message)

