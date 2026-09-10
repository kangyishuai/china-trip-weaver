# ADR-0016: Rental cars and ferries as first-class transport

- **Status:** Proposed
- **Date:** 2026-09-10

## Context

Real itineraries already need two transport shapes the planner cannot express
structurally today: a multi-day, one-way car rental (pick up in one city,
drop off in another, subject to a holiday minimum-rental-period rule) and a
real-name ferry ticket that must be bought the moment sales open, with a
same-day fallback if the crossing is suspended. Both currently have to be
squeezed into `request.assumptions` free text, with any schedule change made
by hand-editing a `closure` replan patch. This section inventories, with
reproducible `file:line` evidence, everything a "make rental cars and ferries
first-class" change would touch, so the Decision below can be judged against
what the code actually does rather than what it is assumed to do.

### Functions that branch on `travel_mode`

- `plugins/china-trip-weaver/src/china_trip_weaver/journey.py:1341` (`_segment_connections`) —
  the only exclusion when picking a same-day transport leg to bridge two Journey
  segments is literal `"flight"`; `drive`/`ferry` legs are treated the same as
  `rail`/`transit`/`walk`.
- `plugins/china-trip-weaver/src/china_trip_weaver/matrix.py:11,61` (`TRAVEL_MODES`,
  `RouteRequest.validate`) — a 9-mode membership check with no per-value
  behavior; `drive`/`ferry` already pass it.
- `plugins/china-trip-weaver/src/china_trip_weaver/planning.py:638,1365,1625,2062,2097`
  (`_day_city_by_date`, `_is_meeting_arrival_leg`, `_routine_availability`,
  `_schedule_problems` ×2) — five independent call sites that each exclude only
  literal `"flight"`; every one silently sends `drive`/`ferry` legs down the
  default ground-transport path with no dedicated handling.
- `plugins/china-trip-weaver/src/china_trip_weaver/planning.py:210` (`plan_trip`) —
  the `rail_legs` progress counter matches literal `"rail"` only.
- `plugins/china-trip-weaver/src/china_trip_weaver/providers/amap.py:261-270`
  (`_route_source`) — AMap routing is wired for `walk`/`transit`/`drive`/`ride`
  only; there is no `ferry` route source and none is implied elsewhere.
- `plugins/china-trip-weaver/src/china_trip_weaver/replan.py:333,361`
  (`_find_rail_leg`, `_recompute_rail_health`) — the `refresh` event can locate
  and recompute health for `"rail"` legs only; it cannot target a `drive` or
  `ferry` leg.
- `plugins/china-trip-weaver/src/china_trip_weaver/scheduler/light.py:497,511`
  (`_evaluate`) — intra-day slot interleaving special-cases literal `"walk"`.
- `plugins/china-trip-weaver/src/china_trip_weaver/validate_trip.py:318`
  (`semantic_issues`) — the "multi-destination trip needs an origin" check
  triggers on `("rail", "flight")` only; a `drive`/`ferry`-only itinerary never
  trips it even when it has the same structural gap.

### Schema fields relevant if rental cars and ferries become first-class

- `plugins/china-trip-weaver/schema/trip.schema.json:553` — `transportLeg.travel_mode`
  enum already lists `drive` and `ferry`; no schema edit is needed just to add
  such a leg.
- `plugins/china-trip-weaver/schema/trip.schema.json:550-576` — `transportLeg`
  already carries `from_ref`/`to_ref`/`depart_at`/`arrive_at`/`duration_minutes`/
  `provider`/`service_number`/`price`/`booking_url`/`claim_ids`/`locked`, i.e.
  pickup/return place and time, an official-channel link, and a price slot.
- `plugins/china-trip-weaver/schema/trip.schema.json:444` — `request.parking_required`
  exists, but its established meaning is "does the lodging search need parking",
  not "is the traveler self-driving"; it is not a rental-car signal.
- `plugins/china-trip-weaver/schema/trip.schema.json:473-474` — `request.constraints`/
  `request.assumptions` (both `$defs/stringList`) — free-text, already in active
  use: `demo/request.json` ships `"assumptions": ["无地图 Key 时使用保守静态路线估算"]`.
- `plugins/china-trip-weaver/schema/trip.schema.json:497-499` — `slot.kind` enum
  (`poi`/`meal`/`lodging`/`transport`/`rest`/`free`/`checkin`/`checkout`) already
  has `transport`, usable for a day's pickup/return time block.
- `plugins/china-trip-weaver/schema/trip.schema.json:248-251` — `budgetItem.category`
  enum (`poi`/`transport`/`lodging`) already has `transport`; `budgetItem.price_type`
  already includes `verify-on-click`, matching "no live price API, check the
  official channel at booking time".
