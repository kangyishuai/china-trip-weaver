"""Live FlyAI lodging inventory and cross-city flight comparisons."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .clock import Clock, isoformat_seconds
from .contracts import AdapterResult, ProviderRequest
from .credentials import CredentialResolution, resolve_credentials
from .evidence import make_claim
from .providers.amap import AMapAdapter
from .providers.amap_http import AMapCallBudget, AMapHTTPTransport
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
    unknowns: Tuple[Mapping[str, Any], ...] = ()


@dataclass(frozen=True)
class AMapLodgingResult:
    lodgings: Tuple[Mapping[str, Any], ...]
    claims: Tuple[Mapping[str, Any], ...]
    unknowns: Tuple[Mapping[str, Any], ...]
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

    def query_lodging(
        self,
        city: str,
        check_in: str,
        check_out: str,
        clock: Clock,
        *,
        party: Optional[Mapping[str, Any]] = None,
        rooms: int = 1,
        adult_count: Optional[int] = None,
        occupancy: Optional[str] = None,
        bed_config: Optional[str] = None,
        parking_required: bool = False,
        cancellation_preference: Optional[str] = None,
    ) -> AdapterResult:
        parameters = _lodging_parameters(
            city=city,
            check_in=check_in,
            check_out=check_out,
            party=party,
            rooms=rooms,
            adult_count=adult_count,
            occupancy=occupancy,
            bed_config=bed_config,
            parking_required=parking_required,
            cancellation_preference=cancellation_preference,
        )
        return self._query(ProviderRequest(
            request_id=stable_id("flyai-lodging", parameters),
            capability="lodging",
            parameters=parameters,
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
        unknowns: List[Mapping[str, Any]] = []
        calls: List[str] = []
        errors: List[str] = []
        if request["start_date"] != request["end_date"]:
            city = request["destinations"][0]["city"]
            lodging_parameters = _lodging_parameters_from_trip(request, city)
            lodging_result = self.query_lodging(clock=clock, **lodging_parameters)
            calls.append("flyai.lodging:%s:%s:%s" % (city, request["start_date"], request["end_date"]))
            lodgings.extend(copy.deepcopy(list(lodging_result.normalized_items)))
            claims.extend(copy.deepcopy(list(lodging_result.claims)))
            unknowns.extend(_unverified_lodging_unknowns(
                lodging_result.normalized_items, lodging_parameters, "flyai",
            ))
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
        return FlyAIInventoryResult(
            tuple(lodgings), tuple(flights), tuple(claims), health, tuple(calls),
            tuple(unknowns),
        )

    def _query(self, request: ProviderRequest, clock: Clock) -> AdapterResult:
        if self.transport is None:
            raise ValueError("FlyAI transport is unavailable")
        return FlyAIAdapter().query(
            request,
            ProviderContext(clock=clock, credentials=self.credentials, transport=self.transport),
        )


class AMapLodgingBackend:
    """Produce price-less lodging candidates through the existing AMap POI path."""

    def __init__(
        self,
        mode: str,
        credentials: CredentialResolution,
        transport: Optional[ProviderTransport],
        *,
        deadline_seconds: float = 12.0,
    ) -> None:
        if mode not in ("auto", "off") or deadline_seconds <= 0:
            raise ValueError("AMap lodging mode must be auto/off with a positive deadline")
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
        deadline_seconds: float = 12.0,
    ) -> "AMapLodgingBackend":
        root = Path(repo_root)
        if spec == "off":
            credentials = resolve_credentials({}, root / ".tmp" / "amap-lodging-no-credentials")
            return cls("off", credentials, None, deadline_seconds=deadline_seconds)
        if spec != "auto":
            raise ValueError("AMap lodging mode must be auto or off")
        credentials = resolve_credentials()
        transport = AMapHTTPTransport(credentials, budget=AMapCallBudget())
        return cls("auto", credentials, transport, deadline_seconds=deadline_seconds)

    def resolve(self, request: Mapping[str, Any], clock: Clock) -> AMapLodgingResult:
        now = isoformat_seconds(clock)
        if self.mode == "off":
            return AMapLodgingResult((), (), (), _amap_health(
                "static", "missing", now,
                "AMap lodging fallback is off; no POI business call was made",
            ), ())
        if not self.credentials.get("AMAP_WEBSERVICE_KEY"):
            return AMapLodgingResult((), (), (), _amap_health(
                "static", "missing", now,
                "AMap credential is missing; lodging fallback made no business call",
            ), ())
        if self.transport is None:
            raise ValueError("auto AMap lodging backend requires a transport")
        if request["start_date"] == request["end_date"]:
            return AMapLodgingResult((), (), (), _amap_health(
                "static", "ready", now,
                "trip has no overnight stay; AMap lodging fallback was not called",
            ), ())

        adapter = AMapAdapter()
        context = ProviderContext(clock=clock, credentials=self.credentials, transport=self.transport)
        lodgings: List[Mapping[str, Any]] = []
        claims: List[Mapping[str, Any]] = []
        unknowns: List[Mapping[str, Any]] = []
        calls: List[str] = []
        errors: List[str] = []
        seen_cities = set()
        for destination in request["destinations"]:
            city = destination["city"]
            if city in seen_cities:
                continue
            seen_cities.add(city)
            provider_request = ProviderRequest(
                request_id=stable_id(
                    "amap-lodging", city, request["start_date"], request["end_date"],
                ),
                capability="poi",
                parameters={
                    "city": city,
                    "keywords": "住宿服务 酒店",
                    "page_size": 5,
                    "page_num": 1,
                },
                deadline_ms=int(min(self.deadline_seconds, 8.0) * 1000),
                as_of=request["start_date"],
                cache_policy="bypass",
                trace={"stage": "amap-lodging-fallback"},
            )
            result = adapter.query(provider_request, context)
            calls.append("amap.lodging:%s:%s:%s" % (
                city, request["start_date"], request["end_date"],
            ))
            if result.error_class:
                errors.append(result.error_class)
                continue
            by_claim_id = {claim["claim_id"]: claim for claim in result.claims}
            for item in result.normalized_items:
                identity = next((
                    by_claim_id[claim_id]["value"]
                    for claim_id in item["claim_ids"]
                    if claim_id in by_claim_id
                    and by_claim_id[claim_id]["field_path"] == "/provider_identity"
                ), None)
                if not _is_lodging_identity(identity):
                    errors.append("non_lodging_result")
                    continue
                lodging, lodging_claims = _amap_lodging_candidate(
                    item, identity, city, request, clock, by_claim_id,
                )
                source_index = len(lodgings)
                lodgings.append(lodging)
                claims.extend(lodging_claims)
                parameters = _lodging_parameters_from_trip(request, city)
                unknowns.extend(_unverified_lodging_unknowns(
                    (lodging,), parameters, "amap", index_offset=source_index,
                ))

        status = "ready" if lodgings or not errors or set(errors) == {"no_results"} else (
            "contract_mismatch" if "contract_mismatch" in errors else "degraded"
        )
        return AMapLodgingResult(
            tuple(lodgings), tuple(claims), tuple(unknowns),
            _amap_health(
                "live" if lodgings else "static",
                status,
                now,
                "poi_calls=%d; lodging_items=%d; prices=verify-on-click; errors=%s" % (
                    len(calls), len(lodgings),
                    ",".join(sorted(set(errors))) if errors else "none",
                ),
            ),
            tuple(calls),
        )


def _lodging_parameters_from_trip(
    request: Mapping[str, Any],
    city: str,
) -> Dict[str, Any]:
    party = request.get("party")
    groups = request.get("traveler_groups")
    if groups:
        adult_count = sum(int(group["travelers"]) for group in groups)
    else:
        adult_count = request.get("adult_count")
        if adult_count is None and isinstance(party, dict):
            adult_count = party.get("adults")
        if adult_count is None:
            adult_count = request["travelers"]
    rooms = request.get("rooms", 1)
    if party is None:
        party = {"adults": adult_count, "children": 0}
    occupancy = request.get("occupancy")
    if occupancy is None:
        occupancy = "%d adult(s) across %d room(s)" % (adult_count, rooms)
    return _lodging_parameters(
        city=city,
        check_in=request["start_date"],
        check_out=request["end_date"],
        party=party,
        rooms=rooms,
        adult_count=adult_count,
        occupancy=occupancy,
        bed_config=request.get("bed_config"),
        parking_required=request.get("parking_required", False),
        cancellation_preference=request.get("cancellation_preference"),
    )


def _lodging_parameters(
    *,
    city: str,
    check_in: str,
    check_out: str,
    party: Optional[Mapping[str, Any]],
    rooms: int,
    adult_count: Optional[int],
    occupancy: Optional[str],
    bed_config: Optional[str],
    parking_required: bool,
    cancellation_preference: Optional[str],
) -> Dict[str, Any]:
    adults = 1 if adult_count is None else adult_count
    normalized_party: Dict[str, Any] = dict(party or {"adults": adults})
    normalized_party.setdefault("children", 0)
    if (
        not isinstance(adults, int) or isinstance(adults, bool) or not 1 <= adults <= 20
        or not isinstance(rooms, int) or isinstance(rooms, bool) or not 1 <= rooms <= 20
        or not isinstance(normalized_party, dict)
        or not set(normalized_party).issubset({"adults", "children"})
        or normalized_party.get("adults") != adults
        or not isinstance(normalized_party.get("children"), int)
        or isinstance(normalized_party.get("children"), bool)
        or not 0 <= normalized_party["children"] <= 20
        or not isinstance(parking_required, bool)
    ):
        raise ValueError("lodging party, adults, rooms, and parking constraints are inconsistent")
    for name, value in (
        ("occupancy", occupancy),
        ("bed_config", bed_config),
        ("cancellation_preference", cancellation_preference),
    ):
        if value is not None and (not isinstance(value, str) or not value.strip() or len(value) > 500):
            raise ValueError("lodging %s must be non-empty text when supplied" % name)
    return {
        "city": city,
        "check_in": check_in,
        "check_out": check_out,
        "party": copy.deepcopy(normalized_party),
        "rooms": rooms,
        "adult_count": adults,
        "occupancy": occupancy,
        "bed_config": bed_config,
        "parking_required": parking_required,
        "cancellation_preference": cancellation_preference,
    }


def _unverified_lodging_unknowns(
    lodgings: Sequence[Mapping[str, Any]],
    parameters: Mapping[str, Any],
    provider: str,
    *,
    index_offset: int = 0,
) -> List[Mapping[str, Any]]:
    unknowns: List[Mapping[str, Any]] = []
    requested = {
        "party": parameters["party"],
        "adult_count": parameters["adult_count"],
        "rooms": parameters["rooms"],
        "occupancy": parameters["occupancy"],
        "bed_config": parameters["bed_config"],
        "parking_required": parameters["parking_required"],
        "cancellation_policy": parameters["cancellation_preference"],
    }
    for local_index, lodging in enumerate(lodgings):
        price = lodging.get("price")
        if not isinstance(price, dict) or price.get("price_type") == "live":
            continue
        index = index_offset + local_index
        claim_id = price.get("claim_id")
        unknowns.append({
            "field_path": "/lodgings/%d/price/amount" % index,
            "reason": "%s cannot verify a context-complete room price; verify on click" % provider,
            "provider": provider,
            "claim_id": claim_id,
        })
        for field, value in requested.items():
            if field in ("bed_config", "parking_required", "cancellation_policy") and value in (None, False):
                continue
            unknowns.append({
                "field_path": "/lodgings/%d/price/amount" % index,
                "reason": "%s did not verify requested %s=%r for this room price" % (
                    provider, field, value,
                ),
                "provider": provider,
                "claim_id": claim_id,
            })
    return unknowns


def _is_lodging_identity(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    poi_type = value.get("type")
    return isinstance(poi_type, str) and any(
        marker in poi_type for marker in ("住宿服务", "酒店", "宾馆", "旅馆", "公寓")
    )


def _amap_lodging_candidate(
    item: Mapping[str, Any],
    identity: Mapping[str, Any],
    city: str,
    request: Mapping[str, Any],
    clock: Clock,
    claims_by_id: Mapping[str, Mapping[str, Any]],
) -> Tuple[Mapping[str, Any], List[Mapping[str, Any]]]:
    lodging_id = item["poi_id"]
    source_claims = [
        copy.deepcopy(claims_by_id[claim_id])
        for claim_id in item["claim_ids"] if claim_id in claims_by_id
    ]
    price_claim = make_claim(
        subject_ref=lodging_id,
        field_path="/price",
        value=None,
        source_url="https://restapi.amap.com/v5/place/text",
        provider="amap",
        status="unknown",
        confidence=0,
        mode="live",
        clock=clock,
    )
    claim_ids = list(item["claim_ids"]) + [price_claim["claim_id"]]
    formatted_address = identity.get("formatted_address")
    area = formatted_address if isinstance(formatted_address, str) and formatted_address else city
    return ({
        "lodging_id": lodging_id,
        "name": item["name"],
        "city": city,
        "area": area,
        "check_in": request["start_date"],
        "check_out": request["end_date"],
        "coordinates": item.get("coordinates"),
        "price": {
            "amount": None,
            "currency": "CNY",
            "price_type": "verify-on-click",
            "unit": "per_night",
            "includes_taxes": None,
            "queried_at": price_claim["queried_at"],
            "claim_id": price_claim["claim_id"],
        },
        "deep_links": copy.deepcopy(list(item["deep_links"])),
        "claim_ids": claim_ids,
        "locked": False,
    }, source_claims + [price_claim])


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


def _amap_health(mode: str, status: str, checked_at: str, reason: str) -> Mapping[str, Any]:
    return {
        "provider": "amap",
        "version": AMapAdapter.provider_version,
        "mode": mode,
        "status": status,
        "checked_at": checked_at,
        "capabilities": ["poi", "lodging-candidate"],
        "reason": reason,
    }
