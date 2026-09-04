# 产品范围

状态：阶段三实现基线。若本文件与后续文件冲突，以 ADR 为准并回改本文件。

## 1. 产品定义与目标用户

`china-trip-weaver` 是一个面向中国境内自由行的只读规划插件：把用户约束、目的地调研、交通/住宿/POI 候选和真实可得的路线信息归一成一个可追溯的 Trip，再产出逐时行程与手机优先单文件 HTML。它只查询、比较和给出带日期的深链，**永不登录代办、占位、下单、实名、支付或退改**。该交易边界是硬规则。[依据：研究决策 20](../research/04-design-insights.md#20-采用查询比较深链止步交易动作永远出-scope)

目标用户：

- 需要规划中国境内 2–7 天多日行程、愿意提供出发地/日期/人数/硬约束的自由行用户。
- 需要快速安排 1–2 天中国城市周末游，并关心当期活动、开放时间和移动成本的用户。
- 已在行中，遇到闭馆、天气、误点或主动删点，希望只调整受影响部分而不破坏已订项目的用户。

小红书在 MVP 中只接收用户主动粘贴的文本或摘要；不接收链接抓取，不保存原文、图片或账号信息。此收窄避免把尚未裁决的反爬、版权和隐私边界写成能力。[依据：开放问题 Q13](../research/05-open-questions.md#q13-小红书输入的技术稳定性版权隐私与来源保留边界是什么)

## 2. 必须支持的三个场景

### S1：多日跨城（2–7 天）

输入至少包含出发地、1 个以上目的城市、开始/结束日期和人数；可含预算、节奏、兴趣、交通偏好、已订交通/住宿。输出须包含城市顺序、跨城交通候选与选择理由、住宿片区/深链、逐日时段、接驳缓冲、证据与未知项。排程前必须先有 provider route-time matrix；直线距离只能预筛，不能冒充可执行路线。[依据：研究决策 13](../research/04-design-insights.md#13-采用先真实-travel-time-matrix再排-time-windows不以直线连线冒充路线)

### S2：城市周末（1–2 天）

输入至少包含城市、日期或明确周末、人数；可含兴趣、同行者、体力和已锁定活动。输出须包含与日期相关的活动/开放信息、按用户兴趣生成的内容维度、POI 候选、用餐/休息窗口、逐时日程、雨天/闭馆替代和来源。不得为凑模板固定加入品牌或“十大”章节。[依据：研究决策 10](../research/04-design-insights.md#10-采用内容调研维度按用户城市动态生成不采用固定喜茶十大商场章节)

### S3：行中异常的局部重排

输入为当前 Trip revision、异常事实（闭馆/天气/晚点/删点等）、用户锁定项和当前时间。输出必须是新 revision 与 versioned patch：列出锁定项、影响范围、实际 operations、未改部分、变更理由和需要重核验的 claims；不得静默重跑全计划。[依据：研究决策 15](../research/04-design-insights.md#15-采用局部重排是-versioned-patch不是重跑全计划)、[开放问题 Q11](../research/05-open-questions.md#q11-局部重排的最小-patchstability-contract-应是什么)

## 3. MVP 功能清单

1. 需求归一化与最少追问；缺省值必须写入 `request.assumptions`。
2. 使用宿主内置搜索做目的地调研，形成 claim 级证据；AnySearch 仅为可选 provider，默认不依赖。[依据：开放问题 Q8](../research/05-open-questions.md#q8-目的地调研应使用内置-webanysearch还是两者组合)
3. 铁路以固定版本的 `12306-mcp` 为主；航班/酒店以固定 `@fly-ai/flyai-cli@1.0.16` 为主；VariFlight 只做可选航空增强。[依据：研究决策 7](../research/04-design-insights.md#7-采用12306-mcp-为铁路主-provider不采用当前-12306-skill)、[研究决策 8](../research/04-design-insights.md#8-采用flyai-主查可售航班酒店variflight-只做航空增强)
4. AMap Web Service 有 Key 时提供 POI、地理编码和步行/公交/驾车/骑行 route；无 Key 时按统一降级阶梯交付，不启用已证伪的 `travelPlanner`。[依据：研究决策 12](../research/04-design-insights.md#12-不采用amap-lbs-skill-的-travelplanner采用其底层-poiroute-provider-角色)
5. 所有外部结果进入统一 Trip Schema；未知值为 `null`/`unknown`，并带 provider health、mode、price type 和 claim 证据，不以 0、空串或示例填充。[依据：研究决策 4](../research/04-design-insights.md#4-采用一个版本化-itineraryjson-是所有层的唯一事实源)、[研究决策 6](../research/04-design-insights.md#6-采用unknownprovider-health-与-price-type-必须进入合同)
6. 先构造 route-time matrix，再以轻量确定性算法排 time windows；OR-Tools 是默认关闭的可选引擎。[依据：研究决策 14](../research/04-design-insights.md#14-采用or-tools-作为复杂日程可选引擎不作为无条件依赖)
7. 支持 versioned patch 局部重排并保护 pinned/booked 项。
8. 只提供一个确定性手机 HTML renderer；Trip Schema 是唯一输入，核心内容离线可读，地图/图片可降级。[依据：研究决策 16](../research/04-design-insights.md#16-采用v1-只做一个-deterministic-手机-html-renderer)、[研究决策 17](../research/04-design-insights.md#17-采用只承诺核心离线可读地图图片显式降级)
9. 输出 provider/claim 状态、验证时间、价格口径、深链和显眼的交易边界说明。

## 4. 非目标

- 任何形式的预订、占位、登录代办、验证码处理、实名、支付、退款或改签。
- 海外行程、港澳台跨境规则、8 天以上长途、移民/签证顾问、团体票务和企业差旅审批。
- 抓取小红书链接、绕过反爬、保存用户账号/全文/图片。
- 保证库存、价格、准点、开放时间或天气不变；动态事实只对 `queried_at` 时刻负责。
- 多主题页面、编辑器、协作后端、账号同步、PWA/service worker、自动通知。
- 把直线距离、mock、静态区间或 deep link 包装成 live route/库存/总价。[依据：研究决策 19](../research/04-design-insights.md#19-不采用silent-mock空字段被包装成成功)
- 复制无明确许可证参考项目的实现；只复用有依据的合同思想。[依据：研究决策 23](../research/04-design-insights.md#23-不采用无明确许可证项目的代码复制)

## 5. 无 Key 端到端验收场景

### 固定输入

> 2 位成人，2026-10-16 从北京出发，上海 3 天 2 晚，2026-10-18 返回；偏好建筑、博物馆和本帮菜，节奏适中，人均地面预算 2500 元；优先高铁；没有任何 API Key；没有已订项目；小红书粘贴文本为空。

运行前清空本产品支持的 Key 环境变量和凭据文件副本，但保留普通网络；允许 `12306-mcp` 的公开查询、宿主内置搜索和 FlyAI 无 Key trial（只有 contract probe 通过才使用）。

### 必须产出

- 一个通过 `trip.schema.json` 的 Trip，`mode` 如实为 `live`、`cached` 或 `static`；绝不能是未标记 mock。
- 需求、3 个 day、至少 1 个铁路候选/腿或明确铁路 provider 失败及 dated 12306 deep link、住宿片区与 dated deep links、POI/餐饮候选、逐时 slots、预算口径、行前清单。
- 每个动态事实有 claim 级 `source_url/provider/queried_at/status/confidence`；每个价格有 `price_type`。
- 全部 provider health；降级原因与使用的 rung 可见。
- 一个手机优先单文件 HTML；断网后仍能读需求、日程、未知项、来源摘要和深链文本；文件中无 secret。
- 若铁路查询成功，班次/余票/价格只以 12306 查询时刻为准；若失败，不得伪造班次。

### 允许为 `unknown` 的字段

- FlyAI 无 Key trial 不可用时：航班实时库存/价格、酒店房型/税费/取消/实时总价。
- 无 AMap Key 时：精确 POI geocode、GCJ-02 route geometry、真实逐 hop route duration/fare；可用明确标为 `estimate` 的保守区间排程，但页面必须显示“路线未由 AMap 实时验证”。
- 官方源未给出时：未来临时闭馆、排队时长、天气和餐厅等位时长。

以下不可为 unknown：日期、人数、城市、交易边界、mode、provider health、价格类型、每条已展示事实的来源状态，以及所有 unknown 的原因。降级顺序固定为 live → fresh cached → keyless public → dated deep link/estimate → unknown。[依据：研究必答专题 C](../research/04-design-insights.md#必答专题-c无-key-时如何降级)

## 6. 阶段三产品验收口径

- 三个场景各有至少一个可复现 fixture；同一输入在固定 fixtures 下产生稳定 JSON/HTML。
- 所有硬边界由测试断言，而非只写提示词。
- 任何 provider 不可用都只能降低该能力，不得让整条 keyless baseline 崩溃。
- 本文件中的“实测能力”只来自 research 锁定证据；FlyAI trial、AMap schema、酒店粒度等仍按开放问题处理，启动时 contract probe 未通过即 degraded。[依据：开放问题 Q3](../research/05-open-questions.md#q3-fly-aiflyai-cli-的当前-commandschemakeyless-trial-到底是什么)、[开放问题 Q5](../research/05-open-questions.md#q5-amap-当前-web-api-的-v3v4v5-schemacrs-与-route-quota-能否形成稳定-adapter)
