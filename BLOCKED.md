## 书 AD3「Journey 页位置示意」（2026-09-11，worktree `.tmp/wt-ad3` 分支 `journey-location-svg`，第十四波三份并行书之一）：两处判断，非阻塞

1. 「界限」写 `tests/test_journey.py（只许新增 def test_）`，但加了必需分区后
   `demo/journey-16d/journey.html` 的 `[data-section]` 数量从 15 变成 16 是
   任务本身唯一可能的结果（`JOURNEY_SECTIONS` 加一项、`_render_journey`
   无条件渲染每个配置的分区，没有条件跳过的余地）；既有测试
   `test_checked_in_sixteen_day_demo_passes_offline_browser_qa`
   硬编码 `"--sections", "15"` 传给 `qa_renderer_browser.py`，任务书自己在
   任务 2 验收命令里又写 `--sections 16`——书内自相矛盾，与「验收教训」记录
   的 Z2 书 pathspec/白名单互斥是同一种情况。实测确认：不改这一行，重生成
   demo 后该测试必红（`sectionCount=16` 与硬编码 `15` 不符，
   `qa-report.json` 报 `"375x812 15 sections"`/`"1440x900 15 sections"`
   两条失败），直接违反硬指标二「全量 OK 0 skipped」；改了这一行不会让
   `git diff fd2e618 -- tests | grep -E '^-\s*def test_'` 出现任何一行（规矩
   给出的字面判据只禁止删除/重写 `def test_` 签名行，没有禁止行内数字）。
   处理：把这一行的 `"15"` 改成 `"16"`，不碰这条测试的其余内容、不加不删
   断言。`scripts/qa_renderer_browser.py:305` 的 `--help` 文案里也留了一句
   过时的 "Journey: 15"，该脚本不在「界限」允许列表内，保持只读，未改。
2. 任务 2 写「跑 ... 与 README demo、build_plan_fixtures、
   build_provider_fixtures」；`build_plan_fixtures.py`/`build_provider_fixtures.py`
   已跑（`git status` 确认零新增差异）。但 README 文档的其余四份 demo
   （`demo/trip.html`/`guangzhou-shenzhen`/`grouped-departures`/
   `multicity-5d`）由 `ctw plan` 走 Trip 页 renderer 生成，「界限」明确写
   `render/html.py、schema、其余 demo 只读`；实测
   `git grep -n journey_html -- render/html.py cli.py` 只在 `cli.py` 的
   `journey validate-html`/`journey render` 两个子命令命中，`render/html.py`
   零命中——两条渲染路径在 import 图上互不相交，本轮只改了
   `render/journey_html.py`，逻辑上不可能影响那四份 demo。为了不对「只读」
   文件做写入（哪怕预期字节不变），选择用这条静态证据代替实际重跑那四条
   `ctw plan` 命令，未触碰 `demo/trip.html` 等四个文件。



任务 0/1/2 全部按任务书字面执行，全程无需停工的冲突，也未发现任何 bug 或想
改动的逻辑——纯逐字节拆分。任务书「现状与任务 0」列出的每一项数字（HEAD、
630 测试、secrets 0、pyflakes 0、625 行、`schedule_day`/`_evaluate`/
`_order_key`/`schedule_plan` 的行号与调用点、`_no_solution(`/`ValueError`
计数、golden 20/no_solution 8 夹具、`def test_` 21 个、`schedule_day(`
调用 6 处）逐条核对全部吻合，零出入，无需记录任何一条差异。

唯一需要自行判断（非裁决分叉，供核对）的一点：新私有类型命名为
`_DayScheduleParams`（frozen dataclass，任务书只给了「NamedTuple 或 frozen
dataclass」两个选项，未点名具体类名），选择理由是与文件里已有的
`PaceProfile`/`Candidate`/`EvaluatedSchedule`/`ScheduleResult` 四个
`@dataclass(frozen=True)` 风格一致；字段除 `_evaluate`/`_order_key` 实际
读取的 11 个外，另加 `profile`/`pace` 两个供 `schedule_day` 终评阶段使用，
均为只读透传、不影响两个方法的内部逻辑。`_evaluate` 签名从 14 参数收窄到
4 个（省 10 行）后，若像 `_order_key` 一样完全不加解包前言，函数会变成
101 行；但若像最初尝试那样每个字段各占一行解包（11 行前言），会变成 112
行、超出「≤111」硬指标 1 行——已改为两两一行的解包写法（6 行前言，107
行），内部计算部分保持逐字节不变，供核对为什么解包不是「一个字段一行」的
最直观写法。完整实测过程（含把 112 行发现并修正为 107 行的记录）见
PROGRESS.md 本书任务 2 小节。

## 书 AB2「拆 providers/base.query」（2026-09-11，worktree `.tmp/wt-ab2` 分支 `split-provider-query`，第十二波两份并行书之一）：无待裁决项

任务 0/1/2 全部按任务书字面执行，全程无需领导裁决的冲突，也未发现任何
bug 或想改动的逻辑——纯逐字节剪切，四个新方法与原 `query` 方法体内部
完全一致，只是把控制流的 `continue`/`break`/落空补齐成方法边界处的
显式 `return` + 调用方 `isinstance` 分流。任务书数字逐条核对全部吻合，
无出入需要记录。

两点自行判断（非裁决分叉，供核对）：

1. 任务书「建议」四个方法名——`_preflight_failure`/
`_execute_with_retries`/`_normalize_envelope`/`_build_result`——全部
照抄采用，但额外多抽了一个任务书未提及的 `_handle_rate_limited`
（rate-limited 分支的重试/失败判定，原 36 行）。原因：`_execute_with_
retries` 若把这 36 行内联在自己体内，连同 setup、其余异常分支、loop
后两次状态检查，会到约 100 行，超过「全文件无函数 >80 行」的硬指标；
拆出这个额外助手后 `_execute_with_retries` 74 行、`_handle_rate_limited`
44 行，均达标。这是「建议有更好的路可以走」条款覆盖的偏离，不是违反
「只允许/不许」的失败项。

2. 反向验证按先例（书 Y1「拆 journey._merge_segment_trips」、书「拆
journey._validate_connection」发现的同款测试缺口）在
`tests/test_providers.py` 新增一个精确断言测试
`test_timeout_exhaustion_pins_the_exact_retry_reason_text`——全仓库
此前对 timeout 耗尽重试后的 `health["reason"]` 文案零精确断言（`grep
-rn "provider deadline exceeded" tests/` 零命中），若不补测试，反向
验证要求的「至少一项测试红」无法满足；不是任务书要求之外的画蛇添足，
而是任务书「反向验证」条款本身能兑现的必要前提，且「界限」明确允许
`tests/test_providers.py` 新增 `def test_`。完整实测过程（含反向验证
的红→绿记录）见 PROGRESS.md 本书任务 2 小节。

另有一处主动放弃的覆盖（同样非待裁决项，已在 PROGRESS.md「覆盖判断」
段落说明理由）：快照脚本未构造 `Rail12306Adapter.query` 的 `ambiguous`
包装分支场景，因为真实触发路径依赖 `tests/test_rail_station_fallback.py`
专用的 subprocess 假 MCP 服务器基础设施，复刻代价远超收益，而该分支
唯一依赖的一行代码是逐字节剪切未改动的一行，且有现成的精确断言测试
作为全量回归的防线。

## 书「拆 journey._validate_connection」（2026-09-11，worktree `.tmp/wt-aa2` 分支 `split-journey-connection`，第十一波三份并行书之一）：无待裁决项

任务 0/1/2 全部按任务书字面执行，全程无需停工的冲突，也未发现任何 bug 或
想改动的逻辑——纯逐字节剪切，三个新函数与原函数内部完全一致。任务书数字
逐条核对全部吻合，无出入需要记录。

唯一需要自行判断（非裁决分叉，供核对）的一点：任务书「建议名」给了
`_check_connection_refs`/`_check_connection_lodging`/
`_check_connection_transport` 三个名字，均照抄采用；参数列表任务书未
指定，按各函数实际读取的字段最小化传参——`_check_connection_transport`
不接收 `left`（函数体从未读取它），其余两个接收
`connection`/`left`/`right`/`path`/`issues`，与「拆
validate_trip.semantic_issues」先例（`_check_*` 函数只接收各自需要的
上下文、`issues` 放最后一位）同构。

反向验证按先例（「拆 validate_trip.semantic_issues」发现同款测试缺口）
在 `tests/test_journey.py` 新增一个精确断言 `(code, path, message)` 的
测试——全仓库此前对 `_validate_connection` 内 10 个 J_ 码零精确断言，
若不补测试，反向验证要求的「至少一项测试红」无法满足；不是任务书要求
之外的画蛇添足，而是任务书「反向验证」条款本身能兑现的必要前提，且
「界限」明确允许 `tests/test_journey.py` 新增 `def test_`。完整实测过程
（含反向验证的红→绿记录）见 PROGRESS.md 本书任务 2 小节。

## 书「拆 validate_trip.semantic_issues」（2026-09-11，main 直改）：无待裁决项

任务 0 核对发现任务书「demo 下 5 个 trip.json」与实际不符：`find demo -name
"trip.json"` 只有 4 份（`demo/trip.json`+`multicity-5d`+`grouped-departures`+
`guangzhou-shenzhen`），第五个 demo 例子 `journey-16d` 用的是 `journey.json`
（README 第 134 行称其为「the fifth example」，产物是 journey 不是 trip），
任务书紧接着单独列出的「demo/journey-16d/journey.json 的三条 trip」已经把
这一份算在别处——「5」应是把「5 个 demo 例子」误记成「5 个 trip.json」。
与先例书「书 W3」（`4 份 demo trip`）、「书『拆 validate_journey_html』」的
现状描述完全一致，判断为任务书笔误、不阻塞，快照语料按实际的 4 份 demo
trip.json + 3 条 journey-16d 内嵌 trip 取，记录见 PROGRESS.md 任务 0 小节。

## 书 Y1「拆 journey._merge_segment_trips」（2026-09-11，main 直改，已按先例处理，非空白裁决）

任务 0 的 1 行行数出入（2574→2573）已单独记在本文件靠后位置，不再重复。
本条记录任务 2 反向验证环节的判断：任务书要求「取反某个新抽出函数里的
一条去重条件 → 快照 diff 非空且 test_journey 至少一项红」；实测对
`_merge_segment_entity_groups`/`_merge_segment_unknowns`/
`_merge_segment_claims` 三处去重条件逐一取反，均能让 six-city 快照哈希
改变（证明三处去重逻辑均真实生效），但 `test_journey`（75 项）三次都
保持全绿——现有测试套件对这类内部合并去重的具体效果本来就缺乏精确断言。
按「验收明确要求的硬指标优先」的既有先例（「书 docs-drift 任务 2」「书
『ctw replan --rail-result』任务 2」），新增 1 个断言性质的测试
`test_six_city_merge_dedupes_a_poi_and_claim_revisited_within_one_
segment`（`tests/test_journey.py`，任务书「界限」明确允许新增
`def test_`）来让反向验证的「红→绿」有真实证据，而非放弃这条验收或
用测试之外的方式蒙混过关。完整的实测过程（含发现三处去重条件均无法
触发红的探索、诊断脚本定位真实合并点、以及一次「探索时机不对导致数错
基线（20 vs 正确的 19）、随后自我纠正」的记录）见 PROGRESS.md 本书任务 2
小节，不构成需要领导裁决的阻塞项。

## 书 Y2「站点 POI 查询加 types=150200、page_size 5→25」（2026-09-11，worktree `.tmp/wt-y2` 分支 `station-poi-types`）：无待裁决项

本书全程未遇到需要领导裁决、又拿不准该怎么办的分叉；任务书「我替领导拍的
板」两条（`types` 可选参数语义、`:355` 断言改法）与任务 0 现状描述逐条核
对全部吻合，字面执行即可。写新夹具时发现 `find_nearby_stations` 发出的
`poi_around` 请求本身没有 `page_num` 键（合同层默认成 1），属实现细节、
不构成裁决分叉，就地改用 `.get("page_num", 1)` 后照常验收，记录在
PROGRESS.md 本书小节。

## 书 X2「12306 站点最近火车站回查」（2026-09-11，worktree `.tmp/wt-x2` 分支 `station-nearby`）：无待裁决项

本书全程未遇到需要领导裁决、又拿不准该怎么办的分叉。任务 0 核对到的一处
文字表述疑问（`test_amap_live.py`/`test_rail_station_fallback.py` 任务书
括注写「新增」但两份文件早已存在）与实现中发现的两处隐藏 bug（第四层会
在没注入 enricher 的既有测试里打真实 AMap 网络请求；`find_nearby_stations`
复用 `_city_centre` 对非行政区地名如「鼓浪屿」会走 AMap geocode 的全国
模糊匹配、永远拿不到中心点）均已就地判断、修复并验证，记录在 PROGRESS.md
本书小节，不构成待裁决项。

## 书 X3「租车与轮渡合成 Trip 夹具」（2026-09-11，无待裁决项）

任务 0/1/2 全部按任务书字面执行，全程无需停工的冲突；硬指标一（夹具三关
全过、页面含「轮渡」「驾车」、反向验证红→绿）与硬指标二（全量 614 测试 OK
0 skipped、secrets 0、pyflakes 0、`plugins`/`demo` 零改动、分支已推送）均
一轮验收即通过，未触发止损。两处需要自行判断的细节记在这里供核对：

① `from_ref`/`to_ref` 端点选型——任务书未指定用 POI 还是城市 ref，照抄
`multicity-static.json` 的火车腿先例（`leg-beijing-nanjing` 的 `from_ref`/
`to_ref` 直接用 `city-beijing`/`city-nanjing`），两条新腿的 `from_ref` 都用
`request.destinations` 里已有的 `city-xiamen`，`to_ref` 各用新建的
`poi-gulangyu`/`poi-nanjing-tulou`；`day-2.city` 沿用 `day-1` 的「厦门」而
非改成「南靖」——任务书没有要求两天必须落在不同 `request.destinations`
城市，用单一目的地可以避免触发 `V_ORIGIN_REQUIRED`（其条件是「目的地>1 或
含 rail/flight 腿」之一为真且无 origin），少一个不必要的 `request.origin`
字段，判断更贴近「合成数据 > 三关全过」的让步顺序。

② `docs/design/adr/0016-rental-car-and-ferry.md`——任务书原文「命令 2、3
后各加一行 done 说明」，已照做；但该文件「Consequences」段落末尾还有一句
2026-09-10 写的「commands 2–3 ... remain open for a future book」，与刚加
的两行 Done 字面矛盾。任务书界限允许编辑整份 ADR 文件，未特别禁止改这一句；
判断保留这句不改会让同一份文档自相矛盾，不符合「覆盖 ADR 四件事」这一让步
优先级，已顺手把这半句改成「shipped in worktree branch rental-ferry-fixture
...」，只改了事实性陈述，未改动任何验收命令本身的文字。

## 书 W2 遗留：`user_delete` 删时段后 `/days/d/slots/s` 路径的同款缺口（2026-09-11，任务书明确排除在外，只记录不处理）

任务书「我替领导拍的板」第三条明确裁定这不在本书范围：`user_delete` 事件
（`replan.py:73-76`）删时段时只 `pop` 该下标的 slot 并 `remove` 对应路径，
不重编号同一天内后续 slot 的下标——与本书修复的 `suspend` 腿重编号是同一类
缺口，但发生在 `/days/d/slots/s` 而非 `/transport_legs/N`。按任务书指示只记
录、不实现。

补充核实（任务书未要求但有助于评估实际影响）：全仓搜索
`field_path.*days|"/days/%d` 未在 `planning.py`/`journey.py` 找到任何会写入
`unknowns[].field_path` 的 `/days/%d/slots/%d/...` 生产者——当前代码里没有
unknown 条目会以这种位置型路径指向某个 slot，所以这条缺口目前是潜在的（结构
性地存在于 `user_delete` 的实现方式里），而非已有可复现的错指数据这一点上
与本书修复前的 `suspend` 不同（`suspend` 有 `planning.py:1397/1403` 两个
现役生产者）。若未来任何模块开始往 `unknowns`/其他结构里写入
`/days/d/slots/s` 形式的位置型引用，这条缺口才会变得可观测，届时需要一本
新任务书专门处理（做法可照抄本书 `_reindex_transport_leg_unknowns` 的模式：
删 slot 后，对同一天内 `field_path`/类似字段里下标大于被删位置的引用整体
减一）。

