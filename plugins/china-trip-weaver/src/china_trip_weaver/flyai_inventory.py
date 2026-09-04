"""Live FlyAI lodging inventory and cross-city flight comparisons."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Mapping, Optional, Sequence, Tuple

from .clock import Clock, isoformat_seconds
from .contracts import AdapterResult, ProviderRequest
from .credentials import CredentialResolution, resolve_credentials
from .providers.base import ProviderContext, ProviderTransport, stable_id
from .providers.flyai import FlyAIAdapter
from .providers.flyai_cli import FlyAISubprocessTransport


@dataclass(frozen=True)
class FlyAIInventoryResult:
    lodgings: Tuple[Mapping[str, Any], ...]
    flights: Tuple[Mapping[str, Any], ...]
    claims: Tuple[Mapping[str, Any], ...]
    health: Mapping[str, Any]
    business_calls: Tuple[str, ...]


class FlyAIBackend:
    def __init__(
        self,
        mode: str,
        credentials: CredentialResolution,
        transport: Optional[ProviderTransport],
        *,
        deadline_seconds: float = 25.0,
    ) -> None:
        if mode not in ("live", "off") or deadline_seconds <= 0:
            raise ValueError("FlyAI mode must be live/off with a positive deadline")
        self.mode = mode
        self.credentials = credentials
        self.transport = transport
        self.deadline_seconds = float(deadline_seconds)

    @classmethod
    def from_spec(
        cls,
        spec: str,
        repo_root: Path,
        *,
        deadline_seconds: float = 25.0,
        keyless_trial: bool = False,
    ) -> "FlyAIBackend":
        root = Path(repo_root)
        if spec == "off":
            credentials = resolve_credentials({}, root / ".tmp" / "flyai-no-credentials")
            return cls("off", credentials, None, deadline_seconds=deadline_seconds)
        if spec != "live":
            raise ValueError("--lodging must be live or off")
        credentials = (
            resolve_credentials({}, root / ".tmp" / "flyai-keyless-trial")
            if keyless_trial else resolve_credentials()
        )
        transport = FlyAISubprocessTransport(
            credentials,
            cache_dir=root / ".npm-cache",
            temp_root=root / ".tmp" / "flyai-runtime",
            cwd=root,
        )
        return cls("live", credentials, transport, deadline_seconds=deadline_seconds)

    def query_lodging(self, city: str, check_in: str, check_out: str, clock: Clock) -> AdapterResult:
        return self._query(ProviderRequest(
            request_id=stable_id("flyai-lodging", city, check_in, check_out),
            capability="lodging",
            parameters={
                "city": city,
                "check_in": check_in,
                "check_out": check_out,
            },
            deadline_ms=int(self.deadline_seconds * 1000),
            as_of=check_in,
            cache_policy="bypass",
            trace={"stage": "flyai-lodging"},
        ), clock)

    def query_flight(
        self,
        origin: str,
        destination: str,
        travel_date: str,
        from_ref: str,
        to_ref: str,
        clock: Clock,
    ) -> AdapterResult:
        return self._query(ProviderRequest(
            request_id=stable_id("flyai-flight", origin, destination, travel_date),
            capability="flight",
            parameters={
                "origin": origin,
                "destination": destination,
                "date": travel_date,
                "from_ref": from_ref,
                "to_ref": to_ref,
            },
            deadline_ms=int(self.deadline_seconds * 1000),
            as_of=travel_date,
            cache_policy="bypass",
            trace={"stage": "flyai-flight"},
        ), clock)

    def resolve(
        self,
        request: Mapping[str, Any],
        routes: Sequence[Any],
        clock: Clock,
    ) -> FlyAIInventoryResult:
        now = isoformat_seconds(clock)
        if self.mode == "off":
            return FlyAIInventoryResult((), (), (), _health(
                "static", "ready", now,
                "candidate-file lodging retained; FlyAI live inventory and flight comparison were not called",
            ), ())
        if self.transport is None:
            raise ValueError("live FlyAI backend requires a transport")

        lodgings: List[Mapping[str, Any]] = []
        flights: List[Mapping[str, Any]] = []
        claims: List[Mapping[str, Any]] = []
        calls: List[str] = []
        errors: List[str] = []
        if request["start_date"] != request["end_date"]:
            city = request["destinations"][0]["city"]
            lodging_result = self.query_lodging(city, request["start_date"], request["end_date"], clock)
            calls.append("flyai.lodging:%s:%s:%s" % (city, request["start_date"], request["end_date"]))
            lodgings.extend(copy.deepcopy(list(lodging_result.normalized_items)))
            claims.extend(copy.deepcopy(list(lodging_result.claims)))
            if lodging_result.error_class:
                errors.append(lodging_result.error_class)

        for route in routes:
            flight_result = self.query_flight(
                route.from_place["name"], route.to_place["name"], route.travel_date,
                route.from_place["ref_id"], route.to_place["ref_id"], clock,
            )
            calls.append("flyai.flight:%s:%s:%s" % (
                route.travel_date, route.from_place["name"], route.to_place["name"],
            ))
            flights.extend(copy.deepcopy(list(flight_result.normalized_items)))
            claims.extend(copy.deepcopy(list(flight_result.claims)))
            if flight_result.error_class:
                errors.append(flight_result.error_class)

        item_count = len(lodgings) + len(flights)
        status = "ready" if item_count or not errors or set(errors) == {"no_results"} else ("contract_mismatch" if "contract_mismatch" in errors else "degraded")
        key_mode = "configured" if self.credentials.get("FLYAI_API_KEY") else "keyless-trial"
        health = _health(
            "live" if item_count else "static",
            status,
            now,
            "calls=%d; credential=%s; lodging_items=%d; flight_items=%d; errors=%s" % (
                len(calls), key_mode, len(lodgings), len(flights),
                ",".join(sorted(set(errors))) if errors else "none",
            ),
        )
        return FlyAIInventoryResult(tuple(lodgings), tuple(flights), tuple(claims), health, tuple(calls))

    def _query(self, request: ProviderRequest, clock: Clock) -> AdapterResult:
        if self.transport is None:
            raise ValueError("FlyAI transport is unavailable")
        return FlyAIAdapter().query(
            request,
            ProviderContext(clock=clock, credentials=self.credentials, transport=self.transport),
        )


def _health(mode: str, status: str, checked_at: str, reason: str) -> Mapping[str, Any]:
    return {
        "provider": "flyai",
        "version": FlyAIAdapter.provider_version,
        "mode": mode,
        "status": status,
        "checked_at": checked_at,
        "capabilities": ["lodging", "flight"],
        "reason": reason,
    }
