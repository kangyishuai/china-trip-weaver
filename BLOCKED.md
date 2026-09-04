# Unresolved items

None. Every item that stood here has been closed.

Standing constraints are not listed here, because a list of unresolved items
should mean pending work. They live where they are enforced:

- Provider terms, attribution, caching, and the licences commercial use would
  require: `THIRD_PARTY_NOTICES.md`.
- Provider pins, deadlines, degradation, and FlyAI's optional status:
  `plugins/china-trip-weaver/references/provider-contracts.md`.
- Architecture decisions, including why this plugin is not listed on a public
  marketplace: `docs/design/adr/`.

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
