"""Same-day rail service selection shared by planning and replan."""

from __future__ import annotations

from typing import Any, Mapping, NamedTuple, Optional, Sequence, Tuple


class ServiceSelection(NamedTuple):
    """Result of matching one service_number against a day's candidate rows.

    `same_service` holds every candidate sharing service_number regardless of
    outcome; it is empty exactly when that service did not run that day at
    all (a "not found" result). `row` is set only when exactly one row
    remains after disambiguation. When `row` is None but `same_service` is
    not empty, the match is still ambiguous and `time_matched` holds the
    rows narrowed by the requested time hint (empty if the hint matched none
    of `same_service`) — callers report these as the remaining candidates.
    """

    row: Optional[Mapping[str, Any]]
    same_service: Tuple[Mapping[str, Any], ...]
    time_matched: Tuple[Mapping[str, Any], ...]


def select_service(
    candidates: Sequence[Mapping[str, Any]],
    service_number: str,
    requested_depart_at: Optional[str] = None,
    requested_arrive_at: Optional[str] = None,
) -> ServiceSelection:
    """Pick the row in `candidates` (already limited to a single day) whose
    service_number matches, disambiguating multiple same-service rows by an
    optional requested depart/arrive time (a full timestamp or "HH:MM").
    """
    same_service = tuple(item for item in candidates if item.get("service_number") == service_number)
    if not same_service:
        return ServiceSelection(None, (), ())
    if len(same_service) == 1:
        return ServiceSelection(same_service[0], same_service, ())
    if len({(item.get("depart_at"), item.get("arrive_at")) for item in same_service}) == 1:
        return ServiceSelection(same_service[0], same_service, ())
    time_matched = same_service
    if requested_depart_at:
        time_matched = tuple(
            item for item in time_matched if _matches_time(item.get("depart_at"), requested_depart_at)
        )
    if requested_arrive_at:
        time_matched = tuple(
            item for item in time_matched if _matches_time(item.get("arrive_at"), requested_arrive_at)
        )
    if len(time_matched) == 1:
        return ServiceSelection(time_matched[0], same_service, ())
    return ServiceSelection(None, same_service, time_matched)


def _matches_time(item_value: Any, requested: str) -> bool:
    item_value = str(item_value)
    if item_value == requested:
        return True
    if len(requested) == 5 and requested[2] == ":":
        return item_value[11:16] == requested
    return False
