"""Asia/Shanghai clocks with deterministic test injection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from zoneinfo import ZoneInfo


SHANGHAI = ZoneInfo("Asia/Shanghai")


class Clock(Protocol):
    def now(self) -> datetime:
        ...


@dataclass(frozen=True)
class SystemClock:
    def now(self) -> datetime:
        return datetime.now(tz=SHANGHAI)


@dataclass(frozen=True)
class FixedClock:
    instant: datetime

    def __post_init__(self) -> None:
        if self.instant.tzinfo is None:
            raise ValueError("FixedClock requires a timezone-aware datetime")

    @classmethod
    def from_iso(cls, value: str) -> "FixedClock":
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("fixed instant must include a timezone")
        return cls(parsed.astimezone(SHANGHAI))

    def now(self) -> datetime:
        return self.instant.astimezone(SHANGHAI)


def isoformat_seconds(clock: Clock) -> str:
    return clock.now().astimezone(SHANGHAI).isoformat(timespec="seconds")

