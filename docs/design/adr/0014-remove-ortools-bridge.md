# ADR-0014: Remove the OR-Tools bridge; light scheduling is the only engine

- **Status:** Accepted
- **Date:** 2026-09-08
- **Supersedes:** ADR-0005

## Context

ADR-0005 kept OR-Tools as an optional, threshold-gated second engine behind
`CTW_ENABLE_ORTOOLS=1`, alongside the default light scheduler. In practice
`scheduler/ortools_bridge.py` was never wired into `planning.py` or any other
production call site — `scheduler/__init__.py` exports only `LightScheduler`
and `ScheduleResult`. The bridge's `ortools_available` and
`should_use_ortools` helpers were reachable solely from
`tests/test_scheduler.py`, which exercised the threshold logic in isolation
without a live OR-Tools dependency or a production caller.

A repository-wide cleanup pass (2026-09-08) removing code with zero
production references found this module as one of five such cases. Since
ADR-0005's premise — a real second engine chosen by hard thresholds — was
never implemented past the standalone helper functions, keeping the module
was carrying dead code and an unmet architectural promise forward.

## Decision

Delete `scheduler/ortools_bridge.py` and its two dedicated tests. The light
scheduler (`scheduler/light.py`, `LightScheduler`) is the sole scheduling
engine; there is no threshold-based switch to a second engine, and none is
planned as part of this change. Deterministic beam insertion with bounded
local improvement, and the three-step `slow`-pace fallback recorded in
`PROGRESS.md`, remain the only scheduling strategy.

## Consequences

- One fewer dependency surface: no `CTW_ENABLE_ORTOOLS` flag, no optional
  `ortools` import path to keep working across Python/OR-Tools versions.
- Cases where a global solver could in principle beat the light algorithm's
  local-improvement result stay unaddressed, same as before this change —
  ADR-0005 documented that risk but no production path ever exercised the
  mitigation.
- Reintroducing a second engine is a new architecture decision, not a
  revert: it should start from a real call site in `planning.py`, not from
  restoring the deleted standalone bridge.

## Evidence

- `git grep -nE 'ortools_bridge' -- plugins tests scripts` returns no
  results after this change.
- Full suite before deletion: `Ran 516 tests`, `OK`, 0 skipped, including the
  two removed `SchedulerCorpusTests` cases
  (`test_ortools_is_never_imported_without_explicit_flag`,
  `test_ortools_thresholds_apply_only_after_probe`). After removal: 507
  tests, `OK`, 0 skipped.
- Superseded: `docs/design/adr/0005-optional-ortools.md`.
