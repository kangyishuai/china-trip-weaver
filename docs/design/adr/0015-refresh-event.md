# ADR-0015: `ctw replan --rail-result` wires the refresh event to a live rail query

- **Status:** Accepted
- **Date:** 2026-09-10

## Context

`replan_trip` already accepted a `refresh` event type and an optional
`rail_result` keyword argument, which replaces one rail transport leg with a
service selected from a `ctw rail --output-json`-shaped result — matching on
`service_number` when the event gives one, otherwise the earliest same-day
arrival. The `ctw replan` command line did not expose this argument:
`_cmd_replan` always called `replan_trip` without `rail_result`, so a refresh
event could only be exercised through the Python API or `run_replan_fixture`
in tests, never end-to-end from the CLI a user or Codex session actually runs.

## Decision

Add `--rail-result FILE` to `ctw replan`. It is required exactly when the
event document's `type` is `refresh`, and rejected — the CLI exits 1 before
ever calling `replan_trip` — for every other event type, since `replan_trip`
has no other use for the argument. When given, `_cmd_replan` reads the file
and checks only its top-level shape: `provider == "12306-mcp"` and the
presence of `transport_legs`, `claims`, and `health`. It does not re-validate
leg contents, claim shapes, or dates; that belongs to `_apply_refresh` and its
existing error codes (`refresh_result_required`, `refresh_not_rail`,
`refresh_no_service`, `refresh_service_not_found`, `refresh_unsupported`,
`refresh_overlap`), which the CLI surfaces unchanged through the existing
`REPLAN_FAILED <code> <message>` path.

Three boundaries scope this change:

1. **Evidence only, never structure.** `--rail-result` supplies claims and a
   replacement leg for the one code path `refresh` already defines in
   `replan.py`; it cannot add, remove, or reorder slots, days, or any other
   part of the Trip. Every other replan event type continues to reject the
   flag outright.
2. **Offline.** The CLI never calls a rail provider itself. The flow is
   always two steps — `ctw rail --output-json` (a separate, already-live
   command) writes a file, then `ctw replan --rail-result` reads it — so
   `ctw replan` stays a pure, offline JSON-in/JSON-out transform like every
   other replan event.
3. **Rail leg first.** Only a rail transport leg can be refreshed
   (`_find_rail_leg` requires `travel_mode == "rail"`); flight and other
   transport legs are out of scope for this event type until a future ADR
   extends it.

## Consequences

- A live refresh now runs as two offline-safe, independently testable
  commands: `ctw rail --date ... --output-json rail-result.json` then
  `ctw replan --trip trip.json --event refresh-event.json --rail-result
  rail-result.json --base-revision N --output-json trip-rN.json --output-html
  trip-rN.html`.
- The CLI's shape check is intentionally shallow; a `rail-result.json` that
  passes it but contains, say, a malformed claim still surfaces as a
  `REPLAN_FAILED <code>` from `replan_trip`'s own validation, not a second,
  competing validator in `cli.py`.
- `--rail-result` on a non-refresh event is a CLI-level contract, not a
  `replan_trip` one: a caller that imports `replan_trip` directly (as
  `run_replan_fixture` does in tests) can still pass `rail_result` alongside
  any event type without the CLI's guard, because `replan_trip` simply
  ignores the argument outside the `refresh` branch.

## Evidence

- `plugins/china-trip-weaver/src/china_trip_weaver/replan.py`:
  `VALID_EVENT_TYPES`, `_apply_refresh`, `_find_rail_leg`,
  `_select_refresh_service`.
- `plugins/china-trip-weaver/src/china_trip_weaver/cli.py`:
  `_add_replan_parser`, `_cmd_replan`.
- `tests/test_replan.py`:
  `test_all_four_replan_fixtures_run_through_cli_and_render` (now five
  fixtures including `refresh.json`, whose embedded `rail_result` is written
  to a file and passed via `--rail-result`),
  `test_cli_refresh_without_rail_result_fails_without_outputs`,
  `test_cli_non_refresh_event_with_rail_result_fails`.
- CLI acceptance run (2026-09-10): `refresh.json`'s fixture `event` and
  `rail_result` replayed through `ctw replan --trip demo/trip.json
  --rail-result ... --base-revision 1` produced revision 2 with
  `trigger=provider_change`, passed `ctw validate` and `ctw validate-html`,
  and the rendered HTML contained the refreshed service number `G1001`.

## Amendment (2026-09-12)

The default selection path (no `service_number` in the event) previously
picked the same-day service with the earliest arrival with no regard for
whether it could depart after the previous slot ends, so `_apply_refresh`'s
existing overlap check then failed the whole `replan` call whenever that
happened to be infeasible — which real-world same-day rail schedules hit far
more often than not (a real refresh drill hit it on 9 of 10 candidates).
`_select_refresh_service` now takes an additional `earliest_depart` argument
(the previous slot's `end_at`, or `None` for a day's first slot, computed and
passed by `_apply_refresh`) and, when no `service_number` is given, first
narrows the same-day candidates to those whose `depart_at` is not earlier
than `earliest_depart` before taking the earliest arrival among what remains.
Only when every same-day candidate is infeasible does it raise
`refresh_overlap`, now with a message naming both the candidate count and the
previous slot's end time (for example: "2 same-day services all depart
before the previous slot ends at 2026-10-18T16:00:00+08:00"). When the event
does give a `service_number`, this feasibility filter is not applied, and
`_apply_refresh`'s existing overlap check is unchanged — so `refresh_overlap`
from an explicit `service_number` still means exactly what it meant before
this amendment.

Requesting an explicit `service_number` can still match more than one
same-day candidate — 12306 sometimes returns two rows for the same service
number with different arrival times. `_select_refresh_service` now
disambiguates: rows whose `depart_at` and `arrive_at` are both identical are
treated as duplicates and the first one is used; otherwise the event may
supply `arrive_at` (a full ISO timestamp or a bare `HH:MM`) to pick the
matching row. When `arrive_at` is absent, or still resolves to more than one
row, `_select_refresh_service` raises the new error code
`refresh_service_ambiguous`, with a message listing every candidate's
`arrive_at` so the caller can retry with a disambiguating value.

Evidence: `tests/test_replan.py` —
`test_refresh_default_selection_skips_services_departing_before_previous_slot`,
`test_refresh_default_selection_reports_overlap_with_all_same_day_candidates`,
`test_refresh_service_number_ambiguous_arrival_times_without_disambiguator`,
`test_refresh_service_number_arrive_at_disambiguates_and_copies_only_that_rows_claims`;
the three tests already listed above under Evidence
(`test_replan_refresh_resolves_to_live_service`,
`test_refresh_rejects_overlap_with_previous_slot`,
`test_refresh_later_arrival_shifts_subsequent_same_day_slots`) pass unchanged.

The refresh patch now removes every existing claim whose `subject_ref` equals
the replaced leg's stable `leg_id` before copying the selected service's
current claims. Each removal is emitted as a `/claims/<index>` JSON Patch
operation in descending index order, and subsequent add paths use the shortened
array length, so the patch remains replayable while claims belonging to every
other leg and POI remain byte-for-byte unchanged. Repeating refresh therefore
replaces the prior refresh's evidence instead of accumulating unreferenced
claims. Evidence: `test_refresh_replaces_target_leg_claims_and_records_removals`,
`test_refresh_twice_keeps_only_the_second_service_claims`, and
`test_refresh_preserves_other_leg_and_poi_claims`.
