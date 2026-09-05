# PROGRESS

## 书 14 车站距离信号开工理解（2026-09-05，≤10 行）
1. 目标：保留 12306 多站候选全集，用既有高德 geocode 城市中心与逐站 POI 坐标补充可信的 `distance_meters`，不替用户选站。
2. 顺序：核对基线 → 独立车站坐标富化模块 → 接入铁路多站 fallback → 完整性/排序/降级测试 → 红绿反向验证 → 全门禁与提交。
3. 正确 Git 根为本目录；开工 HEAD 与 `origin/main` 均为 `ef3e9f9`，工作树 clean。
4. 任务 0：全量 `Ran 393 tests ... OK`、skipped 0；secret scan `0 finding(s) across 371 file(s)`。
5. `distance_meters` 搜索确认站点链目前只有 MCP 可选字段透传及 rail 消费/排序，没有主动坐标生产者；其他命中属于 matrix、mobility 与 AMap 路线距离。
6. 高德任何失败只撤掉距离信号：未知站原样保留并排最后，不阻断铁路、不污染 12306 health。
7. 最大风险：既有 provider/MCP 调用的 deadline 与 health 归属耦合；必须让富化尽力而为且严格保持 12306 成功语义。
8. 边界：只写书 14 白名单，版本保持 0.4.0；不碰 Journey、Schema、planning、mobility、AMap provider、CI、文档或安装态。

## 书 14 任务 1：车站坐标解析（完成）

- 新增独立 `station_distance.py`：高德 geocode 以城市名取 GCJ-02 城市中心；POI 对每个候选精确传 `keywords=站名`、`city=城市`（既有 HTTP transport 映射为 `region`），仅接受同城、站名规范化精确匹配且类型为火车站/铁路的唯一坐标。
- 距离直接调用既有 `matrix.haversine_meters`；富化深拷贝原候选。三站合成 fixture 中近站=104m、远站=1045m、第三站 POI 为空；最终代码保留 3/3，第三站无 `distance_meters`，并实际发出 1 次 geocode + 3 次 POI。
- 首次正向精准门 `/usr/bin/python3 -m unittest tests.test_rail_station_fallback -v` → `Ran 17 tests in 0.943s`、`OK`、skipped 0。
- 反向验证临时过滤无距离候选；单测 exit 1，原始关键输出：

```text
AssertionError: Lists differ: ['BBX', 'AAX', 'CCX'] != ['BBX', 'AAX']
First list contains 1 additional elements.
First extra element 2:
'CCX'
Ran 1 test in 0.054s
FAILED (failures=1)
```

- 还原过滤逻辑后同一完整精准门 → `Ran 17 tests in 0.919s`、`OK`、skipped 0；另有非匹配 POI、缺 Key、城市中心无结果与同距 tie-break 回归，均不猜、不删站。

## 书 14 任务 2：距离排序与降级（完成）

- `RailMCPStdioTransport` 先完成并关闭 12306 MCP 会话，再对 ambiguous 多站组做独立 AMap 富化；铁路子进程继续只收 rail12306 最小环境，高德 Key 不进入子进程。
- 新距离写回 station-resolution transcript，`Rail12306Adapter` 既有排序现实际按“有距离 → 距离升序 → name/code tie-break → 未知最后”生效。无 Key、geocode 无结果、POI 无结果、网络/合同/意外异常均保留原始候选；外层异常隔离不改铁路 health。
- 首次组合门 `/usr/bin/python3 -m unittest tests.test_rail_station_fallback tests.test_mcp_stdio -v` → `Ran 23 tests in 4.716s`、`OK`、skipped 0。
- 反向验证临时把富化异常升级成 `ProviderNetworkError`；先确认 `error_class` 被污染为 `network`，再让健康断言优先输出，原始红态为：

```text
AssertionError: 'ready' != 'degraded'
- ready
+ degraded
Ran 1 test in 0.104s
FAILED (failures=1)
```

- 恢复“异常返回 untouched original resolution”后组合门 → `Ran 23 tests in 4.742s`、`OK`、skipped 0；高德网络失败用例同时断言 3/3 候选、全部无距离、`error_class=ambiguous`、rail health=`ready`。

## 书 14 组合树代码态验收

- 合成三站的可读原始输出（命令 exit 0；坐标为任意合成点，不是真实站点数据）：

```text
AMAP_AVAILABLE {"amap_calls": ["geocode", "poi", "poi", "poi"], "candidates": [{"city": "多站城", "distance_meters": 104, "name": "多站城近站", "ref_id": "station-bbx", "resolution_for": "from", "station_code": "BBX"}, {"city": "多站城", "distance_meters": 1045, "name": "多站城远站", "ref_id": "station-aax", "resolution_for": "from", "station_code": "AAX"}, {"city": "多站城", "name": "多站城未知站", "ref_id": "station-ccx", "resolution_for": "from", "station_code": "CCX"}], "error_class": "ambiguous", "rail_health": "ready"}
AMAP_UNAVAILABLE {"amap_calls": ["geocode"], "candidates": [{"city": "多站城", "name": "多站城未知站", "ref_id": "station-ccx", "resolution_for": "from", "station_code": "CCX"}, {"city": "多站城", "name": "多站城近站", "ref_id": "station-bbx", "resolution_for": "from", "station_code": "BBX"}, {"city": "多站城", "name": "多站城远站", "ref_id": "station-aax", "resolution_for": "from", "station_code": "AAX"}], "error_class": "ambiguous", "rail_health": "ready"}
```

- 首轮全量碰到并行书 13 的临时 Journey 中间态，`Ran 381 ... FAILED (failures=2, errors=2)`，全部 traceback 均落在禁改的 `journey.py`/`test_journey.py`；未触碰或回滚。对方恢复后 `tests.test_journey` 为 32/32 OK。
- 恢复后的组合树 `/usr/bin/python3 -m unittest discover -s tests`（exit 0）：`Ran 402 tests in 27.018s`、`OK`、skipped 0；`/usr/bin/python3 scripts/scan_secrets.py`（exit 0）：`secret scan: 0 finding(s) across 372 file(s)`。
- 额外独立门：providers `Ran 94 ... OK`；packaging+tracked synthetic-data `Ran 8 ... OK`；`py_compile` 与 `git diff --check` exit 0。
- 最终暂存态：全量 `Ran 402 tests in 26.110s ... OK`、skipped 0；secret scan 0/372；铁路+MCP `Ran 23 tests in 4.769s ... OK`；`ALLOWLIST_OK files=6`，禁改路径组合 diff 为空，`VERSION_DIFF_OK changed_version_lines=0`。`BLOCKED.md` 的车站距离项已据实移到 Closed；当前轮次 7/12，书 14 已可提交。

## 书 14 提交后核验（完成）

- 实现提交 `3d1980a36fc47968648cd346426c086764f007f5`（`Add AMap station distance signals`）：6 个白名单文件、650 insertions/47 deletions；包含 `BLOCKED.md` 关闭记录与全部书 14 进度，未吸入并行书 13 hunks。
- 与书 13 的提交线性共存后，提交后全量 `/usr/bin/python3 -m unittest discover -s tests` → `Ran 402 tests in 26.901s`、`OK`、skipped 0；铁路+MCP 精准门 → `Ran 23 tests in 4.749s`、`OK`、skipped 0；secret scan → `0 finding(s) across 372 file(s)`。
- 提交范围复核：`FORBIDDEN_DIFF_OK paths=13`、`VERSION_DIFF_OK changed_version_lines=0`；`git show --stat 3d1980a` 仅列 6 个白名单文件。只读版本仍为 `plugin_version=0.4.0`、`package_version=0.4.0`。
- 最终可读输出仍为 AMap 可用时 `BBX=104m, AAX=1045m, CCX=unknown`，不可用时三站全部保留、无距离且 `rail_health=ready`。代码提交后 `git diff --stat` 无输出；未安装 Codex、未改 CI、未 push。当前轮次 8/12。

## 住宿链锚定修复开工理解（2026-09-05，≤10 行）
1. 目标：Journey 必须把候选住宿的 city/check_in/check_out 当作用户已表达的逐夜事实，段边界和每日城市都与它对齐。
2. 顺序：任务 0 双失败复现 → 先修段边界/城市推进 → 再补无解最近住宿与 unknown 下标校验 → 固化 16 天 6 城 3 人回归。
3. 住宿链与均分交通日冲突时服从住宿链；链真有缺口时继续结构化无解，绝不放宽或静默跳过逐夜住宿门。
4. unknown 的数组下标必须解析到其 claim.subject_ref 对应实体，错误需同时指出当前路径与期望下标。
5. 只写本轮白名单；版本保持 0.4.0，不碰 schema/render/demo/CLI/providers/scheduler/docs，不安装 Codex。
6. 回归中的城市、住宿、景点、链接与价格全部合成；具名门禁只是下限，不把门禁放行当成可提交真实数据的许可。
7. 最大风险：住宿换城日既决定分段，也必须让子 Trip 的 route leg、day.city、stay 选择和跨段桥接保持一致。
8. 当前验收轮次：1/14；任务 0 完成，尚未修改产品代码。

## 住宿链锚定修复任务 0：基线与双失败复现（完成）

- 正确 Git 根为本目录。产品代码仍精确基于 `a1bf1ad`；本地 HEAD=`a95ecf4`、`origin/main=a1bf1ad`，唯一额外提交只改 `PROGRESS.md`，详情同步在 `BLOCKED.md` 的非阻塞说明。
- 基线 `/usr/bin/python3 -m unittest discover -s tests`（exit 0）原始摘要：

```text
..................................................................................................................................................................................................................................................................................................................................................................................................
----------------------------------------------------------------------
Ran 386 tests in 26.982s

OK
```

- skipped 0；`/usr/bin/python3 scripts/scan_secrets.py`（exit 0）原始输出：

```text
secret scan: 0 finding(s) across 370 file(s)
```

- 临时系统目录中生成全合成 16 天、6 城、3 人候选；住宿链连续覆盖 15 晚，故意让住宿 0 的 price unknown 指向 `/lodgings/1/...`。原始输出：

```text
CANDIDATES VALID /tmp/ctw-task0-repro.ZJcLQI/candidates.json
JOURNEY_PLAN_FAILED segment candidates validation failed: C_UNKNOWN_CLAIM /unknowns/0/claim_id unknown references a missing claim
validate_exit=0 journey_exit=1 repro_dir=/tmp/ctw-task0-repro.ZJcLQI
```

- 仅把该路径校正回 `/lodgings/0/price/amount` 后，第二堵墙精确复现为住宿链已覆盖、均分交通却提前进城：

```text
CANDIDATES VALID /tmp/ctw-task0-repro.ZJcLQI/candidates.json
JOURNEY_PLAN_FAILED plan has no feasible stay: {"city":"合成丙城","code":"NO_STAY_FOR_NIGHT","date":"2026-09-25"}
validate_exit=0 journey_exit=1
```

## 住宿链锚定修复任务 1：段边界与每日城市（完成）

- `split_journey_inputs` 先把请求目的地内的候选住宿投影为逐日城市；住宿城市变化日优先成为段起点，同城区间才按 7 天硬切。每个子 Trip 只收到当段住宿城市，内部 route leg、`day.city` 与逐夜 stay 因而一起服从住宿链。
- 按真实试跑日期形状收紧后的 16 天 6 城合成场景拆为 `09-25`、`09-26..28`、`09-29`、`09-30..10-02`、`10-03..05`、`10-06..07`、`10-08`、`10-09..10`；15 个夜晚逐一断言覆盖候选的唯一 city=`day.city`，所选 `candidate_ref` 属于覆盖该夜的候选且 `selected_nights` 包含该夜。
- 三个只有一天的城市段本身不会让 Trip planner 选 stay；既有 `_bridge_segment_lodgings` 现会从该段候选物化边界夜住宿、claims 与 unknowns，再走原预算和 Trip validator，避免完整住宿链被误报 `J_LODGING_GAP`。
- 首次精准门 `/usr/bin/python3 -m unittest tests.test_journey -v` → `Ran 25 tests in 1.589s`、`OK`、skipped 0。
- 必做反向验证：临时令 `_segment_start_dates` 忽略住宿映射、只看均分交通腿，同一边界测试（exit 1）原始关键输出：

```text
test_six_city_segment_boundaries_follow_the_lodging_chain (tests.test_journey.JourneySplitTests) ... FAIL
First differing element 0:
('2026-09-25', '2026-09-25', '合成甲城')
('2026-09-25', '2026-09-26', '合成甲城')
First list contains 1 additional elements.
First extra element 7:
('2026-10-09', '2026-10-10', '合成戊城')
----------------------------------------------------------------------
Ran 1 test in 0.017s

FAILED (failures=1)
```

- 恢复住宿链分支后完整精准门原始摘要：

```text
----------------------------------------------------------------------
Ran 28 tests in 1.982s

OK
```

- skipped 0；最终日期结构上的临时 route-only 代码已完整还原。当前验收轮次：5/14。

## 住宿链锚定修复任务 2：可操作无解与 unknown 下标校验（完成）

- `validate_candidates` 在 JSON Pointer 可解析且 claim 存在后，比较路径的 `/pois|lodgings/<index>` 与 claim.subject_ref 的实体位置；错位报 `C_UNKNOWN_SUBJECT`，同时给 `expected_index` 与可复制的 `expected_prefix`。
- `_select_stays` 的 `NO_STAY_FOR_NIGHT` 保持硬失败，并新增 `nearest_lodging`：候选下标/id/名称/城市/check_in/check_out、日期距离及是否同城；Journey 在住宿链本身缺夜时复用同一结构，未静默接受空夜。
- 下标错位 CLI（exit 1）原始输出：

```text
C_UNKNOWN_SUBJECT /unknowns/0/field_path unknown field_path targets /lodgings/1 but claim claim-j16-six-city-synthetic-a-lodging-price subject_ref lodging-j16-six-city-synthetic-a-central is /lodgings/0; expected_index=0; expected_prefix=/lodgings/0
CANDIDATES INVALID /tmp/ctw-task2-repro.LuThDl/misindexed.json (1 error)
misindexed_exit=1
```

- 住宿链仅缺 2026-09-25 一晚时 Journey CLI（exit 1）原始输出：

```text
JOURNEY_PLAN_FAILED Journey lodging chain has no feasible stay: {"city":"合成乙城","code":"NO_STAY_FOR_NIGHT","date":"2026-09-25","nearest_lodging":{"candidate_index":1,"check_in":"2026-09-22","check_out":"2026-09-25","city":"合成乙城","distance_nights":1,"lodging_id":"lodging-j16-six-city-synthetic-b-central","name":"合成乙城合成住宿","same_city":true}}
gap_exit=1
```

- 首次精准门 `/usr/bin/python3 -m unittest tests.test_candidates tests.test_journey -v` → `Ran 38 tests in 2.405s`、`OK`、skipped 0。
- 必做反向验证：临时关闭 subject/index 检查，精准 CLI 回归（exit 1）原始关键输出：

```text
AssertionError: 1 != 0 : CANDIDATES VALID /Users/kangyishuai/Workspace/core/ChinaTripWeaver/china-trip-weaver/.tmp/tmp5d1f4ljy/misindexed-candidates.json
----------------------------------------------------------------------
Ran 1 test in 0.062s

FAILED (failures=1)
```

- 恢复检查后两组完整精准门 → `Ran 38 tests in 2.111s`、`OK`、skipped 0；临时代码已完整还原。当前验收轮次：3/14。

## 住宿链锚定修复任务 3：16 天 6 城 3 人回归（完成）

- 新增 `tests/fixtures/journey/synthetic-six-city-16d.json`，内含完整 request+candidates；`scripts/build_plan_fixtures.py::write_journey_lodging_chain_fixture` 可确定性重建该文件，但本轮只单独生成新夹具，没有运行会改写 demo 的 builder main。
- 日期与住宿链精确沿用真实场景形状：2026-09-25..10-10、8 个城市段、6 个不同合成城市、9 条住宿候选（含返城与 10-05 同城重叠）、3 位旅客/2 间房；九个住宿/六个景点名称全部含“合成”，价格 amount 全为 null，实体与 claim 链接全部是 `https://example.invalid/`。
- 永久回归逐字段比较生成器与 checked-in fixture，并真实执行 `ctw journey plan` → `ctw journey validate`；同时保留逐夜 city/check_in/check_out/candidate_ref/selected_nights 断言。
- `/usr/bin/python3 -m unittest tests.test_journey -v` 原始摘要：