## 书 W2「suspend 删非末尾腿的 unknowns 重编号」（2026-09-11，已按先例处理，非空白裁决）

任务书「规矩」要求 `git diff main --stat -- plugins/china-trip-weaver/schema
'*/journey.py' '*/planning.py' '*/render/*' demo` 与 `git diff main -- tests
| grep -E '^-\s*def test_'` 均为空，但本书「全局」小节本身声明三本任务书
并行（W1 在 main 直改 journey.py/render/journey_html.py/
validate_journey_html.py，W3 在分支 split-validate-html 改
render/validate_html.py）。验收时 `git log d22e3e6..main --oneline` 显示
`main` 已被 W1 推进一个提交 `1e434bf`（"Add failing spec tests for
deadline-kind checklist wording (task 1)"，W1 任务 1 的先红阶段，
`tests/test_journey.py` 新增 5 个 `def test_`）。若此时直接对移动后的
`main` 跑上述两条命令，`git diff main --stat` 会把 W1 新增的
`test_journey.py` 当作本书"改动"列出（因为本分支缺少该提交），`git diff
main -- tests | grep '^-\s*def test_'` 也会把那 5 个新测试函数签名误判为
本书删除（同理，本分支没有它们，diff 方向上显示为"减号"）——但本书从未
打开过 `tests/test_journey.py`，也没有改动 `journey.py`/`render/`/`demo`
任何字节。

判断：与本文件既有先例「书 A2b 任务 2：`git diff main` 的"删测试"验收因
并行 A1b 书已合入 main 而失真」同款情形，按同一先例处理——改用
`git merge-base main HEAD` 核实的本分支真实分叉点 `d22e3e6`（而非已经
移动的 `main`）重新跑这两条命令，结果均为空/零行，证实本书确实零改动
`schema`/`journey.py`/`planning.py`/`render/`/`demo`，也零行删除测试函数；
`git diff d22e3e6 --stat` 只有 `PROGRESS.md`、
`plugins/china-trip-weaver/src/china_trip_weaver/replan.py`、新增的
`tests/fixtures/scheduler/replan/suspend-first-leg.json`、
`tests/test_replan.py` 四个文件，均在白名单内。不停工，供管理者合并时核对
——merge 时 W1 的新测试会随 main 最新提交自然出现在合并结果里，不需要本书
额外动作。

## 书 W3「拆 validate_html」任务 0：call-site 计数方法与 :156 标注核对（2026-09-11，判断，非阻塞）

任务书「现状与任务 0」写「test_renderer.py 11 处调用 `validate_html`（含
:156 `test_renderer_fixture_manifest`）、test_keyless_e2e.py 7 处、
test_replan.py 2 处」。裸 `grep -n "validate_html"` 三个文件分别命中
13/8/3 行，与任务书数字不吻合；改用 `grep -n "validate_html("`（只数带左括号
的出现，与「调用点」更贴切）分别命中 11/7/2 行，逐字吻合任务书三个数字——
判断任务书的计数方法就是后者，验证通过。唯一仍对不上的是括注
「含 :156 `test_renderer_fixture_manifest`」：`test_renderer.py:156` 确是
`def test_renderer_fixture_manifest(self):`，但该测试体本身只读
`manifest.json` 核对哈希，不调用 `validate_html`（`grep -n "validate_html("`
命中的 11 行里离 156 最近的是 145 行 `test_cli_render_and_validate_html`，
经子进程调 CLI 的 `validate-html` 子命令，而非直接函数调用，含连字符不含
下划线不在这个 grep 的匹配范围内）。判断：不停工。三个总数（11/7/2）已逐字
核对通过，是本任务书唯一会影响「不破坏任何既有调用方」这一验收面的数字；
`:156` 只是一处定位标注的笔误（大概率想指 145 行或单纯说「156 行之前」），
对拆分方案、白名单、验收命令均无影响，按以往「路径写得粗略」「用……标注不
完整」同款先例记录后继续。

## 书 F1「预订清单按开售日」（2026-09-10，无待裁决项）

任务 0/1/2 全部按任务书字面执行，全程无需停工的冲突。两处需要自行判断的
"猜的"细节记在这里供核对，均不影响任何验收命令的结果：①交通项的 `reason`
文案用英文而非任务书示例的中文——全仓库既有 `unknown["reason"]`/
`provider_health.reason` 等原始数据字段一律是英文（渲染时才按 `locale`
转换成中文 label），任务书里的中文示例是任务书本身用中文写的说明性文字，
不是要求往数据里塞中文，按现有数据约定选了英文；②"开售日早于
`generated_at` 时不挪，保持原值"按字面理解为"不写与 `generated_at` 比较/
钳制的代码，让 `depart_at - (PRESALE_DAYS-1)` 的裸算结果（哪怕落在
`generated_at` 之前）直接作为 deadline"，这样排序时自然垫底到列表最前；
demo 与新增测试的固定数据里没有一条腿的出发日期落在这个分支（最早的 rail
腿开售日 2026-09-17 晚于 `generated_at` 2026-09-05），未构造额外场景验证，
但实现本身没有分支判断会让这条路径出错。

## 书「拆 MobilityBackend.resolve」（2026-09-10，无待裁决项）

任务 0 核对全部与任务书吻合（HEAD `ec7c12d`：584 测试、secrets 0、pyflakes
0、长度命令、`resolve` 行号 L124-489、`AMapMobilityTests` 53 项、三处调用方
位置均一致），拆分过程中未发现 bug、未需要改动逻辑，全程无待裁决问题。

## 书「拆 plan_trip 与 _schedule_problems」任务 0：直接调用 plan_trip 的测试处数 41→42（2026-09-10，判断，非阻塞）

