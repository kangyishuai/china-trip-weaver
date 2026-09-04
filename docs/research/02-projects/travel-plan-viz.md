# travel-plan-viz 项目解剖

## 版本锁定

- 仓库：`https://github.com/zexuanw958-svg/travel-plan-viz`
- commit：`07d0155080f72607a6f0a74e063bd05c850dcf01`
- commit 时间：`2026-07-15T13:16:15+08:00`
- 克隆日期：`2026-09-03`
- 类型：跨 Agent 单 Skill + 纯 JavaScript 页面/地图/提醒/校验引擎 + 静态 HTML 样例；不是 Codex Plugin、MCP 或后端应用。
- 许可证：MIT。

## 1. 定位与触发

`travel-plan-viz/SKILL.md` 的 description 原文：

> 把旅行行程做成美观、离线可读、手机优先的单文件 HTML（交互地图+每日时间轴+出发前订票提醒）。两种用法——只给目的地和天数让它帮你规划，或丢一份现成计划让它直接出页面。触发：旅行计划可视化、做旅行攻略网页、行程 HTML、travel plan visualization。

触发有两层：

- 明确关键词：`旅行计划可视化`、`做旅行攻略网页`、`行程 HTML`、`travel plan visualization`。
- 隐含模式 A：只给“目的地 + 天数”也会启动从零规划；这与目标 `plan-china-trip` 的广义旅行规划 description 可能抢隐式触发，即使 Skill 名不重名。
- 模式 B：已有文字/旧 HTML；若旧文件含 `<script id="trip-data" type="application/json">`，直接读 JSON 而不是反解析 DOM。

职责表述很清楚：设计只管呈现，`trip` 是数据源，机械逻辑由 `assets/map.js`、`assets/reminders.js`、`assets/validate.js` 负责。

## 2. 输入、输出与数据结构

权威合同是 `travel-plan-viz/assets/page-contract.md`。顶层 `trip`：

- identity：`title`、`startDate`、`colorScheme`。
- `preTrip`：`weather.summary/typhoon`、`packing`、`payment`、`apps[]`、`ticketTip`。
- `flights`：`booked[]`、`candidates[]`；候选字段 `label/code/time/note/actionLink?`。
- `hotelAreas[]`：`area/reason/options[]`；option 为 `tier/name/priceRange/note/actionLink?`。
- `disclaimer`、`dataSources[]:{name,scope,realtime}`、全程 `tips[]`、`reminders[]:{item,leadDays}`。
- `days[]`：`date/weekday/theme?/tips?/alternatives?/slots[]/dining[]`。
- `slots[]`：`period/name/time/lat/lng/photo/rating/review/openingHours?/closedDays?/ticketPrice?/transport?/seasonal?/needsBooking/leadDays`；`transport` 为 `mode/fare/duration/actionLink?`。
- `dining[]`：`meal/place/hours/dishes[]:{name,price}`。

完整 `trip` 必须原样放进 `<script id="trip-data" type="application/json">`。输出文件名约定 `<行程名>-旅行计划.html`，单文件、手机优先；文字和内嵌数据离线可读，但 Leaflet 瓦片和远程图片需要网络。

机械函数：

- `map.js`：`buildNavLink`、`buildMapAppLinks`、`routeCoordinates`、`gcj02ToWgs84`、`initTravelMap`。
- `reminders.js`：`computeReminders` 从 `startDate - leadDays` 算 deadline，另有 checklist/badge HTML。
- `validate.js`：`validateTrip/validateHTML/extractTripData/validateAll`；检查日期、免责声明、days/slots、坐标范围/离群、booking leadDays、引擎/Leaflet/响应式/trip-data 标记。

坐标合同非常明确：`trip.days[].slots[].lat/lng` 一律 WGS-84；高德/腾讯返回 GCJ-02，必须先调用 `gcj02ToWgs84(lat,lng)`。OSM/WGS 地图点位与境内 GCJ 数据的错位因此被显式处理并有单测。

## 3. 脚本与依赖

