# china-travel-assistant 项目解剖

## 版本锁定

- 仓库：`https://github.com/19Chris19/china-travel-assistant`
- commit：`c258614293535a2713e1d2311060219107327790`
- commit 时间：`2026-08-27T21:54:35+08:00`
- 克隆日期：`2026-09-03`
- 类型：Codex Plugin + 8 个 Agent Skills + Python CLI/库 + 2 个 bundled MCP 配置；项目版本 `0.2.0`。
- 许可证：MIT；外部项目关系另由 `provenance.yml`、`upstream-lock.yml` 与 `THIRD_PARTY_NOTICES.md` 记录。

## 1. 定位与触发

这是 11 项中离目标最近的完整 Codex 插件先例。manifest `plugins/china-travel-assistant/.codex-plugin/plugin.json` 的原始 description：

> Agent-invoked China travel Skill Plugin with OmniRoute exploration and exact visual itineraries.

它与拟建插件同名入口冲突：已经存在 `plan-china-trip`，Codex 官方规则是同名 Skill 不合并、可同时出现在 selector 中；若共同安装，显式 `$plan-china-trip` 与隐式 travel intent 都会发生歧义。

### 8 个 Skill、description 原文与触发短语

1. `plan-china-trip`
   - 原文：`Orchestrate the China Travel Assistant Agent Skills for domestic flights, trains, hotels, maps, transfers, OmniRoute exploration, budgets, and evidence-backed presentation. Use when the user asks to plan or compare a China trip, discover unconventional multimodal combinations, connect airports or stations, optimize cost versus time or fatigue, or turn travel constraints into an executable itinerary.`
   - 触发短语：plan/compare a China trip；unconventional multimodal；connect airports/stations；optimize cost/time/fatigue；executable itinerary。
2. `search-china-flights`
   - 原文：`Search and compare mainland-China flights, nearby airports, fares, taxes, schedules, baggage, and booking links. Use when the user asks about domestic airfare, low prices, airline or date comparisons, flight status, or multimodal flight-plus-train options.`
   - 触发短语：domestic airfare、low prices、airline/date comparison、flight status、flight-plus-train。
3. `search-china-trains`
   - 原文：`Search China Railway train schedules, seats, fares, direct routes, and transfers through the 12306 MCP. Use when the user asks for train tickets, high-speed rail, station connections, or a rail alternative; never submit a purchase or payment.`
   - 触发短语：train tickets、high-speed rail、station connections、rail alternative。
4. `plan-china-transfers`
   - 原文：`Plan China airport, railway-station, metro, bus, taxi, walking, and last-mile transfers using AMap POI and route data. Use when the user asks how to connect transport legs, compare transfer cost and time, find stations or airports, or plan urban transit.`
   - 触发短语：connect transport legs、transfer cost/time、find stations/airports、urban transit。
5. `search-china-hotels`
   - 原文：`Search and compare hotels in mainland China with FlyAI and verify room-level price, cancellation, and availability details through Ego Browser when needed. Use when the user asks for hotels, accommodation, lodging near a station or venue, or price and condition comparison.`
   - 触发短语：hotels、accommodation、lodging near station/venue、price/condition comparison。
6. `verify-travel-web`
   - 原文：`Verify dynamic travel pages using Ego Browser task spaces and the user's existing login state. Use only when API or MCP data is unavailable, login-specific prices or room inventory must be checked, or the user asks to inspect a booking page; pause for user handoff on login, captcha, real-name, or payment.`
   - 触发短语：API/MCP unavailable、login-specific price、room inventory、inspect booking page；是受限 fallback，不是通用浏览器入口。
7. `explore-china-routes`
   - 原文：`Explore and validate imaginative China domestic multimodal routes with the deterministic OmniRoute engine. Use when an Agent needs alternatives beyond conventional travel-app recommendations, including flight-train, train-flight, nearby airports, corridor hubs, split tickets, overnight routes, or explicit Standard, Pro, and Pro Max exploration.`
   - 触发短语：flight-train/train-flight、nearby airports、corridor hubs、split tickets、overnight、Standard/Pro/Pro Max。
