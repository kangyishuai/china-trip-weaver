"""AMap-backed candidate geocoding and bounded live route matrices."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .candidates import validate_candidates
from .clock import Clock, isoformat_seconds
from .contracts import ProviderRequest
from .credentials import CredentialResolution, resolve_credentials
from .evidence import make_claim
from .matrix import RouteCell, bounded_query_plan, haversine_meters
from .providers.amap import AMapAdapter
from .providers.amap_http import AMapCallBudget, AMapHTTPTransport, MAX_CALLS_PER_RUN, MAX_QPS
from .providers.base import ProviderContext, ProviderTransport, stable_id


MODE_ALIASES = {
    "transit": "transit",
    "walking": "walk",
    "walk": "walk",
    "driving": "drive",
    "drive": "drive",
    "riding": "ride",
    "ride": "ride",
}
FATAL_ERRORS = frozenset(("credential_missing", "forbidden", "rate_limited", "contract_mismatch"))


@dataclass(frozen=True)
class MobilityLocation:
    ref_id: str
    name: str
    city: str
    coordinates: Mapping[str, Any]
    claim_ids: Tuple[str, ...]

    def as_dict(self) -> Mapping[str, Any]:
        return {
            "ref_id": self.ref_id,
            "name": self.name,
            "city": self.city,
            "coordinates": copy.deepcopy(dict(self.coordinates)),
            "claim_ids": list(self.claim_ids),
        }


@dataclass(frozen=True)
class MobilityResult:
    locations: Tuple[MobilityLocation, ...]
    cells: Tuple[RouteCell, ...]
    claims: Tuple[Mapping[str, Any], ...]
    health: Mapping[str, Any]
    business_calls: Tuple[str, ...]

    def as_dict(self) -> Mapping[str, Any]:
        return {
            "provider": "amap",
            "provider_version": AMapAdapter.provider_version,
            "locations": [item.as_dict() for item in self.locations],
            "matrix_cells": [item.as_dict() for item in self.cells],
            "claims": [copy.deepcopy(dict(item)) for item in self.claims],
            "health": copy.deepcopy(dict(self.health)),
            "business_calls": list(self.business_calls),
        }


class MobilityBackend:
    def __init__(
        self,
        mode: str,
        credentials: CredentialResolution,
        transport: Optional[ProviderTransport],
        *,
        deadline_seconds: float = 12.0,
    ) -> None:
        if mode not in ("live", "off") or deadline_seconds <= 0:
            raise ValueError("mobility mode must be live/off with a positive deadline")
        self.mode = mode
        self.credentials = credentials
        self.transport = transport
        self.deadline_seconds = float(deadline_seconds)

    @classmethod
    def from_spec(cls, spec: str, repo_root: Path, deadline_seconds: float = 12.0) -> "MobilityBackend":
        if spec == "off":
            credentials = resolve_credentials({}, Path(repo_root) / ".tmp" / "mobility-no-credentials")
            return cls("off", credentials, None, deadline_seconds=deadline_seconds)
        if spec != "live":
            raise ValueError("--mobility must be live or off")
        credentials = resolve_credentials()
        budget = AMapCallBudget(max_calls=MAX_CALLS_PER_RUN, qps=MAX_QPS)
        return cls(
            "live",
            credentials,
            AMapHTTPTransport(credentials, budget=budget),
            deadline_seconds=deadline_seconds,
        )

    def resolve(
        self,
        candidates: Mapping[str, Any],
        clock: Clock,
        modes: Sequence[str] = ("transit",),
    ) -> MobilityResult:
        report = validate_candidates(candidates)
        if not report.ok:
            raise ValueError("invalid candidates: " + "; ".join(item.render() for item in report.errors))
        normalized_modes = normalize_modes(modes)
        now = isoformat_seconds(clock)
        if self.mode == "off":
            return MobilityResult((), (), (), _health(
                "static", "missing", now,
                "AMap mobility is off; calls=0/80 qps<=2; route matrix uses static estimates",
            ), ())
        if not self.credentials.get("AMAP_WEBSERVICE_KEY"):
            return MobilityResult((), (), (), _health(
                "static", "missing", now,
                "AMap credential is missing; calls=0/80 qps<=2; route matrix uses static estimates",
            ), ())
        if self.transport is None:
            raise ValueError("live mobility requires an AMap transport")

        adapter = AMapAdapter()
        context = ProviderContext(clock=clock, credentials=self.credentials, transport=self.transport)
        source_entities = _candidate_entities(candidates)
        locations: Dict[str, MobilityLocation] = {}
        claims: List[Mapping[str, Any]] = []
        calls: List[str] = []
        errors: List[str] = []
        fatal_status: Optional[str] = None

        for entity in source_entities:
            existing = _usable_coordinates(entity["coordinates"])
            if existing is not None:
                locations[entity["ref_id"]] = MobilityLocation(
                    entity["ref_id"], entity["name"], entity["city"], existing, (),
                )
                continue
            request = ProviderRequest(
                request_id=stable_id("amap-geocode", entity["ref_id"], entity["name"], entity["city"]),
                capability="geocode",
                parameters={
                    "subject_ref": entity["ref_id"],
                    "address": "%s%s" % (entity["city"], entity["name"]),
                    "city": entity["city"],
                },
                deadline_ms=int(min(self.deadline_seconds, 8.0) * 1000),
                as_of=now[:10],
                cache_policy="bypass",
                trace={"stage": "mobility-geocode"},
            )
            result = adapter.query(request, context)
            calls.append("amap.geocode:%s" % entity["ref_id"])
            if result.normalized_items and result.claims:
                coordinate_claim = next((item for item in result.claims if item["field_path"] == "/coordinates"), None)
                if coordinate_claim is None or not isinstance(coordinate_claim.get("value"), dict):
                    errors.append("contract_mismatch")
                    fatal_status = "contract_mismatch"
                    break
                claims.extend(result.claims)
                locations[entity["ref_id"]] = MobilityLocation(
                    entity["ref_id"], entity["name"], entity["city"],
                    coordinate_claim["value"], (coordinate_claim["claim_id"],),
                )
            else:
                error = result.error_class or "no_results"
                errors.append(error)
                if error in FATAL_ERRORS:
                    fatal_status = result.health["status"]
                    break

        cells: List[RouteCell] = []
        if fatal_status is None and len(locations) >= 2:
            pairs = _bounded_pairs(tuple(locations.values()), candidates, normalized_modes, _transport_calls(self.transport))
            for left_ref, right_ref in pairs:
                left = locations[left_ref]
                right = locations[right_ref]
                if left.city != right.city:
                    continue
                for mode in normalized_modes:
                    left_point = left.coordinates["gcj02"]
                    right_point = right.coordinates["gcj02"]
                    request = ProviderRequest(
                        request_id=stable_id("amap-route", left_ref, right_ref, mode),
                        capability="route",
                        parameters={
                            "from_ref": left_ref,
                            "to_ref": right_ref,
                            "origin": _point_text(left_point),
                            "destination": _point_text(right_point),
                            "city": left.city,
                            "destination_city": right.city,
                            "travel_mode": mode,
                        },
                        deadline_ms=int(self.deadline_seconds * 1000),
                        as_of=now[:10],
                        cache_policy="bypass",
                        trace={"stage": "mobility-route"},
                    )
                    result = adapter.query(request, context)
                    calls.append("amap.route:%s:%s:%s" % (mode, left_ref, right_ref))
                    if result.normalized_items:
                        leg = result.normalized_items[0]
                        distance = next(
                            (item["value"] for item in result.claims if item["field_path"] == "/distance_meters"),
                            None,
                        )
                        cell = RouteCell(
                            from_ref=left_ref,
                            to_ref=right_ref,
                            travel_mode=mode,
                            duration_minutes=leg["duration_minutes"],
                            distance_meters=distance,
                            provider="amap",
                            provider_version=adapter.provider_version,
                            mode="live",
                            queried_at=result.queried_at,
                            claim_ids=tuple(leg["claim_ids"]),
                            reachable=True,
                            degradation_rung="R0",
                        )
                        cell.validate()
                        cells.append(cell)
                        claims.extend(result.claims)
                        continue
                    error = result.error_class or "no_results"
                    errors.append(error)
                    if error == "no_results":
                        leg_id = stable_id("leg-amap", left_ref, right_ref, mode)
                        unreachable_claim = make_claim(
                            subject_ref=leg_id,
                            field_path="/reachable",
                            value=False,
                            source_url=_route_source(mode),
                            provider="amap",
                            status="verified",
                            confidence=0.9,
                            mode="live",
                            clock=clock,
                        )
                        cell = RouteCell(
                            from_ref=left_ref,
                            to_ref=right_ref,
                            travel_mode=mode,
                            duration_minutes=None,
                            distance_meters=None,
                            provider="amap",
                            provider_version=adapter.provider_version,
                            mode="live",
                            queried_at=result.queried_at,
                            claim_ids=(unreachable_claim["claim_id"],),
                            reachable=False,
                            degradation_rung="R0",
                        )
                        cell.validate()
                        cells.append(cell)
                        claims.append(unreachable_claim)
                    if error in FATAL_ERRORS:
                        fatal_status = result.health["status"]
                        break
                if fatal_status is not None:
                    break

        call_count = _transport_calls(self.transport)
        live_cells = sum(1 for item in cells if item.mode == "live")
        if fatal_status is not None:
            status = fatal_status
        elif live_cells:
            status = "ready"
        else:
            status = "degraded"
        error_summary = ",".join(sorted(set(errors))) if errors else "none"
        health = _health(
            "live" if live_cells else "static",
            status,
            now,
            "calls=%d/80 qps<=2; live_cells=%d; locations=%d; errors=%s" % (
                call_count, live_cells, len(locations), error_summary,
            ),
        )
        return MobilityResult(
            tuple(locations[key] for key in sorted(locations)),
            tuple(sorted(cells, key=lambda item: (item.from_ref, item.to_ref, item.travel_mode))),
            tuple(claims),
            health,
            tuple(calls),
        )


def normalize_modes(modes: Sequence[str]) -> Tuple[str, ...]:
    normalized = []
    for raw in modes:
        key = raw.strip().lower()
        if key not in MODE_ALIASES:
            raise ValueError("unsupported mobility mode: %s" % raw)
        value = MODE_ALIASES[key]
        if value not in normalized:
            normalized.append(value)
    if not normalized:
        raise ValueError("at least one mobility mode is required")
    return tuple(normalized)


def apply_locations(
    pois: Sequence[Mapping[str, Any]],
    lodgings: Sequence[Mapping[str, Any]],
    result: MobilityResult,
) -> Tuple[List[Mapping[str, Any]], List[Mapping[str, Any]]]:
    by_ref = {item.ref_id: item for item in result.locations}

    def update(items: Sequence[Mapping[str, Any]], id_key: str) -> List[Mapping[str, Any]]:
        output = copy.deepcopy(list(items))
        for item in output:
            location = by_ref.get(item[id_key])
            if location is None:
                continue
            item["coordinates"] = copy.deepcopy(dict(location.coordinates))
            item["claim_ids"] = list(dict.fromkeys(list(item["claim_ids"]) + list(location.claim_ids)))
        return output

    return update(pois, "poi_id"), update(lodgings, "lodging_id")


def _candidate_entities(candidates: Mapping[str, Any]) -> Tuple[Mapping[str, Any], ...]:
    entities = []
    for item in candidates["lodgings"]:
        entities.append({
            "ref_id": item["lodging_id"], "name": item["name"], "city": item["city"],
            "coordinates": item["coordinates"], "lodging": True,
        })
    for item in candidates["pois"][:12]:
        entities.append({
            "ref_id": item["poi_id"], "name": item["name"], "city": item["city"],
            "coordinates": item["coordinates"], "lodging": False,
        })
    return tuple(sorted(entities, key=lambda item: item["ref_id"]))


def _usable_coordinates(value: Any) -> Optional[Mapping[str, Any]]:
    if not isinstance(value, dict) or not isinstance(value.get("gcj02"), dict) or not isinstance(value.get("wgs84"), dict):
        return None
    return copy.deepcopy(value)


def _bounded_pairs(
    locations: Sequence[MobilityLocation],
    candidates: Mapping[str, Any],
    modes: Sequence[str],
    calls_used: int,
) -> Tuple[Tuple[str, str], ...]:
    by_ref = {item.ref_id: item for item in locations}
    neighbors: Dict[str, Sequence[str]] = {}
    for left in locations:
        left_point = left.coordinates["gcj02"]
        ranked = []
        for right in locations:
            if left.ref_id == right.ref_id or left.city != right.city:
                continue
            right_point = right.coordinates["gcj02"]
            distance = haversine_meters(
                float(left_point["lng"]), float(left_point["lat"]),
                float(right_point["lng"]), float(right_point["lat"]),
            )
            ranked.append((distance, right.ref_id))
        neighbors[left.ref_id] = tuple(ref for _, ref in sorted(ranked)[:5])
    lodging_refs = tuple(
        item["lodging_id"] for item in candidates["lodgings"] if item["lodging_id"] in by_ref
    )
    pairs = bounded_query_plan(tuple(by_ref), lodging_refs=lodging_refs, cluster_neighbors=neighbors)
    ordered = sorted(pairs, key=lambda pair: (not (pair[0] in lodging_refs or pair[1] in lodging_refs), pair))
    remaining = max(0, MAX_CALLS_PER_RUN - calls_used)
    return tuple(ordered[: remaining // len(modes)])


def _point_text(point: Mapping[str, Any]) -> str:
    return "%.7f,%.7f" % (float(point["lng"]), float(point["lat"]))


def _route_source(mode: str) -> str:
    paths = {
        "walk": "/v3/direction/walking",
        "transit": "/v3/direction/transit/integrated",
        "drive": "/v3/direction/driving",
        "ride": "/v4/direction/bicycling",
    }
    return "https://restapi.amap.com" + paths[mode]


def _transport_calls(transport: ProviderTransport) -> int:
    value = getattr(transport, "calls", 0)
    return int(value) if isinstance(value, int) else 0


def _health(mode: str, status: str, checked_at: str, reason: str) -> Mapping[str, Any]:
    return {
        "provider": "amap",
        "version": AMapAdapter.provider_version,
        "mode": mode,
        "status": status,
        "checked_at": checked_at,
        "capabilities": ["geocode", "poi", "route"],
        "reason": reason,
    }