任务书「现状与任务 0」写"直接调用 plan_trip 的测试 41 处（test_keyless_e2e
11、test_replan 14、test_journey 6、test_amap_live 6、test_flyai_live
3……）"，句尾「……」已自陈是不完全列举。实测 `grep -rn "plan_trip(" tests/*.py`
命中 7 个文件共 42 处：列出的 5 个文件之和 11+14+6+6+3=40 与任务书吻合，未列出
的另外两个文件——`test_anysearch.py`（1 处，L502）、`test_variflight_live.py`
（1 处，L424）——补满 42。逐一核对这两处均为真实的 `plan_trip(...)` 调用（非
`replan_trip(` 等子串误命中），不是计数脚本的假阳性。

判断：不停工。这条数字只是任务书给的背景色（帮助理解"改签名会牵连多少调用点"
这个风险面），不在「完成条件」列出的硬指标之列（硬指标一是函数长度、硬指标二
是快照哈希+语料零漂移+全量测试），且任务书自己用「……」标注了不完整，42 与
「41……」并不矛盾，只是把省略号里的部分数出来了。真正约束拆分工作的锁点——
`plan_trip`/`_schedule_problems` 签名与返回类型不变、`_schedule_problems` 在
`tests/test_keyless_e2e.py:461` 的直接调用——已逐条核对与任务书完全一致，不
受此计数影响。

## 书「Journey 逐日时间轴」任务 0/3：真实 journey 页"40 个 restapi.amap.com 链接"的口径澄清（2026-09-10，判断，非阻塞）

任务书任务 0 写"真实 16 天 journey 渲染页含 40 个指向
restapi.amap.com/v3/geocode/geo 的 href，来自 geocode claim 的 source_url"。
任务 0 当时只核对了仓库内 `demo/` 与代码事实（均对上，见前面 PROGRESS.md
任务 0 小节），没有条件去核对仓库外那份真实文件——任务 3 才第一次真正读它。
任务 3 实测（`/Users/kangyishuai/Workspace/core/ChinaTripWeaver/
fujian-2026-09-25-to-10-10/`）：

- 旧的 journey 级渲染页 `福建中秋国庆16天行程.html`（本轮改动前就存在，
  2026-09-07 生成）里 `grep -o 'href="https://restapi.amap.com[^"]*"' | wc -l`
  为 **0**——journey 页面本来就没有"每条 claim 无条件转成链接"的机制
  （那是 Trip 页 `_evidence_section` 独有的，journey 页只有
  `journey_html.py:_source_link` 会给 checklist/risk 条目里带 `claim_id`
  的那条转链接，而这批 geocode claim 都不落在 unknown/claim_conflict 分支
  里，从未被链接过）。
- 40 这个数字，实测精确等于 `journey.json` 里 `claims[].source_url` 主机为
  `restapi.amap.com` 的条数（`Counter` 逐条数出 40），也是它作为纯文本字符串
  出现在渲染页嵌入 `<script id="journey-data">` 里的次数——嵌入 JSON 按设计
  必须原样保留完整数据（含 source_url），本轮改动没有也不应该碰它，这 40 次
  文本命中不会因为本轮改动而消失，属预期。
- 同目录三份 Trip 级中间产物（`trip-coast-r2-intermediate.html`、
  `trip-coast-r3-intermediate.html`、`trip-coast-r3.html`，经过真正会无条件
  链接每条 claim 的 `_evidence_section`）各自实测有 **14** 个真实可点击的
  `href="https://restapi.amap.com..."`——"点开只有报错"这个动机描述，字面
  精确对应的其实是 Trip 级渲染，任务 1 的修复对这三份文件才会产生
  40→0（或 14→0）这种直观的前后对比；它们不在任务 3 的范围内（任务 3 明确
  只要求渲染 `journey.json`），未重渲染，仅记录供参考。

判断：不影响任务 3 完成——journey.json 重渲染出的 0.9 页真实 href 本来就是
0（渲染前后一致），符合硬指标一"0 个接口地址链接"的字面要求；这条记录只是
澄清"40"这个数字的真实出处（嵌入 JSON 文本命中数，不是 href 数），避免以后
有人拿它去核对 journey 页面时对不上号。任务 1 的 `claim_source_html`/
E106/JH106 修复本身经仓库内 `weekend-live.json`（含实际 restapi.amap.com
href 的反向验证）与 journey 侧 `_source_link` 直接单测双重验证，代码路径本身
无误，只是这份特定的真实 journey 数据没有走到会触发它的分支。

## 书「Journey 逐日时间轴」任务 2：`scripts/qa_renderer_browser.py` 不在白名单但被验收命令点名（2026-09-10，已按最小改动处理，非空白裁决）

任务书「界限」只允许改 `scripts/build_renderer_fixtures.py` 这一个 scripts 文件；
但任务 2 验收明确要求跑 `scripts/qa_renderer_browser.py demo/journey-16d/journey.html
--output .tmp/qa --viewports 375x812,1440x900` 得到 `failures=[]`。实测该脚本
`validate_report()` 里硬编码 `"12 sections": report.get("sectionCount") == 12
and report.get("nonEmptySections") == 12`——这个 12 不是巧合，是 Trip 页
`REQUIRED_SECTIONS`（validate_html.py）与 Journey 页原 `JOURNEY_SECTIONS`
（journey_html.py）当时恰好都是 12 个分区，脚本本身对 Trip/Journey 通用、无
从判断页面类型，就地写死了这个数。本书任务 2 把 Journey 分区从 12 加到 15
后，用任务书给的原始命令跑：`failures: ["375x812 12 sections", "1440x900
12 sections"]`——但同一条报告里 `sectionCount`/`nonEmptySections` 实测均为
15、`horizontalOverflow` 均为 0，说明页面本身没有结构或溢出问题，纯粹是
脚本的旧假设过期。

判断：这是通用工具对旧结构的硬编码假设，不是本书刻意设的边界（界限小节从未
提到"分区数固定 12"是不可变更的约束，反而任务 2 正文明确要求把 Journey
分区数改成 15）；比照本文件已有先例（`test_contracts.py`/`SKILL.md`/
`build_plan_fixtures.py` 三条：验收明确要求的硬指标优先于白名单遗漏一个
文件，做最小改动）处理。已执行：`validate_report()`/`run_qa()`/`main()`
加一个可选 `--sections`（默认 12，不传等于旧行为），把硬编码的 `12` 换成
参数值，检查名同步显示实际期望值（如 `"15 sections"`），不改其他任何逻辑。
本书对 Journey 的调用改传 `--sections 15`；Trip 页两处既有调用者
（`tests/test_renderer.py::test_network_blocked_browser_viewports_and_print`、
`tests/test_keyless_e2e.py::test_keyless_html_opens_offline_with_no_remote_
requests`）都不传该参数，默认值 12 保证它们行为不变。

验证：改动后 `/usr/bin/python3 scripts/qa_renderer_browser.py demo/
journey-16d/journey.html --output .tmp/qa --viewports 375x812,1440x900
--sections 15` → `failures: []`，两个视口 `horizontalOverflow` 均为 0；上述
两个既有 Trip 页测试单独重跑均 `ok`（用默认 12，未受影响）；`tests/
test_journey.py` 新增 `test_checked_in_sixteen_day_demo_passes_offline_
browser_qa` 把这条命令固化为回归测试，防止分区数再变而没人发现。pyflakes
对该文件 0 行。

## 书「ctw replan --rail-result」任务 2：硬指标二的 plugins diff 排除式与白名单本身冲突（2026-09-10，已按白名单执行，非空白裁决）

任务书「界限」明确把 `skills/replan-china-trip/SKILL.md` 列入允许改动清单，
任务 2 正文也明确要求「replan-china-trip/SKILL.md 加 refresh 两步用法」——
这是两处独立、明确写出的要求。但「完成条件」硬指标二写
`git diff 7fc66ec --stat -- plugins ':!*cli.py'` 须为空，而 `SKILL.md` 的
真实路径是 `plugins/china-trip-weaver/skills/replan-china-trip/SKILL.md`，
落在 `plugins` 之下，`':!*cli.py'` 这个 pathspec 只排除文件名匹配
`*cli.py` 的路径（本仓库里就是 `cli.py` 一个文件），不排除同目录树下的
`SKILL.md`——两者字面直接冲突，若不改 `SKILL.md` 就完不成任务 2 的明文要求
（也违反白名单允许改动的意图），若改了 `SKILL.md` 硬指标二这条 grep 式检查
必然非空。

判断：白名单与任务正文两处明确、具体地要求编辑这一个文件，硬指标二那条
pathspec 更像是编写任务书时假设「`plugins` 下这轮只会动 `cli.py`」而漏算了
同样在白名单内、同样在 `plugins/` 目录树下的 `SKILL.md`，是任务书自身的
疏漏而非故意设的边界（对照「界限」小节，读/写权限从未把 `SKILL.md` 排除在
外，反而是唯一点名要求编辑的 skills 文件）。按「算得对 > 做得全」与既有
先例（本文件「书 docs-drift 任务 2」条目：验收硬指标与白名单字面冲突时，
选更接近「说的与代码一致」的一侧）处理：保留 `SKILL.md` 的编辑，不为了让
这条 grep 式检查归零而阉割任务 2 的明文要求。

证据：`git diff 7fc66ec --stat -- plugins ':!*cli.py'` 输出仅一行
`plugins/china-trip-weaver/skills/replan-china-trip/SKILL.md | 9
+++++++++`，是本轮任务 2 新增的 refresh 两步用法段落（`ctw rail
--output-json` → `ctw replan --rail-result`），不含任何其他改动；`plugins/`
下唯二被改的文件就是白名单点名的 `cli.py`（任务 1，已被该 pathspec 排除）
与 `SKILL.md`（任务 2，被排除式漏算）。

## 书 A2b 任务 2：`git diff main` 的"删测试"验收因并行 A1b 书已合入 main 而失真（2026-09-10，判断，非空白裁决）

任务 2 完成后按任务书跑 `git diff main -- tests | grep -E '^-\s*def test_'`，
非 0 行，打出 `test_cli_refresh_without_rail_result_fails_without_outputs`/
`test_cli_non_refresh_event_with_rail_result_fails` 两条。查明：这不是本书
删除的测试——任务书安排的并行书 A1b（`ctw replan --rail-result` 接线，在
main 上直改）已在本书执行期间合入 main（提交 `4216c59`、`f2b0f34`），本
分支仍从任务书指定的分支点 `7fc66ec` 分出、按规矩"不碰 main"未合并 main
后续提交，两条测试是 A1b 书新增，本书从未触碰 `test_replan.py`。

处置：改用本分支真实分出点 `7fc66ec`（而非已经移动的 `main`）重新比较，
`git diff 7fc66ec -- tests | grep -E '^-\s*def test_'` 与
`git diff 7fc66ec --stat -- plugins/china-trip-weaver/schema demo` 均为
0/空，证实本书确实 0 行删测试、0 行碰 schema/demo。任务书的验收命令写在
"main 静止不动"的假设下，未预见另一本并行书会在同一时间窗口合入 main；
按"跳过做别的，继续"处理，不停工，供合并时核对——merge 时这两条测试会随
main 的最新提交自然出现在合并结果里，不需要额外动作。

## 顺手发现：0.7.0 没有实际的 git tag 或 GitHub Release（2026-09-10，未处理，仅记录）

写任务 4（发版流程写进 CONTRIBUTING）时核对历史实际发版步骤，发现 `git tag -l`
只有一条无关的 `backup-before-author-rewrite`、`gh release list` 为空——`0.7.0`
虽然提交信息以 `Release 0.7.0:` 开头、`PROGRESS.md`/`CLAUDE.md` 都记「已发布」，
但实际从未执行过 `git tag`/`gh release create`，只完成了「装进本机真实
Codex」这一步。任务 4 的范围是「把发版流程写进文档，只写不执行」，不包含替
历史版本补标签/Release，因此未处理，仅记在此供领导决定是否要为 `0.7.0`
（或直接从下一个版本开始）补打标签与发布。

## 书 docs-drift 任务 2：`scripts/build_plan_fixtures.py` 不在白名单但被 pyflakes 点名（2026-09-10，已按最小改动处理，非空白裁决）

任务书「界限」只允许改 `scripts/scan_secrets.py` 这一个 scripts 文件；但 pyflakes
`plugins/china-trip-weaver/src tests scripts` 的 11 行里，`scripts/
build_plan_fixtures.py:10: 'typing.Dict' imported but unused` 也在其中，而任务 2
的验收明确要求这条命令整体为 0 行。白名单字面只列一个 scripts 文件，验收字面
要求 scripts 目录全干净，两者直接冲突，无人可问。

判断：比照书 B 任务 1（`tests/test_contracts.py` 越界修改）已定的先例——「验收
明确要求的硬指标」优先于「白名单遗漏一个文件」，且改动本身与已批准的
`scan_secrets.py` 那处是同一类最小改动（删一个未使用的 `typing` 导入名，不改
其他任何字符），按此处理更接近「说的与代码一致」的第一优先级。已执行：
`from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple` 删掉
`Dict`，其余名字不动。验收：pyflakes 三目标合计 0 行；全量
`/usr/bin/python3 -m unittest discover -s tests`：`Ran 507 tests`、`OK`、
0 skipped；`git diff main -- tests | grep -E '^[-+]\s*def test_'` 0 行
（本次改动未新增/删除任何测试函数）。

## 书 docs-drift 任务 0：pyflakes 全仓基线与任务书数字差 1 行（2026-09-10，判断，非空白裁决）

任务书「现状与任务 0」写「`~/miniconda3/envs/core/bin/python -m pyflakes
plugins/china-trip-weaver/src` 0 行，加上 tests scripts 后 10 行」；HEAD
`c9c9c15` 实测（同一解释器、同一 pyflakes 3.4.0）`src` 单独 0 行、加
`tests scripts` 后 **11 行**，比任务书多 1 行：

```
tests/test_contracts.py:19:1: 'china_trip_weaver.clock.SHANGHAI' imported but unused
tests/test_renderer.py:6:1: 'math' imported but unused
tests/test_renderer.py:7:1: 're' imported but unused
tests/test_renderer.py:20:1: 'china_trip_weaver.contracts.canonical_json' imported but unused
tests/test_providers.py:522:9: local variable 'business' is assigned to but never used
tests/test_providers.py:523:9: local variable 'official' is assigned to but never used
tests/test_scheduler.py:11:1: 'unittest.mock' imported but unused
tests/test_evidence.py:3:1: 'json' imported but unused
scripts/scan_secrets.py:7:1: 'os' imported but unused
scripts/scan_secrets.py:12:1: 'typing.Iterable' imported but unused
scripts/build_plan_fixtures.py:10:1: 'typing.Dict' imported but unused
```

判断：任务 2 的验收目标是「pyflakes 点名的项清零」，不是「起点必须恰好是
10」，1 行的起点计数出入不改变任务 2 该做什么（清空以上全部 11 行），也不
影响任务 3/4；无人可问，按「跳过做别的，继续」处理，不停工，只记录证据。
可能原因：任务书基线是别的时刻/别的 pyflakes 版本测出的，或人工计数时漏数
一行；未去追查，因为不影响任何验收口径。

## Closed：GitHub CI 自 2026-09-05 起连续全红（2026-09-08 洁癖收尾发现，同日经领导裁决修复）

- **处置（2026-09-08）**：领导裁决按建议直接修。提交 `b160501`：`test_codex_skill_parser_smoke_runs_standalone` 改用插件自己的 `plugin_conflicts.codex_executable()` 判断本机有无 Codex，没有时 `skipTest`，与另两条 Codex 依赖测试同款；`actions/checkout@v7`、`actions/setup-python@v7`（node24）；CONTRIBUTING 与两份 README 改为「三项 Codex 依赖测试」。本机全量仍 `Ran 507 tests` OK 零跳过；模拟无 Codex（`CODEX_BIN=/nonexistent`）时 `OK (skipped=1)`。推送后 GitHub Actions run 34217843374 两条矩阵均通过：`Ran 507 tests`、`OK (skipped=3)`、`secret scan: 0 finding(s)`，Node 20 弃用告警消失。

- 证据：`gh run list --limit 12` 显示 2026-09-05 `99b9468` 起到 2026-09-08 `d809ab1` 的 12 次 push 全部 `failure`；两条矩阵（Python 3.9 / 3.13）都是 `Ran 507 tests`、`FAILED (failures=1, skipped=2)`，唯一失败是
  `tests/test_skills.py::test_codex_skill_parser_smoke_runs_standalone`——它调用 `scripts/install_local_plugin.sh --skill-smoke`，runner 上没有 Codex，脚本退出 2：「找不到 codex 可执行文件；请设置 CODEX_BIN」。另两条 Codex 依赖测试（`test_all_skills_pass_bundled_validator`、`test_plugin_passes_bundled_validator`）在无 Codex 时 `skipTest`，所以是 skipped=2。
- 为什么一周没人发现：本地机器装了 Codex，全量 507 全绿；没有人看 GitHub Actions 的结果，CONTRIBUTING 也只说「有两项测试会跳过」。
- 影响：远端 CI 对任何 PR/贡献者都是红的，等于没有门禁；README 的「suite has zero skips」只对装了 Codex 的机器成立。
- 建议（未执行，属测试行为改动，需领导裁决）：给 `test_codex_skill_parser_smoke_runs_standalone` 加与另两条同款的环境守卫——`--skill-smoke` 因找不到 codex 而退出 2 时 `skipTest`，其他非零仍失败；CONTRIBUTING 两份改为「三项 Codex 依赖测试在无 Codex 的机器上跳过，装了就必须通过」；本地仍要求零跳过。顺带把 `.github/workflows/ci.yml` 的 `actions/checkout@v4`、`actions/setup-python@v5` 升到 Node 24 版本（GitHub 已发 Node 20 弃用告警）。

## 0.7.0 发版书 任务 4：「`git status --short` 为空」的口径裁决（2026-09-08，判断，非空白裁决）

任务 4 验收原文:「删后再跑全量 507 OK;`git status --short` 为空」。字面上此刻
`git status --short` 不可能为空——任务书自己把任务 4 标题定为「装机后、提交前」
(即任务 1/2/3 的源码改动此时都还未提交,必然显示为 `M`),且「规矩与完成条件」
明确要求最后统一提交一次(`Release 0.7.0` 开头)。无人可问,判断这条验收的真实
意图是「删缓存这个动作本身没有动到任何 git 跟踪的文件」而不是「此刻整棵树无
改动」,理由:`.npm-cache`、`.tmp/*` 均被根 `.gitignore` 挡住、`.tmp/.gitkeep`
是唯一被跟踪的文件且 `rm -rf .tmp/*`(bash 的 `*` 不匹配点开头文件)不会删到它。
按此口径验证:`git status --short -- .npm-cache .tmp` 空输出,`.tmp/.gitkeep`
仍在,`.npm-cache`/`$C/.npm-cache` 均已不存在(`CLEANED` 已过)。全局
`git status --short` 的非空部分逐一核对,只包含任务 1/2/3 白名单内的
17 个文件,不包含任何缓存路径。

## 书 B 任务 1：`tests/test_contracts.py` 越界修改（2026-09-08，已按最小改动处理，非空白裁决）

任务书「界限」只允许改 `tests/test_packaging.py:103` 一处测试；删除
`docs/design/schema/` 的 7 个重复文件后按此执行，全量测试出现
`ERROR: test_packaged_schema_is_byte_identical_to_accepted_schema
(test_contracts.ContractTests)`——`FileNotFoundError`，因为
`tests/test_contracts.py:72-82` 还有两个测试直接依赖被删的
`docs/design/schema/trip.schema.json` 与 `docs/design/schema/examples/`。
用 `ROOT / "docs" / "design" / "schema" / ...` 分段拼路径，之前搜字面量
`docs/design/schema` 的 `git grep -n "docs/design/schema" -- '*.py'` 没扫到，
是任务书基线未覆盖的依赖。

判断：任务 1 删除这 7 个文件是任务书明确要求的核心动作，不能因为一个未列入
白名单的测试而撤回；但「最终门」明确要求全量 507 测试 OK 无 skipped，两者
都是硬指标，字面「只允许改 test_packaging.py」与「507 全绿」在此处直接冲突。
无人可问，判断修 `test_contracts.py` 这两个测试比放弃删除或留红更接近
「说的与代码一致」的第一优先级，且改法与任务书已明确批准的
`test_packaging.py:103` fix 同构（都是断言"目录只剩 check_schema.py"），不是
放宽断言、不是 mock、不删测试、方法名不变，`git diff HEAD -- tests | grep
'^[-+]\s*def test_'` 仍为 0 行。

具体改动：`test_packaged_schema_is_byte_identical_to_accepted_schema` 改为
断言 `docs/design/schema` 只剩 `check_schema.py`（同 `test_packaging.py`
新断言）+ 断言 `plugins/china-trip-weaver/schema/trip.schema.json` 仍存在；
`test_accepted_examples_are_unchanged_in_test_fixtures` 改为断言
`docs/design/schema/examples` 不存在 + `tests/fixtures/trips/schema/{valid,
invalid}` 仍分别是 2/4 个文件（原来 examples 就是 2 valid + 4 invalid，用
计数守住这个历史事实不被静默改变）。

反向验证：`touch docs/design/schema/ghost.json` → 第一个测试
`FAILED (failures=1)`（`['check_schema.py'] != ['check_schema.py',
'ghost.json']`）→ 删除 → 绿；`mkdir -p docs/design/schema/examples &&
touch .../x.json` → 第二个测试 `FAILED (failures=1)`（`True is not
false`）→ `rm -rf` → 绿。改后全量 `/usr/bin/python3 -m unittest discover -s
tests`：`Ran 507 tests`、`OK`、0 skipped；`git diff HEAD -- tests | grep -E
'^[-+]\s*def test_' | wc -l` = 0；`git diff HEAD --stat -- plugins
tests/fixtures .github README.md` 仍为空（越界只发生在 `tests/
test_contracts.py`，未触达这四个受保护路径）。

# Archived items

Book 32 closed the final six coverage-only items in the Book 23 combination table below;
none exposed a product bug. This page now contains archived provenance only; the
per-round evidence lives in `PROGRESS.md`.

## Closed

### Public-distribution legal links are a consequence of ADR-0013, not pending work

Reclassified on 2026-09-05 — reviewed and moved, not fixed, because it was never a task.
`interface.websiteURL` points at the real repository; `privacyPolicyURL` and
`termsOfServiceURL` are deliberately absent rather than invented. That follows directly
from [ADR-0013](docs/design/adr/0013-stay-off-the-public-marketplace.md): the plugin ships
as source and installs from a local marketplace, because every user must obtain their own
AMap, FlyAI, and VariFlight credentials and AMap requires personal verification before it
grants any quota. A public listing would promise an installability that does not exist.
If that decision is ever revisited, publishing reviewed privacy and terms pages, adding
their real HTTPS URLs, and rerunning plugin ingestion validation become prerequisites of
the new decision — reopen it there, not here.

### 12306 station candidates now carry best-effort distance signals

Closed on 2026-09-05. Pinned `12306-mcp@0.3.10` still supplies only station names and
codes; after its process has completed, the rail transport now uses the existing AMap
geocode capability for the candidate city's centre and the existing AMap POI capability
for each station coordinate. It computes GCJ-02-to-GCJ-02 distance with the repository's
existing `haversine_meters` helper and lets the established rail sort place known nearest
stations first and unknown distances last. It never selects a station for the user.

The enrichment accepts only a unique same-city, exact-normalized rail-station POI. A clean
miss leaves that candidate untouched; a missing Key, missing city centre, provider outage,
contract failure, or unexpected exception restores the entire original station resolution.
Those paths do not change 12306 health. Synthetic three-station coverage proves 3/3 are
retained with two calculated distances and one unknown; the combined repository gate is
402 tests, OK, with zero skips, and the repository secret scan has zero findings.

Every other item below was closed during the 2026-09-04/05 audit-remediation rounds. Kept
for provenance; none of it is pending work.

- **Lodging and flight inventory had a single upstream source** — closed 2026-09-04 by
  independent fallbacks: VariFlight `searchFlightsByDepArr` for flights and AMap POI
  accommodation search for lodging, both publishing `verify-on-click` with no price. With
  FlyAI forced to time out on every call, both capabilities still return candidates.
- **`pace=slow` refused tight itineraries instead of degrading** — closed 2026-09-04 by a
  three-step fallback (fewer daily POIs, 0.70 duration compression, balanced end time)
  that records every applied step in `request.assumptions`.
- **Grouped Trips crashed outside the planner** — closed in 0.3.0. The validator, renderer,
  and FlyAI lodging path read `traveler_groups` natively; all compatibility projections
  were deleted.
- **The two request shapes were only one-way exclusive** — closed in 0.3.0. The grouped
  `oneOf` branch now pins `origin` and `travelers` to null, and a contract test asserts
  `S_ONE_OF` in both directions.
- **Same-name Skill detection, provider terms, sample-data redistribution, and the public
  marketplace decision** — all closed 2026-09-04; see the detail preserved below.

---

# Appendix: original per-round records

## Book 8: standalone grouped Trip consumption (resolved in 0.3.0 on 2026-09-05)

- Previous blocker: Book 8 could not edit the public validator or renderer, so a strict grouped Trip produced `KeyError: 'origin'` outside the planner even though its schema-only validation passed. FlyAI lodging parameter derivation likewise raised `KeyError: 'travelers'` without a planner projection.
- Resolution: `validate_trip` now adds every `traveler_groups[].origin` plus `meeting_anchor.location` to the native reference set; renderer totals group travelers and lists every grouped origin; FlyAI lodging derives adults from the group sum. `planning.py` passes the real request to those consumers and deletes all three compatibility projection helpers.
- Evidence: a serialized strict grouped Trip now exits 0 through `ctw validate` and `ctw validate-html`; the checked-in `demo/grouped-departures/` also passes both. Removing the group-origin merge turns the precise regression red with two `V_ENDPOINT_REF` errors and `V_ORIGIN_REQUIRED`; restoring it returns the required 65-test keyless/renderer gate to `OK`.

## 0.3.0 release

- Status: 无新增阻塞（no new blocker）。The grouped-consumer fix, four synthetic demos, exact ten-place version bump, full 361-test gate, repository secret scan, and real Codex 0.3.0 installation all have passing evidence in `PROGRESS.md`.
- The first real installer check found a pre-existing, Git-ignored 398 MB plugin-local npm cache. It was moved out of the plugin tree so the installer could copy it; the second install and final `--check` both passed. Acceptance correction on 2026-09-05: that cache is **no longer recoverable** — the Trash is empty and the directory is gone from disk (most likely the owner emptied it). No loss of substance: it held only npx-downloaded provider packages, which are Git-ignored and re-downloaded on the next provider call. No source, fixture, or credential was in it. This is resolved residue, not pending product work.

## Book 3: ordered multi-city planning

- Status: 无新增阻塞（no new blocker）。The implementation, compatibility, reverse-validation, demo, and schema gates all have an in-scope path to completion.

## Book 1: AMap place identity

- Status: 无新增阻塞（no new blocker）。POI identity, administrative consistency, business conflict preservation, semantic outliers, reverse validation, and synthetic fixtures all have in-scope implementations and passing tests.

## Book 2: live 12306 station candidates have no distance signal

- Status: blocked on 2026-09-04 for physical-distance ordering only; the remaining station fallback and error-classification work continues.
- Evidence: pinned `12306-mcp@0.3.10` implements `get-stations-code-in-city` as a list containing only `station_code` and `station_name`. The current rail `ProviderRequest` likewise carries names/refs/date but no station coordinates or candidate-to-endpoint distances.
- Constraint: `planning.py`, `mobility.py`, and AMap providers are explicitly owned by other books and may not be changed here. Querying every candidate for tickets would produce duration, not physical distance, and could still silently choose the wrong station.
- Safe delivery: return every candidate without selecting one; sort ascending when a synthetic/forward-compatible candidate supplies `distance_meters`, with unknown distances last and deterministic ties. Live candidates without a distance remain deterministic but are not claimed to be physically ranked.

No product-level item is open. Standing constraints are not listed here, because a list of unresolved items
should mean pending work. They live where they are enforced:

- Provider terms, attribution, caching, and the licences commercial use would
  require: `THIRD_PARTY_NOTICES.md`.
- Provider pins, deadlines, degradation, and FlyAI's optional status:
  `plugins/china-trip-weaver/references/provider-contracts.md`.
- Architecture decisions, including why this plugin is not listed on a public
  marketplace: `docs/design/adr/`.

## Book 16: Journey AMap segment budgets and run-local reuse

- Status: 无新增阻塞（no new blocker）。The three-segment synthetic Journey now
  receives one independently counted AMap allowance per logical Trip under a
  configurable Journey-wide ceiling. Exhaustion remains visibly
  `rate_limited`, and the Trip falls back to static routing without widening
  either the segment or total limit.
- Repeated entity POI/geocode responses are reused only in memory and only
  inside one `plan_journey` invocation. No provider response is written to
  disk; a second Journey invocation performs its own calls. Route responses
  remain uncached so their time-sensitive result is queried per segment.
- All evidence is synthetic and offline. No demo, schema, renderer, version,
  Codex installation, publication, or provider cache-policy work was performed.

## Lodging and flight inventory have a single upstream source (closed)

- Status: closed on 2026-09-04, superseded by the tested independent fallbacks
  recorded under Book 4 above. Kept here for provenance; the facts below
  describe the situation before those fallbacks existed.
- Fact: `@fly-ai/flyai-cli` is the only source for both lodging and flight
  inventory. It is an unofficial third-party wrapper published by an individual
  maintainer, it last shipped on 2026-04-21, and its command surface already
  drifted once between releases. If it is abandoned or changes shape, both
  capabilities disappear together.
- Contained, not solved: `--lodging` defaults to `off`, a probe mismatch fails
  closed, and tests assert that a failing FlyAI still yields a schema-valid
  Trip, reports its own health, invents no flight candidate, and leaves lodging
  to the candidate file. The plugin degrades; it does not break.
- Two candidate second sources are already wired into this repository, which
  makes this smaller than it looks:
  - Flights: the VariFlight adapter already calls `searchFlightsByDepArr`,
    which returns dated schedules for a city pair. Today it only enriches
    FlyAI legs with status and comfort. Promoting it to an independent source
    would give schedules and flight identity without prices.
  - Lodging: the AMap adapter already has a `poi` capability. An accommodation
    category search would give candidate properties with verified coordinates,
    again without prices or availability.
- What either would not give: a price. Both fallbacks would have to publish
  `verify-on-click` rather than a number, which the price contract already
  supports.
- Impact if left as is: a FlyAI outage costs lodging and flight inventory for
  the duration. Nothing else regresses.

## What was closed, and when

- 2026-09-04, same-name Skill detection. Codex shipped
  `codex plugin list --json`, so `ctw doctor` now reads it, walks each enabled
  plugin's `skills/` directory, and reports `skill_conflicts`, exiting non-zero
  on a collision. Verified against a real installation of the older
  `china-travel-assistant`, which does expose `plan-china-trip`.
- 2026-09-04, sample-data redistribution. `demo/` and
  `tests/fixtures/providers/` hold only locally generated synthetic values, and
  a regression test scans every Git-tracked file for the retired markers.
- 2026-09-04, provider terms. AMap and VariFlight were reviewed clause by
  clause. Caching is forbidden and no provider response is cached; attribution
  is required and the rendered footer names every contributing provider;
  commercial use needs licences this project does not hold, which the readme
  and notices state plainly.
- 2026-09-04, public marketplace listing. Decided against in
  [ADR-0013](docs/design/adr/0013-stay-off-the-public-marketplace.md).
- 2026-09-04, FlyAI wrapper terms. Its data is treated under the same
  no-cache, no-redistribution rule, and the wrapper itself is now documented and
  tested as an optional, best-effort source.

## Book 5 — public-distribution legal links remain open

- `interface.websiteURL` now points to the real GitHub repository. No
  `privacyPolicyURL` or `termsOfServiceURL` was invented: ADR-0013 keeps this
  plugin off the public marketplace and the project has no real policy pages.
- Before any future public distribution, publish reviewed privacy and terms
  pages, add their real HTTPS URLs to the manifest, and rerun plugin ingestion
  validation. Until then, local/repository distribution is the supported scope.

## Book 5 — required manifest field conflicted with a forbidden exact-fixture test (resolved)

- Status: resolved on 2026-09-04. The task brief required `interface.websiteURL`
  while placing `tests/test_packaging.py` off limits, and that test pins the
  former eight-key `interface` object exactly. The conflict was in the brief,
  not in the implementation.
- Book 5 responded correctly: it relaxed no assertion, edited no forbidden test,
  withdrew no required field, reproduced the deterministic failure twice, and
  recorded the conflict instead of working around it.
- Resolution: `EXPECTED_MANIFEST` now carries the real GitHub `websiteURL`, so
  the assertion stays an exact equality rather than a loosened one. Verified by
  reverse test — pointing the manifest at a different URL fails that test, and
  restoring it passes. Full discovery is `Ran 324 tests ... OK`, skipped 0.

## Book 4 — single lodging/flight upstream closed

- Status: closed on 2026-09-04. The earlier “Lodging and flight inventory have
  a single upstream source” item is superseded by tested independent fallbacks.
- With FlyAI forced to timeout on every call, configured VariFlight
  `searchFlightsByDepArr` returned two dated schedule candidates and configured
  AMap POI returned one accommodation-category candidate. Every fallback price
  was `amount=null` and `price_type=verify-on-click`; FlyAI health remained
  visibly `degraded` with `errors=timeout`.
- No new Book 4 blocker remains. The unrelated Book 5 manifest/test conflict is
  outside Book 4 scope and remains untouched.
## slow 档在紧凑行程上只会无解，不会降配（验收时发现，2026-09-04）

- 现象：同一份 `beijing-shanghai-3d` 候选，`pace=balanced` 与 `full` 都能排出
  完整日程，`pace=slow` 直接 `PLAN_FAILED`，conflict 为
  `{"code":"window","message":"required candidate routine-transfer-buffer-… has no feasible insertion"}`。
  换成 POI 更多的 `demo/multicity-5d` 候选时三档都能排，所以这不是 slow 档普遍
  失效，而是窗口收窄（09:00–20:00）后，必需的餐、休息与跨城 buffer 在这份
  3 天跨城往返上塞不下。
- 为什么不算书 6 未完成：输出是结构化无解而非崩溃，CLI 给出 `PLAN_FAILED` 加
  具名 conflict 并 exit 1，符合任务书对无解的要求；三档可区分这条也成立
  （slow 排 2 个 POI、18:00 结束，balanced/full 排 5 个、19:50 结束）。
- 为什么仍要记一笔：产品语义反直觉——用户选「慢一点」，得到的却是排不出来。
  CTW-004 原本要求的是「结构化无解**或降配**」，目前只实现了前者。
- 建议解法（留给后续发布轮裁决）：slow 档在无解时先尝试降配（减少 POI、缩短
  单点时长、放宽当日结束时间到 balanced 档），仍不可行才返回无解，并在
  unknowns 或 assumptions 里说明降了什么。

## Book 7: baseline observation differs from task brief (2026-09-04)

- Required baseline commands otherwise match exactly: HEAD and `origin/main` are `176dbc70fae76924014dca9e6913337436048ed2`; `/usr/bin/python3 -m unittest discover -s tests` reports `Ran 324 tests in 22.346s` and `OK` with zero skips; `/usr/bin/python3 scripts/scan_secrets.py` reports `secret scan: 0 finding(s) across 357 file(s)`.
- `rg -n "semaphore|Retry-After" plugins/china-trip-weaver/src/china_trip_weaver/providers` is not empty. Its sole output is `amap_http.py:219:    for name in ("Content-Type", "Retry-After"):`. Inspection shows this only preserves a response header in the existing HTTP transport; no semaphore or retry implementation exists. Work that depends on the absence of retry/concurrency control remains unaffected, so Book 7 continues without changing this pre-existing header capture.

## Book 7: full gate temporarily blocked by parallel Book 6 window work (2026-09-04)

- First post-implementation full discovery found 340 tests but exited 1: `Ran 340 tests in 22.464s`, `FAILED (failures=1, errors=16)`. Every traceback terminates at the forbidden Book 6 edit `planning.py:255` with `ValueError: plan has no feasible schedule: window`; affected legacy callers include AMap, FlyAI, keyless E2E, and VariFlight integration tests.
- Book 7's own 55 focused tests are green, compileall and `git diff --check` are clean, and `scripts/scan_secrets.py` remains `0 finding(s) across 357 file(s)`. Per the two-book ownership boundary, Book 7 has not edited or reverted `planning.py`, schema, scheduler, or Book 6 tests and will rerun the full gate after that parallel work settles.

## Book 7: process-rule lapse (2026-09-04)

- During a post-implementation read-only search for `unknown_id`, Book 7 accidentally suffixed `rg` with the categorically forbidden `|| true`. It masked only ripgrep's expected exit 1 for zero matches; no test, assertion, secret scan, threshold, or acceptance command was masked or skipped. The same search was immediately rerun unmasked and its real exit status retained. This syntax use cannot be undone, so it is disclosed here rather than omitted from delivery evidence.

## Book 7: parallel full-gate blocker resolved (2026-09-04)

- The earlier Book 6 `conflict=window` integration blocker is closed by Book 6 commit `9097463`. On the same combined code tree, Book 7 reran full discovery and obtained `Ran 346 tests in 31.327s`, `OK`, skipped 0; the secret scan remained 0 findings.
- No product or code blocker remains for Book 7. The baseline `Retry-After` observation mismatch and the disclosed read-only `|| true` process lapse above remain historical delivery facts, not pending implementation work.

## Journey 模型、拆分与连续性（2026-09-05）

- 本轮新增阻塞：无。
- 已解决的验收冲突：首次全量测试发现禁止修改的
  `tests/test_skills.py` 逐字冻结主 Skill 的 frontmatter description；修改该描述会使
  `test_exact_nine_skill_names_and_descriptions` 失败。已恢复原 description，把 Journey
  路由、完整子 Trip、连续性与 CLI 指令保留在同一 `SKILL.md` 正文；精准测试与
  bundled quick validator 均恢复通过，未修改或放宽既有测试。

## 0.4.0 Journey 总览与本机发布（2026-09-05）

- 本轮新增阻塞：无。

## 书 13 Journey 拆分粒度（2026-09-05）

- 本轮新增阻塞：无。

## Provider 运行时 unknown 原因覆盖（2026-09-05）

- 本轮新增阻塞：无。

## 书 17 Journey provider health 重复原因计数（2026-09-05）

- 本轮新增阻塞：无。

## 书 19 Journey replan 连续性（2026-09-05）

- 本轮新增阻塞：无。
- 中间完整 Trip 的 delay 可由现有 `replan_trip` 完成；改后放回 Journey 的住宿、交通与日期段缝均有本书白名单内的实现和合成离线回归，不需要新增命令、自动顺延后段或修改四种事件语义。

## 书 18 候选身份反馈（2026-09-05）

- 本轮新增阻塞：无。

## 0.5.0 本机发布（2026-09-05）

- 本轮新增阻塞：无。

## 坐标定位失败 unknown（2026-09-05）

- 本轮新增阻塞：无。

## 书 23 组合排查：覆盖空格已由书 30/32 补齐（2026-09-05）

- 状态：书 30 关闭其中 12 格，书 32 用 6 条上层回归补齐余下 6 格；没有一格暴露产品 bug，两轮都没有为覆盖债修改实现。
- 共同复现入口均为离线合成输入：POI 用 `tests.test_providers.amap_scenario_candidates`，住宿 AMap 用 `tests.test_amap_live.lodging_geocode_candidates`，车站用 `tests.test_rail_station_fallback.RailStationFallbackTests._query`，FlyAI/VariFlight 用各自 backend 与 `tests/fixtures/e2e/beijing-shanghai-3d` route；不得访问实网。

| 实体分支 | 最小 provider 输入/失败 | 书 30/32 逐格结论 |
|---|---|---|
| POI × AMap × 无结果 | `poi-v5` + `page_num=1,page_size=2,pois=[]` | 已覆盖：`AMapMobilityTests.test_poi_no_results_degrades_entity_with_exact_warning_and_health` |
| POI × AMap × 限流 | POI 请求返回 HTTP 429 | 已覆盖：`AMapMobilityTests.test_poi_rate_limit_stops_entity_with_exact_warning_and_health` |
| POI × AMap × 契约漂移 | `poi-v5` 但 `pois={}` | 已覆盖：`AMapMobilityTests.test_poi_contract_drift_stops_entity_with_exact_warning_and_health` |
| POI × AMap × 网络失败 | transport 连续两次抛 `ProviderNetworkError` | 已覆盖：`AMapMobilityTests.test_poi_network_failure_retries_then_degrades_exact_entity` |
| 住宿 × AMap × 契约漂移 | `geocode-v3` 但 `geocodes={}` | 已覆盖：`AMapMobilityTests.test_lodging_geocode_contract_drift_stops_with_exact_entity_state` |
| 住宿 × AMap × 网络失败 | transport 连续抛 `ProviderNetworkError` | 已覆盖：`AMapMobilityTests.test_lodging_geocode_network_failure_retries_and_preserves_anchor` |
| 车站 × 12306 station × 网络失败 | 合成 MCP 在 `get-stations-code-in-city` 回答前退出 | 已覆盖：`RailStationFallbackTests.test_station_network_exit_retries_then_degrades_exact_entity` |
| 车站 × AMap enrichment × 歧义 | city geocode 返回两个不同同城坐标 | 已覆盖：`RailStationFallbackTests.test_amap_ambiguous_centre_keeps_all_stations_and_rail_health_ready` |
| 车站 × AMap enrichment × 限流 | station POI 返回 HTTP 429 | 已覆盖：`RailStationFallbackTests.test_amap_poi_rate_limit_keeps_all_stations_and_rail_health_ready` |
| 车站 × AMap enrichment × 契约漂移 | station POI 返回 `pois={}` | 已覆盖：`RailStationFallbackTests.test_amap_poi_contract_drift_keeps_all_stations_and_rail_health_ready` |
| 住宿 × FlyAI × 无结果 | `status=0,data.itemList=[]` 的 lodging 请求 | 已覆盖：`FlyAIBackendEntityFailureTests.test_lodging_no_results_keeps_empty_inventory_with_ready_health_warning` |
| 住宿 × FlyAI × 网络失败 | lodging transport 连续抛 `ProviderNetworkError` | 已覆盖：`FlyAIBackendEntityFailureTests.test_lodging_network_failure_retries_then_degrades_exact_entity` |
| 航班 × FlyAI × 无结果 | `flyai/empty.json` 对应的 flight 空结果形状 | 已覆盖：`FlyAIBackendEntityFailureTests.test_flight_no_results_keeps_empty_comparisons_with_exact_warning_and_health` |
| 航班 × FlyAI × 限流 | `flyai/rate_limit.json` 的 HTTP 429 | 已覆盖：`FlyAIBackendEntityFailureTests.test_flight_rate_limit_keeps_empty_comparisons_with_exact_warning_and_health` |
| 航班 × FlyAI × 契约漂移 | `flyai/wrong_shape.json` 的非 JSON body | 已覆盖：`FlyAIBackendEntityFailureTests.test_flight_contract_drift_keeps_empty_comparisons_with_exact_warning_and_health` |
| 航班 × FlyAI × 网络失败 | `flyai/stderr_error.json` 的 network transport | 已覆盖：`FlyAIBackendEntityFailureTests.test_flight_network_failure_retries_and_keeps_empty_comparisons_with_exact_warning_and_health` |
| 航班 × VariFlight search × 无结果 | `variflight/empty.json` 的空 search | 已覆盖：`VariFlightLiveTests.test_search_no_results_keeps_empty_candidates_with_exact_warning_and_health` |
| 航班 × VariFlight search × 限流 | `variflight/rate_limit.json` 的 HTTP 429 | 已覆盖：`VariFlightLiveTests.test_search_rate_limit_keeps_empty_candidates_with_exact_warning_and_health` |

- 以下是书 23 当时实际验证的住宿 network 可复现输入；书 30 现已把同一 error class 固化为上表具名 unittest，原记录保留作历史证据：

```text
/usr/bin/python3 - <<'PY'
import json
from tests.test_amap_live import FIXED_NOW, credentials, lodging_geocode_candidates
from china_trip_weaver.clock import FixedClock
from china_trip_weaver.mobility import MobilityBackend
from china_trip_weaver.providers.base import ProviderNetworkError
class NetworkFailure:
    def __init__(self): self.calls = 0
    def execute(self, provider, request):
        self.calls += 1
        assert provider == 'amap' and request.capability == 'geocode'
        raise ProviderNetworkError('synthetic lodging geocode outage')
transport = NetworkFailure()
result = MobilityBackend('live', credentials(), transport).resolve(
    lodging_geocode_candidates(), FixedClock.from_iso(FIXED_NOW), ('walking',),
)
print(json.dumps({'calls': transport.calls, 'health_status': result.health['status'],
    'lodging_located': 'lodging-bjs-central' in {item.ref_id for item in result.locations},
    'health_reason': result.health['reason'], 'warnings': list(result.warnings)},
    ensure_ascii=False, sort_keys=True, separators=(',', ':')))
PY
```

```text
{"calls":2,"health_reason":"calls=2/80 qps<=2; live_cells=0; locations=1; errors=network; warnings=network","health_status":"degraded","lodging_located":false,"warnings":["network:lodging-bjs-central:geocode_lookup:{\"candidates\":[],\"suggested_names\":[]}"]}
```

### 书 23 已确认但因禁碰文件未修：VariFlight 部分成功掩盖 comfort 网络失败

- 状态：已关闭（书 26，实现提交 `229530fb7e39068d7eb72cbb27ba2442859dfe76`）。最小合成流程是 `VariFlightBackend("auto", configured_credentials, transport).enrich([], [北京→上海 route], clock)`；transport 使用 `tests/fixtures/provider_matrix_mcp_server.py variflight-comfort-network`，search 返回一条航班，随后的 `flightHappinessIndex` 在响应前退出。
- 仓库根实际运行该输入（exit 0）的原始输出：

```text
{"claim_fields":["/depart_at","/price","/status"],"flights":1,"health_reason":"tools=9; business_calls=2; candidates=1; status_claims=1; comfort_claims=0; errors=network","health_status":"ready","warnings":["network:leg-vf-ae710e3412b6:service=XX1001;date=2026-09-10;action=comfort"]}
```

- 判定：reason 与实体 warning 已承认 `network`，但 health 仍为 `ready`；search 航班与 claims 应保留，health 应为 `degraded`。需要改包根 `plugins/china-trip-weaver/src/china_trip_weaver/variflight_enrichment.py` 的 status 聚合，该文件不在书 23 只允许的 `mobility.py`、`planning.py`、`providers/` 范围内。
- 边界处理：曾用于验证根因的 6 行临时改动已精确收回，未绕到 `planning.py` 做补偿，也没有留下失败/skip 测试。允许范围内保留 `test_comfort_network_failure_is_classified_without_partial_output`，只证明 transport + adapter 能正确给出 `network/degraded`；它不关闭本条上层 bug。
- 关闭实现：书 26 只让 status 聚合读取 `errors`；任一 error 均不再 `ready`，且 `contract_mismatch` 仍优先于 `degraded`。search 航班、3 条 claims、warning、mode 与 reason 格式均保持原样。
- 关闭复现命令（仓库根）：`/usr/bin/python3 -m unittest tests.test_variflight_live.VariFlightLiveTests.test_partial_comfort_network_failure_degrades_without_dropping_search_output -v`。该测试真实启动上述合成 MCP，断言 `flights=1`、`claims=3`、原 warning 和 `health_status=degraded`。

### 书 23 交付标记

- 上述 18 个覆盖空格中，书 30 以 12 条上层回归关闭 12 格，书 32 以 6 条上层回归关闭余下 6 格；已确认的 VariFlight comfort 上层 health bug 另由书 26 的 `229530fb7e39068d7eb72cbb27ba2442859dfe76` 关闭。书 23/30/32 都没有用越界代码、skip 或弱断言掩盖。

## 书 22 候选名回填（2026-09-05）

- 本轮新增阻塞：无。

## 0.5.1 本机发布（2026-09-05）

- 本轮新增阻塞：无。既有开放事项保持原状，本次没有借发布扩大产品行为或修改其结论。

## 书 31 任务 0：版本 grep 被 repo-local npm cache 污染（2026-09-05）

- 状态：阻塞；已按任务硬规则停止，未进入 README、demo、版本同步或真实安装。
- 指定的 `grep -rn "0\.5\.1" ...` 预期恰好 10 行，实际 exit 0 且返回 25 行。
- 预期的 10 行版本面仍完整存在；多出的 15 行全部位于两个 repo-local 路径：`.npm-cache/_npx/a102998d90773fbe/node_modules/` 与 `.npm-cache/_npx/b9180bb7930b46b7/node_modules/`。
- 全量测试、secret scan 与 stale 安装复现均符合基线；完整原始输出已写入 `PROGRESS.md` 的“书 31”小节。
- 本轮没有删除这两个缓存树，也没有用额外 grep 排除规则绕过“恰好 10 行”门禁；需先由领导确认清理/基线处置后再重启任务 0。
- **领导裁决（2026-09-05，已关闭）**：停得对，是任务书给的命令有缺陷，不是执行侧的问题。`.npm-cache/` 早已被 `.gitignore` 第 3 行挡住、git 跟踪 0 个文件，但 `grep -r` 不认 `.gitignore`，会扫进那 428MB 第三方包，命中的 `0.5.1` 全是无关 npm 包的版本号。该目录的内容随 `npx` 何时拉起哪个服务商而变，所以那条命令的行数本来就不稳定——管理者写书时在自己机器上跑出 10 行，纯属当时缓存里恰好没有匹配。
- 修正：版本面的正确定义是**仓库跟踪的文件**，命令改用 `git grep -n "0\.5\.1" -- '*.json' '*.py' '*.md' '*.sh' | grep -v "PROGRESS.md\|BLOCKED.md"`，它只搜 git 跟踪的文件，天然免疫任何 ignored 缓存。实测恰好 10 行，与原定版本面逐行一致。修订后的任务书已重新下发。

## 书 25 歧义判定死角（2026-09-05）

- 本轮新增阻塞：无。两个明确死角已由合成离线夹具复现并修复；前缀与不同地点仍保持人工判定。

## 书 36 仓库瘦身：范围内认定超出本轮、留待专门一轮的四项（2026-09-08，待裁决）

书 36（PROGRESS 归档、删测试专用代码、版本号单源、测试不再污染工作树）执行前
由任务书作者判断以下四项行为不变但改动面大，划出本轮界限之外，本条只记录
实测事实供下一轮裁决，本轮未做任何相关改动。

- **三个 `*_home_shim.cjs` 待合并**：确认存在
  `plugins/china-trip-weaver/src/china_trip_weaver/providers/` 下的
  `flyai_home_shim.cjs`、`rail_home_shim.cjs`、`variflight_home_shim.cjs`
  三个文件，未逐行比对差异面，留给专门一轮判断能否合并为一个带参数的模板。
- **`.npm-cache`/`.tmp` 清理或迁移**：实测大小与任务书的"两处各约 500 MB"
  不完全一致——`.npm-cache/` 428 MB，`.tmp/` 76 MB（`.tmp/` 下是
  `doctor-flyai`、`doctor-variflight`、`flyai-runtime`、`rail-runtime`、
  `variflight-runtime` 五个运行期临时目录，均在 `.gitignore` 内，git 不跟踪
  任何一个文件）。体量真实但两处并不对等，处置方式（删、迁出仓库、还是保留
  但加体积告警）留给专门一轮。
- **`cli.py` 的 `main` 函数拆分**：实测精确为 706 行（`plugins/china-trip-
  weaver/src/china_trip_weaver/cli.py:329-1034`，文件总长 1276 行），占全文件
  过半，是本轮认定"改动面大、行为易变"因而不做的最主要一项。
- **`docs/design` 重复文件与本机路径清理**：本条实测**没有复现**——
  `grep -rlE "/Users/[a-zA-Z]+|/home/[a-zA-Z]+"  docs/design/` 与按内容
  哈希查重均为 0 命中；`docs/design/` 35 个文件里未发现本机路径或字节级重复
  文件。`CLAUDE.md` 描述的"含本机路径与第三方文档拷贝"精确指向仓库根**顶层**
  的 `design/`（未纳入 git、由根 `.gitignore` 挡住的阶段一原件），与仓库内
  `docs/design/`（脱敏后现役副本）是两个不同目录。任务书这条按顶层 `design/`
  转述，本轮予以更正记录；顶层 `design/` 既不在 git 里也不在本轮"源码目录"
  定义内，仍然超出本轮改动范围，留给专门一轮确认是否需要清理及如何清理。

### 更正（书 B，2026-09-08）：上面这条「没有复现」是错的

书 36 判定"docs/design 重复文件与本机路径清理没有复现"，错在两处：一，它的
grep 模式 `/Users/[a-zA-Z]+|/home/[a-zA-Z]+` 只找字面量 `/Users/`、`/home/`
前缀的绝对路径，而当时 `00-README.md`、`03-trip-model.md` 里的真实内容是
`~/miniconda3/bin/python3 ...`（`~` 缩写形式，不含 `/Users/` 或 `/home/`
子串），这条正则结构上就搜不到 `~` 开头的路径，与用户名本身无关；二，它的
查重脚本只在 `docs/design/` 内部两两比较，没有把 `plugins/`、
`tests/fixtures` 也纳入比较范围，而 7 处字节重复恰恰是跨这三个目录的。书 B
重新实测：`git grep -nE
'(^|[^/])design/schema/|miniconda|/Users/kangyishuai' -- 'docs/design/*.md'`
命中 13 行（`00-README.md`、`03-trip-model.md` 各有几处 `~/miniconda3/...`
与裸 `design/schema/...` 路径）；按内容哈希把 `docs/design/` 与全仓库一起查
重，`docs/design/schema/` 下 7 个文件与 `plugins/china-trip-weaver/schema/`、
`tests/fixtures/trips/schema/` 字节相同，构成 10 对重复。这 13 行与 10 对
均已在本书任务 1 清零：7 个字节重复文件已删，校验器与两处文档的命令改指向
`plugins/`、`tests/fixtures` 的真身，`docs/design/*.md` 里不再出现
`design/schema/`、`miniconda`、`/Users/kangyishuai`。

## 书 C：cli.py 的 main/_parser 拆分（2026-09-08，无）

本轮（`main` 706 行拆成分发表 + 13 组 `_cmd_*`，`_parser` 235 行拆成 14 个
`_add_*_parser`）没有遇到需要裁决的越界或含糊之处：界限（只改
`cli.py`/`PROGRESS.md`/`BLOCKED.md`）与验收口径（金样字节相同、pyflakes
0、507 测试 OK、`main`/`_parser`/`_probe_layers`/`_doctor_probe_report` 四个
名字与签名不变）全程没有冲突。任务书标注为「建议」而非硬性要求的一项——把 6
处重复的 `repo_root = Path(__file__).resolve().parents[4]` 合并成
`_repo_root()`——已采纳并执行，不算待裁决，取舍记录见 `PROGRESS.md` 本轮
小节。

## 书：`replan` 支持 `refresh` 事件（2026-09-10，无）

本轮（main 直改，三书并行之一）没有遇到需要停下来问人、必须跳过的越界或
含糊之处。唯一的事实出入（任务书把 `replan.py` 路径写成
`src/china_trip_weaver/replan.py`，实际是 `plugins/china-trip-weaver/src/
china_trip_weaver/replan.py`）无歧义、按实际路径处理，不算待裁决。若干任务
书未点名的实现细节（`refresh_not_rail` 错误码命名、`provider_health`
`reason` 文案自撰、顶层 `mode` 只上调不下调、日程槽位 `claim_ids` 同步、
旧 claim 不删、CLI 循环测试从 glob 改显式名单）均按自身判断处理并记录取舍
理由，见 `PROGRESS.md` 本轮小节，均不影响硬指标或既有断言力度，不算待
裁决。

## 书 A2：journey extract/assemble（2026-09-10，分支 journey-assemble）

无。任务书自身已经替可能有分歧的两点拍板（拼装只认左段自己已选的边界夜住
宿、缺账本 Trip 照拼不补账本），任务 0 核对的现状与任务书描述完全一致
（唯一偏差是 `expected_segment_days` 实际嵌套在
`journey["segmentation"]["expected_segment_days"]` 而非顶层，只是任务书写
得粗略，不影响验收，已在 `PROGRESS.md` 任务 0 小节记录），三个任务与两条
硬指标均一次性达标，过程中没有遇到需要向管理者请示的越界、含糊或验收口径
冲突。

## 书 D：AnySearch 真实合同（2026-09-10，分支 anysearch-contract）

一条记录，不阻塞交付，按「跳过做别的，继续」处理：

- **验收命令 `git diff main --stat -- tests/fixtures/providers
  ':!*/anysearch/*'` 按任务书原样跑不为空**：实际输出只有一个文件——
  `tests/fixtures/providers/manifest.json`（28 行，8 处新增/20 处删除）。
  原因是这份 manifest 是 `scripts/build_provider_fixtures.py` 对**全部**
  provider 一次性生成的合并清单（`fixture_count` 字段 + 每份夹具的
  `path`/`sha256`），不属于任何单一 provider 目录，因此排除模式
  `':!*/anysearch/*'`（只排除路径里含 `anysearch` 的文件）覆盖不到它。
  只要 anysearch 的夹具数量从 10 份（任务书列出的 7 份「合同真」用例之外，
  旧代码还多出 `auto_register`/`usage`/`payment_required` 三个旧形状专属
  用例）收敛到任务书要求的 7 份，`fixture_count`（79→76）与文件清单/哈希
  就必然变化，这是生成器正确性的直接体现，不是手改了其他 provider 的夹具。
  已逐项核实这条差异**只**由 anysearch 引起：`git diff main -- tests/
  fixtures/providers/manifest.json` 里改动的 8 处 `sha256` 全部对应
  anysearch 的 7 个新条目 + 被删的 3 个旧条目，`fixture_count: 79→76`；
  `host_web`/`rail12306`/`flyai`/`amap`/`variflight` 五个 provider 在
  manifest 里的条目哈希逐一比对，与改动前完全相同（`git status --short --
  tests/fixtures` 只列出 `anysearch/*.json` 七个文件 + `manifest.json`
  一个文件，没有任何其他 provider 目录下的文件出现)。判断：这条验收命令
  本身没有预见到 manifest.json 与单个 provider 夹具数量变化之间的耦合，
  按任务书「让步顺序」（合同真实 > 做得全）与「跳过做别的，继续」处理，
  未回退 manifest.json（回退会导致 `test_manifest_hashes_and_file_set_
  are_exact` 断言真实文件集与虚假旧哈希不符，直接把已经全绿的测试改红，
  代价明显更大）。全量测试、`git diff main --stat` 对
  `schema`/`credentials.py`/`cli.py`/`tests` 删测试行的其余三条硬性验收
  命令均按字面通过，见 `PROGRESS.md` 本书「最终门」小节的实际输出。

