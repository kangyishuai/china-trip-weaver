# Provider contracts

All providers are read-only adapters. A provider is `ready` only after its pin/fingerprint, deadline, success/empty/auth/rate/timeout/wrong-shape fixtures, claim generation, and secret scan pass.

| Provider | Pin/fingerprint | Capability | Query deadline | Keyless behavior |
|---|---|---|---:|---|
| Host web | Host runtime with URL-bearing results | Dated destination research | 20s per query | Preferred keyless source; unavailable becomes explicit degradation. |
| 12306 MCP | `12306-mcp@0.3.10`, exact 8 tools | Station/direct/interline/route-stop rail data | 15s direct; 25s interline | Public query; cache → dated 12306 deep link → unknown. |
| FlyAI | `@fly-ai/flyai-cli@1.0.16`, version/help/current envelope | Flight and lodging candidates/deep links | 25s | Trial only after probe; cache → dated Fliggy link → unknown. |
| AMap | v5 POI, v3 geocode/walk/transit/drive, v4 ride fingerprints | POI/geocode/route matrix | 8s POI/geocode; 12s route | No API call; cache → deep link/static estimate → unknown. |
| VariFlight | `@variflight-ai/variflight-mcp@1.0.3`, exact 9 tools | Optional flight status/weather/comfort/price enrichment | 15s | Probe/list only; no business call. |
| AnySearch | Runtime structured-result and usage fingerprint | Optional destination-search supplement | 15s | Disabled without user key; auto-registration is always rejected. |

Degrade each capability independently:

```text
R0 live → R1 fresh cache → R2 keyless public → R3 dated official link / typed estimate → R4 unknown
```

Every rung preserves provider health, mode, query/freshness time, claim status, and reason. Static estimates are not live routes; an unknown is not zero.

## Mutual exclusion

`china-trip-weaver` and `china-travel-assistant` must not be enabled together because both expose `plan-china-trip`. When the old plugin is detected or the entry source is not uniquely known, make zero provider calls and display:

> 检测到另一个 `plan-china-trip`（`china-travel-assistant`）或无法唯一确认入口来源。Codex 不会合并同名 Skill。请先在 Plugins Directory 中禁用/卸载旧插件，或禁用本插件，然后新建会话再试；当前未运行任何行程查询。
