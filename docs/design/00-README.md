# ChinaTripWeaver 阶段二设计索引

本目录把已验收的 `research/` 结论冻结为阶段三实现合同。本阶段只有架构/数据/测试设计，不含产品代码；唯一可执行文件是用于验证示例的 [`schema/check_schema.py`](schema/check_schema.py)。决策冲突以 ADR 为准，未裁决项见 [`BLOCKED.md`](../../BLOCKED.md)。

2026-09-23 的待审阅 v2 渲染候选另见[能力映射](renderer/v2-capability-map.md)和[ADR-0023](adr/0023-versioned-journey-profile.md)。下列 01–09 与 ADR-0006 仍描述已接受的 v1 合同；候选尚未通过视觉和生产安全迁移验收。

## 1. 阅读顺序与文件

| 顺序 | 文件 | 用途 |
|---:|---|---|
| 1 | [`01-product-scope.md`](01-product-scope.md) | 用户、三个必做场景、MVP/非目标、无 Key E2E 验收 |
| 2 | [`02-plugin-skills.md`](02-plugin-skills.md) | manifest、9 Skills、唯一 implicit 路由、MCP/marketplace、安装与冲突 |
| 3 | [`03-trip-model.md`](03-trip-model.md) | Trip 语义、坐标/claim/price/mode/revision/patch 合同 |
| 4 | [`trip.schema.json`](../../plugins/china-trip-weaver/schema/trip.schema.json) | JSON Schema Draft 2020-12 权威机器形状（真身在 `plugins/china-trip-weaver/schema/`） |
| 5 | [`04-providers.md`](04-providers.md) | Adapter、provider、timeout/probe/fixture、证据与五级降级 |
| 6 | [`05-credentials.md`](05-credentials.md) | env→0600 file 优先级、最小注入、五条 secret 禁令 |
| 7 | [`06-pipeline.md`](06-pipeline.md) | research→candidate→matrix→schedule→validate→render、replan |
| 8 | [`07-renderer.md`](07-renderer.md) | 单一确定性手机 HTML、离线/地图/图片/安全/validator |
| 9 | [`08-testing.md`](08-testing.md) | Provider、scheduler、renderer、无 Key E2E 四层判定标准 |
| 10 | [`09-impl-map.md`](09-impl-map.md) | 阶段三未来仓库树、逐模块职责/依赖/章节/DoD |

辅助证据：

- [`evidence/task0-runtime.txt`](evidence/task0-runtime.txt)：阶段二前提核验原始输出。
- [`evidence/task3-schema-validation.txt`](evidence/task3-schema-validation.txt)：Schema valid/invalid 双向实际输出。
- [`tests/fixtures/trips/schema/valid/`](../../tests/fixtures/trips/schema/valid/)：2 个可通过 Trip。
- [`tests/fixtures/trips/schema/invalid/`](../../tests/fixtures/trips/schema/invalid/)：4 个各只破坏一个约束的 Trip。

顶层 Markdown 正好 10 份（本索引 + 01–09），符合设计文档 ≤10；ADR 单独位于 `adr/`。

## 2. ADR

