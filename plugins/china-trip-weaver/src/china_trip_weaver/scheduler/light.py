"""Deterministic beam insertion scheduler with structured no-solution output."""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ..matrix import MatrixError, RouteMatrix


@dataclass(frozen=True)
class PaceProfile:
    start_time: str
    end_time: str
    max_pois: int
    max_walking_segment_km: float
    lunch_rest_minutes: int


PACE_PROFILES: Mapping[str, PaceProfile] = {
    "slow": PaceProfile("09:00", "20:00", 3, 1.5, 90),
    "balanced": PaceProfile("08:30", "21:30", 5, 2.5, 60),
    "full": PaceProfile("08:00", "22:30", 7, 4.0, 30),
}


def pace_profile(value: str) -> PaceProfile:
    try:
        return PACE_PROFILES[value]
    except KeyError:
        raise ValueError("unsupported pace: %s" % value)


@dataclass(frozen=True)
class Candidate:
    ref_id: str
    public_ref_id: Optional[str]
    title: str
    kind: str
    duration_minutes: int
    windows: Tuple[Tuple[datetime, datetime], ...]
    utility: int
    required: bool
    locked: bool
    fixed_start: Optional[datetime]
    cost_cny: Optional[float]
    locationless: bool
    route_boundary: bool
    physical_intensity: str
    recovery: bool
    closed: bool
    blocked_reason: Optional[str]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "Candidate":
        windows = tuple((_dt(item["start_at"]), _dt(item["end_at"])) for item in value.get("windows", ()))
        raw_cost = value.get("cost_cny")
        return cls(
            ref_id=value["ref_id"],
            public_ref_id=value.get("public_ref_id", value["ref_id"]),
            title=value["title"],
            kind=value.get("kind", "poi"),
            duration_minutes=int(value["duration_minutes"]),
            windows=windows,
            utility=int(value.get("utility", 0)),
            required=bool(value.get("required", False)),
            locked=bool(value.get("locked", False)),
            fixed_start=_dt(value["fixed_start"]) if value.get("fixed_start") else None,
            cost_cny=float(raw_cost) if raw_cost is not None else None,
            locationless=bool(value.get("locationless", False)),
            route_boundary=bool(value.get("route_boundary", False)),
            physical_intensity=str(value.get("physical_intensity", "light")),
            recovery=bool(value.get("recovery", False)),
            closed=bool(value.get("closed", False)),
            blocked_reason=value.get("blocked_reason"),
        )


