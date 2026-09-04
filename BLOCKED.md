# Unresolved items

## Book 3: ordered multi-city planning

- Status: 无新增阻塞（no new blocker）。The implementation, compatibility, reverse-validation, demo, and schema gates all have an in-scope path to completion.

## Book 1: AMap place identity

- Status: 无新增阻塞（no new blocker）。POI identity, administrative consistency, business conflict preservation, semantic outliers, reverse validation, and synthetic fixtures all have in-scope implementations and passing tests.

## Book 2: live 12306 station candidates have no distance signal

- Status: blocked on 2026-09-04 for physical-distance ordering only; the remaining station fallback and error-classification work continues.
- Evidence: pinned `12306-mcp@0.3.10` implements `get-stations-code-in-city` as a list containing only `station_code` and `station_name`. The current rail `ProviderRequest` likewise carries names/refs/date but no station coordinates or candidate-to-endpoint distances.
- Constraint: `planning.py`, `mobility.py`, and AMap providers are explicitly owned by other books and may not be changed here. Querying every candidate for tickets would produce duration, not physical distance, and could still silently choose the wrong station.
- Safe delivery: return every candidate without selecting one; sort ascending when a synthetic/forward-compatible candidate supplies `distance_meters`, with unknown distances last and deterministic ties. Live candidates without a distance remain deterministic but are not claimed to be physically ranked.

No product-level item is open. Standing constraints are not listed here, because a list of unresolved items
should mean pending work. They live where they are enforced:

- Provider terms, attribution, caching, and the licences commercial use would
  require: `THIRD_PARTY_NOTICES.md`.
- Provider pins, deadlines, degradation, and FlyAI's optional status:
  `plugins/china-trip-weaver/references/provider-contracts.md`.
- Architecture decisions, including why this plugin is not listed on a public
  marketplace: `docs/design/adr/`.

## Lodging and flight inventory have a single upstream source (closed)

- Status: closed on 2026-09-04, superseded by the tested independent fallbacks
  recorded under Book 4 above. Kept here for provenance; the facts below
  describe the situation before those fallbacks existed.
- Fact: `@fly-ai/flyai-cli` is the only source for both lodging and flight
  inventory. It is an unofficial third-party wrapper published by an individual
  maintainer, it last shipped on 2026-04-21, and its command surface already
  drifted once between releases. If it is abandoned or changes shape, both
  capabilities disappear together.
- Contained, not solved: `--lodging` defaults to `off`, a probe mismatch fails
  closed, and tests assert that a failing FlyAI still yields a schema-valid
  Trip, reports its own health, invents no flight candidate, and leaves lodging
  to the candidate file. The plugin degrades; it does not break.
- Two candidate second sources are already wired into this repository, which
  makes this smaller than it looks:
  - Flights: the VariFlight adapter already calls `searchFlightsByDepArr`,
    which returns dated schedules for a city pair. Today it only enriches
    FlyAI legs with status and comfort. Promoting it to an independent source
    would give schedules and flight identity without prices.
  - Lodging: the AMap adapter already has a `poi` capability. An accommodation
    category search would give candidate properties with verified coordinates,
    again without prices or availability.
- What either would not give: a price. Both fallbacks would have to publish
  `verify-on-click` rather than a number, which the price contract already
  supports.
- Impact if left as is: a FlyAI outage costs lodging and flight inventory for
  the duration. Nothing else regresses.

## What was closed, and when

- 2026-09-04, same-name Skill detection. Codex shipped
  `codex plugin list --json`, so `ctw doctor` now reads it, walks each enabled
  plugin's `skills/` directory, and reports `skill_conflicts`, exiting non-zero
  on a collision. Verified against a real installation of the older
  `china-travel-assistant`, which does expose `plan-china-trip`.
- 2026-09-04, sample-data redistribution. `demo/` and
  `tests/fixtures/providers/` hold only locally generated synthetic values, and
  a regression test scans every Git-tracked file for the retired markers.
- 2026-09-04, provider terms. AMap and VariFlight were reviewed clause by
  clause. Caching is forbidden and no provider response is cached; attribution
  is required and the rendered footer names every contributing provider;
  commercial use needs licences this project does not hold, which the readme
  and notices state plainly.
- 2026-09-04, public marketplace listing. Decided against in
  [ADR-0013](docs/design/adr/0013-stay-off-the-public-marketplace.md).
- 2026-09-04, FlyAI wrapper terms. Its data is treated under the same
  no-cache, no-redistribution rule, and the wrapper itself is now documented and
  tested as an optional, best-effort source.

## Book 5 — public-distribution legal links remain open

- `interface.websiteURL` now points to the real GitHub repository. No
  `privacyPolicyURL` or `termsOfServiceURL` was invented: ADR-0013 keeps this
  plugin off the public marketplace and the project has no real policy pages.
- Before any future public distribution, publish reviewed privacy and terms
  pages, add their real HTTPS URLs to the manifest, and rerun plugin ingestion
  validation. Until then, local/repository distribution is the supported scope.

## Book 5 — required manifest field conflicted with a forbidden exact-fixture test (resolved)

- Status: resolved on 2026-09-04. The task brief required `interface.websiteURL`
  while placing `tests/test_packaging.py` off limits, and that test pins the
  former eight-key `interface` object exactly. The conflict was in the brief,
  not in the implementation.
- Book 5 responded correctly: it relaxed no assertion, edited no forbidden test,
  withdrew no required field, reproduced the deterministic failure twice, and
  recorded the conflict instead of working around it.
- Resolution: `EXPECTED_MANIFEST` now carries the real GitHub `websiteURL`, so
  the assertion stays an exact equality rather than a loosened one. Verified by
  reverse test — pointing the manifest at a different URL fails that test, and
  restoring it passes. Full discovery is `Ran 324 tests ... OK`, skipped 0.

## Book 4 — single lodging/flight upstream closed

- Status: closed on 2026-09-04. The earlier “Lodging and flight inventory have
  a single upstream source” item is superseded by tested independent fallbacks.
- With FlyAI forced to timeout on every call, configured VariFlight
  `searchFlightsByDepArr` returned two dated schedule candidates and configured
  AMap POI returned one accommodation-category candidate. Every fallback price
  was `amount=null` and `price_type=verify-on-click`; FlyAI health remained
  visibly `degraded` with `errors=timeout`.
- No new Book 4 blocker remains. The unrelated Book 5 manifest/test conflict is
  outside Book 4 scope and remains untouched.