8. `present-china-trip`
   - 原文：`Present a validated China travel itinerary as an exact, evidence-backed visual experience. Use when an Agent should turn itinerary.json into a Visualize-first route board, deterministic local HTML or SVG, or complete Markdown without changing times, prices, train or flight numbers, risk labels, evidence, or booking links.`
   - 触发短语：validated itinerary、itinerary.json、Visualize、HTML/SVG/Markdown、exact presentation。

真实文件：`plugins/china-travel-assistant/skills/*/SKILL.md`；集合与 metadata 完整性由 `tests/test_skills.py` 检查。

## 2. 输入、输出与数据结构

公共类型集中在 `plugins/china-travel-assistant/src/china_travel_assistant/contracts.py`：

- `TravelRequest`：`origin`、`destination`、`date_start/date_end`、`travelers`、`budget_cny`、`luggage`、`time_preference`、`fatigue_preference`、`exploration_tier`、`risk_tolerance`、`student_fare`、`allow_overnight`、`arrival_deadline`、`direct_only`。
- `TravelOffer`：`provider/mode/carrier/service_number`、端点与时间、`base_price_cny/taxes_cny/total_price_cny`、时长/换乘、行李/退改、`booking_url`、`queried_at`、`price_type`、`sources`。
- `TransferLeg`：端点、mode、`distance_meters`、`duration_minutes`、`cost_cny`、`transfers`、显式 `buffer_minutes`、source/query time。
- `ItineraryLeg`：`leg_id`、mode、端点/provider/service、时间、总价/时长/buffer、自助换乘、booking URL、`evidence_status`、sources。
- `ItineraryCandidate`：`itinerary_id/title/tier/legs`、baseline、总价/总时长/换乘、risk/evidence、收益/负担/延误兜底、`unknown_fields`。
- enums：`ProviderHealth={ready,missing,expired,forbidden,rate_limited,degraded}`、`ExplorationTier={auto,standard,pro,pro_max}`、`EvidenceStatus={verified,partial,hypothesis}`、`PresentationMode={auto,visualize,html,svg,markdown}`。

`omniroute.py::plan_trip()` 输出顶层字段 `request`、`resolved_tier`、`policy`、`search_plan`、`itineraries`。`plan-china-trip` 把它称为 `itinerary.json` 单一事实源，`presentation.py` 再确定性生成 HTML/SVG/Markdown；`render_html()` 对文本/URL 做 escape 与 scheme 校验，不加载远程脚本/字体。

AMap POI 归一化位于 `amap.py::_normalize_poi()`，字段是 `id/name/address/longitude/latitude/coordinate_system/source`，并把坐标明确标成 `GCJ-02`。项目不提供 WGS-84→GCJ-02 转换。

CLI 位于 `cli.py`，命令：`doctor`、`normalize-request`、`rank-offers`、`provider-plan`、`amap-search`、`amap-route`、`flyai`、`plan`、`render-plan`；输入主要是参数或 stdin JSON，输出 JSON 或 HTML/SVG/Markdown。

## 3. 脚本与依赖

- Python：`>=3.10`，核心包声明 `dependencies=[]`；entry point `travel-assistant = china_travel_assistant.cli:main`。
- bundled MCP：`.mcp.json` 通过 `scripts/run-with-credentials.sh` 启动固定 commit 的 `mcp-server-12306`（`uvx`）和 `@variflight-ai/variflight-mcp@1.0.3`（`npx`）。
- FlyAI：CLI 固定 `@fly-ai/flyai-cli@1.0.16`，不是 Codex MCP。
- 浏览器：要求外部 Ego Browser，且只有 `verify-travel-web` 能调用。
- 安装器 `scripts/install-local.sh` 需要 `codex/python3/npm/uvx/ego-browser/pipx`，会安装 Python CLI、用户级 FlyAI、创建 credentials，并执行 `codex plugin marketplace add`/`codex plugin add`；本研究未运行，以免改 `~/.codex`/`~/.agents`。
- 辅助：`scripts/setup-credentials.sh` 创建本机 `0600` 凭据文件；`skills/plan-china-trip/scripts/validate_plan.py` 校验 plan JSON。