@dataclass(frozen=True)
class EvaluatedSchedule:
    order: Tuple[str, ...]
    slots: Tuple[Mapping[str, Any], ...]
    total_utility: int
    total_travel_minutes: int
    total_walking_meters: int
    total_cost_cny: float
    unknown_cost_refs: Tuple[str, ...]


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
        profile = pace_profile(str(problem["pace"])) if problem.get("pace") else None
        day_value = str(problem.get("date", ""))
        start_value = problem.get("start_at")
        end_value = problem.get("end_at")
        if start_value is None and profile is not None:
            start_value = "%sT%s:00+08:00" % (day_value, profile.start_time)
        if end_value is None and profile is not None:
            end_value = "%sT%s:00+08:00" % (day_value, profile.end_time)
        if start_value is None or end_value is None:
            raise ValueError("scheduler day requires start_at/end_at or a pace and date")
        day_start = _dt(str(start_value))
        day_end = _dt(str(end_value))
        travel_mode = problem.get("travel_mode", "transit")
        buffer_minutes = int(problem.get("buffer_minutes", 0))
        budget = problem.get("budget_cny")
        budget_value = float(budget) if budget is not None else None
        max_optional = int(problem.get("max_optional", 8))
        max_pois = problem.get("max_pois")
        if max_pois is None and profile is not None:
            max_pois = profile.max_pois
        max_pois_value = int(max_pois) if max_pois is not None else None
        max_walking = problem.get("max_walking_segment_meters")
        if max_walking is None and profile is not None:
            max_walking = int(round(profile.max_walking_segment_km * 1000))
        max_walking_value = int(max_walking) if max_walking is not None else None
        requires_senior_recovery = bool(problem.get("requires_senior_recovery", False))
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

        active.sort(key=lambda item: (
            not (item.required or item.locked),
            not item.recovery,
            -item.utility,
            item.ref_id,
        ))
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
                        max_travel_value, max_pois_value, max_walking_value,
                        requires_senior_recovery,
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
                max_travel_value, max_pois_value, max_walking_value,
                requires_senior_recovery,
            ))
            states = unique[: self.beam_width]

        evaluated_states = []
        for state in states:
            evaluated, _ = self._evaluate(
                state, candidates, matrix, day_id, day_start, day_end,
                travel_mode, buffer_minutes, budget_value, max_optional,
                max_travel_value, max_pois_value, max_walking_value,
                requires_senior_recovery,
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
                max_optional, max_travel_value, max_pois_value, max_walking_value,
                requires_senior_recovery,
            )
            excluded[candidate.ref_id] = failure or "low-score"
        objective = {
            "required_selected": sum(1 for ref in best.order if candidates[ref].required or candidates[ref].locked),
            "utility": best.total_utility,
            "selected": len(best.order),
            "travel_minutes": best.total_travel_minutes,
            "cost_cny": _plain_number(best.total_cost_cny),
        }
        if best.unknown_cost_refs:
            objective["unknown_cost_refs"] = list(best.unknown_cost_refs)
        if profile is not None:
            objective.update({
                "pace": str(problem["pace"]),
                "poi_selected": sum(1 for ref in best.order if candidates[ref].kind == "poi"),
                "walking_distance_meters": best.total_walking_meters,
            })
        return ScheduleResult(
            status="SCHEDULED",
            slots=best.slots,
            excluded=tuple({"ref_id": ref, "reason": excluded[ref]} for ref in sorted(excluded)),
            objective_vector=objective,
        )

    def schedule_plan(
        self,
        problems: Sequence[Mapping[str, Any]],
        budget_cny: Optional[float] = None,
        reserved_cost_cny: float = 0.0,
        reserved_unknown_refs: Sequence[str] = (),
        _allow_slow_fallback: bool = True,
    ) -> Mapping[str, Any]:
        if budget_cny is None:
            results = [self.schedule_day(problem) for problem in problems]
            if any(result.status == "NO_SOLUTION" for result in results):
                first = next(result for result in results if result.status == "NO_SOLUTION")
                failed = {"status": "NO_SOLUTION", "days": [item.as_dict() for item in results], "conflict": first.conflict}
                return self._slow_fallback(
                    problems, budget_cny, reserved_cost_cny, reserved_unknown_refs, failed,
                ) if _allow_slow_fallback else failed
            return {"status": "SCHEDULED", "days": [item.as_dict() for item in results]}

        trip_budget = float(budget_cny)
        reserved_cost = float(reserved_cost_cny)
        if trip_budget < 0:
            raise ValueError("trip budget must be non-negative")
        if reserved_cost < 0:
            raise ValueError("reserved trip cost must be non-negative")
        required_by_day = [_known_required_cost(problem) for problem in problems]
        required_total = sum(required_by_day) + reserved_cost
        if required_total > trip_budget:
            failed = _no_solution(
                "budget",
                "required plan cost %.2f exceeds trip budget %.2f" % (required_total, trip_budget),
                ("raise-budget-or-replace-required-cost",),
            )
            failure = {
                "status": "NO_SOLUTION",
                "days": [failed.as_dict()],
                "conflict": failed.conflict,
                "budget_ledger": {
                    "budget_cny": _plain_number(trip_budget),
                    "known_cost_cny": _plain_number(required_total),
                    "remaining_known_cny": _plain_number(trip_budget - required_total),
                    "unknown_cost_refs": sorted(set(_unknown_cost_refs(problems)) | set(reserved_unknown_refs)),
                    "status": "over_budget",
                },
            }
            return self._slow_fallback(
                problems, budget_cny, reserved_cost_cny, reserved_unknown_refs, failure,
            ) if _allow_slow_fallback else failure

        results: List[ScheduleResult] = []
        remaining_optional = trip_budget - required_total
        for problem, required_cost in zip(problems, required_by_day):
            day_problem = dict(problem)
            day_problem.pop("budget_cny", None)
            day_problem["budget_cny"] = required_cost + remaining_optional
            result = self.schedule_day(day_problem)
            results.append(result)
            if result.status == "NO_SOLUTION":
                break
            selected_refs = {slot["ref_id"] for slot in result.slots}
            optional_cost = sum(
                candidate.cost_cny or 0.0
                for candidate in (Candidate.from_mapping(raw) for raw in problem["candidates"])
                if candidate.ref_id in selected_refs
                and not (candidate.required or candidate.locked)
            )
            remaining_optional -= optional_cost
        if any(result.status == "NO_SOLUTION" for result in results):
            first = next(result for result in results if result.status == "NO_SOLUTION")
            failed = {"status": "NO_SOLUTION", "days": [item.as_dict() for item in results], "conflict": first.conflict}
            return self._slow_fallback(
                problems, budget_cny, reserved_cost_cny, reserved_unknown_refs, failed,
            ) if _allow_slow_fallback else failed
        known_cost = reserved_cost + sum(float(result.objective_vector["cost_cny"]) for result in results)
        unknown_refs = tuple(sorted({
            ref
            for result in results
            for ref in result.objective_vector.get("unknown_cost_refs", ())
        } | set(reserved_unknown_refs)))
        return {
            "status": "SCHEDULED",
            "days": [item.as_dict() for item in results],
            "budget_ledger": {
                "budget_cny": _plain_number(trip_budget),
                "known_cost_cny": _plain_number(known_cost),
                "remaining_known_cny": _plain_number(trip_budget - known_cost),
                "unknown_cost_refs": list(unknown_refs),
                "status": "incomplete" if unknown_refs else "within_budget",
            },
        }

    def _slow_fallback(
        self,
        problems: Sequence[Mapping[str, Any]],
        budget_cny: Optional[float],
        reserved_cost_cny: float,
        reserved_unknown_refs: Sequence[str],
        original_failure: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if (
            not problems
            or any(problem.get("pace") != "slow" for problem in problems)
        ):
            return original_failure

        relaxed = copy.deepcopy(list(problems))
        relaxations: List[str] = []

        for problem in relaxed:
            current = int(problem.get("max_pois", PACE_PROFILES["slow"].max_pois))
            problem["max_pois"] = max(0, current - 1)
        relaxations.append("SLOW_FALLBACK_REDUCE_DAILY_POIS max_pois=2")
        result = self.schedule_plan(
            relaxed,
            budget_cny,
            reserved_cost_cny,
            reserved_unknown_refs,
            _allow_slow_fallback=False,
        )
        if result["status"] == "SCHEDULED":
            return _with_relaxations(result, relaxations)

        for problem in relaxed:
            for candidate in problem["candidates"]:
                if candidate.get("kind") in ("poi", "meal"):
                    candidate["duration_minutes"] = max(
                        1, int(math.ceil(int(candidate["duration_minutes"]) * 0.70)),
                    )
        relaxations.append("SLOW_FALLBACK_COMPRESS_POI_DURATION factor=0.70 kinds=poi,meal")
        result = self.schedule_plan(
            relaxed,
            budget_cny,
            reserved_cost_cny,
            reserved_unknown_refs,
            _allow_slow_fallback=False,
        )
        if result["status"] == "SCHEDULED":
            return _with_relaxations(result, relaxations)

        for problem in relaxed:
            balanced_end = _dt(
                "%sT%s:00+08:00" % (problem["date"], PACE_PROFILES["balanced"].end_time)
            )
            current_end = _dt(str(problem["end_at"]))
            if balanced_end > current_end:
                problem["end_at"] = balanced_end.isoformat(timespec="seconds")
        relaxations.append("SLOW_FALLBACK_BALANCED_END_TIME end_time=21:30")
        result = self.schedule_plan(
            relaxed,
            budget_cny,
            reserved_cost_cny,
            reserved_unknown_refs,
            _allow_slow_fallback=False,
        )
        if result["status"] == "SCHEDULED":
            return _with_relaxations(result, relaxations)
        failed = dict(result)
        failed["attempted_relaxations"] = list(relaxations)
        return failed

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
        budget: Optional[float],
        max_optional: int,
        max_travel: Optional[int],
        max_pois: Optional[int],
        max_walking_segment_meters: Optional[int],
        requires_senior_recovery: bool,
    ) -> Tuple[Any, ...]:
        evaluated, _ = self._evaluate(
            order, candidates, matrix, day_id, day_start, day_end, travel_mode,
            buffer_minutes, budget, max_optional, max_travel, max_pois,
            max_walking_segment_meters, requires_senior_recovery,
        )
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
        budget: Optional[float],
        max_optional: int,
        max_travel: Optional[int],
        max_pois: Optional[int],
        max_walking_segment_meters: Optional[int],
        requires_senior_recovery: bool,
    ) -> Tuple[Optional[EvaluatedSchedule], Optional[str]]:
        optional_count = sum(1 for ref in order if not (candidates[ref].required or candidates[ref].locked))
        if optional_count > max_optional:
            return None, "capacity"
        poi_count = sum(1 for ref in order if candidates[ref].kind == "poi")
        if max_pois is not None and poi_count > max_pois:
            return None, "pace-poi-limit"
        total_cost = sum(candidates[ref].cost_cny or 0.0 for ref in order)
        unknown_cost_refs = tuple(sorted(ref for ref in order if candidates[ref].cost_cny is None))
        if budget is not None and total_cost > budget:
            return None, "budget"
        current = day_start
        previous_location: Optional[str] = None
        heavy_since_recovery = False
        total_travel = 0
        total_walking = 0
        slots: List[Mapping[str, Any]] = []
        for ref in order:
            candidate = candidates[ref]
            if requires_senior_recovery:
                if candidate.recovery:
                    heavy_since_recovery = False
                elif candidate.physical_intensity == "heavy":
                    if heavy_since_recovery:
                        return None, "senior-recovery-required"
                    heavy_since_recovery = True
            if (
                previous_location is not None
                and not candidate.locationless
                and not candidate.route_boundary
            ):
                try:
                    travel = matrix.duration(previous_location, ref, travel_mode)
                except MatrixError as exc:
                    reason = {
                        "MATRIX_UNREACHABLE": "route-unreachable",
                        "MATRIX_MISSING": "route-unknown",
                        "MATRIX_UNKNOWN": "route-unknown",
                    }.get(exc.code, "route")
                    return None, reason
                if max_travel is not None and travel > max_travel:
                    return None, "walking-limit"
                cell = matrix.get(previous_location, ref, travel_mode)
                if (
                    max_walking_segment_meters is not None
                    and travel_mode == "walk"
                    and candidates[previous_location].kind in ("poi", "meal")
                    and candidate.kind in ("poi", "meal")
                    and cell is not None
                    and cell.distance_meters is not None
                    and cell.distance_meters > max_walking_segment_meters
                ):
                    return None, "pace-walking-limit"
                if (
                    cell is not None
                    and cell.distance_meters is not None
                    and candidates[previous_location].kind in ("poi", "meal")
                    and candidate.kind in ("poi", "meal")
                    and (
                        travel_mode == "walk"
                        or max_walking_segment_meters is None
                        or cell.distance_meters <= max_walking_segment_meters
                    )
                ):
                    total_walking += cell.distance_meters
                current += timedelta(minutes=travel + buffer_minutes)
                total_travel += travel
            scheduled = _fit_candidate(candidate, current, day_end)
            if scheduled is None:
                return None, "window"
            start, end = scheduled
            slots.append({
                "slot_id": "slot-" + candidate.ref_id,
                "day_id": day_id,
                "ref_id": candidate.public_ref_id,
                "title": candidate.title,
                "kind": candidate.kind,
                "start_at": start.isoformat(timespec="seconds"),
                "end_at": end.isoformat(timespec="seconds"),
                "locked": candidate.locked,
            })
            current = end
            if candidate.route_boundary:
                previous_location = None
            elif not candidate.locationless:
                previous_location = ref
        return EvaluatedSchedule(
            order=tuple(order),
            slots=tuple(slots),
            total_utility=sum(candidates[ref].utility for ref in order),
            total_travel_minutes=total_travel,
            total_walking_meters=total_walking,
            total_cost_cny=total_cost,
            unknown_cost_refs=unknown_cost_refs,
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
        len(evaluated.unknown_cost_refs),
        evaluated.total_travel_minutes,
        evaluated.total_walking_meters,
        evaluated.total_cost_cny,
        evaluated.order,
    )


def _known_required_cost(problem: Mapping[str, Any]) -> float:
    return sum(
        candidate.cost_cny or 0.0
        for candidate in (Candidate.from_mapping(raw) for raw in problem["candidates"])
        if candidate.required or candidate.locked
    )


def _unknown_cost_refs(problems: Sequence[Mapping[str, Any]]) -> Tuple[str, ...]:
    return tuple(sorted({
        candidate.ref_id
        for problem in problems
        for candidate in (Candidate.from_mapping(raw) for raw in problem["candidates"])
        if candidate.cost_cny is None
    }))


def _plain_number(value: float) -> float:
    numeric = float(value)
    return int(numeric) if numeric.is_integer() else round(numeric, 2)


def _with_relaxations(
    result: Mapping[str, Any],
    relaxations: Sequence[str],
) -> Mapping[str, Any]:
    selected = dict(result)
    selected["applied_relaxations"] = list(relaxations)
    return selected


def _no_solution(code: str, message: str, relaxations: Sequence[str]) -> ScheduleResult:
    return ScheduleResult(
        status="NO_SOLUTION",
        slots=(),
        excluded=(),
        objective_vector={},
        conflict={"code": code, "message": message},
        relaxations=tuple(relaxations),
    )