```text
----------------------------------------------------------------------
Ran 28 tests in 2.015s

OK
```

- skipped 0；`/usr/bin/python3 scripts/scan_secrets.py` → `secret scan: 0 finding(s) across 371 file(s)`。
- 合成数据门 `/usr/bin/python3 -m unittest tests.test_no_captured_provider_data -v` → `Ran 1 test in 0.027s`、`OK`、skipped 0。当前验收轮次：4/14。

## 住宿链锚定修复最终代码态验收

- checked-in 合成夹具的公开命令链（均 exit 0）原始输出：

```text
CANDIDATES VALID /tmp/ctw-final-acceptance.ks73J6/candidates.json
JOURNEY_PLAN_COMPLETE json=/tmp/ctw-final-acceptance.ks73J6/journey.json trips=8 days=16 max_trip_days=3 calls= journey_sha256=a5a2cda7cd723e9464002fecd96fb3af8d14767f897ed2da1aa3eb48c68e9f69 errors=0
JOURNEY VALID /tmp/ctw-final-acceptance.ks73J6/journey.json trips=8
2026-09-25 candidate_city=合成甲城 day_city=合成甲城 selected_window=2026-09-25..2026-09-26 candidate_options=1 aligned=true
2026-09-26 candidate_city=合成乙城 day_city=合成乙城 selected_window=2026-09-26..2026-09-29 candidate_options=1 aligned=true
2026-09-27 candidate_city=合成乙城 day_city=合成乙城 selected_window=2026-09-26..2026-09-29 candidate_options=1 aligned=true
2026-09-28 candidate_city=合成乙城 day_city=合成乙城 selected_window=2026-09-26..2026-09-29 candidate_options=1 aligned=true
2026-09-29 candidate_city=合成甲城 day_city=合成甲城 selected_window=2026-09-29..2026-09-30 candidate_options=1 aligned=true
2026-09-30 candidate_city=合成丙城 day_city=合成丙城 selected_window=2026-09-30..2026-10-03 candidate_options=1 aligned=true
2026-10-01 candidate_city=合成丙城 day_city=合成丙城 selected_window=2026-09-30..2026-10-03 candidate_options=1 aligned=true
2026-10-02 candidate_city=合成丙城 day_city=合成丙城 selected_window=2026-09-30..2026-10-03 candidate_options=1 aligned=true
2026-10-03 candidate_city=合成丁城 day_city=合成丁城 selected_window=2026-10-03..2026-10-06 candidate_options=1 aligned=true
2026-10-04 candidate_city=合成丁城 day_city=合成丁城 selected_window=2026-10-03..2026-10-06 candidate_options=1 aligned=true
2026-10-05 candidate_city=合成丁城 day_city=合成丁城 selected_window=2026-10-03..2026-10-06 candidate_options=2 aligned=true
2026-10-06 candidate_city=合成戊城 day_city=合成戊城 selected_window=2026-10-06..2026-10-08 candidate_options=1 aligned=true
2026-10-07 candidate_city=合成戊城 day_city=合成戊城 selected_window=2026-10-06..2026-10-08 candidate_options=1 aligned=true
2026-10-08 candidate_city=合成己城 day_city=合成己城 selected_window=2026-10-08..2026-10-09 candidate_options=1 aligned=true
2026-10-09 candidate_city=合成戊城 day_city=合成戊城 selected_window=2026-10-09..2026-10-10 candidate_options=1 aligned=true
NIGHT_ALIGNMENT_OK nights=15 distinct_cities=6 lodging_candidates=9 trips=8 days=16
```

- 最终夹具负向 CLI（两个命令均预期 exit 1，核验脚本 exit 0）原始输出：

```text
C_UNKNOWN_SUBJECT /unknowns/0/field_path unknown field_path targets /lodgings/1 but claim claim-j16-six-city-synthetic-a-first-lodging-price subject_ref lodging-j16-six-city-synthetic-a-first-central is /lodgings/0; expected_index=0; expected_prefix=/lodgings/0
CANDIDATES INVALID /tmp/ctw-final-negative.SIiWF6/misindexed.json (1 error)
JOURNEY_PLAN_FAILED Journey lodging chain has no feasible stay: {"city":"合成乙城","code":"NO_STAY_FOR_NIGHT","date":"2026-09-28","nearest_lodging":{"candidate_index":1,"check_in":"2026-09-26","check_out":"2026-09-28","city":"合成乙城","distance_nights":1,"lodging_id":"lodging-j16-six-city-synthetic-b-central","name":"合成乙城合成住宿2","same_city":true}}
misindexed_exit=1 gap_exit=1
```

- 暂存前与暂存态全量均为 393；最终暂存态 `/usr/bin/python3 -m unittest discover -s tests` 原始摘要：

```text
.........................................................................................................................................................................................................................................................................................................................................................................................................
----------------------------------------------------------------------
Ran 393 tests in 25.869s

OK
```

- skipped 0；最终精准门 `tests.test_candidates tests.test_journey -v` → `Ran 40 tests in 2.484s`、`OK`；secret scan → `0 finding(s) across 371 file(s)`。
- 新夹具进入 Git index 后，`tests.test_no_captured_provider_data -v` → `Ran 1 test in 0.029s`、`OK`，证明 tracked-files 门实际覆盖它。
- 暂存态仅 9 个白名单路径；`git diff --cached --check` exit 0；schema/render/demo/cli/plugin manifest/__init__/providers/mobility/scheduler/Trip validator/docs/secret scanner/既有合成门组合 diff exit 0 且无输出。
- `ALLOWLIST_OK files=9`；暂存 stat 为 `9 files changed, 1528 insertions(+), 37 deletions(-)`（其中新合成 JSON 773 行）。
- 版本面组合 diff 无输出；只读值仍为 `plugin.json version=0.4.0`、`__version__=0.4.0`。本轮未安装 Codex、未运行 demo 生成器、未发布或推送。
- 当前验收轮次：7/14；没有同一验收三连败，代码完成条件均已绿；9 个白名单文件的交付提交已创建并把本状态记录纳入同一提交，剩余仅提交后只读核验。

## 住宿链锚定修复提交后核验（完成）

- 实现交付提交：`0d6c41328165db503f35787f6c75cadd9f2d60fe`（`Anchor Journey planning to lodging chains`），9 个文件、1530 insertions/37 deletions；`COMMIT_ALLOWLIST_OK files=9`。
- `git diff HEAD^ HEAD --` 对 schema/render/demo/cli/plugin manifest/__init__/providers/mobility/scheduler/Trip validator/docs/secret scanner/既有合成门的组合命令 exit 0、无输出。
- 提交后全量原始摘要：

```text
.........................................................................................................................................................................................................................................................................................................................................................................................................
----------------------------------------------------------------------
Ran 393 tests in 26.275s

OK
```

- skipped 0；提交后 secret scan 为 `0 finding(s) across 371 file(s)`；tracked-files 合成门为 `Ran 1 test in 0.028s`、`OK`。
- 实现提交后工作树 clean，`main...origin/main [ahead 2]`：其中 `a95ecf4` 是开工前仅含 PROGRESS 的用户历史，`0d6c413` 是本轮实现；本轮未 push。
- 当前验收轮次：8/14；全部完成条件已有实际命令证据，本节将作为仅 `PROGRESS.md` 的收尾记录提交。

## 当前状态速览（2026-09-05）

接手先读这一节，下面 68 个章节是按轮次留存的实测证据，不必通读。

- 版本 **0.4.0**，已装进本机 Codex（`plugin list: installed, enabled 0.4.0`，缓存与源码一致）。
- 全量 `/usr/bin/python3 -m unittest discover -s tests` = **393 项 OK、skipped 0**；
  `scripts/scan_secrets.py` = `0 finding(s) across 371 file(s)`。
- demo 五组：`demo/` 根、`guangzhou-shenzhen/`、`multicity-5d/`、`grouped-departures/`、
  `journey-16d/`，各自 validate 与 HTML 校验全过。
- 2026-09-04/05 完成真实行程 dogfood 审计的全部 12 条 finding，测试从 290 涨到 386。
  按管理者—执行者模式跑了 11 份任务书：地点身份、12306 站名 fallback、跨城多目的地、
  住宿硬约束与库存兜底、可读交付与工具口径、节奏预算、并发与 CLI 便利、旅客分组与
  降配、0.3.0 发布、Journey 模型、0.4.0 Journey 总览与发布。
- 仍开着的两条在 `BLOCKED.md` 顶部 Open 区：12306 车站候选无距离信号；公开分发的
  privacy/terms URL 有意留空。
- 真实 16 天行程实测发现的两项待办已在本轮修复：Journey 段边界/每日城市服从候选住宿链；
  `validate-candidates` 会在入口拒绝 unknown 数组下标与 claim.subject_ref 实体错位。

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

## 书 6 开工理解（2026-09-04，≤10 行）

1. 目标：让 pace 真正约束日窗、POI 数、步行与午休，并让 slow/balanced/full 对同一输入产生可区分日程。
2. 第二步把预算改为一次性的全程 ledger；已知 POI/交通/住宿成本参与排程，口径不可比或未知价格只进区间与 unknowns，绝不按 0 隐去。
3. 第三步把午餐、晚餐、午休、跨城 buffer 作为 required candidates；senior 的连续重体力项目之间强制恢复窗。
4. 实现范围只限书 6 白名单；不碰 CLI、candidates、providers、mobility、render、demo、manifest、版本与安装。
5. 每项先补强断言，再做意图性反向红、还原全绿；同一验收连续三败即转下一项，最多 14 轮。
6. 最大风险：现有逐日 scheduler 与全程 ledger 的边界、未知价格的 schema 表达、required 餐休挤压已有 golden 的可行性。
7. 任务 0 实测：HEAD=origin/main=`176dbc7`、工作树干净；324 tests OK、skipped 0；secret scan 0/357；两组 `rg` 均 exit 1 且零输出。
## 书 7 开工理解与任务 0（2026-09-04，≤10 行）
1. 目标：让 FlyAI 限流可控可见，并补齐 NDJSON 进度、四层 doctor probe 与候选文件生成器。
2. 顺序：并发闸门/一次重试 → progress 五类事件 → doctor 四层 → candidates init/add → 全门禁。
3. FlyAI 默认全实例共享单并发；AMap 只复用既有 `acquire()` qps 闸门，不另建限流体系。
4. 限流仅重试一次，遵循 `Retry-After` 或固定上限，health 必须永久保留本次 retry 事实。
5. `--progress ndjson` 默认关闭；开启后每行独立 JSON，且绝不写 Key、凭据或响应正文。
6. 不带 `--probe` 的 doctor 必须字节级保持旧形状；probe 分 credential/contract/network/business。
7. candidates 子命令自动生成稳定 ID、claim/unknown ID 与零基数组 JSON Pointer，产物直接可验证。
8. 最大风险：跨线程共享 probe/闸门状态、CLI stdout 合同、provider health 数据形状与 Schema 必填项。
9. 基线：HEAD=origin/main=`176dbc7`，324 tests OK/skipped 0，secret scan 0；`Retry-After` 现有 1 处只为响应头摘录，已记 BLOCKED。

## 书 7 任务 1：并发闸门与一次可见重试（完成）

- FlyAI 真实 subprocess transport 使用进程级单许可闸门，等待时间计入调用 deadline；root/command probe 与业务调用处于同一串行区，因此八并发只执行共享的 2 个 probe。
- 上游 HTTP/FlyAI 429/402 只对显式 opt-in 的 FlyAI、AMap transport 重试一次；AMap 每次尝试仍经过原 `AMapCallBudget.acquire()`。`Retry-After` 支持秒数/HTTP 日期并截到 2 秒，缺失时固定 0.25 秒。
- 成功或失败的 Adapter health `reason` 均保留 `rate_limit_retries=1` 与实际 delay，warnings 保留 `rate_limit_retry`；未给其他 provider 或 replay fixture 改调用次数。
- 首次整体验收暴露 Rail 子类覆写旧 `_failure` 签名，原始摘要为 `Ran 16 tests ... FAILED (errors=5)`、`TypeError: _failure() got an unexpected keyword argument 'rate_limit_retries'`；已保持旧扩展点签名并由新 helper 包装，未改 rail 文件。
- G8 正向 `/usr/bin/python3 -m unittest tests.test_flyai_live -v`（exit 0）原始摘要：

```text
test_g8_concurrent_rate_limits_serialize_retry_once_and_dedupe ... ok
test_g8_rate_limit_retry_stops_after_one_retry ... ok
----------------------------------------------------------------------
Ran 16 tests in 1.688s

OK
```

- 反向验证：临时将 `MAX_RATE_LIMIT_RETRIES` 从 `1` 改为 `float("inf")`，同命令（exit 1）原始关键输出：

```text
test_g8_rate_limit_retry_stops_after_one_retry ... FAIL
AssertionError: 'rate_limited' != None
----------------------------------------------------------------------
Ran 16 tests in 1.961s

FAILED (failures=1)
```

- 还原后 FlyAI + AMap + provider corpus：`/usr/bin/python3 -m unittest tests.test_flyai_live tests.test_amap_live tests.test_providers -v` → `Ran 120 tests in 2.097s`、`OK`、skipped 0。
- 书 7 当前验收轮次：1/14（意图性反向红不计）。

## 书 7 任务 2：`--progress ndjson`（完成）

- `--progress ndjson` 可置于根命令或 provider 子命令后；默认关闭。事件只写 stderr，stdout 的既有 JSON/完成行不变。
- emitter 只接受 `probe/query/degrade/retry/completion` 五类事件与十个标量白名单字段，拒绝序列化请求参数、argv、URL、响应正文和 diagnostics；线程锁保证并发下每行仍是一个完整 JSON。
- G8 CLI 测试逐行 `json.loads`，五类事件集合精确为 `{probe,query,degrade,retry,completion}`，真实 synthetic response 的 `itemList`/酒店名与注入 credential 均不在事件流；默认模式 stderr 精确为空。
- `/usr/bin/python3 -m unittest tests.test_flyai_live tests.test_credentials -v`（exit 0）原始摘要：

```text
test_progress_is_silent_by_default_and_root_position_is_supported ... ok
test_progress_ndjson_has_five_allowlisted_event_types_and_scans_clean ... ok
----------------------------------------------------------------------
Ran 32 tests in 19.925s

OK
```

- 反向 secret 验证：向临时 NDJSON 事件加入一个合成 credential prefix 后，`/usr/bin/python3 scripts/scan_secrets.py <temp-event>`（exit 1）原始输出：

```text
SECRET /private/tmp/ctw-progress-red.JNGl8U:1 credential prefix
secret scan: 1 finding(s) across 1 file(s)
```

- 临时事件已删除；还原后的仓库扫描 `/usr/bin/python3 scripts/scan_secrets.py`（exit 0）原始输出：`secret scan: 0 finding(s) across 357 file(s)`。
- 书 7 当前验收轮次：2/14。

## 书 7 任务 3：`doctor --probe` 四层报告（完成）

- `doctor --probe` 对 amap/flyai/variflight 执行并发、限时、只读的小型 probe；AnySearch 因本 runtime 没有 transport 明确报 `unsupported`，不拿 configured 冒充可用。
- 每个 provider 只输出 `credential/contract/network/business` 四层枚举，不输出异常文本、URL、请求参数、Key 或响应正文；probe 不改变 doctor 的 conflict exit contract。
- 改动前后 `plugins/china-trip-weaver/scripts/ctw doctor`（exit 0）原始输出逐字相同：

```text
{"plugin_version":"0.2.0","providers":{"amap":"configured","anysearch":"configured","flyai":"configured","variflight":"configured"},"python":"3.9.6","schema_exists":true,"schema_version":"1.0.0","skill_conflicts":{"conflicts":{},"status":"clear"}}
```

- `plugins/china-trip-weaver/scripts/ctw doctor --probe`（exit 0，真实只读调用）原始输出：

