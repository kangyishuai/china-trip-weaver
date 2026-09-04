# Provider、证据与降级

本文件定义阶段三所有外部数据边界。provider 只查询并归一化，不排程、不渲染、不执行交易；主入口只消费统一 AdapterResult。所有版本、schema 和 quota 结论只对 research 锁定快照负责，运行时仍必须 probe。[依据：研究决策 22](../research/04-design-insights.md#22-采用所有外部-climcp-固定版本-启动时-contract-probe)

## 1. 统一 Adapter 合同

### 1.1 接口

阶段三每个 adapter 实现相同语义接口：

```text
probe(context) -> ProviderHealth
query(ProviderRequest, context) -> AdapterResult
```

`ProviderRequest`：

| 字段 | 要求 |
|---|---|
| `request_id` | 本次调用随机 ID，只用于关联日志，不含用户信息。 |
| `capability` | `research/rail/flight/lodging/poi/geocode/route/weather` 之一。 |
| `parameters` | adapter 自己的 typed request；进入进程前完成日期、城市、IATA/站名等校验。 |
| `deadline_ms` | 从调用开始计算的硬 deadline，不允许 provider 无限挂起。 |
| `as_of` | 用户要求的业务日期，不得用 host local “today” 猜中国日期。 |
| `cache_policy` | `bypass/prefer/only`；默认 `prefer`，动态库存只接受对应 freshness window。 |
| `trace` | 非敏感 stage/attempt；不得带 Key、cookie、订单或粘贴原文。 |

`AdapterResult` 必须一次返回：

```text
provider, provider_version, capability, mode, queried_at,
normalized_items[], claims[], health, warnings[], raw_ref?, response_hash?
```

- `normalized_items` 只能是 `trip.schema.json` 对应的候选结构；provider raw payload 不跨 adapter 边界。
- `claims` 与写入字段一一对应；动态事实没有 `source_url/provider/queried_at/status/confidence` 即整个结果 contract FAIL。[依据：研究决策 5](../research/04-design-insights.md#5-采用claim-level-evidence-ledger不采用粗粒度来源列表)
- `mode` 必须是 `live/cached/static/mock`；mock 只允许 tests/显式 demo 且必须标 notice。
- `health.status != ready` 时仍可返回已验证的 cached/static partial data，但 warnings 与 unknowns 必须保留。
- 原始响应仅以脱敏 fixture/cache 引用和 SHA-256 指纹出现；禁止把 raw headers/cookie/account metadata 写进 Trip。

### 1.2 错误分类

| `error_class` | 判定 | health | retry |
|---|---|---|---|
| `invalid_request` | 本地输入不符合 adapter contract | `degraded` | 不重试，回到 intake/候选过滤 |
| `credential_missing` | 所需 env/file 值不存在 | `missing` | 不重试，走无 Key 分支 |
| `credential_expired` | provider 明确返回过期 | `expired` | 不重试，不在对话索取值 |
| `forbidden` | 401/403 且非明确 expired，或账户/余额禁用 | `forbidden` | 不重试 |
| `rate_limited` | 429 或明确 quota 响应 | `rate_limited` | 只尊重 `Retry-After` 且不越过总 deadline；否则降级 |
| `timeout` | adapter/h宿主 deadline 到期 | `degraded` | 幂等请求最多 1 次 |
| `network` | DNS/TLS/连接失败 | `degraded` | 最多 1 次，随后 cached/deep link |
| `upstream_5xx` | 5xx 或 provider 明确临时故障 | `degraded` | 最多 1 次 |
| `contract_mismatch` | JSON/text shape、tool list、字段类型或 fingerprint 漂移 | `contract_mismatch` | **不重试**，禁止 best-effort 猜字段 |
| `no_results` | 合法空结果 | `ready` | 不重试；扩大条件须由主入口明确决定 |
| `policy_blocked` | 需要登录/验证码/实名/交易或违反产品边界 | `unavailable` | 不重试；给官方 deep link |
| `internal` | adapter 自身异常 | `degraded` | 不重试；记录无 secret 的错误码 |

禁止把所有异常折叠成 `null`，也禁止 HTTP 200/wrong-shape 继续发布。[依据：研究决策 19](../research/04-design-insights.md#19-不采用silent-mock空字段被包装成成功)

### 1.3 timeout、版本、probe 与 fixture 的共同规则

- 进程启动、probe、业务 query 分开计时；主入口总预算必须大于各 provider deadline，但取消会话时子进程也要终止。
- 版本 pin 必须出现在调用命令/lock 与 health；仅在文档写版本不算固定。
- probe 先验证 executable/tool list/help/schema fingerprint，后续第一个真实响应再做 response-shape probe。需要额度的 probe 与真实请求合并，避免纯烧额度。
- fingerprint 不匹配立即 `contract_mismatch`；先更新 fixture/adapter/test，再改允许值。
- fixture 是脱敏 raw → normalized + claims 的完整对；包含 provider/version/captured_at/request shape/response hash，Key/cookie/request ID/个人数据必须删除。
- 每个 parser 至少有 success、empty、auth、rate-limit、timeout、wrong-shape fixtures；不能把“能启动/有输出”当测试。[依据：研究决策 21](../research/04-design-insights.md#21-采用四层测试不把能启动能打印当测试)

## 2. Provider 定值表

| Provider（pin） | MVP 能力 | Key | 无 Key 行为 | 首选降级 | 健康要点 |
|---|---|---|---|---|---|
| 宿主内置 web（host version） | 目的地、官方开放、活动、天气/政策链接 | 无本插件 Key | 可用即 `static/live`（按宿主结果）；不可用走用户资料/已有 cache | cached → 用户粘贴/官方 deep links → unknown | 工具缺失=`unavailable`；URL/日期不足=`degraded` |
| `12306-mcp@0.3.10` | station、直达/中转余票、座席/价格、经停 | 无 | 正常公共查询；仍需网络 | fresh cache → 12306 dated deep link → unknown | 冷启动网络、8 tools、text JSON/parser 漂移 |
| `@fly-ai/flyai-cli@1.0.16` | 航班/酒店 inventory 与 deep links | `FLYAI_API_KEY` 可选增强 | 只有 keyless trial probe 通过才调用；质量/额度不作承诺 | cached → trial → dated Fliggy deep link/estimate → unknown | command/schema/version 漂移优先判 mismatch |
| AMap Web Service（endpoint schema fingerprint） | POI、geocode、walking/transit/driving/riding route matrix | `AMAP_WEBSERVICE_KEY` | 不发 API；保留已有可信坐标或 static candidates | cached → keyless official map deep link/estimate → unknown | 401/403/429；v3/v4/v5 shape 与 GCJ-02 |
| `@variflight-ai/variflight-mcp@1.0.3` | 航班状态、转机、舒适度、机场天气、价格交叉 | `VARIFLIGHT_API_KEY` | 只 list/probe，不发业务调用 | 跳过 enrichment → FlyAI/官方 deep link | 9 tools、any/text response、余额/timeout |
| AnySearch（可选，runtime fingerprint） | 中文目的地搜索补充 | `ANYSEARCH_API_KEY` 可选 | anonymous 仅在明确不 auto-register 且 probe 通过时使用 | 宿主 web → cached → official deep links | response/usage/auto-registration 漂移 |

选择依据：12306 是铁路主 provider；当前 `12306-skill` 已三次失败且有确定 cache bug，**永不作为 fallback**。[依据：研究决策 7](../research/04-design-insights.md#7-采用12306-mcp-为铁路主-provider不采用当前-12306-skill) FlyAI 主查航班/住宿，VariFlight 只增强。[依据：研究决策 8](../research/04-design-insights.md#8-采用flyai-主查可售航班酒店variflight-只做航空增强) AMap 只承担底层 POI/route，不采用已证伪的 `travelPlanner`。[依据：研究决策 12](../research/04-design-insights.md#12-不采用amap-lbs-skill-的-travelplanner采用其底层-poiroute-provider-角色)

## 3. 各 Provider contract probe 与 timeout

数值是**实现假设**，须在阶段三 fixture/真实测试中调优；无论调优结果如何都保留硬 deadline。

| Provider | startup/probe | 单 query | contract probe | 关键 fixture/断言 |
|---|---:|---:|---|---|
| host web | 宿主控制 | 每个 research query 20s，整阶段 120s | 工具可用；结果必须含可访问 URL | 官方页、404、无日期、冲突双源 |
| 12306 | 25s | 15s；interline 25s | tools/list **恰为锁定 8 tools**；tool schema fingerprint；`get-current-date` 时区结果只作 probe | station、直达、无票、候补、中转、跨日、5xx、wrong pipe columns |
| FlyAI | 15s | 25s | `--version`；`--help`；实际 command 名与 stdout envelope fingerprint；不认可只在 README 出现的 command | flight/hotel success、empty、trial limit、stderr error、wrong JSON、missing price type |
| AMap | 本地 1s；首个真实请求合并 probe | geocode/POI 8s，route 12s | endpoint version、`status/info`、pagination、route/POI required fields、GCJ-02 marker | 5 个境内点、错城、HK/边界、walking/transit、401/429、shape drift |
| VariFlight | 15s | 15s | tools/list 9 tools、schema fingerprint；有 Key 时把 probe 合并首个只读 query | exact flight identity、weather、raw price、401/403/429、any/wrong-shape |
| AnySearch | 10s | 15s | response shape、usage fields、anonymous 不产生/保存 Key | 中文召回、empty、429/402、auto-register response、source URL |

12306 当前只实测 station，真实余票 parser/日期/失败恢复仍是开放项；fixture 验收通过前 rail inventory 标 beta/degraded。[依据：开放问题 Q4](../research/05-open-questions.md#q4-12306-mcp-的真实余票-parser日期范围与失败恢复是否稳定) FlyAI command 与 keyless trial 同理，不能把文档示例当 probe 结果。[依据：开放问题 Q3](../research/05-open-questions.md#q3-fly-aiflyai-cli-的当前-commandschemakeyless-trial-到底是什么)

## 4. Capability 细则

### 4.1 目的地调研

默认使用宿主内置 web，query 维度由 city/date/user interests 动态生成；优先政府、场馆、运营方等一手源。AnySearch 默认关闭，只在显式配置且 contract probe 通过时作为补充，不允许 anonymous auto-registration 或保存新 Key。对关键开放/活动事实，冲突双源并存，不能把“至少两个来源”简化成粗粒度来源列表。[依据：开放问题 Q8](../research/05-open-questions.md#q8-目的地调研应使用内置-webanysearch还是两者组合)

### 4.2 铁路

顺序：station resolve → direct query → 必要时 bounded interline → 已选车次 route stops。输出只读 schedule/seat/price/deep link；source URL 固定指向对应 12306 public endpoint/official landing，并补 `queried_at`。cache 不跨业务日期，且库存 claim 不得由 station cache 代替。

### 4.3 航班

以 `flight_no + departure airport + arrival airport + local departure date` 建 identity；FlyAI 提供候选/deep link，VariFlight 只补 status/comfort/weather/cross-price。币种、税费、舱位或日期不同不得直接比较；冲突写两个 claims 和 `status=conflict`，不做平均。[依据：开放问题 Q6](../research/05-open-questions.md#q6-航班价格库存状态跨-flyai-与-variflight-如何同一航段对齐)

### 4.4 住宿

Adapter 输出区域、候选物业、dated deep links 和已核验条件。只有 dates/party/room/tax/cancellation 上下文完整的 provider 结果才可标 live；否则 `verify-on-click`。无 Key 不编造 nightly rate。[依据：研究决策 9](../research/04-design-insights.md#9-采用住宿交付片区-dated-deep-links-可核验条件不编造房价)、[开放问题 Q7](../research/05-open-questions.md#q7-无-key有-key-下住宿数据能可靠到什么粒度)

### 4.5 AMap/坐标/route

Adapter 保存 AMap native GCJ-02、再由有版本的转换函数派生 WGS-84；route query 始终使用 GCJ-02。每个 matrix cell 含 from/to/mode/duration/distance/fare?/queried_at/claim/health；不可达也是有证据的 cell。禁止传旧 pagination 字段或把相邻 POI 顺序连线当 route。当前 endpoint/schema/quota 未实测，必须通过 Q5 所述 probe 才进入 ready。[依据：开放问题 Q5](../research/05-open-questions.md#q5-amap-当前-web-api-的-v3v4v5-schemacrs-与-route-quota-能否形成稳定-adapter)

## 5. 降级阶梯

每个 capability 独立走以下阶梯，不因一个 provider 失败把整个 Trip 降为失败：

```text
R0 live provider
  ↓ unavailable / policy / deadline
R1 cached evidence within capability TTL
  ↓ absent / stale
R2 keyless public source (12306、host web、probe 后的 FlyAI trial)
  ↓ no structured result
R3 dated official/deep link + clearly typed estimate
  ↓ estimate would mislead
R4 unknown with reason and next verification action
```

每次下降都写 `mode/provider_health/claim status/freshness/reason`；R3 estimate 不是 live，R4 不是 0。mock 不在生产降级阶梯内。[依据：无 Key 专题](../research/04-design-insights.md#必答专题-c无-key-时如何降级)

### 5.1 Freshness 默认值

以下均为**假设性上限**，provider/用户可要求更短；过期只能作为 `stale/reference`：

| 数据 | R1 最大 age |
|---|---:|
| 余票/库存/实时航班状态 | 5 分钟 |
| 航班/铁路价格 | 15 分钟 |
| 酒店房态/价格 | 15 分钟且 query context 完全相同 |
| AMap route-time matrix | 6 小时；出发前/异常重排重新查 |
| POI/geocode | 30 天，若 provider ID/地址未变 |
| 官方开放时间/活动 | 24 小时；活动日期临近时 6 小时 |
| 静态城市背景 | 30 天 |

provider ToS 若禁止缓存，则对应 R1 禁用；不得用工程便利覆盖服务条款。

## 6. Cache 与 evidence 保留边界

- 默认只缓存归一化所需最小字段、claims、response hash 和脱敏 fixture；不缓存 cookies、auth headers、用户账号、完整搜索文本或支付/订单页面。
- cache key 包含 provider/version/capability/规范化参数/业务日期/party；不得让不同用户的登录态结果互相命中。
- 动态 price/inventory cache 命中仍标 `cached` 并显示原 queried_at。
- provider raw retention/再分发是否允许必须服从条款；公开发布前完成 NOTICE/ToS 审核，未完成时 raw cache 仅限显式测试 fixtures。
- 用户粘贴的小红书文本只在当前运行内提取用户指定兴趣/POI，不进共享 fixture/cache。[依据：开放问题 Q13](../research/05-open-questions.md#q13-小红书输入的技术稳定性版权隐私与来源保留边界是什么)

## 7. Provider acceptance gate

某 provider 标 `ready` 必须同时满足：pin 匹配、probe 匹配、deadline 生效、success/empty/auth/rate-limit/timeout/wrong-shape fixtures 全通过、输出可生成合法 claims、日志/fixture secret scan 通过。缺任一项只能 `degraded/contract_mismatch`。`ready` 不表示结果一定非空或价格可购买，只表示 adapter 合同当前可用。
