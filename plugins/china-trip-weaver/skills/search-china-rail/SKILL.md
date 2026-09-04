---
name: search-china-rail
description: Normalize read-only China Railway station, schedule, seat, fare, direct, transfer, and route-stop results from the pinned 12306 MCP. Invoke explicitly from plan-china-trip for a dated rail leg or rail alternative; never log in, hold, purchase, pay, cancel, or change a ticket.
---

# Search China Rail

Use the pinned `12306-mcp@0.3.10` through the `china-rail` server.

1. Probe the exact eight-tool fingerprint before the first business call.
2. Resolve stations, query direct services, then use bounded interline search only when needed; query route stops only for a selected service.
3. Parse MCP text as JSON and fail closed on tool/schema/pipe-column drift.
4. Normalize dated services, times, seat/fare facts, typed prices, source URL, query time, claims, and health. An empty result is not a provider failure.
5. Return read-only candidates and the official 12306 deep link. Never invoke login or transaction behavior.

The command emits a JSON object with `transport_legs`, `claims`, `health`, `warnings`, and `error_class`:

```bash
scripts/ctw rail --date 2026-09-10 --from 北京 --to 上海 --train-filter-flags GD --limit 10 --output-json rail-result.json
```

Use the actual requested date; the example date only illustrates the format. A fixture run adds `--fixture <provider-fixture.json> --fixed-clock <ISO-8601>`. Use the railway section of `../../references/provider-contracts.md` for pins, deadlines, and degradation.
