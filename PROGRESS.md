# PROGRESS

## 书 3 开工理解（2026-09-04，≤10 行）
1. 目标：补齐 planner 已承诺的 2–7 天有序多城市能力，不收回产品、Skill 或 Schema 合同。
2. 顺序：任务 0 基线与失败复现 → 有序 legs/返程规则 → day.city/逐夜 stay → Schema → 文档与两组 demo → 全门禁与提交。
3. G1 必须走真实 `scripts/ctw plan`：5 天北京→上海→杭州→苏州，默认单向且不得凭空补苏州→北京。
4. 每日城市由带日期的 route legs 推导，跨城当天归到达城市；每个过夜日期必须恰有一个已选 stay。
5. 候选住宿与已选住宿分开，彻底移除 `lodgings[:1]` 默认路径；缺 stay 必须结构化无解。
6. 单目的地兼容是硬门：既有两组 demo 重跑后语义不变且 Trip/HTML 均有效。
7. 最大风险：无目的地停留日期字段，必须确定性分配跨城日期，同时不破坏现有首日去程/末日返程行为。
8. 边界：只写用户白名单；不碰 providers、mobility、CLI、render、scheduler，不升 0.2.0，不安装依赖或插件。

## 任务 0：基线与失败复现（完成）

- 正确 Git 根：`/Users/kangyishuai/Workspace/core/ChinaTripWeaver/china-trip-weaver`；开工 `git status --short --branch` 原始输出：

```text
## main...origin/main
```

- `/usr/bin/python3 -m unittest discover -s tests`（exit 0）原始摘要：

```text
----------------------------------------------------------------------
Ran 290 tests in 20.196s

OK
```

- `/usr/bin/python3 scripts/scan_secrets.py`（exit 0）原始输出：

```text
secret scan: 0 finding(s) across 343 file(s)
```

- G1 失败复现命令从插件根运行，使用合成 5 天北京→上海→杭州→苏州请求、既有合成 candidates、全部 provider off；exit 1 原始输出：

```text
PLAN_FAILED v1 generic planner currently requires exactly one destination
```

- 当前验收轮次：0/14。

## 任务 1：有序多城市交通腿（完成）

- `_normalize_request` 已放开多目的地并保持跨城必须有 origin；`_route_specs` 生成 origin→D1→D2→…，多城市默认不补返程，显式往返才补，最后目的地已是 origin 时不重复；单目的地旧返程规则保留。
- G1 初始红态（实现前）原始输出：

```text
test_g1_multicity_cli_builds_ordered_one_way_transport_legs (tests.test_keyless_e2e.KeylessE2ETests) ... FAIL
AssertionError: 0 != 1 : PLAN_FAILED v1 generic planner currently requires exactly one destination
Ran 1 test in 0.067s
FAILED (failures=1)
```

- 指定反向验证：临时令多城市无条件补返程，同一 G1（exit 1）原始关键输出：

```text
test_g1_multicity_cli_builds_ordered_one_way_transport_legs (tests.test_keyless_e2e.KeylessE2ETests) ... FAIL
Second list contains 1 additional elements.
First extra element 3:
('city-suzhou', 'city-beijing')
  [('city-beijing', 'city-shanghai'),
   ('city-shanghai', 'city-hangzhou'),
   ('city-hangzhou', 'city-suzhou'),
   ('city-suzhou', 'city-beijing')]
Ran 1 test in 0.084s
FAILED (failures=1)
```

- 还原后 `/usr/bin/python3 -m unittest tests.test_keyless_e2e -v`（exit 0）原始摘要：

```text
test_g1_multicity_cli_builds_ordered_one_way_transport_legs (tests.test_keyless_e2e.KeylessE2ETests) ... ok
----------------------------------------------------------------------
Ran 13 tests in 2.791s

OK
```

- 当前验收轮次：1/14。

## 任务 2：每日城市与逐夜 stay（完成）

- planner 先按实际有序 legs 推导多城市 `day.city`（跨城日归到达城市），再逐夜选择同城且覆盖日期的候选；Trip `lodgings` 仅保留已选 stay，并以 `selection_status=selected`、`candidate_ref`、`selected_nights` 与 day `stay_id` 明确关联。
- `_schedule_problems` 已彻底移除 `lodgings[:1]`，对每个 selected stay 建入住约束；POI 只排入同城日期。缺任一夜候选会在写文件前返回 `plan has no feasible stay: {"city":...,"code":"NO_STAY_FOR_NIGHT","date":...}`。
- 任务 2 实现前两项红态（exit 1）原始关键输出：

