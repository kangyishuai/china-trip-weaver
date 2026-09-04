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
13220c0a75a0f0fb9bd7ea9ac28633bcb74d6066b78306669933eef23227de52  ../design/schema/trip.schema.json
13220c0a75a0f0fb9bd7ea9ac28633bcb74d6066b78306669933eef23227de52  docs/design/schema/trip.schema.json
13220c0a75a0f0fb9bd7ea9ac28633bcb74d6066b78306669933eef23227de52  plugins/china-trip-weaver/schema/trip.schema.json
```

- candidates Schema SHA-256：`5dd6862717a02654bfc5f74c3db7c76f9d71176570bfc3d1331a7382af238371`。
- 当前验收轮次：2/14。

## 任务 3：文档与 demo 对齐（完成）

- README 中英文新增范围段；主 Skill 与产品范围统一为：既有一日/单城市兼容，2–7 天多城市按 `origin→D1→D2→…`，默认不补返程，逐夜 selected stay；超过 7 天、多人异地出发再会合仍不支持。
- `/usr/bin/python3 -m unittest tests.test_skills -v`（exit 0）原始摘要：

```text
test_all_skills_pass_bundled_validator ... ok
test_exact_nine_skill_names_and_descriptions ... ok
----------------------------------------------------------------------
Ran 7 tests in 0.215s