## 书：`ctw candidates import` 批量导入（2026-09-10，worktree `.tmp/wt-c` 分支 `candidates-import`）

无需要停工请示领导的裁决项；以下几处任务书留白/含糊之处已按自身判断处理，
均不影响硬指标或既有断言力度，完整取舍与实测证据见 `PROGRESS.md` 本书
小节，此处只列结论：

1. 任务书路径写 `src/china_trip_weaver/candidates.py`，实际是
   `plugins/china-trip-weaver/src/china_trip_weaver/candidates.py`——与
   `replan.py`/`journey.py` 此前的同类出入（已有先例判过不算待裁决）
   同款处理，按实际路径改。
2. `CANDIDATES_IMPORT_COMPLETE pois=N lodgings=M` 的 N/M 语义任务书未
   点名，判为「本批次新增计数」而非「文件累计总数」，因为对用户更有
   信息量、也更贴近现有 `CANDIDATE_POI_ADDED`/`CANDIDATE_LODGING_ADDED`
   逐条打印一次新增的既有风格。
3. `item=N` 的编号任务书未点名 0-based 还是 1-based，判为 1-based（与
   人类清单描述"第几条"的直觉一致），已在 fixture 与测试里实测验证。
4. 反向验证一节，任务书写"用 `git stash push -u -m import-check` 掉
   candidates.py 改动 → 新测试红 → 恢复 → 绿"，但 candidates.py 的任务 1
   改动此刻已单独提交（遵守"每个任务一次 `git commit`"的规矩），不是
   未提交状态，无法照字面顺序执行（`stash push` 只能保存未提交差异，
   且 push 后工作区必然回到 HEAD，与"push 后应处于失败态"字面冲突）。
   采用等价且合乎 git 语义的操作序列（先用 `git show <分支起点>:文件`
   覆盖工作区制造未提交差异、`stash push` 限定 pathspec 只保存这一个
   文件、`stash apply <SHA>` 触发红、`checkout HEAD --` 恢复、核对
   `stash@{0}` 等于记录的 SHA 后 `stash drop` 清理），push/apply/drop
   三个动作都用到，且全程只影响 candidates.py 一个文件的 pathspec，
   任务 2 其余未提交改动（测试、文档、fixture）未受干扰。终端记录见
   `PROGRESS.md`。