## 4. 外部服务、Key、配额与费用

来源为 commit 内 `plugins/china-travel-assistant/references/credentials.md`（最后核验 2026-08-27）；配额是该 commit 快照，不替代当前控制台：

| 服务 | Key | 项目用途 | 仓库记录的配额/费用 | 无 Key 降级 |
|---|---|---|---|---|
| AMap Web Service | `AMAP_WEBSERVICE_KEY` 必需于 POI/接驳 | POI、步行/公交/驾车/出租 | 个人非商业自认证起 1 年；基础 LBS 150,000/月、基础搜索 5,000/月、QPS 3 | provider `missing`；地图腿保持部分/未知，不用浏览器伪造 API。 |
| AMap JS API | `AMAP_JSAPI_KEY` + `AMAP_SECURITY_CODE` 可选 | 未来交互地图 | 随账户/应用类型 | v0.2 HTML/SVG 不需要。 |
| FlyAI | `FLYAI_API_KEY` 增强可选 | 航班、酒店、预订链接 | 公开页无统一赠送额度/价格承诺 | CLI 是否给公共结果以实际响应为准；失败标 partial。 |
| Variflight | `VARIFLIGHT_API_KEY` 可选 | 航班状态/准点率/价格交叉证据 | 仓库称新用户 ¥50 试用；有效期/接口看控制台 | 不作为核心单点依赖，跳过 enrichment。 |
| 12306 MCP | 无查询 Key | 车次、余票、票价 | 公共查询无 API Key | 需要 MCP runtime；不存在则 `missing/degraded`。 |
| Ego Browser | 无本项目 Key | 登录态页面核验 | 独立运行时 | 不可用则不做登录价/page evidence。 |
| Visualize | 无本项目 Key | 对话内 route board | 取决于账号/平台 | HTML → SVG → Markdown。 |

真实值优先级是进程环境变量 > `~/.config/china-travel-assistant/credentials.env` > 未配置；Key 不进命令行、URL、日志、HTML 或 Git。

## 5. 测试现状与实测

自带测试 13 个文件，CI 同时覆盖 Python 3.10/3.13，并另跑 `compileall`、Ruff、wheel、gitleaks。按 README 原命令实测：

```bash
PYTHONPATH=plugins/china-travel-assistant/src \
  python3 -m unittest discover -s tests -v
```

结果：exit `0`，`Ran 103 tests in 0.328s`，`OK`。完整逐项原始输出：[`../evidence/china-travel-assistant-tests.txt`](../evidence/china-travel-assistant-tests.txt)。测试使用 mock/fake transport，没有发付费或需 Key 的请求；因此它证明 contracts、route/pruning、render、security/packaging，不证明 2026-09-03 的真实库存/价格或外部 MCP 可用性。

## 6. 优点、缺点与职责边界

### 优点

- 当前 Codex plugin/package 形状完整，能直接证明 marketplace、manifest、Skill metadata、MCP wrapper 如何组合。
- 供应商查询、确定性规划、事实展示三层分离；typed contracts、unknown=`null`、evidence/provider health 降低幻觉。
- OmniRoute 保留稳妥 baseline，再对 Pro/Pro Max 做硬约束、换乘缓冲、风险与未知费用校验。
- 明确 GCJ-02、transaction confirmation、browser fallback、Key 边界；HTML escape 和无远程脚本适合本地交付。
- 103 个 keyless 单元/集成式测试是 11 项中测试证据最强的一档。

### 缺点

