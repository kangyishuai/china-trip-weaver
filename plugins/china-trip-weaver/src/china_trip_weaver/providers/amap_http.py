"""Bounded standard-library HTTP transport for AMap Web Service APIs."""

from __future__ import annotations

import copy
import json
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from ..contracts import ProviderRequest
from ..credentials import CredentialResolution
from .base import (
    ContractMismatch,
    ProviderEnvelope,
    ProviderNetworkError,
    ProviderRateLimited,
    ProviderTimeout,
)


AMAP_ORIGIN = "https://restapi.amap.com"
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_CALLS_PER_RUN = 80
MAX_QPS = 2.0
_MEMOIZED_AMAP_ERRORS = (
    ContractMismatch,
    ProviderNetworkError,
    ProviderRateLimited,
    ProviderTimeout,
)


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        del req, fp, code, msg, headers, newurl
        return None


class _AMapStartRateLimiter:
    """Share one start-rate clock across independently counted call budgets."""

    def __init__(
        self,
        qps: float,
        monotonic: Callable[[], float],
        sleep: Callable[[float], None],
    ) -> None:
        self.qps = float(qps)
        self._monotonic = monotonic
        self._sleep = sleep
        self._last_started: Optional[float] = None
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            now = self._monotonic()
            if self._last_started is not None:
                wait = (1.0 / self.qps) - (now - self._last_started)
                if wait > 0:
                    self._sleep(wait)
                    now = self._monotonic()
            self._last_started = now


class AMapCallBudget:
    """Thread-safe request counter and start-rate limiter."""

    def __init__(
        self,
        max_calls: int = MAX_CALLS_PER_RUN,
        qps: float = MAX_QPS,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        _rate_limiter: Optional[_AMapStartRateLimiter] = None,
    ) -> None:
        if max_calls < 0 or qps <= 0:
            raise ValueError("non-negative AMap max_calls and positive qps are required")
        self.max_calls = int(max_calls)
        self._rate_limiter = _rate_limiter or _AMapStartRateLimiter(
            qps,
            monotonic,
            sleep,
        )
        self.qps = self._rate_limiter.qps
        self._calls = 0
        self._lock = threading.Lock()

    @property
    def calls(self) -> int:
        with self._lock:
            return self._calls

    def acquire(self) -> None:
        with self._lock:
            if self._calls >= self.max_calls:
                raise ProviderRateLimited("AMap call budget exhausted")
            self._rate_limiter.acquire()
            self._calls += 1

    def fork(self, max_calls: int) -> "AMapCallBudget":
        """Create an empty counter while retaining this run's global QPS gate."""

        return AMapCallBudget(
            max_calls=max_calls,
            qps=self.qps,
            _rate_limiter=self._rate_limiter,
        )


class AMapRequestMemo:
    """Ephemeral entity-query outcome reuse for one Journey invocation."""

    def __init__(self) -> None:
        self._outcomes: Dict[str, Tuple[str, Any]] = {}
        self._lock = threading.Lock()

    def get(self, provider: str, request: ProviderRequest) -> Optional[ProviderEnvelope]:
        if not _memoizable_entity_request(request):
            return None
        key = _request_memo_key(provider, request)
        with self._lock:
            outcome = self._outcomes.get(key)
        if outcome is None:
            return None
        kind, value = outcome
        if kind == "response":
            return copy.deepcopy(value)
        error_type, message = value
        raise error_type(message)

    def store(
        self,
        provider: str,
        request: ProviderRequest,
        response: ProviderEnvelope,
    ) -> None:
        if not _memoizable_entity_request(request):
            return
        key = _request_memo_key(provider, request)
        with self._lock:
            self._outcomes[key] = ("response", copy.deepcopy(response))

    def store_error(
        self,
        provider: str,
        request: ProviderRequest,
        error: Exception,
    ) -> None:
        if not _memoizable_entity_request(request):
            return
        if not isinstance(error, _MEMOIZED_AMAP_ERRORS):
            raise TypeError("unsupported AMap memo error")
        key = _request_memo_key(provider, request)
        with self._lock:
            self._outcomes[key] = ("error", (type(error), str(error)))