5. 写验收记录时发现 `main` 已被并行的「渲染页可读性」书推进（新增/删除
   了 `render/`、`tests/test_journey.py`、`tests/test_renderer.py` 等与
   本书无关的内容）。此刻字面执行任务书写的 `git diff main ...` 会把
   那些改动混进比对结果。按 `journey-replace`/`docs-drift` 等书已有的
   同款先例（分支分出后 main 前进，验收改用 `git merge-base HEAD main`
   核实的真实分出点），本书统一改用真实分出点 `1f1e966` 做比对，两条
   规矩检查（无删测试函数、schema/demo 零改动）均干净通过。

## 书 D2：`ctw research` 命令 + doctor 探针 + planning 健康行（2026-09-10，main 直改）

一条记录，不阻塞交付，按「跳过做别的，继续」处理（本条其实已按判断解决，
非真正卡住，记录供领导复核）：

- **`tests/test_providers.py` 不在「只允许改」名单，但任务 2 的夹具改动
  必然触发它**：该文件有模块级循环，对 `tests/fixtures/providers/*/*.json`
  逐文件自动生成测试方法（`test_fixture_<provider>_<case>`），无法通过
  夹具自身字段开关跳过。新增 `anysearch/probe_success.json`/
  `probe_401.json` 后：① `test_manifest_hashes_and_file_set_are_exact`
  硬编码 `self.assertEqual(76, manifest["fixture_count"])`，与新增后的
  真实值 78 不符；② 自动生成的 `test_fixture_anysearch_probe_success`
  起初按 `fixture()` 默认值把 `expected.error_class` 留空、`health_status`
  留 `ready`，但 `probe_success.json` 的响应体是 `get_sub_domains` 风格的
  纯文本列表（不是「search」工具专属的「## Search Results」markdown），
  实测把它喂给真实的 `AnySearchAdapter().query()`（`run_fixture()` 对每份
  夹具都这么跑）会如实产生 `contract_mismatch`（已用 Python 直接调用该
  adapter 验证，非猜测，见 `PROGRESS.md` 本书任务 2 小节的实测输出）。
  判断：按「仓库瘦身第二轮」那次 `test_packaging.py`/`test_contracts.py`
  的同款先例（断言真实状态，不放宽逻辑、不 mock、不删用例）处理——把
  `76` 改成 `78`，把 `probe_success.json` 生成器调用里的 `expected`
  字段改成实测的真实值（`health="contract_mismatch",
  error_class="contract_mismatch"`）。这两处改动都不影响硬指标一（doctor
  探针本身 `cli._probe_anysearch` 从不调用 `normalize()`，只读
  `envelope.status_code`，不受这份夹具「跑完整 adapter 会 contract_mismatch」
  这一事实影响，`tests/test_anysearch.py` 的
  `AnySearchDoctorProbeTests`/`AnySearchProbeFixtureTests` 单独覆盖了探针
  自己的正确行为）。反向验证（终端记录）：改回 76 → 该测试
  `AssertionError: 76 != 78`（红）→ 改回 78 → 绿；把
  `probe_success.json` 的 `expected.health_status`/`error_class` 手动改回
  默认值（`ready`/`null`）→ 自动生成测试 `AssertionError: 'ready' !=
  'contract_mismatch'`（红）→ 用生成器重新生成、与改动前的备份逐字节
  相同 → 绿。`git diff df5712e -- tests | grep -E '^-\s*def test_'` 0 行
  （未删除任何测试函数，只改了一处断言数值、生成器新增内容触发的两个
  自动测试沿用生成器逻辑本身，非手写增减）。

