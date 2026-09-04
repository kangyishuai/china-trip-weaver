# 流水线、排程与局部重排

本文件定义阶段三单向 pipeline。每阶段只消费上游合同、产生可验证输出；不允许 renderer 回填事实、scheduler 直接联网、provider 自行安排日程。一个版本化 Trip 是阶段之间和交付后的唯一事实源。[依据：研究决策 4](../research/04-design-insights.md#4-采用一个版本化-itineraryjson-是所有层的唯一事实源)

## 1. 总体状态机

```text
INTAKE
  → RESEARCHED
  → CANDIDATES_READY
  → MATRIX_READY | MATRIX_DEGRADED
  → SCHEDULED | NO_SOLUTION
  → VALIDATED
  → RENDERED
```

失败原则：provider 局部失败进入显式降级；Schema/语义/安全校验失败阻止发布；hard constraints 无解返回 `NO_SOLUTION`，不能静默删约束或生成看似完整的页面。

## 2. 阶段合同

| 阶段 | 输入 | 必做 | 输出/门禁 |
|---|---|---|---|
| P0 Intake/normalize | 用户文本；可选既有 Trip | 抽取目的地/日期/人数/预算/兴趣/locks；只对软偏好设 assumption；去除粘贴内容中的敏感字段提示 | normalized request；硬字段缺失则问用户，不发 provider query |
| P1 Research | request、query budget、用户粘贴文本 | 日期锁定的官方源/内容调研；动态生成维度；claim 级证据、冲突与 unknown | destination claims + POI/activity candidates；每个事实有 URL/time/status |
| P2 Candidates | request、research claims | 交通/住宿/POI provider queries；identity/dedupe；typed prices/health/deep links | candidate Trip（尚无最终 slots）+ complete provider health |
| P3 Route matrix | candidate Trip、requested modes | 解析 native CRS；AMap GCJ-02 真 route；为可能相邻的 endpoints 建 matrix；失败时逐 cell 降级 | matrix cells + route claims；标 `live/cached/static`，不可达也是结果 |
| P4 Schedule | candidate Trip、matrix、windows、dwell/buffer、locks | 轻量确定性排程；必要且允许时切 OR-Tools；预算/时间/移动日/餐休约束 | scheduled Trip 或 structured no-solution；不得联网 |
| P5 Validate | scheduled Trip、base revision（若 replan） | JSON Schema、cross-ref/time/matrix/evidence/price/CRS/patch/transaction checks | VALIDATED Trip + machine report；任一 error 阻断 renderer |
| P6 Render | **仅 VALIDATED Trip** | 确定性 HTML、escape、内嵌 JSON、离线核心与降级说明 | HTML + renderer validation report；不得修改 Trip |

这落实“真实 route-time matrix 先于 time windows”的顺序；Haversine/直线只可在 P2 预筛或 P3 的 `estimate` 降级，不能进入 live matrix。[依据：研究决策 13](../research/04-design-insights.md#13-采用先真实-travel-time-matrix再排-time-windows不以直线连线冒充路线)

## 3. P0–P2：需求、调研与候选

### 3.1 Intake

硬字段：destination、实际日期/范围、travelers；跨城另需 origin。缺任一项停止在 P0。pace/budget split/meal preference/walking tolerance 可用保守默认，但写 `request.assumptions`。已有 booking/accepted item 转为 `locked=true`，只有用户可解除。

交易意图在 P0 截断：保留“比较/官方深链”部分，拒绝登录、实名、下单、付款和退改。[依据：研究决策 20](../research/04-design-insights.md#20-采用查询比较深链止步交易动作永远出-scope)

### 3.2 Research

按 `city × business date × user interests` 生成 query；基线维度为官方开放/临时关闭、当期活动、季节天气、交通注意、餐饮和行前须知。最多两轮补查：第一轮填必需 claims，第二轮只补冲突/低置信度/日程硬门。固定品牌章节禁止进入 query template。[依据：研究决策 10](../research/04-design-insights.md#10-采用内容调研维度按用户城市动态生成不采用固定喜茶十大商场章节)

输出不是 prose report，而是候选实体与 claims；用户粘贴内容只能形成 `provider=user-pasted-note` 的 hypothesis/partial claim，不能提升为官方事实。

### 3.3 Candidate generation 与去重

- Rail：station resolution → direct → 必要时 bounded interline；Flight：dated exact identity；Lodging：area → property/deep link；POI：官方/内容候选 → AMap resolve。
- 去重 key：交通使用 provider service identity + endpoints + local date/time；lodging 使用 provider ID 或标准化 name/address；POI 使用 provider ID，缺 ID 才用 normalized name + city + 100m 邻近。
- 去重只合并 identity，不合并冲突事实；每个值保留自己的 claims。
- 每日最多把 12 个 POI 送入 matrix；超过时按 hard-required → evidence confidence → user-interest score → geographic prefilter 确定性裁剪，并列 excluded reasons。此上限是**实现假设**，待 benchmark 调整。
- 价格不可直接加总，除非 currency/unit/party/tax context 可比；否则预算保持区间/unknown。

## 4. P3：真实 route-time matrix

### 4.1 Matrix cell

每个有向 cell：

```text
from_ref, to_ref, travel_mode,
duration_minutes, distance_meters, fare?, geometry_ref?,
provider, provider_version, mode, queried_at,
claim_ids[], reachable, degradation_rung
```

Trip v1 不持久化完整 geometry；`geometry_ref` 只可指向允许保留的脱敏 cache，HTML 只画点位示意并给安全 deep link。OR-Tools/轻量算法只消费 duration matrix，不消费 CRS。[依据：坐标专题](../research/04-design-insights.md#必答专题-b坐标系处理)

### 4.2 查询集合

不做完整 `N² × all modes` 无界查询。对每个 day/city：

1. 所有 locked/pinned endpoints 与住宿必须互查。
2. 每个候选与同 cluster 最近的最多 5 个候选按可用 mode 查询。
3. 跨城 transport endpoint 与首/末 POI、住宿互查。
4. 排程插入遇到缺 cell 时，可在总 query budget 内按需补查一次，再冻结 matrix。

AMap query 一律使用 GCJ-02。无 Key/失败时：fresh cached cell → public/deep link → 用明确方法和上界 buffer 的 estimate → unknown/unreachable。estimate cell 令整体状态 `MATRIX_DEGRADED`，页面必须显示未实时验证；unknown cell 不能作为可行移动边。

### 4.3 Matrix 验收

- 每个最终相邻 slot hop 有一个同 mode cell，或 schedule 标出明确的 unknown gap。
- duration 为非负整数；`reachable=false` 不能同时有正常 duration。
- live/cached cell 有 claim 与 query time；estimate 有方法/置信度/静态来源。
- 不能用直线距离、顺序连线或地图 marker 成功替代 route API success。

## 5. P4：轻量排程 v1

### 5.1 约束优先级

词典序目标（前项绝不为后项让步）：

1. 所有 hard constraints、locks、transport/check-in 时刻、opening/service windows 可行。
2. 每个 hop 有 route cell，且 buffer/door-to-door time 足够。
3. 最大化 must/accepted 与高证据候选覆盖；未知/冲突事实受 penalty。
4. 满足餐休、每日活动上限、步行/体力/预算等软约束。
5. 最小化总移动时间、跨区折返和空白碎片。
6. 最大化用户兴趣得分；同分按稳定 ID 字典序，保证 deterministic。
7. replan 时最后最小化相对 base revision 的 churn；但稳定性不能覆盖安全/可行性。

### 5.2 算法

1. 按 city/date 建 day buckets；先固定跨城腿、住宿 check-in/out 和 locked slots，计算可用 gaps。
2. 对候选计算确定性 utility：hard/must、用户兴趣、证据 confidence、日期特异性、dwell、价格与 unknown penalty；不使用 LLM 自由排序作为最终分。
3. 按 utility 降序逐个做 cheapest-feasible insertion：枚举 day/gap/position，使用 matrix 增量、opening windows、dwell、buffer、餐休和 day limits 判可行。
4. 每步保留前 24 个 partial states（beam width=24，**假设**）；state key 用完整 schedule canonical JSON 排同分。
5. 对完成 state 做 bounded relocate/swap/2-opt（最多 2 轮），只接受词典序目标改善且保持硬约束。
6. 选择最优可行 state；未选候选逐个输出 `capacity/window/route/budget/low-score/unknown` 原因。
7. 无可行 state 时返回最小冲突集合近似：列出第一个冲突 lock/window/hop 与可选松绑项，绝不自动松绑。

默认单日最多安排 8 个可选 visit（locked 另计）；这是基于研究中“简单 5–8 点轻算法足够”的设计假设，不是实测阈值。[依据：研究决策 14](../research/04-design-insights.md#14-采用or-tools-作为复杂日程可选引擎不作为无条件依赖)

### 5.3 OR-Tools 切换阈值

OR-Tools 默认关闭且绝不自动安装。只有同时满足以下前置条件才可切换：

```text
feature flag CTW_ENABLE_ORTOOLS=1
AND dependency/version probe passes
AND complete live/cached matrix exists for all hard-required hops
```

前置满足后，命中任一阈值使用 OR-Tools：

- 任一 day 有 **≥9** 个 schedulable candidates；
- 任一 day 有 **≥4** 个独立 hard time windows；
- 存在 **≥2** 个跨日耦合约束；
- light scheduler 返回 no-solution，但 hard-required candidates ≤20，且需要区分算法不足与真实无解。

OR-Tools 每次 solve wall time 上限 5 秒、单日候选上限 20；超时回到 light 的最佳可行结果或 structured no-solution，不能发布部分未校验解。该阈值是 ADR 中的**暂定假设**，必须通过 Q10 的 20 个 golden benchmark 后才能称为稳定。[依据：开放问题 Q10](../research/05-open-questions.md#q10-轻量排程与-or-tools-的切换阈值是什么)

## 6. P5：发布前语义校验

依次运行；前一层 FAIL 仍可汇总后续独立错误，但最终不可渲染：

1. Trip JSON Schema。
2. ID/ref/claim/unknown/provider-health 完整性。
3. request dates、days、slot time order/no overlap、transport chronology/timezone。
4. 最终 hop matrix coverage、opening window、dwell/buffer、lock、预算口径。
5. coordinate native/derived consistency 与单次转换。
6. claim source/query time/freshness/status、price type、top mode consistency。
7. transaction boundary、URL `https` allow policy、无 credential-shaped fields。
8. replan 时 patch continuity/replay、locked/unchanged byte stability。

warnings（例如 static hours）必须在 HTML 可见；errors（missing claim、overlap、wrong CRS、silent mock、secret、transaction URL）阻断。

## 7. 局部重排合同

局部重排不是从用户原文重跑 P0–P6，而是以 `base Trip + event + locks` 进入影响分析。[依据：研究决策 15](../research/04-design-insights.md#15-采用局部重排是-versioned-patch不是重跑全计划)

### 7.1 输入与并发门

```text
base_trip_id, base_revision, event(type/time/subject/evidence),
user_locked_refs[], optional allowed_changes[], now
```

`base_revision` 必须等于当前 revision；不等即返回 `revision_conflict`，要求用最新 Trip 重试，不自动把旧 patch rebase。

### 7.2 影响范围传播

| event | 初始范围 | 扩展范围 |
|---|---|---|
| POI closure/user delete | 该 POI slot | 同 day 前后各 1 hop、受空档影响候选 |
| weather | 受影响时间/户外 slots | 同 day alternatives、相邻 hops |
| local delay | 延迟 leg/slot | 从该点到下一个 locked anchor 之间 |
| cross-city train/flight delay/cancel | 该 transport leg | 到达 day、接驳/check-in；只有跨午夜/失去住宿时才扩下一 day |
| provider claim stale/conflict | 引用该 claim 的字段 | 依赖该字段的 slot/hop/price summary |

范围外 days/refs 不进入 provider requery 或 scheduler state。

### 7.3 锁定与稳定性硬约束

- 用户 locked/accepted/booked refs、未受事件否定的跨城腿与住宿不可改变。
- 影响范围外 day 的 canonical JSON 必须字节相同；claim query time 也不能无故刷新。
- 影响范围内先保留原顺序/时间，只有不可行才最小移动；操作数、总分钟偏移、被删除 accepted 项依次受 penalty。
- 不允许为了更优评分改城市顺序、住宿或 transport，除非 event 直接使其不可行且用户明确解锁。
- stability score = preserved eligible refs / all eligible refs；只是报告指标，不能掩盖 locked violation。

### 7.4 Patch 输出

先复制 base，再只在白名单路径生成 `add/remove/replace/move` operations；执行后 revision +1。patch 必须列 `scope.day_ids/affected_refs/locked_refs`、`reverify_claim_ids`、preserved/changed refs、reason/trigger。输出 before/after 摘要和 structured no-solution（若有）。

### 7.5 必须重核验的 claims

- 被替换/移动 POI 的 opening/booking/weather claim。
- 新增或变化相邻 hop 的 route duration/fare/可达性。
- 延迟交通腿的 status/arrival 与受影响接驳/check-in。
- 日期、party 或候选变更后的任何 price/inventory。
- 超过 provider freshness TTL 且仍影响决策的 claim。

未受影响且未过期的 claims 不重查。最小 patch/stability contract 的最终阈值仍需四类 golden（下雨、闭馆、误车、删点）验证。[依据：开放问题 Q11](../research/05-open-questions.md#q11-局部重排的最小-patchstability-contract-应是什么)

## 8. Pipeline 可恢复性与确定性

- 每阶段产生带 `trip_id/revision/stage/schema_version/input_hash/provider versions` 的 checkpoint；不保存 secret/raw personal data。
- 相同 request、fixtures、policy version、matrix 与 clock fixture 必须得到 canonical-equal Trip；实时 provider 值不同不要求相同，但来源/差异可解释。
- resume 从最后一个通过门禁的 stage 开始；版本/probe/input hash 变化时只失效依赖阶段。
- renderer 失败可单独重跑；不得因此重新查 provider 或改变 generated Trip。