```text
{"plugin_version":"0.2.0","probes":{"amap":{"business":"passed","contract":"passed","credential":"configured","network":"passed"},"anysearch":{"business":"unsupported","contract":"unsupported","credential":"configured","network":"unsupported"},"flyai":{"business":"passed","contract":"passed","credential":"configured","network":"passed"},"variflight":{"business":"not_run","contract":"failed","credential":"configured","network":"passed"}},"providers":{"amap":"configured","anysearch":"configured","flyai":"configured","variflight":"configured"},"python":"3.9.6","schema_exists":true,"schema_version":"1.0.0","skill_conflicts":{"conflicts":{},"status":"clear"}}
```

- 该实测证明分层有用：VariFlight 的 Key 存在且 MCP 可达，但当前工具指纹契约失败，business 未运行；未把它误报为可用。
- 反向验证：临时给默认 stdout 加 `DOCTOR ` 前缀，三条冻结测试（exit 1）原始摘要：

```text
test_runtime_entry_is_executable_and_cwd_independent ... ERROR
test_cli_validate_and_doctor ... ERROR
test_doctor_reports_conflict_status_and_keeps_credentials_opaque ... ERROR
json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
----------------------------------------------------------------------
Ran 3 tests in 3.639s

FAILED (errors=3)
```

- 还原后 `/usr/bin/python3 -m unittest tests.test_credentials tests.test_contracts tests.test_plugin_conflicts tests.test_packaging -v` → `Ran 48 tests in 11.527s`、`OK`、skipped 0；默认 doctor 再次输出上述完全相同字节。
- 书 7 当前验收轮次：3/14。

## 书 7 任务 4：候选生成器（完成）

- 新增 `ctw candidates init/add-poi/add-lodging`；init 对既有文件 fail closed，只有显式 `--force` 才覆盖。实体与 claim ID 自动按内容稳定生成，未知字段用自动 claim ID 关联。
- frozen unknown schema 没有 `unknown_id` 字段，因此没有伪造额外字段；unknown 以其自动 `claim_id` 追踪，并按实际 append index 生成可解析 JSON Pointer。
- POI 可选日期窗、时长、参考价；住宿可选每晚参考价/含税状态。未研究的坐标、窗、时长、价格、含税项均如实成为 unknown，不拿 null 冒充已知。
- `/usr/bin/python3 -m unittest tests.test_candidates -v`（exit 0）原始摘要：

```text
test_cli_generator_output_validates_without_manual_edits ... ok
test_generator_refuses_overwrite_and_duplicate_without_changing_file ... ok
test_generator_uses_actual_zero_based_index_for_every_append ... ok
----------------------------------------------------------------------
Ran 10 tests in 0.381s

OK
```

- 真实临时文件 CLI 流程（每步 exit 0，文件随后删除）原始输出：

```text
CANDIDATES_INITIALIZED /tmp/ctw-candidates.en3k1n/candidates.json
CANDIDATE_POI_ADDED /tmp/ctw-candidates.en3k1n/candidates.json id=poi-3fc6c64453a2
CANDIDATE_LODGING_ADDED /tmp/ctw-candidates.en3k1n/candidates.json id=lodging-9f19bd21d2a7
CANDIDATES VALID /tmp/ctw-candidates.en3k1n/candidates.json
```

- 书 7 当前验收轮次：4/14。

## 书 6 任务 1：pace 真参数（完成）

- scheduler 的唯一 `PACE_PROFILES` 已落地：slow=`09:00–20:00/3 POI/1.5km/90min`，balanced=`08:30–21:30/5/2.5km/60min`，full=`08:00–22:30/7/4km/30min`；planning 将 pace 日窗、POI 上限和步行段阈值传入 scheduler，跨城固定交通仅扩展必要的总包络。
- 首轮定向验收发现 4 日样例由 10 slots 降至 9：原因是把 transit 全程距离误当步行；改为只有 `travel_mode=walk` 的景点段才应用步行阈值后，`/usr/bin/python3 -m unittest tests.test_scheduler tests.test_keyless_e2e -v` → `Ran 60 tests in 3.471s`、`OK`、skipped 0。
- 反向红（临时把 slow/full 都同化为 balanced，已还原）原始输出：

```text
test_same_complete_plan_has_distinct_slow_balanced_full_results ... FAIL
AssertionError: 3 != 5 : slow
----------------------------------------------------------------------
Ran 1 test in 0.022s
FAILED (failures=1)
```

- 还原绿原始输出：`Ran 1 test in 0.073s`、`OK`。同一合成候选的原始结果：slow=`09:00` 起，依次 `poi-pace-1..3`，末项 `11:55`；full=`08:00` 起，依次 `poi-pace-1..7`，末项 `15:15`。
- 书 6 当前验收轮次：2/14（意图性反向红不计）。

## 书 6 任务 2：全程预算与真实成本（完成）

- `schedule_plan(..., budget_cny=...)` 现在先为所有天的 required/locked 已知成本预留，再按剩余全程额度选择 optional；不再向 day problem 写整趟预算。预算 100、后日必选 60、前日可选 70 时保留必选并降配为总成本 60；两日必选 60+50 时返回结构化 `NO_SOLUTION/conflict.code=budget/known_cost_cny=110`。
- POI/交通的 `per_person` 按 travelers 换算，住宿 `per_night` 按 nights×rooms；缺 rooms 输出 1..travelers 房的区间。unknown/verify-on-click、外币、from-price、税费未确认或单位不适用均不按 0 冒充，scheduler 标记 `unknown_cost_refs`，Trip `budget_ledger` 输出上下界并追加可解析路径的 unknown。
- 正向：`/usr/bin/python3 -m unittest tests.test_scheduler -v` → `Ran 46 tests in 0.705s`、`OK`、skipped 0；另 `test_trip_budget_is_not_copied_into_daily_scheduler_problems` → `Ran 1 ... OK`。POI 25/人×2=50、交通 120/人×2=240、住宿 300/晚×2晚×1房=600；房数缺失区间=600..1200。
- 反向红（临时恢复 day problem 的 `"budget_cny": request["budget_cny"]`，已还原）原始输出：

```text
test_trip_budget_is_not_copied_into_daily_scheduler_problems ... FAIL
AssertionError: False is not true
----------------------------------------------------------------------
Ran 1 test in 0.000s
FAILED (failures=1)
```

- 还原后书 6 联合验收：`/usr/bin/python3 -m unittest tests.test_scheduler tests.test_keyless_e2e -v` → `Ran 65 tests in 4.431s`、`OK`、skipped 0。
- 书 6 当前验收轮次：4/14（意图性反向红不计）。

## 书 6 任务 3：餐、休息与恢复窗（完成）

- 每天强制 60 分钟午餐与晚餐；默认允许开始窗分别为 11:00–13:00、16:30–19:30，长途交通覆盖餐窗时选择离目标最近的可行前/后窗口。地点待定餐位以有 planner claim 的 POI 占时，价格为 null 并进 unknown，不虚构店铺或价格。
- 每天强制 pace 对应午休；每个跨城 rail slot 增加强制 45 分钟行李/进出站换乘 buffer。餐位/休息为 locationless，交通为 route boundary，避免把未知餐厅路线或跨城端点间路线伪造成已知矩阵。
- request schema 已接受可选 `mobility_profile`（含 senior）、`walking_tolerance_km`、`meal_windows`、`rest_windows`；POI 可标 `physical_intensity`。senior 即使 `fitness_level=good`，两个 heavy POI 之间也必须存在 recovery rest；Trip day 输出 pace 与实际 planned walking km。
- 首轮餐休联合验收因回程日把未知餐厅间的 4.5km 静态估算当真实移动导致 `window` 无解；改为餐位 locationless 后恢复。最终 `/usr/bin/python3 -m unittest tests.test_scheduler tests.test_keyless_e2e -v` → `Ran 67 tests in 4.489s`、`OK`、skipped 0；G9 单测 `Ran 1 in 0.039s ... OK`。
- 反向红（临时把午/晚餐、午休与 senior 恢复窗降为 optional，已还原）原始输出：

```text
test_g9_balanced_senior_gets_meals_rest_recovery_and_pace_limits ... FAIL
AssertionError: 2 != 1
----------------------------------------------------------------------
Ran 1 test in 0.036s
FAILED (failures=1)
```

- 还原绿：同一 G9 `Ran 1 test in 0.039s ... OK`。`schedule-china-trip/SKILL.md` 经 bundled skill-creator validator：`Skill is valid!`。
- 书 6 当前验收轮次：7/14（意图性反向红不计）。

## 书 7 集成门禁（代码与测试完成）

- 第一轮全量在书 6 尚未完成餐休窗口时得到 `Ran 340 tests in 22.464s`、`FAILED (failures=1, errors=16)`；所有 traceback 均止于其独占 `planning.py:255 ... conflict=window`。未越界修补，证据已记 `BLOCKED.md`。
- 书 6 完成并自行还原窗口可行性后，第二轮 `/usr/bin/python3 -m unittest discover -s tests`（exit 0）原始输出：

```text
........................................................................................................................................................................................................................................................................................................................................................
----------------------------------------------------------------------
Ran 344 tests in 26.739s

OK
```

- 最终 G8 精确命令 `/usr/bin/python3 -m unittest tests.test_flyai_live -v`（exit 0）：`Ran 20 tests in 2.098s`、`OK`、skipped 0；其中 FlyAI 八并发、一次重试上限、AMap 原 qps gate/Retry-After 两项均 `ok`。
- 最终 progress/credential 命令 `/usr/bin/python3 -m unittest tests.test_flyai_live tests.test_credentials -v`（exit 0）：`Ran 36 tests in 7.285s`、`OK`、skipped 0。
- synthetic `--progress ndjson` 原始 stderr（stdout 被单独保留）为：

```text
{"attempt":1,"capability":"lodging","event":"query","provider":"flyai"}
{"event":"probe","provider":"flyai","scope":"root","status":"started"}
{"capability":"search-hotel","event":"probe","provider":"flyai","scope":"command","status":"started"}
{"attempt":1,"capability":"lodging","error_class":"rate_limited","event":"degrade","provider":"flyai"}
{"attempt":2,"capability":"lodging","delay_seconds":0.25,"error_class":"rate_limited","event":"retry","provider":"flyai"}
{"attempt":2,"capability":"lodging","event":"query","provider":"flyai"}
{"command":"lodging","event":"completion","items":1,"provider":"flyai","status":"ok"}
```

- `/usr/bin/python3 scripts/scan_secrets.py`（exit 0）：`secret scan: 0 finding(s) across 357 file(s)`；`git diff --check` 与 compileall 均 exit 0。
- 书 7 当前验收轮次：6/14；剩余为并行提交归属与最终 forbidden-path/diff 审计。

## 书 6 最终验收（提交前）

- 最终定向：`/usr/bin/python3 -m unittest tests.test_scheduler tests.test_keyless_e2e -v`（exit 0）→ `Ran 69 tests in 4.701s`、`OK`、skipped 0。
- 最终全量：`/usr/bin/python3 -m unittest discover -s tests`（exit 0）原始输出：

```text
..........................................................................................................................................................................................................................................................................................................................................................
----------------------------------------------------------------------
Ran 346 tests in 26.016s

OK
```

- 最终 slow 原始日程（同一 7 POI 合成输入）：

```json
[{"kind":"poi","ref_id":"poi-pace-1","start_at":"2026-10-16T09:00:00+08:00","end_at":"2026-10-16T09:45:00+08:00"},{"kind":"poi","ref_id":"poi-pace-2","start_at":"2026-10-16T10:05:00+08:00","end_at":"2026-10-16T10:50:00+08:00"},{"kind":"poi","ref_id":"poi-pace-3","start_at":"2026-10-16T11:10:00+08:00","end_at":"2026-10-16T11:55:00+08:00"},{"kind":"meal","ref_id":"poi-routine-meal-620a5960f942","start_at":"2026-10-16T11:55:00+08:00","end_at":"2026-10-16T12:55:00+08:00"},{"kind":"rest","ref_id":null,"start_at":"2026-10-16T13:00:00+08:00","end_at":"2026-10-16T14:30:00+08:00"},{"kind":"meal","ref_id":"poi-routine-meal-e3757ee53ef1","start_at":"2026-10-16T16:30:00+08:00","end_at":"2026-10-16T17:30:00+08:00"}]
```

- 最终 full 原始日程（同一输入）：

```json
[{"kind":"poi","ref_id":"poi-pace-1","start_at":"2026-10-16T08:00:00+08:00","end_at":"2026-10-16T08:45:00+08:00"},{"kind":"poi","ref_id":"poi-pace-2","start_at":"2026-10-16T09:05:00+08:00","end_at":"2026-10-16T09:50:00+08:00"},{"kind":"poi","ref_id":"poi-pace-3","start_at":"2026-10-16T10:10:00+08:00","end_at":"2026-10-16T10:55:00+08:00"},{"kind":"poi","ref_id":"poi-pace-4","start_at":"2026-10-16T11:15:00+08:00","end_at":"2026-10-16T12:00:00+08:00"},{"kind":"meal","ref_id":"poi-routine-meal-620a5960f942","start_at":"2026-10-16T12:00:00+08:00","end_at":"2026-10-16T13:00:00+08:00"},{"kind":"poi","ref_id":"poi-pace-5","start_at":"2026-10-16T13:20:00+08:00","end_at":"2026-10-16T14:05:00+08:00"},{"kind":"rest","ref_id":null,"start_at":"2026-10-16T14:05:00+08:00","end_at":"2026-10-16T14:35:00+08:00"},{"kind":"poi","ref_id":"poi-pace-6","start_at":"2026-10-16T14:55:00+08:00","end_at":"2026-10-16T15:40:00+08:00"},{"kind":"poi","ref_id":"poi-pace-7","start_at":"2026-10-16T16:00:00+08:00","end_at":"2026-10-16T16:45:00+08:00"},{"kind":"meal","ref_id":"poi-routine-meal-e3757ee53ef1","start_at":"2026-10-16T16:45:00+08:00","end_at":"2026-10-16T17:45:00+08:00"}]
```

- 最终静态门禁：`scripts/scan_secrets.py` → `0 finding(s) across 357 file(s)`；`git diff --check`、两文件 `cmp -s`、planning/scheduler `py_compile` 均 exit 0；两份 schema SHA-256 同为 `66a951fc3b52d44b7371202c53ecadcf3559136d142e70bf6a7496c036873f63`；package 与 manifest 版本仍 `0.2.0`。
- 书 6 最终验收轮次：10/14（3 次意图性反向红不计）；未触发连续三败止损。

## 书 7 最终交付

- 独占代码、测试与两份相关 Skill 已以 `3f2082d Add provider resilience and CLI helpers` 提交；该提交精确 10 个书 7 路径、`1378 insertions(+), 30 deletions(-)`，未夹带书 6 源码。
- 书 6 随后以 `9097463` 提交其 planning/schema/scheduler 工作和此前共享日志；提交后工作树一度完全干净，证明两份所有权已分离。
- 最终联合全量（书 6 最后代码 + 书 7 最后代码）`/usr/bin/python3 -m unittest discover -s tests` 原始收尾：

```text
................
----------------------------------------------------------------------
Ran 346 tests in 31.327s

OK
```

- skipped 0；高于要求的 ≥330。最终 `/usr/bin/python3 scripts/scan_secrets.py` 为 `secret scan: 0 finding(s) across 357 file(s)`。
- 版本保持 `0.2.0`；未运行 demo、未 pip/npm install、未安装进 Codex、未修改 CI。所有指定红→绿证据、doctor 两模式与 progress 原始事件均在书 7 上述小节。
- 流程偏差如实保留在 `BLOCKED.md`：一次只读无命中 grep 曾误用禁用的 `|| true`；它未掩盖验收失败，但按任务书的绝对措辞仍是已披露的不合格点。
- 书 7 最终验收轮次：7/14；无连续三败，代码功能与全部自动验收均完成。