- **`tests/test_skills.py` 同样不在名单，任务 3 改 SKILL.md 第 12 行的
  逐字文案后触发**：
  `test_destination_research_contract_uses_host_first_then_anysearch_fallback`
  硬编码 `fallback = "fall back to AnySearch with an already configured
  key"` 逐字匹配旧文案（`self.assertIn(fallback, body)`）。任务书明确要求
  把这一行改成「用 `ctw research --city --query` 取候选，把 health 报给
  父 Skill」，字面文案变化后旧断言必然对不上。判断同上——按「仓库瘦身
  第二轮」先例就地把硬编码字面量改成新文案对应子串，不改断言的逻辑与力度
  （仍是三段顺序 `assertIn` + `index` 先后关系判断），不删用例。反向验证：
  改回旧字面量 → 该测试报出完整新 SKILL.md 正文证明确实改了（红）→ 改回
  新字面量 → 绿。终端记录见 `PROGRESS.md` 本书任务 3 小节。

## 书 G：浏览器 QA 握手加固（2026-09-10，worktree `.tmp/wt-g` 分支 `qa-handshake`）

无需要停工请示领导的裁决项。以下两点已按自身判断处理，均不影响硬指标，
完整实测见 `PROGRESS.md` 本书小节：

1. 任务书通篇称呼要打桩/加固的类为 `Browser`，仓库内真实类名是
   `ChromePipe`——`__init__`/`command`/`run_qa`/首条 `Target.createTarget`/
   `validate_report` 检查字典的行号（71/107/202/214/173）与方法签名
   （`close()`/`command()`）全部与任务书描述精确吻合，只有类名字面不同。
   判为任务书的描述性用词、不是要求真的把类改名为 `Browser`（改名是
   任务书未要求的额外改动，且会牵连测试里对该名字的引用），按真实类名
   `ChromePipe` 实现，任务 2 的打桩测试同样打在 `ChromePipe` 上。
2. 顺手发现 `tests/test_journey.py:1430`
   （`test_checked_in_sixteen_day_demo_passes_offline_browser_qa`）也用
   `subprocess.run([...qa_renderer_browser.py...], timeout=60)` 调用同一
   脚本。本书加固后握手最坏耗时约为原来的 6 倍（10 秒→30 秒握手超时 ×
   最多 2 次尝试），若某次 CI 运行恰好触发一次重启，这个测试自身的
   `timeout=60` 有可能先于脚本内部逻辑触发 `subprocess.TimeoutExpired`，
   把"握手重试后成功"变成"外层子进程超时失败"，与本书要消除 CI 抖动的
   目标背道而驰。`tests/test_journey.py` 不在本书「只允许改」白名单内
   （白名单只列了 `tests/test_renderer.py`、`tests/test_keyless_e2e.py`
   第 1154 行附近那一处），未改动，只记录供领导定夺是否需要单独一本书
   把这个 `timeout=60` 也放宽（建议同样改成 150，与本书对
   `test_keyless_e2e.py` 的改法一致）。
3. （环境笔记，非代码判断）`git push -u origin qa-handshake` 首次直接
   执行时连续失败：本机 `HTTP_PROXY`/`HTTPS_PROXY` 指向的本地代理
   （`127.0.0.1:7897`，进程本身在监听）到 `github.com:443` 的 TLS 隧道
   报 `SSL_ERROR_SYSCALL`，13 次自动重试（4 分钟窗口）均未恢复；
   `curl --noproxy '*' https://github.com` 直连返回 200，证明问题在代理
   到 GitHub 这条链路本身，不在网络整体或仓库状态。改用
   `env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy git
   push ...` 绕开代理直连后一次成功。记录供以后任何需要 `git push`/
   `gh` 访问 GitHub 的任务书参考：这台机器上遇到同款 `SSL_ERROR_SYSCALL`
   时，先用 `curl --noproxy '*' https://github.com` 探一次直连，通的话
   同样用 `env -u HTTP_PROXY -u HTTPS_PROXY ...` 绕开代理即可，不必假设
   是网络整体故障。

## 书 H：租车与轮渡 ADR（2026-09-10，worktree `.tmp/wt-h` 分支 `rental-ferry-adr`）

无。任务 0 的全部 file:line 断言逐条核对均吻合，任务 1/2 撰写 ADR 过程中
自查出的两处引用错误（`trip.schema.json` 行号引到了 `group_refs` 数组而非
完整属性列表；`journey_html.py` 一处 deadline 来源函数引成了
`_journey_trace_deadline`，实际主逻辑在 `journey_booking_checklist`）均已
在撰写阶段自行发现并改正，未留待裁决项，详见 `PROGRESS.md` 本书任务 1/2
小节的记录。

## 书 F2：replan suspend 事件（2026-09-10，worktree `.tmp/wt-f2` 分支 `replan-suspend`）

一处判断，非阻塞：任务书「界限」明确只许 `tests/test_replan.py` 新增
`def test_` 与改 CLI 循环夹具元组/计数这两类改动，但把 `"suspend"` 加进
`VALID_EVENT_TYPES`（任务 0 现状小节已指出这行要改）后，`test_cli_kind_
field_reports_type_contract` 里对 `event_type` 报错文案的 `assertEqual`
精确匹配（`"closure, weather, delay, user_delete, refresh"`）必然与运行时
真实文案（多一个 `, suspend`）不符，不改这一行该测试必红，直接违反硬指标二
「全量 OK」。这不是放宽或绕过断言——断言值本身就该等于当前合法事件类型枚举
拼出的文案，`suspend` 成为合法类型后旧字符串就是过期的，而不是被我改松了。
已按最小改动处理：只把这一行的期望字符串追加 `, suspend`，改动计入任务 2
的 commit（而不是任务 1，因为只有 `suspend` 真正进入枚举后这个新字符串才是
「正确」而非巧合），未触碰同一测试里对 CLI `--help` 静态文案的另一条断言
（`cli.py` 该处是字面量、未读 `VALID_EVENT_TYPES`，只读未改 `cli.py` 已
确认）。留给领导复核：是否认可这一行例外，或希望改用其他方式（例如把这条
测试整体移出白名单豁免、或事后由领导亲自改）。

另记一条环境观察、非本书代码问题：验收期间发现本机 `main` 分支被另一个并行
会话（「预订清单按开售日」书）在本书开工后推进了一个提交，往
`tests/test_journey.py` 加了新测试，导致 `git diff main -- tests | grep
'^-\s*def test_'` 会把那些新增测试误判成本分支「删除」——只是 `main` 作为
比较基准提前移动的假象。改用本分支真实分叉点 `05f1056`（`git merge-base
main HEAD` 核实）重跑同组命令，全部空输出，证据见 `PROGRESS.md` 本书任务 2
小节。

## 书 S1：12306 站点跨城/后缀（2026-09-10，worktree `.tmp/wt-s1` 分支 `station-cross-city`）

任务 1「后缀重试」，「我替领导拍的板」写的是「返回的 `query` 改为剥后缀后
的名字」——按此实现后，实网 `ctw rail --to 武夷山市` 返回
`contract_mismatch`，不是任务书基线记录的 `station_resolution_no_results`。
排查发现 `providers/rail12306.py:270`（只读文件，不在本书「只允许改」
白名单内）有一条既有硬校验：
```python
if query != request.parameters.get(parameter_name):
    raise ContractMismatch("12306 station resolution query does not match the request")
```
`query` 必须逐字等于**原始请求参数**（`from_name`/`to_name`，即用户敲的
「武夷山市」），不允许偏离——这是一条我不能碰、且验证下来是真实生产路径
上会触发的硬约束，不是猜测分歧。任务书自己也把「query 改名」标成
「（猜的）」，与此处的硬约束直接冲突。
判断：功能目标是「武夷山市」能查到候选站（`legs=10`），不是「query 字段
必须显示剥后缀后的名字」——后者只是任务书给的一种实现细节猜想。按目标
优先，保留 `query` 为原始请求名（"武夷山市"），只让**候选站点列表**换成
剥后缀重试后解析到的结果；不改 `rail12306.py`。已把
`test_rail_station_fallback.py` 里新增的
`test_suffixed_city_empty_after_three_layers_retries_stripped_name_and_resolves`
断言同步改为 `query == "武夷山市"`（不是 "武夷山"）。改后实网
`--to 武夷山市` 返回 `legs=10`（见 PROGRESS.md 本书任务 1 小节实测输出），
硬指标一达成。

## 书「优先事项卡片按 deadline 种类措辞」任务 1：5 个新测试里 2 个天生绿，非「全红」（2026-09-11，判断，非阻塞）

任务书任务 1 列了 5 条断言（presale_open 双日期、check_in 措辞、declared
措辞、页面不泄漏 "presale window is"、item_id 前后不变），验收写「新测试此时
全红」。实测 5 个新 `def test_` 里 3 个真红（`KeyError: 'deadline_kind'`，
证明确实在测未实现的新字段/新分支）、2 个天生绿——「页面不泄漏 reason 原文」
与「item_id 不变」这两条按其定义本来就该在改动前后都成立（前者是防止我在
实现新措辞时手滑把 `item["reason"]` 渲染出来的回归哨兵，`reason` 字段现在
就没被 `_checklist_item_html`/`_trace_attributes` 引用过，grep demo html 确认
0 命中；后者是防止我改坏 `_journey_action_item` 的 identity 计算的回归哨兵，
改动前 identity 计算完全没碰过，自然相等）。
判断：不删这两条、不放宽断言凑「全红」的字面——任务书原文明确要求
这 5 条断言都要有对应测试，删掉两条等于减少任务书自己要求的覆盖面，属于更
糟的选择；且"全红"的精神是防止我写出对新旧代码都通过的空测试，这两条是
`KeyError`/字段缺失以外的另一类必要保障（防止实现阶段引入新泄漏或改坏
identity），不是偷懒判定。5 个测试的完整红/绿输出见 `PROGRESS.md` 本书任务 1
小节。

## 书「拆 validate_journey_html」任务 0：文件总行数与任务书差 1 行（2026-09-11，判断，非阻塞）

任务书写「validate_journey_html.py 共 428 行」，`wc -l` 实测 427 行；3 个
顶层函数的起始行号、各自长度（`validate_journey_html` L26 225 行、
`_validate_trace_nodes` L253 30 行、`_shared_document_issues` L285 143 行）、
JH 码字面量计数（44 个、15 种）、`tests/test_journey.py` 里
`validate_journey_html(` 调用计数（12 处）与 `test_journey_html_rejects_*`
计数（8 个）全部逐字吻合。判断：428→427 的 1 行出入不影响任何硬指标或
拆分方案，大概率是任务书写作时的计数笔误（例如文件末尾换行符的计入方式
不同），不是「对不上」的实质性分歧，不停工。

