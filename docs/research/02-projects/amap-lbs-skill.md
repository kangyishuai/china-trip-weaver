# amap-lbs-skill 项目解剖

## 版本锁定

- 仓库：`https://github.com/AMap-Web/amap-lbs-skill`
- commit：`cc418173bed7eaad7f40b67a46a09fce69be84eb`
- commit 时间：`2026-04-14T19:28:36+08:00`
- 克隆日期：`2026-09-03`
- 类型：OpenClaw 风格 Agent Skill + CommonJS library/CLI；调用 AMap Web Service 并生成 hosted visualization links。不是 Codex Plugin/MCP。
- Skill version `2.0.0`；npm package `amap-webservice@1.0.0`（版本不一致）。
- 许可证：MIT。

## 1. 定位与触发

`SKILL.md` description 原文：

> 高德地图综合服务，支持POI搜索、路径规划、旅游规划、周边搜索和热力图数据可视化

正文明确触发：

- 搜某类地点/确定地点：“搜美食”“找酒店”“天安门在哪”。
- 位置周边：“西直门周边美食”“北京南站附近酒店”。
- 路线：“从天安门到故宫怎么走”“规划驾车路线”。
- 旅游：“帮我规划北京一日游”“杭州西湖游览路线”。
- 热力图/地图数据可视化。
- 还把“搜/找/查/附近/周边/路线/规划”列为关键词，范围极宽，会与 `plan-china-trip`、酒店/POI/route provider Skill 抢隐式触发。

Skill 的场景 1/2/3 主要是让 Agent 拼 AMap search/heatmap URL；场景 4/5/6 才调用仓库脚本/API。它还指示每次行为前 curl `restapi.amap.com/v3/log/init?...skill.call...` 做 telemetry，代码没有统一实现该步骤，且没有用户可见 opt-out。

## 2. 输入、输出与数据结构

核心 `index.js` exports：`readConfig/saveConfig/getWebServiceKey/setWebServiceKey/ensureWebServiceKey/searchPOI/walkingRoute/drivingRoute/ridingRoute/transitRoute/generateMapLink/travelPlanner`。

### POI

`searchPOI(params)` 输入 `keywords/city/types/location/radius/page/offset/cityLimit`，向 `https://restapi.amap.com/v5/place/text` 发送 `key/keywords/region/city_limit/...params/appname`，成功时返回 AMap 原始 response（`status/count/pois[]`）。CLI 打印 `pois[].name/address/type/tel/location/distance`。

当前官方 v5 文档（抓取 2026-09-03）使用 `page_size/page_num`，而代码透传旧式 `offset/page`；这两个参数不会自动改名，分页行为存在 schema drift 风险。官方 URL：`https://lbs.amap.com/api/webservice/guide/api-advanced/newpoisearch`。

### route

- walking/driving/riding/transit 输入都是 `origin/destination` 的 `经度,纬度`；driving 另有 `waypoints/strategy`，transit 另有 `city/strategy/nightflag`。
- 返回 AMap 原始 route JSON；CLI 读取 `paths[].distance/duration/tolls/traffic_lights` 或 `transits[].duration/cost/walking_distance`。
- `generateMapLink(mapTaskData)` 把 JSON URL-encode 到 `https://a.amap.com/jsapi_demo_show/static/openclaw/travel_plan.html?data=...`。task 形状：POI `{type:'poi',lnglat:[lng,lat],sort,text,remark}`；route `{type:'route',routeType,start,end,city?,remark}`。

### `travelPlanner`

输入 `city/interests[]/routeType`。实际实现只是按 interest 顺序抓每类前 5 个 POI，并把相邻 POI 写成 route task；**没有调用** walking/driving/riding/transit API。更严重的是函数最终只 `return {pois: poiResults}`，丢弃已构建的 `mapTaskData`，也不返回 JSDoc/README 承诺的 `mapLink/htmlLink`。因此“智能旅游规划+路线+可视化”在 library output 上不成立。

### 坐标系

项目不在 schema、日志或文档中声明 `GCJ-02`，也没有 WGS-84 转换；它把 AMap `location` 原样传给 AMap hosted page，内部同一 provider 时通常一致，但一旦与 OSM/其他项目合并就没有 provenance 防线。这是后续矩阵必须补的关键缺口。

## 3. 脚本与依赖

- Node/CommonJS；唯一 dependency `axios ^1.13.6`，无 `package-lock.json`，Node version 未声明。
- `scripts/poi-search.js`、`route-planning.js`、`travel-planner.js` 用自制 `--key=value` parser。
- 所有 axios call 无 timeout、retry/backoff、HTTP status 分类；API-level `status/info` 失败返回 `null`。
- endpoint 混用 v3/v4/v5；维护时需逐一对照 AMap 当前 docs。
- `config.json` 在 `.gitignore`，但 key 以明文 JSON 放 Skill 根目录，无权限设置/secret store。

实现/文档不一致：core 同时接受 `AMAP_KEY` 与 `AMAP_WEBSERVICE_KEY`，frontmatter primary env 是 `AMAP_WEBSERVICE_KEY`；但 `scripts/poi-search.js` 预检**只接受** `AMAP_KEY`，仅设置标准变量会被提前拒绝。

## 4. 外部服务、Key、配额与费用

必须申请 AMap Web Service Key；无 Key 时 `ensureWebServiceKey()` 抛错。场景 1 的普通 search URL、场景 3 hosted heatmap link 和 telemetry 无 Key，但 API/route/nearby/travelPlanner 都需要。

