"""Bounded route-time matrix planning and truthful degradation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


MATRIX_MODES = frozenset(("live", "cached", "static"))
TRAVEL_MODES = frozenset(("walk", "transit", "drive", "ride", "taxi", "bus", "rail", "flight", "ferry"))


class MatrixError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class RouteCell:
    from_ref: str
    to_ref: str
    travel_mode: str
    duration_minutes: Optional[int]
    distance_meters: Optional[int]
    provider: str
    provider_version: str
    mode: str
    queried_at: Optional[str]
    claim_ids: Tuple[str, ...]
    reachable: bool
    degradation_rung: str
    estimate_method: Optional[str] = None
    fare: Optional[Mapping[str, Any]] = None
    geometry_ref: Optional[str] = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "RouteCell":
        return cls(
            from_ref=value["from_ref"],
            to_ref=value["to_ref"],
            travel_mode=value["travel_mode"],
            duration_minutes=value.get("duration_minutes"),
            distance_meters=value.get("distance_meters"),
            provider=value["provider"],
            provider_version=value["provider_version"],
            mode=value["mode"],
            queried_at=value.get("queried_at"),
            claim_ids=tuple(value.get("claim_ids", ())),
            reachable=bool(value["reachable"]),
            degradation_rung=value["degradation_rung"],
            estimate_method=value.get("estimate_method"),
            fare=value.get("fare"),
            geometry_ref=value.get("geometry_ref"),
        )

    def validate(self) -> None:
        if not self.from_ref or not self.to_ref or self.from_ref == self.to_ref:
            raise MatrixError("MATRIX_ENDPOINT", "matrix cell requires two distinct endpoint refs")
        if self.travel_mode not in TRAVEL_MODES:
            raise MatrixError("MATRIX_MODE", "unsupported travel mode")
        if self.mode not in MATRIX_MODES:
            raise MatrixError("MATRIX_DATA_MODE", "matrix mode must be live, cached, or static")
        if self.duration_minutes is not None and (not isinstance(self.duration_minutes, int) or isinstance(self.duration_minutes, bool) or self.duration_minutes < 0):
            raise MatrixError("MATRIX_DURATION", "duration must be a non-negative integer or null")
        if self.distance_meters is not None and (not isinstance(self.distance_meters, int) or isinstance(self.distance_meters, bool) or self.distance_meters < 0):
            raise MatrixError("MATRIX_DISTANCE", "distance must be a non-negative integer or null")
        if not self.reachable and self.duration_minutes is not None:
            raise MatrixError("MATRIX_UNREACHABLE_DURATION", "unreachable cell cannot have a normal duration")
        if self.reachable and self.duration_minutes is None:
            raise MatrixError("MATRIX_REACHABLE_DURATION", "reachable cell requires a duration")
        if self.mode in ("live", "cached") and (not self.queried_at or not self.claim_ids):
            raise MatrixError("MATRIX_EVIDENCE", "live/cached cell requires query time and claims")
        if self.mode == "static" and self.reachable and not self.estimate_method:
            raise MatrixError("MATRIX_ESTIMATE", "static reachable cell requires an estimate method")

    def as_dict(self) -> Dict[str, Any]:
        return {
            "from_ref": self.from_ref,
            "to_ref": self.to_ref,
            "travel_mode": self.travel_mode,
            "duration_minutes": self.duration_minutes,
            "distance_meters": self.distance_meters,
            "provider": self.provider,
            "provider_version": self.provider_version,
            "mode": self.mode,
            "queried_at": self.queried_at,
            "claim_ids": list(self.claim_ids),
            "reachable": self.reachable,
            "degradation_rung": self.degradation_rung,
            "estimate_method": self.estimate_method,
            "fare": self.fare,
            "geometry_ref": self.geometry_ref,
        }


class RouteMatrix:
    def __init__(self, cells: Sequence[RouteCell] = ()) -> None:
        self._cells: Dict[Tuple[str, str, str], RouteCell] = {}
        for cell in cells:
            self.add(cell)

    @classmethod
    def from_mappings(cls, cells: Sequence[Mapping[str, Any]]) -> "RouteMatrix":
        return cls([RouteCell.from_mapping(cell) for cell in cells])

    def add(self, cell: RouteCell) -> None:
        cell.validate()
        key = (cell.from_ref, cell.to_ref, cell.travel_mode)
        if key in self._cells:
            raise MatrixError("MATRIX_DUPLICATE", "duplicate directed matrix cell")
        self._cells[key] = cell

    def get(self, from_ref: str, to_ref: str, travel_mode: str) -> Optional[RouteCell]:
        if from_ref == to_ref:
            return None
        return self._cells.get((from_ref, to_ref, travel_mode))

    def duration(self, from_ref: str, to_ref: str, travel_mode: str) -> int:
        if from_ref == to_ref:
            return 0
        cell = self.get(from_ref, to_ref, travel_mode)
        if cell is None:
            raise MatrixError("MATRIX_MISSING", "route cell is missing")
        if not cell.reachable:
            raise MatrixError("MATRIX_UNREACHABLE", "route cell is unreachable")
        if cell.duration_minutes is None:
            raise MatrixError("MATRIX_UNKNOWN", "route duration is unknown")
        return cell.duration_minutes

    def coverage(self, ordered_refs: Sequence[str], travel_mode: str) -> Tuple[Tuple[str, str], ...]:
        missing = []
        for left, right in zip(ordered_refs, ordered_refs[1:]):
            try:
                self.duration(left, right, travel_mode)
            except MatrixError:
                missing.append((left, right))
        return tuple(missing)

    def cells(self) -> Tuple[RouteCell, ...]:
        return tuple(self._cells[key] for key in sorted(self._cells))


def bounded_query_plan(
    endpoint_refs: Sequence[str],
    locked_refs: Sequence[str] = (),
    lodging_refs: Sequence[str] = (),
    cluster_neighbors: Optional[Mapping[str, Sequence[str]]] = None,
) -> Tuple[Tuple[str, str], ...]:
    endpoints = tuple(dict.fromkeys(endpoint_refs))
    required = tuple(dict.fromkeys(tuple(locked_refs) + tuple(lodging_refs)))
    pairs = set()
    for left in required:
        for right in required:
            if left != right:
                pairs.add((left, right))
    neighbors = cluster_neighbors or {}
    for left in endpoints:
        selected = [item for item in neighbors.get(left, ()) if item in endpoints and item != left][:5]
        for right in selected:
            pairs.add((left, right))
    return tuple(sorted(pairs))


def haversine_meters(left_lng: float, left_lat: float, right_lng: float, right_lat: float) -> int:
    radius = 6371008.8
    phi1 = math.radians(left_lat)
    phi2 = math.radians(right_lat)
    delta_phi = math.radians(right_lat - left_lat)
    delta_lambda = math.radians(right_lng - left_lng)
    value = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    return int(round(radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))))


def static_estimate_cell(
    from_ref: str,
    to_ref: str,
    travel_mode: str,
    distance_meters: int,
    speed_kmh: float,
    buffer_minutes: int,
) -> RouteCell:
    if distance_meters < 0 or speed_kmh <= 0 or buffer_minutes < 0:
        raise MatrixError("MATRIX_ESTIMATE_INPUT", "invalid static estimate inputs")
    duration = int(math.ceil(distance_meters / (speed_kmh * 1000 / 60))) + buffer_minutes
    return RouteCell(
        from_ref=from_ref,
        to_ref=to_ref,
        travel_mode=travel_mode,
        duration_minutes=duration,
        distance_meters=distance_meters,
        provider="ctw-static-estimate",
        provider_version="1",
        mode="static",
        queried_at=None,
        claim_ids=(),
        reachable=True,
        degradation_rung="R3",
        estimate_method="haversine/%gkmh/+%dmin" % (speed_kmh, buffer_minutes),
    )
