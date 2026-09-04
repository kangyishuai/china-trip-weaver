# 统一 Trip 数据模型

权威机器合同：[`schema/trip.schema.json`](schema/trip.schema.json)，JSON Schema Draft 2020-12。Trip 是调研、provider、排程、局部重排和 renderer 之间唯一事实源；阶段三不得再定义并行的 itinerary/page/provider 公共模型。[依据：研究决策 4](../research/04-design-insights.md#4-采用一个版本化-itineraryjson-是所有层的唯一事实源)

## 1. 顶层对象

| 字段 | 语义 |
|---|---|
| `schema_version` | 合同版本，v1 固定 `1.0.0`；Schema 破坏性变化才升 major。 |
| `trip_id` | 跨 revision 稳定 ID。 |
| `revision` | 当前 revision number、parent、原因、时间和创建者。 |
| `mode` | 整份交付的最高真实性口径：`live/cached/static/mock`。混合来源时取最保守且在 claim/provider 层保留各自 mode。 |
| `mock_notice` | 仅 mock 必须为非空；其他 mode 可缺。silent mock 由 Schema 直接拒绝。[依据：研究决策 19](../research/04-design-insights.md#19-不采用silent-mock空字段被包装成成功) |
| `request` | 用户原始硬字段的归一化结果，以及显式 assumptions。 |
| `days[].slots[]` | 日与逐时段；slot 只引用 transport/lodging/POI 等实体，不复制其动态事实。 |
| `transport_legs` | 跨城与市内交通腿，含端点、时刻、时长、价格、深链、locks 和 claims。 |
| `lodgings` | 住宿片区/候选、入住日期、坐标、typed price、dated deep links 与 claims。 |
| `pois` | POI/餐饮/活动候选、坐标、停留时长、开放窗口、价格、deep links 与 claims。 |
| `claims` | 每个动态或外部事实的 evidence ledger。 |
| `provider_health` | 本次运行中每个尝试/跳过 provider 的版本、mode、状态、能力与原因。 |
| `unknowns` | 对最终展示仍未知的字段给出 JSON Pointer、原因、provider 与关联 claim。 |
| `patches` | 从旧 revision 到当前 revision 的 versioned patch 历史。 |
| `generated_at` | 当前 JSON 生成时间，不等于外部事实查询时间。 |

`null` 只表示“值未知/不适用”，不表示 0、免费、无库存或立即可用。最终展示中的每个 `null` 动态字段必须由 `unknowns` 或 `status=unknown/unavailable` 的 claim 解释；这是语义校验规则。[依据：研究决策 6](../research/04-design-insights.md#6-采用unknownprovider-health-与-price-type-必须进入合同)

## 2. Request、日与时段

`request` 的目的城市、日期、人数是硬输入；软偏好缺省必须进入 `assumptions[]`。城市周末可令 `origin=null`；跨城场景必须由语义校验器要求 origin。日期跨度的产品限制（1–7 天）同时由 Schema `days.maxItems=7` 和 request/day 对齐校验保证。

每个 `slot` 有完整 ISO 8601 `start_at/end_at`、`kind`、引用实体 `ref_id`、`locked` 和 claim IDs。Schema 验证形状；阶段三语义校验器还必须断言：

1. 同一天 slots 按开始时间排序且不重叠，`end_at > start_at`。
2. `ref_id` 指向存在且类型与 `kind` 相容的对象；`claim_ids` 全部存在。
3. transport slot 的时间覆盖对应腿及安全 buffer；POI slot 落在已验证 opening window 或显式 tentative。
4. `locked=true` 只能由用户接受、已订事实或 replan policy 设定，不能由 provider 猜测。

真实路线时间矩阵必须先于最终 schedule；无 AMap Key 的 estimate 必须同时带 `mode=static`、estimate price/time claim 或 unknown，不能把 Haversine/顺序连点写成 route。[依据：研究决策 13](../research/04-design-insights.md#13-采用先真实-travel-time-matrix再排-time-windows不以直线连线冒充路线)

## 3. 坐标合同

每个非空 `coordinates` 必须包含：

```text
source_crs       WGS84 | GCJ02 | BD09 | provider-unknown
native           provider 原样经纬度，永不覆盖
wgs84            WGS-84 点或 null
gcj02            GCJ-02 点或 null
conversion       status/method/version/derived_fields/converted_at/accuracy_m
```

规则：

- AMap 输入/route/render 使用 GCJ-02；KML/OSM 使用 WGS-84。消费者只能读对应字段，禁止拿 `native` 猜 CRS。
- 来源是 WGS84/GCJ02 时，对应标准字段应等于 native；另一字段若派生，`conversion.derived_fields` 必须列出，方法与版本不得为空。
- `source_crs=provider-unknown` 时不得执行转换；`wgs84/gcj02` 保持 null，另列 unknown/claim。
- 一次转换的结果不可再次作为 native 转换，避免二次偏移。
- Schema 约束字段存在与数值范围；上述等值、单次转换和消费者选择由坐标语义测试断言。

该设计不在“只存 WGS”与“只存 GCJ”之间二选一，保留 native + 两种消费坐标及 provenance。[依据：研究决策 11](../research/04-design-insights.md#11-采用同时保存-provider-native-与规范化坐标不做无标记的单坐标)、[坐标专题](../research/04-design-insights.md#必答专题-b坐标系处理)

## 4. Claim 级证据

每条 claim 最少包含 `claim_id/subject_ref/field_path/value/source_url/provider/queried_at/status/confidence/mode`。核心五字段 `source_url/provider/queried_at/status/confidence` 均为必填；粗粒度“用过哪些来源”不能替代 field-level mapping。[依据：研究决策 5](../research/04-design-insights.md#5-采用claim-level-evidence-ledger不采用粗粒度来源列表)

- `field_path` 是指向 subject 内字段的 JSON Pointer；`value` 是当时采纳/比较的值。
- `status`：`verified/partial/hypothesis/unknown/stale/conflict/unavailable/mock`；冲突不能被最后写入者静默覆盖。
- `confidence` 是 0–1 的证据置信度，不是推荐分数；provider 自报分不直接当 confidence。
- `mode` 独立记录该 claim 是 live/cached/static/mock。
- `raw_ref/response_hash/json_path` 可选，只能指向脱敏 fixture/cache；Trip 不嵌原始响应、cookie、headers 或个人查询信息。
- 动态价格/库存/状态必须带真实 query time；网页/规则型静态事实也要带获取时间和 URL。

raw 数据保存粒度仍需用脱敏 fixtures 验证，本合同先采用 `raw_ref + sha256 + selected path`，不承诺保存完整 provider payload。[依据：开放问题 Q9](../research/05-open-questions.md#q9-claim-level-evidence-ledger-保存多少-raw-data-才可重放又不泄露)

## 5. Price 与 provider health

所有价格对象都强制 `price_type`：

| `price_type` | 含义 |
|---|---|
| `live` | provider 在 `queried_at` 返回、且上下文与日期/人数匹配；仍不保证随后可买。 |
| `reference` | 历史/列表级/区间参考，不是当前 checkout total。 |
| `estimate` | 明确算法或静态估算；必须可解释来源。 |
| `verify-on-click` | 只有 dated deep link/checkout 能确认。 |
| `unknown` | 不知道；`amount` 应为 null。 |

`unit` 区分 total/per_person/per_night/from，`includes_taxes` 允许 unknown。酒店不能把 list lead price 写成 room-level all-in total。[依据：研究决策 9](../research/04-design-insights.md#9-采用住宿交付片区-dated-deep-links-可核验条件不编造房价)

provider health 至少覆盖 `ready/missing/expired/forbidden/rate_limited/degraded/unavailable/contract_mismatch`；`mode/version/checked_at/reason` 强制进入对象。HTTP 200 但响应 wrong-shape 必须是 `contract_mismatch`，不是 ready。

## 6. Revision 与局部 patch

新建 Trip 从 revision 1、`parent_revision=null`、`patches=[]` 开始。局部重排创建 `target_revision=base_revision+1` 的 patch，包含：

- trigger/reason；受影响 days/refs；所有 locked refs。
- JSON-Patch 形状 operations；阶段三只允许 `add/remove/replace/move` 修改白名单路径。
- `reverify_claim_ids`；变化 hop 新 claim 不能沿用旧 queried_at。
- stability：preserved/changed refs 与 0–1 score。

语义校验器必须断言 base 与 current revision 连续、operation 可重放、locked refs 未改、未受影响 day 的 canonical JSON 字节相同。Schema 只能验证 patch 形状，不能假称已验证这些跨文档性质。[依据：研究决策 15](../research/04-design-insights.md#15-采用局部重排是-versioned-patch不是重跑全计划)、[开放问题 Q11](../research/05-open-questions.md#q11-局部重排的最小-patchstability-contract-应是什么)

## 7. 示例与设计期校验器

目录：

```text
schema/
├── trip.schema.json
├── check_schema.py
└── examples/
    ├── valid/      # weekend-live.json、multicity-static.json
    └── invalid/    # 各只破坏一个约束
```

`check_schema.py` 仅用于本阶段示例门禁，使用现有 Python 3.13 环境中的 `jsonschema.Draft202012Validator`，不属于产品运行时。它先校验 Schema 本身，再逐文件打印 PASS/FAIL；任一文件 FAIL 即 exit 1。

验收命令：

```text
~/miniconda3/bin/python3 design/schema/check_schema.py design/schema/trip.schema.json design/schema/examples/valid
~/miniconda3/bin/python3 design/schema/check_schema.py design/schema/trip.schema.json design/schema/examples/invalid
```

invalid fixtures 分别且仅违反：坐标缺 `source_crs`、claim 缺 `source_url`、`mode=mock` 缺 `mock_notice`、price 缺 `price_type`。

## 8. 阶段三需补的语义验证

JSON Schema 之后还必须实现：ID/claim/ref 完整性、日期与 slot 顺序、request/day 数量一致、route matrix 覆盖、价格与 claim 对齐、provider health 覆盖、mode 取最保守值、坐标派生规则、patch 可重放/稳定性、禁止交易 URL scheme/敏感字段。此分层避免把 Schema 做不到的关系约束写成“已保证”。四层测试设计见 `08-testing.md`。[依据：研究决策 21](../research/04-design-insights.md#21-采用四层测试不把能启动能打印当测试)