OK
```

- 两组既有 demo 与 G1 重跑（均 exit 0）原始输出：

```text
PLAN_COMPLETE json=demo/trip.json html=demo/trip.html mode=static stages=INTAKE,RESEARCHED,CANDIDATES_READY,MATRIX_DEGRADED,SCHEDULED,VALIDATED,RENDERED calls=rail12306.fixture:2026-10-16:北京:上海,rail12306.fixture:2026-10-18:上海:北京 trip_sha256=cbee2f8e2f66b8f504fba2e86569cd72d9f563d5cfbc19f327544effc580dd26 html_sha256=3efbad80cbf6732667e7f7294313b16f3d8886e01e23bd340f5069a600251e79 errors=0
PLAN_COMPLETE json=demo/guangzhou-shenzhen/trip.json html=demo/guangzhou-shenzhen/trip.html mode=static stages=INTAKE,RESEARCHED,CANDIDATES_READY,MATRIX_DEGRADED,SCHEDULED,VALIDATED,RENDERED calls=rail12306.fixture:2026-09-10:广州:深圳,rail12306.fixture:2026-09-10:深圳:广州 trip_sha256=9e9c03abb4995e728855f9f74f385f67e71751ef8c436e1365377f4aa19182f4 html_sha256=1ff25d197912470b4abf48e496dac62272666914a2f9177275e19d14b23a3156 errors=0
PLAN_COMPLETE json=demo/multicity-5d/trip.json html=demo/multicity-5d/trip.html mode=static stages=INTAKE,RESEARCHED,CANDIDATES_READY,MATRIX_DEGRADED,SCHEDULED,VALIDATED,RENDERED calls= trip_sha256=b12bb288a8751bee3c4d1dd2849b8f783d45d5910bdcac5781de8315e786f95a html_sha256=ccc32422fe07ef66af26fda0d0428716b3ab31534346bef22db79a0cbe2fd6d5 errors=0
```

- Trip/HTML 验证（六条命令均 exit 0）原始输出：

```text
VALID demo/trip.json
HTML VALID demo/trip.html errors=0
VALID demo/guangzhou-shenzhen/trip.json
HTML VALID demo/guangzhou-shenzhen/trip.html errors=0
VALID demo/multicity-5d/trip.json
HTML VALID demo/multicity-5d/trip.html errors=0
```

- 既有 demo 重跑前后语义摘要完全一致：北京→上海仍为 3 days/7 slots/2 rail legs/1 lodging/4 POIs；广州→深圳仍为 1 day/3 slots/2 rail legs/0 lodging/3 POIs。
- G1 为 5 days，城市序列 `上海,杭州,杭州,苏州,苏州`，三条顺序 rail legs，无苏州→北京；4 个过夜日期由 3 个同城 selected stays 恰好覆盖。
- 当前验收轮次：3/14。

## 书 3 实现审阅（完成）

- 收紧策略采用向后兼容判别：旧 Trip 没有 `day.stay_id` 时继续接受 legacy lodging；新 planner 为每个 day 明确写该字段，一旦采用新形状，Schema 强制 Trip `lodgings` 全部为 selected stay，候选混入会失败。
- 第一次直接按“多目的地”收紧时，现有合法 `multicity-static.json` 被误伤；合同验收 `Ran 39 ... FAILED (failures=3)`。改为按新字段存在性判别后，同一 39 项 `OK`，未改旧 fixture 或放宽其断言。
- 同日多腿保持原 route 顺序（不再用派生 ID 打破平局）；有可用开放窗口但与所在城市日期不一致的 POI 不再被当无窗口候选塞入别天；到达时间解析兼容 `Z`。这是覆盖正确性优先于最小 diff 的取舍。
- 最终三份 Trip Schema SHA-256 均为 `13220c0a75a0f0fb9bd7ea9ac28633bcb74d6066b78306669933eef23227de52`。
- 当前验收轮次：4/14（首次合同门失败后第二次通过；未触发三连止损）。

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
- 实现口径（猜的）：同城“离群”至少需 3 个样本，并以最近邻仍超过 50km 判定；仅有两点无法识别哪一个是离群点，若两点有同日窗口则由同日相邻规则覆盖。选择该口径是为了减少合法远郊点的误伤。
- 三份独立合成场景正向：`/usr/bin/python3 -m unittest tests.test_providers -v` → `Ran 93 tests in 0.052s`、`OK`、skipped 0。
- 反向红：临时将距离阈值改为 `float("inf")`，同日相邻精准测试 → `AssertionError: 'semantic_outlier' not found in ()`，`Ran 1 test ... FAILED (failures=1)`。
- 还原绿：恢复 `50_000.0` 后上述 93 项全绿；临时改动已还原。
- 书 1 当前验收失败轮次：0/10（两次意图性反向红不计）。

## 书 2 交付门禁（完成）

- 全量：`/usr/bin/python3 -m unittest discover -s tests` → `Ran 310 tests in 21.374s`，`OK`，skipped 0（基线 290，满足 ≥296）。
- 秘密扫描：`/usr/bin/python3 scripts/scan_secrets.py` → `secret scan: 0 finding(s) across 352 file(s)`。
- 书 2 当前验收轮次：8/10；没有连续验收失败，两个临时反向变更均已还原。

## 书 3 最终门禁（完成）

- G1 从插件根连续两次真实运行 `scripts/ctw plan`，两次原始输出相同：

```text
PLAN_COMPLETE json=../../demo/multicity-5d/trip.json html=../../demo/multicity-5d/trip.html mode=static stages=INTAKE,RESEARCHED,CANDIDATES_READY,MATRIX_DEGRADED,SCHEDULED,VALIDATED,RENDERED calls= trip_sha256=b12bb288a8751bee3c4d1dd2849b8f783d45d5910bdcac5781de8315e786f95a html_sha256=ccc32422fe07ef66af26fda0d0428716b3ab31534346bef22db79a0cbe2fd6d5 errors=0
```

- G1 最终验证原始输出：

```text
VALID ../../demo/multicity-5d/trip.json
HTML VALID ../../demo/multicity-5d/trip.html errors=0
```

- G1 两次文件 SHA-256 均为 Trip `ec14fb1a589e111c1380517a4d6fbc1a9ecdd6d53b9f6dcf9cf54ee29d63a46b`、HTML `ccc32422fe07ef66af26fda0d0428716b3ab31534346bef22db79a0cbe2fd6d5`；canonical Trip hash 为上方 `b12bb288...`。
- 最终 `/usr/bin/python3 -m unittest discover -s tests`（exit 0）原始摘要：

```text
----------------------------------------------------------------------
Ran 311 tests in 20.998s

