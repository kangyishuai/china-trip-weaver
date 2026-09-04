# 插件结构与 Skill 路由

状态：阶段三 package/Skill 实现合同。**合格条件 A：只有 `plan-china-trip` 允许隐式触发；其余全部 `allow_implicit_invocation: false`。** 这是硬门禁，不是建议。[依据：研究决策 3](../research/04-design-insights.md#3-采用主-skill-独占宽泛旅行意图子-skill-默认禁止隐式调用)、[官方规范核查 3.2](../research/01-codex-spec.md#32-agentsopenaiyaml)

## 1. 未来插件包布局

以下是阶段三将实现的 package；本阶段不创建这些产品文件：

```text
marketplace-root/
├── .agents/plugins/marketplace.json
└── plugins/china-trip-weaver/
    ├── .codex-plugin/plugin.json
    ├── .mcp.json
    ├── skills/
    │   ├── plan-china-trip/
    │   ├── research-china-destination/
    │   ├── search-china-trains/
    │   ├── search-china-flights/
    │   ├── search-china-lodging/
    │   ├── resolve-china-mobility/
    │   ├── schedule-china-trip/
    │   ├── replan-china-trip/
    │   └── render-china-trip/
    ├── src/china_trip_weaver/
    ├── scripts/
    ├── references/
    └── assets/
```

只有 `plugin.json` 放进 `.codex-plugin/`，Skills、MCP 和其他目录都位于插件根。[依据：官方规范核查 2](../research/01-codex-spec.md#2-插件目录与-pluginjson)

## 2. `.codex-plugin/plugin.json` 字段定值

阶段三首个本地版本必须生成以下语义等价 JSON；未列字段不得自行加入：

```json
{
  "name": "china-trip-weaver",
  "version": "0.1.0",
  "description": "Evidence-backed, read-only planning for 1-7 day trips within mainland China, with provider degradation, local replanning, and deterministic mobile HTML.",
  "author": {"name": "ChinaTripWeaver contributors"},
  "license": "UNLICENSED",
  "keywords": ["china-travel", "itinerary", "12306", "amap", "evidence", "replanning"],
  "skills": "./skills/",
  "mcpServers": "./.mcp.json",
  "interface": {
    "displayName": "China Trip Weaver",
    "shortDescription": "Evidence-backed China trip planning",
    "longDescription": "Plan and locally replan short mainland-China trips with explicit sources, provider health, price types, and a deterministic mobile itinerary.",
    "developerName": "ChinaTripWeaver contributors",
    "category": "Productivity",
    "capabilities": ["trip planning", "provider comparison", "local replanning", "mobile HTML"],
    "defaultPrompt": [
      "Plan a three-day China trip with sources and explicit unknowns.",
      "Replan only the affected part of this itinerary.",
      "Render this validated Trip as a mobile HTML file."
    ],
    "brandColor": "#C94F36"
  }
}
```

字段判定：

| 字段 | 决定与理由 |
|---|---|
| `name/version/description` | 必填，固定如上；`name` 是 kebab-case namespace，版本从 `0.1.0` 起。[依据：官方字段清单](../research/01-codex-spec.md#21-字段清单) |
| `author` | 本地开发期用团队占位名；公开发布前替换为真实责任主体。**假设**：该占位仅用于本地包，不进入公开 marketplace。 |
| `license` | 暂为 `UNLICENSED`，因为发布方式和第三方 ToS 尚未裁决；不得擅自写 MIT。[依据：开放问题 Q14](../research/05-open-questions.md#q14-发布前许可证服务条款与-marketplace-metadata-还缺什么) |
| `homepage/repository` | 省略：当前目录不是仓库，也没有真实 URL；禁止编造。 |
| `skills/mcpServers` | 精确指向根目录组件。 |
| `apps` | 省略：MVP 没有已注册 app/connector；`.app.json` 不能证明授权或可调用。[依据：官方规范核查 6](../research/01-codex-spec.md#6-appjson) |
| `hooks` | 省略：MVP 不需要生命周期副作用，避免安装即执行命令。 |
| `interface` | 采用公开字段；不复制 `logoDark`、`bundledContentVariant` 等内部扩展。[依据：官方规范核查 12.1](../research/01-codex-spec.md#121-不一致或公开规范未覆盖处) |
| `category` | **假设**使用已见样本值 `Productivity`；发布前必须经当时安装流程验证，因为公开规范没有枚举 schema。 |

## 3. Skill 清单与 description 原文

下列 description 是未来 `SKILL.md` frontmatter 的**逐字原文**。所有 name 与父目录同名，description 同时限定做什么和何时显式使用。[依据：官方 Skill frontmatter](../research/01-codex-spec.md#31-skillmd-yaml-frontmatter)

### 3.1 主入口（唯一 implicit）

`plan-china-trip`

> Plan, compare, or locally replan a read-only trip within mainland China for 1-7 days. Use when the user asks for a China itinerary, a city weekend, cross-city transport and lodging choices, an executable day schedule, a disruption-aware revision, or a sourced mobile trip page. Orchestrate the plugin's explicit-only research, provider, scheduling, replanning, and rendering Skills; never book, log in, submit identity, pay, cancel, or change an order.

### 3.2 子 Skills（全部 explicit-only）

`research-china-destination`

> Build date-bound destination and POI claims for a mainland-China city from authoritative web sources and user-pasted notes. Invoke explicitly from plan-china-trip when candidate places, current events, opening information, seasonal constraints, food, or local cautions are missing; do not create or render a full itinerary.

`search-china-trains`

> Normalize read-only China Railway station, schedule, seat, fare, direct, transfer, and route-stop results from the pinned 12306 MCP. Invoke explicitly from plan-china-trip for a dated rail leg or rail alternative; never log in, hold, purchase, pay, cancel, or change a ticket.

`search-china-flights`

> Normalize dated mainland-China flight candidates and booking deep links from the pinned FlyAI CLI, with optional VariFlight status, comfort, weather, and price enrichment. Invoke explicitly from plan-china-trip for a flight leg or flight-versus-rail comparison; do not transact or present an untyped price.

`search-china-lodging`

> Produce dated mainland-China lodging areas, candidate properties, verifiable conditions, and deep links from the pinned FlyAI CLI or explicit degradation. Invoke explicitly from plan-china-trip when overnight stays are required; never claim room-level inventory, tax, cancellation, or total price unless the corresponding claim is verified.

`resolve-china-mobility`

> Resolve mainland-China POIs, geocodes, coordinate provenance, and walking, transit, driving, or cycling route-time matrix cells through the AMap adapter. Invoke explicitly from plan-china-trip after candidates exist or when affected hops need revalidation; do not schedule a trip or treat straight lines as routes.

`schedule-china-trip`

> Create or validate deterministic day slots from a schema-valid Trip, a route-time matrix, opening windows, dwell times, buffers, and locks. Invoke explicitly from plan-china-trip after evidence collection; return a feasible schedule or a structured no-solution result, never silently drop a hard constraint.

`replan-china-trip`

> Apply a versioned local patch to a schema-valid Trip after a disruption or user edit. Invoke explicitly from plan-china-trip with the current revision, event, locks, and affected scope; preserve unrelated days and accepted or booked items byte-for-byte and list every claim that must be reverified.

`render-china-trip`

> Render a schema-valid Trip as the single deterministic, phone-first HTML artifact and validate its structure, security, accessibility, and offline core. Invoke explicitly from plan-china-trip only after Trip validation; never research, reschedule, alter facts, or embed credentials.

## 4. Skill policy、输入输出与调用面

每个 Skill 都有 `agents/openai.yaml`。主入口 policy 为 `true`（也可省略但为可审计性显式写出）；其余统一为：

```yaml
policy:
  allow_implicit_invocation: false
```

显式 `$skill` 仍可用；禁止隐式不等于禁用。[依据：官方规范核查 3.2](../research/01-codex-spec.md#32-agentsopenaiyaml)

| Skill | implicit | 输入 | 输出 | 阶段三脚本/工具调用 |
|---|---:|---|---|---|
| `plan-china-trip` | **是** | 用户文本；可选现有 Trip/revision | schema-valid Trip、决策摘要、可选 HTML | `cli.py normalize/validate`；显式调用下面 Skills |
| `research-china-destination` | 否 | city、dates、interests、pasted notes、query budget | candidates + claim ledger + conflicts | 宿主内置 web；可选 `providers/anysearch.py` |
| `search-china-trains` | 否 | date、from/to、time/seat/direct filters | normalized transport offers、claims、health | MCP `china-rail`；`providers/rail12306.py` |
| `search-china-flights` | 否 | dated city/airport pair、party、filters | normalized offers、deep links、claims、health | `providers/flyai.py` 调 CLI；可选 MCP `variflight` |
| `search-china-lodging` | 否 | city/area、check-in/out、party、constraints | areas/properties、typed prices、conditions、deep links | `providers/flyai.py`；无 Key 时 deep-link builder |
| `resolve-china-mobility` | 否 | places/endpoints、native coordinates、modes | resolved coordinates、matrix、claims、health | `providers/amap.py`；无 Key 时 `degrade.py` |
| `schedule-china-trip` | 否 | Trip candidates、matrix、windows、locks | scheduled Trip 或 `no_solution` explanation | `scheduler/light.py`；可选 `scheduler/ortools.py` |
| `replan-china-trip` | 否 | current Trip、event、locks、base revision | new Trip + patch + reverify set | `replan.py`、scheduler、受影响 provider adapters |
| `render-china-trip` | 否 | **仅** schema-valid Trip | `.html` + validator report | `renderer.py`、`validate_html.py` |

脚本名是实现地图合同，不代表本阶段已有产品代码。所有 provider 输出先归一化再进入 Trip；renderer 不直连 provider。[依据：研究决策 4](../research/04-design-insights.md#4-采用一个版本化-itineraryjson-是所有层的唯一事实源)

## 5. 主入口确定性路由

```text
收到旅行意图
  ├─ 检测到重复 plan-china-trip → 停止并给互斥提示
  ├─ 涉及下单/登录/实名/支付/退改 → 拒绝该动作，只提供只读比较/深链
  ├─ 已有 Trip + 异常/删改请求 → replan → affected providers → schedule → validate → render
  ├─ 已有 schema-valid Trip + 只要求页面 → render
  └─ 新计划
       normalize → 必要追问 → destination research
       → train / flight / lodging providers（按行程需要）
       → mobility matrix → schedule → validate → render
```

路由细则：

1. 同一用户请求只由主入口持有会话状态；子 Skill 返回结构结果，不直接向另一个子 Skill 分派。
2. 城市周末且无过夜时跳过 transport inventory/lodging；跨城计划按距离、时长和用户偏好显式比较铁路/航班。
3. 12306 为铁路主源；FlyAI train 只能补 deep link，不得覆盖冲突的 12306 live claim。[依据：研究必答专题 A](../research/04-design-insights.md#必答专题-a重名与触发竞争)
4. FlyAI 为航班/酒店主 inventory；VariFlight 只在有 Key、probe 通过且需状态/舒适度/天气/交叉价格时调用。[依据：研究决策 8](../research/04-design-insights.md#8-采用flyai-主查可售航班酒店variflight-只做航空增强)
5. AMap 只做 POI/geocode/route；不调用参考项目 `travelPlanner`。
6. 任一 provider probe 或查询失败，立即写 health 并进入统一降级阶梯；不把失败转成空成功。
7. 只有通过 Schema 与语义校验的 Trip 才能进入 renderer。

### 必须问用户的情况

- 新计划缺目的城市、实际日期/日期范围或人数；这些会改变所有 provider query，不得猜。
- 存在两个互斥硬约束（例如“必须参加 10:00 活动”与同城外 10:00 已订车次），且没有可行解。
- 用户要求改变已标 `locked/booked/accepted` 项；先列出影响并获得明确选择。
- 用户粘贴内容可能含账号、手机号、订单号或身份证号；要求先删去敏感信息。
- 用户要求交易动作；不询问凭据，直接说明只读边界并给官方/dated deep link。

### 不问、但必须记录假设的情况

节奏、餐型、可步行距离、预算分配或展示语言未给出时，采用保守默认并写入 `request.assumptions`；这些默认可由用户随后 patch。只有软偏好可假设，日期/人数/目的地不可假设。

## 6. `.mcp.json` 定值

```json
{
  "mcpServers": {
    "china-rail": {
      "command": "npx",
      "args": ["-y", "12306-mcp@0.3.10"]
    },
    "variflight": {
      "command": "npx",
      "args": ["-y", "@variflight-ai/variflight-mcp@1.0.3"],
      "env_vars": ["VARIFLIGHT_API_KEY", "X_VARIFLIGHT_KEY", "VARIFLIGHT_API_URL"]
    }
  }
}
```

- 两个包都固定完整版本；每次会话首次业务调用前做 tools/list/schema fingerprint probe，漂移即 `contract_mismatch/degraded`。[依据：研究决策 22](../research/04-design-insights.md#22-采用所有外部-climcp-固定版本-启动时-contract-probe)
- `china-rail` 无用户 Key；其冷启动仍依赖网络，失败只降低铁路能力。[依据：12306 选择](../research/04-design-insights.md#7-采用12306-mcp-为铁路主-provider不采用当前-12306-skill)
- VariFlight 环境项只传变量名，不落值；无 Key 时不发业务调用。
- FlyAI 是 CLI 而非 bundled MCP，由 adapter 以 `npx -y @fly-ai/flyai-cli@1.0.16 ...` 调用并先解析当前 `--help`。它的实际 command/schema/keyless trial 未决，probe 不通过不得猜 command。[依据：开放问题 Q3](../research/05-open-questions.md#q3-fly-aiflyai-cli-的当前-commandschemakeyless-trial-到底是什么)
- AMap 使用 Python 标准库 HTTP adapter，不伪装成现成 MCP；Key 来源见 `05-credentials.md`。

## 7. 本地 marketplace 条目

`marketplace-root/.agents/plugins/marketplace.json` 语义等价内容：

```json
{
  "name": "china-trip-weaver-local",
  "interface": {"displayName": "China Trip Weaver Local"},
  "plugins": [
    {
      "name": "china-trip-weaver",
      "source": {"source": "local", "path": "./plugins/china-trip-weaver"},
      "policy": {"installation": "AVAILABLE", "authentication": "ON_USE"},
      "category": "Productivity"
    }
  ]
}
```

相对 `source.path` 以 marketplace root 解析；本地安装运行缓存副本，改源码后必须重装/刷新并重启验证。[依据：官方规范核查 7](../research/01-codex-spec.md#7-marketplace位置与-claude-兼容)

## 8. 与旧入口互斥：检测与提示

安装前置规则：`china-travel-assistant` 与 `china-trip-weaver` 不得同时启用，因为两者都有完全同名 `plan-china-trip`，Codex 不会合并同名 Skill。[依据：研究决策 2](../research/04-design-insights.md#2-不采用与现有插件并存两个-plan-china-trip)

检测分两层：

1. **安装/doctor 层**：读取 `codex plugin list --json`（若当前版本支持）或受控检查已配置插件清单；发现 `china-travel-assistant` 即 exit 非零并打印下面的固定文案。不得扫描/改写其他插件源码。
2. **会话层**：主 Skill 检查宿主提供的 Skill catalog/source metadata；若能看到第二个同名入口或来源不可判定，fail closed，不开始规划。

固定用户提示：

> 检测到另一个 `plan-china-trip`（`china-travel-assistant`）或无法唯一确认入口来源。Codex 不会合并同名 Skill。请先在 Plugins Directory 中禁用/卸载旧插件，或禁用本插件，然后新建会话再试；当前未运行任何行程查询。

宿主是否稳定暴露 source metadata 仍未实测，已列入 `BLOCKED.md`；在该能力明确前，阶段三必须把“同时安装测试应拒绝”作为人工安装验收，不得声称自动检测 100% 可用。[依据：开放问题 Q1](../research/05-open-questions.md#q1-目标-plan-china-trip-与旧同名-skill-的真实-ui调用行为是什么)

## 9. 桌面应用本地安装验证路径（无 CLI）

本阶段不执行；阶段三在专用测试环境按以下步骤验收：[依据：官方规范核查 10](../research/01-codex-spec.md#10-桌面应用无-cli-时的本地安装与验证)

1. 静态验证 package 中有 `.codex-plugin/plugin.json`、9 个 Skill 和 `.mcp.json`；9 个 name/目录匹配，8 个子 Skill policy 均为 `false`。
2. 在 Plugins Directory 检查并禁用/卸载 `china-travel-assistant`；若不能确认，停止。
3. 将 local marketplace 条目加入专用测试用户的 personal marketplace；完全退出并重启 desktop。
4. 从 `China Trip Weaver Local` 安装 `china-trip-weaver`，再新建任务。
5. 显式运行 `$plan-china-trip` 的无 Key fixture；自然语言“帮我规划上海三天”只能命中主入口。
6. 分别用“查北京到上海高铁”“把行程做成 HTML”等自然语言验证**不会**隐式命中子 Skill；再用 `$search-china-trains`、`$render-china-trip` 验证显式调用仍可用。
7. 暂时同时启用旧插件，验证出现固定互斥提示且零 provider calls；随即恢复互斥状态。
8. 重启一次并复测，确认安装缓存副本与 source 版本均为 `0.1.0`。

## 10. CLI 本地安装验证路径

本阶段不执行；阶段三在隔离 Codex home/测试账户运行：

```text
codex plugin marketplace add /ABS/PATH/marketplace-root
codex plugin marketplace list
codex plugin add china-trip-weaver@china-trip-weaver-local --json
codex plugin list
```

CLI selector 形状与 marketplace 命令来自锁定的本机帮助和官方规范。[依据：官方规范核查 8](../research/01-codex-spec.md#8-codex-plugin-marketplace-命令)

然后新建会话，重复桌面路径第 5–8 步，并额外断言：MCP server 名为 `china-rail/variflight`；12306 tools/list 与固定 fingerprint 一致；无 `VARIFLIGHT_API_KEY` 时不调用其业务 tool；卸载/重装后没有旧 cache 版本。任何安装命令都不得在本设计阶段运行。

## 11. 重名与抢触发消除表

| 参考能力 | 原冲突 | 本插件处理 | 验收 |
|---|---|---|---|
| `china-travel-assistant/plan-china-trip` | **完全同名**，显式/隐式均歧义 | 互斥安装，检测不确定即 fail closed | 同装时固定提示、0 provider calls |
| `trip-planner` | trip/flight/hotel/navigation/HTML 全吃 | 不打包；其思想拆入窄子 Skills，全部 explicit-only | 自然语言不出现该 Skill |
| `travel-plan-viz` | “目的地+天数”也从零规划 | 不打包；`render-china-trip` 只接已验证 Trip | renderer 缺 Trip 时拒绝研究/规划 |
| FlyAI Skill | priority 90 + travel 宽触发 | 不打包原 Skill；只 pin CLI，由主入口 adapter 调 | catalog 中无 `flyai` Skill |
| `amap-lbs-skill` | 搜/找/附近/路线/规划均触发 | 不打包；HTTP adapter + explicit mobility Skill | 普通路线问句仍由主入口裁决 |
| `weekend-city-trip` | always invoke 中国城市短途 | 不打包；研究阶段成为 explicit-only 子 Skill | 周末请求只命中主入口 |
| `12306-skill` / FlyAI train | 与铁路入口三抢一 | 已证伪 `12306-skill` 永不启用；12306 MCP 为事实主源 | 无 `12306-skill` package/config |
| VariFlight / OR-Tools | 本身无 Skill 同名 | 仅工具/可选库，由主入口阈值控制 | 不出现在 Skill selector |

该表落实研究中的完整冲突矩阵，不依赖 selector 让用户猜。[依据：研究必答专题 A](../research/04-design-insights.md#必答专题-a重名与触发竞争)
