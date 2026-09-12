---
name: replan-china-trip
description: Apply a versioned local patch to a schema-valid Trip after a disruption or user edit. Invoke explicitly from plan-china-trip with the current revision, event, locks, and affected scope; preserve unrelated days and accepted or booked items byte-for-byte and list every claim that must be reverified.
---

# Replan China Trip

Require the current Trip, exact base revision, event, and user locks.

- Reject a stale base revision; do not silently rebase it.
- Propagate only the event's affected day, adjacent hops, and dependencies. Preserve unrelated day canonical bytes and unexpired claims.
- Preserve the recorded destination-search rung in provider health. If affected claims need new destination research, return them for `$research-china-destination`; do not choose a search provider here.
- Never change a locked/accepted/booked item unless the event makes it impossible and the user explicitly unlocks it.
- Return revision +1, allowed JSON Patch operations, affected/preserved/changed refs, stability score, reasons, and all claims requiring revalidation.
- If the affected scope cannot be made feasible, return structured no-solution instead of replanning the whole trip.

The event file is either the event object itself or a fixture wrapper containing `event` and `user_locked_refs`. Run:

```bash
scripts/ctw replan --trip trip.json --event event.json --base-revision 1 --output-json trip-r2.json --output-html trip-r2.html
```

A `refresh` event replaces one rail leg with a freshly queried 12306 service instead of editing a slot by hand; it is two commands, query then apply:

```bash
scripts/ctw rail --date 2026-10-16 --from CITY --to CITY --output-json rail-result.json
scripts/ctw replan --trip trip.json --event refresh-event.json --rail-result rail-result.json --base-revision 1 --output-json trip-r2.json --output-html trip-r2.html
```

`--rail-result` is required when the event's `type` is `refresh` and rejected for every other event type; it only checks the file's top-level shape (provider `12306-mcp` with `transport_legs`, `claims`, and `health`), then hands it to the same revision/lock/stability rules above. Omit the event's `service_number` to let it pick automatically: it only considers same-day services that depart no earlier than the previous slot ends, taking the earliest arrival among those, and fails with `refresh_overlap` (naming the candidate count and that end time) only when none qualify. Give a `service_number` that still matches more than one same-day row with different arrival times, and it fails with `refresh_service_ambiguous` unless the event also sets `arrive_at` (a full ISO timestamp or a bare `HH:MM`) to pick one.

A `suspend` event handles a service that stopped running altogether — a suspended ferry crossing, a cancelled train — by removing the leg and its slot in one patch instead of leaving a hand-patch step for later:

```bash
scripts/ctw replan --trip trip.json --event suspend-event.json --base-revision 1 --output-json trip-r2.json --output-html trip-r2.html
```

Give it the same `subject_ref` (the slot's `slot_id`, or the leg's `ref_id`) and a required `replacement_slot` as `closure`/`weather`, with two extra rules: `replacement_slot.kind` must be `free` or `poi`, and its `ref_id` must not point at the leg being removed. The patch removes the transport leg, the leg's `budget_ledger` line (recomputed via the same path `refresh` uses), and any claim whose `subject_ref` was that leg — they would otherwise be orphaned and fail validation. A locked leg or slot is rejected with `locked_ref`, same as every other event. The patch `trigger` is `disruption`.

Treat `revision_conflict` as a stop condition. Deliver only when the command reports `errors=0`; the output Trip contains the appended patch and revision metadata.