OK
```

- skipped 为 0（unittest 输出无 `skipped=`）；基线 290，最终 311，满足 ≥293。
- 最终 `/usr/bin/python3 scripts/scan_secrets.py`（exit 0）原始输出：

```text
secret scan: 0 finding(s) across 355 file(s)
```

- `scripts/ctw doctor`（exit 0）确认 `plugin_version=0.2.0`、`schema_version=1.0.0`、`skill_conflicts.status=clear`。
- `scripts/build_plan_fixtures.py` 重跑前后 tracked diff 与五个输入/manifest 哈希逐字节相同；原始输出 `wrote 3 plan cases, 3 invalid candidates, and single/multi-city demo inputs; packaged reference verified`。
- 两组旧 demo 与 G1 的六条最终 validate/validate-html 再次全部 exit 0；`git diff --check` exit 0。
- 禁碰 `providers/`、`mobility.py`、`cli.py`、`render/`、`scheduler/` 的当前 diff 原始输出为空；当前 diff stat 仅含书 3 白名单和获明确授权同步的三份 Trip Schema 副本。
- 三份 Trip Schema 最终 SHA-256 均为 `13220c0a75a0f0fb9bd7ea9ac28633bcb74d6066b78306669933eef23227de52`；`BLOCKED.md` 已写书 3“无新增阻塞”，未覆盖书 2 既有事实。
- 书 3 当前验收轮次：5/14；完成条件已全部满足并精确提交；提交后工作区 clean，禁碰路径的提交 diff 为空。

## 书 1 交付门禁（完成）

- 最终定向：`/usr/bin/python3 -m unittest tests.test_providers tests.test_amap_live -v` → `Ran 104 tests in 0.425s`、`OK`、skipped 0。
- 最终全量：`/usr/bin/python3 -m unittest discover -s tests` → `Ran 311 tests in 21.198s`、`OK`、skipped 0（基线 290，满足 ≥295）。
- 最终秘密扫描：`/usr/bin/python3 scripts/scan_secrets.py` → `secret scan: 0 finding(s) across 355 file(s)`。
- 代码提交 `977188e`（`Harden AMap place identity resolution`）只含 12 个书 1 白名单路径；其 commit stat 为 1,334 insertions、35 deletions。
- `git diff --quiet`、禁碰路径 working-tree diff、禁碰路径 `977188e^..977188e` diff 均 exit 0；planning、两处 schema、CLI、MCP stdio、rail12306 均未被书 1 修改。
- 版本核对：plugin manifest 与 package `__version__` 均为 `0.2.0`；`BLOCKED.md` 已记录书 1“无新增阻塞”。
- 书 1 最终验收失败轮次：0/10；两个意图性反向红均已还原。

## 书 5 开工记录

- 目标：让 HTML 正文只说实体名称和本地化状态，同时保留 `data-*` 校验锚点；补齐候选指针修法、搜索阶梯合同与安装解析自检。
- 顺序：先完成渲染器与 G10，再做 candidates 错误，再对齐 Skills，最后补 manifest/安装 smoke test 与全量门禁。
- 基线：`/usr/bin/python3 -m unittest discover -s tests` → `Ran 311 tests in 20.909s`、`OK`、skipped 0；秘密扫描 → `0 finding(s) across 355 file(s)`。
- 最大风险：可见 ref 与 `data-*` 锚点共用模板，去除显示文本时最容易误删校验依赖；分组地图也可能触发现有离线/视口/对抗断言。
- 边界：不碰 `cli.py`、住宿/价格逻辑、providers/schema/demo 或未列白名单文件；版本保持 `0.2.0`，不安装/刷新 Codex 缓存。

## 书 4 开工理解（2026-09-04，≤10 行）
1. 目标：住宿价格只有在日期、人数、房间、入住容量、税费与取消语境均可证实时才可标 live；否则 amount=null、verify-on-click。
2. 顺序：硬约束入请求与价格降级 → live 与调研候选合并 → VariFlight/AMap 独立兜底 → 全量门禁与提交。
3. live 住宿只能增强候选；必须保留 locked 项、未解决 unknown、claims，并沿用 selection_status，确保每晚恰有一个 stay。
4. FlyAI 全挂时仍由 VariFlight 产出航班、既有 AMap POI 能力产出住宿；两者绝不提供价格数字。
5. 基线：311 tests、OK、skipped 0；secret scan 0 finding(s) across 355 file(s)；HEAD=1119c5a 且工作区 clean。
6. 仅改任务白名单，禁碰 demo/render/candidates/mobility/amap providers/CI/版本/依赖；证据与状态只追加本书小节。
7. 最大风险：旧请求兼容、每夜唯一 stay 不变量，以及在不修改 AMap provider 的前提下正确复用 POI 能力。

## 书 5 任务 2：候选指针修法（完成）

- `_resolve_pointer` 现返回含 `expected`、`found`、`example=/lodgings/0/price/amount` 与失败位置详情的结构化 `C_UNKNOWN_PATH`，并明确数组必须用从 0 开始的下标，不能写实体 ID。
- 反向红（临时删除 example 后）：`Ran 1 test in 0.002s`，`FAILED (failures=1)`，原始断言为 `example=/lodgings/0/price/amount not found`；临时改动已还原。
- 还原绿：`/usr/bin/python3 -m unittest tests.test_candidates -v` → `Ran 7 tests in 0.104s`、`OK`、skipped 0。

## 书 5 任务 1：页面说人话（完成）

- 交通端点由 ref 映射为实体名称，raw ref/status/kind/health/mode 只保留在 `data-*`；页面以本地化文案区分已选、备选、未知，并把 unknown/provider 风险移到行程细节之前。
- evidence 改为默认关闭的 `<details>` 且按风险降序；位置视图按城市与该城日期分组，每组独立 CRS/SVG，不再跨城市连线。
- G10 反向红（临时恢复可见 `from_ref`，exit 1）原始关键输出：

```text
test_g10_visible_copy_uses_names_localized_states_and_choice_markers ... FAIL
AssertionError: Regex matched: 'poi-bund' matches '\\b(?:city|poi|lodging|leg)-[A-Za-z0-9._:-]+'
Ran 1 test in 0.004s
FAILED (failures=1)
```

- 还原后 `/usr/bin/python3 -m unittest tests.test_renderer -v`（exit 0）原始摘要：

```text
----------------------------------------------------------------------
Ran 33 tests in 1.734s

