# variflight-mcp 项目解剖

## 版本锁定

- 仓库：`https://github.com/variflight/variflight-mcp`
- commit：`d515d56204684b3179a75fb9cdd3f4600a0cb128`
- commit 时间：`2026-04-20T14:40:22+08:00`
- 克隆日期：`2026-09-03`
- 类型：官方 TypeScript stdio MCP Server + npm package `@variflight-ai/variflight-mcp@1.0.3`。
- 许可证：`package.json` 声明 ISC，但仓库没有 README 所链接的 `LICENSE` 文件；许可证文本缺失。

## 1. 定位与触发

`package.json` description 原文：

> Variflight MCP Server

`server.json` 更完整原文：

> VariFlight's official MCP server provides tools to query flight, weather, comfort, and fare data.

没有 Skill/自然语言总入口；MCP host 按 9 个 tool descriptions 触发（README 只把 8 个业务 tool 编号，源码另有 `getTodayDate`）：

1. `searchFlightsByDepArr`：城市或机场出发/到达 + 日期的直飞搜索。
2. `searchFlightsByNumber`：flight no + date，可选 exact dep/arr airport。
3. `getFlightTransferInfo`：城市间 connecting options。
4. `flightHappinessIndex`：准点/机型/舱位布局/座椅/餐饮/娱乐等舒适度。
5. `getRealtimeLocationByAnum`：tail number 实时位置。
6. `getTodayDate`：本机 local timezone 的今天。
7. `getFutureWeatherByAirport`：IATA airport 未来 3 天天气。
8. `searchFlightItineraries`：推荐/最低价/最短时长的自然语言总结。
9. `getFlightPriceByCities`：每航班/舱位的 raw sale prices。

这些 descriptions 已较好划清“推荐 summary vs raw prices”“城市 code vs airport code”“comfort vs fare”的触发边界，适合直接作为 provider tools，不会像宽泛 travel Skill 抢整个 itinerary 意图。

## 2. 输入、输出与数据结构

所有日期要求 `YYYY-MM-DD`，机场/城市要求大写 IATA 3-letter code，flight no 要匹配 `[A-Z0-9]{2,3}[0-9]{1,4}`。

- `searchFlightsByDepArr` 字段：`dep?`/`depcity?`、`arr?`/`arrcity?`、`date`。description 要求每侧二选一且不得混用，但 Zod schema 没有 refine，实际允许都缺或同侧同时提供。
- `searchFlightsByNumber`/`flightHappinessIndex`：`fnum/date/dep?/arr?`。
- transfer：`depcity/arrcity/depdate`。
- realtime：`anum`；weather：`airport`。
- itinerary：`depCityCode/arrCityCode/depDate`；raw price：`dep_city/arr_city/dep_date`，代码额外固定 `price_mode:'lowest'`。

`services/openalService.ts` 把所有调用统一 POST 到 `VARIFLIGHT_API_URL` 或 `https://mcp.variflight.com/api/v1/mcp/data`：

```json
{"endpoint":"flights|flight|transfer|realtimeLocation|futureAirportWeather|happiness|searchFlightItineraries|getFlightPriceByCities","params":{...}}
```

header 是 `X-VARIFLIGHT-KEY`。返回类型全部 `any`；server 把 `JSON.stringify(result,null,2)` 放在 MCP `content[].text`，无 `structuredContent`、TypeScript response interface、nullable/price currency contract、query timestamp 或 source URL。HTTP non-2xx 转 `Error: API request failed: status text` 并 `isError:true`。

## 3. 脚本与依赖

- Node/ESM；没有 `engines` 字段。
- runtime：MCP SDK `^1.8.0`、dotenv `^16.4.7`、zod `^3.24.2`；dev TypeScript/tsx；`package-lock.json` 存在。
- `npm run build` = `tsc && chmod 755 dist/index.js`；`start` = checked-in dist；stdio only。
- `server.json` 注册 MCP registry metadata 与 required secret `VARIFLIGHT_API_KEY`。
- `config.ts` 的 `server.version` 仍为 `0.0.1`，但真正 McpServer/package/server.json 都是 `1.0.3`；此字段目前未被 server 用到，仍是版本债务。
- HTTP fetch 没有 timeout、AbortController、retry/backoff、429/余额分类；remote call 挂住时 MCP tool 只能依赖宿主 timeout。

## 4. 外部服务、Key、配额与费用

