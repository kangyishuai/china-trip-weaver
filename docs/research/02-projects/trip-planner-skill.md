# trip-planner-skill 项目解剖

## 版本锁定

- 仓库：`https://github.com/skywain/trip-planner-skill`
- commit：`624196a743327d310e07a7888ebe60f406716525`
- commit 时间：`2026-09-03T01:11:48+08:00`
- 克隆日期：`2026-09-03`
- 类型：开放 Agent Skill + Python keyless 规划/地理/渲染工具链 + 8 套主题 HTML renderer + 静态素材库；不是 Codex Plugin 或 MCP。
- 许可证：MIT；字体/图标另有 `THIRD-PARTY-NOTICES.md`。

## 1. 定位与触发

`SKILL.md` frontmatter name 是 `trip-planner`。description 原文（YAML folded 后为一段）：

> End-to-end international trip planning: turns "I want to go to X for N days" into a verified, bookable plan — route skeleton across cities, flight price scans (international + domestic legs), train-vs-fly decisions, hour-by-hour daily timelines with opening hours, dwell times, holiday collisions and tappable turn-by-turn map links (小时级行程+地图导航+离线KML), hotel shortlists by neighborhood, budget rollup, and a booking checklist with deep links. Use this whenever the user asks to plan a trip, vacation, itinerary or honeymoon, compare flight dates/prices, pick between cities or routes, schedule a travel day hour by hour, fill a spare block of time ("I'm near X with 2 free hours"), turn a finished plan into a designed page (eight themed renders: illustrated / clay / noir / glass / journal / zine / splash / portal — 插画/黏土/夜航/玻璃/手账/Zine/闪屏/穿越版), or asks 旅行规划/行程安排/机票比价/去某国玩N天怎么安排/现在有空档干嘛/把行程做成好看的网页 — even if they only mention one piece (just flights, just hotels, or just navigation), the playbook and verification rules here still apply.

触发面极宽：trip/vacation/itinerary/honeymoon、flight price、city/route selection、hour-by-hour day、2-hour gap、HTML theme，以及中文“旅行规划/行程安排/机票比价/去某国玩 N 天/现在有空档/好看的网页”；甚至只提 flights/hotels/navigation 也声明应用全套规则。与目标 `plan-china-trip`、`travel-plan-viz`、flight/hotel provider Skills 共装时会抢隐式触发，适合做显式主编排入口或关闭隐式调用，不适合安静地充当 renderer。

四个运行模式：full pipeline；single day；gap filler；live replan。全程最多两个通常交互点（缺核心输入时 intake、route skeleton 选择），headless 可假设并继续。

## 2. 输入、输出与数据结构

权威样例 `assets/plan.example.json`（注释称 `plan.geo.json`）顶层：

- `trip/lang/tz/prefs/meta`：标题、`zh|en`、IANA zone、theme/pictures/travel_style/lodging/scenery/pace/budget/assumption notes、日期/人数/route/FX/generated/self-check。
- `decisions[]`：Agent 代用户做且可否决的选择。
- `checklist[]`：`item/deadline/price/link/note`，后续也生成 `.ics` gates。
- `legs[]`：`type/date/carrier/from/to/dep/arr/price/bags/link/backup`。
- `days[]`：`date/tz/city/label/sun/walking_km/ribbon/day_map/rain_alt/late_cut/travel_day/timeline[]/stops[]/sun_stop?`。
- `timeline[]`：`t/what/kind/price/note/tag/verify/link/map?`；`tag` 区分 `pinned/opener/skippable/swap→X`，支持局部重排。
- `stops[]`：`name/query/lat/lon/mode?`，按访问顺序；进入 stop 的 mode vocabulary 为 `walk/transit/fly/drive/boat/train/bus`。
- `hotels[]`：base/area/why/options；`budget[]`；`brief`（visa/holidays/weather/money/connectivity）；`unverified[]`。

`plan.geo.json` 同时喂给：

- `scripts/route_tools.py`：`geocode/check/links/kml/sun`，可回写坐标、链接、sun 和 KML。
- `scripts/render_plan.py`：朴素 HTML。
- `themes/render_*.py`：illustrated/clay/noir/glass/journal/zine/splash/portal 主题 HTML；`<plan>.art.json` 是图片/标题/caption sidecar。
- Phase 6：还可输出 booking gates `.ics`、离线 KML、budget/checklist 与最终 designed page。

HTML 是单文件、资源 data URI 内联；portal 是唯一需要视频 sidecar 的主题。实际生成的 keyless 样例见 `research/evidence/trip-planner-skill/`。

## 3. 脚本与依赖

- 主工具均 Python 3.9+ standard library：`render_plan.py`、`route_tools.py`、8 个 renderer、`qc.py`、stock art。
- `flight_scan.py` 可选安装 `fast-flights`；无依赖时打印 Google Flights deep link 并继续。
- 图片处理可选 Pillow；没有 Pillow 仍可用已带素材渲染。
- `gen.py/genvideo.py` 可选 OpenRouter API；原生 image/video generation 优先；两者都无则 illustrated 的 stock kit 完整、clay 可用，另外 6 个主题缺专属图。
- `xprobe.sh/xt.sh` 依赖 macOS + Chrome 做 export/screenshot probe；`qc.py` 本身 keyless/offline。
- 仓库无 `pyproject.toml`、`requirements.txt`、`package.json` 或 lockfile，依赖版本未集中锁定。

