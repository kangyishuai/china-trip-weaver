# weekend-city-trip 项目解剖

## 版本锁定

- 仓库：`https://github.com/liangdabiao/weekend-city-trip`
- commit：`f8e3efb9a30350a4935b775be288e984f7c81008`
- commit 时间：`2026-07-14T01:15:53+08:00`
- 克隆日期：`2026-09-03`
- 类型：单 Agent Skill + AnySearch CLI + Python Markdown/HTML/AMap geocode/map toolchain + 示例报告；不是 Plugin/MCP server。
- 许可证：仓库无 LICENSE 文件，README/SKILL 未给许可证；复用法律条件不明。

## 1. 定位与触发

`SKILL.md` description 原文：

> Comprehensive weekend city travel investigation skill for Chinese cities. Use this skill PROACTIVELY whenever the user wants to research a city for weekend or near-future (within 1 month) travel — including 小红书 activities, 演唱会/concerts, 集市/markets, 球赛/sports matches, 博物馆/museums, 优惠门票/discount tickets, 喜茶门店/Heytea locations, 美食街/food streets, city walk routes, 5A 景区/scenic areas, and 地铁路线/subway routes. Triggers on phrases like "调研XX城市"、"XX城市周末去哪"、"周末小旅游"、"XX城市旅游攻略"、"本周末/下周末去XX"、"XX城市近期活动"、"weekend trip to [city]"、"investigate [city]"、"城市调查". Search via anysearch CLI. All judgment, extraction, and writing done by the runtime agent (you) — no external LLM API calls. Generates text-only Markdown reports (no inline images; anysearch `search` does not return thumbnailUrl). Always invoke this skill when the user mentions researching any Chinese city for short-term travel, even if they don't explicitly ask for a "skill" or "攻略".

边界：只做中国城市本周末/下周末/未来 1 个月；不适合海外、超过 1 个月的旅居/移民、单一演出深查。它要求 proactive/always invoke，和目标主 Skill 的“目的地调研”有明显隐式竞争；如果作为子能力，应改为显式内部调用或禁隐式。

固定调查 11 方向：近期/小红书活动、演唱会、集市、球赛、博物馆、优惠门票、喜茶、食品街、city walk、5A 景区、地铁/出口/商场。

## 2. 输入、输出与数据结构

### 输入与 AnySearch

核心输入：城市、具体日期/本周末/下周末/未来 30 天、可选人群偏好、`markdown|html|both`、可选地图。11 个 query template 每条 `{query,max_results}`，拆为 5+4+2 三个 `batch_search`；client 每 query 强制 `max_results<=10`。

`scripts/anysearch_cli.py` 发送 JSON-RPC `tools/call` 到 `https://api.anysearch.com/mcp`；仓库预期响应是 `result.content[].text`，文本块按 `标题/URL/摘要` 分隔。当前 AnySearch 官方 `/v1/search` 已有结构化 `data.results[].title/url/snippet/content`，但该 client 仍走 MCP text contract，存在服务演进差异。

### 报告

`references/report_template.md` 定义 10 节（实际编号 〇～十）：报告头、速览、活动、优惠、喜茶、食品街、city walk、地铁/出口/商场、周末组合路线、API 统计、引用源/时效。报告必须列调查日期/覆盖时段/API 次数/主要信源，关键事实 ≥2 来源，至少 3 类来源。

### 地点与地图

- runtime agent 从 Markdown 抽 `places.json`：`id/name/type/address/note`。
- `geocode.py` 输出 `.places.geo.json`，增加 `lat/lng/level/geocoded/geocode_status?`；坐标明确为 **GCJ-02**。
- `inject.py` 把列表注入 `templates/map_panel.html` 的 `TRIP_DATA`：`city/date_range/total/center/zoom/places`，并嵌 `AMAP_JS_KEY/AMAP_SECURITY`。
- `validate_map.py` 检查 file size、占位符、非北京 fallback center、geocoded count、NaN、中国 bbox；不检查路线耗时、开放时间或 source URL。
- 普通 HTML 由 `md_to_html.py` 生成单文件，无地图。