- 必须 `VARIFLIGHT_API_KEY`（也兼容 `X_VARIFLIGHT_KEY`）；没有 Key 时仍可启动/list tools，但业务请求会带空 key 并失败。
- 默认 broker endpoint 可由 `VARIFLIGHT_API_URL` 覆盖。Key 直接控制余额，不能进仓库/前端。
- 当前官方首页 `https://mcp.variflight.com/`（抓取 2026-09-03）宣称国内航班覆盖 99.99%、国际约 97%、7 个 core service APIs，新用户送 **¥50 trial credits**。
- 2026-01 官方 DataWorks 文章曾写每 key 100 free calls；与当前“¥50 credits”口径不同，说明试用机制已变化。具体每 tool 扣费、有效期和余额以当前 console 为准，本仓库没有 price table。
- 当前官方 Tripmatch 文档公开的是另一服务/包 `@variflight-ai/tripmatch-mcp`，增加铁路/空铁联运与 credit pricing；不能把它的 9 tools/价格误套到本仓库 Aviation `1.0.3`。
- 无 Key 无业务降级；外层应将 401 归 missing/invalid，403 归余额/禁用，429/timeout 分类，并回退 FlyAI/公开航班链接。

## 5. 测试现状与实测

自动 tests：**无**。仓库没有 tests/CI，`package.json` 也没有 `test` script；只有 build/start/dev。由于所有业务调用需要 API Key，按任务边界只做静态分析，没有申请/猜测 Key，也没有安装依赖或启动空壳 server。

可复现静态检查：`git ls-files` 只有 14 个文件；tool 与 Zod schema 位于 `index.ts`，HTTP broker 位于 `services/openalService.ts`，registry secret 位于 `server.json`。

## 6. 优点、缺点与职责边界

### 优点

- 航班状态、连接、舒适度、实时位置、天气、价格覆盖互补，正好补 FlyAI 以“可售库存”为主的盲点。
- 每个 tool description 边界清晰，Zod 约束日期/IATA/flight no，MCP `isError` 正确标错误。
- 官方 provider、npm/lockfile/registry metadata 齐，接入成本低。
- raw price 与 natural-language recommendation 分成两个 tool，是很好的职责设计。

### 缺点

- 无 response schema/tests/CI/LICENSE 文件；结果 `any`+text JSON，难做 contract regression。
- Zod 未强制 dep/depcity 与 arr/arrcity 的 exclusive-one-of，description 不能替代 validation。
- no timeout/retry/error taxonomy；API key/余额/限流都变成 generic non-2xx。
- `getTodayDate` 用 host local timezone，不是明确 Asia/Shanghai；remote host 时相对日期可能错一天。
- README 8 tools、源码 9 tools；config version 0.0.1 vs package 1.0.3。
- 没有 booking URL、税费/行李/退改标准合同，无法单独承担可购票比较。
- API key 是硬门槛、试用/计费口径变化，必须可解释降级。

### 职责边界

负责航空数据 enrichment/flight pricing；不负责 train（本 repo）、hotel、POI/geocode、ground route、hourly itinerary、HTML 或交易。

## 7. 可搬走什么、为什么不搬

### 采用其思想

- 作为 FlyAI 的可选航班状态/准点/机型/天气/price cross-check provider，而非单点主源。
- 采用 summary tool 与 raw-price tool 分离、IATA/日期严格校验、known flight 才查 comfort/location。
- 外层缓存 tool schema，给每次结果补 provider/version/queried_at/query/currency/evidence status。

### 不搬

- 不复制 broker wrapper/`any` response；直接 pin npm MCP，做 startup/tool-list/fixture contract tests。
- 不假设 ¥50 等于固定调用次数，也不把 Tripmatch 价格套给 Aviation。
- 不把 Key 值写进 `.mcp.json`；使用 env var name 或 OAuth/secret store。
- 不让 generic error 直接进用户层；做 401/403/429/timeout/degraded 分类。
- 不让 host local date 决定中国行程日期；统一 Asia/Shanghai。

## 8. 能力矩阵证据

<a id="cap-destination-research"></a>
- 目的地调研：**无**。

<a id="cap-train"></a>
- 火车：**无**。铁路属于另一个 Tripmatch 产品，不在本 commit。

<a id="cap-flight"></a>
- 航班：**有**。状态/直达/中转/舒适/位置/天气/价格完整。

<a id="cap-lodging"></a>
- 住宿：**无**。

<a id="cap-poi-geocode"></a>
- POI 与地理编码：**无**。

<a id="cap-route-validation"></a>
- 路线校验：**部分**。能验证航空直达/中转/实时状态，不验证地面与全行程。

<a id="cap-hourly-schedule"></a>
- 逐时排程：**无**。

<a id="cap-local-replan"></a>
- 局部重排：**无**。实时状态可作为触发信号，但 server 不重排。

<a id="cap-html"></a>
- HTML 交付：**无**。

<a id="cap-credentials"></a>
- 凭据管理：**部分**。required secret env metadata 有，storage/rotation/health/fallback 无。

<a id="cap-tests"></a>
- 测试：**无**。无 tests/CI/test script。

<a id="cap-source-evidence"></a>
- 来源证据：**部分**。官方 live provider，但 response 无 source/query timestamp/schema。
