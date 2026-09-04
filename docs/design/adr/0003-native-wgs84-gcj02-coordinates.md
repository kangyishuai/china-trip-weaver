# ADR-0003：坐标同时保存 native、WGS-84、GCJ-02 与转换 provenance

- **Status:** Accepted
- **Date:** 2026-09-03

## Context

中国行程同时消费 AMap route/render（GCJ-02）与 KML/OSM/通用数据（WGS-84）。参考项目有未标 CRS、向 AMap 直接喂 WGS、只存单一坐标等缺陷，也有在 render boundary 转换的正例。单坐标字段无法安全跨 provider，重复转换会再次偏移。

## Decision

每个非空坐标强制 `coordinates{source_crs,native,wgs84,gcj02,conversion}`。native 永不覆盖；来源对应的标准字段等于 native；另一字段只有在记录 method/version/derived_fields/time/accuracy 时派生。`provider-unknown` 不转换。AMap query/deep link 只用 GCJ-02，KML/OSM 只用 WGS-84；任何消费者不得猜 native CRS或二次转换。

## Consequences

- 好处：跨地图/provider 可追溯，坐标错误能在 contract/fixture 层发现。
- 代价：每个地点字段更大，adapter/validator/test 必须维护转换 metadata。
- 风险：算法转换精度和香港/边界行为需 known-point tests；provider 未声明 CRS 时只能 unknown，可能降低地图覆盖。
- renderer v1 只画明确标注的点位示意，不把顺序连线冒充 route。

## Evidence

- [研究决策 11](../../research/04-design-insights.md#11-采用同时保存-provider-native-与规范化坐标不做无标记的单坐标)
- [坐标专题逐项目对照](../../research/04-design-insights.md#必答专题-b坐标系处理)
- [AMap schema/CRS 开放问题 Q5](../../research/05-open-questions.md#q5-amap-当前-web-api-的-v3v4v5-schemacrs-与-route-quota-能否形成稳定-adapter)