- `plugins/china-trip-weaver/src/china_trip_weaver/journey.py:2077`
  (`_journey_trace_deadline`) — "deadline" for a priority action is defined as
  `depart_at` (transport leg) or `check_in` (lodging) only; there is no concept
  of a booking/sale-open date that precedes departure. This is the one place a
  useful rental/ferry reminder needs new logic regardless of schema choice.

### Producer functions (what currently creates `transport_legs`)

- `plugins/china-trip-weaver/src/china_trip_weaver/planning.py:1449` (`_deep_link_leg`,
  `"rail"` leg at line 1487) — the only rail producer, a 12306 deep link.
- `plugins/china-trip-weaver/src/china_trip_weaver/planning.py:2044`
  (`_schedule_problems`, `"transit"` at line 2275) — not a `transport_legs`
  producer; it is an internal scheduling constraint that hardcodes intra-day
  movement as `transit`, so a self-driving day is not reflected here either.
- `plugins/china-trip-weaver/src/china_trip_weaver/providers/flyai.py:94` — the
  only flight producer.
- `plugins/china-trip-weaver/src/china_trip_weaver/mobility.py:124` (`resolve`) —
  POI/lodging geocoding and AMap route enrichment; it aliases `drive`/`ride` to
  AMap's driving/cycling APIs (`MODE_ALIASES`, `mobility.py:23-31`) but has no
  concept of a rental period, a pickup counter, or a drop-off fee — it only
  computes a point-to-point route.

### Render sections

- `plugins/china-trip-weaver/src/china_trip_weaver/render/html.py:484`
  (`_transport_section`) and `plugins/china-trip-weaver/src/china_trip_weaver/render/journey_html.py:700`
  (`_transport_overview_section`) both render every leg through one generic
  card templated on `travel_mode`, with the label coming from a lookup table
  (`render/html.py:28,59`); neither branches by mode, so `drive`/`ferry` legs
  already render today with no new section required.
- `plugins/china-trip-weaver/src/china_trip_weaver/render/journey_html.py:594`
  (`_priority_actions_section`) and `:836` (`data-deadline`) — the priority-action
  card surfaces exactly one date, `item["deadline"]`, sourced from
  `_journey_trace_deadline` above; it has no field for "sale opens on" vs.
  "departs on".

### Replan events

- `plugins/china-trip-weaver/src/china_trip_weaver/replan.py:21`
  (`VALID_EVENT_TYPES = ("closure", "weather", "delay", "user_delete", "refresh")`).
- `plugins/china-trip-weaver/src/china_trip_weaver/replan.py:62-70` — `closure`/
  `weather` replace exactly one `days[].slots[]` entry with a caller-supplied
  `replacement_slot`; they never touch `transport_legs`, `lodgings`, or
  `budget_ledger`, so a ferry suspension handled this way still needs a
  follow-up hand patch to remove the ferry leg and its budget line — this is
  the "hand-patch after closure" workaround the leader's real itinerary
  already relies on.
- `plugins/china-trip-weaver/src/china_trip_weaver/replan.py:232` (`_apply_refresh`,
  added by ADR-0015) is the only event handler that atomically updates a
  transport leg, its health, and the budget ledger together — the template a
  future "ferry re-book" or "rental re-quote" event would follow, independent
  of whether the Trip schema itself changes.

### Tests likely to need touching

- `tests/test_contracts.py:69-70` (`test_versions_are_frozen`) — hard-asserts
  `SCHEMA_VERSION == "1.0.0"`; any additive schema field still needs this
  reviewed even if the project's existing convention (ADR-0007/0010/0012 all
  added optional fields without a version bump) means it need not change.
- `tests/test_contracts.py:81-84` (`test_accepted_examples_are_unchanged_in_test_fixtures`) —
  hard-asserts 2 valid / 4 invalid example fixtures; a new required-field
  combination worth covering would bump these counts.
- `tests/test_journey.py:1344`
  (`test_priority_actions_are_the_five_earliest_deadline_checklist_items`) —
  exercises the exact `deadline`-sort logic that `_journey_trace_deadline`
  would need to extend for a genuine booking/sale-open reminder.
- `tests/test_replan.py:59,221` (`run_replan_fixture`,
  `test_all_four_replan_fixtures_run_through_cli_and_render`) — the
  fixture-driven CLI loop ADR-0015 used as the template for `refresh`; a new
  replan event for ferry suspension or rental re-quote would extend this same
  loop, not replace it.
