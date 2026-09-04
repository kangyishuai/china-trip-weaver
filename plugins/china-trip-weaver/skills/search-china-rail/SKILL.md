---
name: search-china-rail
description: Normalize read-only China Railway station, schedule, seat, fare, direct, transfer, and route-stop results from the pinned 12306 MCP. Invoke explicitly from plan-china-trip for a dated rail leg or rail alternative; never log in, hold, purchase, pay, cancel, or change a ticket.
---

# Search China Rail

Use the pinned `12306-mcp@0.3.10` through the `china-rail` server.

1. Probe the exact eight-tool fingerprint before the first business call.
2. `--from` and `--to` each accept either an exact Chinese station name (for example `昆明南`) or a Chinese city name (for example `昆明`). Resolve each value in this order: exact station name, city representative station, then every station in the city.
3. Parse MCP text as JSON and fail closed on tool/schema/pipe-column drift.
4. Normalize dated services, times, seat/fare facts, typed prices, source URL, query time, claims, and health. An empty result is not a provider failure.
5. Return read-only candidates and the official 12306 deep link. Never invoke login or transaction behavior.

Do not substitute host search or AnySearch for railway schedules, seats, or fares. If the pinned railway path and documented degradation are unavailable, leave those facts unknown and report railway health independently of the destination-search rung.

If all three station-resolution layers are empty, return `no_results`. If the final city lookup returns multiple stations, return every candidate in distance order when distance metadata is available, classify the result as `ambiguous`, and require the caller to choose an exact station and retry; never guess one station for the user. A documented lookup error at one layer is a fallback signal, not `contract_mismatch`.

The command emits a JSON object with `transport_legs`, `claims`, `health`, `warnings`, and `error_class`:

```bash
scripts/ctw rail --date 2026-09-10 --from 北京 --to 上海 --train-filter-flags GD --limit 10 --output-json rail-result.json
```

Use the actual requested date; the example date only illustrates the format. A fixture run adds `--fixture <provider-fixture.json> --fixed-clock <ISO-8601>`. Use the railway section of `../../references/provider-contracts.md` for pins, deadlines, and degradation.
