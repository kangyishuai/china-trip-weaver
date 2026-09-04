# ADR-0006：v1 只实现一个确定性手机 HTML renderer

- **Status:** Accepted
- **Date:** 2026-09-03

## Context

参考项目的 8 主题带来大量已知视觉/导出问题；另一个单文件方案证明 phone contract、embedded JSON 和 validator 有价值，但 Leaflet/CDN/remote images 并非离线。共享 HTML 嵌 AMap JS key/security 不符合凭据边界。

## Decision

v1 只有一个 renderer，只接 schema/semantic-valid Trip，输出 deterministic UTF-8 单文件 HTML并内嵌 canonical Trip JSON。页面手机优先、核心离线可读；remote scripts/CSS/fonts/images/tiles 为零，CSP `script-src 'none'`，无地图 Key。地图仅为内联点位/访问顺序示意并明确“非真实路线”，交互通过用户主动点击的安全 HTTPS deep links。生成后 validator 检查事实一致、安全、secret、offline、mobile、print、a11y。

## Consequences

- 好处：表面积小、可复现、可分享、无 secret，事实与页面一一对应。
- 代价：没有多主题、在线瓦片、真实道路 geometry 或远程图片，视觉表现更克制。
- 风险：非执行 JSON `<script>` 与严格 CSP 的浏览器兼容需实测；不兼容时改用转义 template，不放宽 CSP。
- 新主题/图片/交互地图需要新 Schema/ADR，不能在模板私加第二数据源。

## Evidence

- [研究决策 16：单 renderer](../../research/04-design-insights.md#16-采用v1-只做一个-deterministic-手机-html-renderer)
- [研究决策 17：核心离线](../../research/04-design-insights.md#17-采用只承诺核心离线可读地图图片显式降级)
- [开放问题 Q12](../../research/05-open-questions.md#q12-手机单文件-html-能否同时做到-secret-free核心离线与地图可用)