- 没有 `package.json`、lockfile 或 Python 依赖；引擎是 CommonJS/浏览器双用的纯 JS，测试只需要 Node（本机 v24）。
- HTML 运行时通过 CDN 引入 Leaflet CSS/JS，默认读取 OpenStreetMap 瓦片；图片通常是远程 URL。
- 设计软依赖 `frontend-design` 或 `huashu-design`，都没有则读 `references/design-guidelines.md`。
- 旅行数据软依赖用户已装的 FlyAI、高德、腾讯地图、滴滴等 Skill/MCP；都没有则用宿主的联网搜索/抓取做静态调研。
- HTML 校验命令：`node travel-plan-viz/assets/validate.js <生成的.html>`。

## 4. 外部服务、Key、配额与费用

核心引擎自身不读取任何 Key，也不直连实时票价 API：

| 服务 | Key | 用途 | 配额/费用记录 | 无 Key/无服务降级 |
|---|---|---|---|---|
| 宿主 web search/fetch | 取决于宿主 | 目的地、开放时间、天气、餐饮、票价区间等静态调研 | 仓库无统一额度/价格 | 资料不足就保守标参考/待核验。 |
| AMap/Tencent Skill/MCP | 高德明确需用户 Web Service Key；腾讯未在仓库给具体变量 | 精确地理编码、route、POI、weather/actionLink | 只说“以官方实时文档为准” | 静态查坐标/交通；缺 actionLink 不渲染。 |
| FlyAI | 仓库说明需 API Key | 航班/酒店/门票实时结果与官方链接 | 体验版数据有缺；未写固定额度/价格 | 本 Skill 只给 3–5 个静态待选班次和酒店片区/价位，不声称实时。 |
| 滴滴 | 外部 Skill，认证细节未定义 | 打车/估价/跟踪/唤端链接 | 标为 Beta，无费用快照 | 不出现叫车 actionLink。 |
| Leaflet CDN + OSM tiles | 无 Key | 交互地图 | 仓库未给 quota/cost；需联网 | 文字仍离线可读，地图应优雅降级。 |
| Wikimedia Commons 等图片 | 无 Key | 景点图 | 仓库未给 quota/cost | 图片 `onerror` 隐藏，显示主题色底。 |

项目对第三方实时数据只做适配、不背书；`dataSources` 只是来源名/scope/realtime 的页面说明，不含逐字段 URL、抓取时间或许可证。

## 5. 测试现状与实测

仓库自带 `test/map.test.js`、`reminders.test.js`、`validate.test.js`，README/CLAUDE 指定：

```bash
node --test test/*.test.js
```

实测 exit `0`：`tests 21`、`pass 21`、`fail 0`、`duration_ms 33.12025`。逐项原始输出：[`../evidence/travel-plan-viz-tests.txt`](../evidence/travel-plan-viz-tests.txt)。

覆盖纯函数：导航/地图链接、路线坐标、GCJ-02→WGS-84、提醒日期/escape、trip/HTML 合同与离群检测。明确不覆盖 `initTravelMap` 的浏览器+Leaflet 行为、Agent 的调研质量、HTML 视觉生成与四个 `samples/` 的当前合同（维护文档称旧样例早于 `trip-data` 约定）。

## 6. 优点、缺点与职责边界

### 优点

- `trip` 单一数据源 + 内嵌 JSON 解决“交付后继续改”最容易丢字段的问题。
- 手机/桌面响应式、行前清单、每日时间轴、酒店片区、航班候选、餐饮、免责声明，交付合同比多数纯 prompt 完整。
- 首个明确实现 GCJ-02→WGS-84 的参考项目，并有天安门与境外不转换单测。
- 可选 provider 适配与内置静态降级使 core keyless；actionLink 不存在就不伪造。
- validator 把字段、坐标和必要页面标记变成可复现门禁，21 项测试实际通过。

### 缺点

