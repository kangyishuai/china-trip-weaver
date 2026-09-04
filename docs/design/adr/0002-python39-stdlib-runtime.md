# ADR-0002：默认运行时为 Python 3.9 标准库，Node 承载固定外部工具

- **Status:** Accepted
- **Date:** 2026-09-03

## Context

Codex 默认 shell 实测 `python3` 为 3.9.6、Node 为 v24.14.0；另有 Python 3.13+jsonschema，但硬约束是不手动 activate venv。参考实现证明标准库足以做 renderer/route 工具，但也暴露了声明 Python 3.7+、实际使用 3.12 语法的兼容失败。OR-Tools wheel/venv 体积大，不适合默认依赖。

## Decision

核心 CLI、contracts、credentials、HTTP adapters、evidence/cache/geo、matrix、light scheduler、replan、Trip/HTML validators 和 renderer 使用系统 `python3`、兼容 Python 3.9、只依赖标准库。`scripts/ctw` 在默认 shell 直接运行。12306/VariFlight/FlyAI 由 Node/npx 调固定完整版本并 probe。完整 Draft 2020-12 Schema 检查用于设计/CI，可使用已有 Python 3.13+jsonschema；产品默认路径实现固定 v1 的 release-critical shape/semantic validator，不要求通用 JSON Schema 包。OR-Tools 只在显式 feature flag、独立 runner 可用时调用，默认不 import/安装。

## Consequences

- 好处：零手动 venv、启动面小、与实测默认 shell 一致；核心 keyless 路径可直接运行。
- 代价：不得使用 3.10+ 语法/库便利；HTTP、DOM 与验证需要更多自有标准库代码和强测试。
- 风险：固定 v1 validator 不是通用 JSON Schema 引擎；必须持续用 `jsonschema` fixtures 交叉验证，Schema 变化时同步更新。
- npx 首次可能需下载且受网络影响；这属于 provider health/degradation，不得让 core import 失败。

## Evidence

- [任务 0 实测输出](../evidence/task0-runtime.txt)
- [研究决策 14：OR-Tools 可选](../../research/04-design-insights.md#14-采用or-tools-作为复杂日程可选引擎不作为无条件依赖)
- [trip-planner 标准库与兼容证据](../../research/02-projects/trip-planner-skill.md#3-脚本与依赖)
- [weekend-city-trip Python 版本证伪](../../research/02-projects/weekend-city-trip.md#5-测试现状与实测)

