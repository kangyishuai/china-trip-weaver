"""P0-P6 transition and checkpoint integrity guards."""

from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .contracts import canonical_json


STAGES = (
    "INTAKE",
    "RESEARCHED",
    "CANDIDATES_READY",
    "MATRIX_READY",
    "MATRIX_DEGRADED",
    "SCHEDULED",
    "NO_SOLUTION",
    "VALIDATED",
    "RENDERED",
)
TRANSITIONS = {
    None: ("INTAKE",),
    "INTAKE": ("RESEARCHED",),
    "RESEARCHED": ("CANDIDATES_READY",),
    "CANDIDATES_READY": ("MATRIX_READY", "MATRIX_DEGRADED"),
    "MATRIX_READY": ("SCHEDULED", "NO_SOLUTION"),
    "MATRIX_DEGRADED": ("SCHEDULED", "NO_SOLUTION"),
    "SCHEDULED": ("VALIDATED",),
    "NO_SOLUTION": (),
    "VALIDATED": ("RENDERED",),
    "RENDERED": (),
}
FORBIDDEN_CHECKPOINT_KEYS = frozenset((
    "password", "secret", "api_key", "apikey", "authorization", "cookie",
    "credential", "credentials",
))


class PipelineError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class Checkpoint:
    stage: str
    schema_version: str
    trip_id: str
    revision: int
    input_hash: str
    payload_hash: str
    provider_versions: Mapping[str, str]
    payload: Mapping[str, Any]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "stage": self.stage,
            "schema_version": self.schema_version,
            "trip_id": self.trip_id,
            "revision": self.revision,
            "input_hash": self.input_hash,
            "payload_hash": self.payload_hash,
            "provider_versions": dict(self.provider_versions),
            "payload": copy.deepcopy(dict(self.payload)),
        }


class PipelineRun:
    def __init__(self, normalized_input: Mapping[str, Any], schema_version: str = "1.0.0") -> None:
        _assert_safe(normalized_input)
        self.normalized_input = copy.deepcopy(dict(normalized_input))
        self.schema_version = schema_version
        self.input_hash = _hash(normalized_input)
        self._checkpoints: List[Checkpoint] = []

    @property
    def stage(self) -> Optional[str]:
        return self._checkpoints[-1].stage if self._checkpoints else None

    def advance(
        self,
        stage: str,
        payload: Mapping[str, Any],
        trip_id: str,
        revision: int,
        provider_versions: Optional[Mapping[str, str]] = None,
    ) -> Checkpoint:
        if stage not in STAGES:
            raise PipelineError("stage_unknown", "unknown pipeline stage")
        if stage not in TRANSITIONS[self.stage]:
            raise PipelineError("stage_order", "invalid transition %s -> %s" % (self.stage, stage))
        _assert_safe(payload)
        checkpoint = Checkpoint(
            stage=stage,
            schema_version=self.schema_version,
            trip_id=trip_id,
            revision=revision,
            input_hash=self.input_hash,
            payload_hash=_hash(payload),
            provider_versions=dict(provider_versions or {}),
            payload=copy.deepcopy(dict(payload)),
        )
        self._checkpoints.append(checkpoint)
        return checkpoint

    def resume(self, normalized_input: Mapping[str, Any], provider_versions: Mapping[str, str]) -> Optional[Checkpoint]:
        if _hash(normalized_input) != self.input_hash:
            return None
        for checkpoint in reversed(self._checkpoints):
            if all(provider_versions.get(name) == version for name, version in checkpoint.provider_versions.items()):
                return checkpoint
        return None

    def invalidate_from(self, stage: str) -> None:
        if stage not in STAGES:
            raise PipelineError("stage_unknown", "unknown pipeline stage")
        index = next((index for index, item in enumerate(self._checkpoints) if item.stage == stage), len(self._checkpoints))
        del self._checkpoints[index:]

    def checkpoints(self) -> Tuple[Checkpoint, ...]:
        return tuple(self._checkpoints)


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _assert_safe(value: Any, path: str = "") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = key.lower().replace("-", "").replace("_", "")
            if normalized in {item.replace("_", "") for item in FORBIDDEN_CHECKPOINT_KEYS}:
                raise PipelineError("checkpoint_secret", "forbidden checkpoint field at %s/%s" % (path, key))
            _assert_safe(child, path + "/" + str(key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_safe(child, path + "/%d" % index)
