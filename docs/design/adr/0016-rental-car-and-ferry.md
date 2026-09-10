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
- `plugins/china-trip-weaver/src/china_trip_weaver/journey.py:1769-1790`
  (`journey_booking_checklist`) — every transport leg unconditionally gets a
  checklist item whose `"deadline"` is `leg.get("depart_at")`; there is no
  concept of a booking/sale-open date that precedes departure, for any
  `travel_mode` including the `rail` legs that already exist today. This is
  the one place a useful rental/ferry reminder needs new logic regardless of
  schema choice.

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
  card surfaces exactly one date, `item["deadline"]`, computed by
  `journey_booking_checklist` (journey.py:1769) above; it has no field for
  "sale opens on" vs. "departs on".

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
  `SCHEMA_VERSION == "1.0.0"`; `git log -p --follow -- .../__init__.py` shows
  `SCHEMA_VERSION` has been `"1.0.0"` in every one of the 12 release commits
  from `0.2.0` through `0.11.0`, so a schema edit does not strictly force this
  line to change, but it is the one place that convention is asserted and
  would need re-confirming.
- `tests/test_contracts.py:81-84` (`test_accepted_examples_are_unchanged_in_test_fixtures`) —
  hard-asserts 2 valid / 4 invalid example fixtures; a new required-field
  combination worth covering would bump these counts.
- `tests/test_journey.py:1344`
  (`test_priority_actions_are_the_five_earliest_deadline_checklist_items`) —
  exercises the exact `deadline`-sort order that `journey_booking_checklist`
  (journey.py:1769) would need to change for a genuine booking/sale-open
  reminder.
- `tests/test_replan.py:59,221` (`run_replan_fixture`,
  `test_all_four_replan_fixtures_run_through_cli_and_render`) — the
  fixture-driven CLI loop ADR-0015 used as the template for `refresh`; a new
  replan event for ferry suspension or rental re-quote would extend this same
  loop, not replace it.

All JSON below is synthetic: public city and station names are real, every
provider slug, order id, price, and URL is invented for illustration and
resolves to nothing.

## Options

Both options are graded against the same four requirements: (1) pickup/return
time and place, (2) rental-period rules — minimum-rental-days, one-way
drop-off, (3) cost and a booking deadline that actually feeds
`budget_ledger`/priority-actions, (4) a replan path for a suspended ferry or a
changed rental term.

### Option A — no schema change; express with existing `slots` + `claims` + `request.assumptions`

**1. Pickup/return time and place.** A `drive` leg already carries everything:
place refs (which may be POIs created for the rental counters), a start/end
timestamp pair, and an official link.

```json
{
  "leg_id": "leg-rental-fz-qz-01",
  "travel_mode": "drive",
  "from_ref": "poi-fuzhou-airport-rental-counter",
  "to_ref": "poi-quanzhou-rental-return-counter",
  "depart_at": "2026-10-01T10:00:00+08:00",
  "arrive_at": "2026-10-05T10:00:00+08:00",
  "duration_minutes": 5760,
  "provider": "demo-car-rental",
  "booking_url": "https://demo-car-rental.invalid/orders/demo123",
  "claim_ids": []
}
```

**2. Rental-period rules.** The rule itself (a National Day 96-hour minimum,
a one-way drop-off) is not structured data anywhere; it lives as a note in
`request.assumptions`, and its only structural trace is that whoever authors
the leg above made `arrive_at - depart_at` honor it. Nothing re-checks this.

```json
{
  "assumptions": [
    "国庆期间租车公司通常最低起租 96 小时（4 天），本行程按此固定取还车时间，规则本身不进 schema",
    "福州取车、泉州还车属异地还车，产生的异地还车费单独计入 budget_ledger 的一条 transport 项"
  ]
}
```

**3. Cost and booking deadline.** The base rental fee and the one-way fee are
two ordinary `budgetItem`s under `category: "transport"`, both referencing the
leg. A useful *booking* deadline (distinct from `depart_at`) has no field to
live in today, so Option A represents it as a claim with a conventional
`field_path`; `journey_booking_checklist` (journey.py:1769) would need a small
code change to prefer such a claim over `leg.get("depart_at")` when present —
a code change, not a schema change.

```json
[
  {"ref_id": "leg-rental-fz-qz-01", "category": "transport", "price_type": "estimate",
   "amount_min_cny": 1100, "amount_max_cny": 1450, "basis": "4-day compact car, synthetic quote",
   "included_in_scheduler": true, "reason": null},
  {"ref_id": "leg-rental-fz-qz-01", "category": "transport", "price_type": "reference",
   "amount_min_cny": 200, "amount_max_cny": 200, "basis": "one-way drop-off fee",
   "included_in_scheduler": true, "reason": "异地还车费，福州取泉州还"}
]
```

```json
{
  "claim_id": "claim-ferry-booking-deadline-01",
  "subject_ref": "leg-ferry-gulangyu-01",
  "field_path": "/booking_deadline",
  "value": "2026-09-21",
  "source_url": "https://www.xmferry.com/",
  "provider": "manual",
  "status": "hypothesis",
  "mode": "static"
}
```

**4. Replan path.** Today's only route is a `closure` event that swaps the
`slot`, leaving `transport_legs`/`budget_ledger` for a human to patch by hand
— the exact workflow the leader's real itinerary already relies on
(replan.py:62-70).

```json
{
  "type": "closure",
  "subject_ref": "slot-day3-ferry-gulangyu",
  "reason": "台风预警，鼓浪屿航线临时停航",
  "replacement_slot": {
    "slot_id": "slot-day3-ferry-gulangyu",
    "start_at": "2026-10-03T09:00:00+08:00",
    "end_at": "2026-10-03T12:00:00+08:00",
    "kind": "free",
    "ref_id": null,
    "title": "轮渡停航，本岛替代方案待定",
    "locked": false,
    "status": "tentative"
  }
}
```

