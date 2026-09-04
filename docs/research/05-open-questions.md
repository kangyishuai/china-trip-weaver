# 待验证问题

共 14 项；每项都写明验证方法与前置条件。已被实测证伪的当前 commit（如 `12306-skill`）不再包装成开放问题，见对应 02 文档。

## Q1. 目标 `plan-china-trip` 与旧同名 Skill 的真实 UI/调用行为是什么？

- 未决：官方文档只说同名不合并、会同时出现，尚未在隔离环境同时安装两个同名 Skill 观察 `$plan-china-trip` 选择器、implicit ranking 和错误提示。
- 怎么验证：做两个最小 test plugins，各含同名 Skill、不同 marker output；repo/personal marketplace 各装一组，分别测显式 `$`、自然语言、重启和 disable。
- 条件：允许在专用测试账户/临时 Codex home 修改 plugin config；不能在本研究只读的 `~/.codex`/`~/.agents` 上做。
- 证据背景：[`china-travel-assistant.md#1-定位与触发`](02-projects/china-travel-assistant.md#1-定位与触发)、[`01-codex-spec.md#3-skill目录触发与前置字段`](01-codex-spec.md#3-skill目录触发与前置字段)。

## Q2. `.app.json` 注册 UI 返回的 `plugin_asdk_app...` 如何映射到落盘 `asdk_app_...`/`connector_...`？

- 未决：官方 build 文档与本机/GitHub 样本前缀不一致，脚手架不验证或转换。
- 怎么验证：在 ChatGPT developer mode 注册一个无敏感数据的 test MCP，记录 browser technical ID，让官方 `@plugin-creator` 生成 package，再比较 `.app.json` 与 runtime exposed app id。
- 条件：有 developer mode、可注册的 test MCP URL、允许创建个人 test marketplace；不需要生产服务。
- 证据背景：[`01-codex-spec.md#121-不一致或公开规范未覆盖处`](01-codex-spec.md#121-不一致或公开规范未覆盖处)。

## Q3. `@fly-ai/flyai-cli` 的当前 command/schema/keyless trial 到底是什么？

- 未决：仓库 1.0.14/1.0.15、npm 1.0.16、官方 quickstart `fliggy-fast-search` 与 repo `keyword-search` 漂移；公开 quota/返回上限不完整。
- 怎么验证：在隔离 XDG/home 下 pin `1.0.16`，跑 `--help`/每 command `--help`，保存 schema fingerprint；用无 Key 做一次 harmless query，再用用户自备 test Key 做同 query，对比字段、条数、price type、rate headers 和 usage console。
- 条件：允许非全局 npm install 到临时目录；FlyAI test Key（用户自行配置，不进聊天/命令行）；接受一次/两次额度消耗。
- 证据背景：[`flyai-skill.md#5-测试现状与实测`](02-projects/flyai-skill.md#5-测试现状与实测)。

## Q4. `12306-mcp` 的真实余票 parser、日期范围与失败恢复是否稳定？

- 未决：本研究只查 station；ticket pipe columns、dynamic endpoints、cookie 与 price parser 没有 recorded fixture，cold start 无 cache。
- 怎么验证：在未来 15 天选北京南→上海虹桥，调用 JSON mode并保存脱敏 raw→normalized fixture；测无票、候补、跨日、中转、12306 5xx/TLS；重启离线验证 station cache 设计原型。
- 条件：网络可达 12306、只做 public query、不登录/占票；遵守调用频率；固定 MCP commit/npm version。
- 证据背景：[`12306-mcp.md#6-优点缺点与职责边界`](02-projects/12306-mcp.md#6-优点缺点与职责边界)。

## Q5. AMap 当前 Web API 的 v3/v4/v5 schema、CRS 与 route quota 能否形成稳定 adapter？

- 未决：参考 Skill 混用 endpoint，v5 pagination 已漂移，返回不标 CRS；当前计费页面和账户实际权限可能不同。
- 怎么验证：用 test Web Service Key 分别调用 geocode、POI v5、walking/transit/driving/riding，记录 request/response/error/QPS headers；同点用官方 picker 比对 GCJ，做 WGS↔GCJ round-trip 误差测试。
- 条件：用户自行提供受限 test Key、同意少量额度；固定 5–10 个北京/边界/HK 测试点；不把 Key 写日志。
- 证据背景：[`amap-lbs-skill.md#2-输入输出与数据结构`](02-projects/amap-lbs-skill.md#2-输入输出与数据结构)。

## Q6. 航班“价格/库存/状态”跨 FlyAI 与 VariFlight 如何同一航段对齐？

- 未决：两个 provider 的 service identity、币种、税费、舱位、时间字段与 freshness 未实际对比；VariFlight raw response 无 schema。
- 怎么验证：选 3 条国内航线/2 个日期，用 exact flight no+airports+date 建 identity，双源查询并对照 booking page；定义冲突规则与 price provenance fixture。
- 条件：FlyAI 与 VariFlight test Key/额度、查询不下单；固定 timezone/currency；保存原响应但脱敏。
- 证据背景：[`flyai-skill.md#2-输入输出与数据结构`](02-projects/flyai-skill.md#2-输入输出与数据结构)、[`variflight-mcp.md#2-输入输出与数据结构`](02-projects/variflight-mcp.md#2-输入输出与数据结构)。

## Q7. 无 Key/有 Key 下住宿数据能可靠到什么粒度？

- 未决：没有 keyless hotel API；FlyAI 示例有 `price/detailUrl`，但未证明日期、税费、房型、取消和库存均绑定。
- 怎么验证：同城市/同 dates/party 跑 keyless trial 和 test Key，打开 3 个 detail/checkout 深链，只读比对 all-in total、room、tax、cancellation；记录哪些字段只能 `verify-on-click`。
- 条件：FlyAI test Key可选、浏览器只读、无需登录或使用专用测试账户；不填个人资料/不预订。
- 证据背景：[`trip-planner-skill.md#4-外部服务key配额与费用`](02-projects/trip-planner-skill.md#4-外部服务key配额与费用)。

## Q8. 目的地调研应使用内置 web、AnySearch，还是两者组合？

- 未决：AnySearch 有 batch/中文召回和 quota，但当前 client contract、batch usage 计数、auto-registration 与 source quality 未实测；固定 11 query 又过窄。
- 怎么验证：为同一城市/日期制定 20 个 ground-truth claims，用内置 web、AnySearch free key、组合三组跑盲评；比较 recall、source authority、freshness、费用/调用数与 claim citation 正确率。
- 条件：AnySearch 用户自备 free Key并禁止 auto-save 新 Key；搜索预算相同；人工核验官方源。
- 证据背景：[`weekend-city-trip.md#4-外部服务key配额与费用`](02-projects/weekend-city-trip.md#4-外部服务key配额与费用)。

## Q9. claim-level evidence ledger 保存多少 raw data 才可重放又不泄露？

- 未决：完整 raw response 可审计但可能含 provider metadata/个人查询；只存 URL/hash 又可能无法复现动态价格。
- 怎么验证：为 train/flight/hotel/POI/hours 各做一个 fixture，尝试 `raw_ref + response hash + selected JSONPath + redaction`，让另一会话 10 分钟内重放每条 claim。
- 条件：定义数据保留/脱敏政策、provider ToS；所有 fixtures 无账号标识/Key/cookie。
- 证据背景：[`04-design-insights.md#5-采用claim-level-evidence-ledger不采用粗粒度来源列表`](04-design-insights.md#5-采用claim-level-evidence-ledger不采用粗粒度来源列表)。

## Q10. 轻量排程与 OR-Tools 的切换阈值是什么？

- 未决：OR-Tools 6 点 warm run 5s、venv 188MB；尚未比较 5–12 POI 的质量、cold start 与稳定性。
- 怎么验证：构造 20 个带 opening/service/meal/pinned/rain-alt 的 golden itineraries，比较 greedy insertion、DP/beam、OR-Tools 的可行率、objective、wall time、解释性和小变更 churn。
- 条件：有真实 AMap matrix fixtures；统一 1s/5s budget；macOS/Linux/桌面 app 三环境。
- 证据背景：[`or-tools.md#6-优点缺点与职责边界`](02-projects/or-tools.md#6-优点缺点与职责边界)。

## Q11. 局部重排的最小 patch/stability contract 应是什么？

- 未决：TripPick 能 drag/drop，trip-planner 有 tags，OR-Tools 会重解；尚无共同的 locked/affected/reverified diff schema。
- 怎么验证：定义 `PlanRevision`/JSON Patch，覆盖下雨、闭馆、误车、用户删点四场景；断言未受影响 day 与 pinned booking 字节不变，只重新查询改变的 hops/claims。
- 条件：versioned itinerary schema、provider fixture、用户接受状态与 booking locks。
- 证据背景：[`trippick.md#2-输入输出与数据结构`](02-projects/trippick.md#2-输入输出与数据结构)、[`trip-planner-skill.md#1-定位与触发`](02-projects/trip-planner-skill.md#1-定位与触发)。

## Q12. 手机单文件 HTML 能否同时做到 secret-free、核心离线与地图可用？

- 未决：AMap JS 需 key/security，Leaflet/tiles 非离线；KML/SVG 可离线但交互弱。
- 怎么验证：做三种原型：静态 SVG+deep links、Leaflet online enhancement、service-worker/PWA（若允许多文件）；iPhone/Android 真机 airplane mode、弱网、China network、打印/分享测试，并扫描 HTML 无 secret/remote analytics。
- 条件：至少 iOS Safari/Android Chrome、国内网络、无 Key baseline；明确“单文件”是否允许可选 sidecar/PWA。
- 证据背景：[`travel-plan-viz.md#6-优点缺点与职责边界`](02-projects/travel-plan-viz.md#6-优点缺点与职责边界)、[`weekend-city-trip.md#6-优点缺点与职责边界`](02-projects/weekend-city-trip.md#6-优点缺点与职责边界)。

## Q13. 小红书输入的技术稳定性、版权/隐私与来源保留边界是什么？

- 未决：TripPick feed/HTML 抓取受反爬影响，用户笔记可能含账号、图片和 copyrighted text；目标是否应接收链接、粘贴摘要还是只接用户自有笔记未定。
- 怎么验证：法务/ToS review + 20 条用户授权分享样本；测只保留短摘要/URL/POI claim，不保存全文/图片/账号；抓取失败始终回退手动粘贴。
- 条件：明确用户授权、数据 retention、删除机制；不破解签名/不维护 cookie pool。
- 证据背景：[`trippick.md#2-输入输出与数据结构`](02-projects/trippick.md#2-输入输出与数据结构)。

## Q14. 发布前许可证、服务条款与 marketplace metadata 还缺什么？

- 未决：3 个参考仓库无 LICENSE；AMap/AnySearch/Fliggy/VariFlight/OSM/素材各有不同条款；本阶段只研究未做法律确认。
- 怎么验证：逐依赖形成 provenance/NOTICE 表：代码许可证、数据/地图 attribution、商用限制、缓存/再分发、隐私 URL、terms URL；用官方 plugin submission checklist 验证 manifest。
- 条件：确定是否仅个人使用或公开发布/商用；必要时法务与 provider 商务确认。
- 证据背景：[`04-design-insights.md#23-不采用无明确许可证项目的代码复制`](04-design-insights.md#23-不采用无明确许可证项目的代码复制)、[`01-codex-spec.md#2-插件目录与-pluginjson`](01-codex-spec.md#2-插件目录与-pluginjson)。
