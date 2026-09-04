# 测试策略与判定标准

阶段三测试按四层发布门组织；“能安装、能启动、能打印 JSON/HTML”都不是通过。每层必须有 assertions、稳定 fixture 和非零失败退出；live provider smoke 是补充证据，不替代可重复门禁。[依据：研究决策 21](../research/04-design-insights.md#21-采用四层测试不把能启动能打印当测试)

## 1. 共同测试原则

- 默认 tests 不用真实 Key、不改用户 `~/.codex`/`~/.agents`/provider config、不下单、不登录；外部写操作一律不在 suite 中。
- clock/timezone 固定 Asia/Shanghai；随机测试固定 seed；fixtures 锁 provider/version/response hash。
- 每个 failure 输出 stable code、fixture/test name 和最小 field path；禁止只打 traceback/warning 后 exit 0。
- canary secrets 仅为假值；每层结束扫描 argv/log/cache/Trip/HTML/fixture，0 命中才通过。
- 运行时基线在系统 `python3` 3.9 与 Node 24；设计期 Schema fixture 另用已存在的 Python 3.13+jsonschema。不得要求手动 activate venv。[依据：任务 0 实测](../design/evidence/task0-runtime.txt)
- provider live tests 明确 opt-in、只读、预算/频率受限，并记录 `queried_at`；不纳入离线 PR 必过，发布前可作为人工 gate。

## 2. Layer 1：Provider fixture 合同

目标：证明每个 adapter 对已锁 raw shapes 能正确归一、分类错误、生成 claims/health，并对漂移 fail closed。[依据：研究决策 22](../research/04-design-insights.md#22-采用所有外部-climcp-固定版本-启动时-contract-probe)

### 2.1 必备 fixtures

每个 provider 至少：

| 类别 | 断言 |
|---|---|
| success | normalized items 通过字段合同；每个动态字段有 claim；version/mode/time/source 正确 |
| empty | `items=[]`、health ready、`no_results`；不生成 fake candidate |
| auth missing/expired/forbidden | 精确 health/error class；不重试；进入预期无 Key rung |
| rate limit | 识别 429/provider code/Retry-After；不越总 deadline |
| timeout/network/5xx | 取消/最多一次幂等 retry；进程无泄漏；health degraded |
| wrong shape/fingerprint | `contract_mismatch`、0 normalized items、exit nonzero；不得 WARN-and-continue |
| malicious strings | provider HTML/ANSI/URL/secret-like text 不越过 normalized/escape/redaction 边界 |

Provider-specific 最小集：

- 12306：8-tool fingerprint、station、direct、no-seat、候补、中转、跨日、pipe column drift；当前真实余票尚未实测，fixture 通过前标 beta。[依据：开放问题 Q4](../research/05-open-questions.md#q4-12306-mcp-的真实余票-parser日期范围与失败恢复是否稳定)
- FlyAI：version/help、实际 command envelope、flight/hotel、trial limit、stderr error、non-JSON、price missing context；不能从 README 猜 command。[依据：开放问题 Q3](../research/05-open-questions.md#q3-fly-aiflyai-cli-的当前-commandschemakeyless-trial-到底是什么)
- AMap：POI pagination、geocode GCJ02、walking/transit/driving/riding、unreachable、401/429、v3/v4/v5 drift、边界/HK point；round-trip 误差独立断言。[依据：开放问题 Q5](../research/05-open-questions.md#q5-amap-当前-web-api-的-v3v4v5-schemacrs-与-route-quota-能否形成稳定-adapter)
- VariFlight：9-tool fingerprint、flight identity、status/weather/comfort/raw price、401/403/429、`any` wrong shape；无 Key 不发业务调用。
- web/AnySearch：official URL/date extraction、conflicting sources、404、usage/auto-register response；AnySearch 不得保存自动产生的 Key。[依据：开放问题 Q8](../research/05-open-questions.md#q8-目的地调研应使用内置-webanysearch还是两者组合)

### 2.2 判定标准

PASS 当且仅当：

1. 上述 fixture matrix 全覆盖且 assertions 全绿；success/empty/auth/rate/timeout/wrong-shape 每 provider 至少一例。
2. 每个 success 结果可合并进 `trip.schema.json` valid fixture；claim 五字段和 price type 100% 存在。
3. wrong-shape 100% fail closed；未映射 raw 字段不进入 public model。
4. timeout 不超过设计 deadline + 1s 测试容差，子进程/连接全部清理。
5. canary secret scan 0 命中；raw fixtures 有 redaction manifest/hash。

任何 provider 只通过 tools/list 或成功样例、不测失败 shape，均 FAIL。

## 3. Layer 2：排程 golden / 无解 / 局部重排

目标：证明 lightweight scheduler 在固定 matrix 下可行、确定、可解释；无解不丢约束；replan 只改影响范围。OR-Tools 只在 opt-in threshold suite 对照。[依据：研究决策 14](../research/04-design-insights.md#14-采用or-tools-作为复杂日程可选引擎不作为无条件依赖)

### 3.1 Golden corpus

至少 20 个 golden，覆盖：

- 1/2 天城市周末各 3；2–7 天跨城各类 5；moving day/早晚交通 3。
- overlapping opening windows、closed day、meal/rest、不同 pace、预算/步行限制、unreachable matrix、estimate matrix。
- locked/accepted/booking、同分 deterministic tie、候选 >8 的 prune/threshold。
- 下雨、闭馆、误车/延误、用户删点 4 个 replan golden。[依据：开放问题 Q11](../research/05-open-questions.md#q11-局部重排的最小-patchstability-contract-应是什么)

Golden 不锁完整漂亮文案，只锁：selected IDs/order/start/end、hard constraints、matrix hops、excluded reason codes、objective vector、patch operations/stability/reverify set。

### 3.2 无解集

至少 8 个单因/组合无解：两个 locked overlap、交通到达晚于 locked activity、闭馆全天、route unreachable、buffer 不足、预算硬上限、住宿 check-in/跨城冲突、所有 candidates 依赖 unknown route。每例必须返回 `NO_SOLUTION`、最小冲突解释和可选松绑项；输出不得含正常 rendered Trip。

### 3.3 Property/invariant tests

固定 seed 生成小规模 slots/windows/matrix，至少断言：

- no overlap；start < end；所有 hop duration/buffer 被计入。
- locks byte-identical；每个 scheduled ref 唯一；unreachable edge 不使用。
- 增加 travel time 不应让原 schedule 更“宽松”；删除可选 candidate 不应破坏剩余 hard feasibility。
- 同一输入重复 20 次 canonical output 相同。
- replan 范围外 canonical day bytes 相同；base revision mismatch 必须拒绝。

### 3.4 OR-Tools threshold 对照

仅当 `CTW_ENABLE_ORTOOLS=1` 且 pin 可用时，用同一 20 golden 比较 light/OR-Tools：hard feasibility 必须一致或 OR-Tools 给出更强有证据解；5s deadline；输出仍经统一 validator。阶段三正式固定阈值前记录 feasible rate、objective、cold/warm time、解释性和小改动 churn。[依据：开放问题 Q10](../research/05-open-questions.md#q10-轻量排程与-or-tools-的切换阈值是什么)

### 3.5 判定标准

PASS 当且仅当：20+ golden 全匹配关键合同，8+ 无解全部明确失败，property invariants 0 violation，determinism 20/20，相同 replan scope 外字节 100% 相同；OR-Tools 不存在/关闭不影响 default suite。

## 4. Layer 3：Renderer 校验

目标：证明 renderer 不改变事实，输出单一、确定、安全、手机/离线可读的 HTML。[依据：研究决策 16](../research/04-design-insights.md#16-采用v1-只做一个-deterministic-手机-html-renderer)

### 4.1 Fixture set

- 2 个 Schema valid examples；no-Key E2E Trip；1/7-day min/max；revision patch；mixed health/mode/unknowns。
- adversarial：`</script>`、HTML/attribute injection、RTL/emoji/超长中文、dangerous schemes、embedded URL credentials、fake API keys、provider ANSI/HTML、duplicate IDs。
- degradation：无坐标、只有 WGS、只有 GCJ、AMap missing、price unknown、all remote links offline。

### 4.2 机器判定

1. 相同 Trip 连续 render 2 次 SHA-256 相同；embedded `trip-data` parse 后 canonical-equal 输入。
2. `07-renderer.md` E001–E204 全执行；正常 fixtures error=0，adversarial fixtures 必须触发预期 code 或安全 escape 后通过。
3. DOM 中 day/slot/entity/claim counts 与 Trip 精确对应；无额外时间、价格、车次或事实。
4. remote executable/resource request=0；CSP 精确或更严；危险 URL=0；secret canary=0。
5. Chromium/headless network denied 打开无 console error/failed resource；核心 sections 仍有可读文本。
6. 320/375/430px horizontal overflow=0；375×812/1440×900/print snapshots 通过结构审阅；WCAG AA contrast、heading/landmark/focus/touch target checks 通过。
7. 位置连线若有必须含“非真实路线”标签；unknown coordinate 无默认 marker。

### 4.3 判定标准

任一安全/事实/secret/remote-script/embedded-data mismatch 为 fatal。视觉差异只有在不影响 overflow、可读性、信息顺序和 accessibility 时才可人工 accept，并记录 golden 更新理由。

## 5. Layer 4：无 Key 端到端

目标：证明不配置任何 Key 时，从固定 request 到 Trip/HTML 的主路径可交付，且每个降级真实可见。[依据：无 Key 专题](../research/04-design-insights.md#必答专题-c无-key-时如何降级)

### 5.1 必过 deterministic fixture run

输入使用 `01-product-scope.md` 的北京→上海 3 天 2 晚固定场景。测试进程使用临时 config/home，显式移除 `AMAP_WEBSERVICE_KEY/FLYAI_API_KEY/VARIFLIGHT_API_KEY/X_VARIFLIGHT_KEY/ANYSEARCH_API_KEY`，禁止读取真实 `~/.config/china-trip-weaver/credentials.env`。provider transport 使用脱敏 fixtures：12306 public success；host web official sources；FlyAI trial unavailable；AMap missing。

流程必须跑完整 P0→P6，不允许直接喂 renderer fixture。

### 5.2 可选 live no-Key smoke

在用户/CI 明确 opt-in、普通网络可用时，只发低频 public query：12306 station/dated search、host web；FlyAI trial 仅 probe 后调用。它记录实际 mode/health，不因远端波动决定 PR 成败，但发布报告必须披露失败。AMap/VariFlight/AnySearch 无 Key不调用。

### 5.3 判定标准

必过 run 同时满足：

- exit 0；Trip 通过 Schema + semantic validator；HTML renderer errors=0。
- 3 days、铁路腿/候选、住宿片区/dated deep link、POI/餐饮 candidates、slots、unknowns、provider health、只读边界均存在。
- 12306 claim 标 public fixture/live 对应 mode；AMap missing，route estimate/unknown 可见；FlyAI unavailable 后酒店 total 是 `verify-on-click/unknown`。
- 每个展示动态事实有 claim；每个 price 有 type；mock=0；secret scan=0；provider business calls 与预期清单精确相等。
- HTML 断网核心可读、remote scripts=0、Key=0；没有 purchase/login/payment/cancel/change action。
- 同 fixtures 连跑 2 次，Trip（排除测试 harness 外部路径）canonical equal，HTML hash 相同。

## 6. 安装与路由专项门

在隔离 Codex home/桌面测试账户完成，不属于普通 unit suite：

- 9 个 Skill name/目录/description 合法；只有主入口 implicit=true，8 个子项全部 false。
- 自然语言完整行程只命中主入口；子 Skill 自然关键词不隐式命中；显式 `$subskill` 可用。
- 同装 `china-travel-assistant` 时固定互斥提示、0 provider calls；移除后新会话恢复。
- desktop 无 CLI 与 CLI marketplace 两条安装路径都通过；缓存版本与 manifest `0.1.0` 一致。[依据：同名开放问题 Q1](../research/05-open-questions.md#q1-目标-plan-china-trip-与旧同名-skill-的真实-ui调用行为是什么)

## 7. 发布判定

本地/内部 v0.1 发布：四层必过门全绿、安装路由人工门全绿、8 ADR accepted、BLOCKED 中只允许明确不阻塞本地实现的事项。公开 marketplace 发布另需 `BLOCKED.md` 中法律/metadata 项裁决；live smoke 失败若有安全/合同漂移则对应 provider 默认 degraded/关闭后才可发布。
