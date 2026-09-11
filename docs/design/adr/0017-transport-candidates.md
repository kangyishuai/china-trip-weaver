# ADR-0017: Where rental-car and ferry legs come from

- **Status:** Proposed
- **Date:** 2026-09-11

## Context

ADR-0016 proved `trip.schema.json` already accepts a hand-written rental-car
(`drive`) leg and a `ferry` leg with **zero** schema change
(`tests/fixtures/trips/schema/valid/rental-ferry.json` is `VALID` against the
unmodified schema, and its rendered HTML is `HTML VALID ... errors=0`), and
it shipped the two things that were actually broken for such a leg: the
booking-deadline read (`journey.py:1984`, below) and the `suspend` replan
event (`replan.py:401`, below), both pure code, no schema change. What
ADR-0016 deliberately left open, in its own closing sentence, is: *"If a real
rental-car or ferry-ticket producer is ever built ... that book is the right
place to add fields the new producer actually populates and a new consumer
actually reads — not before."* This ADR is that book, but only the design
half: does such a producer exist anywhere today, where would a user or Skill
declare intent, and which function would turn that declaration into a
`transportLeg`. No code, schema, or test file is changed by this ADR.

### The pipeline a rail leg already goes through (reproducible today)

`rail` is the only travel mode with a real, live producer. Its pipeline is
the working precedent Options A and B are measured against below.

- 声明 (declare): `request.assumptions` is free text
  (`trip.schema.json:474`, `$ref: stringList`); `planning.py:683-692`
  already scans it (plus `constraints`/`pasted_notes`) for `"单程"`/`"往返"`
  to toggle a return leg — the only place free text already steers transport
  shape, and it only flips a boolean; it never creates a `drive`/`ferry`
  route.
- 路线 (route spec): `planning.py:647` `_route_specs` turns
  `request.destinations`/`origin`/dates into `RouteSpec` tuples with **no**
  `travel_mode` field; the same tuple set feeds both producers below.
- 生产 (produce): `planning.py:1328` `_resolve_rail` queries the live 12306
  backend per route, falling back to `planning.py:1588` `_deep_link_leg` (a
  static 12306-search deep link, `status="hypothesis"`/`"unknown"` claims)
  when there is no live match; `providers/flyai.py:61` `_flight` is the sole
  flight producer, dispatched from `:23` `normalize` by `request.capability`.
- 归一化 (normalize): `planning.py:634` `_normalize_candidates` calls
  `candidates.py:160` `validate_candidates` before any producer runs.
- 日程 (schedule): `planning.py:2454` `_schedule_problems` feeds
  `scheduler/light.py`'s `LightScheduler`, which has no cross-city
  `travel_mode` special case (only intra-day `"walk"` pacing does, at
  `scheduler/light.py:497,511`) — `drive`/`ferry` legs already schedule
  exactly like `rail`.
- 账本 (ledger): `planning.py:2060` `_budget_ledger` calls `planning.py:1878`
  `_cost_range`, generic over `budgetItem.category="transport"`; a leg whose
  `price.amount` is `null`/`price_type` is `"verify-on-click"` (exactly what
  the rental-ferry fixture uses) becomes an `unknowns` entry automatically —
  no per-mode code exists or is needed.
- 健康行 (health): `planning.py:2663` `_provider_health` is a fixed 6-entry
  list; its `:2673` entry, `_health("host-web", "candidate-file", "static",
  "ready", ...)`, is the generic probe pois/lodgings already reuse for
  anything sourced from a file rather than a live API.
- 渲染 (render): `render/html.py:57-59` already maps `"drive"→"驾车"`,
  `"ferry"→"轮渡"` in its `travel_mode` label dictionary.
- 校验 (validate): `validate_trip.py:318` `semantic_issues`'s
  origin-required check only trips on `travel_mode in ("rail","flight")`;
  `render/validate_journey_html.py:179` `_check_transport_overview_coverage`
  counts `trip["transport_legs"]` generically, with no per-mode branch.
