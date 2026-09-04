# Provider contracts

All providers are read-only adapters. A provider is `ready` only after its pin/fingerprint, deadline, success/empty/auth/rate/timeout/wrong-shape fixtures, claim generation, and secret scan pass.

| Provider | Pin/fingerprint | Capability | Query deadline | Keyless behavior |
|---|---|---|---:|---|
| Host web | Host runtime with URL-bearing results | Dated destination research | 20s per query | Preferred keyless source; unavailable becomes explicit degradation. |
| 12306 MCP | `12306-mcp@0.3.10`, exact 8 tools | Station/direct/interline/route-stop rail data | 15s direct; 25s interline | Public query; cache → dated 12306 deep link → unknown. |
| FlyAI (optional) | `@fly-ai/flyai-cli@1.0.16`, version/help/current envelope | Flight and lodging candidates/deep links | 25s | Trial only after probe; dated Fliggy link → unknown. |
| AMap | v5 POI, v3 geocode/walk/transit/drive, v4 ride fingerprints | POI/geocode/route matrix | 8s POI/geocode; 12s route | No API call; cache → deep link/static estimate → unknown. |
| VariFlight | `@variflight-ai/variflight-mcp@1.0.3`, exact 9 tools | Optional flight status/weather/comfort/price enrichment | 15s | Probe/list only; no business call. |
| AnySearch | Runtime structured-result and usage fingerprint | Optional destination-search supplement | 15s | Disabled without user key; auto-registration is always rejected. |

Degrade each capability independently:

```text
R0 live → R1 fresh cache → R2 keyless public → R3 dated official link / typed estimate → R4 unknown
```

Every rung preserves provider health, mode, query/freshness time, claim status, and reason. Static estimates are not live routes; an unknown is not zero.

R1 is disabled and no provider response is cached today. AMap's terms section
3.5 forbid storing or caching its service data, and VariFlight's terms forbid
caching for redistribution without a written contract. Every capability
therefore falls straight from R0 to R2. A future cache may only be enabled for
a provider whose terms permit it.

## FlyAI is an optional, best-effort source

`@fly-ai/flyai-cli` is an unofficial third-party wrapper around Fliggy
services, published by an individual maintainer, and its command surface has
already drifted once between releases. Lodging and flight inventory are
therefore optional: `--lodging` defaults to `off`, a probe mismatch fails
closed, and a failure of any kind degrades that one capability instead of the
plan. No long-term availability is promised. Tests assert that a failing FlyAI
still yields a schema-valid Trip, reports its own health honestly, invents no
flight candidate, and leaves lodging to the candidate file.

## Attribution

When a provider actually contributed data, the rendered page names it in the
footer. AMap's terms section 7.7 require naming 高德地图 as the source wherever
its data is shown, and VariFlight's terms carry an attribution mandate for
permitted non-commercial sharing. The renderer emits this automatically from
`provider_health`, so a provider that was missing or degraded is never named.

## Mutual exclusion

Codex does not merge Skills that share a name, so two enabled plugins exposing `plan-china-trip` both reach the selector. `scripts/ctw doctor` detects this automatically: it reads `codex plugin list --json`, walks each enabled plugin's `skills/` directory, and reports `skill_conflicts` as `clear`, `conflict` with the offending plugin ids, or `unknown` when no Codex CLI could be consulted. Treat `conflict` and `unknown` alike: make zero provider calls and display the reported notice:

> 检测到另一个同名 Skill。Codex 不会合并同名 Skill，两个入口会同时出现在选择器里。请先在 Plugins Directory 中禁用或卸载其中一个，然后新建会话再试；当前未运行任何行程查询。
