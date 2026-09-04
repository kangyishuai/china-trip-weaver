---
name: schedule-china-trip
description: Create or validate deterministic day slots from a schema-valid Trip, a route-time matrix, opening windows, dwell times, buffers, and locks. Invoke explicitly from plan-china-trip after evidence collection; return a feasible schedule or a structured no-solution result, never silently drop a hard constraint.
---

# Schedule China Trip

Consume only normalized candidates and the frozen route-time matrix; do not call providers.

- Treat locks, transport/check-in times, opening windows, buffers, unreachable routes, and the single whole-trip budget ledger as hard constraints. Never copy the trip budget into each day or coerce an unknown price to zero.
- Apply the request pace in the scheduler: `slow` is 09:00–20:00, at most 3 POIs, 1.5 km per walking segment, and 90 minutes of lunch rest; `balanced` is 08:30–21:30, 5 POIs, 2.5 km, and 60 minutes; `full` is 08:00–22:30, 7 POIs, 4 km, and 30 minutes. A user `walking_tolerance_km` overrides the mapped walking threshold.
- Reserve required lunch and dinner slots for 60 minutes, using lunch starts at 12:00±1 hour and dinner starts at 18:00±1.5 hours unless `meal_windows` overrides them. Reserve `rest_windows` or the pace-default lunch rest, and add a required luggage/transfer buffer on every cross-city day.
- Read optional `mobility_profile`; when `senior=true`, never place two `physical_intensity=heavy` POIs without a recovery `rest` slot between them, even when fitness is `good`.
- Accumulate comparable CNY POI, scheduled transport, and selected lodging prices across the trip. Emit a min/max range and an `unknowns` reason when room count, tax inclusion, currency, unit, or an unverified/from-price prevents a single comparable total.
- Use the deterministic lightweight scheduler by default. OR-Tools remains disabled unless the explicit feature flag, dependency probe, complete matrix, and threshold all pass; never install it.
- Return scheduled slots with selected order, times, matrix hops, exclusions, and objective vector, or `NO_SOLUTION` with a minimal conflict and optional relaxations.
- Preserve claims and provider health, including the destination-search rung, without rewriting which search tool supplied the evidence.
- Do not render a normal Trip for a no-solution result and do not drop a requirement to make the output look complete.

The scheduler is executed inside the real plan command; there is no separate `ctw schedule` command:

```bash
scripts/ctw plan --request request.json --candidates candidates.json --rail off --output-json trip.json --output-html trip.html
```

The input files follow the request definition in `../../schema/trip.schema.json` and `../../schema/candidates.schema.json`; success writes a schema-valid Trip and HTML, while infeasibility exits without a normal Trip.