- replan: `replan.py:21`'s `VALID_EVENT_TYPES` lists `suspend`; `:401`
  `_apply_suspend` requires "a transport leg" but never checks its
  `travel_mode`.
- 清单 deadline: `journey.py:1984` `_journey_transport_leg_deadline` prefers
  a `/booking_deadline`-shaped claim, else falls back per `travel_mode`.

### candidates.json's own shape (what Option B would touch)

- `candidates.schema.json` top level: `required = ["candidates_version",
  "pois", "lodgings", "claims", "unknowns"]`, `additionalProperties: false`
  — a `transport` array is not legal today.
- `candidates.py:175` hardcodes entity-id scanning as `for group, id_key in
  (("pois","poi_id"),("lodgings","lodging_id")):` inside `validate_candidates`.
- `candidates.py:827` `initialize_candidates` writes the same 5-key skeleton
  literally.
- `candidates.py:1207` `_import_item_kind` accepts only `kind in ("poi",
  "lodging")`; `:1227` `import_candidates` dispatches on it.
- `candidates.py:1269` `_editable_candidates` rejects anything but an exact
  key-set match (`set(value) != EXPECTED_DOCUMENT_KEYS`) — a `transport` key
  would need `EXPECTED_DOCUMENT_KEYS` to grow too, or every existing
  `ctw candidates add-*`/`import` call on a file that already has one would
  start raising "not a v1 five-key skeleton".
- `tests/test_contracts.py:68` `test_versions_are_frozen` pins
  `SCHEMA_VERSION == "1.0.0"` — this covers `trip.schema.json`, the file
  both `request` and `transportLeg` live in as `$defs`; nothing pins
  `CANDIDATES_VERSION` by name anywhere in `tests/`.
  `tests/test_providers.py:117` separately pins `fixture_count == 79`.
- `grep -rl candidates_version tests/` → 11 test files; the same search
  under `tests/fixtures/` → 8 fixtures — the rough blast radius any
  structural change to the candidates document shape would need auditing
  against, per this project's own prior experience (`BLOCKED.md`'s "AnySearch
  真实合同" and "`ctw research` 命令" books, both cited in ADR-0016, each
  rippled into a test file its task's file allowlist had not anticipated).

Neither `providers/` adapter list (`amap`, `anysearch`, `flyai`, `host_web`,
`rail12306`, `variflight`) nor the two Skills cover this: the research Skill
(`skills/research-china-destination/SKILL.md:21`) explicitly says "Do not
add `transport_legs`" and its document shape is still the five-key
`pois`/`lodgings`/`claims`/`unknowns` skeleton; `grep -c "rental\|ferry\|租车\|轮渡"
plugins/china-trip-weaver/skills/plan-china-trip/SKILL.md` is 0.

## Options

### Option A — declare on `request`

A new, optional `request.transport_plan` array. This requires a new
`$defs/transportPlanItem` in `trip.schema.json` and therefore a
`SCHEMA_VERSION` bump — a deliberate version bump, not a workaround, since
`tests/test_contracts.py:68` exists specifically to make that kind of change
intentional rather than casual.

```json
{
  "transport_plan": [
    {"kind": "rental_car", "pickup": {"ref_id": "city-fuzhou", "at": "2026-09-26T09:00:00+08:00"}, "dropoff": {"ref_id": "city-quanzhou", "at": "2026-09-28T18:00:00+08:00"}, "one_way_fee_cny": 200, "min_rental_hours": 72, "booking_url": "https://example-car-rental.invalid/rates"},
    {"kind": "ferry", "from_ref": "poi-xiamen-ferry-terminal", "to_ref": "poi-gulangyu", "depart_at": "2026-09-27T10:30:00+08:00", "booking_url": "https://gulangyu-ferry.example.invalid/schedule"}
  ]
}
```