核心命令：

```text
python3 scripts/flight_scan.py ...
python3 scripts/route_tools.py geocode|check|links|kml|sun plan.geo.json
python3 scripts/render_plan.py plan.geo.json -o trip.html
python3 themes/render_<theme>.py plan.geo.json -o trip-<theme>.html
python3 themes/qc.py trip-<theme>.html
```

## 4. 外部服务、Key、配额与费用

默认路径不要求 Key；`references/data-sources.md` 的顺序是 bundled script/keyless API → browser → web search → 标 `verify on click` 的 deep link。

| 服务 | Key | 用途 | 配额/费用/风险 | 无 Key 降级 |
|---|---|---|---|---|
| Google Flights via `fast-flights` | 无 | 日期/晚数 grid 价格扫描 | Google cache，只适合比较；脚本限默认 12 fetch、每组合约 5–10s，重复调用可能 throttling/bot wall | 打印 deep link，标 price unverified。 |
| Hotels/OTA | 通常登录/浏览器 | 日期化酒店价格 | 项目明确“没有好的 keyless hotel API”；需看 checkout all-in | 给片区、2–3 个物业与 dated deep links，不编造 nightly rate。 |
| Nominatim/OSM | 无 | venue geocode | 强制 User-Agent、≤1 req/s、cache；非拉丁名 quiet miss | 本地语言 re-query，再 browser/手填并标 `est`。 |
| Nager.Date | 无 | fixed public holidays | 即时；缺宗教/农历假日 | 补一次政府/节日日历搜索并标 expected ±1 day。 |
| Open-Meteo | 无 | geocode、历史气候、16 天内 forecast | archive 首次可约 10s；无固定费用快照 | 搜索/官方天气源，保持 unverified。 |
| sunrise-sunset.org | 无 | civil dawn/sunrise/sunset | 要可见 attribution；重用会 429 + Retry-After | `sun` cache/重试；失败则不写，不凭记忆。 |
| Frankfurter | 无 | ECB FX | 约 30 种币；unsupported 返回 200 但缺 key | `open.er-api.com`（约 160 币，daily）；仍缺就显式 unknown。 |
| Google/Apple/Amap URI | 无 | per-hop/day deep links | Google 中国不可用；Amap 无 keyless multipoint，WGS→GCJ 可偏几百米 | 中国 Android 用 Amap、iPhone Apple；KML/Organic Maps 离线兜底。 |
| Amadeus | `AMADEUS_KEY/AMADEUS_SECRET` 可选 | flight/hotel upgrade | 仓库未记录固定配额/价格 | 不申请、不阻塞。 |
| SerpAPI | `SERPAPI_KEY` 可选 | Flights/Hotels JSON | 仓库未记录固定配额/价格 | browser/deep link。 |
| OpenRouter image/video | `.auth_header`，可选 | 无原生生成时的 gpt-image-2 / video | video 默认 Veo 3.1 Lite 约 $0.03/s，十世界链约 $3；Hailuo 约 $0.13/s；图片成本逐 asset 记 manifest | native generation；再不行 stock kit。 |

项目还给 planner 设搜索预算：orchestrator 约 25 次、每 city subagent ≤8 次；这是成本/时间门，而非服务商 quota。

## 5. 测试现状与实测

自动化 test suite：**无**。仓库没有 `tests/`、`test_*.py`、`*.test.js`，README 也没有统一测试命令；维护方法是 friction/adversarial runs、renderer static QC 和 headless visual probe。`docs/verification.md` 记录 9 次端到端 friction run，`docs/KNOWN-ISSUES.md` 公开 30 个 issue（29 open/planned、1 resolved 于该快照）。

按 README 的 keyless quick-start 实测：

```bash
python3 scripts/render_plan.py examples/kyoto-sample.plan.geo.json -o .../kyoto.html
python3 themes/render_clay2.py examples/china-2026/china.geo.json -o .../china-clay.html
python3 themes/qc.py .../china-clay.html
```

实际输出：

```text
wrote .../kyoto.html (2 days)
china-clay.html: 841KB, days=8, assets=16
PASS china-clay.html              841KB
```

exit `0`；输出大小 Kyoto 13K、China Clay 841K。完整原始输出：[`../evidence/trip-planner-skill-render-qc.txt`](../evidence/trip-planner-skill-render-qc.txt)，生成物在 [`../evidence/trip-planner-skill/`](../evidence/trip-planner-skill/)。这证明 keyless renderer/QC 可运行，不证明 planning、web fact-check、flight scan 或所有主题。

## 6. 优点、缺点与职责边界

### 优点