## 书 Y1「拆 journey._merge_segment_trips」任务 0：文件总行数与任务书差 1 行（2026-09-11，判断，非阻塞）

任务书写「journey.py 共 2574 行」，`wc -l` 实测 2573 行（文件确以换行符
结尾，非漏算末行）。与「拆 validate_journey_html」任务 0 的 428→427 同一类
情形——真正约束本书范围的三个数字全部逐字吻合：71 个顶层函数、
`_merge_segment_trips` 行号 L859-1071、长度 213 行（AST 命令实测
`[(859, 1071, 213, '_merge_segment_trips')]`，另两个 `_merge*` 开头的既有
函数 `_merged_identifier`14 行、`_merge_provider_health`56 行不在本书范围）；
唯一调用点 journey.py:279（`trip_document = _merge_segment_trips(atomic_trips,
segment)`），确在 `plan_journey`（起始行 207）函数体内。判断：1 行出入不
影响任何硬指标或拆分方案，不停工。

## 书「租车与轮渡候选设计 ADR-0017」（2026-09-11，worktree `.tmp/wt-y3` 分支 `transport-candidates-adr`）：无待裁决项

任务 0/1/2 全部按任务书字面执行，全程无需停工的分叉。任务书列出的全部
file:line 逐条核对通过，随机抽查的 3 条（`render/html.py:57-59`、
`candidates.py:1269`、`replan.py:21`）复核依旧吻合。Decision 选了「暂不做」
而非 A/B 之一，但这是任务书明确列出的第三个合格选项（"『暂不做，继续手写
Trip』也是合格答案，但要给证据"），不是回避裁决——ADR 正文列了 5 条独立
可复现证据支持这个选择，并在 Consequences 给出了「如果以后要做，选 B 不
选 A」的理由与验收命令草案，供领导日后裁决是否立项。硬指标一、二均已实测
通过，见 PROGRESS.md 本书小节。

## 书 Z2「文档漂移清零第二轮 docs-drift-2」（2026-09-11，worktree `.tmp/wt-z2` 分支 `docs-drift-2`）：无待裁决项，但记一条验收命令的字面矛盾

任务 0/1/2 全部按任务书字面执行，未发现任何「怀疑是代码错了」的情形——
盘清的 15 条漂移全部是「代码有、文档没有」，没有一条是「文档说的与代码
不符」，因此没有触发「记 BLOCKED 不改代码」这条规则。

唯一记录在案的是任务书「界限」段落与自身「硬指标二」验收命令之间的字面
矛盾，不是我发现的代码问题，而是任务书本身的一处细节：「界限」明确把
`plugins/china-trip-weaver/references/provider-contracts.md` 列为允许改的
文件之一（任务书原话："只允许改：…provider-contracts.md…"），但硬指标二
要求 `git diff main --stat -- plugins tests` 必须为空——这条 pathspec 用
`plugins` 前缀会把 provider-contracts.md 自身的改动也纳入统计，与"允许改
它"字面上互斥。按"文档不撒谎"高于"字面通过某条验收命令"的让步顺序，我
选择照做任务书明确要求的 provider-contracts.md 改动（AMap 段列全四个能力
与 `types`/`city_limit` 两个可选参数），并在 PROGRESS.md 里同时贴出两条
证据：`git diff main --stat -- plugins tests` 的真实非空结果（只有
provider-contracts.md 一个文件），以及改用真正的只读边界
`plugins/china-trip-weaver/src plugins/china-trip-weaver/skills
plugins/china-trip-weaver/schema tests` 作 pathspec 后结果为空——证明
`src`/`skills`/`schema`/`tests` 这些真正只读的目录确实一字未动，只是
硬指标二给的检查命令本身没排除掉它自己在"界限"里明确放行的那一个文件。
这不是我猜代码错了，是任务书这两句话字面上互斥，按更具体、更明确的
"界限"白名单执行，供领导确认这个判断是否合理。

## 书 Z3「真实行程火车票刷新实战」任务 0：日期未达门槛，止步（2026-09-11，非裁决）

任务书原文：「本书只能在 2026-09-12（含）之后跑，之前跑必然
outside_presale_window」；任务 0 第一步：「先 `date` 确认已是 2026-09-12
或之后，不是就停，把日期写进 BLOCKED.md 交卷」。本轮实测：

```
$ date
Fri Sep 11 15:22:28 CST 2026
```

2026-09-11 < 2026-09-12，未达门槛，按任务书字面止步于任务 0 第一步。
以下步骤均未执行：`ctw doctor`、`ctw rail --date 2026-09-26 --from 福州
--to 武夷山`、任务 1（刷新第一段）、任务 2（记录选中车次/账本变化等）。
真实行程目录 `fujian-2026-09-25-to-10-10/` 全程未被读写，原文件字节
未受影响。

不是待领导裁决的分叉——任务书本身把「日期不足→停」列为合格的止步路径，
不属于「拿不准」。记录在此仅为下次续跑提供依据：2026-09-12（含）之后
重新进入本任务时，直接复用已建好并推送的 worktree `.tmp/wt-z3`（分支
`refresh-drill`），从任务 0 第二步（`ctw doctor`）继续即可。

## 书 AA1「拆 variflight_enrichment.enrich」（2026-09-11，main 直接干）：无待裁决项

任务 0/1/2 全部按任务书字面执行，未发现任何 bug 或需要改逻辑之处——
`enrich` 原有 167 行行为在拆分前后完全保留，30 组合快照（见 PROGRESS.md
本书小节）逐字节相同，未触发「只拆不改，发现问题记 BLOCKED、代码保持
原样」这条规则。

唯一值得记录的判断：任务书「让步顺序」允许在拆得清楚与拆得彻底之间取舍，
本书选择不新增测试（与先例书「拆 validate_trip.semantic_issues」不同，
那本书发现全仓没有一处精确比对三元组、判断为真实覆盖缺口才补测试）。
本书检查后确认现有 10 个 `test_variflight_live` 用例 + 全仓所有不显式传
`variflight_backend` 的 `plan_trip` 调用（隐式走 `VariFlightBackend.
from_spec("off", ...)` 分支）已覆盖拆分触及的每一条分支，`git grep`
`'VariFlightBackend("off"\|VariFlightBackend\.from_spec("off"'` 在
`tests/` 下 0 命中，确认 off 分支的测试覆盖确实是"隐式通过 e2e"而非
显式断言，但该分支从未被拆分改动过（`_early_exit_result` 里 off 分支
与原代码逐字节一致），且 30 组合快照已包含 6 组 off 模式记录并连跑两次
逐字节相同，判断不构成需要补测试的覆盖缺口。硬指标不要求新增测试，
`tests/test_variflight_live.py` 本轮零改动。止损轮次未触发。

## 书 Z3「真实行程火车票刷新实战」任务 0：同日第二次派发，日期仍未达门槛，止步（2026-09-11 16:22，非裁决）

同一自然日内本任务书被第二次派发（上一次的 worktree/分支已被清理，按
「全局」重新建）。本轮实测：

```
$ date
Fri Sep 11 16:22:19 CST 2026
```

2026-09-11 < 2026-09-12，未达门槛，按任务书字面止步于任务 0 第一步。
`ctw doctor`、`ctw rail`、任务 1、任务 2 均未执行；真实行程目录
`fujian-2026-09-25-to-10-10/` 全程只读，原文件字节未受影响（基线哈希见
PROGRESS.md 本节）。

不是待领导裁决的分叉，理由同上条。唯一新增信息：这是同一自然日内的
第二次空跑，供管理者判断是否需要调整派发时机——建议 2026-09-12（含）
之后再派发本书。

## 书「地图与图片 ADR-0018」（2026-09-11，worktree `.tmp/wt-ac1` 分支 `adr-map-images`）：无待裁决项

任务 0/1/2 全部按任务书字面执行，全程无需停工的分叉。任务书「现状与
任务 0」段列出的全部 file:line/条款逐一核对通过，无出入。自查阶段发现
并当场修正了两处引用错误（均在写作过程中自己发现，非任务书本身出入）：
研究决策 17 号的路径写成了 `docs/design/04-design-insights.md`，实际
是 `docs/research/04-design-insights.md:87`；`render/html.py:580` 写成
`_location_section` 定义行，实际 580 是空行、581 才是 `def` 所在行。
另有一处措辞问题：草稿曾把验收命令写成引用不存在的
`tests/test_journey_html.py`，改为真实存在的 `tests/test_journey.py`
（`render_journey`/`validate_journey_html` 的全部既有测试都在这一个
文件里，含 `JourneyContinuityTests` 类，L734）。三处均已在 ADR 定稿
前修正，未进入最终提交版本。

Decision 对四个问题给了「不做/不做/不做/做」，不是四个都"暂不做"的
回避答案——第 4 条（Journey 页位置示意）给了肯定答案与最小实现方案，
因为它不是新功能审批，而是把已经合规、已经实现的 `_location_svg`
（07-renderer.md §2 第 8 条既定合同）补齐到一个尚未调用它的页面，
证据链和 ADR-0017 先例的"暂不做"一样扎实，只是这次证据指向"可以做
且成本极低"而非"不做"。硬指标一、二均已实测通过，见 PROGRESS.md
本书小节。

## 书 AC2「第二价源 ADR-0019」（2026-09-11，worktree `.tmp/wt-ac2` 分支 `adr-second-price`，第十三波三份并行书之一）：无待裁决项

任务 0/1/2 全部按任务书字面执行，全程无需停工的分叉。任务书列出的全部
file:line（`/price` claim 10 处、04-providers.md L105/L111、
trip.schema.json L196-222/L736、evidence.py L1/L14、render/html.py
`_price`+evidence 区）逐条核对通过；写进 ADR 正文的全部 55 条唯一
file:line 引用事后又做了一轮独立提取+抽查复核，无漂移（过程见
PROGRESS.md 本书任务 2 小节）。

Decision 对火车票/机票/住宿/门票四类分别给出「不做/做/做（排后）/不做」
——不是「只有航班需要，其余不做」这种单一结论，是四类各自独立证据支撑
的判断，满足任务书「四类价格全覆盖」的让步顺序。唯一算得上分叉的一点：
任务书建议的验证命令「用...离线跑 `ctw plan --offline-fixture` 看
claims」本身在 CLI 层不可执行——`cli.py:914`（及 `journey plan` 同款
校验 `cli.py:1002`）规定 `--offline-fixture` 必须配 `--lodging off`，
两者不能同时出现。这不是任务书出错（`--offline-fixture` 的这条限制原本
就与本书要验证的场景无关，只是恰好都涉及「lodging」），是建议达成同一
验证目的的命令本身不可行——按「建议」条款的让步空间，改用直接调用真实
的 `planning._merge_lodging_candidates` 函数（纯函数、同一份代码、零
mock）做等价离线验证，过程与输出已写进 PROGRESS.md，不影响 Context 与
Decision 的证据强度。

硬指标一、二均已实测通过，见 PROGRESS.md 本书任务 2 小节。

## 书 AC3「真实行程实网复核」疑似代码缺陷（2026-09-11，只诊断不修）

以下 5 条都是本轮福建 16 天真实行程实网复跑（0.15.3，`.tmp/journey-live.json`，
`journey_sha256=44059a3b480827245ef7877b87e4de96dc9daafd9ab62a24e2abf9169e36611d`）
中定位到的疑似代码缺陷，代码与真实数据一行未改，供领导裁决是否要修。

### 1. rail12306/flyai/variflight 的路线查询统一用了地点的展示名而非城市名

`request.json` 的 `meeting_anchor.location` 与 `traveler_groups[].origin`
每个地点对象都同时提供 `name`（展示名，可能含机场名/行程批注文字）和
`city`（干净城市名）——例如本轮 `meeting_anchor.location.name`="福州长乐
国际机场" 而 `.city`="福州"，`traveler_groups[0].origin.name`="昆明（由
个旧于9月24日前置）" 而 `.city`="昆明"。但 `planning.py` 的 `RouteSpec`
（45-50 行）与 5 处消费点全部只读 `.name`、从不读 `.city`：
`planning.py:95-96`（`RailBackend.query` 的 `from_name`/`to_name`）、
`planning.py:1354-1355`（`_resolve_rail` 的 call 日志）、
`planning.py:1595-1596`（12306 dated-deep-link 的 `fs`/`ts` 参数）、
`flyai_inventory.py:192,196`、`variflight_enrichment.py:136-137`
（`CITY_IATA.get(route.from_place["name"])`）。`_route_specs`
（`planning.py:652-658`）把 `item["origin"]`（整个 dict）直接塞进
`RouteSpec.from_place`，没有在这一步换成 `.city`。

复现（真实数据，本轮已产生的结果）：`.tmp/journey-live.json` trip0 的
`unknowns[]` 里两条 `field_path=/transport_legs/N/service_number`：
`ambiguous:leg-rail-fallback-4a6455b157b9:route=city-beijing->airport-fuzhou-changle;date=2026-09-25`
与
`no_results:leg-rail-fallback-59677adb7500:route=city-kunming-prepositioned->airport-fuzhou-changle;date=2026-09-25`；
对应两条 `provider=12306-deep-link` 的 claim，其 `source_url` 解码后
`fs=北京&ts=福州长乐国际机场&date=2026-09-25` 与
`fs=昆明（由个旧于9月24日前置）&ts=福州长乐国际机场&date=2026-09-25`——
后者的 `fs` 参数把括号批注文字也发给了 12306，前者的 `ts` 参数用机场名
查火车站。这两条路线只要涉及 `meeting_anchor` 汇合腿就会触发，与具体
日期无关，不属于开售窗口问题（其余 6 条同 trip 的干净城市名路线都正常
判定为 `outside_presale_window`，只有这两条不是）。

### 2. VariFlightBackend.CITY_IATA 静态表只覆盖 5 个城市

`variflight_enrichment.py:18-24`：

```python
CITY_IATA = {
    "北京": "BJS", "上海": "SHA", "广州": "CAN",
    "深圳": "SZX", "杭州": "HGH",
}
```

本次行程涉及的福州/武夷山/平潭/泉州/厦门/南靖一个都不在表里。
`_enrich_route`（同文件 136-140 行）：`dep_city`/`arr_city` 任一
`None` 就 `errors.append("unsupported_city_code")` 直接 `return`，
从不调用 `adapter.query(...)`。复现：本轮三个 trip 的 variflight health
`reason` 都是 `errors=unsupported_city_code ×N`（N=该 trip 内的航线数）；
`git blame`/`git log -p` 显示这张表从该文件最早的提交起就只有这 5 个
城市，没有随后续版本扩展过，也没有设计文档说明"只覆盖 5 个枢纽
城市"是有意为之。

### 3. doctor --probe 对 variflight 的独立信号：adapter 解析可能跟不上当前响应形状

与第 2 条不同、互相独立的另一个疑似缺陷。`ctw doctor --probe` 对
variflight 的探针（`cli.py:1647-1663`）用真实凭据发起
`dep_city="PEK", arr_city="SHA"` 的真实搜索——这两个是硬编码 IATA 码，
完全不经过 `CITY_IATA`——`_probe_layers`（`cli.py:1705-1724`）判定
`error_class == "contract_mismatch"` 从而 `contract="failed"`（且
`business="not_run"`，因为 contract 先失败）。复现：

```
$ plugins/china-trip-weaver/scripts/ctw doctor --probe
...  "variflight":{"business":"not_run","contract":"failed","credential":"configured","network":"passed"} ...
```

意味着即便把第 2 条的 `CITY_IATA` 补全到覆盖所有城市，北京→上海这类
CITY_IATA 已经支持的枢纽航线，adapter 对 VariFlight 当前真实返回体的
解析可能仍然失败——指向 `providers/variflight.py` 的 normalize 逻辑
没跟上 VariFlight 当前的响应形状，偏服务商变化而非纯本地代码疏漏，但
未读 `providers/variflight.py` 源码逐行定位到具体哪个字段（本轮时间
预算内未展开，留给下一轮或领导裁决是否值得单独立项调查）。

### 4. doctor --probe 对 flyai 只测 lodging 能力，测不到 flight 能力的故障