- 从零规划、开放时间/价格核验、时段合理性主要依赖 Agent 指令；没有 deterministic scheduler、旅行时间矩阵或冲突求解。
- 地图的虚线只是按 slot 顺序连点，不是 provider route；validator 只检查坐标/离群，不证明两点之间路线可行。
- `dataSources` 粒度粗，没有 fact-level URL、query timestamp、confidence；“两信源”也没有机器合同。
- 核心声称“离线可读”是准确的，但地图瓦片、Leaflet CDN、远程图片都非离线；不能包装成完全离线应用。
- 真实 flight/hotel/train 能力完全取决于外部已装 Skill；自身不查实时票价，也没有 credentials/provider health。
- 单元测试没有浏览器快照/视觉回归；旧 samples 与新 validator 合同不同，样例不能直接当验收 fixture。
- 局部修改是“让 Agent 改 JSON 后重渲染”的流程约定，不是可验证 patch/revision 算法。

### 职责边界

负责：目的地静态调研指导、结构化 `trip`、手机单文件 HTML、点位地图、提醒与机械合同校验。明确不负责：实时票价、订票、后端、多语言 UI、真实 route solver、第三方数据真实性。

## 7. 可搬走什么、为什么不搬

### 采用其思想

- 采用一个可版本化的 itinerary JSON 作为规划、HTML、后续修改共同事实源。
- 采用 WGS-84 canonical storage + 明示 provider coordinate system + 转换测试。
- 采用 phone-first 自包含页面合同、图片/地图离线降级、HTML escape、显著免责声明。
- 采用 deadline reminder、slot/transport/actionLink/dataSources 等字段，但 source 要升级为逐事实证据对象。
- 采用生成后 validator；新增时间重叠、开放时段、route duration、source freshness、HTML 可访问性门禁。

### 不直接搬代码/规则

- 不直接复制以 Agent 自由生成完整页面的做法；目标需要 deterministic renderer 或严格模板，避免每次输出结构漂移。
- 不把 Leaflet/OSM CDN 当“全离线”，也不把直线连点当 route validation。
- 不采用“官方 Skill 的真实性由对方负责，所以本 Skill 不复核”的绝对免责；目标仍应保存原始响应、查询时间并做跨字段一致性检查。
- 不搬固定的提前天数经验值为真理；应把它们标成策略默认，并允许实时票务规则覆盖。
- 不让宽泛的“目的地+天数” description 与主编排 Skill 同时隐式竞争；可作为 presenter 子 Skill 或禁隐式调用。

## 8. 能力矩阵证据

<a id="cap-destination-research"></a>
- 目的地调研：**有**。Mode A + `research-guide.md` 覆盖天气、开放时间、餐饮、活动、交通与住宿片区，但主要由 Agent 搜索完成。

<a id="cap-train"></a>
- 火车：**部分**。有高铁 reminder/静态交通内容，可适配外部旅行 Skill；自身无 12306 查询。

<a id="cap-flight"></a>
- 航班：**部分**。结构支持 booked/candidates 与 FlyAI actionLink，自身不查实时价。

<a id="cap-lodging"></a>
- 住宿：**部分**。完整酒店片区/价位结构，但数据是静态调研或外部 Skill。

<a id="cap-poi-geocode"></a>
- POI 与地理编码：**部分**。slot 有坐标/POI 内容，支持外部 geocoder 与 GCJ→WGS；自身无 geocoder。

<a id="cap-route-validation"></a>
- 路线校验：**部分**。坐标范围/离群与顺序可验，未验证 provider route、耗时和接驳可达性。

<a id="cap-hourly-schedule"></a>
- 逐时排程：**有**。days/slots/time/period/transport/openingHours 合同完整，但合理性依赖 Agent。

<a id="cap-local-replan"></a>
- 局部重排：**有**。旧 HTML 内嵌 `trip-data` 可直接修改并重渲染；没有算法化 diff。

<a id="cap-html"></a>
- HTML 交付：**有**。核心能力就是 phone-first 单文件 HTML + map/reminder/validator。

<a id="cap-credentials"></a>
- 凭据管理：**无**。只消费外部已安装 Skill/MCP，不管理 Key。

<a id="cap-tests"></a>
- 测试：**有**。21 个 Node tests 实测全通过；浏览器/视觉仍未自动测。

<a id="cap-source-evidence"></a>
- 来源证据：**部分**。有 `dataSources`、actionLink 与免责声明，但没有 fact-level URL/timestamp。
