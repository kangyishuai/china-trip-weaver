# ADR-0008：产品永久止步于查询、比较与深链

- **Status:** Accepted
- **Date:** 2026-09-03

## Context

铁路、航班和住宿页面涉及登录、验证码、实名、订单、支付、退改及价格/库存责任，权限和风险远高于行程研究。参考项目对该边界处理不一；目标 MVP 已拍板永不下单/实名/支付。

## Decision

所有 Skills、CLI、provider adapters、Trip、renderer 和 tests 都只允许 public/read-only query、比较、官方/dated HTTPS deep links。禁止登录代办、验证码、cookie/session reuse、占位/hold、提交身份、下单、支付、取消、改签/退订；不接受这些凭据/信息。用户提出混合请求时拒绝交易部分，继续提供只读比较/深链。URL/action/schema/HTML validator 与 provider call allowlist 把边界变成机器门禁。

## Consequences

- 好处：显著缩小权限、隐私、财务和误操作风险，keyless baseline 可成立。
- 代价：用户必须离开 artifact 在官方/OTA 页面自行核验并完成交易，插件不能保证库存/总价。
- 风险：provider description 可能写 booking；adapter 只能保留 deep link，不可暴露 transaction tool。发现新交易 tool 默认 deny。
- 此边界为永久架构原则；扩大必须新 ADR、威胁/法律审查和明确用户授权，不能作为普通 feature 开关。

## Evidence

- [研究决策 20](../../research/04-design-insights.md#20-采用查询比较深链止步交易动作永远出-scope)
- [凭据与网络控制面](../../research/01-codex-spec.md#9-凭据环境变量与沙箱网络)
- [china-travel-assistant 职责边界](../../research/02-projects/china-travel-assistant.md#6-优点缺点与职责边界)

