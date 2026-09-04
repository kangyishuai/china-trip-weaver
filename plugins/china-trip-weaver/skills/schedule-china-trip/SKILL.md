---
name: schedule-china-trip
description: Create or validate deterministic day slots from a schema-valid Trip, a route-time matrix, opening windows, dwell times, buffers, and locks. Invoke explicitly from plan-china-trip after evidence collection; return a feasible schedule or a structured no-solution result, never silently drop a hard constraint.
---

# Schedule China Trip

Consume only normalized candidates and the frozen route-time matrix; do not call providers.

- Treat locks, transport/check-in times, opening windows, buffers, unreachable routes, and hard budgets as hard constraints.
- Use the deterministic lightweight scheduler by default. OR-Tools remains disabled unless the explicit feature flag, dependency probe, complete matrix, and threshold all pass; never install it.
- Return scheduled slots with selected order, times, matrix hops, exclusions, and objective vector, or `NO_SOLUTION` with a minimal conflict and optional relaxations.
- Do not render a normal Trip for a no-solution result and do not drop a requirement to make the output look complete.

The scheduler is executed inside the real plan command; there is no separate `ctw schedule` command:

```bash
scripts/ctw plan --request request.json --candidates candidates.json --rail off --output-json trip.json --output-html trip.html
```

The input files are the frozen request shape and `../../schema/candidates.schema.json`; success writes a schema-valid Trip and HTML, while infeasibility exits without a normal Trip.
