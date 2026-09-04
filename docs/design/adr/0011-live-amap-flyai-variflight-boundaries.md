# ADR-0011: Live AMap, FlyAI, and VariFlight boundaries

- **Status:** Accepted
- **Date:** 2026-09-03

## Context

ADR-0010 made candidate-file planning and real 12306 rail executable, but the
route matrix remained static and AMap, FlyAI, and VariFlight stopped at replay
adapters. The accepted design requires truthful real route durations before
scheduling, dated lodging/flight comparisons, optional aviation enrichment,
and provider-specific degradation without exposing credentials or changing the
frozen Trip schema.

The live probes also established provider contracts that differ from earlier
fixtures: AMap spans v3/v4/v5 envelopes; FlyAI uses numeric top-level status,
masked or exact CNY strings, and undeclared hotel coordinate CRS; VariFlight
returns arbitrary JSON text through a nine-tool MCP and optional fields can be
heterogeneous.

## Decision

Use a standard-library HTTPS transport for AMap. Pin the official v3 geocode,
walking, transit, and driving endpoints, v4 bicycling, and v5 POI pagination.
AMap coordinates are native GCJ-02 with a single versioned WGS-84 derivation.
Each plan has a hard 80-call ceiling and request starts are spaced to at most
2 QPS. Only successful route API responses become live matrix cells;
Haversine remains a labeled static fallback.

Run `@fly-ai/flyai-cli@1.0.16` through constant argv and a provider-only
environment. Verify root and subcommand help before business calls. Masked
prices remain amount `null` and `verify-on-click`; exact CNY values can be
`live`. FlyAI hotel coordinates remain `provider-unknown`, with no conversion
or map placement. Flight results are comparison legs and are not scheduled in
addition to the selected rail legs.

Use `@variflight-ai/variflight-mcp@1.0.3` only as optional enrichment. Every
business session verifies the exact nine-tool fingerprint. With no key, only
initialize and `tools/list` are allowed. With a key, match
`searchFlightsByDepArr` results to existing FlyAI leg IDs and attach bounded
status claims; query `flightHappinessIndex` for one matched candidate per
direction and attach bounded comfort claims. Do not duplicate flight legs or
persist unbounded raw payloads.

All Node providers use repository-local npm/temp/config/cache paths and a
provider-only preload that redirects `os.homedir()` without changing `HOME`.
Credentials come only from the strict resolver and `provider_environment`;
they never enter argv, logs, fixtures, Trip, HTML, or Git. The Trip schema stays
byte-identical.

## Consequences

- `ctw mobility`, `ctw lodging`, and `ctw air` expose read-only provider
  diagnostics; `ctw plan --mobility live --lodging live` runs the integrated
  path and automatically enriches flights when VariFlight is configured.
- A provider may be ready with no results. This is distinct from missing,
  forbidden, rate-limited, or contract-mismatch health.
- A one-day trip makes no hotel inventory call. A short-haul market may have no
  flight candidates without invalidating live rail and ground mobility.
- Provider response changes fail closed at their capability boundary. Other
  providers and explicit fallbacks remain usable.
- Live results are non-deterministic facts with timestamps; fixture projections
  remain redacted and deterministic for regression tests.

## Evidence

- Redacted live AMap v3/v4/v5, FlyAI keyless/configured, and VariFlight
  search/comfort fixture projections in `tests/fixtures/providers/`.
- Provider subprocess tests for minimal env, constant argv, help/tool
  fingerprints, timeouts, cleanup, exact value redaction, and isolated homes.
- Beijing→Shanghai all-live Trip: ready/live rail, AMap, FlyAI, and VariFlight.
- Guangzhou→Shenzhen same-day round trip: two live rail legs, live AMap matrix,
  no hotel call, and explicit ready/no-results flight health.
- Workspace and full Git-history exact credential-value scans with zero hits.