`cli.py:1544-1579` `_probe_flyai`：固定 `capability="lodging"`（city=
北京，7 天后入住 1 晚），整个探针函数没有任何测试 `capability="flight"`
的分支。复现对照：同一时刻 `ctw doctor --probe` 报
`"flyai":{"business":"passed","contract":"passed",...}` 全绿，但同一
批 journey plan 实测（见第 5 条与 PROGRESS.md 任务 1）flight 能力 7/9
次查询 `contract_mismatch`。这意味着只要 flyai 的 lodging 能力保持健康，
`ctw doctor --probe` 会一直对 flight 能力的真实故障报绿灯，是探针覆盖
缺口，不是"没有故障"。

### 5. FlyAI flight 与 lodging 价格解析严格度不对称（推测，未获得原始响应体确认）

`providers/flyai.py`：`_flight()`（61-111 行）第 72 行
`_price(raw.get("ticketPrice", raw.get("adultPrice")), require_numeric=True)`——
`_price()`（172-203 行）里 `require_numeric=True` 时，价格为
`None`/布尔/无法解析成数字的字符串会直接 `raise ContractMismatch("FlyAI
price lacks numeric context")`。`_lodging()`（113-153 行）第 121-125
行调用同一个 `_price()` 但传 `require_numeric=False`，对同样是
`None`/掩码字符串（`MASKED_PRICE_RE`，如"¥×××"这类）的取值会优雅退化成
`price_type="verify-on-click"`，不抛异常。

复现：按 PROGRESS.md 任务 1 "FlyAI contract_mismatch 定位" 小节的命令
跑出的 `.tmp/lodging-only-progress.ndjson`，7 条
`"capability":"flight","error_class":"contract_mismatch"`、0 条
lodging 相关 degrade；9 次 flight 查询里恰好是全部 7 次省内短途航线失败、
2 次长途干线（昆明/北京→福州）成功。这个"同批查询里 lodging 全过、
flight 系统性失败"的现象，与 `_flight()`/`_lodging()` 价格解析严格度不
对称的假设吻合，但本轮没有拿到 FlyAI 原始响应体——要拿到就得改代码加
调试输出，而本书界限只允许改 PROGRESS.md/BLOCKED.md，所以无法逐字确认
是不是恰好命中这一支——标注为**推测**，供领导判断是否值得在下一轮
任务书里专门加日志字段验证（而非在本书界限内用改代码的方式验证）。

## 书「路线查询改用 city」（2026-09-11，main 直接干）：无待裁决项

任务书要求的 5 处消费者、2 条新测试、既有测试字节不变、分组示例重生成
全部按预期完成，唯一与任务书"猜的"预期不符的一点（分组示例 trip.json/
trip.html 实为零字节差异，而非任务书猜测的"会随之改变"）已在
PROGRESS.md 任务 0/2 记录并给出根因（`success.json` 夹具命中真实车次走
`12306-mcp`，深链用夹具内部解析出的站名而不读 `from_place`，
`_deep_link_leg` 从未触发），不构成需要裁决的分歧。

## 书 AD2「FlyAI 空结果误判」：上条第 5 点的推测已被真实抓取推翻（2026-09-11，判断，非阻塞）

书 AD2 任务 0 用真实 Key 直接抓取福州→武夷山 9/26 的原始 envelope：
`status=1、data is None=True、message 长度=10`，且不含"结果为空/no
result"。这不是价格字段解析问题（`_price()`/`require_numeric` 从未
被调用到——`normalize()` 在进入 `_flight()`/`_price()` 之前就已经因为
`status != 0` 落进 `raise ContractMismatch("FlyAI success envelope
changed")`）。真正原因是空结果判定的关键词白名单过窄：服务商用非
"结果为空/no result"措辞报告的失败/无结果，被当成合同不匹配处理。上条
（第 5 条）"价格解析严格度不对称"的推测就此证伪，仅保留原文作历史
记录，不必再作为待验证假设排期。

## 书 AD2「FlyAI 空结果误判」：顺手发现一处越界的文档漂移，留给下一轮 docs-drift（2026-09-11，非阻塞）

`docs/design/adr/0017-transport-candidates.md:90` 写着
"`tests/test_providers.py:117` separately pins `fixture_count ==
79`"——本书任务 2 把该断言改成了 `80`（新增 flyai `search_failed`
夹具），这处引用现在是错的。该文件不在本书「界限」允许修改的清单内
（只允许改 providers/flyai.py、cli.py 的 `_probe_flyai`、
build_provider_fixtures.py、fixtures、三份指定测试文件、两份 README
的夹具总数、PROGRESS.md、BLOCKED.md），所以本轮未动，留给下一轮
docs-drift 类任务书一并处理。

## 书 AE1「VariFlight 错误对象降级」：无待裁决项，两点非阻塞观察（2026-09-11）

本书两项硬指标均已达成（PROGRESS.md 任务 2 小节有完整证据），没有需要
管理者裁决的分歧。顺手记两点非阻塞观察：

1. 上一条 docs-drift 记录的 `docs/design/adr/0017-transport-candidates.md:90`
   `fixture_count == 79` 引用，本书任务 2 把真实断言值又推进到 `81`
   （现在差两版而不是一版）；该文件仍不在本书「界限」内，继续留给
   docs-drift 类任务书一并处理，不单独处理。
2. `ctw doctor --probe` 在本次执行所用的沙箱环境下，四个 provider 并发
   探测时 variflight 单独报 `network=failed`——根因是这个沙箱的出口网络
   需要透传一个仅顶层 shell 持有的本机代理，子进程本来就拿不到（这是
   `SAFE_PROCESS_ENV` 刻意不传代理变量的隔离设计，不应改），加上四个探针
   并发抢占资源，`_probe_variflight` 硬编码的 `deadline_ms=8000` 在这个
   组合条件下不够用；单独调用同一个 `_probe_variflight()`（不带另外三个
   探针的并发抢占）能在 8 秒内拿到 `contract=passed`，证明判定逻辑本身没
   问题。这只在本沙箱复现，用户真机大概率没有这层代理，不需要改
   `deadline_ms`；但如果管理者在真机验收时看到并发 `doctor --probe` 下
   variflight 也报 network 层失败，值得留意是不是本机网络也在这个边界
   上，而不是直接归因为本书改动有问题。

## 书 AE2「Journey 页 375px 横向溢出」：day-card h3 的「6px」不是断行问题，CSS 治不了（2026-09-11，非阻塞）

真实 0.16 版行程页里「九曲溪竹筏（必须以出票班次为准）」等 3 处 slot
标题 h3（由共享函数 `_render_day_slots`，html.py 只读，产出，但
`.day-card h3` 是后代选择器天然覆盖它）`scrollWidth` 比 `clientWidth`
多 6px。用 `!important` 强制该 h3 `word-break: break-all`（比任务书猜的
`overflow-wrap: anywhere` 更激进的断行规则）重跑真实页面，6px 纹丝不动
——而且该 h3 本来就已经从 `body { overflow-wrap: anywhere; }`
（`assets/renderer.css:36`，全局继承）拿到过兜底，不是没加过。判断是
CJK 右括号「）」附近的字体墨水度量伪影，不是可断行/不可断行的问题，
断行类 CSS（`word-break`/`overflow-wrap`）治不了；它不冒泡到根级
`horizontalOverflow`（day-card 内边距余量比页头大，局部溢出被吸收，
QA 的「horizontal overflow」判失败项不受影响）。仍按任务书要求给
`.day-card h3` 显式加了 `overflow-wrap: anywhere`（对现状是空操作，
不违反任何规则，留作显式防御）。用本书新增的 `internalOverflow` 诊断
字段实测：真实行程页应用本书修复后，`.journey-title-route` 的根级溢出
归零，但 `internalOverflow` 仍报 12（3 个 day-card 各自的 article/ol/li/h3
共 4 层祖先元素，就是这个未解的 6px 现象）——这不在本书「硬指标一」
范围内（硬指标一只要求本书新增的合成测试 internalOverflow==0，该测试
刻意不构造这个已证实不可控的案例，见 PROGRESS.md 本书任务 0）。如果
领导认为这 12 处局部溢出值得继续查，需要新开一本任务书，方向大概率
不是 CSS，而是字体度量或 CJK 标点避头尾（kinsoku）规则。

## 书「汇合腿铁路赶不上时取合规航班」（2026-09-12，main 直接干）：无待裁决项

任务书要求的三条新测试、三处函数改动、README 两句、四个语料命令零差异、
反向验证全部按预期完成，唯一与任务书预判不符的一点：任务 1 的测试③
（两班铁路 12:00/11:00 到、meet_by 12:30，要求过滤后仍取最早到达）在
改动前实测就已经是绿的，不是任务书猜测的"此刻选错"——因为
`_resolve_rail` 现状的候选选择本就是按到达时间取 `min`，与"先按缓冲过滤
再取最早到达"在"缓冲合规是到达时间的单调函数"这一前提下逐场景结果相同
（最早到达的候选要么合规，两种算法都选它；要么不合规，则不存在更晚到达
但合规的候选，两种算法都得空）。已在 PROGRESS.md 本书任务 1 记录数学
证明与实测输出，未强行制造一个不相关的失败来凑"先红后绿"；测试③本身
仍有效，锁定重构后这个已经正确的场景不会被弄坏。不构成需要裁决的分歧。

## 书 AF1「VariFlight 城市间票价接到 FlyAI 航班腿」（2026-09-12）：无

任务书全程未出现需要管理者裁决的分叉，按完成条件的要求随交付记一笔：
无阻塞项。唯一偏离任务书猜测措辞之处（price 第三次调用只在
`not candidate_mode`——真有 FlyAI 航班腿可比价——时发出，不是「每条
路线」不加区分地都发三次）不算待裁决分叉：任务书原文把这条设计标了
「（猜的）」，硬指标一原文只要求「已选航班腿」两条 claim，偏离理由与
对现有 7 个 candidate_mode 测试零影响的核对已写进 PROGRESS.md 本书
「理解的目标」与「任务 2」两处，判断依据充分，未构成需要停工等待的
分叉。

## 书 AG1「VariFlight 一次票价调用覆盖整条路线每班 FlyAI 航班」（2026-09-12）：无

任务书全程未出现需要管理者裁决的分叉。唯一需要说明、但不构成待裁决
分歧的一点：「界限」把 `variflight_enrichment.py` 允许改动的范围写成
`_enrich_price`、`_build_price_request`、warning 行三处，但
`_enrich_price` 的形参从 `selected` 改成 `route_flights` 之后，
`_enrich_route` 里那一行调用 `self._enrich_price(...)` 的实参必须
跟着从 `selected` 换成 `route_flights`，否则代码根本不能跑——这是
函数签名变化带来的机械连带，不是对 `_enrich_route` 业务逻辑的改动
（该变量本就在同一函数作用域内现成可用，不需要新增计算，`_enrich_
route` 的其余每一行、`_select_flight` 整个函数都未触碰）。「规矩」
一节用 `git diff 12e3a92 --stat` 按文件校验「界限」，这一处改动仍在
`variflight_enrichment.py` 文件内、不引入新文件，判断不算越界，已在
PROGRESS.md 本书「任务 2」记录理由。其余「我替领导拍的板」三条均按
标注的「猜的」原样执行，未发现需要停工等待管理者裁决的分歧。

## 书 Z3「真实行程火车票刷新实战」任务 1：两条链路缺陷（2026-09-12，只诊断不修）

真实数据刷新 `fujian-2026-north` trip 的 `north-2-rail`（9/26 福州→
武夷山）时发现，代码与真实数据本轮一行未改，供领导裁决是否要修。

### 1. refresh 事件不指定 service_number 时，默认选车逻辑不检查与既有时段表的可行性，失败即整体失败、不会退而选下一个候选

`replan.py` 的 `_select_refresh_service`（约 L340-359）在事件不带
`service_number` 时，只按 `min(same_day, key=lambda item:
(item["arrive_at"], item["depart_at"]))` 取当天到达最早的一班，完全
不看这班车的发车时间是否晚于前一个已排定时段的结束时间；随后
`_apply_refresh`（约 L255-258）才检查
`selected["depart_at"] < previous_slot["end_at"]`，一旦为真就
`raise ReplanError("refresh_overlap", ...)`，整个 `replan` 调用直接
失败，不会自动尝试第二早、第三早的候选。

复现（真实数据）：`north-2-rail` 前一个时段 `north-2-checkout` 于
`07:45` 结束；`ctw rail --date 2026-09-26 --from 福州 --to 武夷山`
当天返回的 10 条候选里到达最早的是 `G1644`（`06:52→07:54`），发车
`06:52` 早于 `07:45`，不指定 `service_number` 的 `refresh` 事件
100% 复现 `REPLAN_FAILED refresh_overlap`。10 条候选里只有 1 条
（`G1902`，`07:50` 发车）满足「发车 ≥ 07:45」，本轮已改用显式
`service_number=G1902` 绕过（详见 PROGRESS.md 本节任务 1 记录），
链路最终走通，但这不是「默认路径」自己找到的解。

供裁决：这不是解析错误或数据错误，是「默认选车」这个功能本身的
覆盖范围问题——真实世界里「当天到达最早的车」经常发车更早，与
前一晚/前一段行程的收尾时段冲突是常态而非例外（本次 10 条候选里
9 条都撞了）。若领导认为这个功能应该继续保留「失败就报错、把车次
决定权交回人」的行为，不用动；若希望默认路径本身具备「取到达最早
且不违反前序时段」的能力（例如在同一批候选里过滤掉不可行的再取
`min`），需要改 `_select_refresh_service`，本轮按「只诊断不修」的
界限未动这处代码。

### 2. 12306-mcp 对同一天同一车次号返回了两条 leg_id 完全相同但到达时间/时长/价格不同的记录，导致该车次的 claims 被重复写入

`ctw rail --date 2026-09-26 --from 福州 --to 武夷山` 返回的
`transport_legs` 里，`service_number=G1902` 出现两条记录，`leg_id`
都是 `leg-rail-28bfe4157e41`、`depart_at` 都是
`2026-09-26T07:50:00+08:00`，但 `arrive_at`/`duration_minutes`/
二等座价格不同：一条 `09:30`／`100` 分钟／`128.5` 元，另一条
`09:15`／`85` 分钟／`112.5` 元。`claims` 数组里对应
`subject_ref=leg-rail-28bfe4157e41` 的 claim 也有两组共 6 条
（`/depart_at`/`/price`/`/availability` 各 2 条，值与上述两条记录
一一对应），而不是正常情况下一条 leg 对应的 3 条。

同一天同一车次号本身重复出现是正常的（`G1756`/`G2374` 也各出现两次，
但它们的两条记录各有独立的 `leg_id`，互不冲突，猜测对应不同的
`fs`/`ts` 站点组合或余票批次）；异常的是 `G1902` 这两条记录共享了
同一个 `leg_id`，这本该是每条候选记录的唯一标识。

影响（真实复现）：`replan --event`（`service_number=G1902`，不带
能区分这两条记录的字段）解析时，`_select_refresh_service` 的
`matches = [item for item in same_day if item.get("service_number")
== service_number]` 会命中两条，`matches[0]` 取 `rail_result
["transport_legs"]` 原始顺序里排在前面的那条（本次是 `arrive=09:30`
那条，取决于 12306-mcp 返回顺序、不是「更优」或「更早」排序的结果）；
`_apply_refresh` 复制 claim 时按 `claim.get("subject_ref") ==
selected.get("leg_id")` 过滤，两条记录的 6 条 claim 因为
`subject_ref` 相同全部被复制进 `trip.claims`，其中 3 条
（未被选中的 `09:15` 那组）不会被任何时段的 `claim_ids` 引用、成为
游离 claim；`ctw journey validate`/`validate-html` 都未对「存在未被
引用的 claim」报错（复现见本轮 `journey-r3.json`，`errors=0`）。

供裁决：不确定这是 12306-mcp 适配器（`providers/rail12306*.py`）的
`leg_id` 生成逻辑漏了区分字段（比如只按 `service_number`+
`depart_at` 生成、没把 `arrive_at` 或余票批次编号纳入），还是 12306
真实接口本身对同一车次在同一次查询里返回了两条本该合并、字段却不
完全一致的记录（本轮没有抓到该接口的原始返回做进一步比对，不猜测
是哪一层的问题）。若领导认为「同 leg_id 必须唯一标识一条候选」是
硬约束，需要在适配器层加去重或让 `leg_id` 生成把 `arrive_at` 纳入；
若这种重复本身就是真实数据的常态、下游能容忍，则只需要考虑要不要让
`replan` 在遇到 claim 数量与 leg 数量不匹配时报警（而不是静默接受
游离 claim），本轮均未动代码。
