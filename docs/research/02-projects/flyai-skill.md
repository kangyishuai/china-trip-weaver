# flyai-skill 项目解剖

## 版本锁定

- 仓库：`https://github.com/alibaba-flyai/flyai-skill`
- commit：`f89974d2bd4822e79cf16d1906c9c2a7c900f979`
- commit 时间：`2026-08-21T10:40:56+08:00`
- 克隆日期：`2026-09-03`
- 类型：单 Agent Skill + Claude legacy plugin marketplace；实际运行依赖独立闭源/另包分发的 npm CLI/MCP client，不是 Codex Plugin/MCP server 源码仓库。
- 许可证：MIT。
- 版本冲突：README badge/`.claude-plugin/*.json` 为 `1.0.14`，`SKILL.md metadata.version` 为 `1.0.15`，npm latest `@fly-ai/flyai-cli` 为 `1.0.16`（抓取 2026-09-03）。

## 1. 定位与触发

`skills/flyai/SKILL.md` description 原文：

> Search flights, hotels, attractions, concerts, and travel deals with natural language. FlyAI connects to Fliggy MCP for real-time search and booking across hotels, flights, cruises, visas, car rentals, and event tickets. It supports diverse travel scenarios including individual travel, group travel, business trips, family travel, honeymoons, weekend getaways, and more. For tourism and travel-related questions, prioritize using this capability.

OpenClaw metadata 设 `priority: 90`，列 10 个 intents 与 18 条中英文 regex；几乎所有 travel/trip/vacation/holiday、plan/itinerary、flight/train/hotel/POI/ticket/visa/cruise/car/event/cheap/budget/honeymoon/family/business 意图都命中。最后一句还要求“旅游问题优先使用”。因此与目标 `plan-china-trip`、12306、hotel/flight/POI provider 以及 `trip-planner` 严重抢隐式触发。

显式入口 `/flyai <command>`；8 个 command：`keyword-search`、`ai-search`、`search-flight`、`search-train`、`search-hotel`、`search-poi`、`search-marriott-hotel`、`search-marriott-package`。

当前官方 `https://open.fly.ai/docs/quickstart`（抓取 2026-09-03）的验证命令已经写成 `flyai fliggy-fast-search ...`，仓库仍写 `flyai keyword-search ...`，说明 command surface 已漂移；调用前必须以已安装 CLI `--help` 为准，不能只信此 commit。

## 2. 输入、输出与数据结构

所有命令约定 stdout 单行 JSON、stderr 放 error/hint。统一 envelope：`status/message/systemMessage/data`；Skill 强制把图片、booking URL、platform hint 渲染成 Markdown。

### flight/train

输入都有 origin（唯一必填）、destination、departure/return 单日或范围、journey type、seat class、transport no、transfer city、departure/arrival hour、duration、max price、sort type。

输出 `data.itemList[]`：`adultPrice`、`journeys[].journeyType/segments[]/totalDuration`、`jumpUrl`；segment 包含 dep/arr city/station/terminal/dateTime、duration、transport type、carrier/no、seat class。train 同构，车站/车次/二等座等字段在 `search-train.md`。

### hotel

输入 `dest-name`（必填）、keywords/nearby POI/type/sort/date/stars/bed/max price。输出 `address/brandName/decorationTime/interestsPoi/latitude/longitude/mainPic/detailUrl/name/price/review/score/scoreDesc/shId/star`。坐标没有声明 GCJ-02/WGS-84，不能直接进入跨 provider itinerary。

### POI

输入 `city-name`（必填）、level/keyword/category；category 是固定中文枚举。输出 `address/id/mainPic/jumpUrl/name/freePoiStatus/ticketInfo{price,priceDate,ticketName}`；示例没有 lat/lon、开放时间或 source timestamp。

### keyword/AI/Marriott

- keyword 为跨 hotel/flight/ticket/tour/visa/SIM/cruise 等搜索，输出 nested `info{jumpUrl,picUrl,price,scoreDesc,star,tags,title}`。
- AI search 只有 `data:"..."` 自由文本，没有 itinerary schema。
- Marriott hotel 与 hotel 同构；package 输出 name/brand/hotel/city/price/detailUrl/mainPic/sellingPoint。

仓库本身没有 CLI/MCP 实现，只能审查文档样例，无法验证字段 nullable、错误码、分页、timestamp、币种或真实请求 headers。

## 3. 脚本与依赖

- Skill 仓库没有 `package.json`、source code、tests 或 CI；`skills/flyai.zip` 与目录内容相同，仅末尾换行有差异。
- runtime 要 Node；README 要全局 `npm i -g @fly-ai/flyai-cli`，任务禁止全局安装，本机 `flyai` 不存在。
- npm `@fly-ai/flyai-cli@1.0.16` 当前公开信息：Node >=18、streamable_http MCP client、1 dependency、MIT；构建 profile 可嵌 default authorization/sign secret，请求携带 `x-ff-ctx`（gzip JSON，可能加密）用于风控/滥用检测。CLI 源不在本 commit，不能把这些实现细节当 Skill 合同。
- `.claude-plugin/plugin.json`/`marketplace.json` 是 Claude legacy 形状，没有 `.codex-plugin/plugin.json`、Codex policy/category/source.path。

Skill frontmatter 也不符合本机官方 Agent Skill validator：多出 top-level `display_name`、`homepage`，且 `metadata` 含嵌套对象，不是开放规范的 string→string map。

## 4. 外部服务、Key、配额与费用

