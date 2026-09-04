# ADR-0005：轻量排程为默认，OR-Tools 按阈值显式启用

- **Status:** Accepted
- **Date:** 2026-09-03

## Context

OR-Tools 的 6 点 time-window 示例实测可行，但 wheel 约 21.9MB、venv 约 188MB，且尚未与 5–12 POI 的轻量算法做统一 benchmark。MVP 多为 1–7 天、单日 5–8 个访问点；默认依赖 OR-Tools 会破坏直接运行基线。

## Decision

v1 默认使用 Python 3.9 标准库的 deterministic beam insertion + bounded local improvement。OR-Tools 默认关闭、不自动安装；仅当 `CTW_ENABLE_ORTOOLS=1`、独立 runner/version probe 通过、hard-required matrix 完整，并命中以下任一阈值才调用：单日候选 ≥9、hard windows ≥4、跨日耦合 ≥2、或 light no-solution 且候选 ≤20。solve 上限 5 秒，结果必须回到统一 validator；超时/缺依赖回 light 最佳可行结果或 structured no-solution。

## Consequences

- 好处：常见计划零额外依赖、确定易解释；复杂案例仍有更强 solver 路径。
- 代价：light algorithm 可能错过全局更优解；要维护统一 objective/result adapter。
- 风险：阈值是设计假设，不是当前实测结论；阶段三 20-golden benchmark 后可用新 ADR 调整，不能静默改常量。
- OR-Tools 不是缺 route/provider 数据的替代品，estimate/unknown matrix 仍必须显式。

## Evidence

- [研究决策 14](../../research/04-design-insights.md#14-采用or-tools-作为复杂日程可选引擎不作为无条件依赖)
- [开放问题 Q10](../../research/05-open-questions.md#q10-轻量排程与-or-tools-的切换阈值是什么)
- [OR-Tools 实测边界](../../research/02-projects/or-tools.md#5-测试现状与实测)

