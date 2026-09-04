---
name: search-china-air
description: Normalize dated mainland-China flight candidates and booking deep links from the pinned FlyAI CLI, with optional VariFlight status, comfort, weather, and price enrichment. Invoke explicitly from plan-china-trip for a flight leg or flight-versus-rail comparison; do not transact or present an untyped price.
---

# Search China Air

FlyAI is an optional, best-effort third-party wrapper. When it is unavailable or its contract has drifted, report the degraded health and continue with rail comparison rather than inventing a flight.

Use FlyAI as the candidate/deep-link source and VariFlight only as optional enrichment.

- Probe `@fly-ai/flyai-cli@1.0.16` version/help and current command envelope before use; never infer a command from stale documentation.
- Identify a flight by number, departure airport, arrival airport, and local departure date. Keep conflicts between providers as separate claims.
- Invoke VariFlight business tools only when its key is locally configured and the exact nine-tool fingerprint passes.
- Type every price and preserve currency, party, tax/seat context, query time, and confidence. Do not average incompatible or conflicting prices.
- Return candidates, deep links, claims, health, and warnings. Never log in or complete a booking.

Query live read-only comparisons directly, then require the assembled Trip to pass validation:

```bash
scripts/ctw air --origin 北京 --destination 上海 --date YYYY-MM-DD --output-json air.json
scripts/ctw validate trip.json
```

Each flight leg uses the frozen `transportLeg` shape: dated endpoints/times, `service_number`, typed `price`, booking deep link, and resolvable `claim_ids`.