```text
test_g1_multicity_cli_builds_ordered_one_way_transport_legs ... FAIL
AssertionError: Lists differ: ['上海', '杭州', '杭州', '苏州', '苏州'] != ['上海', '上海', '上海', '上海', '上海']
test_multicity_missing_overnight_candidate_is_structured_no_solution ... FAIL
AssertionError: 1 != 0 : PLAN_COMPLETE ... errors=0
Ran 2 tests in 0.173s
FAILED (failures=2)
```

- 指定反向验证：临时把 `_trip_days` 的 `day.city` 退回 `destinations[0]`，G1（exit 1）原始输出：

```text
test_g1_multicity_cli_builds_ordered_one_way_transport_legs (tests.test_keyless_e2e.KeylessE2ETests) ... FAIL
AssertionError: Lists differ: ['上海', '杭州', '杭州', '苏州', '苏州'] != ['上海', '上海', '上海', '上海', '上海']
First differing element 1:
'杭州'
'上海'
Ran 1 test in 0.088s
FAILED (failures=1)
```

- 还原后 `/usr/bin/python3 -m unittest tests.test_keyless_e2e -v`（exit 0）原始摘要：

```text
test_g1_multicity_cli_builds_ordered_one_way_transport_legs ... ok
test_multicity_missing_overnight_candidate_is_structured_no_solution ... ok
test_multicity_return_is_explicit_or_already_present_in_destinations ... ok
----------------------------------------------------------------------
Ran 15 tests in 2.914s

OK
```

- 三份 Trip Schema 新 SHA-256（原均为 `f560fc1a...`）：

```text
b85157984c8c2af2ecf0e15b752dfc9c8cbd6c7fdfea4732d6990a57dbb4e367  ../design/schema/trip.schema.json
b85157984c8c2af2ecf0e15b752dfc9c8cbd6c7fdfea4732d6990a57dbb4e367  docs/design/schema/trip.schema.json
b85157984c8c2af2ecf0e15b752dfc9c8cbd6c7fdfea4732d6990a57dbb4e367  plugins/china-trip-weaver/schema/trip.schema.json
```

- candidates Schema SHA-256：`5dd6862717a02654bfc5f74c3db7c76f9d71176570bfc3d1331a7382af238371`。
- 当前验收轮次：2/14。

## 书 2 开工理解与任务 0（2026-09-04，≤10 行）

1. 目标：把站名解析失败从契约漂移中剥离，保留真正的 12306 工具/响应结构漂移报警。
2. 顺序：精确站名 → 城市代表站 → 城市全部车站；三层皆空 `no_results`，多候选 `ambiguous`。
3. 多候选全部返回，不替用户选；最大风险是误吞真实 shape/tool 漂移或伪造距离排序。
4. 边界：只改书 2 白名单，不碰其他书独占文件，不升版、不安装、不新增流程或依赖。
5. 基线：全量 `Ran 290 tests in 20.204s`、`OK`、skipped 0；secret scan `0 finding(s) across 343 file(s)`。
6. 调用点：`grep` 仅输出 `32:    "get-station-code-by-names",`，与任务现状一致。

## 书 2 任务 1：三层站名解析（完成）

- transport 只对未解析端点按三层继续；正常 error/空结果不抛契约异常，坏类型/坏站码继续 fail closed。
- 多候选停止票务调用并全部返回；有 `distance_meters` 时升序、未知距离末尾、同距稳定排序。真实合同缺距离信号已置顶写入 `BLOCKED.md`。
- `SKILL.md` 已明确 `--from`/`--to` 接受精确站名或城市名，以及 `no_results`/`ambiguous` 的调用方行为。
- 正向：`/usr/bin/python3 -m unittest tests.test_rail_station_fallback tests.test_mcp_stdio -v` → `Ran 18 tests in 4.490s`，`OK`，skipped 0。
- 反向红：临时令精确层返回空映射，最终 G5 → `AssertionError: 'no_results' is not None`；`Ran 1 test in 0.051s`，`FAILED (failures=1)`。
- 还原绿：同一两模块命令 → `Ran 18 tests in 4.433s`，`OK`，skipped 0；临时变更已还原。
- 书 2 当前验收轮次：6/10（意图性反向红与一次还原脚本路径笔误不计验收失败）。

## 书 2 任务 2：错误分类归位（完成）

