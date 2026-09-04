"""Deterministic beam insertion scheduler with structured no-solution output."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ..matrix import MatrixError, RouteMatrix


@dataclass(frozen=True)
class Candidate:
    ref_id: str
    title: str
    kind: str
    duration_minutes: int
    windows: Tuple[Tuple[datetime, datetime], ...]
    utility: int
    required: bool
    locked: bool
    fixed_start: Optional[datetime]
    cost_cny: int
    closed: bool
    blocked_reason: Optional[str]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "Candidate":
        windows = tuple((_dt(item["start_at"]), _dt(item["end_at"])) for item in value.get("windows", ()))
        return cls(
            ref_id=value["ref_id"],
            title=value["title"],
            kind=value.get("kind", "poi"),
            duration_minutes=int(value["duration_minutes"]),
            windows=windows,
            utility=int(value.get("utility", 0)),
            required=bool(value.get("required", False)),
            locked=bool(value.get("locked", False)),
            fixed_start=_dt(value["fixed_start"]) if value.get("fixed_start") else None,
            cost_cny=int(value.get("cost_cny", 0)),
            closed=bool(value.get("closed", False)),
            blocked_reason=value.get("blocked_reason"),
        )


@dataclass(frozen=True)
class EvaluatedSchedule:
    order: Tuple[str, ...]
    slots: Tuple[Mapping[str, Any], ...]
    total_utility: int
    total_travel_minutes: int
    total_cost_cny: int


@dataclass(frozen=True)
class ScheduleResult:
    status: str
    slots: Tuple[Mapping[str, Any], ...]
    excluded: Tuple[Mapping[str, str], ...]
    objective_vector: Mapping[str, Any]
    conflict: Optional[Mapping[str, Any]] = None
    relaxations: Tuple[str, ...] = ()

    def as_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "slots": [dict(item) for item in self.slots],
            "excluded": [dict(item) for item in self.excluded],
            "objective_vector": dict(self.objective_vector),
            "conflict": dict(self.conflict) if self.conflict else None,
            "relaxations": list(self.relaxations),
        }


class LightScheduler:
    def __init__(self, beam_width: int = 24) -> None:
        if beam_width <= 0:
            raise ValueError("beam width must be positive")
        self.beam_width = beam_width

    def schedule_day(self, problem: Mapping[str, Any]) -> ScheduleResult:
        day_id = problem["day_id"]
        day_start = _dt(problem["start_at"])
        day_end = _dt(problem["end_at"])
        travel_mode = problem.get("travel_mode", "transit")
        buffer_minutes = int(problem.get("buffer_minutes", 0))
        budget = problem.get("budget_cny")
        budget_value = int(budget) if budget is not None else None
        max_optional = int(problem.get("max_optional", 8))
        max_travel = problem.get("max_travel_minutes")
        max_travel_value = int(max_travel) if max_travel is not None else None
        candidates = {item.ref_id: item for item in (Candidate.from_mapping(raw) for raw in problem["candidates"])}
        if len(candidates) != len(problem["candidates"]):
            return _no_solution("duplicate_ref", "candidate refs must be unique", ())
        matrix = RouteMatrix.from_mappings(problem.get("matrix", ()))

        blocked: Dict[str, str] = {}
        active: List[Candidate] = []
        for candidate in candidates.values():
            reason = "closed" if candidate.closed else candidate.blocked_reason
            if candidate.duration_minutes <= 0:
                reason = "invalid_duration"
            if reason:
                if candidate.required or candidate.locked:
                    return _no_solution(reason, "%s is required but unavailable" % candidate.ref_id, ("unlock-or-replace:%s" % candidate.ref_id,))
                blocked[candidate.ref_id] = reason
            else:
                active.append(candidate)

        active.sort(key=lambda item: (not (item.required or item.locked), -item.utility, item.ref_id))
        states: List[Tuple[str, ...]] = [()]
        last_failures: List[str] = []
        for candidate in active:
            next_states: List[Tuple[str, ...]] = []
            if not (candidate.required or candidate.locked):
                next_states.extend(states)
            for state in states:
                for position in range(len(state) + 1):
                    order = state[:position] + (candidate.ref_id,) + state[position:]
                    evaluated, failure = self._evaluate(
                        order, candidates, matrix, day_id, day_start, day_end,
                        travel_mode, buffer_minutes, budget_value, max_optional,
                        max_travel_value,
                    )
                    if evaluated is not None:
                        next_states.append(order)
                    elif failure:
                        last_failures.append(failure)
            if not next_states:
                return _no_solution(
                    last_failures[-1] if last_failures else "no_feasible_insertion",
                    "required candidate %s has no feasible insertion" % candidate.ref_id,
                    ("relax-window-or-route:%s" % candidate.ref_id,),
                )
            unique = sorted(set(next_states), key=lambda order: self._order_key(
                order, candidates, matrix, day_id, day_start, day_end,
                travel_mode, buffer_minutes, budget_value, max_optional,
                max_travel_value,
            ))
            states = unique[: self.beam_width]

        evaluated_states = []
        for state in states:
            evaluated, _ = self._evaluate(
                state, candidates, matrix, day_id, day_start, day_end,
                travel_mode, buffer_minutes, budget_value, max_optional,
                max_travel_value,
            )
            if evaluated is not None:
                evaluated_states.append(evaluated)
        if not evaluated_states:
            return _no_solution("no_feasible_state", "no complete feasible schedule", ("relax-a-hard-constraint",))
        best = sorted(evaluated_states, key=_evaluated_key)[0]
        selected = set(best.order)
        excluded = dict(blocked)
        for candidate in candidates.values():
            if candidate.ref_id in selected or candidate.ref_id in excluded:
                continue
            _, failure = self._evaluate(
                best.order + (candidate.ref_id,), candidates, matrix, day_id,
                day_start, day_end, travel_mode, buffer_minutes, budget_value,
                max_optional, max_travel_value,
            )
            excluded[candidate.ref_id] = failure or "low-score"
        objective = {
            "required_selected": sum(1 for ref in best.order if candidates[ref].required or candidates[ref].locked),
            "utility": best.total_utility,
            "selected": len(best.order),
            "travel_minutes": best.total_travel_minutes,
            "cost_cny": best.total_cost_cny,
        }
        return ScheduleResult(
            status="SCHEDULED",
            slots=best.slots,
            excluded=tuple({"ref_id": ref, "reason": excluded[ref]} for ref in sorted(excluded)),
            objective_vector=objective,
        )

    def schedule_plan(self, problems: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
        results = [self.schedule_day(problem) for problem in problems]
        if any(result.status == "NO_SOLUTION" for result in results):
            first = next(result for result in results if result.status == "NO_SOLUTION")
            return {"status": "NO_SOLUTION", "days": [item.as_dict() for item in results], "conflict": first.conflict}
        return {"status": "SCHEDULED", "days": [item.as_dict() for item in results]}

    def _order_key(
        self,
        order: Tuple[str, ...],
        candidates: Mapping[str, Candidate],
        matrix: RouteMatrix,
        day_id: str,
        day_start: datetime,
        day_end: datetime,
        travel_mode: str,
        buffer_minutes: int,
        budget: Optional[int],
        max_optional: int,
        max_travel: Optional[int],
    ) -> Tuple[Any, ...]:
        evaluated, _ = self._evaluate(order, candidates, matrix, day_id, day_start, day_end, travel_mode, buffer_minutes, budget, max_optional, max_travel)
        return _evaluated_key(evaluated) if evaluated else (999999, order)

    def _evaluate(
        self,
        order: Sequence[str],
        candidates: Mapping[str, Candidate],
        matrix: RouteMatrix,
        day_id: str,
        day_start: datetime,
        day_end: datetime,
        travel_mode: str,
        buffer_minutes: int,
        budget: Optional[int],
        max_optional: int,
        max_travel: Optional[int],
    ) -> Tuple[Optional[EvaluatedSchedule], Optional[str]]:
        optional_count = sum(1 for ref in order if not (candidates[ref].required or candidates[ref].locked))
        if optional_count > max_optional:
            return None, "capacity"
        total_cost = sum(candidates[ref].cost_cny for ref in order)
        if budget is not None and total_cost > budget:
            return None, "budget"
        current = day_start
        previous: Optional[str] = None
        total_travel = 0
        slots: List[Mapping[str, Any]] = []
        for ref in order:
            candidate = candidates[ref]
            if previous is not None:
                try:
                    travel = matrix.duration(previous, ref, travel_mode)
                except MatrixError as exc:
                    reason = {
                        "MATRIX_UNREACHABLE": "route-unreachable",
                        "MATRIX_MISSING": "route-unknown",
                        "MATRIX_UNKNOWN": "route-unknown",
                    }.get(exc.code, "route")
                    return None, reason
                if max_travel is not None and travel > max_travel:
                    return None, "walking-limit"
                current += timedelta(minutes=travel + buffer_minutes)
                total_travel += travel
            scheduled = _fit_candidate(candidate, current, day_end)
            if scheduled is None:
                return None, "window"
            start, end = scheduled
            slots.append({
                "slot_id": "slot-" + candidate.ref_id,
                "day_id": day_id,
                "ref_id": candidate.ref_id,
                "title": candidate.title,
                "kind": candidate.kind,
                "start_at": start.isoformat(timespec="seconds"),
                "end_at": end.isoformat(timespec="seconds"),
                "locked": candidate.locked,
            })
            current = end
            previous = ref
        return EvaluatedSchedule(
            order=tuple(order),
            slots=tuple(slots),
            total_utility=sum(candidates[ref].utility for ref in order),
            total_travel_minutes=total_travel,
            total_cost_cny=total_cost,
        ), None


def _dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("scheduler timestamps require timezone")
    return parsed


def _fit_candidate(candidate: Candidate, earliest: datetime, day_end: datetime) -> Optional[Tuple[datetime, datetime]]:
    if candidate.fixed_start is not None:
        start = candidate.fixed_start
        end = start + timedelta(minutes=candidate.duration_minutes)
        if start < earliest or end > day_end:
            return None
        if candidate.windows and not any(window_start <= start and end <= window_end for window_start, window_end in candidate.windows):
            return None
        return start, end
    windows = candidate.windows or ((earliest, day_end),)
    for window_start, window_end in sorted(windows):
        start = max(earliest, window_start)
        end = start + timedelta(minutes=candidate.duration_minutes)
        if end <= window_end and end <= day_end:
            return start, end
    return None


def _evaluated_key(evaluated: EvaluatedSchedule) -> Tuple[Any, ...]:
    return (
        -evaluated.total_utility,
        -len(evaluated.order),
        evaluated.total_travel_minutes,
        evaluated.total_cost_cny,
        evaluated.order,
    )


def _no_solution(code: str, message: str, relaxations: Sequence[str]) -> ScheduleResult:
    return ScheduleResult(
        status="NO_SOLUTION",
        slots=(),
        excluded=(),
        objective_vector={},
        conflict={"code": code, "message": message},
        relaxations=tuple(relaxations),
    )

