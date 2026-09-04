# trippick 项目解剖

## 版本锁定

- 仓库：`https://github.com/zjgttz/trippick`
- commit：`dbdf53c19fc69a466137471c9f9eb7cfdaa0cd6e`
- commit 时间：`2026-06-10T17:02:36+08:00`
- 克隆日期：`2026-09-03`
- 类型：Next.js 14 Web 应用（App Router）+ LLM extraction/API + mobile itinerary/map/collaboration UI；不是 Skill/Plugin/MCP。
- package version：`0.1.0`，private。
- 许可证：仓库没有 LICENSE，README 未声明；复用条件不明。

## 1. 定位与触发

没有 `SKILL.md` 或可被 Codex 隐式调用的 description。产品触发方式是访问 Web app，粘贴 2–8 篇小红书笔记/分享链接，经过分析页选择 POI，再进入 itinerary。

README 一句话定位原文：

> 把你收藏的小红书旅行攻略，拼成真正能出发的行程。

第二句边界原文：

> 不是 AI 帮你从零生成行程——而是从你已经喜欢的内容里，帮你做决定。

五步 flow：多篇输入 → LLM 结构化 POI/住宿/预算/避雷 → 去重/推荐次数 → 距离/口碑/过载/前置条件冲突 → 用户 accepted/pending/rejected 后按地理排 Day。

实现有一处违背定位：`app/api/enrich/route.ts` 在候选 <6 时要求 LLM 从知识库新增 3–5 个高人气 POI，并标 `source=ai_recommended`。虽有显式来源颜色，但已不是“只从你给的笔记里组织”。

## 2. 输入、输出与数据结构

### analyze input/output

`app/api/analyze/route.ts` 请求：`notes` 2–8 篇，每篇 20–3500 字；可选 titles 与 preferences（budget/party/styles/duration）。每 IP 内存 rate limit 15 calls/hour。

`lib/schema.ts`：

- `POIItem`：`name`、`type={景点,餐厅,住宿,交通,其他}`、`source_count`、`recommended_reasons[]`、`warnings[]`、`suitable_for[]`、`estimated_budget`、`suggested_time`、`confidence_score 0..100`、`source={user_note,ai_recommended}`。
- `Conflict`：`conflict_type={distance,opinion,time_overload,prerequisite}`、`items[]/reason/suggestion`。
- `ItineraryDay`：`day` + `slots[]:{time_slot=morning|afternoon|evening,items[],note}`。
- `AnalysisResult`：destination、trip_style、items、conflicts、itinerary_suggestion、`source_titles[]`、generated_at、is_mock。

LLM JSON 经 Zod lenient preprocessing/validation，失败最多 3 retries，最终 API 返回 HTTP 200 + `should_fallback:true`，前端加载 `public/mock-result.json`。

### 决策、重排与分享

- Zustand session state：analysis、`decisions{name→accepted|pending|rejected|unset}`、partnerDecisions、`customItinerary`。
- `reorder-by-geo.ts`：day 内景点/餐厅按 Haversine 贪心最近邻重排，保留 morning 起点；住宿锁 evening，交通/无坐标项不参与；8km outlier 拆 slot；容量 base 2/2/1、dense 3/3/2。
- UI 支持 drag/drop、跨 slot/day 移动、添加自定义项、重跑 geo reorder，并可用 `html-to-image` 导出 PNG。
- 协作：本机 `BroadcastChannel`；可选 Upstash Redis `TripState{version,decisions,analysis,updated_at,last_client_id}` 30 天 TTL；URL `?trip=<id>` 即权限。

`trip_id = timestamp(base36)+4 位 Math.random(base36)`，服务端 GET/PUT 只检查长度、不鉴权/不校验 decision schema，也没有 rate limit；“URL 即凭证”便捷但熵与写权限隔离不足，不适合含私人旅行笔记的公开部署原样复用。

### 小红书输入

前端 regex parser 保留 shortLink 作为来源回链；server route 可尝试 feed API（需 xsec token）→ HTML/initial state/meta → blocked/manual copy，20s abort，不破解签名/不存 cookie pool。