| ADR | 决定 |
|---|---|
| [`ADR-0001`](adr/0001-exclusive-plan-china-trip.md) | 保留 `plan-china-trip`，与旧同名插件互斥，只有主入口 implicit |
| [`ADR-0002`](adr/0002-python39-stdlib-runtime.md) | Python 3.9 标准库 core；Node 固定工具；不手动 venv |
| [`ADR-0003`](adr/0003-native-wgs84-gcj02-coordinates.md) | native + WGS-84 + GCJ-02 + conversion provenance |
| [`ADR-0004`](adr/0004-provider-portfolio.md) | 12306/FlyAI/AMap 主组合，VariFlight/AnySearch 可选 |
| [`ADR-0005`](adr/0005-optional-ortools.md) | light scheduler 默认，OR-Tools 显式阈值切换 |
| [`ADR-0006`](adr/0006-single-deterministic-renderer.md) | v1 单一、确定性、zero-remote-script HTML renderer |
| [`ADR-0007`](adr/0007-claim-level-evidence.md) | claim 级 evidence、typed price、health/mode |
| [`ADR-0008`](adr/0008-read-only-transaction-boundary.md) | 永久止步查询/比较/HTTPS deep link，不做交易 |
| [`ADR-0009`](adr/0009-rename-rail-air-skills.md) | 铁路与航空 Skill 更名，避免与旧同名插件混淆 |
| [`ADR-0010`](adr/0010-candidate-file-planning-and-live-rail.md) | 以候选文件驱动规划，铁路走实时边界（12306 固定版本 MCP） |
| [`ADR-0011`](adr/0011-live-amap-flyai-variflight-boundaries.md) | AMap、FlyAI、VariFlight 三家实时调用的边界与降级档位 |
| [`ADR-0012`](adr/0012-open-source-under-mit.md) | 本项目自有代码以 MIT 开源 |
| [`ADR-0013`](adr/0013-stay-off-the-public-marketplace.md) | 不上公开市场；FlyAI 只作可选增强 |
| [`ADR-0014`](adr/0014-remove-ortools-bridge.md) | 移除从未接线的 OR-Tools 桥；轻量排程是唯一引擎 |
| [`ADR-0015`](adr/0015-refresh-event.md) | `ctw replan --rail-result` 把 refresh 事件接到实时铁路查询 |
| [`ADR-0016`](adr/0016-rental-car-and-ferry.md) | 租车与轮渡作为一等交通腿 |
| [`ADR-0017`](adr/0017-transport-candidates.md) | 租车/轮渡腿的来源，以及暂缓做候选生产者 |
| [`ADR-0018`](adr/0018-map-and-images.md) | 手机页不放交互地图与图片，改用离线位置示意 |
| [`ADR-0019`](adr/0019-second-price-source.md) | 逐价格类别判断是否值得加第二价源 |
| [`ADR-0020`](adr/0020-locked-service-assumption.md) | 「已购锁定车次」表达缺口：推荐加结构化锁定字段，报错定位为独立可做的低成本项，不隔离自由文本 |
| [`ADR-0021`](adr/0021-weather-forecast-source.md) | 天气只用高德（现有 Key）、视野当天+3 天、歧义不选、规则表提示不改排程；预报作 claim 与 `day.weather` 进 Trip，两页各一行并由 E006/JH006 回读 |
| [`ADR-0022`](adr/0022-nearby-dining-references.md) | 附近餐饮参考：扫街榜无接口，用高德周边搜索综合排序（评分/人均/菜系/营业时间/距离）＋深链跳 App；圆心是餐前最近有坐标的时段、1.5 km、前 3 家有评分的；存 `slot.dining`、E007/JH007 逐字回读；折回命令与规划器接线复用同一套规则 |
| [`ADR-0023`](adr/0023-versioned-journey-profile.md) | v2 时间剖面及 v1 旧文件兼容的候选决定；仍待独立验收 |

已接受的 ADR-0001–0022 与待审阅的 ADR-0023 分别标明状态。若阶段三 benchmark 或官方规范改变决定，新增/替代 ADR，不静默改实现常量。

## 3. 阶段三施工硬顺序

1. 复制并锁定 Schema/fixtures；实现 Python 3.9 contracts 与固定 v1 semantic validator。
2. 实现 credentials/evidence/cache/geo 安全边界及 canary tests。
3. 按 12306/host web → FlyAI/AMap → optional providers 顺序完成 adapters 与 fixture matrix。
4. 实现 matrix/light scheduler/replan，先过 golden/no-solution 再接 pipeline。
5. 实现唯一 renderer，过安全/离线/mobile/a11y 门。
6. 最后落 package/Skills/MCP/marketplace，再做隔离 desktop/CLI 安装和 keyless E2E。

