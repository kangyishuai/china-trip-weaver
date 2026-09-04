---
name: replan-china-trip
description: Apply a versioned local patch to a schema-valid Trip after a disruption or user edit. Invoke explicitly from plan-china-trip with the current revision, event, locks, and affected scope; preserve unrelated days and accepted or booked items byte-for-byte and list every claim that must be reverified.
---

# Replan China Trip

Require the current Trip, exact base revision, event, and user locks.

- Reject a stale base revision; do not silently rebase it.
- Propagate only the event's affected day, adjacent hops, and dependencies. Preserve unrelated day canonical bytes and unexpired claims.
- Never change a locked/accepted/booked item unless the event makes it impossible and the user explicitly unlocks it.
- Return revision +1, allowed JSON Patch operations, affected/preserved/changed refs, stability score, reasons, and all claims requiring revalidation.
- If the affected scope cannot be made feasible, return structured no-solution instead of replanning the whole trip.

The event file is either the event object itself or a fixture wrapper containing `event` and `user_locked_refs`. Run:

```bash
scripts/ctw replan --trip trip.json --event event.json --base-revision 1 --output-json trip-r2.json --output-html trip-r2.html
```

Treat `revision_conflict` as a stop condition. Deliver only when the command reports `errors=0`; the output Trip contains the appended patch and revision metadata.