- **生产者:** a new `_resolve_transport_plan(normalized_request, clock)`,
  called beside `_resolve_rail` in `_plan_resolve_candidates`
  (`planning.py:181`), reading `normalized_request["transport_plan"]`
  directly — no `RouteSpec`, no candidates.json involvement — and emitting
  one `transportLeg` plus one claim pair per item, mirroring
  `_deep_link_leg`'s `status="hypothesis"`/`"unknown"` shape when
  `booking_url` is the only evidence available.
- **租期规则/异地还车费 → 账本:** `one_way_fee_cny`/`min_rental_hours` are
  producer-only inputs, folded into one `budgetItem`
  (`category="transport"`, `amount_min_cny == amount_max_cny` = base + fee
  when both are known, `reason="含异地还车费 ¥200，最短起租 72 小时"`).
  Nothing new is validated structurally — this matches ADR-0016's own
  finding that no code anywhere enforces a minimum-rental-hours rule today;
  Option A gives the rule a named field instead of prose, it does not make
  the rule machine-enforced.
- **预订截止 → 清单:** the producer attaches a `/booking_deadline`-shaped
  claim when the item declares one; `_journey_transport_leg_deadline`
  (`journey.py:1984`) already prefers that claim over `depart_at` — this
  consumer is already built, by ADR-0016.
- **停航 → suspend:** unaffected. Once the leg is a normal `transportLeg`,
  `replan.py:401` `_apply_suspend` already handles it exactly like a
  hand-written leg — another consumer ADR-0016 already built.

### Option B — declare in candidates.json

A new, optional `transport` array beside `pois`/`lodgings`.

```json
{
  "transport": [
    {"transport_id": "transport-ferry-gulangyu", "kind": "ferry", "from_ref": "poi-xiamen-ferry-terminal", "to_ref": "poi-gulangyu", "depart_at": "2026-09-27T10:30:00+08:00", "claim_ids": ["claim-ferry-schedule"]}
  ],
  "claims": [
    {"claim_id": "claim-ferry-schedule", "subject_ref": "transport-ferry-gulangyu", "field_path": "/depart_at", "source_url": "https://gulangyu-ferry.example.invalid/schedule", "provider": "gulangyu-ferry.example.invalid", "status": "hypothesis", "confidence": 0.3, "mode": "static", "queried_at": "2026-09-11T08:00:00+08:00", "as_of": null, "raw_ref": null, "response_hash": null, "json_path": null, "value": "班次与票价以现场为准"}
  ]
}
```

(claim shape copied field-for-field from the already-shipped
`claim-ferry-schedule` entry in `tests/fixtures/trips/schema/valid/rental-ferry.json`.)

- **生产者:** a new `_resolve_transport_candidates(normalized_candidates,
  clock)`, called beside `_resolve_rail` in `_plan_resolve_candidates`
  (`planning.py:181`), turning each `transport` candidate straight into a
  `transportLeg` 1:1 — no live-query/fallback split like `_resolve_rail` has,
  because there is no rental-car or ferry API in `providers/` to query in
  the first place (unlike `rail12306`/`flyai`).
- **租期规则/异地还车费、预订截止、停航:** identical mechanics to Option A
  (same `budgetItem.reason`, same `/booking_deadline` claim convention, same
  `_apply_suspend`) — the only difference from A is *where* the raw
  declaration lives and what schema/tests it touches.
- **Schema/test cost specific to B:** the new `transport` property is
  additive and optional (not added to `required`), so `candidates.schema.json`'s
  `additionalProperties: false` and the 8 existing fixtures under
  `tests/fixtures/` stay valid untouched; `tests/test_contracts.py:68` is
  untouched too, because it only freezes `SCHEMA_VERSION` (the Trip schema),
  never `CANDIDATES_VERSION`. What *does* need to change: `candidates.py:175`'s
  entity-group tuple, `:827`'s skeleton dict, `:1207`'s `kind` check, and
  `:1269`'s exact-key-set gate (the concrete gotcha found above) all grow a
  third branch. Net surface is strictly smaller than A's, because A's field
  lives inside the file `SCHEMA_VERSION` guards and B's does not.

