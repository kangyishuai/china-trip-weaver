"""Plain-data contracts shared by every China Trip Weaver layer."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


JSONValue = Any


def canonical_json(value: JSONValue) -> str:
    """Return the one canonical JSON representation used for hashes and equality."""

    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def canonical_bytes(value: JSONValue) -> bytes:
    return canonical_json(value).encode("utf-8")


def canonical_sha256(value: JSONValue) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("JSON document must be an object")
    return value


def write_canonical_json(path: Path, value: JSONValue) -> None:
    path.write_text(canonical_json(value) + "\n", encoding="utf-8")


@dataclass(frozen=True)
class TripDocument:
    """A defensive wrapper around the single public Trip JSON model."""

    data: Mapping[str, Any]

    @classmethod
    def from_path(cls, path: Path) -> "TripDocument":
        return cls(read_json(path))

    def to_dict(self) -> Dict[str, Any]:
        return copy.deepcopy(dict(self.data))

    def canonical_json(self) -> str:
        return canonical_json(self.data)

    def sha256(self) -> str:
        return canonical_sha256(self.data)


@dataclass(frozen=True)
class ProviderRequest:
    request_id: str
    capability: str
    parameters: Mapping[str, Any]
    deadline_ms: int
    as_of: str
    cache_policy: str = "prefer"
    trace: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AdapterResult:
    provider: str
    provider_version: str
    capability: str
    mode: str
    queried_at: str
    normalized_items: Tuple[Mapping[str, Any], ...]
    claims: Tuple[Mapping[str, Any], ...]
    health: Mapping[str, Any]
    warnings: Tuple[str, ...] = ()
    raw_ref: Optional[str] = None
    response_hash: Optional[str] = None
    error_class: Optional[str] = None

    @classmethod
    def build(
        cls,
        provider: str,
        provider_version: str,
        capability: str,
        mode: str,
        queried_at: str,
        normalized_items: Sequence[Mapping[str, Any]],
        claims: Sequence[Mapping[str, Any]],
        health: Mapping[str, Any],
        warnings: Sequence[str] = (),
        raw_ref: Optional[str] = None,
        response_hash: Optional[str] = None,
        error_class: Optional[str] = None,
    ) -> "AdapterResult":
        return cls(
            provider=provider,
            provider_version=provider_version,
            capability=capability,
            mode=mode,
            queried_at=queried_at,
            normalized_items=tuple(copy.deepcopy(list(normalized_items))),
            claims=tuple(copy.deepcopy(list(claims))),
            health=copy.deepcopy(dict(health)),
            warnings=tuple(warnings),
            raw_ref=raw_ref,
            response_hash=response_hash,
            error_class=error_class,
        )


@dataclass(frozen=True)
class MatrixCell:
    from_ref: str
    to_ref: str
    travel_mode: str
    duration_minutes: Optional[int]
    distance_meters: Optional[int]
    provider: str
    provider_version: str
    mode: str
    queried_at: str
    claim_ids: Tuple[str, ...]
    reachable: bool
    degradation_rung: str
    fare: Optional[Mapping[str, Any]] = None
    geometry_ref: Optional[str] = None


@dataclass(frozen=True)
class PatchResult:
    trip: Mapping[str, Any]
    patch: Mapping[str, Any]
    reverify_claim_ids: Tuple[str, ...]
