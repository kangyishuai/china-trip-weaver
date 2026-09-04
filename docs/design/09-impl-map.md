# 阶段三实现地图

这是未来仓库/插件 package 的目录与完成定义，不是本阶段要创建的代码。核心使用系统 Python 3.9 标准库，Node 只承载固定版本 MCP/CLI；默认路径不依赖手动 venv。[依据：官方插件布局](../research/01-codex-spec.md#2-插件目录与-pluginjson)、[运行时研究取舍](../research/04-design-insights.md#14-采用or-tools-作为复杂日程可选引擎不作为无条件依赖)

## 1. 未来目录树

```text
.
├── .agents/plugins/marketplace.json
├── plugins/china-trip-weaver/
│   ├── .codex-plugin/plugin.json
│   ├── .mcp.json
│   ├── skills/
│   │   ├── plan-china-trip/{SKILL.md,agents/openai.yaml}
│   │   ├── research-china-destination/{SKILL.md,agents/openai.yaml}
│   │   ├── search-china-trains/{SKILL.md,agents/openai.yaml}
│   │   ├── search-china-flights/{SKILL.md,agents/openai.yaml}
│   │   ├── search-china-lodging/{SKILL.md,agents/openai.yaml}
│   │   ├── resolve-china-mobility/{SKILL.md,agents/openai.yaml}
│   │   ├── schedule-china-trip/{SKILL.md,agents/openai.yaml}
│   │   ├── replan-china-trip/{SKILL.md,agents/openai.yaml}
│   │   └── render-china-trip/{SKILL.md,agents/openai.yaml}
│   ├── scripts/ctw
│   ├── src/china_trip_weaver/
│   │   ├── __init__.py
│   │   ├── cli.py
│   │   ├── contracts.py
│   │   ├── validate_trip.py
│   │   ├── errors.py
│   │   ├── clock.py
│   │   ├── credentials.py
│   │   ├── evidence.py
│   │   ├── cache.py
│   │   ├── geo.py
│   │   ├── matrix.py
│   │   ├── pipeline.py
│   │   ├── providers/
│   │   │   ├── base.py
│   │   │   ├── host_web.py
│   │   │   ├── rail12306.py
│   │   │   ├── flyai.py
│   │   │   ├── amap.py
│   │   │   ├── variflight.py
│   │   │   └── anysearch.py
│   │   ├── scheduler/{light.py,ortools_bridge.py}
│   │   ├── replan.py
│   │   └── render/{html.py,validate_html.py,template.py}
│   ├── schema/trip.schema.json
│   ├── assets/renderer.css
│   └── references/{credentials.md,provider-contracts.md}
├── tests/
│   ├── fixtures/{providers,trips,scheduler,renderer}/
│   ├── test_contracts.py
│   ├── test_credentials.py
│   ├── test_evidence.py
│   ├── test_geo.py
│   ├── test_providers.py
│   ├── test_scheduler.py
│   ├── test_replan.py
│   ├── test_renderer.py
│   ├── test_keyless_e2e.py
│   ├── test_skills.py
│   └── test_packaging.py
└── THIRD_PARTY_NOTICES.md
```

`.codex-plugin/plugin.json` 是 `.codex-plugin/` 中唯一文件；`.mcp.json`、Skills 和 assets 位于插件根。[依据：官方插件目录](../research/01-codex-spec.md#2-插件目录与-pluginjson)

## 2. Package、入口与 Skills

| 路径/模块 | 一行职责 | 依赖 | 设计对应 | 完成定义 |
|---|---|---|---|---|
| `.agents/plugins/marketplace.json` | 暴露 local marketplace 条目 | plugin root | §02.7；[规范 §7](../research/01-codex-spec.md#7-marketplace位置与-claude-兼容) | CLI/desktop 两路径可发现，path/policy/category 与设计一致 |
| `.codex-plugin/plugin.json` | 插件身份与 components/interface | Skills、`.mcp.json` | §02.2；[规范 §2.1](../research/01-codex-spec.md#21-字段清单) | 安装成功；字段逐值测试；无内部扩展 |
| `.mcp.json` | 固定 12306/VariFlight stdio MCP | Node/npx/env names | §02.6；[规范 §5.2](../research/01-codex-spec.md#52-插件内mcpjson) | exact pins、tools probe、无 secret value |
| `skills/plan-china-trip` | 唯一 implicit 编排入口与交易/互斥门 | 全部 explicit Skills、CLI | §02.3–5；[决策 3](../research/04-design-insights.md#3-采用主-skill-独占宽泛旅行意图子-skill-默认禁止隐式调用) | description 原文一致、implicit=true、三场景 routing tests 通过 |
| `skills/research-china-destination` | 显式日期化内容研究 | host web/AnySearch adapter | §02.3、§06 P1；[决策 10](../research/04-design-insights.md#10-采用内容调研维度按用户城市动态生成不采用固定喜茶十大商场章节) | implicit=false；输出 candidates+claims，不生成 itinerary prose |
| `skills/search-china-trains` | 显式铁路查询归一 | rail adapter/MCP | §02.3、§04.4.2；[决策 7](../research/04-design-insights.md#7-采用12306-mcp-为铁路主-provider不采用当前-12306-skill) | implicit=false；只读；fixture/error/degrade 全过 |
| `skills/search-china-flights` | 显式航班主查/增强 | FlyAI/VariFlight | §02.3、§04.4.3；[决策 8](../research/04-design-insights.md#8-采用flyai-主查可售航班酒店variflight-只做航空增强) | implicit=false；identity/conflict/price tests 全过 |
| `skills/search-china-lodging` | 显式住宿片区/候选/深链 | FlyAI/degrade | §02.3、§04.4.4；[决策 9](../research/04-design-insights.md#9-采用住宿交付片区-dated-deep-links-可核验条件不编造房价) | implicit=false；未知房价不编造；dated link 有 context |
| `skills/resolve-china-mobility` | 显式 POI/geocode/route matrix | AMap/geo/matrix | §02.3、§06 P3；[决策 12](../research/04-design-insights.md#12-不采用amap-lbs-skill-的-travelplanner采用其底层-poiroute-provider-角色) | implicit=false；真实 route/CRS/estimate 分明 |
| `skills/schedule-china-trip` | 显式 deterministic schedule/no-solution | scheduler/validator | §02.3、§06 P4；[决策 14](../research/04-design-insights.md#14-采用or-tools-作为复杂日程可选引擎不作为无条件依赖) | implicit=false；20 golden/8 no-solution/invariants 全过 |
| `skills/replan-china-trip` | 显式 versioned local patch | replan/scheduler/providers | §02.3、§06.7；[决策 15](../research/04-design-insights.md#15-采用局部重排是-versioned-patch不是重跑全计划) | implicit=false；4 disruption goldens；范围外 bytes 相同 |
| `skills/render-china-trip` | 显式 schema-valid Trip → HTML | render/validator | §02.3、§07；[决策 16](../research/04-design-insights.md#16-采用v1-只做一个-deterministic-手机-html-renderer) | implicit=false；不研究/改 facts；renderer layer 全过 |
| `scripts/ctw` | 默认 shell 可直接运行的薄入口 | system `python3` | ADR-0002；[任务 0](evidence/task0-runtime.txt) | executable；不需 activate/install；转发稳定 exit codes |

## 3. Core modules

| 模块 | 一行职责 | 依赖 | 设计对应 | 完成定义 |
|---|---|---|---|---|
| `__init__.py` | 公开 package/version 常量 | stdlib | ADR-0002 | `0.1.0` 与 manifest 单源测试一致 |
| `cli.py` | `doctor/plan/replan/render/validate` 参数与 JSON I/O | pipeline/validators | §02、§06 | argv 无 secrets；每命令 help/exit/golden tests |
| `contracts.py` | 构造/序列化 Trip、AdapterResult、matrix/patch plain data | stdlib dataclasses/json | §03；[决策 4](../research/04-design-insights.md#4-采用一个版本化-itineraryjson-是所有层的唯一事实源) | Python 3.9；canonical JSON；schema examples round-trip |
| `validate_trip.py` | 无第三方依赖的 release-critical shape/语义校验 | contracts/geo | §03.8、§06.6 | 与 JSON Schema fixtures/invalid cases一致；cross-ref/time/mode/patch gates 完整 |
| `errors.py` | 稳定 error/health taxonomy | stdlib | §04.1.2 | 每 class 映射、retry flag、public message 有 tests |
| `clock.py` | Asia/Shanghai clock 与 injectable test clock | datetime/zoneinfo | §06/§08 | 不使用 host local date；fixed clock deterministic |
| `credentials.py` | env→0600 file allowlist resolver/最小注入/redaction | os/stat/pathlib | §05；[决策 18](../research/04-design-insights.md#18-不采用聊天cli-参数源码目录html-中保存-key) | permission/symlink/parser/isolation/canary tests 全过 |
| `evidence.py` | claim creation、dedupe、conflict/freshness/raw refs | contracts/clock | §03.4、§04 | 每外部事实 claim 五字段；conflict 不覆盖 |
| `cache.py` | 最小 normalized cache、TTL、mode 与 ToS disable | evidence/clock | §04.5–6 | context-complete keys；no secret/personal data；TTL tests |
| `geo.py` | CRS 标记与单次 WGS84↔GCJ02 转换 | math only | §03.3；[决策 11](../research/04-design-insights.md#11-采用同时保存-provider-native-与规范化坐标不做无标记的单坐标) | known points/边界/unknown/double-conversion tests |
| `matrix.py` | bounded route query plan、cell 合并与 coverage | geo/providers/evidence | §06.4；[决策 13](../research/04-design-insights.md#13-采用先真实-travel-time-matrix再排-time-windows不以直线连线冒充路线) | final hops covered；unreachable/estimate 不伪 live |
| `pipeline.py` | P0–P6 状态机、checkpoint、取消与 stage invalidation | all core | §06.1–2 | resume/hash/version tests；失败不越 stage boundary |

`validate_trip.py` 不尝试重新实现任意 JSON Schema 引擎；它实现本产品固定 v1 release-critical checks，并用设计期 `jsonschema` suite 交叉验证。完整 Draft 2020-12 校验保留在 CI/开发工具，不让默认 `python3` 依赖手动 venv。此取舍见 ADR-0002。

## 4. Provider modules

| 模块 | 一行职责 | 依赖 | 设计对应 | 完成定义 |
|---|---|---|---|---|
| `providers/base.py` | ProviderRequest/Result、deadline/subprocess/HTTP 抽象 | errors/clock/evidence | §04.1 | success/error/timeout/wrong-shape harness 复用 |
| `host_web.py` | 接收宿主 web 结果并归一 official claims | base/evidence | §04.4.1；[Q8](../research/05-open-questions.md#q8-目的地调研应使用内置-webanysearch还是两者组合) | URL/date/conflict fixtures；无工具时 degraded |
| `rail12306.py` | 调 8 个 MCP tools、解析 text JSON | base/cache | §04.2–4.2；[决策 7](../research/04-design-insights.md#7-采用12306-mcp-为铁路主-provider不采用当前-12306-skill) | exact pin/fingerprint；rail fixture matrix 全过 |
| `flyai.py` | probe 1.0.16 CLI 并归一 flight/hotel | base/credentials | §04.2–4.4；[Q3](../research/05-open-questions.md#q3-fly-aiflyai-cli-的当前-commandschemakeyless-trial-到底是什么) | 不猜 command；trial/key/error/wrong-shape 全过 |
| `amap.py` | stdlib HTTP POI/geocode/routes，GCJ02 标记 | base/credentials/geo | §04.3–4.5；[Q5](../research/05-open-questions.md#q5-amap-当前-web-api-的-v3v4v5-schemacrs-与-route-quota-能否形成稳定-adapter) | endpoints/probe/quota/error/CRS fixtures 全过 |
| `variflight.py` | 调可选 MCP 航空增强并对齐 flight identity | base/credentials | §04.2–4.3；[Q6](../research/05-open-questions.md#q6-航班价格库存状态跨-flyai-与-variflight-如何同一航段对齐) | 9-tool fingerprint；无 Key 0 business call；conflict tests |
| `anysearch.py` | 可选搜索补充，拒绝 auto-registration | base/credentials | §04.2–4.1；[Q8](../research/05-open-questions.md#q8-目的地调研应使用内置-webanysearch还是两者组合) | 默认 off；usage/402/429/auto-key fixtures 全过 |

## 5. Scheduler、replan 与 renderer

| 模块 | 一行职责 | 依赖 | 设计对应 | 完成定义 |
|---|---|---|---|---|
| `scheduler/light.py` | beam insertion + bounded local improvement | contracts/matrix | §06.5 | deterministic；20 golden/8 no-solution/property gates |
| `scheduler/ortools_bridge.py` | 可选进程边界与统一结果验证 | optional configured runner | §06.5.3；[Q10](../research/05-open-questions.md#q10-轻量排程与-or-tools-的切换阈值是什么) | default import/install=0；flag/threshold/5s/fallback tests |
| `replan.py` | 影响传播、白名单 patch、stability/reverify | scheduler/evidence/validator | §06.7；[决策 15](../research/04-design-insights.md#15-采用局部重排是-versioned-patch不是重跑全计划) | revision conflict、replay、locks、范围外 byte tests |
| `render/template.py` | 固定安全 HTML skeleton/components | stdlib | §07.2–5 | 无 provider/clock/network；escape contexts tested |
| `render/html.py` | Trip→deterministic single file | template/contracts | §07.1–6；[决策 16](../research/04-design-insights.md#16-采用v1-只做一个-deterministic-手机-html-renderer) | repeat hash same；embedded Trip exact；zero remote script |
| `render/validate_html.py` | E001–E204 DOM/security/fact/a11y gate | stdlib HTML parser + test browser harness | §07.7 | normal=0 errors；adversarial expected codes；exit 1 on error |
| `assets/renderer.css` | inline mobile/print/a11y styles source | none | §07.3 | bundled inline；320px no overflow；AA/print checks |
| `schema/trip.schema.json` | package copy of authoritative v1 contract | none | §03；[决策 4](../research/04-design-insights.md#4-采用一个版本化-itineraryjson-是所有层的唯一事实源) | byte/hash sync test against design-approved schema |
| `references/credentials.md` | 面向用户的变量名、0600 配置/轮换和无 Key 行为 | `credentials.py` 合同 | §05；[决策 18](../research/04-design-insights.md#18-不采用聊天cli-参数源码目录html-中保存-key) | 不含值/过时 quota；配置步骤通过专用 home 验证 |
| `references/provider-contracts.md` | 公开 pins、capability、probe、timeout、降级与已知边界 | provider adapters | §04；[决策 22](../research/04-design-insights.md#22-采用所有外部-climcp-固定版本-启动时-contract-probe) | 与代码常量/fixtures 单源测试一致，开放项不写成实测 |

## 6. Tests、fixtures 与 notices

| 模块 | 一行职责 | 依赖 | 设计对应 | 完成定义 |
|---|---|---|---|---|
| `tests/fixtures/providers` | 脱敏 raw→normalized contract corpus | provider pins | §08.2 | 每 provider 7 类；manifest/hash/redaction/secret scan |
| `tests/fixtures/trips` | valid/invalid/schema/revision/adversarial Trips | schema | §03、§08.4 | 与设计 examples 同步；每 invalid 单因 |
| `tests/fixtures/scheduler` | 20+ golden、8+ no-solution、4 replan | matrix/trips | §08.3 | corpus 数量/coverage assertions |
| `tests/fixtures/renderer` | snapshots/DOM expectations | renderer | §08.4 | mobile/desktop/print/offline references 审核 |
| `test_contracts.py` | schema/canonical/cross-ref tests | contracts/validator | §03、§08 | Python 3.9 pass；design checker 交叉 pass |
| `test_credentials.py` | 0600/parser/isolation/五禁令 canary | credentials | §05、§08 | secret scan 0；invalid permissions fail closed |
| `test_evidence.py` | claim/price/health/freshness/conflict | evidence/cache | §03.4–5、§04 | external fact coverage 100% |
| `test_geo.py` | CRS known points/边界/double conversion | geo | §03.3 | bounded error；unknown 不转 |
| `test_providers.py` | 全 adapter fixture matrix | providers | §08.2 | success→wrong-shape 全门通过 |
| `test_scheduler.py` | golden/no-solution/property/threshold | schedulers | §08.3 | exact pass criteria 全满足 |
| `test_replan.py` | 4 disruptions、revision/stability/reverify | replan | §08.3 | scope 外 bytes 100% 相同 |
| `test_renderer.py` | determinism/DOM/security/offline/mobile | render | §08.4 | E001–E204、browser checks 全绿 |
| `test_keyless_e2e.py` | 固定 request 完整 P0–P6 | pipeline/fixtures | §08.5 | schema+HTML+truth+no-secret+determinism 全绿 |
| `test_skills.py` | 9 Skill metadata/policy/routing static checks | skill files | §02、§08.6 | 1 true + 8 false；description exact |
| `test_packaging.py` | manifest/MCP/marketplace/pins/notices | package files | §02、§08.6 | local install artifact complete；无 forbidden files |
| `THIRD_PARTY_NOTICES.md` | 代码/数据/服务 provenance 与条款状态 | legal review | §04/§05；[Q14](../research/05-open-questions.md#q14-发布前许可证服务条款与-marketplace-metadata-还缺什么) | local release 列 pins/licenses；public release 前 blockers cleared |

## 7. 实现顺序与阶段退出条件

1. **Contract first**：复制 Schema、contracts/validator/errors/clock；设计 examples 全通过。
2. **Safety boundary**：credentials/evidence/cache/geo；canary 与 CRS tests 全过。
3. **Provider adapters**：逐个以 fixtures 完成，先 12306/host web，再 FlyAI/AMap，最后 optional providers。
4. **Planning core**：matrix/light scheduler/replan；golden/no-solution 全过后才接 pipeline。
5. **Renderer**：只接 validated Trip；安全/offline/mobile gate 全过。
6. **Skills/package**：metadata/routes/marketplace/MCP；静态与隔离安装门。
7. **E2E**：keyless deterministic 必过；live smoke opt-in；公开发布另过 legal metadata。

每步 DoD 是表中测试证据，不是文件存在。阶段三不得绕过前置合同直接从 prompt 拼 HTML。