## 3. 脚本与依赖

- Next 14.2.18、React 18、Zod、Zustand、Upstash Redis、Tailwind、html-to-image；`package-lock.json` 有。
- LLM：优先 `GEMINI_API_KEY`（默认 `gemini-2.5-flash`），失败/无 Gemini 后走 `OPENROUTER_API_KEY`（代码默认 Qwen 模型，而 `.env.example` 推荐 Gemini 2.5 Pro，文档再次漂移）。25s timeout，3 retries，Zod validation。
- geocode：Nominatim WGS-84 + city bbox/bounded/candidates/in-memory cache。
- map：动态加载 Leaflet 1.9.4 CDN，用 keyless AMap WMTS tile，WGS→GCJ 后画 marker/polyline。
- package scripts：dev/build/start/lint；没有 test script/CI。

Nominatim 实现违反自己的 `<1 req/s` 注释：未缓存地点按 5 个一批 `Promise.all` 并发，候选之间仅 350ms；这不符合 Nominatim public usage policy，应改为全局串行 ≤1 req/s 或使用自有 geocoder。

README 列 `AMAP_KEY/AMAP_SECRET`，当前代码实际不用：geocode 改为 Nominatim，map 使用无 key tile URL。部署说明已过时。

## 4. 外部服务、Key、配额与费用

| 服务 | Key | 用途 | 配额/费用 | 无 Key 降级 |
|---|---|---|---|---|
| Google Gemini API | `GEMINI_API_KEY`，二选一 | JSON analysis/enrich | 模型/账户相关；仓库只称 free quota 大，未锁当前数字/成本 | 若 OpenRouter 也无，mock fallback。 |
| OpenRouter | `OPENROUTER_API_KEY`，二选一 | Gemini fallback/多模型 | model/provider-dependent，仓库无成本预算 | mock fallback。 |
| Nominatim/OSM | 无 | city bbox + POI WGS geocode | public policy 约 ≤1 req/s；代码当前超速 | 坐标 null，列表仍显示。 |
| AMap keyless WMTS | 无 | 中文 tile | 仓库未给官方 quota/使用许可 | map load error，itinerary 仍显示。 |
| Xiaohongshu web/feed | 无用户 Key；分享 URL/xsec token | 抓正文 | 反爬/接口不稳定 | 引导手动复制文本。 |
| Upstash Redis/Vercel KV | `KV_REST_API_URL/TOKEN` 可选 | 跨设备 state | 仓库未记录 quota/cost | 本机 sessionStorage/BroadcastChannel；跨设备 API 503。 |

README 所称“三层降级：实时 LLM → 缓存结果 → Mock”不完全成立：没有 server-side LLM result cache；只有 sessionStorage 已有状态、geocode memory cache、Redis 协作 state。新请求在 LLM 失败时直接 mock。

## 5. 测试现状与实测

正式 test suite/CI：**无**。只有 `scripts/test-parse-xhs.mjs`，没有 assertion，打印 5 个 smoke case 后无条件 exit 0。

按自带脚本实测：

```bash
node scripts/test-parse-xhs.mjs
```

exit `0`；标准短链、xiaohongshu full URL、仅正文、普通文本、空字符串均输出预期形状/`null`。完整原始输出：[`../evidence/trippick-test-parse-xhs.txt`](../evidence/trippick-test-parse-xhs.txt)。因为无 assertions，它证明 parser 运行/样例可读，不是 regression guarantee。未安装依赖、未调用 LLM/Upstash/小红书 live API（需要 Key 或外部状态）。

## 6. 优点、缺点与职责边界

### 优点

- “用户内容 → 候选 → 明确决策 → 行程”的控制权模型，比从零 hallucinate 更符合真实规划。
- Zod schema、source_count/confidence/warnings/source、mock fallback 让 LLM 失败可控。
- WGS-84 存储、render boundary 转 GCJ-02 是 11 项中最干净的跨坐标系实现之一。
- geo reorder、slot capacity/outlier、住宿锚点、drag/drop/custom itinerary 展示了实用局部编辑模型。
- mobile-first UI、PNG export、share/partner decisions 是产品层可借鉴的交互。