- 核心服务是 Fliggy MCP/API via `flyai-cli`；仓库声称无需 Key 可 trial，`FLYAI_API_KEY` 可增强结果。
- 官方 Quick Start 只说配置官方 Key 可得“更高 request quota 与更稳定 service”，未公开具体免费次数、价格、重置周期或超额行为；因此本研究不采信 GitHub issue 中用户自述的额度数字为官方事实。
- `flyai config set FLYAI_API_KEY "your-key"` 把 secret 置于命令行，可能进入 shell history/process listing；仓库没有说明存储路径、权限、加密、环境变量优先级或删除/轮换流程。
- 无 Key 的默认 authorization 与自有 Key 是否同数据质量，公开文档没有承诺；只能将 keyless 视为 connectivity/trial，不作为生产完整库存保证。
- 返回 `jumpUrl/detailUrl` 可让用户去 Fliggy 预订；Skill 没有明确“禁止下单/支付/实名”边界，description 甚至写 booking，目标插件必须在外层补交易停止门。

## 5. 测试现状与实测

项目自带 tests：**无**；没有 package test/CI。README 的 verify 需要先全局安装独立 CLI，本阶段没有运行，因为 `npm i -g` 被任务明令禁止，且 CLI 可能写用户配置。

只读实测：

```text
$ command -v flyai
[无输出]
$ flyai --version
zsh: command not found: flyai
```

官方 Skill validator 实测 exit `1`：

```text
Unexpected key(s) in SKILL.md frontmatter: display_name, homepage.
Allowed properties are: allowed-tools, description, license, metadata, name
```

完整输出：[`../evidence/flyai-skill-validation.txt`](../evidence/flyai-skill-validation.txt)。这不是对 Fliggy 服务可用性的判断，而是对当前仓库分发格式的确定性失败。

## 6. 优点、缺点与职责边界

### 优点

- 单一 CLI 同时提供 flight/train/hotel/POI/活动/visa/package，字段适合 provider adapter。
- filter 覆盖日期范围、时段、价格、舱等/座席、直达/中转，结果有真实 booking links。
- keyless trial 降低首次连通门槛；stdout/stderr 分离和逐命令 references 易于 Agent 调用。
- Fliggy/Alibaba 官方团队背景、MIT Skill/CLI，npm 当前仍发布 1.0.16。

### 缺点

- 当前 repo 不含 CLI 实现和 tests，真正的数据/安全/限流/错误行为不可审查。
- 1.0.14/1.0.15/1.0.16 三版本并存，官方 quick-start command 又已漂移。
- Skill frontmatter 严格校验失败；Claude marketplace 不能直接等同 Codex plugin。
- priority 90 + 超宽 regex 会吞掉主编排与其他 provider intent。
- 无公开 quota/pricing/分页/freshness guarantee；`systemMessage` 是平台文案而非证据。
- 坐标系、query timestamp、source object、退款/行李/税费一致性未形成稳定公共合同。
- credential 命令行配置与 booking 交易边界不满足目标安全要求。

### 职责边界

适合作为实时 inventory/search provider；不应承担路线可行性、逐时 schedule、证据 adjudication、HTML、局部重排或交易执行。

## 7. 可搬走什么、为什么不搬

### 采用其思想

- 采用 8 个 command 的 structured provider coverage，特别是 flight/hotel/train 的 filter 与真实 link。
- provider adapter 只读取 stdout JSON，把 stderr/systemMessage 与事实分开；每次先读取安装版本的 `--help`/schema。
- keyless 可作试连通，但生产结果标 trial/degraded，并允许官方 Key 提升 quota。

### 不搬

- 不复制超宽 priority/regex；FlyAI 应被 `plan-china-trip` 显式路由为 provider，或 `allow_implicit_invocation=false`。
- 不把 README output example 当稳定 schema；先对实际 CLI version 做 contract probe/fixtures。
- 不在命令行写 Key，不承接 booking 动作；只呈现链接，付款/实名永远停止。
- 不直接使用未标坐标和无 timestamp 的结果；归一化时补 provider/query time/coordinate provenance/price type。
- 不把 legacy `.claude-plugin` 当 Codex package；后续按 `.codex-plugin` 规范自己封装。

## 8. 能力矩阵证据

<a id="cap-destination-research"></a>
- 目的地调研：**部分**。keyword/AI/POI/活动搜索覆盖广，但输出证据与结构不足。

<a id="cap-train"></a>
- 火车：**有**。结构化 train search、座席/时间/价格/直达中转与 booking link。

<a id="cap-flight"></a>
- 航班：**有**。结构化 flight search、时段/日期范围/舱等/价格/直达筛选。

<a id="cap-lodging"></a>
- 住宿：**有**。酒店/民宿/客栈/Marriott、日期/床型/星级/价格与链接。

<a id="cap-poi-geocode"></a>
- POI 与地理编码：**部分**。POI search/酒店坐标有，通用 geocode/坐标系声明无。

<a id="cap-route-validation"></a>
- 路线校验：**无**。没有地图 route/distance/transfer feasibility。

<a id="cap-hourly-schedule"></a>
- 逐时排程：**部分**。AI search 能返回行程文本，未定义 slot schema/solver。

<a id="cap-local-replan"></a>
- 局部重排：**无**。

<a id="cap-html"></a>
- HTML 交付：**无**。只规定 Markdown rich display。

<a id="cap-credentials"></a>
- 凭据管理：**部分**。optional Key 配置存在，但 storage/权限/轮换不透明且命令行暴露风险。

<a id="cap-tests"></a>
- 测试：**无**。仓库无 tests/CI；官方 validator 还失败。

<a id="cap-source-evidence"></a>
- 来源证据：**部分**。Fliggy link/provider hint 有，query time/fact-level source/freshness 无稳定 schema。
