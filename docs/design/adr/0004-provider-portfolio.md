# ADR-0004：采用 12306 + FlyAI + AMap 主组合，VariFlight/AnySearch 可选

- **Status:** Accepted
- **Date:** 2026-09-03

## Context

没有单一 provider 能覆盖中国铁路、航班、住宿、POI/地理编码和真实地面路线。`12306-mcp` 已实测启动/站点调用；当前 `12306-skill` 三次失败且有 cache bug。FlyAI 覆盖航班/酒店但 CLI/schema/trial 漂移；VariFlight 强在航空增强；AMap 的底层 POI/route 合适，但参考 `travelPlanner` 未实际 route 且丢输出。目的地研究默认可用宿主 web，AnySearch contract/auto-registration 未实测。

## Decision

铁路主源固定 `12306-mcp@0.3.10`；航班/住宿主源固定 `@fly-ai/flyai-cli@1.0.16`，只有 runtime probe 通过才调用；POI/geocode/route 使用自写薄 AMap Web Service adapter。VariFlight `1.0.3` 只做可选 flight status/comfort/weather/price enrichment，AnySearch 默认关闭且只做可选目的地搜索补充。`12306-skill` 与 AMap `travelPlanner` 永不作为 fallback。所有 provider 固定版本、probe、typed adapter、deadline、fixtures 和独立 health。

## Consequences

- 好处：各 provider 职责窄、可替换；主能力有最符合中国场景的来源组合。
- 代价：多进程/多 schema、identity/冲突/凭据/降级复杂度增加。
- 风险：FlyAI/AMap/12306 response 尚有开放验证项；probe/fixtures 完成前对应 health 只能 degraded/beta。
- 无 Key 仍须沿 live→cached→keyless public→deep link/estimate→unknown 交付，不能因 AMap/VariFlight 缺 Key 失败全局。

## Evidence

- [研究决策 7：铁路](../../research/04-design-insights.md#7-采用12306-mcp-为铁路主-provider不采用当前-12306-skill)
- [研究决策 8：FlyAI/VariFlight](../../research/04-design-insights.md#8-采用flyai-主查可售航班酒店variflight-只做航空增强)
- [研究决策 12：AMap 底层能力](../../research/04-design-insights.md#12-不采用amap-lbs-skill-的-travelplanner采用其底层-poiroute-provider-角色)
- [无 Key 降级专题](../../research/04-design-insights.md#必答专题-c无-key-时如何降级)