### 缺点

- README 红线“只组织不创造”被 enrich AI POI 破坏；需用户明确 opt-in。
- geo reorder 是球面直线 nearest-neighbor，不考虑道路/交通模式/开放时间/停留/预约，polyline 仍是直线。
- morning/afternoon/evening 不是 hour-level schedule；estimated budget/时间来自 LLM，未实时核验。
- source_titles/source_count 不能映射某 claim 到具体 note/URL，源证据粒度不足。
- Nominatim 并发违反公共政策；keyless AMap tile 的许可/稳定性未文档化。
- mock fallback 可能让用户把示例误当自己结果，虽 UI 有标记；HTTP 200 掩盖 upstream failure。
- URL-as-credential 可猜/可写、Redis analysis 未 schema validate，涉及私人笔记。
- 无正式 tests/CI；README env/LLM/cache 描述与代码多处漂移。

### 职责边界

负责：用户提供内容的提取、聚合、选择、粗排、地图/UI/协作。明确不负责：实时 flight/train/hotel inventory、营业时间/票价事实核验、真实 route、逐时可执行 schedule、单文件 HTML artifact。

## 7. 可搬走什么、为什么不搬

### 采用其思想

- 采用 candidate decision states、用户勾选后才入计划、source=user/AI 分色、conflict banner。
- 采用 WGS canonical → provider-specific render conversion；保留 bbox/错位拒绝。
- 采用 custom itinerary/drag move/geo reorder 作为局部重排 UX，但在目标中落成 JSON patch/revision。
- 采用 schema validation、timeout/retry、explicit mock/degraded 标记。

### 不搬

- 不允许后台静默 AI enrich 用户未选内容；改为单独“建议候选”区，需用户接受后进入 plan。
- 不用 Haversine/直线代替 AMap route matrix；排序要按真实 travel time + opening windows。
- 不复制公共 Nominatim 并发、keyless tile 与弱 URL token；后端/本地 artifact 需更稳的 provider/security boundary。
- 不把 mock 200 当成功；内部状态要保留 failure reason，交付明确示例。
- 不搬 Next app 作为 Codex 手机 HTML 交付；提炼 schema/editor interaction，render 成自包含 artifact。

## 8. 能力矩阵证据

<a id="cap-destination-research"></a>
- 目的地调研：**部分**。从用户笔记抽取/聚合，少量 AI enrich；不做多源实时查证。

<a id="cap-train"></a>
- 火车：**无**。

<a id="cap-flight"></a>
- 航班：**无**。

<a id="cap-lodging"></a>
- 住宿：**部分**。POI schema 能抽“住宿”，无日期库存/价格/房型。

<a id="cap-poi-geocode"></a>
- POI 与地理编码：**有**。Nominatim WGS+bbox，render 时 WGS→GCJ；调用节流有缺陷。

<a id="cap-route-validation"></a>
- 路线校验：**部分**。geo nearest-neighbor/outlier/slot capacity，有空间 sanity；无真实 route/time。

<a id="cap-hourly-schedule"></a>
- 逐时排程：**部分**。day + morning/afternoon/evening，不到小时级。

<a id="cap-local-replan"></a>
- 局部重排：**有**。决策状态、drag/drop、跨 day/slot、自定义项、geo reorder/customItinerary。

<a id="cap-html"></a>
- HTML 交付：**部分**。mobile Web app + PNG export，不生成可交付单文件 HTML。

<a id="cap-credentials"></a>
- 凭据管理：**部分**。server env secrets/fallback 有，用户级配置/rotation/connector policy 无。

<a id="cap-tests"></a>
- 测试：**部分**。只有无 assertion 的 XHS parser smoke script。

<a id="cap-source-evidence"></a>
- 来源证据：**部分**。source_count/reasons/warnings/source_titles 有，claim→note URL/timestamp 无。