## 书 8 开工理解（2026-09-04，≤10 行）
1. 目标：在 0.2.0 内让异地 traveler groups 可分别出发并按 meeting anchor 会合，同时让紧凑 slow 行程按显式阶梯降配后可交付。
2. 顺序：任务 0 基线/复现 → traveler_groups 与 meeting_anchor → transport group_refs/分组及全团价格 → slow 三步降配 → 全门禁/提交。
3. 单 `origin + travelers` 是冻结兼容路径；与 `traveler_groups` 同时出现必须结构化失败，绝不猜测优先级。
4. 每条分组交通腿必须明确 group_refs；归属缺失绝不默认全团，人数和价格口径必须能从 Trip 追溯。
5. meeting buffer 默认 60 分钟；不足必须结构化冲突，不可静默通过。
6. slow 仅在原排程无解时依次减当日 POI、压到推荐时长 70%、放宽到 balanced 结束时间，每次实际降配都追加 request.assumptions。
7. 最大风险：分组去程与既有单 origin 往返路线共存时破坏旧 Trip bytes/预算语义，以及降配误吞非窗口类硬冲突。
8. 只写任务书白名单，不动 CLI/providers/render/demo/manifest/版本，不安装依赖或插件；当前验收轮次 0/14。

## 书 8 任务 0：基线与 slow 失败复现（完成）

- Git 根为本目录；开工 `git status --short --branch` 输出 `## main...origin/main`，HEAD 与 `origin/main` 均为 `5eb2b7fdaad3db857192c4de29431106097caf90`。
- `/usr/bin/python3 -m unittest discover -s tests`（exit 0）原始摘要：`Ran 346 tests in 29.244s`、`OK`，skipped 0。
- `/usr/bin/python3 scripts/scan_secrets.py`（exit 0）原始输出：`secret scan: 0 finding(s) across 357 file(s)`。
- 内存加载 `tests/fixtures/e2e/beijing-shanghai-3d/{request,candidates,rail}.json`，仅把 request `pace` 改为 `slow` 后调用同一 `plan_trip`（exit 1）原始输出：

```text
PLAN_FAILED plan has no feasible schedule: {"budget_ledger":null,"conflict":{"code":"window","message":"required candidate routine-transfer-buffer-2ab34ef75296 has no feasible insertion"}}
```

- 现状与任务书逐项吻合，进入任务 1；当前验收轮次 0/14。

## 书 8 任务 1：旅客分组与会合锚点（完成）

- request 接受 `traveler_groups[]`（`group_id/travelers/origin/可选 mobility_profile`）与 `meeting_anchor`（`location/meet_by/buffer_minutes`）；buffer 缺省时规范化为 60。调用方若把该形状与单 `origin + travelers` 同时提交，立即返回含 `TRAVELER_REPRESENTATION_CONFLICT` 的结构化错误。
- 两组合成 G6 使用北京 2 人、广州 1 人分别到 `airport-shanghai`；两条 rail leg 均为 08:00–12:00，`meet_by=13:00`，实际 buffer 恰为 60 分钟。会合前并行腿不挤进共享日程；13:00 前午餐明确留在分组阶段，request assumption 记录 `MEETING_PRE_JOIN_MEAL meal_type=lunch`。
- 单 origin 兼容断言：输入 request 与 Trip request 全等，既有 legs 不新增 `group_refs`，Trip 不新增 `transport_pricing`；完整旧 E2E 均通过。
- 指定反向验证：临时去掉 `actual_buffer < required_buffer` 判断（已还原），精准 G6（exit 1）原始输出：

```text
test_g6_insufficient_meeting_buffer_is_a_structured_conflict ... FAIL
AssertionError: ValueError not raised
----------------------------------------------------------------------
Ran 1 test in 0.019s

FAILED (failures=1)
```

- 还原后 `/usr/bin/python3 -m unittest tests.test_keyless_e2e -v`（exit 0）原始摘要：`Ran 28 tests in 3.865s`、`OK`，skipped 0。
- 当前验收轮次 1/14；无非意图性失败。

## 书 8 任务 2：交通腿归属与分组价格（完成）

- grouped request 的每条 rail/flight leg 都必须显式关联 `group_refs`；meeting arrival 为单组 refs，共同行程为全部参与组 refs。找不到、未知或重复归属均返回 `TRANSPORT_GROUP_*` 结构化冲突，不回退到全团。
- G6 两条腿原始价格均为 CNY 300/人；按 refs 与人数计算后 `family-beijing=600`、`family-guangzhou=300`，Trip `transport_pricing.party_total_cny={minimum:900,maximum:900}`；budget transport items 同为 600/300，meeting legs 作为已承诺成本预留但不强塞进单线共享日程。
- 指定反向验证：临时把缺失 refs 改为 `refs = list(groups)` 默认全团（已还原），精准用例（exit 1）原始输出：

```text
test_grouped_transport_without_group_refs_never_defaults_to_the_party ... FAIL
AssertionError: ValueError not raised
----------------------------------------------------------------------
Ran 1 test in 0.018s

FAILED (failures=1)
```

- 还原后 `/usr/bin/python3 -m unittest tests.test_keyless_e2e -v`（exit 0）原始摘要：`Ran 28 tests in 3.840s`、`OK`，skipped 0。
- 当前验收轮次 2/14；两次指定反向红均已还原。

## 书 8 任务 3：slow 降配阶梯（完成）

- `LightScheduler.schedule_plan` 在 `pace=slow` 原排程无解时累计尝试：每日 POI cap 3→2；POI 与作为 POI 实体建模的 meal 时长取推荐值 70%（向上取整）；day end 放宽到 balanced 21:30。命中即停止；三步不能改变的硬冲突保留原 code，并列出全部 attempted relaxations。
- 任务 0 的北京→上海 3 日输入在第 2 步排出，Trip request assumptions 精确追加 `SLOW_FALLBACK_REDUCE_DAILY_POIS max_pois=2` 与 `SLOW_FALLBACK_COMPRESS_POI_DURATION factor=0.70 kinds=poi,meal`；每天实际景点数均 ≤2。
- 独立 scheduler 用例证明第 3 步只有前两步仍失败才执行；固定时段重叠的极端输入三步后仍为 `NO_SOLUTION/window` 并带 3 个 `attempted_relaxations`；closed 硬冲突三步后仍保留 `closed`。
- 指定反向验证：临时停止把 scheduler relaxations 追加到 request assumptions（已还原），精准用例（exit 1）原始关键输出：

```text
test_task0_tight_slow_plan_uses_visible_ordered_degradation ... FAIL
AssertionError: Lists differ: ['无地图 Key 时使用保守静态路线估算', 'SLOW_FALLBACK_REDUCE_DAILY_POIS ...', 'SLOW_FALLBACK_COMPRESS_POI_DURATION ...'] != ['无地图 Key 时使用保守静态路线估算']
First list contains 2 additional elements.
----------------------------------------------------------------------
Ran 1 test in 0.032s

FAILED (failures=1)
```

- 还原后 `/usr/bin/python3 -m unittest tests.test_scheduler tests.test_keyless_e2e -v`（exit 0）原始摘要：`Ran 79 tests in 4.679s`、`OK`，skipped 0。
- 当前验收轮次 3/14；三项功能与三次指定反向红→绿均完成。

## 书 8 合同收紧与集成门禁

- 发现并修正中间实现的兼容投影泄漏：最终 grouped Trip request 只含 `traveler_groups + meeting_anchor`，明确不含 `origin/travelers`；旧 consumer 需要的总人数/共同起点投影只在 planner 内部调用边界临时生成。G6 与旧形状精准两测 `Ran 2 ... OK`。
- Schema root 对 grouped request 条件要求 `transport_pricing`，并要求每条 transport leg 有 `group_refs`；raw grouped request 经 `SchemaSubsetValidator(...request)` 实测 `group_request_schema_issues=0`。两份 Schema 逐字一致。
- 文档仅更新 README 中英文的旅客/节奏段与主 Skill 对应边界：二选一输入、默认 60 分钟、分组/全团价格、slow 三步顺序与留痕；未改安装、版本、demo 或 provider 章节。
- `/usr/bin/python3 -m unittest tests.test_scheduler tests.test_keyless_e2e -v`（严格互斥形状收紧后，exit 0）→ `Ran 79 tests in 4.549s`、`OK`，skipped 0。
- 首次全量 `/usr/bin/python3 -m unittest discover -s tests`（exit 0）原始摘要：`Ran 356 tests in 30.591s`、`OK`，skipped 0（基线 346，新增 10，满足 ≥352）。
- 不能在白名单内原生修正的事实已置顶写入 `BLOCKED.md`：公开 `validate_trip` 仍直接索引 legacy origin，单独验证 grouped Trip 原始输出为 `KeyError: 'origin'`；planner 内已对真实形状做 schema 检查并用临时 endpoint 投影跑完整既有语义检查，未把投影写入 Trip。
- 当前验收轮次 5/14；无非意图性测试失败。

## 书 8 最终交付门禁（提交前）

- 按拍板字面收紧：slow 的三步会在任意原始无解后依次尝试；对 `closed/route/budget` 等无法改变的硬冲突，三步后保留原 conflict code 并附 `attempted_relaxations`，不吞错。最终联合 `/usr/bin/python3 -m unittest tests.test_scheduler tests.test_keyless_e2e -v` → `Ran 79 tests in 4.089s`、`OK`，skipped 0。
- 任务 0 同一内存改 pace 命令的改后原始输出（exit 0）：

```text
PLAN_COMPLETE trip_sha256=b98070dd9052c95cb0962f88641b9aa0aadfbe32b1e256bf4b8bc7499866e778
assumptions=["无地图 Key 时使用保守静态路线估算","SLOW_FALLBACK_REDUCE_DAILY_POIS max_pois=2","SLOW_FALLBACK_COMPRESS_POI_DURATION factor=0.70 kinds=poi,meal"]
daily_poi_counts=[1,1,1]
```

- G6 最终原始摘要（exit 0）：

```text
G6_COMPLETE
request_keys=assumptions,budget_cny,constraints,destinations,end_date,interests,locale,meeting_anchor,pace,pasted_notes,start_date,traveler_groups
meeting_buffer_minutes=60
legs=[{"from_ref":"city-beijing","to_ref":"airport-shanghai","group_refs":["family-beijing"],"travelers":2,"unit_price_cny":300},{"from_ref":"city-guangzhou","to_ref":"airport-shanghai","group_refs":["family-guangzhou"],"travelers":1,"unit_price_cny":300}]
transport_pricing={"currency":"CNY","group_totals":[{"group_ref":"family-beijing","travelers":2,"total_cny":{"minimum":600,"maximum":600}},{"group_ref":"family-guangzhou","travelers":1,"total_cny":{"minimum":300,"maximum":300}}],"party_total_cny":{"minimum":900,"maximum":900}}
```

- 最终全量 `/usr/bin/python3 -m unittest discover -s tests`（exit 0）原始输出：

```text
....................................................................................................................................................................................................................................................................................................................................................................
----------------------------------------------------------------------
Ran 356 tests in 24.682s

OK
```

- skipped 0；基线 346→最终 356。`/usr/bin/python3 scripts/scan_secrets.py`（exit 0）→ `secret scan: 0 finding(s) across 357 file(s)`。
- `git diff --check` exit 0；`git diff --name-only` 恰为 11 个白名单文件；针对 `cli.py/providers/mobility.py/render/demo/plugin.json/test_packaging.py/scan_secrets.py/docs/research` 的 diff 命令 exit 0 且输出为空。
- 两份 Schema `cmp -s` exit 0，SHA-256 同为 `fa8c9075fa044fd51d71fc5ddc7b3c2cd5dbbbbd85b677d5135661aa58d345ff`；manifest 只读核验版本仍为 `0.2.0`。
- 当前验收轮次 8/14；没有非意图性验收失败，三次指定反向变更均已还原。公开 validator 的白名单阻塞保留在 `BLOCKED.md`，其余书 8 条件已完成。

## 0.3.0 发布开工理解（2026-09-04，≤10 行）

1. 目标：公开 validator、renderer、FlyAI inventory 原生消费严格互斥的分组 request，并发布/安装 0.3.0。
2. 顺序：任务 0 基线与 KeyError 复现 → 三消费方与投影清理 → 四组 demo → 10 处版本 → 真实 Codex 安装。
3. 分组端点集合必须并入每组 origin；人数取各组之和；渲染出发地按组列出，不向 request 持久化派生字段。
4. planning.py 只删除本次原生支持后确实多余的投影，仍服务其他旧消费者的投影保留并注明原因。
5. 每项保留真实命令输出；validator 合并组出发地必须做一次临时移除的红→还原绿验证。
6. 最大风险：语义引用集合、HTML 内嵌原始 Trip 与 planner 内部调用边界同时收紧时破坏旧单出发流程。
7. 边界：只写任务白名单；不动 schema、docs/research、其他 provider/CLI/scheduler，不放宽断言、不跳过测试。
8. 止损上限 14 轮；同一验收连败 3 次转下一项并如实记录，最终 `BLOCKED.md` 必须随交付存在。

## 0.3.0 任务 0：基线与分组崩溃复现（完成）

- Git 根为 `/Users/kangyishuai/Workspace/core/ChinaTripWeaver/china-trip-weaver`；开工 HEAD 与 `origin/main` 均为 `0034ac6c1c45de5902ddcb138bfcfedba3ae4a6a`，worktree clean。
- `/usr/bin/python3 -m unittest discover -s tests`（exit 0）原始输出：

```text
....................................................................................................................................................................................................................................................................................................................................................................
----------------------------------------------------------------------
Ran 356 tests in 25.923s

OK
```

- `/usr/bin/python3 scripts/scan_secrets.py`（exit 0）原始输出：

```text
secret scan: 0 finding(s) across 357 file(s)
```

- 使用既有全合成 G6 构造器在内存生成 Trip；schema-only 验证为真，request 严格不含 `origin/travelers`，两腿均有 `group_refs`，根含 `transport_pricing`。随后直接调用两个公开消费方，原始输出：

```text
GROUPED_TRIP_SCHEMA_OK True
REQUEST_KEYS ['assumptions', 'budget_cny', 'constraints', 'destinations', 'end_date', 'interests', 'locale', 'meeting_anchor', 'pace', 'pasted_notes', 'start_date', 'traveler_groups']
GROUPS [('family-beijing', 2, 'city-beijing'), ('family-guangzhou', 1, 'city-guangzhou')]
LEG_GROUP_REFS [['family-beijing'], ['family-guangzhou']]
TRANSPORT_PRICING_PRESENT True
BEGIN validate_trip
Traceback (most recent call last):
  File "<stdin>", line 17, in <module>
  File "<stdin>", line 14, in <lambda>
  File ".../validate_trip.py", line 486, in validate_trip
    semantic_errors = semantic_issues(trip) if semantic else []
  File ".../validate_trip.py", line 293, in semantic_issues
    origin = trip["request"]["origin"]
KeyError: 'origin'
END validate_trip
BEGIN render_trip
Traceback (most recent call last):
  File "<stdin>", line 17, in <module>
  File "<stdin>", line 14, in <lambda>
  File ".../render/html.py", line 140, in render_trip
    report = validate_trip(trip)
  File ".../validate_trip.py", line 486, in validate_trip
    semantic_errors = semantic_issues(trip) if semantic else []
  File ".../validate_trip.py", line 293, in semantic_issues
    origin = trip["request"]["origin"]
KeyError: 'origin'
END render_trip
```

- 当前验收轮次：0/14；复现与任务现状一致，可以进入实现。

## 0.3.0 任务 1：三个消费方原生支持分组（完成）

- `validate_trip` 原生把每个 `traveler_groups[].origin`、`meeting_anchor.location` 与 destinations 合入引用集合；跨城起点判定接受非空分组起点，不再索引缺失的 legacy `origin`。
- renderer 原生汇总各组人数；中文出发地按 `北京（2 人）、广州（1 人）` 显示，英文按逐组 traveler(s) 显示；引用名包含各组起点与会合点，交通腿不再显示“地点尚未解析”。
- FlyAI/AMap lodging 参数对分组 request 的 `adult_count` 固定取各组 `travelers` 之和；legacy `adult_count → party.adults → travelers` 优先级保持不变。
- planning 已把真实 grouped request 直接交给 FlyAI，并直接调用公开 `validate_trip`/`render_trip`；删除 `_legacy_request_projection`、`_validate_planned_trip`、`_render_planned_trip` 及私有 renderer/embedded JSON imports。仓内已无兼容投影引用，故没有仍需保留并注释的投影。
- 新增 4 个精准回归，改前同一命令原始摘要为 `Ran 4 tests ... FAILED (errors=4)`；三处分别 `KeyError: 'origin'`，FlyAI 为 `KeyError: 'travelers'`。改后原始摘要：