OK
```

- skipped 为 0；现有 HTML 校验、离线 Chrome 四视口、截图、打印与全部对抗 fixture 均通过，临时反向改动已还原。

## 书 5 任务 3：搜索阶梯合同（完成）

- `$research-china-destination` 明文固定三级顺序：宿主内置网络搜索优先；仅在缺失/不可用时用已配置 Key 且 probe 通过的 AnySearch；两者皆无则只用用户粘贴资料、health 标 `degraded`、其余事实保持 unknown。
- provider health 以 `host-web` / `anysearch` / `user-pasted-only` 及 reason 如实记录实际 rung；铁路、移动、排程、重排与渲染 Skill 已对齐为“不替代/不改写该 rung”。
- `/usr/bin/python3 -m unittest tests.test_skills -v`（exit 0）原始摘要：`Ran 9 tests in 0.232s`、`OK`、skipped 0；其中新增断言同时锁住宿主优先与 AnySearch 降级措辞及顺序。

## 书 5 任务 4：manifest 与安装自检（完成）

- manifest 仅在 `interface` 补真实 `websiteURL=https://github.com/kangyishuai/china-trip-weaver`；版本仍为 `0.2.0`，不存在真实政策页，因此未编造 privacy/terms URL，后续公开分发前置条件已追加到 `BLOCKED.md`。
- 单独 smoke（exit 0）原始输出：`SKILL parser smoke: OK (9 SKILL.md via codex debug prompt-input)`；它把源码 SKILL.md 复制到隔离临时 home，并调用 Codex 自身 `debug prompt-input` 解析路径，不读取/刷新已安装缓存。
- 反向红（临时把 render Skill 的 SKILL.md 改名）原始输出：`SKILL parser smoke 失败：读不到 .../render-china-trip/SKILL.md`，`exit=6`；恢复后同一 smoke 再次 `OK`。
- plugin-creator validator 原始输出：`Plugin validation passed: .../plugins/china-trip-weaver`；`/usr/bin/python3 -m unittest tests.test_skills -v` → `Ran 11 tests in 0.510s`、`OK`、skipped 0。
- `scripts/install_local_plugin.sh --check` 先报 smoke `OK`，随后按预期因旧 0.2.0 缓存与源码不一致非零退出；未运行安装模式，本机 Codex 缓存未改动。