- FlyAI、12306、Variflight 仍是外部进程/服务；仓库内只有 AMap 客户端与 orchestration，离线测试不覆盖真实 schema 漂移、库存和费用。
- HTML 是“联程 route board”，不是包含逐日内容、住宿片区、POI 开放时间与逐时日程的完整手机旅行页。
- `ItineraryLeg` 时间轴可组合，但没有持久 plan revision、局部 diff/patch 或天气/闭馆触发的 day-level 重排模型。
- 坐标只声明 AMap `GCJ-02`，没有输入坐标 provenance、WGS-84 转换或混用自动拒绝。
- 安装器依赖较多且会修改用户级工具和 Codex 配置；不适合本阶段复用。
- credentials 文档内额度会随时间过期；必须运行时/控制台再核验。

### 职责边界

负责：国内交通/住宿/接驳查询编排、候选联程组合与校验、证据状态、确定性 route presentation。明确不负责：从零目的地内容调研、真实预订/实名/付款/退改、保证库存、完整逐日内容编辑器、WGS/GCJ 转换。

## 7. 可搬走什么、为什么不搬

### 采用其思想

- 采用 `plan-*` orchestration + provider Skills + deterministic planner + presenter 的职责分层。
- 采用 `TravelRequest/Offer/Leg/Candidate` 一类稳定中间合同，但后续要扩充 POI visit、opening-hours evidence、lodging、day revision 与坐标 provenance。
- 采用 unknown 不补值、source + query time、provider health、baseline/alternative、transaction boundary。
- 采用自包含 HTML 的事实 escape、URL 白名单和 Visualize 不可用时本地 fallback。
- 采用凭据环境变量引用与 provider-specific 注入，不把 Key 传给无关进程。

### 不直接搬代码/配置

- 本阶段禁止写产品代码；即使后续复用，也应先从合同/测试设计迁移，避免把 v0.2 外部依赖、路径和固定版本原样绑定。
- 不搬 `install-local.sh` 的全套用户级安装与 `codex plugin add` 副作用。
- 不搬 Ego Browser-only 的排他策略；目标应按宿主可用性选择受控浏览/搜索，且页面验证不能变成主数据源。
- 不把作者的配额快照当产品常量。
- 不通过重命名规避冲突后同时装两个 `plan-china-trip`；目标名已由需求固定，兼容/迁移策略需后续裁决。

## 8. 能力矩阵证据

<a id="cap-destination-research"></a>
- 目的地调研：**部分**。能编排交通、酒店、POI，但没有多源目的地内容研究 pipeline。

<a id="cap-train"></a>
- 火车：**有**。`search-china-trains` + pinned 12306 MCP。

<a id="cap-flight"></a>
- 航班：**有**。FlyAI 主查、Variflight 按需增强。

<a id="cap-lodging"></a>
- 住宿：**有**。`search-china-hotels` 处理酒店/房型/价格/取消条件，真实结果依赖 FlyAI/Ego。

<a id="cap-poi-geocode"></a>
- POI 与地理编码：**有**。AMap POI 归一化，输出 GCJ-02。

<a id="cap-route-validation"></a>
- 路线校验：**有**。`omniroute.py` 校验连通性、时间序、buffer、自助换乘、风险与 unknown。

<a id="cap-hourly-schedule"></a>
- 逐时排程：**部分**。交通腿含精确时间/时长，但没有 POI 日程与开放时段排程器。

<a id="cap-local-replan"></a>
- 局部重排：**部分**。可用新 legs 重跑 deterministic composition，但无局部 patch/revision 模型。

<a id="cap-html"></a>
- HTML 交付：**有**。确定性、自包含、响应式 route board，并有 SVG/Markdown fallback。

<a id="cap-credentials"></a>
- 凭据管理：**有**。0600 文件、环境覆盖、provider-specific 注入、doctor 状态分类。

<a id="cap-tests"></a>
- 测试：**有**。103 tests 实测通过，另有 CI lint/wheel/secret scan。

<a id="cap-source-evidence"></a>
- 来源证据：**有**。source/query time/evidence status/unknown 字段进入公共合同与展示。