不得从 prompt 直接拼 HTML、先装 OR-Tools、复活 `12306-skill`/AMap `travelPlanner`，或把 unresolved provider shape 当实测。[依据：核心研究取舍](../research/04-design-insights.md#设计决策)

## 4. 当前设计验收命令

在项目根运行。`PY` 是任务书指定且任务 0 已验证的现有解释器；不安装任何依赖。

### 4.1 前提与 Schema 正向

```bash
ls docs/research/02-projects | wc -l
python3 --version
node --version
python3 -c 'import jsonschema;print(jsonschema.__version__)'  # 需先 pip install jsonschema

python3 \
  docs/design/schema/check_schema.py \
  plugins/china-trip-weaver/schema/trip.schema.json \
  tests/fixtures/trips/schema/valid
```

期望：项目数 11；运行时与 [`evidence/task0-runtime.txt`](evidence/task0-runtime.txt) 一致；两个 valid 都打印 `PASS`，exit 0。

### 4.2 Schema 反向

```bash
python3 \
  docs/design/schema/check_schema.py \
  plugins/china-trip-weaver/schema/trip.schema.json \
  tests/fixtures/trips/schema/invalid
test $? -eq 1
```

期望：四个 invalid 都打印 `FAIL`，validator exit 1；随后 `test` exit 0。反向命令本身的非零是预期验收，不是测试故障。

### 4.3 数量、字段与代码边界

```bash
test "$(find docs/design -maxdepth 1 -type f -name '*.md' | wc -l | tr -d ' ')" -le 10
test "$(find docs/design/adr -maxdepth 1 -type f -name '*.md' | wc -l | tr -d ' ')" -ge 8
test "$(wc -l < docs/design/schema/check_schema.py | tr -d ' ')" -le 60

test "$(find docs/design -type f \( -name '*.py' -o -name '*.js' -o -name '*.ts' \) \
  ! -path 'docs/design/schema/check_schema.py' | wc -l | tr -d ' ')" -eq 0

for f in docs/design/adr/*.md; do
  rg -q '^[-] \*\*Status:\*\*' "$f" &&
  rg -q '^## Context$' "$f" &&
  rg -q '^## Decision$' "$f" &&
  rg -q '^## Consequences$' "$f" &&
  rg -q '^## Evidence$' "$f" || exit 1
done
```

期望：10 份顶层设计文档、8 份 ADR、checker ≤60 行、除 checker 外无 `.py/.js/.ts`、每 ADR 五段齐全。

### 4.4 边界与完整性审计

```bash
find research -type f -newer design/evidence/task0-runtime.txt -print
find design -type f | sort
ls -1A
rg -n 'allow_implicit_invocation|只有.*implicit|全部.*false' design/02-plugin-skills.md design/adr/0001-exclusive-plan-china-trip.md
rg -n '12306-skill|travelPlanner|下单|实名|支付|mock_notice|price_type|source_crs' design
```

期望：第一条无输出（本阶段开始后没有修改 research）；顶层只是在原有 `research/`、`PROGRESS.md`、`BLOCKED.md` 旁新增 `design/`；路由文档明确 1 个 implicit + 8 个 false；已证伪方案只以禁止语境出现，交易/证据/Schema 硬词均可抽查。

## 5. 阶段三最终发布门（尚未执行）

实现完成后以 [`08-testing.md`](08-testing.md) 的四层标准为准：Provider fixture 全错误矩阵、scheduler 20+ golden/8+ no-solution/4 replan、renderer E001–E204 + offline/mobile/a11y、固定无 Key 请求完整 P0–P6。只跑 smoke 或只生成文件不能验收。[依据：研究决策 21](../research/04-design-insights.md#21-采用四层测试不把能启动能打印当测试)

公开 marketplace 还需先裁决 `BLOCKED.md` 的 provider ToS/license/metadata；同名 Skill 自动检测仍需隔离 Codex home/UI 实测。它们不阻塞本地按本设计施工，但禁止提前声称已解决。