## 书 4 任务 1：硬约束进请求与价格降级（完成）

- request schema 与公开 lodging 调用现携带 party/rooms/adult_count/occupancy/bed_config/parking_required/cancellation_preference；CLI 已提供对应参数。
- 缺任一 matching `lodgingContext`（日期、party、room、occupancy、tax、cancellation）时，即使 provider 返回数值也强制 amount=null、verify-on-click；未证实硬约束逐项写入有效 `/lodgings/*/price/amount` unknown reason。
- 正向验收：`/usr/bin/python3 -m unittest tests.test_flyai_live tests.test_keyless_e2e -v` → `Ran 30 tests in 3.734s`、`OK`、skipped 0。
- 反向红原始输出（临时令 `live_allowed=True`，已还原）：

```text
test_g2_numeric_lodging_without_quote_context_is_verify_on_click (tests.test_flyai_live.FlyAISubprocessTests) ... FAIL
AssertionError: 4321.0 is not None
----------------------------------------------------------------------
Ran 1 test in 0.001s
FAILED (failures=1)
```

- 还原绿原始输出：

```text
test_g2_numeric_lodging_without_quote_context_is_verify_on_click (tests.test_flyai_live.FlyAISubprocessTests) ... ok
----------------------------------------------------------------------
Ran 1 test in 0.000s
OK
```
- 书 4 当前验收轮次：4/14；前两次失败均为实现期有效发现，意图性反向红不计。

## 书 4 任务 2：live 结果合并不替换（完成）

- 合并顺序为 locked 调研候选 → live FlyAI → AMap 兜底 → 未锁定调研候选；所有候选与 claims 进入既有 selection_status 选择阶段，原 unknown 索引随合并重映射。
- G2 锁定候选、原 price unknown 与 claim 均保留；每个过夜日期仍恰有一个 selected stay。
- 反向红原始输出（临时恢复 inventory wholesale replacement，已还原）：

```text
test_g2_live_plan_merges_inventory_and_preserves_locked_lodging_unknowns (tests.test_flyai_live.FlyAISubprocessTests) ... FAIL
AssertionError: 'lodging-bjs-central' != 'lodging-flyai-4cbcb48a738a'
----------------------------------------------------------------------
Ran 1 test in 0.303s
FAILED (failures=1)
```

- 还原绿原始输出：

```text
test_g2_live_plan_merges_inventory_and_preserves_locked_lodging_unknowns (tests.test_flyai_live.FlyAISubprocessTests) ... ok
----------------------------------------------------------------------
Ran 1 test in 0.336s
OK
```

## 书 4 任务 3：VariFlight 与 AMap 独立兜底（完成）

- VariFlight 在无 FlyAI 航班时独立调用 `searchFlightsByDepArr`，生成 schedule/identity/status/comfort claims；候选价格恒为 amount=null、verify-on-click。
- FlyAI 无住宿结果时复用既有 AMap POI transport 搜索住宿类目，生成候选/identity/business claims；不声明库存且价格恒为 amount=null、verify-on-click。
- 定向验收：`/usr/bin/python3 -m unittest tests.test_variflight_live tests.test_keyless_e2e -v` → `Ran 21 tests in 3.441s`、`OK`、skipped 0。
- 反向红原始输出（临时令 VariFlight fallback amount=999.0、price_type=live，已还原）：

