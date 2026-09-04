# ADR-0001：保留 `plan-china-trip`，并与旧同名插件互斥

- **Status:** Accepted
- **Date:** 2026-09-03

## Context

目标主入口名已拍板为 `plan-china-trip`；现有 `china-travel-assistant` 使用完全同名 Skill。Codex 不合并同名 Skill，会同时暴露给选择器；真实 selector/implicit source metadata 尚未在隔离环境实测。其他参考 Skills 也有宽泛 travel/flight/hotel/HTML descriptions，会争抢自然语言意图。

## Decision

保留 `plan-china-trip`。`china-trip-weaver` 与 `china-travel-assistant` 不得同时启用；安装/doctor 和会话 catalog 任一层无法唯一确认入口来源时 fail closed、显示固定互斥提示、调用 provider 数为 0。插件内只有主入口 `allow_implicit_invocation: true`，其余 8 个子 Skill 全部 false，只由主入口显式路由。

## Consequences

- 好处：用户不会在两个同名入口或多个宽触发器之间猜，路由与责任主体唯一。
- 代价：用户不能平滑并装比较两个插件；迁移需禁用/卸载旧插件并新开会话。
- 风险：运行时来源检测接口未公开稳定；阶段三必须做隔离 UI/CLI 测试，验证前只承诺 fail-closed 人工门，见 `BLOCKED.md`。

## Evidence

- [同名不合并与 Skill 触发规范](../../research/01-codex-spec.md#3-skill目录触发与前置字段)
- [研究决策 2：不并存两个入口](../../research/04-design-insights.md#2-不采用与现有插件并存两个-plan-china-trip)
- [研究决策 3：只有主入口隐式触发](../../research/04-design-insights.md#3-采用主-skill-独占宽泛旅行意图子-skill-默认禁止隐式调用)
- [开放问题 Q1](../../research/05-open-questions.md#q1-目标-plan-china-trip-与旧同名-skill-的真实-ui调用行为是什么)

