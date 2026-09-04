# ChinaTripWeaver 阶段二设计索引

本目录把已验收的 `research/` 结论冻结为阶段三实现合同。本阶段只有架构/数据/测试设计，不含产品代码；唯一可执行文件是用于验证示例的 [`schema/check_schema.py`](schema/check_schema.py)。决策冲突以 ADR 为准，未裁决项见 [`BLOCKED.md`](../../BLOCKED.md)。

## 1. 阅读顺序与文件

| 顺序 | 文件 | 用途 |
|---:|---|---|
| 1 | [`01-product-scope.md`](01-product-scope.md) | 用户、三个必做场景、MVP/非目标、无 Key E2E 验收 |
| 2 | [`02-plugin-skills.md`](02-plugin-skills.md) | manifest、9 Skills、唯一 implicit 路由、MCP/marketplace、安装与冲突 |
| 3 | [`03-trip-model.md`](03-trip-model.md) | Trip 语义、坐标/claim/price/mode/revision/patch 合同 |
| 4 | [`schema/trip.schema.json`](schema/trip.schema.json) | JSON Schema Draft 2020-12 权威机器形状 |
| 5 | [`04-providers.md`](04-providers.md) | Adapter、provider、timeout/probe/fixture、证据与五级降级 |
| 6 | [`05-credentials.md`](05-credentials.md) | env→0600 file 优先级、最小注入、五条 secret 禁令 |
| 7 | [`06-pipeline.md`](06-pipeline.md) | research→candidate→matrix→schedule→validate→render、replan |
| 8 | [`07-renderer.md`](07-renderer.md) | 单一确定性手机 HTML、离线/地图/图片/安全/validator |
| 9 | [`08-testing.md`](08-testing.md) | Provider、scheduler、renderer、无 Key E2E 四层判定标准 |
| 10 | [`09-impl-map.md`](09-impl-map.md) | 阶段三未来仓库树、逐模块职责/依赖/章节/DoD |

辅助证据：

- [`evidence/task0-runtime.txt`](evidence/task0-runtime.txt)：阶段二前提核验原始输出。
- [`evidence/task3-schema-validation.txt`](evidence/task3-schema-validation.txt)：Schema valid/invalid 双向实际输出。
- [`schema/examples/valid/`](schema/examples/valid/)：2 个可通过 Trip。
- [`schema/examples/invalid/`](schema/examples/invalid/)：4 个各只破坏一个约束的 Trip。

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

8 份均含 Status/Context/Decision/Consequences/Evidence。若阶段三 benchmark 或官方规范改变决定，新增/替代 ADR，不静默改实现常量。

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
ls research/02-projects | wc -l
python3 --version
node --version
~/miniconda3/bin/python3 -c 'import jsonschema;print(jsonschema.__version__)'

~/miniconda3/bin/python3 \
  design/schema/check_schema.py \
  design/schema/trip.schema.json \
  design/schema/examples/valid
```

期望：项目数 11；运行时与 [`evidence/task0-runtime.txt`](evidence/task0-runtime.txt) 一致；两个 valid 都打印 `PASS`，exit 0。

### 4.2 Schema 反向

```bash
~/miniconda3/bin/python3 \
  design/schema/check_schema.py \
  design/schema/trip.schema.json \
  design/schema/examples/invalid
test $? -eq 1
```

期望：四个 invalid 都打印 `FAIL`，validator exit 1；随后 `test` exit 0。反向命令本身的非零是预期验收，不是测试故障。

### 4.3 数量、字段与代码边界

```bash
test "$(find design -maxdepth 1 -type f -name '*.md' | wc -l | tr -d ' ')" -le 10
test "$(find design/adr -maxdepth 1 -type f -name '*.md' | wc -l | tr -d ' ')" -ge 8
test "$(wc -l < design/schema/check_schema.py | tr -d ' ')" -le 60

test "$(find design -type f \( -name '*.py' -o -name '*.js' -o -name '*.ts' \) \
  ! -path 'design/schema/check_schema.py' | wc -l | tr -d ' ')" -eq 0

for f in design/adr/*.md; do
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