- 11 项中最完整的旅行 planning playbook：intake、country brief、route skeleton、flight/train、城市日程、hotel、budget、gates、delivery 全覆盖。
- 调度规则具体到 dwell time、security margin、energy curve、moving day、jet lag、weather/sun、degradation tag，可转成 deterministic constraints。
- `plan.geo.json` 把日程、点位、hop、budget、source freshness 与 HTML/KML/ICS 放进一条可复现链。
- keyless-first、missing 不猜、source+as-of、搜索预算与 explicit unverified 规则很成熟。
- 8 个 renderer、stock fallback、static QC、公开 known issues 和 friction reports，展示了真实交付工程而非只写 prompt。

### 缺点

- 785 个 tracked files 但无自动 test suite/lockfile；脚本回归主要靠人工/文档，维护与移植风险高。
- 大量“算法”仍是 Agent 读指令执行；没有独立 schedule optimizer，hours/closures/route consistency 无统一机器门禁。
- China rail 只建议 12306 browser；没有结构化 12306 MCP。酒店也只有 browser/deep link。
- `fast-flights` 依赖 Google cache/非官方库，可能 bot wall；返回航段和币种还有已知边界。
- China 坐标来自 OSM/WGS-84，Amap URI 不做 GCJ-02 转换，文档接受几百米点位偏差；对“真正能出发”不够。
- public known issues 包含 export 尾白、部分主题/语言缺陷、portal/mobile 限制、wrong-shape 只 WARN、stock 资产静默丢失等。
- `SCO-2` 明确非实时：无 delay tracking/rebooking；>3 个月通常只有季节 pattern。

### 职责边界

负责：从模糊需求到可点击/可打印/可离线参考的完整国际行程，所有事实需 source/as-of 或 verify flag。明确不负责：预订/支付/实名、服务化授权、实时延误与自动改签、保证 OTA 价格、完全自动化验证。

## 7. 可搬走什么、为什么不搬

### 采用其思想

- 采用 phased planning 与最多两个 checkpoint，但将每阶段产物落成 schema 和可恢复状态。
- 采用 hour-level scheduling 约束：pinned/opener、dwell、door-to-door buffer、energy curve、moving day、late-cut/swap。
- 采用 `plan.geo.json`→route validation/deep links/KML→renderer/QC 的流水线，拆成中国适配的 deterministic modules。
- 采用 keyless-first fallback、source/as-of/unverified、search budget、stock presentation fallback。
- 采用 known-issues/verification log 的透明工程习惯。

### 不直接搬代码/规则

- 不搬 8 套主题和大素材库作为 v1 核心；先锁定一个手机 HTML renderer，减少 30 个已知 issue 的表面积。
- 不把 Google/OSM 路线/坐标默认带进中国；中国需要 GCJ-02 canonical/provider boundary 和真实 AMap route。
- 不以 `fast-flights` 或 browser-only 12306/hotels 作为唯一实时源。
- 不复制无 tests/lockfile 的大脚本集合；应先提炼 contract、golden fixtures 和 validator。
- 不让 `trip-planner` 的超宽 description 与主 Skill 共同隐式启用；如果作为参考/辅助，应改成 explicit-only 或拆窄职责。

## 8. 能力矩阵证据

<a id="cap-destination-research"></a>
- 目的地调研：**有**。country brief、官方源优先、holiday/weather/visa/festival/search budget 完整。

<a id="cap-train"></a>
- 火车：**部分**。有 train-vs-fly、operator/browser/12306 规则与 links，但无结构化 rail client。

<a id="cap-flight"></a>
- 航班：**有**。`flight_scan.py` + browser fallback + price/source rules，可靠性受 Google/fast-flights 限制。

<a id="cap-lodging"></a>
- 住宿：**有**。日期深链、片区/物业 shortlist、评分与 all-in 复核；无 keyless API。

<a id="cap-poi-geocode"></a>
- POI 与地理编码：**有**。Nominatim geocode/cache/warning + stops schema；中国坐标误差仍有边界。

<a id="cap-route-validation"></a>
- 路线校验：**有**。`route_tools check/links/kml`、hop 对齐、distance/mode/China provider 警告。

<a id="cap-hourly-schedule"></a>
- 逐时排程：**有**。hour-level timeline、dwell/buffer/energy/opening/sun/day type 规则最完整。

<a id="cap-local-replan"></a>
- 局部重排：**有**。live-replan 只重建受影响 day，依赖 pinned/opener/skippable/swap/late_cut tags。

<a id="cap-html"></a>
- HTML 交付：**有**。plain + 8 themes、keyless stock、QC；portal 需 sidecar。

<a id="cap-credentials"></a>
- 凭据管理：**部分**。可选 env vars 与本地 `.auth_header` 有保密规则，但无集中 provider credential manager/health。

<a id="cap-tests"></a>
- 测试：**部分**。无自动 test suite；有 static QC、headless probe、9 次 friction run 与公开 known issues。

<a id="cap-source-evidence"></a>
- 来源证据：**有**。硬规则要求 price/hour source+as-of 或 verify flag，并有 `unverified[]`；schema 仍可进一步 fact-level 化。
