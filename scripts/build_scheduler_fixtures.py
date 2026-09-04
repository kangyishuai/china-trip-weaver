#!/usr/bin/env python3
"""Build explicit synthetic scheduling, no-solution, and replan corpora."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "tests" / "fixtures" / "scheduler"
SYNTHETIC_AT = "2026-09-04T00:00:00+08:00"


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))


def iso(day: str, hour: int, minute: int = 0) -> str:
    return "%sT%02d:%02d:00+08:00" % (day, hour, minute)


def candidate(
    ref_id: str,
    title: str,
    *,
    duration: int = 60,
    utility: int = 50,
    required: bool = False,
    locked: bool = False,
    fixed_start: Optional[str] = None,
    windows: Sequence[Tuple[str, str]] = (),
    cost: int = 0,
    closed: bool = False,
    blocked_reason: Optional[str] = None,
    kind: str = "poi",
) -> Dict[str, Any]:
    return {
        "ref_id": ref_id,
        "title": title,
        "kind": kind,
        "duration_minutes": duration,
        "windows": [{"start_at": start, "end_at": end} for start, end in windows],
        "utility": utility,
        "required": required,
        "locked": locked,
        "fixed_start": fixed_start,
        "cost_cny": cost,
        "closed": closed,
        "blocked_reason": blocked_reason,
    }


def matrix_cells(
    refs: Sequence[str],
    duration: int = 15,
    overrides: Optional[Mapping[Tuple[str, str], Any]] = None,
    static: bool = False,
) -> List[Dict[str, Any]]:
    result = []
    changes = dict(overrides or {})
    for left in refs:
        for right in refs:
            if left == right:
                continue
            value = changes.get((left, right), duration)
            if value == "missing":
                continue
            reachable = value != "unreachable"
            minutes = int(value) if reachable else None
            mode = "static" if static else "live"
            result.append({
                "from_ref": left,
                "to_ref": right,
                "travel_mode": "transit",
                "duration_minutes": minutes,
                "distance_meters": minutes * 500 if minutes is not None else None,
                "provider": "ctw-static-estimate" if static else "synthetic-route-fixture",
                "provider_version": "1",
                "mode": mode,
                "queried_at": None if static else SYNTHETIC_AT,
                "claim_ids": [] if static else ["claim-route-%s-%s" % (left, right)],
                "reachable": reachable,
                "degradation_rung": "R3" if static else "R0",
                "estimate_method": "fixture-conservative-upper-bound" if static and reachable else None,
                "fare": None,
                "geometry_ref": None,
            })
    return result


def day_problem(
    case_id: str,
    day: str,
    candidates: Sequence[Mapping[str, Any]],
    expected_order: Sequence[str],
    *,
    excluded: Optional[Mapping[str, str]] = None,
    duration: int = 15,
    overrides: Optional[Mapping[Tuple[str, str], Any]] = None,
    static_matrix: bool = False,
    start_hour: int = 9,
    end_hour: int = 20,
    buffer_minutes: int = 10,
    budget: Optional[int] = None,
    max_optional: int = 8,
    max_travel: Optional[int] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    refs = [item["ref_id"] for item in candidates]
    matrix = matrix_cells(refs, duration=duration, overrides=overrides, static=static_matrix)
    problem = {
        "day_id": case_id + "-day",
        "date": day,
        "start_at": iso(day, start_hour),
        "end_at": iso(day, end_hour),
        "travel_mode": "transit",
        "buffer_minutes": buffer_minutes,
        "budget_cny": budget,
        "max_optional": max_optional,
        "max_travel_minutes": max_travel,
        "candidates": list(candidates),
        "matrix": matrix,
    }
    expected = manual_expected(problem, expected_order, excluded or {})
    return problem, expected


def manual_expected(problem: Mapping[str, Any], order: Sequence[str], excluded: Mapping[str, str]) -> Dict[str, Any]:
    candidates = {item["ref_id"]: item for item in problem["candidates"]}
    cells = {(item["from_ref"], item["to_ref"]): item for item in problem["matrix"]}
    current = datetime.fromisoformat(problem["start_at"])
    previous = None
    starts = []
    ends = []
    hops = []
    travel_total = 0
    for ref in order:
        item = candidates[ref]
        if previous is not None:
            cell = cells[(previous, ref)]
            minutes = cell["duration_minutes"]
            current += timedelta(minutes=minutes + problem["buffer_minutes"])
            travel_total += minutes
            hops.append({"from_ref": previous, "to_ref": ref, "duration_minutes": minutes})
        if item["fixed_start"]:
            current = datetime.fromisoformat(item["fixed_start"])
        elif item["windows"]:
            window_start = datetime.fromisoformat(item["windows"][0]["start_at"])
            current = max(current, window_start)
        starts.append(current.isoformat(timespec="seconds"))
        current += timedelta(minutes=item["duration_minutes"])
        ends.append(current.isoformat(timespec="seconds"))
        previous = ref
    objective = {
        "required_selected": sum(1 for ref in order if candidates[ref]["required"] or candidates[ref]["locked"]),
        "utility": sum(candidates[ref]["utility"] for ref in order),
        "selected": len(order),
        "travel_minutes": travel_total,
        "cost_cny": sum(candidates[ref]["cost_cny"] for ref in order),
    }
    return {
        "selected_ids": list(order),
        "start_at": starts,
        "end_at": ends,
        "hops": hops,
        "excluded": [{"ref_id": ref, "reason": excluded[ref]} for ref in sorted(excluded)],
        "objective_vector": objective,
    }


def golden_fixture(case_id: str, tags: Sequence[str], days: Sequence[Tuple[Mapping[str, Any], Mapping[str, Any]]]) -> Dict[str, Any]:
    return {
        "fixture_version": 1,
        "case_id": case_id,
        "tags": list(tags),
        "days": [problem for problem, _ in days],
        "expected": {"status": "SCHEDULED", "days": [expected for _, expected in days]},
    }


def simple_day(case_id: str, day: str, prefix: str, durations: Tuple[int, int] = (60, 60)):
    items = [
        candidate(prefix + "-a", "核心候选 A", duration=durations[0], utility=90),
        candidate(prefix + "-b", "核心候选 B", duration=durations[1], utility=70),
    ]
    return day_problem(case_id, day, items, [prefix + "-a", prefix + "-b"])


def build_goldens() -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    result.append(golden_fixture("weekend-1-basic", ["weekend", "1-day"], [simple_day("w1-basic", "2026-10-16", "w1")]))

    slow = [candidate("slow-a", "慢节奏博物馆", duration=150, utility=90), candidate("slow-b", "慢节奏街区", duration=120, utility=70)]
    result.append(golden_fixture("weekend-1-slow", ["weekend", "1-day", "pace-slow"], [day_problem("w1-slow", "2026-10-17", slow, ["slow-a", "slow-b"], duration=20, buffer_minutes=20)]))

    meal = [
        candidate("meal-a", "上午建筑", duration=90, utility=90),
        candidate("meal-m", "已锁午餐", duration=60, utility=100, required=True, locked=True, fixed_start=iso("2026-10-18", 12), windows=[(iso("2026-10-18", 12), iso("2026-10-18", 13))], kind="meal"),
        candidate("meal-z", "下午公园", duration=90, utility=60),
    ]
    result.append(golden_fixture("weekend-1-meal", ["weekend", "1-day", "meal", "locked"], [day_problem("w1-meal", "2026-10-18", meal, ["meal-a", "meal-m", "meal-z"], duration=10)]))

    result.append(golden_fixture("weekend-2-basic", ["weekend", "2-day"], [simple_day("w2-basic-1", "2026-10-16", "w2d1"), simple_day("w2-basic-2", "2026-10-17", "w2d2")]))

    closed_items = [candidate("closed-a", "开放博物馆", utility=90), candidate("closed-b", "周一闭馆", utility=80, closed=True)]
    result.append(golden_fixture("weekend-2-closed", ["weekend", "2-day", "closed-day"], [simple_day("w2-closed-1", "2026-10-18", "wc1"), day_problem("w2-closed-2", "2026-10-19", closed_items, ["closed-a"], excluded={"closed-b": "closed"})]))

    rain_items = [candidate("rain-a", "室内展览", utility=90), candidate("rain-b", "户外步行", utility=80, blocked_reason="weather")]
    result.append(golden_fixture("weekend-2-rain", ["weekend", "2-day", "weather"], [simple_day("w2-rain-1", "2026-10-20", "wr1"), day_problem("w2-rain-2", "2026-10-21", rain_items, ["rain-a"], excluded={"rain-b": "weather"})]))

    for length in (2, 3, 4, 5, 7):
        days = []
        start = date(2026, 11, 1)
        for index in range(length):
            day = (start + timedelta(days=index)).isoformat()
            if index == 0:
                prefix = "cross%d-d%d" % (length, index + 1)
                items = [
                    candidate(prefix + "-transport", "跨城铁路", duration=180, utility=200, required=True, locked=True, fixed_start=iso(day, 9), windows=[(iso(day, 9), iso(day, 12))], kind="transport"),
                    candidate(prefix + "-visit", "抵达后活动", duration=60, utility=60),
                ]
                days.append(day_problem("cross%d-%d" % (length, index + 1), day, items, [prefix + "-transport", prefix + "-visit"], duration=25, static_matrix=(length == 5)))
            else:
                days.append(simple_day("cross%d-%d" % (length, index + 1), day, "cross%d-d%d" % (length, index + 1)))
        result.append(golden_fixture("cross-city-%d-day" % length, ["cross-city", "%d-day" % length], days))

    for suffix, hour, mode in (("early", 10, "rail"), ("late", 16, "rail"), ("flight", 13, "flight")):
        day = "2026-11-%02d" % (10 + len(result) % 10)
        activity_windows = [(iso(day, 12), iso(day, 20))] if hour == 10 else []
        items = [
            candidate("move-%s-a" % suffix, "移动日前活动", duration=60, utility=80, windows=activity_windows),
            candidate("move-%s-m" % suffix, "已锁跨城%s" % mode, duration=120, utility=200, required=True, locked=True, fixed_start=iso(day, hour), windows=[(iso(day, hour), iso(day, min(23, hour + 2)))], kind="transport"),
        ]
        order = ["move-%s-a" % suffix, "move-%s-m" % suffix] if hour >= 13 else ["move-%s-m" % suffix, "move-%s-a" % suffix]
        result.append(golden_fixture("moving-day-%s" % suffix, ["moving-day", mode], [day_problem("moving-%s" % suffix, day, items, order, duration=20, start_hour=7, end_hour=22)]))

    day = "2026-12-01"
    narrow = [
        candidate("window-a", "上午窗口", duration=60, utility=90, windows=[(iso(day, 9), iso(day, 11))]),
        candidate("window-b", "下午窗口", duration=60, utility=80, windows=[(iso(day, 14), iso(day, 16))]),
    ]
    result.append(golden_fixture("overlapping-opening-windows", ["opening-window", "deterministic"], [day_problem("windows", day, narrow, ["window-a", "window-b"], duration=30)]))

    budget_items = [candidate("budget-a", "高优先候选", utility=100, cost=70), candidate("budget-b", "低优先候选", utility=60, cost=60)]
    result.append(golden_fixture("budget-hard-limit", ["budget"], [day_problem("budget", "2026-12-02", budget_items, ["budget-a"], excluded={"budget-b": "budget"}, budget=100)]))

    walking_items = [candidate("walk-a", "近点", utility=100), candidate("walk-b", "远点", utility=50)]
    walking_overrides = {("walk-a", "walk-b"): 90, ("walk-b", "walk-a"): 90}
    result.append(golden_fixture("walking-limit", ["walking-limit"], [day_problem("walking", "2026-12-03", walking_items, ["walk-a"], excluded={"walk-b": "walking-limit"}, overrides=walking_overrides, max_travel=30)]))

    unreachable_items = [candidate("unreach-a", "可达点", utility=100), candidate("unreach-b", "不可达点", utility=50)]
    unreachable_overrides = {("unreach-a", "unreach-b"): "unreachable", ("unreach-b", "unreach-a"): "unreachable"}
    result.append(golden_fixture("unreachable-optional", ["unreachable"], [day_problem("unreachable", "2026-12-04", unreachable_items, ["unreach-a"], excluded={"unreach-b": "route-unreachable"}, overrides=unreachable_overrides)]))

    tie_items = [candidate("tie-a", "同分 A", utility=80), candidate("tie-b", "同分 B", utility=80)]
    result.append(golden_fixture("deterministic-tie", ["tie", "deterministic"], [day_problem("tie", "2026-12-05", tie_items, ["tie-a", "tie-b"]) ]))

    prune_items = [candidate("prune-%s" % chr(97 + index), "候选 %d" % index, duration=30, utility=100 - index) for index in range(10)]
    selected = [item["ref_id"] for item in prune_items[:8]]
    excluded = {item["ref_id"]: "capacity" for item in prune_items[8:]}
    result.append(golden_fixture("candidate-prune-threshold", ["candidate>8", "capacity"], [day_problem("prune", "2026-12-06", prune_items, selected, excluded=excluded, duration=5, buffer_minutes=5, max_optional=8)]))

    if len(result) != 20:
        raise RuntimeError("expected exactly 20 golden fixtures")
    return result


def no_solution_fixture(case_id: str, tags: Sequence[str], problem: Mapping[str, Any], expected_code: str) -> Dict[str, Any]:
    return {
        "fixture_version": 1,
        "case_id": case_id,
        "tags": list(tags),
        "days": [problem],
        "expected": {"status": "NO_SOLUTION", "conflict_code": expected_code},
    }


def build_no_solutions() -> List[Dict[str, Any]]:
    day = "2026-12-10"
    fixtures = []

    overlap = [
        candidate("lock-a", "锁定 A", duration=90, utility=100, required=True, locked=True, fixed_start=iso(day, 9), windows=[(iso(day, 9), iso(day, 11))]),
        candidate("lock-b", "锁定 B", duration=90, utility=100, required=True, locked=True, fixed_start=iso(day, 9, 30), windows=[(iso(day, 9, 30), iso(day, 11, 30))]),
    ]
    fixtures.append(no_solution_fixture("locked-overlap", ["locked", "overlap"], day_problem("ns-lock", day, overlap, [])[0], "window"))

    late = [
        candidate("late-a", "到达交通", duration=60, utility=100, required=True, locked=True, fixed_start=iso(day, 9), windows=[(iso(day, 9), iso(day, 10))], kind="transport"),
        candidate("late-b", "锁定活动", duration=60, utility=100, required=True, locked=True, fixed_start=iso(day, 10, 30), windows=[(iso(day, 10, 30), iso(day, 11, 30))]),
    ]
    fixtures.append(no_solution_fixture("arrival-after-locked", ["transport", "locked"], day_problem("ns-late", day, late, [], overrides={("late-a", "late-b"): 60, ("late-b", "late-a"): 60})[0], "window"))

    closed = [candidate("closed-required", "全天闭馆", utility=100, required=True, closed=True)]
    fixtures.append(no_solution_fixture("closed-required", ["closed-day"], day_problem("ns-closed", day, closed, [])[0], "closed"))

    unreachable = [candidate("route-a", "起点", required=True), candidate("route-b", "必到点", required=True)]
    fixtures.append(no_solution_fixture("route-unreachable", ["unreachable"], day_problem("ns-route", day, unreachable, [], overrides={("route-a", "route-b"): "unreachable", ("route-b", "route-a"): "unreachable"})[0], "route-unreachable"))

    buffer_items = [
        candidate("buffer-a", "前项", duration=60, required=True, locked=True, fixed_start=iso(day, 9), windows=[(iso(day, 9), iso(day, 10))]),
        candidate("buffer-b", "后项", duration=60, required=True, locked=True, fixed_start=iso(day, 10, 10), windows=[(iso(day, 10, 10), iso(day, 11, 10))]),
    ]
    fixtures.append(no_solution_fixture("buffer-insufficient", ["buffer"], day_problem("ns-buffer", day, buffer_items, [], duration=0, buffer_minutes=15)[0], "window"))

    budget = [candidate("budget-required", "超预算必选", required=True, utility=100, cost=500)]
    fixtures.append(no_solution_fixture("budget-required", ["budget"], day_problem("ns-budget", day, budget, [], budget=100)[0], "budget"))

    checkin = [
        candidate("checkin-a", "到店交通", duration=120, required=True, locked=True, fixed_start=iso(day, 15), windows=[(iso(day, 15), iso(day, 17))], kind="transport"),
        candidate("checkin-b", "锁定入住", duration=30, required=True, locked=True, fixed_start=iso(day, 17, 10), windows=[(iso(day, 17, 10), iso(day, 17, 40))], kind="checkin"),
    ]
    fixtures.append(no_solution_fixture("checkin-conflict", ["lodging", "checkin"], day_problem("ns-checkin", day, checkin, [], duration=20, buffer_minutes=10)[0], "window"))

    unknown = [candidate("unknown-a", "起点", required=True), candidate("unknown-b", "未知路线必到", required=True)]
    fixtures.append(no_solution_fixture("all-routes-unknown", ["unknown-route"], day_problem("ns-unknown", day, unknown, [], overrides={("unknown-a", "unknown-b"): "missing", ("unknown-b", "unknown-a"): "missing"})[0], "route-unknown"))

    if len(fixtures) != 8:
        raise RuntimeError("expected exactly 8 no-solution fixtures")
    return fixtures


def replacement(slot_id: str, start_at: str, end_at: str, title: str) -> Mapping[str, Any]:
    return {
        "slot_id": slot_id,
        "start_at": start_at,
        "end_at": end_at,
        "kind": "free",
        "ref_id": None,
        "title": title,
        "locked": False,
        "status": "tentative",
        "claim_ids": [],
    }


def build_replans() -> List[Dict[str, Any]]:
    base = "tests/fixtures/trips/schema/valid/weekend-live.json"
    return [
        {
            "fixture_version": 1, "case_id": "closure", "base_fixture": base,
            "event": {"type": "closure", "subject_ref": "slot-1", "reason": "外滩临时关闭", "replacement_slot": replacement("slot-1-alt", "2026-10-16T09:30:00+08:00", "2026-10-16T11:30:00+08:00", "室内备选"), "reverify_claim_ids": ["claim-bund-hours"]},
            "user_locked_refs": [], "expected": {"affected_day": "day-1", "unchanged_day_indexes": [1], "operation_count": 1, "trigger": "closure"},
        },
        {
            "fixture_version": 1, "case_id": "weather", "base_fixture": base,
            "event": {"type": "weather", "subject_ref": "poi-bund", "reason": "暴雨改室内", "replacement_slot": replacement("slot-weather-alt", "2026-10-16T09:30:00+08:00", "2026-10-16T11:30:00+08:00", "雨天室内备选"), "reverify_claim_ids": ["claim-bund-hours"]},
            "user_locked_refs": [], "expected": {"affected_day": "day-1", "unchanged_day_indexes": [1], "operation_count": 1, "trigger": "weather"},
        },
        {
            "fixture_version": 1, "case_id": "delay", "base_fixture": base,
            "event": {"type": "delay", "subject_ref": "slot-2", "reason": "接驳晚点 15 分钟", "delta_minutes": 15, "reverify_claim_ids": ["claim-route-duration", "claim-route-fare"]},
            "user_locked_refs": [], "expected": {"affected_day": "day-1", "unchanged_day_indexes": [1], "operation_count": 4, "trigger": "delay"},
        },
        {
            "fixture_version": 1, "case_id": "user-delete", "base_fixture": base,
            "event": {"type": "user_delete", "subject_ref": "slot-3", "reason": "用户删除备选活动", "reverify_claim_ids": []},
            "user_locked_refs": [], "expected": {"affected_day": "day-2", "unchanged_day_indexes": [0], "operation_count": 1, "trigger": "user_edit"},
        },
    ]


def write_group(name: str, fixtures: Sequence[Mapping[str, Any]], manifest_files: List[Mapping[str, str]]) -> None:
    directory = OUTPUT / name
    directory.mkdir(parents=True, exist_ok=True)
    for fixture in fixtures:
        relative = Path(name) / (fixture["case_id"] + ".json")
        encoded = (json.dumps(fixture, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
        (OUTPUT / relative).write_bytes(encoded)
        manifest_files.append({"path": relative.as_posix(), "sha256": hashlib.sha256(encoded).hexdigest()})


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manifest_files: List[Mapping[str, str]] = []
    goldens = build_goldens()
    no_solutions = build_no_solutions()
    replans = build_replans()
    write_group("golden", goldens, manifest_files)
    write_group("no_solution", no_solutions, manifest_files)
    write_group("replan", replans, manifest_files)
    manifest = {
        "manifest_version": 1,
        "generated_by": "scripts/build_scheduler_fixtures.py",
        "counts": {"golden": len(goldens), "no_solution": len(no_solutions), "replan": len(replans)},
        "files": sorted(manifest_files, key=lambda item: item["path"]),
    }
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("wrote %d golden, %d no-solution, %d replan fixtures" % (len(goldens), len(no_solutions), len(replans)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