```text
test_independent_search_emits_price_less_verify_on_click_candidate (tests.test_variflight_live.VariFlightLiveTests) ... FAIL
AssertionError: 999.0 is not None
----------------------------------------------------------------------
Ran 1 test in 0.109s
FAILED (failures=1)
```

- 还原绿原始输出：

```text
test_independent_search_emits_price_less_verify_on_click_candidate (tests.test_variflight_live.VariFlightLiveTests) ... ok
----------------------------------------------------------------------
Ran 1 test in 0.211s
OK
```

- FlyAI 全挂实测原始摘要：`flyai.status=degraded; reason=calls=3; credential=keyless-trial; lodging_items=0; flight_items=0; errors=timeout`；`amap.status=ready; lodging_items=1`；`variflight.status=ready; candidates=2`。
- 候选原始价格摘要：VariFlight 两项与 AMap 一项均为 `{"amount":null,"price_type":"verify-on-click"}`；完整 provider_health 已由同次 exit 0 命令留存。

## 书 4 最终门禁

- G2 正向原始输出：

```text
test_g2_numeric_lodging_without_quote_context_is_verify_on_click (tests.test_flyai_live.FlyAISubprocessTests) ... ok
test_g2_live_plan_merges_inventory_and_preserves_locked_lodging_unknowns (tests.test_flyai_live.FlyAISubprocessTests) ... ok
----------------------------------------------------------------------
Ran 2 tests in 0.369s
OK
```

- 仅含书 4 staged snapshot 的全量原始输出（exit 0）：

```text
............................................................................................................................................................................................................................................................................................................................
----------------------------------------------------------------------
Ran 316 tests in 20.898s
OK
```

- 同一 snapshot 秘密扫描原始输出：`secret scan: 0 finding(s) across 357 file(s)`；主工作树含并行书 5 变更时同样为 0/357。
- FlyAI 全挂同次 provider_health 原始输出：

```json
[{"capabilities":["rail"],"checked_at":"2026-09-03T12:00:00+08:00","mode":"static","provider":"12306-mcp","reason":"dated deep-link fallback used: no_results","status":"degraded","version":"0.3.10"},{"capabilities":["research"],"checked_at":"2026-09-03T12:00:00+08:00","mode":"static","provider":"host-web","reason":"researched candidate file supplied; no web call was made","status":"ready","version":"candidate-file"},{"capabilities":["lodging","flight"],"checked_at":"2026-09-03T12:00:00+08:00","mode":"static","provider":"flyai","reason":"calls=3; credential=keyless-trial; lodging_items=0; flight_items=0; errors=timeout","status":"degraded","version":"1.0.16"},{"capabilities":["geocode","poi","route","lodging-candidate"],"checked_at":"2026-09-03T12:00:00+08:00","mode":"live","provider":"amap","reason":"lodging=poi_calls=1; lodging_items=1; prices=verify-on-click; errors=none; mobility=AMap mobility is off; calls=0/80 qps<=2; route matrix uses static estimates","status":"ready","version":"web-service-v5-v3-route"},{"capabilities":["flight","weather","comfort"],"checked_at":"2026-09-03T12:00:00+08:00","mode":"live","provider":"variflight","reason":"tools=9; business_calls=4; candidates=2; status_claims=2; comfort_claims=2; errors=none","status":"ready","version":"1.0.3"},{"capabilities":["research"],"checked_at":"2026-09-03T12:00:00+08:00","mode":"static","provider":"anysearch","reason":"optional search supplement is disabled; no auto-registration or business call was made","status":"missing","version":"runtime-probe-v1"}]
```