```text
test_grouped_trip_validates_natively_with_each_origin_endpoint ... ok
test_grouped_trip_renders_natively_with_total_and_origin_list ... ok
test_grouped_trip_public_cli_validate_and_validate_html ... ok
test_grouped_flyai_lodging_adult_count_is_group_sum ... ok
----------------------------------------------------------------------
Ran 4 tests in 0.168s

OK
```

- 指定反向验证：临时把 validator 的 group-origin 合并替换为空列表（已还原），精准测试 exit 1 原始关键输出：

```text
test_grouped_trip_validates_natively_with_each_origin_endpoint ... ERROR
ValueError: Trip validation failed: V_ENDPOINT_REF /transport_legs/0/from_ref transport endpoint does not exist; V_ENDPOINT_REF /transport_legs/1/from_ref transport endpoint does not exist; V_ORIGIN_REQUIRED /request/origin cross-city travel requires an origin
----------------------------------------------------------------------
Ran 1 test in 0.009s

FAILED (errors=1)
```

- 还原后要求的 `/usr/bin/python3 -m unittest tests.test_keyless_e2e tests.test_renderer -v`（exit 0）原始摘要：

```text
----------------------------------------------------------------------
Ran 65 tests in 5.405s

OK
```

- 严格分组 Trip 序列化后公开 CLI 原始输出：

```text
COMMAND .../scripts/ctw validate exit 0
VALID .../.tmp/tmpso0nyy4j/grouped-trip.json
COMMAND .../scripts/ctw validate-html exit 0
HTML VALID .../.tmp/tmpso0nyy4j/grouped-trip.html errors=0
```

- 当前验收轮次：1/14；Task 1 正向门与指定红→绿均完成，临时变更已还原。

## 0.3.0 任务 2：四组 demo 重跑（完成）

- `build_plan_fixtures.py` 新增纯合成 `grouped_departures_demo()`，生成 `demo/grouped-departures/request.json|candidates.json`：北京 2 人、广州 1 人分别到上海虹桥机场会合；request 严格不含 legacy `origin/travelers`。生成器重跑输出：

```text
wrote 3 plan cases, 3 invalid candidates, and single/multi-city/grouped demo inputs; packaged reference verified
```

- 三组首次与 grouped 新组离线重跑中，北京→上海、多城市、分组组均 exit 0；原始输出：

```text
PLAN_COMPLETE json=demo/trip.json html=demo/trip.html mode=static stages=INTAKE,RESEARCHED,CANDIDATES_READY,MATRIX_DEGRADED,SCHEDULED,VALIDATED,RENDERED calls=rail12306.fixture:2026-10-16:北京:上海,rail12306.fixture:2026-10-18:上海:北京 trip_sha256=5c4a3c32db5bf700228ce1faa35dee23999f4868555bcd213f0fde5b7547a17c html_sha256=ed161aa9f0f2ecbe368fc02230f14e2d9c8a0b59b472ee474d941703cd7cf47b errors=0
PLAN_COMPLETE json=demo/multicity-5d/trip.json html=demo/multicity-5d/trip.html mode=static stages=INTAKE,RESEARCHED,CANDIDATES_READY,MATRIX_DEGRADED,SCHEDULED,VALIDATED,RENDERED calls= trip_sha256=12b01b2971970d291253d8e5e0a0b611bfa3211d30290bcbc9d3988e61c132c1 html_sha256=a8f83e9aeb00b89c3067fb4e734f06746533499e54a8598ec64804c82865ef9f errors=0
PLAN_COMPLETE json=demo/grouped-departures/trip.json html=demo/grouped-departures/trip.html mode=static stages=INTAKE,RESEARCHED,CANDIDATES_READY,MATRIX_DEGRADED,SCHEDULED,VALIDATED,RENDERED calls=rail12306.fixture:2026-09-10:北京:上海虹桥国际机场,rail12306.fixture:2026-09-10:广州:上海虹桥国际机场 trip_sha256=4be53526d0c77112344b3a0aa99f0168f03a2cf75ba54f0b2b5afb9c18206c96 html_sha256=3715615d7514a8ace116235a72c68caf2d03f173d190606d0d115c1d85774162 errors=0
```

- 广州→深圳首次重跑（exit 1）暴露旧 demo 输入与新硬缓冲的真实冲突：5 小时合成降级腿之间只有 3 小时，却要求两次 45 分钟换乘缓冲及默认各 60 分钟的午餐、晚餐、午休；原始输出：

```text
PLAN_FAILED plan has no feasible schedule: {"attempted_relaxations":[],"budget_ledger":null,"conflict":{"code":"window","message":"required candidate routine-transfer-buffer-3fe32ee61fc6 has no feasible insertion"}}
```

- 保留一日往返语义，只在该合成 request 明示 30 分钟午/晚简餐与 15 分钟短休；第二次同一离线命令 exit 0：

```text
PLAN_COMPLETE json=demo/guangzhou-shenzhen/trip.json html=demo/guangzhou-shenzhen/trip.html mode=static stages=INTAKE,RESEARCHED,CANDIDATES_READY,MATRIX_DEGRADED,SCHEDULED,VALIDATED,RENDERED calls=rail12306.fixture:2026-09-10:广州:深圳,rail12306.fixture:2026-09-10:深圳:广州 trip_sha256=85c2b9f73bf831b786f91397b6c2600c4e1322d999de3b1c9aec017eb2cf1288 html_sha256=db28a8d0ec8780be7a1e22e4b21cbac1edcb23f24b79c88cd7294f819b7ff4fa errors=0
```

- 四组公开验证八条命令均 exit 0，原始输出：

```text
VALID demo/trip.json
HTML VALID demo/trip.html errors=0
VALID demo/guangzhou-shenzhen/trip.json
HTML VALID demo/guangzhou-shenzhen/trip.html errors=0
VALID demo/multicity-5d/trip.json
HTML VALID demo/multicity-5d/trip.html errors=0
VALID demo/grouped-departures/trip.json
HTML VALID demo/grouped-departures/trip.html errors=0
```

- `/usr/bin/python3 scripts/scan_secrets.py` 对 `rg --files demo` 的全部 16 个文件（exit 0）：`secret scan: 0 finding(s) across 16 file(s)`。
- 新的 checked-in demo 回归（exit 0）断言严格互斥 request、3 人合计、两条 group refs、party CNY 900、可见分组出发地及 Trip/HTML 全有效：`Ran 1 test in 0.009s`、`OK`。
- 当前验收轮次：2/14；一次非连续 demo 验收失败已由白名单内合成输入修正，未触碰 scheduler。

## 0.3.0 任务 3：版本发布面同步（完成）

- 一次补齐任务书列出的 10 处精确版本：package `__version__`、manifest、MCP `clientInfo`、两份 README 安装预期、`test_packaging.py` 两处，以及 credentials/contracts/skills 各一处；所有断言仍为 `assertEqual("0.3.0", ...)` 精确相等。
- 两份 README 同时删除已失效的“旧消费端兼容投影”说法，改为 validator/renderer/inventory 原生消费分组；新增第四组 demo 的可见证据入口。
- `rg -n '0\.3\.0'` 对上述九个文件（packaging 含两处）实际恰好返回 10 行。固定字符串旧版本审计：

```text
/usr/bin/grep -rnF --exclude-dir=__pycache__ "0.2.0" README.md README.zh-CN.md plugins/china-trip-weaver/src plugins/china-trip-weaver/.codex-plugin tests/test_packaging.py tests/test_credentials.py tests/test_contracts.py tests/test_skills.py scripts/build_renderer_fixtures.py scripts/build_plan_fixtures.py demo
exit=1
<no output>
```

- 一次检查误用 plain `grep "0.2.0"`，点号按正则通配而命中 demo 数字和旧 `.pyc`；未修改文件。随后以上 fixed-string source audit 给出真实零命中。
- `git diff -- docs/research plugins/china-trip-weaver/schema docs/design/schema`（exit 0）输出为空。
- 版本后的全量 `/usr/bin/python3 -m unittest discover -s tests`（exit 0）原始输出：

```text
.........................................................................................................................................................................................................................................................................................................................................................................
----------------------------------------------------------------------
Ran 361 tests in 28.079s

OK
```

- skipped 0；满足 ≥360。同期 `/usr/bin/python3 scripts/scan_secrets.py`（exit 0）：`secret scan: 0 finding(s) across 361 file(s)`。
- 当前验收轮次：3/14；版本、精确断言、全量测试与旧版本审计均通过。

## 0.3.0 任务 4：安装进真实 Codex（完成）

- 按要求不设置 `CODEX_HOME`，真实目标为 `/Users/kangyishuai/.codex`。首次 `scripts/install_local_plugin.sh` 已把 plugin list 更新到 `installed, enabled 0.3.0`，但 source/cache diff 因插件源码下遗留的 398 MB Git-ignored `.npm-cache` 而 exit 1：

```text
SKILL parser smoke: OK (9 SKILL.md via codex debug prompt-input)
已执行 plugin add china-trip-weaver@china-trip-weaver-local
plugin list: installed, enabled 0.3.0
校验失败：缓存与源码不一致（先跑不带 --check 的本脚本刷新）
Only in .../plugins/china-trip-weaver/.npm-cache/.../node_modules/.bin: 12306-mcp
```

- `git status --ignored` 与 `git check-ignore -v` 确认该树完全由根 `.gitignore:3:.npm-cache/` 忽略，mtime 为 2026-09-04，且不属于源码或安装缓存。直接删除被执行环境拒绝，故按可恢复原则把唯一精确目录移入 `/Users/kangyishuai/.Trash/china-trip-weaver-plugin-npm-cache-20260905-release`；源码位置已不存在，tracked 状态未受影响。
- 第二次同一真实安装命令（exit 0）原始输出：

```text
codex: /Applications/ChatGPT.app/Contents/Resources/codex
源码: .../plugins/china-trip-weaver (manifest 版本 0.3.0)
Codex home: /Users/kangyishuai/.codex
SKILL parser smoke: OK (9 SKILL.md via codex debug prompt-input)
本地市场已注册 -> /Users/kangyishuai/Workspace/core/ChinaTripWeaver/china-trip-weaver
已执行 plugin add china-trip-weaver@china-trip-weaver-local
plugin list: installed, enabled 0.3.0
OK：china-trip-weaver@china-trip-weaver-local 0.3.0 已安装且缓存与源码一致
提醒：在 Codex 里新建一个任务才会加载新版本；若 Skill 未出现，重启 Codex 桌面版
```

- 独立 `/Applications/ChatGPT.app/Contents/Resources/codex plugin list` 目标行（exit 0）：

```text
china-trip-weaver@china-trip-weaver-local  installed, enabled  0.3.0    /Users/kangyishuai/Workspace/core/ChinaTripWeaver/china-trip-weaver/plugins/china-trip-weaver
```

- 最终 `scripts/install_local_plugin.sh --check`（exit 0）原始关键输出：

```text
SKILL parser smoke: OK (9 SKILL.md via codex debug prompt-input)
本地市场已注册 -> /Users/kangyishuai/Workspace/core/ChinaTripWeaver/china-trip-weaver
plugin list: installed, enabled 0.3.0
OK：china-trip-weaver@china-trip-weaver-local 0.3.0 已安装且缓存与源码一致
```

- 当前验收轮次：4/14；真实安装、独立状态核对与只读缓存一致性检查均完成。

## 0.3.0 最终验收（完成）

- 最终代码审阅补了防御式 `request.get("traveler_groups") or ()`，避免非法 null 形状在直接调用内部语义/渲染 helper 时变成迭代异常；冻结 Schema 实际会先以 `S_ONE_OF + S_REQUIRED` 拒绝显式 null。新增负向回归最初错误地假设该形状合法，精准门 `Ran 4 ... FAILED (errors=1)`；核对 Schema 后改为断言 typed rejection，同门 `Ran 4 ... OK`，未改 Schema。
- 最终全量 `/usr/bin/python3 -m unittest discover -s tests`（exit 0）原始输出：

```text
..........................................................................................................................................................................................................................................................................................................................................................................
----------------------------------------------------------------------
Ran 362 tests in 24.601s

OK
```

- skipped 0；基线 356→最终 362，满足 ≥360。最终 repo scan：`secret scan: 0 finding(s) across 361 file(s)`；demo 全 16 文件：`secret scan: 0 finding(s) across 16 file(s)`。
- 最终四组八条公开校验原始输出：

```text
VALID demo/trip.json
HTML VALID demo/trip.html errors=0
VALID demo/guangzhou-shenzhen/trip.json
HTML VALID demo/guangzhou-shenzhen/trip.html errors=0
VALID demo/multicity-5d/trip.json
HTML VALID demo/multicity-5d/trip.html errors=0
VALID demo/grouped-departures/trip.json
HTML VALID demo/grouped-departures/trip.html errors=0
```

- 最终固定字符串 0.2.0 审计 exit 1、输出为空。要求的 keyless+renderer 命令最终为 `Ran 67 tests in 6.200s`、`OK`、skipped 0。
- 防御式两行代码是在上一次真实安装后加入，故首次最终 `--check` 如实 exit 1 并列出 validator/renderer cache stale；随即再次运行不带 `CODEX_HOME` 的 installer 刷新源码，exit 0。刷新后的最终 `--check` 原始关键输出：

```text
SKILL parser smoke: OK (9 SKILL.md via codex debug prompt-input)
plugin list: installed, enabled 0.3.0
OK：china-trip-weaver@china-trip-weaver-local 0.3.0 已安装且缓存与源码一致
```

- 最终独立 plugin list 行：`china-trip-weaver@china-trip-weaver-local  installed, enabled  0.3.0    /Users/kangyishuai/Workspace/core/ChinaTripWeaver/china-trip-weaver/plugins/china-trip-weaver`。
- 当前验收轮次：6/14；没有同一验收三连败，所有完成条件已绿。

## 0.3.0 最终边界快照

- `git diff --check` exit 0。`git status --short` 只列任务白名单中的 25 个 tracked 文件及 `?? demo/grouped-departures/`；没有 schema、`docs/research/`、禁碰 provider/CLI/candidates/mobility/scheduler/test/scan 脚本路径。
- `git diff --stat` 原始摘要为 `25 files changed, 671 insertions(+), 129 deletions(-)`；新增 grouped demo 目录因未跟踪而由上方 status 单列，仍在 `demo/全部` 白名单内。
- `git diff --name-only -- docs/research docs/design/schema plugins/china-trip-weaver/schema ...禁碰路径...` exit 0 且输出为空；`rg -n '0\.3\.0'` 对版本清单恰好输出 10 行。
- `git status --short --ignored plugins/china-trip-weaver/.npm-cache` exit 0 且输出为空，确认已移入废纸篓的生成缓存未在源码处复生。
- 边界快照后的 repo secret scan 仍为 `secret scan: 0 finding(s) across 361 file(s)`。

## Journey 模型、拆分与连续性开工理解（2026-09-05，≤10 行）
1. 目标：用一个 Journey 唯一事实源内嵌多个原样完整 Trip，覆盖 16 天等长行程的模型、拆分与跨段连续性。
2. 顺序：任务 0 基线 → Journey Schema/模型 → `ctw journey plan` 自动拆分 → 日期/住宿/预算连续性 → 全量门禁与提交。
3. 拆分优先跨城日，其次硬切；每段仍须独立通过既有 `_normalize_request` 的 1–7 天边界、Trip validator 与 replan。
4. 连续性必须拒绝日期缺口/重叠，显式记录跨段住宿延续，总预算按各段 ledger 加跨段交通汇总。
5. 只写任务书白名单；不碰 render/demo/version/Trip Schema/providers/scheduler/既有测试，不安装 Codex。
6. 最大风险：现有 request/candidates/Trip 数据形状如何无损分段，以及跨城日归属与跨段住宿/预算 ledger 的口径对齐。
7. 任务 0 实测通过：HEAD 与 origin/main=`b73c838`；`Ran 363 tests ... OK`、skipped 0；secret scan 0/361；`replan_trip(` 确认为单 Trip API。
8. 当前验收轮次：1/14；尚未修改产品代码。