地图只显示分类 marker/filter/card，未调用 AMap route planning；“周末组合路线可执行性”由 Agent/quality checklist 人工判断，不是 route engine。

## 3. 脚本与依赖

- README 声称 Python 3.7+；`requirements.txt` 只有 `requests>=2.20`，无 upper bound/lock。
- `anysearch_cli.py` 有 30s timeout、HTTP/connection/timeout 分支、batch max 5；其 API key 优先级是 CLI flag > `.env` > environment > anonymous，且 `.env` 会覆盖已有环境变量。
- `geocode.py` 用标准库 urllib、8s timeout、3 retry、known coords、city match、中国 bbox；默认 `QPS_DELAY=0.15`（约 7 QPS），高于当前 AMap 个人基础 QPS 3，靠超限后自适应重试兜底。
- `md_to_html.py` 可选 `markdown+pymdown-extensions`，没有则 fallback converter；但源码 line 359 的 f-string 表达式含反斜杠，只在 Python 3.12+ 语法可用，和 3.7+ 声明冲突。
- `build_map.sh` 串 extract(由 agent 手动产 places) → geocode → inject → validate；`generate_index.py` 建报告目录索引。

## 4. 外部服务、Key、配额与费用

### AnySearch

- `ANYSEARCH_API_KEY` 推荐但 anonymous 可用；Skill 不调用外部 LLM，只用搜索 API。
- 当前官方 `https://anysearch.com/pricing`（抓取 2026-09-03）：Free `$0/mo`、1,000 requests/day、20 QPS per key；Professional 尚未开放，Enterprise 自定义。
- 官方 docs 说明 anonymous 按 IP rate-limit 并消耗 daily free quota，但未给 anonymous 精确值；authenticated 计入 key 的 quota。429 带 limit/remaining/reset；402 区分 anonymous daily、paid quota、registered user daily。
- 仓库写“预算 50”“总 API 调用 ≤15”，且把 11 query 记为 11 次，实际 transport 是 3 个 batch call；usage 计费到底按 batch 还是子 query 必须以响应/console 为准。
- `auto_registered` 可能含新账号/Key；本研究没有匿名实搜，避免自动申请/暴露凭据。

### AMap

- `AMAP_KEY`：Web Service geocode；`AMAP_JS_KEY + AMAP_SECURITY`：浏览器 JS map。两种 key 不能互换。
- 当前个人非商业 1 年月配额：基础 LBS 150,000、基础搜索 5,000、QPS 3；流量包 30 元/万次。仓库 `references/map_generation.md` 仍写“默认 3000/日”，已过时。
- JS key/security 被直接写入最终共享 HTML；仓库承认无法避免。这不符合目标“手机 HTML 可安全分享”的凭据边界，目标不能沿用。
- `VERBOSE` 会打印 AMap Key 前 8 后 4 字符，也不应带入产品日志。

## 5. 测试现状与实测

自动 tests/CI：**无**。`references/quality_check.md` 含“自动检查脚本模板”，但仓库没有对应 runnable test file；实际可运行门禁是 `validate_map.py`。

Keyless 本地实测：

1. `python3 scripts/validate_map.py example/广州地图_Anysearch版.html --verbose`：exit `0`，文件 35,493 bytes，58/58 geocoded、0 NaN、0 越界、center `(113.303,23.120)`，全部通过。
2. 系统 Python 3.9.6 解析 `md_to_html.py` 即 SyntaxError，证明 README 的 Python 3.7+ 不成立。
3. 已有 Python 3.13.12 运行相同 converter 成功，生成 `research/evidence/weekend-city-trip-report.html` 57.2KB，fallback engine，exit `0`。

完整输出：[`../evidence/weekend-city-trip-local-checks.txt`](../evidence/weekend-city-trip-local-checks.txt)。AnySearch 与 geocode/map injection 需要 Key 或可能自动发 Key，本阶段未调用。

## 6. 优点、缺点与职责边界

### 优点

