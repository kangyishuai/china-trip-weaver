"""Optional OR-Tools boundary. It never imports or installs OR-Tools by default."""

from __future__ import annotations

import importlib.util
import os
from typing import Mapping, Sequence


def ortools_available(environ: Mapping[str, str] = os.environ) -> bool:
    if environ.get("CTW_ENABLE_ORTOOLS") != "1":
        return False
    return importlib.util.find_spec("ortools") is not None


def should_use_ortools(
    candidates_per_day: Sequence[int],
    hard_windows_per_day: Sequence[int],
    cross_day_constraints: int,
    light_no_solution: bool,
    hard_required_candidates: int,
    environ: Mapping[str, str] = os.environ,
) -> bool:
    if not ortools_available(environ):
        return False
    return (
        any(count >= 9 for count in candidates_per_day)
        or any(count >= 4 for count in hard_windows_per_day)
        or cross_day_constraints >= 2
        or (light_no_solution and hard_required_candidates <= 20)
    )