## Journey 任务 1：模型（完成）

- 新增插件内唯一 `schema/journey.schema.json` 与 `journey.py`：Journey 含独立 id/revision、全程日期、互斥的共享 `origin + travelers` 或 `traveler_groups + meeting_anchor`、0.3.0 同口径总预算 ledger、完整 `trips[]` 与跨段衔接记录；版本保持 0.3.0。
- Journey Schema 按 candidates 惯例引用唯一 `trip.schema.json`；运行时只读合并 Trip `$defs` 后交给现成 `SchemaSubsetValidator`，并逐个调用 `validate_trip` 做语义校验，没有复制或修改 Trip Schema。
- 正向验收：从 Journey 取出的完整子 Trip 直接 `validate_trip` 为 ok，并原样传给 `replan_trip` 生成 revision 2 后仍有效；`/usr/bin/python3 -m unittest tests.test_journey -v` → `Ran 2 tests in 0.017s`、`OK`、skipped 0。
- 反向红态：临时把正向测试中的子 Trip 换为仅 `schema_version + trip_id` 的裁剪版，同一精准测试 exit 1：`AssertionError: False is not true`，`Ran 1 test ... FAILED (failures=1)`。
- 还原绿态：撤销临时裁剪后重跑完整 `tests.test_journey`，2/2 OK；永久负向测试另断言裁剪版返回 `S_REQUIRED`，没有 skip/mock/放宽断言。
- 当前验收轮次：2/14；Task 1 的临时变更已全部还原。

## Journey 任务 2：自动拆分（完成）

- `planning.py` 仅抽取原规范化公共部分；`_normalize_request` 的 `day_count < 1 or day_count > 7` 与原错误文本保持不变。Journey 长请求走独立公共规范化，每个子请求随后显式再过原 `_normalize_request`，没有放宽 Trip 产品边界。
- 拆分先用原有有序 route 分布定位跨城日，再只对跨城间隔按七天硬切；合成 16 天北京→上海→杭州→苏州得到 `2026-10-01..05`、`06..10`、`11..16` 三段（5/5/6），同城 16 天得到 7/7/2。
- 每段按城市保留完整候选实体/claims，并重写 unknown JSON Pointer；三段分别直接进入现有 `plan_trip`，全部 `validate_trip` 为 ok、days ≤7。
- 首轮同城拆分曾因按日期过滤后违反既有 candidates 的 `pois/claims minItems` 而 1 个测试 ERROR；改为按城市保留候选、由调度器忽略段外窗口，未放宽候选合同。随后 5/5 tests OK。
- 反向红态：临时把硬切步长改为 8 天，精准测试 exit 1；原始错误为 `ValueError: request must cover between one and seven inclusive days`，`Ran 1 test ... FAILED (errors=1)`，证明原 Trip 门实际阻断 8 天段。
- 还原绿态：恢复七天步长后 `/usr/bin/python3 -m unittest tests.test_journey -v` → `Ran 5 tests in 0.119s`、`OK`、skipped 0。
- `plugins/china-trip-weaver/scripts/ctw journey plan --help` exit 0，已暴露 request/candidates/provider/offline/fixed-clock/output-json 参数；实际产物留在 G7 验收。
- 当前验收轮次：3/14；Task 2 的临时 8 天变更已还原。

## Journey 任务 3：跨段连续性（完成）

- G7 合成 16 天 Journey 为 5/5/6 三个完整 Trip；相邻日期逐日相接，前两段最后一天的 stay 被显式延长覆盖边界夜，15 个全程过夜日恰好各覆盖一次。两条 `lodging_continuity` 均为可追溯的 `changed`，两条跨城腿均为 `included_in_next_trip`。
- Journey validator 对日期 gap/overlap 分别返回 `J_DATE_GAP`/`J_DATE_OVERLAP`；同时验证连接相邻 id/日期、from/to lodging、边界夜覆盖、同店/换店状态、transport owner/ref/cost 与总 ledger。预算篡改返回 `J_BUDGET_MISMATCH`。
- 总 ledger 保留 0.3.0 的 currency/budget/known/remaining/range/status/items 口径：Trip ledger 全部相加；已归某子 Trip 的跨段交通显示实际口径但追加额为 0，独立跨段交通则另加。合成离线铁路价格不可比时仍输出 `{minimum:null,maximum:null}` 区间，known lodging cost 为 CNY 4200。
- 正向精准门：`/usr/bin/python3 -m unittest tests.test_journey -v` → `Ran 11 tests in 0.591s`、`OK`、skipped 0；包含 CLI plan+validate、gap、overlap、budget tamper、separate transport addition 与三子 Trip replan。
- 缺口反向红态：临时把第二段 `start_date` 从 10-06 推后到 10-07，G7 exit 1，原始错误列表含 `J_DATE_GAP ... uncovered calendar gap`、`J_CONNECTION_REF`、`J_LODGING_GAP`、`J_TRIP_V_DAY_COUNT`、`J_TRIP_V_DAY_DATES`；`Ran 1 test ... FAILED (failures=1)`。
- 还原绿态：撤销临时日期后同一完整精准门 11/11 OK。
- 实际 CLI：`ctw journey plan ... --rail off --offline-fixture` exit 0 → `JOURNEY_PLAN_COMPLETE ... trips=3 days=16 max_trip_days=6 ... journey_sha256=5bdf15b... errors=0`；紧接 `ctw journey validate` exit 0 → `JOURNEY VALID ... trips=3`。
- 三个子 Trip 的 `ctw validate` 均 exit 0；逐段 `ctw replan` 均输出 `REPLAN_COMPLETE ... revision=2 ... errors=0`，三个 replan 产物再次 `ctw validate` 均 exit 0。
- 主 Skill 已把 >7 天路由到 Journey、保留单 Trip 1–7 天硬边界，并明确不做 Journey 页面/checklist；bundled quick validator exit 0：`Skill is valid!`。
- 当前验收轮次：4/14；Task 3 临时缺口已还原，三项开发任务均完成。

## Journey 最终验收与边界状态

- 新增 grouped 长 Journey 回归：两组旅客只在首段会合，后两段聚合为 3 人的完整 legacy Trip；同城 16 天为 7/7/2，跨段均 `continued + not_required`，Journey 顶层仍保存原 `traveler_groups`。精准门现为 `Ran 13 tests in 0.741s ... OK`、skipped 0。
- 首次全量为 `Ran 375 tests in 39.049s ... FAILED (failures=1)`；唯一失败是禁止修改的 `test_skills.py` 对 frontmatter description 的逐字冻结。恢复该描述、仅把 Journey 指令留在 Skill 正文后，精准冻结测试与 bundled quick validator 均 OK，未改既有测试。
- 恢复后全量为 `Ran 375 tests in 26.528s ... OK`；固化 grouped 回归后的代码态全量为 `Ran 376 tests in 24.545s ... OK`，skipped 0，满足 ≥370。
- `/usr/bin/python3 scripts/scan_secrets.py` → `secret scan: 0 finding(s) across 364 file(s)`；`git diff --check` exit 0；Journey Schema 经 `/usr/bin/python3 -m json.tool` exit 0。
- 原 Trip 上限仍精确位于 `planning.py:369-370`：`day_count < 1 or day_count > 7` 与 `between one and seven inclusive days`；0.4.0 命中 0，plugin version 未改。
- 禁碰路径（render、demo、plugin.json、Trip/candidates Schema、docs、providers、mobility、scheduler、Trip validator、FlyAI、既有 tests、secret scanner）组合 `git diff` 与 `git diff --name-only` 均无输出。
- `BLOCKED.md` 已追加本轮“新增阻塞：无”，并保留 Skill description 冻结冲突的已解决证据；没有总览页、booking checklist、demo 重跑、Codex 安装或版本发布动作。
- 当前验收轮次：7/14；接下来只做暂存态最终门、白名单提交与提交后只读核验。

## 0.4.0 Journey 总览发布开工理解（2026-09-05，≤10 行）
1. 目标：把 16 天 Journey 渲染为可读、离线、确定且可校验的单页总览，并发布安装 0.4.0。
2. 顺序：任务 0 基线 → Journey 渲染/校验 → checklist/风险追溯 → 第五组 demo → 10 处版本 → 全量门禁 → 真实安装。
3. 复用现有 `RENDERER_VERSION`、CSP 与 Trip renderer/validator 约束；新增 `ctw journey render` 与 Journey HTML 校验入口。
4. checklist 必须覆盖全部交通腿、住宿 check-in 与 unknown，按截止时间排序；风险不得漏 degraded/missing、conflict 或未解决 unknown。
5. 只改任务书白名单，尤其不碰 `docs/`、Trip/candidates Schema、`planning.py`、scheduler、mobility、Trip validator 与禁碰测试。
6. 最大风险：Journey/Trip 内引用形状多样，既要完整覆盖、可追溯、无内部 ID，又不能破坏 CSP、离线与字节确定性。
7. 任务 0 实测：HEAD/origin=`5e14bf8`；`Ran 376 tests in 25.546s ... OK`、skipped 0；secret scan 0/364；16 天 Journey=3 Trip/16 天/max 6/SHA-256 `5bdf15b...`。
8. 当前验收轮次：1/14；尚未修改产品代码，基线 Journey 保存在系统临时目录供后续渲染验证。

## 0.4.0 任务 1：Journey 总览页（完成）

- 新增 `render_journey` 与 `validate_journey_html`，由 `ctw journey render` / `ctw journey validate-html` 暴露；复用 `RENDERER_VERSION="1"`、同一 `renderer.css`、CSP、转义、canonical JSON、URL/secret/offline/a11y 门，入口用 lazy export 避免 Journey→planning→render 循环且未碰 `planning.py`。
- 页面继承既有纸色/玉色/朱色视觉系统，以连续分段路线轴为主线；包含全程路线、每段起止、总预算、预订与核验清单、风险与衔接，嵌入完整 Journey，内部 ID 只在校验用 `data-*` 中、不可见文本无泄漏。
- 当前 CLI 输出对应页面 SHA-256 为 `61dd8c6871a9a75f7fcd982efcffa97205105a1929831ac28c14f5e949a66a94`，并通过 `ctw journey validate-html`；先前落盘命令的输出形状为 `JOURNEY_RENDERED ... sha256=<digest> errors=0`。
- 精准正向门：`/usr/bin/python3 -m unittest tests.test_renderer tests.test_journey -v` → `Ran 56 tests in 3.586s`、`OK`、skipped 0。
- 必做反向验证：临时加入 `datetime.now().isoformat()` meta 后确定性测试 exit 1，`Ran 1 ... FAILED (failures=1)`，两次 bytes 仅时间戳 `02.047896`/`02.066575` 不同；移除临时时间戳后同一测试 `Ran 1 test in 0.180s ... OK`。
- 当前验收轮次：2/14；临时时间戳已完整还原。
- `craft-frontend-design` R1 首轮机器 QA 四视口均无 overflow/resource/console 错误，但实际查看 1440 截图发现共享 Trip h1 令“杭州”断字且路线卡右侧空置；以 Journey-only 标题/宽屏路线 CSS 修复后同条件重跑。
- 最终 Chrome QA：320/375/430/1440 的 `failures=[]`、12/12 非空 section、font 16px/line-height 24.8px、min link 44px、resourceRequests/consoleErrors 均空；实际复看 375 与 1440 顶部及移动端 checklist/risk/segment 截图，无剩余 P0–P2。

## 0.4.0 任务 2：checklist 与风险项（完成）

- `journey_booking_checklist` 对每个 Trip 汇总全部交通腿、住宿 check-in 与每条 unknown；日期/时间截止由来源实体确定，缺具体时间保持 date-only 并保守排前，不编造时刻。
- `journey_risk_items` 对每个 degraded/missing health capability、每个 conflict claim 与每条 unresolved unknown 各生成一项；稳定 id、Trip 序号、source kind/ref、claim/path/capability 只进入结构化追溯属性，页面显示名称与本地化状态。
- 16 天基线实测：`checklist=85 kinds={'lodging': 3, 'transport': 3, 'unknown': 79} sorted=True traceable=True`；`risks=103 kinds={'unresolved_unknown': 79, 'provider_capability': 24} traceable=True`。
- 永久回归同时注入 degraded 与 conflict 后精确比较全部 capability/claim/unknown 集合，并验证删任一 checklist/risk DOM 节点分别报 `JH202`/`JH203`；`tests.test_journey` 为 22/22 OK。
- 当前验收轮次：3/14；未丢弃或合并任何 unresolved unknown。

## 0.4.0 任务 3：第五组 16 天 demo（完成）

- `scripts/build_renderer_fixtures.py` 复用现有 `journey_sixteen_day_case()`、固定时钟与 `RailBackend off`，生成 `demo/journey-16d/request.json|candidates.json|journey.json|journey.html`；写入前先跑 Journey HTML validator。
- 最终生成器原始输出：`wrote 9 Trip and 11 HTML renderer fixtures; Journey demo trips=3 days=16 journey_sha256=5bdf15b998e51e0931189181b17102ac11290f98c4bb1d72cc5ac4b425982b7d html_sha256=61dd8c6871a9a75f7fcd982efcffa97205105a1929831ac28c14f5e949a66a94`。
- 五组公开校验全部 exit 0：四组依次输出 `VALID .../trip.json` 与 `HTML VALID .../trip.html errors=0`；Journey 组输出 `JOURNEY VALID demo/journey-16d/journey.json trips=3` 与 `JOURNEY HTML VALID demo/journey-16d/journey.html errors=0`。
- 对 `rg --files demo` 枚举的全部 20 个文件运行 secret scan：`secret scan: 0 finding(s) across 20 file(s)`。
- checked-in demo 回归断言 16 天、页面等于 fresh `render_journey` bytes 且 validator 通过；`/usr/bin/python3 -m unittest tests.test_journey -v` → `Ran 23 tests in 1.281s ... OK`、skipped 0。
- 当前验收轮次：4/14；四组旧 demo 文件未被生成器改写。

## 0.4.0 任务 4：升版本（完成）

- 一次把现状清单的 10 处精确版本从 0.3.0 改为 0.4.0：package、manifest、MCP clientInfo、两份 README、packaging 两处及 credentials/contracts/skills 各一处；所有 manifest/version 断言仍为精确 `assertEqual`。
- 版本精准门：`/usr/bin/python3 -m unittest tests.test_packaging tests.test_credentials tests.test_contracts tests.test_skills -v` → `Ran 53 tests in 8.942s ... OK`、skipped 0；主 Skill description 随 Journey 发现能力改成精确新文本，`tests/test_skills.py` 只同步同一字面值，九个名称与逐字冻结仍通过、未放宽匹配。
- 对十处清单运行 `/usr/bin/grep -rnF "0.3.0" ...` → exit 1、无输出；同一清单 grep 0.4.0 → 恰好 10 行。
- 全量 `/usr/bin/python3 -m unittest discover -s tests` → `Ran 386 tests in 29.192s ... OK`、skipped 0；repo secret scan → `0 finding(s) across 370 file(s)`。
- `git diff --check` exit 0；`git diff -- docs .../trip.schema.json .../candidates.schema.json .../planning.py .../scheduler .../mobility.py .../validate_trip.py` exit 0、无输出。
- 当前验收轮次：6/14；已满足 ≥384 且版本门全绿，尚未执行真实 Codex 安装。

## 0.4.0 任务 5：安装进真实 Codex（完成）

- 未设置 `CODEX_HOME`，运行 `scripts/install_local_plugin.sh`，实际目标 `/Users/kangyishuai/.codex`；exit 0，输出含 `SKILL parser smoke: OK (9 SKILL.md via codex debug prompt-input)`、`plugin list: installed, enabled 0.4.0`、`OK：... 0.4.0 已安装且缓存与源码一致`。
- 独立 `/Applications/ChatGPT.app/Contents/Resources/codex plugin list` 目标行：`china-trip-weaver@china-trip-weaver-local  installed, enabled  0.4.0    /Users/kangyishuai/Workspace/core/ChinaTripWeaver/china-trip-weaver/plugins/china-trip-weaver`。
- 随后 `scripts/install_local_plugin.sh --check` exit 0，输出再次含 `SKILL parser smoke: OK (9 SKILL.md via codex debug prompt-input)`、`plugin list: installed, enabled 0.4.0` 与缓存/源码一致的 `OK`。
- 当前验收轮次：7/14；真实 Codex 安装与只读复核均一次通过。

