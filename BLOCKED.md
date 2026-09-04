# Unresolved items

One open item, parked deliberately. Standing constraints are not listed here, because a list of unresolved items
should mean pending work. They live where they are enforced:

- Provider terms, attribution, caching, and the licences commercial use would
  require: `THIRD_PARTY_NOTICES.md`.
- Provider pins, deadlines, degradation, and FlyAI's optional status:
  `plugins/china-trip-weaver/references/provider-contracts.md`.
- Architecture decisions, including why this plugin is not listed on a public
  marketplace: `docs/design/adr/`.

## Lodging and flight inventory have a single upstream source

- Status: parked on 2026-09-04. Known, accepted, not scheduled.
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
