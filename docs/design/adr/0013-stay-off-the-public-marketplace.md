# ADR-0013: Stay off the public marketplace and treat FlyAI as optional

- **Status:** Accepted
- **Date:** 2026-09-04

## Context

Three items sat unresolved after publication: whether to list the plugin on a
public Codex marketplace, what commercial use would require, and the fact that
no terms page governing the pinned FlyAI wrapper could be located.

Two of them turned out not to need new work. Reviewing the provider terms
established what commercial use costs, and that answer is a standing constraint
recorded in `THIRD_PARTY_NOTICES.md` rather than a pending decision. The FlyAI
terms gap is already covered by treating its data under the same no-cache,
no-redistribution rule as every other provider.

The marketplace question is a real decision, and the wrapper's health is a real
engineering risk. `@fly-ai/flyai-cli` is published by an individual maintainer,
its command surface drifted between releases during development, and it is the
only source for both lodging and flight inventory.

## Decision

This plugin is not listed on a public Codex marketplace. It is distributed as
source and installed from a local marketplace pointed at a clone.

Two reasons. Every user must first obtain their own AMap, FlyAI, and VariFlight
credentials, and AMap requires personal verification before granting any Web
service quota, so a marketplace listing would promise an installability the
plugin cannot deliver. Separately, AMap's terms section 3.2.2 treats a product
that is not operated by its own developer as a commercial purpose requiring a
purchased licence from both the developer and the operator; distributing the
plugin for others to run is difficult to keep outside that reading.

FlyAI is documented and tested as an optional, best-effort source. `--lodging`
defaults to `off`, a probe mismatch fails closed, and a failure degrades only
lodging and flight inventory. No long-term availability is promised.

## Consequences

- Distribution stays on GitHub, which already reaches the intended audience.
- Anyone wanting a marketplace listing must own the privacy and terms URLs and
  the provider licences themselves, and should record that in a new ADR.
- Losing FlyAI costs two capabilities, not the product. Adding a second
  lodging or flight source would remove the last single point of failure in the
  provider portfolio. That work is parked rather than scheduled, and
  `BLOCKED.md` records the two candidate sources already wired into this
  repository.
- `BLOCKED.md` now records no unresolved items. Standing constraints live in
  `THIRD_PARTY_NOTICES.md`, not in a list that implies pending work.

## Evidence

- `THIRD_PARTY_NOTICES.md` for the cited AMap and VariFlight clauses
- `plugins/china-trip-weaver/references/provider-contracts.md`
- `tests/test_flyai_live.py`, class `FlyAIIsAnOptionalSourceTests`
