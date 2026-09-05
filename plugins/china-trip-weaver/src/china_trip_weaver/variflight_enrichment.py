"""Optional VariFlight status and comfort enrichment for FlyAI flight legs."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .clock import Clock, isoformat_seconds
from .contracts import ProviderRequest
from .credentials import CredentialResolution, resolve_credentials
from .providers.base import ProviderContext, ProviderTransport, stable_id
from .providers.variflight import VariFlightAdapter
from .providers.variflight_mcp import VariFlightMCPTransport


CITY_IATA = {
    "北京": "BJS",
    "上海": "SHA",
    "广州": "CAN",
    "深圳": "SZX",
    "杭州": "HGH",
}


@dataclass(frozen=True)
class VariFlightEnrichmentResult:
    flights: Tuple[Mapping[str, Any], ...]
    claims: Tuple[Mapping[str, Any], ...]
    health: Mapping[str, Any]
    business_calls: Tuple[str, ...]
    warnings: Tuple[str, ...] = ()


class VariFlightBackend:
    def __init__(
        self,
        mode: str,
        credentials: CredentialResolution,
        transport: Optional[ProviderTransport],
        *,
        deadline_seconds: float = 15.0,
    ) -> None:
        if mode not in ("auto", "off") or deadline_seconds <= 0:
            raise ValueError("VariFlight mode must be auto/off with a positive deadline")
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
        deadline_seconds: float = 15.0,
    ) -> "VariFlightBackend":
        root = Path(repo_root)
        if spec == "off":
            credentials = resolve_credentials({}, root / ".tmp" / "variflight-no-credentials")
            return cls("off", credentials, None, deadline_seconds=deadline_seconds)
        if spec != "auto":
            raise ValueError("--aviation must be auto or off")
        credentials = resolve_credentials()
        transport = VariFlightMCPTransport(
            credentials,
            cache_dir=root / ".npm-cache",
            temp_root=root / ".tmp" / "variflight-runtime",
            cwd=root,
        )
        return cls("auto", credentials, transport, deadline_seconds=deadline_seconds)

    def enrich(
        self,
        flights: Sequence[Mapping[str, Any]],
        routes: Sequence[Any],
        clock: Clock,
    ) -> VariFlightEnrichmentResult:
        now = isoformat_seconds(clock)
        copied_flights = copy.deepcopy(list(flights))
        if self.mode == "off":
            return VariFlightEnrichmentResult(tuple(copied_flights), (), _health(
                "static", "missing", now,
                "VariFlight enrichment is off; no business call was made and tools/list was not run",
            ), ())
        if not isinstance(self.transport, VariFlightMCPTransport):
            raise ValueError("auto VariFlight backend requires its MCP transport")

        has_key = bool(
            self.credentials.get("VARIFLIGHT_API_KEY")
            or self.credentials.get("X_VARIFLIGHT_KEY")
        )
        if not has_key:
            tools = self.transport.probe(self.deadline_seconds)
            return VariFlightEnrichmentResult(tuple(copied_flights), (), _health(
                "static", "missing", now,
                "keyless probe verified tools=%d; business_calls=0" % len(tools),
            ), ())

        adapter = VariFlightAdapter()
        context = ProviderContext(clock=clock, credentials=self.credentials, transport=self.transport)
        claims: List[Mapping[str, Any]] = []
        calls: List[str] = []
        errors: List[str] = []
        runtime_warnings: List[str] = []
        for route in routes:
            dep_city = CITY_IATA.get(route.from_place["name"])
            arr_city = CITY_IATA.get(route.to_place["name"])
            if dep_city is None or arr_city is None:
                errors.append("unsupported_city_code")
                continue
            route_flights = [
                item for item in copied_flights
                if item["from_ref"] == route.from_place["ref_id"]
                and item["to_ref"] == route.to_place["ref_id"]
                and isinstance(item.get("depart_at"), str)
                and item["depart_at"][:10] == route.travel_date
            ]
            service_map = {
                item["service_number"]: item["leg_id"]
                for item in route_flights if item.get("service_number")
            }
            candidate_mode = not service_map
            search_parameters: Dict[str, Any] = {
                "action": "search",
                "dep_city": dep_city,
                "arr_city": arr_city,
                "date": route.travel_date,
            }
            if candidate_mode:
                search_parameters.update({
                    "candidate_mode": True,
                    "from_ref": route.from_place["ref_id"],
                    "to_ref": route.to_place["ref_id"],
                })
            else:
                search_parameters["subject_refs_by_service"] = service_map
            search_request = ProviderRequest(
                request_id=stable_id("variflight-search", dep_city, arr_city, route.travel_date),
                capability="flight",
                parameters=search_parameters,
                deadline_ms=int(self.deadline_seconds * 1000),
                as_of=route.travel_date,
                cache_policy="bypass",
                trace={"stage": "variflight-status"},
            )
            search = adapter.query(search_request, context)
            calls.append("variflight.search:%s:%s:%s" % (route.travel_date, dep_city, arr_city))
            claims.extend(copy.deepcopy(list(search.claims)))
            if search.error_class:
                errors.append(search.error_class)
                runtime_warnings.extend(_runtime_failure_warnings(
                    search.error_class,
                    tuple(service_map.values()),
                    "flight@%s->%s" % (
                        route.from_place["ref_id"], route.to_place["ref_id"],
                    ),
                    "route=%s->%s;date=%s;action=search" % (
                        route.from_place["ref_id"], route.to_place["ref_id"], route.travel_date,
                    ),
                ))
                continue
            if candidate_mode:
                route_flights = copy.deepcopy(list(search.normalized_items))
                copied_flights.extend(route_flights)
                selected = route_flights[0] if route_flights else None
            else:
                matched_subjects = {
                    item["subject_ref"] for item in search.claims
                    if item["field_path"] == "/status"
                }
                selected = next((
                    item for item in route_flights if item["leg_id"] in matched_subjects
                ), None)
            if selected is None:
                errors.append("no_matching_flight")
                runtime_warnings.append(
                    "no_matching_flight:flight@%s->%s:route=%s->%s;date=%s;action=search" % (
                        route.from_place["ref_id"], route.to_place["ref_id"],
                        route.from_place["ref_id"], route.to_place["ref_id"], route.travel_date,
                    )
                )
                continue
            comfort_request = ProviderRequest(
                request_id=stable_id("variflight-comfort", selected["service_number"], route.travel_date),
                capability="flight",
                parameters={
                    "action": "comfort",
                    "flight_no": selected["service_number"],
                    "date": route.travel_date,
                    "subject_ref": selected["leg_id"],
                },
                deadline_ms=int(self.deadline_seconds * 1000),
                as_of=route.travel_date,
                cache_policy="bypass",
                trace={"stage": "variflight-comfort"},
            )
            comfort = adapter.query(comfort_request, context)
            calls.append("variflight.comfort:%s:%s" % (route.travel_date, selected["service_number"]))
            claims.extend(copy.deepcopy(list(comfort.claims)))
            if comfort.error_class:
                errors.append(comfort.error_class)
                runtime_warnings.extend(_runtime_failure_warnings(
                    comfort.error_class,
                    (selected["leg_id"],),
                    "flight@%s->%s" % (
                        route.from_place["ref_id"], route.to_place["ref_id"],
                    ),
                    "service=%s;date=%s;action=comfort" % (
                        selected["service_number"], route.travel_date,
                    ),
                ))

        claim_ids_by_subject: Dict[str, List[str]] = {}
        for claim in claims:
            claim_ids_by_subject.setdefault(claim["subject_ref"], []).append(claim["claim_id"])
        for flight in copied_flights:
            additions = claim_ids_by_subject.get(flight["leg_id"], ())
            flight["claim_ids"] = list(dict.fromkeys(list(flight["claim_ids"]) + list(additions)))

        status_claims = sum(item["field_path"] == "/status" for item in claims)
        comfort_claims = sum(item["field_path"] == "/comfort" for item in claims)
        candidate_count = sum(item.get("provider") == "variflight" for item in copied_flights)
        status = "ready" if claims or not errors else ("contract_mismatch" if "contract_mismatch" in errors else "degraded")
        return VariFlightEnrichmentResult(
            tuple(copied_flights),
            tuple(claims),
            _health(
                "live" if claims else "static",
                status,
                now,
                "tools=9; business_calls=%d; candidates=%d; status_claims=%d; comfort_claims=%d; errors=%s" % (
                    len(calls), candidate_count, status_claims, comfort_claims,
                    ",".join(sorted(set(errors))) if errors else "none",
                ),
            ),
            tuple(calls),
            tuple(runtime_warnings),
        )


def _runtime_failure_warnings(
    cause: str,
    entity_refs: Sequence[str],
    scope: str,
    detail: str,
) -> Tuple[str, ...]:
    warnings = ["%s:%s:%s" % (cause, ref_id, detail) for ref_id in entity_refs]
    if not warnings:
        warnings.append("%s:%s:%s" % (cause, scope, detail))
    return tuple(warnings)


def _health(mode: str, status: str, checked_at: str, reason: str) -> Mapping[str, Any]:
    return {
        "provider": "variflight",
        "version": VariFlightAdapter.provider_version,
        "mode": mode,
        "status": status,
        "checked_at": checked_at,
        "capabilities": ["flight", "weather", "comfort"],
        "reason": reason,
    }
