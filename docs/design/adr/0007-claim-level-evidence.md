# ADR-0007：所有外部事实使用 claim-level evidence ledger

- **Status:** Accepted
- **Date:** 2026-09-03

## Context

粗粒度 `dataSources[]`/来源标题只能证明“用过某源”，无法确定某个价格、班次、开放时间或路线时长来自哪里、何时查询、是否冲突。动态 provider 常以 text JSON、无 timestamp、wrong shape 或 lead price 输出，缺失也容易被误写为 0/成功。

## Decision

Trip 中每个外部/动态事实由 claim 指向具体 subject/field，强制 `source_url/provider/queried_at/status/confidence/mode`；可选 `as_of/raw_ref/response_hash/json_path`。unknown、conflict、stale、unavailable、mock 都是一等状态。每个价格强制 `price_type/unit/tax context/query time/claim`，每个 provider 返回 version/mode/health。原始数据只以脱敏最小 fixture/cache 引用，不把 cookie、headers、账号或完整个人查询嵌入 Trip。

## Consequences

- 好处：10 分钟内可沿字段追源，冲突/过时/降级可机器验证，renderer 不必猜真实性。
- 代价：Trip 更冗长，adapter 必须做字段级 mapping，cache/retention 更复杂。
- 风险：raw 保留粒度与 provider ToS 尚未核准；当前采用最小 `raw_ref+hash+path`，公开发布前再验证。
- 没有 claim 的动态事实阻断发布，而不是只显示 warning。

## Evidence

- [研究决策 5](../../research/04-design-insights.md#5-采用claim-level-evidence-ledger不采用粗粒度来源列表)
- [研究决策 6](../../research/04-design-insights.md#6-采用unknownprovider-health-与-price-type-必须进入合同)
- [开放问题 Q9](../../research/05-open-questions.md#q9-claim-level-evidence-ledger-保存多少-raw-data-才可重放又不泄露)