- fallback candidate 原始输出：`{"flights":[{"amount":null,"price_type":"verify-on-click","provider":"variflight","service_number":"XX1001"},{"amount":null,"price_type":"verify-on-click","provider":"variflight","service_number":"XX1001"}],"lodgings":[{"amount":null,"candidate_ref":"poi-amap-synthetic-lodging-g2","price_type":"verify-on-click"}]}`。
- staged `git diff --stat` 仅含 17 个书 4 白名单路径；demo/render/candidates.py/mobility.py/providers/amap*.py/mcp_stdio.py/rail12306.py staged diff 原始输出为空；schema SHA-256 同为 `18087f60c8126aaa15bc21e9f0c4dd7da2af6680f7b4ca5f206d6878da2dfefd`；版本仍为 0.2.0。
- 主工作树全量另受已记录的并行书 5 manifest/test 冲突影响：`Ran 324 tests ... FAILED (failures=1)`，唯一失败为 `test_plugin_manifest_is_exact_and_version_matches_package`；不属于书 4 staged snapshot，未越权修改。
- 书 4 最终验收轮次：7/14；无连续三次失败，三处意图性反向红均已还原。

## 书 5 可读性与浏览器复验

- project probe：无前端框架/构建依赖；Python 确定性字符串 renderer，既有设计权威为 `assets/renderer.css` 与 renderer 合同。本轮属 refinement，保护 12 section、CSP、embedded Trip、离线与 `data-*` 锚点；未改禁碰 stylesheet。
- 视觉复验后把英文 unknown/provider 技术 reason 留在 `data-*`，正文改为可执行的本地化核验说明；renderer 自有补充样式保证 evidence summary 44px、焦点沿用既有规则、城市组间距与打印时展开内容。
- `/usr/bin/python3 scripts/qa_renderer_browser.py ... --viewports 375x812,1440x900`（exit 0）：两视口 `failures=[]`、horizontalOverflow=0、body 16px/24.8px、minLinkHeight=44、12/12 sections、resourceRequests=[]、consoleErrors=[]、SVG/time semantics=true。
- 同条件截图人工检查：375px 首屏先显示 truth banner 与“备选与未知项”，无截断/遮挡；1440px 风险与需求形成清晰双栏，数据源状态随后全宽。范围内未发现 P0–P2。
- ego-browser 原生交互复验：`detailsCount=4`、`allClosed=true`、`minSummaryHeight=44`、`riskBeforeRequest=true`、`horizontalOverflow=0`；summary 获焦后 `Enter` 打开，指针点击关闭；隔离 task space 已关闭（`done=true`）。

## 书 5 最终门禁（受单一白名单冲突阻塞）

- 定向总验收 `/usr/bin/python3 -m unittest tests.test_renderer tests.test_candidates tests.test_skills -v`（exit 0）原始摘要：

```text
----------------------------------------------------------------------
Ran 51 tests in 2.890s

OK
```

- 全量发现已达 324（≥315）、skipped 0，但唯一失败是禁改 `tests/test_packaging.py` 的旧 exact manifest：

```text
======================================================================
FAIL: test_plugin_manifest_is_exact_and_version_matches_package (test_packaging.PackagingTests)
AssertionError: ... EXPECTED_MANIFEST ... != ... interface.websiteURL ...
----------------------------------------------------------------------
Ran 324 tests in 21.568s

FAILED (failures=1)
```

- `/usr/bin/python3 scripts/scan_secrets.py`（exit 0）原始输出：`secret scan: 0 finding(s) across 357 file(s)`。
- `git diff --check` 与白名单审计均 exit 0；当前 17 个 diff 路径全在书 5 白名单，`cli.py`、`planning.py`、schema/、providers/、mobility.py、flyai/variflight inventory、demo/ 与 `tests/test_packaging.py` 的当前 diff 原始输出为空。
- 插件版本仍 `0.2.0`；本机安装缓存目录最新 mtime 仍为 `Sep 4 17:15:59 2026`，早于本轮，且安装脚本从未以 install 模式运行。
- 全量门禁同一确定性冲突已复验 2 次；没有放宽断言、改禁碰测试或撤掉必需 manifest 字段。阻塞证据与唯一授权解法已写入 `BLOCKED.md`。