## Decision

**暂不做 (status quo continues).** Evidence:

1. The status quo already works end to end with zero producer: per this
   book's own brief, the leader's real itinerary already declares
   rental-car rules as prose in `request.assumptions` and hand-edits the
   Trip; reschedules go through a `closure` event plus a manual patch. That
   is not a workaround — `request.assumptions` (`trip.schema.json:474`) is
   exactly the free-text field the schema already offers for this.
2. ADR-0016 already shipped the only two things that were actually broken
   for a hand-written `drive`/`ferry` leg (booking-deadline read, suspend
   handling), both pure code, zero schema change, proven live by
   `tests/fixtures/trips/schema/valid/rental-ferry.json` passing
   `validate`/`validate-html` unmodified.
3. Neither A nor B is a producer in the sense `_resolve_rail`/`_flight` are
   producers: `providers/` ships six adapters today (`amap`, `anysearch`,
   `flyai`, `host_web`, `rail12306`, `variflight`) and none talks to a
   rental-car or ferry API. What A and B each mechanize is a copy from a
   human-typed declaration into a `transportLeg` — marginally less typing
   than hand-writing the leg into the Trip directly, at the cost of a new
   schema surface, a new planning function, and (for A specifically) a
   `SCHEMA_VERSION` bump through a test built to make that deliberate.
4. Blast radius is measurable, not hypothetical: `grep -rl
   candidates_version tests/` → 11 files, the same search under
   `tests/fixtures/` → 8 fixtures, would need auditing even for B's
   additive, optional field — matching this project's own two prior
   fixture/contract-shape books that each rippled into an unplanned test
   file (cited in ADR-0016).
5. Volume: this repository has exactly one real trip that has ever needed a
   rental-car or ferry leg, and the status quo already serves it fully
   (ADR-0016 commands 2-3, done 2026-09-11).

If a second real trip needs a rental-car/ferry leg the **scheduler** must
route around automatically — not merely validate and render, which the
status quo already does — **Option B is the design to build, not Option
A.** B costs strictly less (`SCHEMA_VERSION`'s freeze is never touched;
only `candidates.py`'s four hardcoded spots above grow a third branch), and
it places the declaration at the same pipeline stage (research/candidate
curation, evidence-backed via `claim_ids`) as a `poi`/`lodging` candidate,
rather than on `request`, which is filled in before research and carries no
evidence requirement at all.

## Consequences

Draft acceptance commands for the execution book that would implement
Option B, if greenlit later. None of these should pass yet — they describe
the target, not today's state:

1. `git diff main --stat -- plugins/china-trip-weaver/schema/trip.schema.json`
   → empty (Option B never touches the Trip schema; only
   `candidates.schema.json` grows a new optional property).
2. `/usr/bin/python3 -m unittest tests.test_contracts -k test_versions_are_frozen -v`
   → still passes unmodified (`SCHEMA_VERSION` untouched by an additive,
   optional `candidates.schema.json` field).
3. `ctw candidates add-transport <file>.json --kind ferry --from <ref> --to <ref> --depart-at <iso>`
   (new subcommand, mirrors `add_poi_candidate`) → appends one valid
   `transport` candidate; `validate_candidates` stays `OK` on all 8 existing
   fixtures under `tests/fixtures/`, untouched.
4. `ctw plan --candidates <fixture-with-transport>.json ...` → the new
   `_resolve_transport_candidates` produces a `transportLeg` with
   `travel_mode` in `{"drive","ferry"}`, and `_budget_ledger` places it as a
   known `transport` line or an `unknowns` entry per `_cost_range`'s
   existing generic rule — no new ledger code.
5. `/usr/bin/python3 -m unittest tests.test_journey -k booking_checklist -v`
   → a transport-candidate-sourced leg carrying a `/booking_deadline` claim
   produces the same checklist item shape ADR-0016 already built for rail.
6. `/usr/bin/python3 -m unittest discover -s tests` → `OK`, same skip count
   as this book's baseline (regression gate).
