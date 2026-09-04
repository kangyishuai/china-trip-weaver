# china-trip-weaver 设计启示

版本口径：结论只对 [`01-codex-spec.md`](01-codex-spec.md) 与 11 份 [`02-projects/`](02-projects/) 所锁版本负责。共 23 条，未为凑数补齐 25。

## 设计决策

### 1. 采用：一个 Plugin，主编排 Skill + 窄 provider/presenter Skills

- 理由：`china-travel-assistant` 已证明 Codex plugin 可把 8 个 Skill、MCP 与 typed core 组合；官方规范也支持一个 plugin 包多个 Skills/MCP/hooks。主 Skill 只编排，provider/search/presentation 保持可替换。
- 证据：[`01-codex-spec.md#2-插件目录与-pluginjson`](01-codex-spec.md#2-插件目录与-pluginjson)、[`china-travel-assistant.md#6-优点缺点与职责边界`](02-projects/china-travel-assistant.md#6-优点缺点与职责边界)。

### 2. 不采用：与现有插件并存两个 `plan-china-trip`

- 理由：`19Chris19/china-travel-assistant` 已占用目标固定入口名；Codex 不合并同名 Skill。应把它列为互斥/迁移冲突：安装目标插件前禁用或卸载旧插件，不能靠 selection UI 让用户猜。
- 证据：[`01-codex-spec.md#3-skill目录触发与前置字段`](01-codex-spec.md#3-skill目录触发与前置字段)、[`china-travel-assistant.md#1-定位与触发`](02-projects/china-travel-assistant.md#1-定位与触发)。

### 3. 采用：主 Skill 独占宽泛旅行意图，子 Skill 默认禁止隐式调用

- 理由：FlyAI priority 90、`trip-planner`“只提 flight/hotel 也触发”、AMap“规划/附近”、weekend “always invoke”、travel-plan-viz 的“目的地+天数”会互抢。子 Skill 用 `agents/openai.yaml policy.allow_implicit_invocation:false`，由主 Skill 显式 `$name` 或 MCP tool 路由。
- 证据：[`flyai-skill.md#1-定位与触发`](02-projects/flyai-skill.md#1-定位与触发)、[`trip-planner-skill.md#1-定位与触发`](02-projects/trip-planner-skill.md#1-定位与触发)、[`amap-lbs-skill.md#1-定位与触发`](02-projects/amap-lbs-skill.md#1-定位与触发)、[`weekend-city-trip.md#1-定位与触发`](02-projects/weekend-city-trip.md#1-定位与触发)、[`01-codex-spec.md#32-agentsopenaiyaml`](01-codex-spec.md#32-agentsopenaiyaml)。

### 4. 采用：一个版本化 `itinerary.json` 是所有层的唯一事实源

- 理由：CTA 的 typed contracts、travel-plan-viz 的内嵌 `trip-data`、trip-planner 的 `plan.geo.json`、TripPick 的 custom itinerary 分别解决查询归一化、回传编辑、地图/render 和局部修改。目标应合并而非另造四套对象。
- 证据：[`china-travel-assistant.md#2-输入输出与数据结构`](02-projects/china-travel-assistant.md#2-输入输出与数据结构)、[`travel-plan-viz.md#2-输入输出与数据结构`](02-projects/travel-plan-viz.md#2-输入输出与数据结构)、[`trip-planner-skill.md#2-输入输出与数据结构`](02-projects/trip-planner-skill.md#2-输入输出与数据结构)、[`trippick.md#2-输入输出与数据结构`](02-projects/trippick.md#2-输入输出与数据结构)。

### 5. 采用：claim-level evidence ledger，不采用粗粒度“来源列表”

- 理由：动态事实需要 `claim_id/value/unit/source_url/provider/queried_at/as_of/confidence/status/raw_ref`；`dataSources[]`、`source_titles[]`、`systemMessage` 只能说明“用过谁”，无法重放某个票价/营业时间。
- 证据：[`travel-plan-viz.md#6-优点缺点与职责边界`](02-projects/travel-plan-viz.md#6-优点缺点与职责边界)、[`trippick.md#6-优点缺点与职责边界`](02-projects/trippick.md#6-优点缺点与职责边界)、[`weekend-city-trip.md#6-优点缺点与职责边界`](02-projects/weekend-city-trip.md#6-优点缺点与职责边界)。

### 6. 采用：unknown、provider health 与 price type 必须进入合同

- 理由：缺失不能变 0，list-level lead price 不能冒充 bookable total；状态至少覆盖 `ready/missing/expired/forbidden/rate_limited/degraded`，价格区分 live/reference/estimate/verify-on-click。
- 证据：[`china-travel-assistant.md#2-输入输出与数据结构`](02-projects/china-travel-assistant.md#2-输入输出与数据结构)、[`trip-planner-skill.md#4-外部服务key配额与费用`](02-projects/trip-planner-skill.md#4-外部服务key配额与费用)。

### 7. 采用：`12306-mcp` 为铁路主 provider；不采用当前 `12306-skill`

- 理由：MCP 已实测 build/start/station call，工具覆盖直达/中转/经停；Python Skill 连 `list-tools` 三次失败、cache 路径确定错误且无许可证。目标仍需给 MCP 加 station cache、timestamp、fixture contract test 与降级。
- 证据：[`12306-mcp.md#5-测试现状与规定实测`](02-projects/12306-mcp.md#5-测试现状与规定实测)、[`12306-skill.md#5-测试现状与实测`](02-projects/12306-skill.md#5-测试现状与实测)。

### 8. 采用：FlyAI 主查可售航班/酒店，VariFlight 只做航空增强

- 理由：FlyAI 提供 booking links 与 flight/hotel/train/POI filters，但 schema/版本/额度不稳定；VariFlight 擅长状态、准点、机型、天气、comfort 与 price cross-check，却无住宿/交易合同。两者交叉而非互相替代。
- 证据：[`flyai-skill.md#6-优点缺点与职责边界`](02-projects/flyai-skill.md#6-优点缺点与职责边界)、[`variflight-mcp.md#6-优点缺点与职责边界`](02-projects/variflight-mcp.md#6-优点缺点与职责边界)。

### 9. 采用：住宿交付“片区 + dated deep links + 可核验条件”，不编造房价

- 理由：没有稳定 keyless hotel API；FlyAI 可给候选/链接但无 Key trial 完整性未承诺。房价、税费、取消和房型只有 checkout/date context 才成立。
- 证据：[`trip-planner-skill.md#4-外部服务key配额与费用`](02-projects/trip-planner-skill.md#4-外部服务key配额与费用)、[`flyai-skill.md#2-输入输出与数据结构`](02-projects/flyai-skill.md#2-输入输出与数据结构)。

### 10. 采用：内容调研维度按用户/城市动态生成；不采用固定“喜茶/十大商场”章节

- 理由：weekend-city-trip 的日期锁定、多源、补查门很强，但固定品牌章节会逼 Agent 凑数。保留“活动/官方开放时间/季节/餐饮/行前须知”基线，按兴趣扩展。
- 证据：[`weekend-city-trip.md#6-优点缺点与职责边界`](02-projects/weekend-city-trip.md#6-优点缺点与职责边界)。

### 11. 采用：同时保存 provider-native 与规范化坐标，不做无标记的单坐标

- 理由：中国-only 仍有两种消费者：AMap route/render 需要 GCJ-02，KML/OSM/Nominatim 需要 WGS-84。建议 `coordinates:{source_crs,native,wgs84,gcj02,conversion}`，从哪来就保留哪一份，另一份标算法派生，禁止二次转换。
- 证据：[`travel-plan-viz.md#2-输入输出与数据结构`](02-projects/travel-plan-viz.md#2-输入输出与数据结构)、[`trippick.md#3-脚本与依赖`](02-projects/trippick.md#3-脚本与依赖)、[`amap-lbs-skill.md#2-输入输出与数据结构`](02-projects/amap-lbs-skill.md#2-输入输出与数据结构)。

### 12. 不采用：`amap-lbs-skill` 的 `travelPlanner`；采用其底层 POI/route provider 角色

- 理由：当前 `travelPlanner` 没调用 route API且丢 map result，v5 pagination 也漂移；但 walking/transit/driving/riding API 正是中国 route truth。目标需自写有 timeout/error/schema/CRS 的薄 adapter。
- 证据：[`amap-lbs-skill.md#2-输入输出与数据结构`](02-projects/amap-lbs-skill.md#2-输入输出与数据结构)、[`amap-lbs-skill.md#6-优点缺点与职责边界`](02-projects/amap-lbs-skill.md#6-优点缺点与职责边界)。

### 13. 采用：先真实 travel-time matrix，再排 time windows；不以直线/连线冒充路线

- 理由：TripPick Haversine、travel-plan-viz 直线、trip-planner distance estimate 都只能做预筛；最终顺序必须由 AMap mode/time route matrix + opening/service windows 驱动。
- 证据：[`trippick.md#6-优点缺点与职责边界`](02-projects/trippick.md#6-优点缺点与职责边界)、[`travel-plan-viz.md#6-优点缺点与职责边界`](02-projects/travel-plan-viz.md#6-优点缺点与职责边界)、[`or-tools.md#2-输入输出与数据结构`](02-projects/or-tools.md#2-输入输出与数据结构)。

### 14. 采用：OR-Tools 作为复杂日程可选引擎，不作为无条件依赖

- 理由：6 点 time-window 实测可行且 arrival range 可解释；但 wheel 21.9MB、venv 188MB，简单 5–8 点可能用更轻的 insertion/DP 足够。以候选数/约束数阈值选择，先 benchmark。
- 证据：[`or-tools.md#5-测试现状与实测`](02-projects/or-tools.md#5-测试现状与实测)、[`or-tools.md#6-优点缺点与职责边界`](02-projects/or-tools.md#6-优点缺点与职责边界)。

### 15. 采用：局部重排是 versioned patch，不是“重跑全计划”

- 理由：用户 accepted/pinned、已订票、住宿与跨城腿必须锁定；只重算受影响 day/cluster，并用 stability penalty 限制无关改动，输出 before/after + 原因 + reverified claims。
- 证据：[`trippick.md#2-输入输出与数据结构`](02-projects/trippick.md#2-输入输出与数据结构)、[`trip-planner-skill.md#1-定位与触发`](02-projects/trip-planner-skill.md#1-定位与触发)、[`or-tools.md#6-优点缺点与职责边界`](02-projects/or-tools.md#6-优点缺点与职责边界)。

### 16. 采用：v1 只做一个 deterministic 手机 HTML renderer

- 理由：travel-plan-viz 的 phone contract/embedded JSON/validator 与 CTA 的 escape/no-remote-script 足够；trip-planner 的 8 themes 带来 30 个 live issues。先把事实、可访问性、打印、移动端做到稳，再扩主题。
- 证据：[`travel-plan-viz.md#6-优点缺点与职责边界`](02-projects/travel-plan-viz.md#6-优点缺点与职责边界)、[`china-travel-assistant.md#6-优点缺点与职责边界`](02-projects/china-travel-assistant.md#6-优点缺点与职责边界)、[`trip-planner-skill.md#6-优点缺点与职责边界`](02-projects/trip-planner-skill.md#6-优点缺点与职责边界)。

### 17. 采用：只承诺“核心离线可读”，地图/图片显式降级

- 理由：Leaflet/CDN/tiles/remote images 不是离线；可内联行程、证据、清单和简化 SVG，并另交 KML；网络地图失败时不破坏时间线、不露破图。
- 证据：[`travel-plan-viz.md#2-输入输出与数据结构`](02-projects/travel-plan-viz.md#2-输入输出与数据结构)、[`trip-planner-skill.md#2-输入输出与数据结构`](02-projects/trip-planner-skill.md#2-输入输出与数据结构)。

### 18. 不采用：聊天/CLI 参数/源码目录/HTML 中保存 Key

- 理由：采用 env var name、Codex MCP OAuth/secret store 或权限受控本地文件；provider process 只收自己需要的 secret。严禁 AMap JS security 嵌可分享 HTML、FlyAI key 进 shell history、AMap plaintext config、自动注册 Key。
- 证据：[`01-codex-spec.md#9-凭据环境变量与沙箱网络`](01-codex-spec.md#9-凭据环境变量与沙箱网络)、[`amap-lbs-skill.md#4-外部服务key配额与费用`](02-projects/amap-lbs-skill.md#4-外部服务key配额与费用)、[`weekend-city-trip.md#4-外部服务key配额与费用`](02-projects/weekend-city-trip.md#4-外部服务key配额与费用)、[`flyai-skill.md#4-外部服务key配额与费用`](02-projects/flyai-skill.md#4-外部服务key配额与费用)。

### 19. 不采用：silent mock/空字段被包装成成功

- 理由：fallback 可以交付，但必须顶层 `mode=live|cached|static|mock`、provider health、未验证项和原因；HTTP 200 不得让示例看成用户结果，wrong-shape 不能只 WARN 后继续发布。
- 证据：[`trippick.md#4-外部服务key配额与费用`](02-projects/trippick.md#4-外部服务key配额与费用)、[`trip-planner-skill.md#6-优点缺点与职责边界`](02-projects/trip-planner-skill.md#6-优点缺点与职责边界)。

### 20. 采用：查询/比较/深链止步，交易动作永远出 scope

- 理由：实名、订单、付款、退改的权限/责任远高于行程研究；所有项目里 CTA 的 confirmation boundary 最完整，应变成 plugin hard rule 与测试。
- 证据：[`china-travel-assistant.md#6-优点缺点与职责边界`](02-projects/china-travel-assistant.md#6-优点缺点与职责边界)、[`trip-planner-skill.md#1-定位与触发`](02-projects/trip-planner-skill.md#1-定位与触发)。

### 21. 采用：四层测试，不把“能启动/能打印”当测试

- 理由：provider recorded fixtures + schema contract；scheduler golden/no-solution/property；renderer validator + accessibility/mobile screenshot；end-to-end keyless/live opt-in。12306-skill/amap/FlyAI/VariFlight/TripPick 的失败证明 smoke/文档不能替代 assertions。
- 证据：[`china-travel-assistant.md#5-测试现状与实测`](02-projects/china-travel-assistant.md#5-测试现状与实测)、[`travel-plan-viz.md#5-测试现状与实测`](02-projects/travel-plan-viz.md#5-测试现状与实测)、[`12306-skill.md#5-测试现状与实测`](02-projects/12306-skill.md#5-测试现状与实测)、[`trippick.md#5-测试现状与实测`](02-projects/trippick.md#5-测试现状与实测)。

### 22. 采用：所有外部 CLI/MCP 固定版本 + 启动时 contract probe

- 理由：FlyAI 已同时出现 1.0.14/1.0.15/1.0.16 与 command 漂移；12306/VariFlight docs/schema 也漂移。plugin manifest 只 pin command 不够，运行前要 tools/list/help/schema fingerprint，变更即 degraded。
- 证据：[`flyai-skill.md#6-优点缺点与职责边界`](02-projects/flyai-skill.md#6-优点缺点与职责边界)、[`12306-mcp.md#6-优点缺点与职责边界`](02-projects/12306-mcp.md#6-优点缺点与职责边界)、[`variflight-mcp.md#6-优点缺点与职责边界`](02-projects/variflight-mcp.md#6-优点缺点与职责边界)。

### 23. 不采用：无明确许可证项目的代码复制

- 理由：`12306-skill`、`weekend-city-trip`、`trippick` 在锁定 commit 无 LICENSE；只能学思想、重写合同/测试，不复制实现。所有第三方服务条款与素材许可证也要进入 provenance/NOTICE。
- 证据：[`12306-skill.md#版本锁定`](02-projects/12306-skill.md#版本锁定)、[`weekend-city-trip.md#版本锁定`](02-projects/weekend-city-trip.md#版本锁定)、[`trippick.md#版本锁定`](02-projects/trippick.md#版本锁定)。

## 必答专题 A：重名与触发竞争

| 同装组合 | 风险 | 处理结论 |
|---|---|---|
| 目标 `plan-china-trip` + china-travel-assistant | **精确同名**，selector/显式调用歧义 | 互斥安装或迁移禁用旧 Skill；不能同时保持启用。 |
| 目标 + trip-planner + travel-plan-viz | 三者都吃“规划旅行/目的地+天数/做 HTML” | 目标独占隐式；后两者不打包，或窄化为 presenter 且 explicit-only。 |
| 目标 + FlyAI | FlyAI priority 90 覆盖 plan/train/flight/hotel/POI | FlyAI 只作为 CLI/provider，由主 Skill 调；禁隐式。 |
| 目标 + amap-lbs-skill | AMap 用“搜/找/查/附近/路线/规划”宽触发 | 不直接捆原 Skill；只包窄 MCP/adapter。 |
| 目标 + weekend-city-trip | “任何中国城市短期调研都 always invoke” | 内容研究变成主 Skill 的内部 phase；禁独立隐式。 |
| search-china-trains + 12306-skill + FlyAI train | 同一铁路问句命中 3 条 | 只保留一个显式 train subskill；内部 provider order=12306→FlyAI link enrichment。 |
| VariFlight MCP、OR-Tools、TripPick app | tool/library/app 本身无 Skill 同名 | 不直接抢 trigger；仍需由主 Skill 控制何时调用/导入。 |

## 必答专题 B：坐标系处理

| 项目 | 实际处理 | 判断 |
|---|---|---|
| china-travel-assistant | AMap output 明标 GCJ-02；不转 WGS | provider 内一致，跨地图合同不足。 |
| travel-plan-viz | `trip` 存 WGS-84；高德/腾讯 GCJ→WGS 后画 OSM | 正确方向，有转换测试。 |
| trip-planner-skill | Nominatim/OSM WGS；Amap deep link仍喂 WGS，文档接受数百米偏差 | 中国出发不合格。 |
| 12306-mcp / 12306-skill | 不处理坐标 | 不适用。 |
| amap-lbs-skill | 原样传 AMap location/route；未标 CRS | 同 provider 勉强可用，跨层危险。 |
| flyai-skill | hotel 有 lat/lon，未声明 CRS；POI 样例无坐标 | 必须视为未知，不能直接入地图。 |
| weekend-city-trip | AMap geocode 输出 GCJ-02，AMap JS 渲染同 CRS | 一致，但 HTML 嵌 Key。 |
| variflight-mcp | 不处理地面坐标 | 不适用。 |
| trippick | Nominatim 存 WGS；渲染 AMap 前 WGS→GCJ | 最清晰的 render-boundary 先例。 |
| OR-Tools | 只消费 matrix，不关心 CRS | matrix producer 必须先统一/标注。 |

目标结论：**不选“只存 GCJ”或“只存 WGS”**；保存 native + WGS + GCJ 和 conversion provenance，AMap route 使用 GCJ，KML/OSM 使用 WGS。

## 必答专题 C：无 Key 时如何降级

| 项目 | 无 Key 行为 |
|---|---|
| china-travel-assistant | 12306 可用；AMap/Variflight missing；FlyAI 是否返回 trial 以 CLI 为准；Visualize→HTML/SVG/Markdown。 |
| travel-plan-viz | 静态 web research + 内置 engine；无实时 actionLink/价；仍交完整 HTML。 |
| trip-planner-skill | keyless APIs/browser/deep links；无图片生成则 stock；酒店只片区/深链。 |
| 12306-mcp | 不需 API Key，完整 public query；必须有网络。 |
| 12306-skill | 设计上不需 Key，但当前 commit 初始化失败，不能作为 fallback。 |
| amap-lbs-skill | 普通 search/hosted heatmap link 可拼；POI/geocode/route/travel API 直接失败。 |
| flyai-skill | 声称 default/trial 可用但 quota/完整性更低；当前仓库不含 CLI，需先做 contract probe。 |
| weekend-city-trip | AnySearch anonymous 低 quota且可能 auto-register；普通已有 Markdown→HTML 可 keyless；AMap map 不可生成。 |
| variflight-mcp | business tools 不可用；只能启动/list，无数据。 |
| trippick | LLM 无 Key→显式 mock；Nominatim/map仍 keyless；Redis 无 Key→仅本机状态。 |
| OR-Tools | 安装后完全本地；无数据 provider 时只能拒绝/用标明 estimate 的 matrix。 |

目标降级顺序：**live provider → cached fresh-enough evidence → keyless public source → dated deep link/estimate → unknown**；任何 rung 都保留 mode/source/freshness，不把 mock 或静态区间伪装实时。