## 0.4.0 最终提交前验收

- 最终原始产物命令：`ctw journey render demo/journey-16d/journey.json --output /tmp/.../journey-release.html` → `JOURNEY_RENDERED ... sha256=61dd8c6871a9a75f7fcd982efcffa97205105a1929831ac28c14f5e949a66a94 errors=0`。
- 五组十条公开校验最终均 exit 0：四组分别为 `VALID .../trip.json` + `HTML VALID .../trip.html errors=0`；长行程为 `JOURNEY VALID demo/journey-16d/journey.json trips=3` + `JOURNEY HTML VALID demo/journey-16d/journey.html errors=0`。
- 最终全量 `/usr/bin/python3 -m unittest discover -s tests` → `Ran 386 tests in 24.963s ... OK`、skipped 0；repo scan `0 finding(s) across 370 file(s)`；20 个 demo 文件 scan `0 finding(s)`。
- 最终离线 Chrome R1：四视口 `failures=[]`、无横向溢出/外部资源/console error，12/12 section 非空；同条件截图复看标题、路线、checklist、系统风险与分段，P0–P2 均已关闭。
- 最终再次无 `CODEX_HOME` 刷新真实安装并 `--check`：两次均 exit 0；独立 plugin list 为 `installed, enabled 0.4.0`，缓存与当前插件源码一致。
- 修改/新增清单只含任务书白名单；`docs/`、Trip/candidates Schema、`planning.py`、scheduler、mobility、Trip validator diff 为空，mcp_stdio diff 仅 clientInfo 版本串，`git diff --check` 通过。
- `BLOCKED.md` 保留全部历史事实并追加本轮状态“新增阻塞：无”。当前验收轮次：8/14；下一步仅暂存态复核与提交。

## 书 13 Journey 拆分粒度开工理解（2026-09-05，8 行）
1. 目标：住宿城市变化只作候选切点；先守逐夜住宿链与 7 天硬上限，再让 Journey 段数最少。
2. 顺序：任务 0 基线与 8 段复现 → 最少段数 → 可选 1–7 天期望段长 → 两次反向红绿 → 全量门禁与提交。
3. 缺省应把 16 天夹具压到约束允许的最少段数；必须切时先选不晚于硬上限的最近住宿城市变化，否则按第 7 天硬切。
4. 指定期望段长时按偏好寻找切点，但偏好不得突破 7 天或改变候选住宿的逐夜城市、日期与引用。
5. 若实际段长偏离期望值，Journey assumptions 必须写明实际分段与约束优先原因。
6. 最大风险：现有分段候选过滤会不会让跨城市子 Trip 丢住宿/目的地，进而破坏书 12 的逐夜住宿链成果。
7. 任务 0 原始门：`Ran 393 tests in 25.823s`、`OK`、skipped 0；`secret scan: 0 finding(s) across 371 file(s)`。
8. 改前原始 CLI：`JOURNEY_PLAN_COMPLETE ... trips=8 days=16 max_trip_days=3 ... errors=0`；随后 `JOURNEY VALID ... trips=8`。当前轮次 1/12。

## 书 13 任务 1：段数最少化（完成）

- 住宿城市变化已从硬边界降为候选切点；缺省先固定 `ceil(days/7)` 的最少段数，再选仍能保持该段数的最晚住宿变化，找不到才在第 7 天硬切。16 天六城夹具因此从 8 段 `[1,3,1,3,3,2,1,2]` 降为最少 3 段 `[5,6,5]`。
- 每个逻辑 Trip 内部仍按逐夜住宿城市做原子规划，再合并为一个完整多目的地 Trip；合并后重新建立唯一引用、claims/unknown pointers、provider health 与预算，最终逐个 `validate_trip`，没有改 `planning.py` 或放宽住宿链。
- 正向精准门：`/usr/bin/python3 -m unittest tests.test_journey -v` → `Ran 32 tests in 2.567s`、`OK`、skipped 0；逐夜城市/候选住宿、每段 ≤7 天及 Journey validate 均在同一套永久回归内。
- 反向红态：临时把缺省策略改回 `_strict_segment_start_dates` 后，精准测试 exit 1，原始核心输出为 `AssertionError: 3 != 8`、`Ran 1 test in 0.018s`、`FAILED (failures=1)`。
- 还原绿态：恢复最少段数策略后完整 `tests.test_journey` 32/32 OK；临时回退已完整撤销。当前轮次 2/12。

## 书 13 任务 2：可选期望段长（完成）

- Journey API 新增末尾可选关键字 `expected_segment_days`，只接受整数 1–7；未改 Trip Schema 或 CLI。缺省仍最少段数，给值后先确定 `ceil(total/expected)` 个逻辑段，再优先把必要切点放在住宿城市变化处并在同优先级下贴近期望长度。
- 同一 16 天夹具：缺省 3 段 `[5,6,5]`；`expected_segment_days=5` 为 4 段 `[4,4,5,3]`，两者逐夜住宿城市均与候选链一致、每段均 ≤7、Journey validate 均通过。
- Journey Schema 新增可选 `segmentation` 事实块；fresh 产物记录 requested/max/actual/strategy/assumptions，且同一说明进入每个子 Trip assumptions。validator 会以 `J_SEGMENT_LENGTHS` 拒绝篡改的实际段长，旧 0.4.0 demo 未被重写且仍兼容。
- 反向红态：临时令期望参数生成两个 8 天逻辑段，精准测试 exit 1；原始错误为 `ValueError: request must cover between one and seven inclusive days`（`planning.py:370`），`Ran 1 test in 0.013s`、`FAILED (errors=1)`。
- 还原绿态：撤销临时 8 天注入后 `/usr/bin/python3 -m unittest tests.test_journey -v` → `Ran 32 tests in 2.556s`、`OK`、skipped 0。当前轮次 3/12。

## 书 13 最终验收与提交

- 最终合并态 `/usr/bin/python3 -m unittest discover -s tests`（exit 0）原始摘要：`Ran 402 tests in 28.230s`、`OK`、skipped 0；满足本书要求的 ≥397。
- 最终 `/usr/bin/python3 scripts/scan_secrets.py`（exit 0）：`secret scan: 0 finding(s) across 372 file(s)`。
- 改后同夹具 CLI 原始核心输出：`JOURNEY_PLAN_COMPLETE ... trips=3 days=16 max_trip_days=6 ... journey_sha256=14827632538f31bed68939dd0a8da703d980f0a51ff239aa57a185f3540a2438 errors=0`；紧接 `JOURNEY VALID ... trips=3`；结构核验为 `actual_segment_days=[5,6,5]`、`all_trip_days_at_most_seven=true`、`selected_night_count=15`。
- 期望值 5 的独立原始摘要：`trips=4`、`actual_segment_days=[4,4,5,3]`、`max_trip_days=5`、`night_city_matches=15/15`、`journey_valid=true`，assumptions 写明 requested/actual 与住宿变化/7 天上限原因。
- 书 13 代码提交 `279bed2` 只含 Journey Schema、`journey.py`、`tests/test_journey.py`；记录提交 `b28d9c6` 只含 `PROGRESS.md`/`BLOCKED.md`。并行书 14 提交 `3d1980a` 独立夹在两者之间，未混入书 13 提交。
- 两个书 13 提交对 Trip/candidates Schema、`planning.py`、`candidates.py`、CLI、providers、render、demo、mobility、scheduler、Trip validator、manifest/docs 的路径审计均为空；版本保持 0.4.0，未安装 Codex。`BLOCKED.md` 本轮为“无”。当前轮次 5/12。

## Provider 运行时 unknown 原因覆盖：开工理解（2026-09-05，8 行）
1. 目标：provider 真正执行后，用可操作的运行时事实覆盖同 provider 候选 unknown 的陈旧 reason；未执行时逐字保留。
2. 通用覆盖范围是 AMap、12306、FlyAI、VariFlight，不改 unknown 结构，也不做 AMap 特判补丁。
3. 顺序：任务 0 离线复现 → 通用映射/AMap → off 保护与反向红绿 → 其余三 provider → 全量门禁与提交。
4. AMap 优先使用带实体的 `identity_conflict:<ref_id>:<detail>` 等 warning；其余 provider 从实际调用的结果错误/警告生成同样可操作的实体原因。
5. provider off、缺凭据、没有业务调用或流程没走到时，绝不把 health 的具体降级描述冒充已运行结果。
6. 最大风险：候选 unknown 的 JSON Pointer、claim subject 与 provider 调用实体并非总是一一对应，错误广播会把真文案改成另一句假话。
7. 夹具全部合成，禁止实网、demo 重跑、版本变更与 Codex 安装；只写任务书白名单。
8. 开工 HEAD/origin=`dfe0d3e`、工作树 clean；当前验收轮次 1/12，尚未修改产品代码。

## Provider 运行时 unknown 原因覆盖：任务 0（完成）

- 基线 `/usr/bin/python3 -m unittest discover -s tests`（exit 0）：`Ran 403 tests in 27.977s`、`OK`、skipped 0。
- 基线 `/usr/bin/python3 scripts/scan_secrets.py`（exit 0）：`secret scan: 0 finding(s) across 372 file(s)`。
- 使用现有纯合成 `g3_identity_conflict.json`，内存加入陈旧 AMap unknown，注入合成 configured credential 与 replay transport，跑完整 `plan_trip`；没有实网调用。
- 改前原始核心输出：

```text
AMAP_CONFIGURED True
AMAP_CALLS 1 ['poi']
AMAP_WARNINGS ['identity_conflict', 'identity_conflict:poi-g3-corridor:ambiguous_name_margin']
AMAP_HEALTH {"capabilities": ["geocode", "poi", "route"], "checked_at": "2026-09-05T12:00:00+08:00", "mode": "static", "provider": "amap", "reason": "calls=1/80 qps<=2; live_cells=0; locations=0; errors=identity_conflict; warnings=identity_conflict", "status": "degraded", "version": "web-service-v5-v3-route"}
TRIP_UNKNOWN {"claim_id": "claim-9bcdb062394bae07", "field_path": "/pois/0/coordinates", "provider": "amap", "reason": "AMap is not configured; coordinates remain unverified"}
TRIP_VALID 873887719d7865973451ca4ffbb34dfb0c632c050bb4b0f875c18400326ab02f ('INTAKE', 'RESEARCHED', 'CANDIDATES_READY', 'MATRIX_DEGRADED', 'SCHEDULED', 'VALIDATED', 'RENDERED')
```

- 结论：运行时已有带实体的真实冲突原因，但 `_selected_candidate_unknowns` 仍原样携带候选 reason，缺陷被完整离线复现。当前验收轮次 2/12。

## Provider 运行时 unknown 原因覆盖：任务 1（完成）

- `planning.py` 新增唯一中心规则 `_apply_runtime_unknown_reasons`：由 final unknown JSON Pointer、claim subject 与 lodging `candidate_ref` 解析实体；只接受 `cause:scope:detail` 三段式运行时证据，精确实体优先、能力范围次之，裸 health/warning 不足以覆盖。
- AMap 接入既有 `MobilityResult.warnings`；同一合成完整 plan 改后 reason 精确为 `identity_conflict:poi-g3-corridor:ambiguous_name_margin`，transport calls=1。
- 永久 off 回归用同一候选原文和完整 plan，断言 transport calls=0 且 reason 逐字等于 `AMap is not configured; coordinates remain unverified`。
- 两条精准门恢复后原始摘要：

```text
test_full_plan_replaces_stale_amap_unknown_with_entity_conflict ... ok
test_full_plan_mobility_off_preserves_candidate_reason_byte_for_byte ... ok
Ran 2 tests in 0.024s
OK
```

- 反向验证临时在零 warning 时注入 `provider_not_run:poi:synthetic_reverse_check`，off 保护断言按预期变红（exit 1）：

```text
AssertionError: 'AMap is not configured; coordinates remain unverified' != 'provider_not_run:poi-g3-corridor:synthetic_reverse_check'
Ran 1 test in 0.013s
FAILED (failures=1)
```

- 立即还原临时注入并确认源码无 `synthetic_reverse_check|provider_not_run`；规定门 `/usr/bin/python3 -m unittest tests.test_keyless_e2e tests.test_amap_live -v`（exit 0）→ `Ran 45 tests in 4.384s`、`OK`、skipped 0。当前验收轮次 4/12。

## Provider 运行时 unknown 原因覆盖：任务 2（完成）

- 12306 规划层现在保留每次实际 adapter 结果的原因并绑定最终 leg；`outside_presale_window` 优先于泛化 `no_results`，已选车次无库存也会绑定 service/date。rail=off 的 `result is None` 分支不生成 runtime warning。
- `FlyAIInventoryResult` 与 `VariFlightEnrichmentResult` 新增内部 `warnings`（默认空，非 Trip Schema 字段）；只有实际 lodging/flight/search/comfort adapter query 返回错误时才写 `cause:scope:detail`。VariFlight 无 Key 仅 probe、unsupported city 未调用时均保持空。
- Mobility 同步为无结果、限流、契约漂移等实际 POI/geocode 失败补充精确 ref_id warning；既有两段式/汇总 warning 保留供 health 使用，中心规则只消费三段式项。
- 三条新增精准门首次运行（exit 0）：

```text
test_rail_runtime_presale_reason_replaces_each_fallback_unknown ... ok
test_variflight_contract_drift_reason_targets_the_queried_flight ... ok
test_rate_limited_live_run_replaces_stale_lodging_unknown_reason ... ok
Ran 3 tests in 0.105s
OK
```

- 铁路完整 plan 的 4 条 fallback unknown 均精确为 `outside_presale_window:<leg_id>:route=<from_ref>-><to_ref>;date=<date>`；实际 fixture business calls=2、health=degraded。
- FlyAI 完整 plan 实际合成 429 调用 3 次；被选住宿 reason 精确为 `rate_limited:lodging-bjs-central:city=上海;check_in=2026-10-16;check_out=2026-10-18`，health=degraded。
- VariFlight 使用本地 MCP stdio `wrong-tools`（8/9 tool）真实执行一次 search；health=contract_mismatch，reason 精确绑定 `leg-flight-runtime-target` 与 route/date/action。
- 规定门 `/usr/bin/python3 -m unittest tests.test_flyai_live tests.test_keyless_e2e -v`（exit 0）→ `Ran 56 tests in 6.195s`、`OK`、skipped 0。当前验收轮次 6/12。

## Provider 运行时 unknown 原因覆盖：改后完整 plan 原始输出

- 与任务 0 完全相同的合成输入，使用记录单次 `resolve` 结果的内存 backend 重跑，命令 exit 0；configured 与 off 两支原始输出：

```text
AMAP_CONFIGURED True
AMAP_CALLS 1 ['poi']
AMAP_WARNINGS ['identity_conflict', 'identity_conflict:poi-g3-corridor:ambiguous_name_margin']
AMAP_HEALTH {"capabilities": ["geocode", "poi", "route"], "checked_at": "2026-09-05T12:00:00+08:00", "mode": "static", "provider": "amap", "reason": "calls=1/80 qps<=2; live_cells=0; locations=0; errors=identity_conflict; warnings=identity_conflict", "status": "degraded", "version": "web-service-v5-v3-route"}
TRIP_UNKNOWN {"claim_id": "claim-9bcdb062394bae07", "field_path": "/pois/0/coordinates", "provider": "amap", "reason": "identity_conflict:poi-g3-corridor:ambiguous_name_margin"}
TRIP_VALID 04b0b98ac78b852dca5e4a6790c7d197a5519b9201a1b780d11eefb858dea5a2 ('INTAKE', 'RESEARCHED', 'CANDIDATES_READY', 'MATRIX_DEGRADED', 'SCHEDULED', 'VALIDATED', 'RENDERED')
OFF_CALLS 0
OFF_WARNINGS []
OFF_UNKNOWN_REASON 'AMap is not configured; coordinates remain unverified'
```