当前官方口径（`https://lbs.amap.com/upgrade` 与 `https://lbs.amap.com/pages/base_service_price`，抓取 2026-09-03）：

- 非商业个人认证开发者自认证起 1 年免费月配额：基础 LBS 150,000、基础搜索 5,000；两组基础 QPS 都是 3。
- 超配额基础 LBS/基础搜索流量包均 30 元/万次，有效期 1 年；基础 LBS 大量调用有阶梯价，基础搜索暂无折扣。
- 未认证开发者当前表中对应 Web API 月配额为 0。
- 搜索相同请求翻页最多 200 条。

仓库 README 只写“免费用户每日有限制”，已落后于当前按月计费/配额口径，不能复用为产品文案。商用/授权条件仍应以控制台和服务协议为准。

凭据优先级：`AMAP_KEY || AMAP_WEBSERVICE_KEY` → 根目录 `config.json.webServiceKey` → error。Skill 文本甚至要求用户在对话里“提供 Key”，这违反目标的凭据边界；目标只能提示用户在环境/本地配置中自行设置，不能把 Key 粘到对话。

## 5. 测试现状与实测

tests：**无**。没有 test files/CI；`package.json` 自带命令实际是占位失败：

```bash
npm test
```

原始结果 exit `1`：

```text
> echo "Error: no test specified" && exit 1
Error: no test specified
```

完整输出：[`../evidence/amap-lbs-skill-tests.txt`](../evidence/amap-lbs-skill-tests.txt)。因所有实质 API 都需 Key，本研究没有安装依赖或发请求；按约束只做静态分析。

## 6. 优点、缺点与职责边界

### 优点

- POI、walking/driving/riding/transit 是中国自由行最关键的地图 provider 能力，输入/CLI 简单。
- AMap 原始 response 保留 route/POI 丰富字段；地图 hosted link 可快速人工查看。
- 明确支持周边、城市、waypoints、night bus 等实用参数。
- 官方维护 org、MIT，当前 AMap pricing/docs 可追溯。

### 缺点

- 无测试/lockfile/Node engine；npm test 明确失败。
- `travelPlanner` 不调用 route API、丢 `mapTaskData/mapLink`，与 README/JSDoc 不一致。
- v5 POI 用旧分页名，API schema 漂移风险已出现。
- 坐标完全不标 GCJ-02、无跨 provider 转换/验证。
- plaintext `config.json`、无 0600、要求 chat 提供 Key；脚本 env 名还互相冲突。
- API error 全折叠为 `null`，没有 missing/forbidden/rate_limited/expired 或 query timestamp/source metadata。
- Skill 触发极宽，并把 telemetry curl 作为每场景第零步；不应无条件照搬。
- hosted heatmap 示例还是 `http://`，data URL/位置被放到 query string，隐私与长度需评估。

### 职责边界

适合做 AMap provider adapter（POI/geocode/route）；不适合承担完整 itinerary、逐时 schedule、住宿/交通库存、HTML artifact、证据 ledger 或凭据管理。

## 7. 可搬走什么、为什么不搬

### 采用其思想

- 采用 AMap 为中国 POI/geocode/route 的主要 provider，保留 walking/transit/driving/riding 多模式与 route alternatives。
- 采用 provider 原始 response → normalized POI/route contract → visualization/action link 的分层。
- 将当前官方 quota/cost 写成运行时/文档快照，不编码成常量。

### 不搬

- 不搬 `travelPlanner` 伪 route task；必须调用真实 route API、累积 duration/cost 并校验可达。
- 不搬明文根目录 key/chat 索取/telemetry-first；目标用环境引用和 provider-specific secret boundary。
- 不搬宽泛 description；把 AMap Skill 限定为 POI/geocode/route provider，主行程由 `plan-china-trip` 编排。
- 不搬 raw AMap response 直接跨层流动；先标 `coordinate_system=GCJ-02`、source、queried_at，再按 renderer 需要转换。
- 不采用旧分页字段与无 timeout/error taxonomy 的 HTTP wrapper。

## 8. 能力矩阵证据

<a id="cap-destination-research"></a>
- 目的地调研：**部分**。按 interests 抓 POI，但无内容/开放时间/证据研究。

<a id="cap-train"></a>
- 火车：**无**。

<a id="cap-flight"></a>
- 航班：**无**。

<a id="cap-lodging"></a>
- 住宿：**部分**。可搜索“酒店” POI/周边，不查房型、日期库存或价格。

<a id="cap-poi-geocode"></a>
- POI 与地理编码：**有**。Web Service POI；geocode 在 Skill 场景指令中，core 未封装。

<a id="cap-route-validation"></a>
- 路线校验：**有**。真实 AMap walking/driving/riding/transit functions；`travelPlanner` 没真正调用它们。

<a id="cap-hourly-schedule"></a>
- 逐时排程：**无**。

<a id="cap-local-replan"></a>
- 局部重排：**无**。

<a id="cap-html"></a>
- HTML 交付：**无**。只生成 AMap hosted visualization URL，不是自包含 artifact。

<a id="cap-credentials"></a>
- 凭据管理：**部分**。env/file fallback 存在，但 plaintext、env 名冲突且要求聊天提供 Key。

<a id="cap-tests"></a>
- 测试：**无**。`npm test` 是占位失败。

<a id="cap-source-evidence"></a>
- 来源证据：**部分**。原始 AMap response 有 provider identity，但无 queried_at/fact-level evidence/health。