- 四个独立合成合同测试确认 `武夷山北`、`南平市`、`昆明南`、`平潭` 都由精确站名层解析，`error_class=None`、health=`ready`。
- 三层皆空断言 `no_results` + health=`ready`；多站断言 `ambiguous` + health=`ready` 并返回全部候选；坏 station payload 仍为 `contract_mismatch`。
- 工具指纹漂移 fixture 少一个工具时，固定 8-tool 探针断言 `contract_mismatch`；`EXPECTED_12306_TOOLS` 最终字节未改。
- 最终正向：`/usr/bin/python3 -m unittest tests.test_rail_station_fallback -v` → `Ran 12 tests in 0.643s`，`OK`，skipped 0。
- 反向红：临时从工具指纹常量移除 fixture 同样缺失的工具后，指纹回归 → `AssertionError: 'contract_mismatch' != None`；`Ran 1 test in 0.052s`，`FAILED (failures=1)`。
- 还原绿（反向验证当时）：同一模块 → `Ran 10 tests in 0.536s`，`OK`，skipped 0；随后新增两个正向边界测试，最终为 12 条全绿，临时常量变更已还原。
- 书 2 当前验收轮次：7/10（两次意图性反向红均不计连续失败）。

## 书 1 开工理解（2026-09-04，≤10 行）

1. 目标：高德地点不能再凭错误或歧义坐标冒充 verified；无法可靠确认身份时必须返回 unknown。
2. 顺序：基线核对 → POI 文本搜索与身份唯一性 → 三类语义离群降级 → 红绿反向验证 → 全量门禁与提交。
3. 正确性优先；首/次名称相似度差 `<0.15` 或首条行政区不符即 `identity_conflict` 且无坐标。
4. POI claim 保留 provider identity、匹配名、地址、行政区、adcode、类型与 business；仅完整地址继续 geocode。
5. 同日同城相邻点直线距离 `>50km` 仅警告，但命中的 claim 不得继续标 verified。
6. 只改书 1 白名单；不碰 planning、schema、CLI、MCP stdio、rail12306、CI、版本与依赖。
7. 最大风险：城市层级/别名误判、相似度边界错误，以及离群规则误伤合法远郊实体。

## 书 1 任务 0：基线（完成）

- `/usr/bin/python3 -m unittest discover -s tests` → `Ran 290 tests in 19.909s`、`OK`、skipped 0；`/usr/bin/python3 scripts/scan_secrets.py` → `0 finding(s) across 343 file(s)`。
- `rg -n 'capability=' .../mobility.py` 仅列 `geocode`（145）与 `route`（189）；其余 `poi` 命中均为数据字段/声明，无 POI 调用点。

## 书 1 任务 1：POI 身份（完成）

- POI 先走 v5 text（`city_limit=true`、2 候选），保留 identity/business claims；歧义、POI/geocode 行政区不符或地址不完整均不写坐标；MobilityLocation 使用 provider name/city。
- G3/G4 正向：`/usr/bin/python3 -m unittest tests.test_providers tests.test_amap_live -v` → `Ran 103 tests in 0.391s`、`OK`、skipped 0；G4 两条 claim 均保留并标 `conflict`。
- 反向红：临时删除 geocode 行政区检查，同一 G3 → `AssertionError: 'identity_conflict' not found in ()`，`Ran 1 test ... FAILED (failures=1)`。
- 还原绿：同一 G3 → `Ran 1 test in 0.004s ... OK`；临时改动已还原。
- 书 1 当前验收失败轮次：0/10（意图性反向红不计）。

## 书 1 任务 2：语义离群（完成）

- mobility 在坐标用于矩阵前检查三类异常：同城至少 3 点时最近邻仍 `>50km`、不同实体同一 GCJ02 坐标、同一日期窗口的相邻 POI 直线 `>50km`；均记录 `semantic_outlier`，相关 location claims 不再保留 `verified`。
- 三份独立合成场景正向：`/usr/bin/python3 -m unittest tests.test_providers -v` → `Ran 93 tests in 0.052s`、`OK`、skipped 0。
- 反向红：临时将距离阈值改为 `float("inf")`，同日相邻精准测试 → `AssertionError: 'semantic_outlier' not found in ()`，`Ran 1 test ... FAILED (failures=1)`。
- 还原绿：恢复 `50_000.0` 后上述 93 项全绿；临时改动已还原。
- 书 1 当前验收失败轮次：0/10（两次意图性反向红不计）。

## 书 2 交付门禁（完成）

- 全量：`/usr/bin/python3 -m unittest discover -s tests` → `Ran 310 tests in 21.374s`，`OK`，skipped 0（基线 290，满足 ≥296）。
- 秘密扫描：`/usr/bin/python3 scripts/scan_secrets.py` → `secret scan: 0 finding(s) across 352 file(s)`。
- 书 2 当前验收轮次：8/10；没有连续验收失败，两个临时反向变更均已还原。