- 对照任务 0 的改前 `TRIP_UNKNOWN.reason`，唯一语义变化是陈旧“未配置”被真实 `identity_conflict:<entity>:<detail>` 替代；unknown 结构未变。当前验收轮次 7/12。

## Provider 运行时 unknown 原因覆盖：首轮全量与真值收紧

- 首轮全量 `/usr/bin/python3 -m unittest discover -s tests`（exit 0）：`Ran 408 tests in 27.848s`、`OK`、skipped 0，满足 ≥407。
- 同轮 `/usr/bin/python3 scripts/scan_secrets.py`（exit 0）：`secret scan: 0 finding(s) across 372 file(s)`。
- 代码审查后主动去掉 VariFlight provider-wide warning 广播，并把能力 scope 收紧为 `lodging@城市`、`flight@from->to`；这防止已查询 A 城住宿或一条航线时误改 B 城/另一航线的 unknown，落实“没到那一步不覆盖”。
- 收紧后五条核心回归 `/usr/bin/python3 -m unittest ... -v`（exit 0）→ `Ran 5 tests in 0.132s`、`OK`、skipped 0；所有原精确 reason 断言保持不变。
- `BLOCKED.md` 已追加本轮“新增阻塞：无”；当前验收轮次 8/12。

## Provider 运行时 unknown 原因覆盖：最终提交前验收

- 暂存态规定门 `/usr/bin/python3 -m unittest tests.test_keyless_e2e tests.test_amap_live -v`（exit 0）→ `Ran 47 tests in 4.570s`、`OK`、skipped 0。
- 暂存态规定门 `/usr/bin/python3 -m unittest tests.test_flyai_live tests.test_keyless_e2e -v`（exit 0）→ `Ran 56 tests in 6.202s`、`OK`、skipped 0。
- 暂存态全量 `/usr/bin/python3 -m unittest discover -s tests`（exit 0）原始摘要：

```text
........................................................................................................................................................................................................................................................................................................................................................................................................................
----------------------------------------------------------------------
Ran 408 tests in 27.633s

OK
```

- 同轮 `/usr/bin/python3 scripts/scan_secrets.py`（exit 0）：`secret scan: 0 finding(s) across 372 file(s)`。
- 白名单审计原始输出为 `ALLOWLIST_OK files=9`；仅 `BLOCKED.md`、`PROGRESS.md`、4 个允许源文件与 3 个允许测试。schema/、demo/、render/、cli.py、Journey、station_distance、candidates、scheduler、Trip validator、禁碰 AMap/MCP providers、docs 与所有版本承载文件的 diff 均为空；`git diff --check` exit 0。
- 没有改 `demo/candidates.json`、没有重跑 demo、没有改 0.4.0、没有安装 Codex、没有新增依赖或流程。当前验收轮次 9/12，代码与文档已可提交。

## Provider 运行时 unknown 原因覆盖：提交后核验（完成）

- 实现提交 `fff7fbc6851840e9750929f5dde600ad0a1b97bc`（`Report runtime provider reasons for unknowns`）：9 个白名单文件，554 insertions/4 deletions；包含 `BLOCKED.md` 的“无”记录。
- 提交后全量 `/usr/bin/python3 -m unittest discover -s tests`（exit 0）→ `Ran 408 tests in 27.374s`、`OK`、skipped 0。
- 提交后 `/usr/bin/python3 scripts/scan_secrets.py`（exit 0）→ `secret scan: 0 finding(s) across 372 file(s)`。
- `HEAD^..HEAD` 复核输出：`POST_COMMIT_FORBIDDEN_DIFF_OK paths=14`、`POST_COMMIT_VERSION_DIFF_OK files=8 value=0.4.0`、`POST_COMMIT_WORKTREE_CLEAN`。
- `demo/candidates.json` 与实现提交父树逐字节相同，SHA-256=`2668b3ed8c0862eef9036ef7d62c882b5cedadb37496932f540970dae9ff3f99`；未 push、未发布、未安装 Codex。当前验收轮次 10/12，任务完成。

## 书 16 Journey AMap 预算与运行内去重：开工理解（2026-09-05，8 行）
1. 目标：每个 Journey 逻辑段各有独立的最多 80 次 AMap 额度，同时以 CLI 可配的 Journey 总上限约束用户配额消耗。
2. 同一次 Journey 内，同一实体的坐标解析结果只在内存中解析一次并跨段复用；不落盘、不跨运行。
3. 顺序：任务 0 基线/离线复现/health 溯源 → 任务 1 分段预算与 CLI 总上限 → 任务 2 实体去重 → 全量门禁与提交。
4. 先保证算得准，再减少重复调用，最后才考虑运行时间；不得降低 POI 身份、行政区或坐标语义校验强度。
5. 任一分段或总额度耗尽都必须继续映射为 `rate_limited`，保留静态估算降级，不得隐式扩容。
6. 只改任务书白名单；版本保持 0.4.0，不跑实网/demo、不安装 Codex、不改 provider 响应缓存条款。
7. 最大风险：当前一个逻辑段可含多个 atomic Trip，预算必须按最终逻辑段隔离，而去重生命周期必须覆盖整次 Journey。
8. 次大风险：AMap mobility 与 lodging fallback 可持有不同 transport；总上限和 health 数字不能漏算或误报。

## 书 16 任务 0：基线、预算耗尽复现与 health 溯源（完成）

- 仓库根为 `china-trip-weaver/`，开工 `HEAD` 与 `origin/main` 均为 `03fced1ba39514cb1e9f05b13b10811db712e4ee`，工作树 clean；全程未发实网请求。
- 基线 `/usr/bin/python3 -m unittest discover -s tests`（exit 0）原始摘要：`Ran 409 tests in 27.385s`、`OK`；无 skipped 汇总，即 skipped 0。
- 基线 `/usr/bin/python3 scripts/scan_secrets.py`（exit 0）：`secret scan: 0 finding(s) across 372 file(s)`。
- 用现有全合成 `journey_sixteen_day_case()`、`ScriptedAmapTransport` 与真实 `AMapCallBudget(max_calls=4,qps=1000000)` 包装器跑完整 `plan_journey`；包装器在 delegate 前 acquire，故走正式 adapter 的 `ProviderRateLimited → rate_limited`，`NETWORK_CALLS 0`。

```text
JOURNEY_TRIPS 3
SHARED_BUDGET_CALLS 4 MAX 4
TRIP 1 DATES 2026-10-01 2026-10-05 AMAP_STATUS rate_limited MODE live
TRIP 1 AMAP_REASON calls=4/80 qps<=2; live_cells=1; locations=2; errors=rate_limited; warnings=none
TRIP 2 DATES 2026-10-06 2026-10-10 AMAP_STATUS rate_limited MODE static
TRIP 2 AMAP_REASON calls=4/80 qps<=2; live_cells=0; locations=0; errors=rate_limited; warnings=rate_limited
TRIP 3 DATES 2026-10-11 2026-10-16 AMAP_STATUS rate_limited MODE static
TRIP 3 AMAP_REASON calls=4/80 qps<=2; live_cells=0; locations=0; errors=rate_limited; warnings=rate_limited
BUSINESS_CALL_ATTEMPTS ["amap.geocode:lodging-j16-shanghai-central", "amap.poi:poi-j16-shanghai", "amap.geocode:poi-j16-shanghai", "amap.route:transit:lodging-j16-shanghai-central:poi-j16-shanghai", "amap.route:transit:poi-j16-shanghai:lodging-j16-shanghai-central", "amap.geocode:lodging-j16-hangzhou-central", "amap.geocode:lodging-j16-suzhou-central"]
```

- 复现结论：同一 mobility transport 的计数停在 4；第一段耗尽额度后，第二、三段首次 geocode 即得到 `rate_limited`，继续生成有效 Journey 但以 static matrix 降级，准确复现“后段拿不到额度”。当前 reason 的 `/80` 是硬编码显示，和注入的 4 不一致，也纳入任务 1 修复。
- 两组统计来源已独立用全合成六城 Journey 证实：最终三个逻辑段分别由 3/2/3 个住宿对齐 atomic Trip 构成；`_merge_provider_health` 对同 provider 的 reason 做分号去重合并，所以 `CALL_STAT_GROUPS` 分别为 3/2/3，第二段原始 reason 为 `calls=30/80 ...; calls=40/80 ...`。这不是 `_combined_amap_health` 的 lodging+mobility 拼接；本次 fixture 的 lodging fallback 为 off。
- 决定：任务 1 会让同一逻辑段内的 atomic Trip 共用该段额度，并让 health 展示段内真实计数/上限；不会删除多来源 health 事实来掩盖问题。当前验收轮次 1/12。

## 书 16 任务 1：按段预算与 CLI 总上限（完成）

- `AMapCallBudget.fork()` 现在创建独立空计数器但共享同一个 start-rate limiter；所以 Journey 各逻辑段单独计数、同段的 mobility 与 AMap lodging 共用额度，同时整次运行仍守全局 `qps<=2`。零额度会在首次 acquire 原样抛 `ProviderRateLimited`，不会扩容。
- `plan_journey(..., amap_total_max_calls=None)` 缺省按 `80×逻辑段数`；显式非负总量先封顶于该默认值，再尽可能平均分配，余数从前段依次加一。每段上限永不超过 80，总量 3/三段得到 `[1,1,1]`。
- `ctw journey plan --amap-total-max-calls N` 已暴露并传入 planner。正向 CLI 用 checked-in 合成 16 天输入、rail/lodging/aviation off、mobility live 与总量 0；预算在 HTTP opener 前拒绝，物理网络调用为 0。原始输出为 `JOURNEY_PLAN_COMPLETE ... trips=3 days=16 max_trip_days=6 calls= ... errors=0`，三段 health 均为 `status=rate_limited mode=static`、`calls=0/0 ... errors=rate_limited`。负数 subprocess 另以 `JOURNEY_PLAN_FAILED Journey AMap total max calls must be a non-negative integer`（exit 1）证明参数确实到达 planner。
- mobility health 的分母改为 transport 的真实段上限；总量 12 的三段离线原始输出均为 `calls=4/4`、`status=rate_limited`，delegate 实际总调用 12。总量 3 的永久回归逐段为 `calls=1/1`、`errors=rate_limited`，三段 Journey validator 仍通过。
- 规定组合门首轮 `/usr/bin/python3 -m unittest tests.test_journey tests.test_amap_live -v`（exit 0）：`Ran 54 tests in 4.704s`、`OK`、skipped 0。
- 反向红态：临时改回一个 `shared_amap_budget(max_calls=80)` 后，精准测试 exit 1；原始差异为 `['calls=5/80 ...', 'calls=10/80 ...', 'calls=15/80 ...']` 不满足每段都以 `calls=5/80` 开始，`Ran 1 test in 0.135s`、`FAILED (failures=1)`。
- 还原绿态：恢复每段 `fork(amap_segment_limits[index])` 后，两条预算精准门 `Ran 2 tests in 0.320s`、`OK`、skipped 0；临时共享计数器已完整撤销。当前验收轮次 2/12。

## 书 16 任务 2：单次 Journey 内实体去重（完成）

- `AMapRequestMemo` 只由每次 `plan_journey` 在栈内新建，键只含非敏感的 provider/request id/capability/parameters/as-of；只深拷贝内存中的 `ProviderEnvelope`，不写文件、不复用异常、不跨 Journey 调用。
- 每个段 transport 在预算 acquire 前查询同一 Journey memo；所以命中不会消耗段额度或 2 QPS 起始槽，未命中才走正式 transport、身份校验、行政区校验、语义异常校验并保存响应。没有降低任何坐标验证强度。
- 四段六城合成场景（`expected_segment_days=4`）改前 transport 实际调用 65；改后为 57，恰好省掉 8 次跨段重复实体调用。同一实体的永久计数从两轮降为一轮：两个重复 POI 各 `poi=1, geocode=1`，四个重复住宿各 `geocode=1`；route 为保证时效性仍逐段查询。
- 两个跨段 POI 均在恰好两个最终 Trip 中出现；`poi-j16-six-city-synthetic-a` 两段 GCJ02 都是 `{lng:121.2,lat:31.2}`，`synthetic-e` 两段都是 `{lng:122.2,lat:32.2}`，完整 coordinates 对象逐字相等，Journey validator 通过。
- 跨运行保护：对同一个 backend/transport 连续调用两次 `plan_journey`，delegate 计数严格从 15 增至 30；第二次没有读取第一次 memo。
- 严格失败去重：某重复 POI 的第一次实际调用抛合成 timeout 后，后段复用同一失败事实，delegate 与公开 `business_calls` 均恰为 1；本地段预算在发网前拒绝的异常不保存，因此新段仍可用自己的独立额度尝试。
- 反向红态：临时把两个 memo 移入 segment 循环（等价于关闭跨段复用），精准测试 exit 1，原始错误 `AssertionError: 1 != 2` 位于重复 POI 调用计数，`Ran 1 test in 0.290s`、`FAILED (failures=1)`。
- 还原绿态：恢复每次 Journey 一份 memo 后 `/usr/bin/python3 -m unittest tests.test_journey -v`（exit 0）→ `Ran 38 tests in 4.150s`、`OK`、skipped 0；临时关闭去重已完整撤销。当前验收轮次 3/12。

## 书 16 最终提交前验收

- 最终代码态全量 `/usr/bin/python3 -m unittest discover -s tests`（exit 0）原始摘要：`Ran 422 tests in 29.354s`、`OK`、skipped 0；基线 409 + 13 个严格回归，满足 ≥414。
- 同轮 `/usr/bin/python3 scripts/scan_secrets.py`（exit 0）：`secret scan: 0 finding(s) across 372 file(s)`。
- 最终任务 2 精准门 `/usr/bin/python3 -m unittest tests.test_journey -v`（exit 0）→ `Ran 39 tests in 4.613s`、`OK`、skipped 0。
- 最终任务 1 规定门 `/usr/bin/python3 -m unittest tests.test_journey tests.test_amap_live -v`（exit 0）→ `Ran 59 tests in 5.190s`、`OK`、skipped 0。
- CLI 正向零网络原始 health：三个 Trip 逐个输出 `STATUS rate_limited MODE static` 与 `REASON calls=0/0 qps<=2; live_cells=0; locations=0; errors=rate_limited; warnings=rate_limited`；CLI 主输出 `JOURNEY_PLAN_COMPLETE ... trips=3 days=16 max_trip_days=6 calls= ... errors=0`。
- 机器白名单审计原始输出 `ALLOWLIST_OK files=9`；仅 `BLOCKED.md`、`PROGRESS.md`、5 个允许源文件与 2 个允许测试。`git diff --check` exit 0。
- schema/、demo/、render/、station_distance、candidates、FlyAI、VariFlight、scheduler、Trip validator、plugin manifest、docs 与 secret scanner 的组合 `git diff --exit-code` exit 0、无输出；README/manifest/`__init__.py` 等版本承载文件 diff 亦为空，版本保持 0.4.0。
- `BLOCKED.md` 已随交付记录“无新增阻塞”；未跑实网/demo、未安装 Codex、未发布、未写 provider 响应到磁盘。当前验收轮次 4/12，下一步仅最终文档态门禁、暂存复核与提交。

## 书 16 提交后核验（完成）

- 实现与验收提交 `38ef00472954be9633afc6affc72b7fbcc5a404e`（`Scope AMap calls per Journey segment`）包含恰好上述 9 个白名单文件，`867 insertions/27 deletions`；`BLOCKED.md` 已在同一提交中。
- 提交后首次并发全量只因工具 30 秒 yield 边界返回进度点、没有退出码，未冒充成功或失败；单独重跑同一命令（exit 0）完整输出 `Ran 422 tests in 29.532s`、`OK`、skipped 0。
- 提交后 secret scan（exit 0）仍为 `0 finding(s) across 372 file(s)`；禁碰路径的 `HEAD^..HEAD` diff exit 0、无输出。
- 实现提交后 `git status --short --branch` 为 `main...origin/main [ahead 1]` 且无文件项；本地 HEAD 为 `38ef004...`，`origin/main` 仍为开工的 `03fced1...`，确认未 push/未发布。
- 本段记录随后作为仅 `PROGRESS.md` 的收尾提交交付；当前验收轮次 5/12，书 16 完成。