class AMapBudgetedTransport:
    """Apply a Journey segment budget and run-local memo to a non-HTTP transport."""

    def __init__(
        self,
        transport: Any,
        budget: AMapCallBudget,
        memo: AMapRequestMemo,
    ) -> None:
        self.transport = transport
        self.budget = budget
        self.memo = memo
        self.retry_rate_limits = bool(getattr(transport, "retry_rate_limits", False))
        if hasattr(transport, "progress"):
            self.progress = transport.progress

    @property
    def calls(self) -> int:
        return self.budget.calls

    @property
    def max_calls(self) -> int:
        return self.budget.max_calls

    def execute(self, provider: str, request: ProviderRequest) -> ProviderEnvelope:
        cached = self.memo.get(provider, request)
        if cached is not None:
            return cached
        self.budget.acquire()
        try:
            response = self.transport.execute(provider, request)
        except _MEMOIZED_AMAP_ERRORS as exc:
            self.memo.store_error(provider, request, exc)
            raise
        self.memo.store(provider, request, response)
        return response


class AMapHTTPTransport:
    """Map typed ProviderRequests to pinned AMap HTTPS endpoint families."""

    retry_rate_limits = True

    def __init__(
        self,
        credentials: CredentialResolution,
        *,
        budget: Optional[AMapCallBudget] = None,
        opener: Optional[Callable[..., Any]] = None,
        memo: Optional[AMapRequestMemo] = None,
    ) -> None:
        self.credentials = credentials
        self.budget = budget or AMapCallBudget()
        self._open = opener or urllib.request.build_opener(_NoRedirectHandler()).open
        self.memo = memo

    @property
    def calls(self) -> int:
        return self.budget.calls

    @property
    def max_calls(self) -> int:
        return self.budget.max_calls

    def with_budget(
        self,
        budget: AMapCallBudget,
        memo: AMapRequestMemo,
    ) -> "AMapHTTPTransport":
        """Create a same-endpoint transport scoped to one Journey segment."""

        scoped = AMapHTTPTransport(
            self.credentials,
            budget=budget,
            opener=self._open,
            memo=memo,
        )
        if hasattr(self, "progress"):
            scoped.progress = self.progress
        return scoped

    def execute(self, provider: str, request: ProviderRequest) -> ProviderEnvelope:
        if provider != "amap":
            raise ContractMismatch("AMap HTTP transport is restricted to amap")
        key = self.credentials.get("AMAP_WEBSERVICE_KEY")
        if not key:
            raise ContractMismatch("AMap transport requires configured credentials")
        endpoint, parameters, api = _request_contract(request)
        if self.memo is not None:
            cached = self.memo.get(provider, request)
            if cached is not None:
                return cached
        parameters["key"] = key
        self.budget.acquire()
        try:
            response = self._execute_acquired(request, endpoint, parameters, api)
        except _MEMOIZED_AMAP_ERRORS as exc:
            if self.memo is not None:
                self.memo.store_error(provider, request, exc)
            raise
        if self.memo is not None:
            self.memo.store(provider, request, response)
        return response

    def _execute_acquired(
        self,
        request: ProviderRequest,
        endpoint: str,
        parameters: Mapping[str, Any],
        api: str,
    ) -> ProviderEnvelope:
        url = endpoint + "?" + urllib.parse.urlencode(parameters)
        http_request = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "User-Agent": "ChinaTripWeaver/0.1"},
            method="GET",
        )
        timeout = request.deadline_ms / 1000.0
        try:
            response = self._open(http_request, timeout=timeout)
            with response:
                final_url = response.geturl() if hasattr(response, "geturl") else url
                if urllib.parse.urlsplit(final_url).hostname != "restapi.amap.com":
                    raise ProviderNetworkError("AMap redirected outside its pinned origin")
                status = int(getattr(response, "status", response.getcode()))
                raw = _read_bounded(response)
                headers = _safe_headers(getattr(response, "headers", {}))
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            raw = _read_bounded(exc)
            headers = _safe_headers(exc.headers or {})
        except (socket.timeout, TimeoutError) as exc:
            raise ProviderTimeout("AMap request deadline exceeded") from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, (socket.timeout, TimeoutError)):
                raise ProviderTimeout("AMap request deadline exceeded") from exc
            raise ProviderNetworkError("AMap network request failed") from exc
        except OSError as exc:
            raise ProviderNetworkError("AMap network request failed") from exc

        body: Any = {}
        if raw:
            try:
                body = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                if status < 400:
                    raise ContractMismatch("AMap response is not UTF-8 JSON") from exc
        if status < 400 and not isinstance(body, dict):
            raise ContractMismatch("AMap response root is not an object")
        if isinstance(body, dict):
            body = dict(body)
            body["api"] = api
            if request.capability == "poi":
                body["page_size"] = parameters["page_size"]
                body["page_num"] = parameters["page_num"]
        response = ProviderEnvelope(
            status_code=status,
            body=body,
            headers=headers,
            raw_ref=endpoint,
        )
        return response