### Option B — add structured fields for rental cars and ferries

Dimensions 1 and 4 are unchanged from Option A: place/time already fit in the
existing leg shape, and a suspension still needs a new `_apply_XXX` replan
handler (schema-independent) rather than a new field. Dimensions 2 and 3 are
where B would add fields:

**2. Rental-period rules**, as fields on the leg instead of prose:

```json
{
  "leg_id": "leg-rental-fz-qz-01",
  "travel_mode": "drive",
  "rental_min_hours": 96,
  "one_way_fee_cny": 200,
  "one_way_fee_reason": "福州取车、泉州还车"
}
```

**3. Booking deadline**, as a field on the leg instead of a claim convention:

```json
{
  "leg_id": "leg-ferry-gulangyu-01",
  "travel_mode": "ferry",
  "booking_deadline": "2026-09-21T00:00:00+08:00"
}
```

## Decision

**Option A.** Evidence, dimension by dimension:

- **Pickup/return.** `transportLeg` (schema/trip.schema.json:550-576) already
  has every field the example above uses; `travel_mode` already lists `drive`
  and `ferry` (schema/trip.schema.json:553). Zero schema change either way —
  this dimension does not even distinguish A from B.
- **Rental-period rules.** No code anywhere validates a minimum-rental-hours
  or a one-way-fee rule today (there is no producer for such a leg at all —
  `mobility.py:124`'s `drive` alias computes a point-to-point AMap route, not
  a multi-day rental). A schema field with nothing reading or enforcing it is
  inert; `request.assumptions` (schema/trip.schema.json:473-474) already
  carries planning-time rules like this in the shipped `demo/request.json`.
- **Cost.** `budgetItem.category` already includes `transport`
  (schema/trip.schema.json:248), and its `reason` field already exists to
  explain an itemized add-on fee. Nothing sums or reasons over `one_way_fee_cny`
  differently than it would over a second `transport` budget item — the
  saving from Option B here is a queryable number, not a new capability.
- **Booking deadline.** This is the one dimension with a real gap, but the
  gap is in `journey_booking_checklist` (journey.py:1769-1790), which reads
  `leg.get("depart_at")` unconditionally for *every* `travel_mode` — including
  the `rail` legs that exist in production today. `providers/rail12306.py:28`
  defines `PRESALE_DAYS = 15`, and line 124 produces
  `"no_results: requested date is outside the 12306 %d-day presale window"`
  when a rail query falls outside it: rail tickets already have a real
  "cannot book before this date" boundary the codebase knows about, and
  `journey_booking_checklist` ignores it just as completely as it would
  ignore a ferry sale-open date. Fixing this is worth doing regardless of
  Option A/B, and a schema field does not remove the need to change
  `journey_booking_checklist` — it only changes what that function reads
  (`leg["booking_deadline"]` instead of a claim by convention). Option A pays
  for the fix once, in code, and it also improves rail.
- **Replan path.** `replan.py:62-70` shows `closure`/`weather` already only
  touch `days[].slots[]`; ADR-0015's `_apply_refresh` (replan.py:232) is the
  precedent for a handler that also updates `transport_legs` and
  `budget_ledger`. That precedent is pure Python; nothing about it depends on
  whether `trip.schema.json` grows new fields.

This project's own history is further evidence against B: `BLOCKED.md`
records two recent fixture/contract-shape changes (the "AnySearch 真实合同"
book and the "`ctw research` 命令" book, both 2026-09-10) each rippling into
test files that were not on either task's allowed-file list —
`tests/fixtures/providers/manifest.json` (a shared, auto-generated manifest
whose diff footprint the task's own exclusion pattern did not anticipate) and
`tests/test_providers.py`'s hardcoded `fixture_count` assertion (`76` →
`78`), plus a hardcoded string match in `tests/test_skills.py`. Neither
change added a schema field — they only changed fixture *shape* — and still
cost each book an unplanned detour. A `trip.schema.json` field change is a
strictly bigger surface than a fixture change. Adding fields nothing yet
reads would pay a similar or larger cost for no working feature. If a real
rental-car or ferry-ticket producer is ever built (the `_deep_link_leg`-style
function that does not exist today), *that* book is the right place to add
fields the new producer actually populates and a new consumer actually reads
— not before.

## Consequences

Draft acceptance commands for the execution book that implements the
`journey_booking_checklist` fix and a suspension-aware replan event (both
pure code, no schema edits):

1. `git diff main --stat -- plugins/china-trip-weaver/schema` → empty (confirms
   the "no schema change" commitment held).
2. `ctw validate .tmp/synthetic-rental-ferry-trip.json` → `VALID` for a
   hand-authored Trip containing one `drive` rental leg and one `ferry` leg,
   against the *unmodified* schema.
3. `ctw validate-html .tmp/synthetic-rental-ferry-trip.html .tmp/synthetic-rental-ferry-trip.json`
   → `HTML VALID ... errors=0` (proves the existing generic transport card
   needs no new render branch).
4. `/usr/bin/python3 -m unittest tests.test_journey -k booking_checklist -v` →
   a new test asserting a leg with a `/booking_deadline`-shaped claim produces
   a checklist item whose `deadline` is the claim's value, not `depart_at`.
5. `/usr/bin/python3 -m unittest tests.test_replan -v` → a new fixture (e.g.
   `ferry_suspension.json`) exercised through a new `_apply_XXX` handler that
   removes the suspended leg and its `budget_ledger` item together, mirroring
   `_apply_refresh`'s all-or-nothing pattern.
6. `/usr/bin/python3 -m unittest discover -s tests` → `OK` with the same
   skip count as this book's baseline (regression gate).