- 中国城市短期活动/内容调研最细：11 方向、时效 query、信息密度阈值、补查询最多 2 轮。
- 强制 URL、API 统计、多源类别、关键事实 2 来源、过时/跨城噪声/冲突检查，证据意识强。
- runtime Agent 提取，不另调 LLM，避免二次模型成本与不透明摘要。
- AMap GCJ-02 全链一致，known coords/city match/bbox/outlier/validator 防止错城点位。
- 普通 HTML keyless 生成、地图样例 58/58 validator 实测通过。

### 缺点

- 调查方向过度固定（“喜茶”占独立章节），容易为了密度凑数，和任意用户兴趣不匹配。
- “至少两来源”主要是 checklist，没有 fact-level structured evidence/自动 URL-to-claim 校验。
- 路线可执行性人工判断；地图只打点，不做 route/time matrix。
- AnySearch client/usage 计数/官方 API contract 已出现漂移；anonymous auto-registration 有凭据风险。
- 普通 HTML converter 与声明最低 Python 不兼容；无 tests/CI/lock。
- Map HTML 把 JS key/security 嵌进共享文件并依赖在线 AMap JS/tiles，不能称完全离线或安全分享。
- `geocode.py` 默认约 7 QPS 超过当前个人 QPS 3；错误后再降速会浪费额度/触发风控。
- `.env` 覆盖进程环境变量、VERBOSE 打 key 片段，都违背最小 secret exposure。

### 职责边界

负责：中国城市 ≤1 月内内容/活动/攻略调研、Markdown/普通 HTML、可选 AMap marker panel。明确不负责：跨城交通库存、住宿实时房价、真实 route solver、长途/海外、交易。

## 7. 可搬走什么、为什么不搬

### 采用其思想

- 采用 date-locked query、source category、多源交叉、跨城噪声/过时/密度/冲突 QA 与最多 2 轮补查。
- 采用 `places → geocode → HTML → validate` 流水线与 GCJ-02 一致性/错城拒绝。
- 采用报告头记录 query budget、来源、未验证项，但升级为 claim-level evidence ledger。

### 不搬

- 不固定“喜茶/10 大商场”等品牌式章节；调查维度由用户兴趣、城市与日期动态选择。
- 不把 batch 内 query 数冒充 API request；记录 provider 返回的 usage/request_id。
- 不嵌 AMap JS security 到可分享 HTML；优先静态数据+安全 deep links，或后端代理。
- 不复用 auto-registered Key 保存机制、`.env` 覆盖 env、key 片段日志。
- 不采用人工 route checklist 代替 AMap route/time matrix；内容 route 必须经过空间与时间校验。
- 不搬无 tests/3.7 不兼容的 converter；先加 fixture/golden tests。

## 8. 能力矩阵证据

<a id="cap-destination-research"></a>
- 目的地调研：**有**。11 方向、10 节模板、多源 QA、补查闭环。

<a id="cap-train"></a>
- 火车：**无**。只调研城市地铁，不查铁路库存。

<a id="cap-flight"></a>
- 航班：**无**。

<a id="cap-lodging"></a>
- 住宿：**部分**。报告可给片区/行动信息，但无专门实时 hotel schema/provider。

<a id="cap-poi-geocode"></a>
- POI 与地理编码：**有**。places + AMap GCJ-02 + known coords/city/bbox/outlier validation。

<a id="cap-route-validation"></a>
- 路线校验：**部分**。quality checklist 和 marker spatial sanity 有，真实 AMap route/time 无。

<a id="cap-hourly-schedule"></a>
- 逐时排程：**部分**。周末组合路线含时间表，依赖 Agent 人工排冲突。

<a id="cap-local-replan"></a>
- 局部重排：**无**。

<a id="cap-html"></a>
- HTML 交付：**有**。普通单文件 + AMap panel；地图需要在线 JS 且嵌 key/security。

<a id="cap-credentials"></a>
- 凭据管理：**部分**。env/.env 有，但 auto Key、env precedence、key fragment 与 HTML secret 不合格。

<a id="cap-tests"></a>
- 测试：**部分**。无 test suite/CI；map validator 样例通过，converter 有版本兼容缺陷。

<a id="cap-source-evidence"></a>
- 来源证据：**有**。强制 URLs、两来源/三类别、API stats/引用章节；仍缺机器 claim mapping。
