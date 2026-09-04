# ADR-0010: Candidate-file planning with a live rail boundary

- **Status:** Accepted
- **Date:** 2026-09-03

## Context

The v0.1 executable path accepted only one hard-coded Beijing-to-Shanghai,
three-day, two-traveler scenario. Its railway probe did not parse the real
`12306-mcp@0.3.10` result shape, and local replanning was available only as a
library workflow. This prevented the accepted research → candidates → matrix →
schedule → validate → render design from operating on independent inputs.

The Trip schema is frozen. Research output and provider transport therefore
need an input boundary that reuses the accepted Trip entity definitions without
adding research-only fields to Trip itself.

## Decision

Add `schema/candidates.schema.json` beside the packaged Trip schema. A candidate
document contains exactly `candidates_version`, `pois`, `lodgings`, `claims`,
and `unknowns`; its entity definitions reference `trip.schema.json#/$defs/*`.
Transport legs are not accepted from the research file. `ctw plan` derives
cross-city routes from the normalized request and resolves them through one of
three explicit railway modes: `live`, `fixture:<file>`, or `off`.

The live railway mode uses a dependency-free, line-delimited JSON-RPC stdio
client to initialize the pinned MCP, verify its exact eight-tool fingerprint,
resolve representative station codes, and call `get-tickets`. The adapter
parses real MCP text arrays and records dated service, price, availability,
claims, and health. Empty, unavailable, and outside-presale results degrade to
a dated official 12306 deep link; they never become fabricated inventory.

AMap and FlyAI remain fixture-only in this increment. Without a configured map
provider, plan builds labeled conservative static route estimates. Local
replanning is exposed through `ctw replan` and continues to preserve unaffected
day canonical bytes.

## Consequences

- Independent 1–7 day request/candidate files can run through the same P0–P6
  pipeline; local-city requests make no railway business call.
- Research output is validated before any provider call, so a missing entity
  claim or invalid unknown path stops the run.
- Fixed regression dates can truthfully exercise outside-presale degradation,
  while the checked-in demo can use a date inside the live sale window.
- The Trip schema and its three accepted copies remain byte-identical. Future
  candidate fields require a candidate-schema version decision, not a silent
  Trip-schema change.
- The stdio client adds an ephemeral repository-local npm cache; `_npx`
  installation trees are removed after live verification so packaging remains
  free of `node_modules`.

## Evidence

- `docs/design/03-trip-model.md` and the frozen `schema/trip.schema.json` `$defs`.
- `docs/design/06-pipeline.md`, research → candidates → matrix → schedule →
  validate → render.
- `docs/design/04-providers.md`, railway pin/fingerprint and degradation ladder.
- Real `12306-mcp@0.3.10` recordings for representative stations, live ticket
  arrays, empty arrays, interline results, and outside-presale `isError` output.
- Deterministic E2E fixtures for Beijing–Shanghai (3 days), Shanghai local
  (2 days, zero railway calls), and Beijing–Hangzhou (4 days).