def _request_memo_key(provider: str, request: ProviderRequest) -> str:
    """Key only non-secret request context; never serialize credentials."""

    return json.dumps(
        {
            "provider": provider,
            "request_id": request.request_id,
            "capability": request.capability,
            "parameters": request.parameters,
            "as_of": request.as_of,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _memoizable_entity_request(request: ProviderRequest) -> bool:
    return (
        request.capability in ("poi", "geocode")
        and isinstance(request.parameters.get("subject_ref"), str)
        and bool(request.parameters["subject_ref"])
    )


def _request_contract(request: ProviderRequest) -> Tuple[str, Dict[str, Any], str]:
    if request.deadline_ms <= 0:
        raise ContractMismatch("AMap deadline must be positive")
    values = request.parameters
    if request.capability == "geocode":
        return (
            AMAP_ORIGIN + "/v3/geocode/geo",
            {
                "address": _required_text(values, "address"),
                "city": _required_text(values, "city"),
                "output": "JSON",
            },
            "geocode-v3",
        )
    if request.capability == "poi":
        page_size = _bounded_integer(values.get("page_size", 20), "page_size", 1, 25)
        page_num = _bounded_integer(values.get("page_num", 1), "page_num", 1, 100)
        return (
            AMAP_ORIGIN + "/v5/place/text",
            {
                "keywords": _required_text(values, "keywords"),
                "region": _required_text(values, "city"),
                "city_limit": "true",
                "page_size": page_size,
                "page_num": page_num,
                "show_fields": "business",
            },
            "poi-v5",
        )
    if request.capability != "route":
        raise ContractMismatch("unsupported AMap capability")

    origin = _coordinate_text(values, "origin")
    destination = _coordinate_text(values, "destination")
    mode = _required_text(values, "travel_mode")
    common: Dict[str, Any] = {"origin": origin, "destination": destination}
    if mode == "walk":
        return AMAP_ORIGIN + "/v3/direction/walking", common, "route-walking-v3"
    if mode == "drive":
        common.update({"strategy": 10, "extensions": "base"})
        return AMAP_ORIGIN + "/v3/direction/driving", common, "route-driving-v3"
    if mode == "ride":
        return AMAP_ORIGIN + "/v4/direction/bicycling", common, "route-riding-v4"
    if mode == "transit":
        common.update({
            "city": _required_text(values, "city"),
            "cityd": _required_text(values, "destination_city"),
            "strategy": 0,
            "nightflag": 0,
        })
        return AMAP_ORIGIN + "/v3/direction/transit/integrated", common, "route-transit-v3"
    raise ContractMismatch("unsupported AMap travel mode")


def _read_bounded(response: Any) -> bytes:
    raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ContractMismatch("AMap response exceeds 8 MiB")
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
        raise ContractMismatch("AMap request is missing %s" % name)
    return value.strip()


def _bounded_integer(value: Any, name: str, minimum: int, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise ContractMismatch("AMap %s must be between %d and %d" % (name, minimum, maximum))
    return value


def _coordinate_text(values: Mapping[str, Any], name: str) -> str:
    value = _required_text(values, name)
    if value.count(",") != 1:
        raise ContractMismatch("AMap %s must be lng,lat" % name)
    try:
        lng, lat = (float(part) for part in value.split(","))
    except ValueError as exc:
        raise ContractMismatch("AMap %s must be numeric lng,lat" % name) from exc
    if not -180 <= lng <= 180 or not -90 <= lat <= 90:
        raise ContractMismatch("AMap %s is outside coordinate bounds" % name)
    return "%.7f,%.7f" % (lng, lat)
