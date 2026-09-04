"""Minimal normalized cache with context-complete keys and strict retention."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from .clock import Clock, SHANGHAI
from .contracts import canonical_json


DEFAULT_TTL_SECONDS = {
    "inventory": 5 * 60,
    "rail": 5 * 60,
    "flight": 5 * 60,
    "price": 15 * 60,
    "lodging": 15 * 60,
    "route": 6 * 60 * 60,
    "poi": 30 * 24 * 60 * 60,
    "geocode": 30 * 24 * 60 * 60,
    "research": 24 * 60 * 60,
    "static": 30 * 24 * 60 * 60,
}
FORBIDDEN_KEYS = frozenset((
    "apikey", "secret", "secretkey", "password", "credential", "credentials",
    "authorization", "authorizationheader", "cookie", "cookies", "userid",
    "username", "phone", "phonenumber", "idcard", "passport", "orderid",
    "paymentid",
))


@dataclass(frozen=True)
class CacheContext:
    provider: str
    provider_version: str
    capability: str
    parameters: Mapping[str, Any]
    as_of: str
    party: Mapping[str, Any]

    def canonical(self) -> Mapping[str, Any]:
        return {
            "provider": self.provider,
            "provider_version": self.provider_version,
            "capability": self.capability,
            "parameters": copy.deepcopy(dict(self.parameters)),
            "as_of": self.as_of,
            "party": copy.deepcopy(dict(self.party)),
        }

    def key(self) -> str:
        return hashlib.sha256(canonical_json(self.canonical()).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CacheHit:
    normalized_items: Tuple[Mapping[str, Any], ...]
    claims: Tuple[Mapping[str, Any], ...]
    stored_at: str
    expires_at: str
    mode: str = "cached"


def _assert_minimal(value: Any, path: str = "") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = key.lower().replace("_", "").replace("-", "")
            if normalized in FORBIDDEN_KEYS:
                raise ValueError("forbidden cache field at %s/%s" % (path, key))
            _assert_minimal(child, path + "/" + key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_minimal(child, path + "/%d" % index)
    elif isinstance(value, str):
        if "-----BEGIN " in value or re_secret_prefix(value):
            raise ValueError("credential-shaped cache value at %s" % (path or "/"))


def re_secret_prefix(value: str) -> bool:
    compact = value.strip()
    return (
        (compact.startswith("gh") and len(compact) > 24 and "_" in compact[:6])
        or (compact.startswith("sk-") and len(compact) > 24)
        or (compact.startswith("AKIA") and len(compact) == 20)
    )


class NormalizedCache:
    def __init__(self, root: Path, clock: Clock, enabled: bool = True) -> None:
        self.root = root
        self.clock = clock
        self.enabled = enabled
        if enabled:
            root.mkdir(parents=True, exist_ok=True, mode=0o700)
            if os.name == "posix":
                root.chmod(0o700)

    def put(
        self,
        context: CacheContext,
        normalized_items: Sequence[Mapping[str, Any]],
        claims: Sequence[Mapping[str, Any]],
        ttl_seconds: Optional[int] = None,
    ) -> bool:
        if not self.enabled:
            return False
        _assert_minimal(context.canonical())
        _assert_minimal(list(normalized_items))
        _assert_minimal(list(claims))
        ttl = DEFAULT_TTL_SECONDS.get(context.capability, 0) if ttl_seconds is None else ttl_seconds
        if ttl <= 0:
            raise ValueError("cache TTL must be positive")
        stored = self.clock.now().astimezone(SHANGHAI)
        payload = {
            "cache_version": 1,
            "key": context.key(),
            "context": context.canonical(),
            "stored_at": stored.isoformat(timespec="seconds"),
            "expires_at": (stored + timedelta(seconds=ttl)).isoformat(timespec="seconds"),
            "normalized_items": copy.deepcopy(list(normalized_items)),
            "claims": copy.deepcopy(list(claims)),
        }
        target = self.root / (context.key() + ".json")
        temporary = self.root / (context.key() + ".tmp")
        temporary.write_text(canonical_json(payload) + "\n", encoding="utf-8")
        if os.name == "posix":
            temporary.chmod(0o600)
        temporary.replace(target)
        if os.name == "posix":
            target.chmod(0o600)
        return True

    def get(self, context: CacheContext) -> Optional[CacheHit]:
        if not self.enabled:
            return None
        target = self.root / (context.key() + ".json")
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        if payload.get("key") != context.key() or canonical_json(payload.get("context")) != canonical_json(context.canonical()):
            raise ValueError("cache context mismatch")
        expires = datetime.fromisoformat(payload["expires_at"])
        if self.clock.now().astimezone(SHANGHAI) >= expires:
            return None
        claims = copy.deepcopy(payload["claims"])
        for claim in claims:
            claim["mode"] = "cached"
        return CacheHit(
            normalized_items=tuple(copy.deepcopy(payload["normalized_items"])),
            claims=tuple(claims),
            stored_at=payload["stored_at"],
            expires_at=payload["expires_at"],
        )
