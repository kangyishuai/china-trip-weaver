# PROGRESS

唯一的当前进度记录：现状速览（0.8.0 起每个版本一条）加最近一波的执行者记录。2026-09-03 到 09-06 与 2026-09-08 到 09-12 的逐轮任务书、实测证据、验收记录已归档，见「历史索引」。

## 书 Z3d「9/26 与 9/29 高铁腿实网刷新」（2026-09-15，第二十五波四份并行书之一，只做实网刷新这一份）

**任务 0 核对**（15:15 实网查询，主检出 `main`，HEAD 与上一条健康审计一致）：

- `ctw rail --date 2026-09-26 --from 福州南 --to 武夷山北 --limit 30`：5 条腿，G1902 07:50→09:30 仍在，
  15:15:33 查询结果已开售——二等座「有」、无座「有」（均 128.5 元），商务座/一等座「无」。现状文件
  `trip-north-r2.json` 的 `leg-fuzhou-wuyi` 只有 2 条 live claim（`/depart_at`、`/price`）加 1 条人工
  锁定 claim，没有 `/availability` claim，本次刷新要把余票数据补上。
- `ctw rail --date 2026-09-29 --from 武夷山北 --to 福州 --limit 30`：8 条腿（`station_rows_filtered:22`，
  被过滤的是南平市站，符合预期），15:15:55 查询 31 个席别全部 `*`（未开售）。到达站混着「福州」
  （FZS）与「福州南」（FYS）两种；核对 `trip-north-r2.json` 当日 9/29 之后的日程（午餐、福建博物院、
  西湖公园、五一广场／三坊七巷片区入住）全部在福州市区，且占位腿原深链是 `ts=福州`（非福州南），
  判定目的站应为「福州」（FZS）不是「福州南」。到福州（FZS）的行里最早到达的是 D2325
  08:24→10:11（二等座/一等座/无座三档价格 128.5/80/80，全 `*`），与领导 14:31 观察到的「最早
  D2325」一致；选它既满足「到正确站」死规矩，到达时间（10:11）也早于原占位腿的到达（11:10），
  后续午餐（11:30 起）等时段不需要顺移。
- 全量测试 `/usr/bin/python3 -m unittest discover -s tests`：`Ran 685 tests in 98.995s ... OK`，
  0 skipped（机器负载导致的正常耗时波动，见「验收教训」）。仓库状态确认健康，可以动工。

**理解的目标／顺序／最大风险**（≤10 行）：目标是用 12306 实网数据替换两条腿的占位/空余票数据，只新增
产物文件，不动仓库代码与既有产物。顺序按任务书 0→1→2→3：先刷已开售的 9/26（数据更完整，能先暴露
流程问题），再刷未开售的 9/29（选车更容易选错站），最后合并出 journey 与页面。最大风险有二：一是
9/26 的 `leg-fuzhou-wuyi` 当前 `locked:true`（人工确认已购），`replan` 会因「锁定项无显式解锁」报
`locked_ref`，需要显式传 `--locked-ref leg-fuzhou-wuyi`——这不违反「不许编造车次」的规矩，因为车次号
和时刻不变，只是补齐余票数据,且刷新逻辑本身会保留 `locked` 字段；二是 9/29 到福州的行里「福州」与
「福州南」站混在同一次查询结果里，必须显式指定 `service_number` 锁定正确站，不能依赖默认「最早到达」
逻辑（本例中两者恰好重合，但不能假设每次都重合）。

**任务 1 完成（9/26 `leg-fuzhou-wuyi` 刷新）**：

- 修正任务 0 里的一个错误预判：`--locked-ref` 不是解锁开关，是**追加**锁定——`_locked_refs()`
  （`replan.py:143-155`）只读 Trip JSON 自身两处 `locked` 字段（transport_legs 与对应 day/slot 各一
  处，`leg-fuzhou-wuyi`／`north-2-rail` 当时都是 `true`），CLI 没有任何参数能把已经是 `true` 的
  `locked` 项在这一次调用里临时解锁；直接跑 `ctw replan --locked-ref leg-fuzhou-wuyi ...` 两次都报
  `REPLAN_FAILED locked_ref`。处理：新建一份只把这两处 `locked` 改成 `false` 的工作副本
  `trip-north-r2-unlocked-for-refresh.json`（不覆盖 `trip-north-r2.json`），用它作 `--trip` 才跑通，
  产出 `trip-north-r3-intermediate.json/html`（revision 3，errors=0，但 leg 与 slot 的 `locked` 都被
  `_apply_refresh`（`replan.py:262-263`，字段级原样拷贝旧 leg 的 `locked`）连带置成 `false`）。车票
  已购这个事实没有变，只是本地临时解锁以便刷新余票，刷新完成后手工把 `trip-north-r3-intermediate.json`
  的这两处 `locked` 改回 `true`，另存为最终产物 `trip-north-r3.json`；`ctw validate`/`ctw render`/
  `ctw validate-html` 三条命令对最终版全部重跑一遍，`VALID`／`errors=0`／`errors=0`，不是「改了校验
  就一定过」。
- 副作用：`_apply_refresh` 会无条件删掉旧 leg 的全部 claim 再补新的（`replan.py:290-296`），人工确认
  claim `claim-g1902-user-booked`（`provider:"user-confirmed"`，记录「用户已确认购买」）随之被删除；
  没有手工重建它——重建等于编造一条「用户今天又确认了一次」的假记录，而 leg 自身的
  `service_number:"G1902"` 加恢复后的 `locked:true` 已经完整表达「已购锁定」这个事实，此处只是如实
  记录这条 claim 消失了。
- 余票数据：leg 的 3 条 claim 全部换成 2026-09-15 15:15:33 查询的实时结果——rail-result 原始行
  `{"service_number":"G1902","depart_at":"07:50","arrive_at":"09:30","price":128.5}` 加
  availability `[{"商务座","无"},{"一等座","无"},{"二等座","有",128.5},{"无座","有",128.5}]`；最终
  trip 里 `leg-fuzhou-wuyi` 逐字段对应：`service_number:"G1902"`、`depart_at:"2026-09-26T07:50:00+08:00"`、
  `arrive_at:"2026-09-26T09:30:00+08:00"`、`price.amount:128.5`，页面「交通摘要」渲染为「座位：商务座
  无 · 一等座 无 · 二等座 有 · 无座 有」。
- claim 计数（与任务书预期不同，如实记录）：刷新前该腿 3 条 claim，全部在 `claim_ids` 里被引用，
  **0 条游离**；刷新后仍是 3 条、0 条游离——这条腿本来就没有游离 claim，缺的是 `/availability` 这个
  字段本身（此前刷新时票还没开售，查不到余票），这次刷新是补空白字段而不是清理游离项。trip 全局
  `claims` 总数刷新前后都是 26（3 条出、3 条进，净不变）。

**任务 2 完成（9/29 `leg-wuyi-fuzhou` 刷新）**：这条腿与其 slot（`north-5-rail`）本来就是
`locked:false`，不需要任务 1 那套解锁手续，直接以 `trip-north-r3.json`（revision 3）为 `--trip`、
`--base-revision 3` 跑通，产出 `trip-north-r4.json/html`（revision 4，errors=0）。

- 选车：8 条候选里到「福州」（FZS，非福州南 FYS）的最早一班是 D2325 08:24→10:11，与任务 0 的判断
  一致；事件文件只带 `service_number:"D2325"` 就唯一命中（这趟车在 rail-result 里只有到福州 FZS 一
  行，不像 G1902 那样需要再靠 `depart_at` 消歧）。最终 leg 的 `booking_url` 落地
  `ts=%E7%A6%8F%E5%B7%9E%2CFZS`（福州,FZS），不是福州南、更不是南平市站，满足选车死规矩。
- 余票数据：rail-result 原始行 `{"service_number":"D2325","depart_at":"08:24","arrive_at":"10:11",
  "price":80}`，availability 三档（一等座 128.5／二等座 80／无座 80）**全部 `*`**；最终 trip 里
  `leg-wuyi-fuzhou` 逐字段对应：`service_number:"D2325"`、`depart_at:"2026-09-29T08:24:00+08:00"`、
  `arrive_at:"2026-09-29T10:11:00+08:00"`、`price.amount:80`，页面渲染「车站：武夷山北 → 福州 座位：
  一等座 未开售 · 二等座 未开席 · 无座 未开售」——如实记录：**刷新时这趟车尚未开售**，车次号和时刻是
  真的，余票是空的。
- claim 计数：刷新前该腿 2 条 claim（排程窗口 hypothesis + 价格 unknown，均被引用，0 游离）；刷新后
  3 条（depart_at／price／availability，均 live/verified，均被引用，0 游离）。trip 全局 `claims`
  总数 26 → 27（2 条出、3 条进，净 +1，新增的是此前完全没有的余票字段）。
- 观察但未处理（记入 BLOCKED.md）：`_apply_refresh` 只更新 slot 的 `start_at`/`end_at`/`claim_ids`，
  不碰 `title` 文字，`north-5-rail` 这一 slot 的标题仍停留在旧占位文案「武夷山→福州高铁（当前为排程
  窗口）」，与已经写入的真实 D2325 数据不一致；页面「交通摘要」区块本身文字正确（因为那部分是从
  leg 字段直接渲染，不读 slot 标题），只有逐日时间轴那一行标题文字滞后。未改——这是渲染器行为，
  「不许为了让流程跑通而改仓库代码」，如实记录待管理者裁决。

**任务 3 完成（装配 journey-r5.json 与新页面）**：`ctw journey assemble --journey journey-r4.json
--replace-trip trip-north-r4.json --base-revision 4 --reason "..." --output-json journey-r5.json`
→ `JOURNEY_ASSEMBLE_COMPLETE trips=3 days=16 errors=0`；`ctw journey render journey-r5.json --output
福建中秋国庆16天行程-r5.html` → `errors=0`；`ctw journey validate-html 福建中秋国庆16天行程-r5.html
journey-r5.json` → `JOURNEY HTML VALID ... errors=0`；`ctw journey validate journey-r5.json` →
`JOURNEY VALID ... trips=3`。四条命令全部一次通过，未触碰任何校验器代码。

两条腿「rail-result 原始行」与「最终 trip/journey 里那条腿」逐字段对照：

| 字段 | 9/26 rail-result 原始行 | 9/26 最终 leg（`leg-fuzhou-wuyi`） | 9/29 rail-result 原始行 | 9/29 最终 leg（`leg-wuyi-fuzhou`） |
|---|---|---|---|---|
| service_number | G1902 | G1902 ✓ | D2325 | D2325 ✓ |
| depart_at | 2026-09-26T07:50 | 2026-09-26T07:50 ✓ | 2026-09-29T08:24 | 2026-09-29T08:24 ✓ |
| arrive_at | 2026-09-26T09:30 | 2026-09-26T09:30 ✓ | 2026-09-29T10:11 | 2026-09-29T10:11 ✓ |
| price.amount（二等座） | 128.5 | 128.5 ✓ | 80 | 80 ✓ |
| 到达站（booking_url ts） | 武夷山北,WBS | 同左 ✓ | 福州,FZS（非福州南） | 同左 ✓ |
| availability | 商务座/一等座 无，二等座/无座 有 | claim 原文照搬 ✓ | 三档全部 `*`（未开售） | claim 原文照搬 ✓ |

页面上两处可见文本（`福建中秋国庆16天行程-r5.html`，「跨城交通」区块）：

- 9/26：「铁路 · G1902 · 福州 → 武夷山 · 2026-09-26 07:50 车站：福州南 → 武夷山北 座位：商务座
  无 · 一等座 无 · 二等座 有 · 无座 有」
- 9/29：「铁路 · D2325 · 武夷山 → 福州 · 2026-09-29 08:24 车站：武夷山北 → 福州 座位：一等座
  未开售 · 二等座 未开售 · 无座 未开售」

**交付前自查**：`git diff -- plugins tests scripts docs demo .github README.md` 输出为空；
`git status --short` 只有 `PROGRESS.md`、`BLOCKED.md` 两行（本节写入前）；仓库代码一个字节未改。
真实行程目录只新增文件，未覆盖任何既有产物：新增 `rail-2026-09-26-fuzhounan-wuyishanbei.json`、
`rail-2026-09-29-wuyishanbei-fuzhou.json`、`event-refresh-2026-09-26-g1902.json`、
`event-refresh-2026-09-29-d2325.json`、`trip-north-r2-unlocked-for-refresh.json`、
`trip-north-r3-intermediate.json/html`、`trip-north-r3.json/html`、`trip-north-r4.json/html`、
`journey-r5.json`、`福建中秋国庆16天行程-r5.html`；`journey.json`/`journey-r2.json`/`journey-r4.json`/
`trip-north-r2.json` 与既有全部 `.html` 均未写入（只读）。任务 0-3 一轮内全部完成，未触发 5 轮上限。
`BLOCKED.md` 本轮新增一条非阻塞观察（slot 标题不随刷新更新），无待裁决的硬阻塞项。
## 2026-09-15「E003 已购锁定表达缺口」ADR（第二十五波之一，worktree `.tmp/wt-adr` 分支 `e003-locked-service-adr`，四份并行书中的第③份，只出结论不改代码）

（本条追加于文件顶部而非任务书「界限」字面写的「末尾追加」：本文件与
`BLOCKED.md` 的实际既有约定都是新的在最上面——本条正上方就是同日期的健康审计
条目——任务 0 又明确要求相关证据「写 BLOCKED.md 最上面」，按「说的与文件实际
结构一致」优先处理，两处都改为顶部插入，供管理者合并时核对。）

**任务 0（离线复现 E003）**：任务书字面指令（跑 `ctw journey validate-html`）
复现不出来——`render/validate_journey_html.py` 整份文件没有任何
`TRAIN_FACT_RE`/E003 检查（`git grep` 零命中），它是与 Trip 级 `validate_html.py`
完全独立的一套 `JH0xx` 校验。改用 `plan_trip` 内部真正调用的 Trip 级
`ctw validate-html` 复现成功，输出与真实故障逐字一致（`E003 rendered train
fact is absent from Trip: G1902`）。判断记入 `BLOCKED.md` 顶部，供裁决是否
认可「命令名对不上，但护栏真实行为已验证」这类处理方式；未因此停工，因为
任务 0 的真正目的——核实护栏真实行为——已经用可复跑的命令完整达成。完整命令
与输出见 `docs/design/adr/0020-locked-service-assumption.md` 的 Context 一节。

**理解的目标／顺序／最大风险（≤10 行）**：目标是给管理者一份能直接拍板的
ADR，回答「已购锁定」这类既成事实该怎么表达，而不是顺手把 E003 的报错改好——
任务书三次强调「零代码改动」。顺序按任务书给定的 0→1→2：先离线坐实护栏的真实
触发路径（结果发现任务书点的命令是错的，必须先修正理解才能谈后续判断，这也是
为什么任务 0 必须最先做）；再把 A/加字段、B/改报错、C/隔离文本三条路都查到能
互相比较的深度，额外补了一条零代码的 D/沿用既有 refresh 机制作对照；最后写
ADR。最大风险是「查得全」压过「证据真」——本轮刻意把每条判断都钉死在具体
`git grep`/文件:行号/亲自跑出的命令输出上，而不是转述任务书自己给的「已知
事实」；次大风险是 00-README.md 的 ADR 表格自 ADR-0009 起已经 11 个版本没跟上
（只列到 0008），这是任务书之外发现的既有文档漂移，按「顺手活不许做」原则只
加了 ADR-0020 一行、不回填历史行，记入 BLOCKED.md。

**任务 1/2（三路径评估 + 写 ADR）已完成**：结论与逐条证据见
[`docs/design/adr/0020-locked-service-assumption.md`](docs/design/adr/0020-locked-service-assumption.md)（Status: Proposed）。
6 条结论提要：① 任务 0 需要用 Trip 级 `ctw validate-html` 而非任务书写的
`ctw journey validate-html` 才能复现；② Direction A（结构化锁定字段）可行，
20 golden/8 no-solution 夹具经核实是完全不相关的 day-scheduler 子系统、不受
影响，`_resolve_rail` 可复用 `replan.py` 里已经写好并测过的
`_select_refresh_service`/`_disambiguate_service_matches`/`_matches_time`；
③ Direction B（只改报错）比任务书设想的更便宜——`_check_rendered_facts` 已经
拿到完整 `trip`，`assumptions`/`constraints` 是仅有两处会被渲染成可见文本的
自由字段，无需新增跨层传参；④ Direction C（隔离自由文本）不建议，恰在风险
最高处摘掉护栏，工程上也做不到解析器与浏览器口径一致；⑤ 补充的 Direction D
（零代码，沿用 `ctw replan --event refresh`）已在真实的 G1902 这条腿跑通过
（`fujian-2026-09-25-to-10-10/event-g1902-booked.json`），但只治当次产物、
不治 `request.json` 本身，每次从零重新 `journey plan` 会再撞同一个 E003；
⑥ 推荐 A 定长期方向、B 独立先做、C 不采纳、D 写作临时工作流。
`docs/design/00-README.md` 第 29 行「## 2. ADR」表格已加 ADR-0020 一行。

**收尾核对**：`git diff main -- plugins tests scripts .github demo README.md`
为空；`.tmp/e003-repro/` 全程只在本 worktree 内、被根 `.gitignore`
（`.tmp/*`）挡住，`git status --short` 不显示它。全量测试结果见下方本轮末尾
的独立记录。

## 2026-09-15 健康审计（第二十四波，进行中——诊断，不改代码）

**任务 0 核对**：五条基线命令逐一亲手重跑，四条逐字吻合（685 测试 OK 49.7s、pyflakes 0 行、
install_local_plugin.sh --check 0.20.1 一致、ci.yml 确实只有两步）。两处不完全吻合但均判定不
阻塞：① `scan_secrets.py` 报 389 file(s) 而非 388——查源码 `repository_files()` 用
`git ls-files --cached --others --exclude-standard` 同时统计未跟踪但未被 .gitignore 挡住的文件，
本机会话开始前已有一个游离的未跟踪 `.coverage`（不在 .gitignore 里，且不是我产生的）正好补上这
1 个文件差；实质结论「0 finding」两次都成立。② 任务书「TODO/FIXME 全仓仅 2 处」，
`git grep -n "TODO\|FIXME"` 实测 3 处命中，但逐条读发现 3 处全部是「提及 TODO 概念的说明文字」或
「检查不存在 `[TODO:` 占位符的测试断言」，真正意义上「留给自己以后处理的代码待办」是 0 处——判断
任务书这个数字是次要背景色、不影响任何硬指标，不停工。

**理解的目标／顺序／最大风险**（≤10 行）：目标是诊断不是修复，交付一份排好序的问题清单给领导定
下一波，而不是把绿灯变得更绿。顺序按任务书给定的 1→2→3→4，因为任务 1（绿灯审计）判断后面结论
还信不信得过，必须最先做。最大风险是「查得全」压过「证据真」——尤其任务 2 文档核对量极大（README
×2、SKILL.md ×9、provider-contracts.md），已拆成并行子代理各自用 git grep 逐条核证，但最终结论要
我亲自抽查过citation 才能写进报告，不能直接转述子代理原话。次大风险是实网抽查（任务 3）会消耗真
实 Key 额度且只许跑一次，需等任务 1/2 的本地检查全部完成、确认没有会污染真实行程目录的意外副作用
后再执行。

**任务 1 进展**：
1. 覆盖率真因已查清并已解决（非「查不出来」分支）：本机唯一装了 coverage 的解释器是
   一个跨项目共用的本机 conda 环境的解释器（不是本项目专用，
   不是本项目专用），其 site-packages 里有一个与本项目无关的一个与本项目无关的第三方包
   自带了一个真正的 `tests/__init__.py`（落在该环境的 site-packages 根下），
   在 Python 的 import 优先级里，正规包会盖过 PEP 420 命名空间包，导致该解释器下 `import
   tests.test_providers` 永远解析到那个第三方包的 `tests/` 而不是仓库自己的 `tests/`——这与
   Python 版本无关（用 `/usr/bin/python3` 3.9 或该 conda 环境的 3.12 裸测试均可复现同一结论：
   干净解释器都能跑满 685，只要 site-packages 里没有同名 `tests` 包）。证据：`python -c "import
   tests; print(tests.__file__)"` 在该 conda 环境下打出 site-packages 里的路径；`pip show -f` 反查
   `importlib.metadata` 确认属主。解决：在 一个会话专用的临时目录（会话专用
   临时目录，不在仓库、不进 git、不装进用户任何持久环境）用 `/usr/bin/python3 -m venv` 建一个干净
   venv，只装 `coverage`+`pyyaml`（后者是 685 项里一条测试要 shell 出去调 Codex 自带
   validator 脚本、该脚本本身 import yaml，与本仓库源码无关），在其中跑
   `coverage run -m unittest discover -s tests` 得到 **685 tests OK**，`coverage report
   --include="plugins/china-trip-weaver/src/*"` 得到 **总体 85%（10640 行、缺 1614 行）**，
   `cli.py` 单独 **48%**——与 CLAUDE.md 记的历史基线「总体 84%，cli.py 47%（子进程未追踪）」
   几乎完全吻合（相差 1 个百分点，落在版本间正常代码变动范围）。结论：此前「62%」纯粹是
   452/685 残缺跑法的测量伪影，不代表真实覆盖率下降；真实覆盖率与历史基线一致，84% 基线本身
   没有失真。
2. 本机会红、CI 不会红的检查清单（逐条核对 `.github/workflows/ci.yml` 全文只有 unittest+
   scan_secrets 两步后得出）：① `pyflakes` 全仓 0 行——CI 从未跑过 pyflakes，任何 PR 引入未用
   导入/未定义名不会让 CI 变红；② `scripts/install_local_plugin.sh --check`——结构性地不能在
   CI 跑（GitHub runner 没有 Codex 二进制），非缺陷但是真实盲区；③
   `tests/test_packaging.py:133`、`tests/test_skills.py:134,141` 三个测试用
   `codex_executable() is None` 门控 `skipTest`，GitHub `ubuntu-latest` 从不装 Codex，故这
   3 项测试在 CI 上**每次都跳过**，「Codex 打包的 skill/plugin 校验器认为这份插件合格」这件事
   完全不在 CI 的把关范围内，只在装了 Codex 的本机才是真的验证过——这与 PROGRESS.md 已归档的
   「2026-09-05~08 CI 连红一周没人发现」是同一类型的盲区,只是这次没有变红，是静默跳过。
3. 三项反向验证，均在副本/隔离环境上做，`git status --short -- plugins tests scripts docs
   demo .github` 全程为空（证据见下），仓库本体零改动：
   - `scan_secrets.py`：复制 `cli.py` 到 `.tmp/health/reverse-verify/cli_copy.py`，干净时
     `0 finding(s)`；追加一行 一行 GitHub token 形状的假字符串 后
     `1 finding(s)`（`credential prefix`）、exit 1；再追加
     一行 `AMAP_WEBSERVICE_KEY` 赋值形状的假字符串 后 `2 finding(s)`（另加
     `secret variable assignment`）；还原回干净副本后 `0 finding(s)`、exit 0。真实报警器。（合并时由管理者改写：原记录直接贴了两个凭据形状的字面串，会让 `scan_secrets.py` 在仓库自己的 PROGRESS 上报 2 处命中、CI 必红；写反向验证记录时只描述形状，不要贴字面串。）
   - `pyflakes`：复制 `geo.py`，干净 exit 0；注入一行未用 `import json as
     _unused_injected_import` 后立即报 `imported but unused`、exit 1；还原后 exit 0。真实报警器。
   - **项目最重要的安全承诺**（只读、永不下单）的反向验证：12306 侧用
     `mcp_stdio.py:347 EXPECTED_12306_TOOLS` 精确元组指纹 + `mcp_stdio.py:392` 硬编码调用名
     `"get-tickets"` 兜底。复制整个 `china_trip_weaver` 包到
     `.tmp/health/reverse-verify/src_copy/`，写一个小驱动脚本用 `sys.modules` 预热让
     `tests/test_mcp_stdio.py`（未改动的真实测试文件）从副本而非仓库本体加载
     `china_trip_weaver`（用 `assert copy_path in china_trip_weaver.__file__` 自证生效）；副本
     未改时 6/6 绿；把副本里 `client.call_tool("get-tickets", ...)` 改成
     `client.call_tool("book-tickets", ...)`（模拟"如果代码试图调用一个像预订的工具名"）后，
     `test_transport_runs_station_then_ticket_and_adapter_emits_live_leg` 立即红：
     `AssertionError: 'contract_mismatch' is not None`。证明「只调用只读接口」这条护栏是真实生效
     的代码机制（工具名指纹允许列表），不是纯靠约定。
   - 承诺侧的一个真实旁路（非该反向验证项，是任务 2 顺带查到、记在此处备用）：
     `credentials.py:resolve_credentials()` 对每个凭据名先查 `os.environ`，只有环境变量未设置
     时才落到 `credentials.env` 文件；`git grep -n "resolve_credentials(" --
     plugins/china-trip-weaver/src` 确认 cli.py/mcp_stdio.py 等全部生产调用点都用默认
     `environ=None`（即读真实 `os.environ`），意味着如果用户 shell 里恰好设了同名环境变量，会
     不经过该文件、直接生效——`provider_environment()`（credentials.py:145）则相反，是好的隔离
     设计，只把安全白名单变量+目标 provider 自己的凭据传给子进程，不透传整个父进程环境。判断是否
     真与文档承诺冲突，需等 README/provider-contracts.md 并行审计子代理的结果。

**任务 2 完成**：4 个并行子代理（README×2、provider-contracts.md、SKILL.md×9 分两组）全部回来，
逐条抽查引用（git grep 重跑确认行号与文本）后采信。confirmed discrepancies：
provider-contracts.md 3 处（12306 15s/25s 分列不存在、AnySearch 10s 应为 15s/6000ms、「cache→」与
文档自身矛盾）；README ×2 处（未提及 `demo/multicity-5d`、ZH 版把中文的 `docs/design/` 标成英文）；
SKILL.md ×2 处（`search-china-lodging` 的 `--keyless-trial` 位置引起误解、
`research-china-destination` 的 `exact_original_confirmed` 分支实际是 automatic 不是 manual）。凭据
「环境变量优先于文件」核实为 README 已准确记载的行为，不是隐藏旁路（README.md:42／
README.zh-CN.md:42 明确写在先）。全部 7 处文档问题按「顺手活」不许改，记入 BLOCKED.md。

**任务 3 完成**：结构债——AST 逐函数量长度，`planning.py` 最长 `_resolve_rail`（110 行非任务书说的
120，差异不影响结论）、`journey.py` 最长 `validate_journey`（103 行）；抽查 `_resolve_rail` 全文，
判断长度来自业务分支顺序步骤、非重复逻辑，未发现拆分的具体证据，如实报告调查深度（未逐一通读
journey.py/cli.py 其余长函数）。cli.py 子进程覆盖率追踪额外发现：`_cmd_rail`（85 行独立子命令）
即使算上子进程也几乎零覆盖，全仓没有测试以 `[CTW,"rail",...]` 形式调用它。实网抽查按约定只跑一次：
`ctw journey plan --rail live --mobility live --lodging live --aviation auto` 用真实
`fujian-2026-09-25-to-10-10/{request,candidates}.json`，输出到 `.tmp/health/`。探针确实打到真服务商
（FlyAI×1、VariFlight×6、AMap geocode/poi/route 数十次，见
`.tmp/health/journey-live-probe.stderr.ndjson`），但最终 `JOURNEY_PLAN_FAILED HTML validation
failed: E003 rendered train fact is absent from Trip: G1902`——定位到 `request.json` 第 125 条
assumptions「G1902车票已购并锁定……」这条自由文本人工备注，`journey plan`（区别于 replan/refresh 的
显式 service_number 机制）没有结构化字段能把它当约束喂给活选逻辑，实时选中的车次与文本不符时
`render/validate_html.py:272-275` 的反幻觉校验器 E003 正确整体拒绝渲染。安全网生效、非算错结果，但
报错未指回真正病因。未产出 Trip/输出 JSON，故 `provider_health` 三段完整性无法核实，如实记录为未
验证而非「查过没问题」。已消耗本轮唯一一次实网额度，不重跑。

**任务 4 完成**：`../HEALTH-2026-09-15.md` 已写就，10 条结论（≤12 条上限内）按「值不值得下一波做」
排序，每条附严重度、可复跑证据命令、工作量估计、建议动作；末尾候选清单 7 行。`BLOCKED.md` 已记录
7 处「顺手活」文档问题 + 2 项候选后续任务（E003 表达缺口、覆盖率方法论沉淀）+ 2 项正面结论
（只读护栏、scan_secrets/pyflakes 均反向验证为真）。

**本轮健康审计结束**，一轮内完成全部任务 0-4，未触发「6 轮」上限。交付前核对：
`git diff -- plugins tests scripts docs demo .github` 为空，`git status --short` 只有 PROGRESS.md、
BLOCKED.md 两个文件（会话开始前遗留的游离 `.coverage` 已清理）。

## 现状速览（2026-09-15 实测，0.21.0）

- 版本：`0.21.0`，唯一来源是
  `plugins/china-trip-weaver/.codex-plugin/plugin.json` 与
  `src/china_trip_weaver/__init__.py` 的 `__version__`，两处一致，仓库内其余
  代码与文档一律引用这两处之一；只有本节的逐版本条目和 git tag 以版本号作索引。
- 测试：仓库根 `/usr/bin/python3 -m unittest discover -s tests` 全量 `Ran 690 tests`，`OK`，0 skipped；
  `scripts/scan_secrets.py` 0 命中；
  `~/miniconda3/envs/core/bin/python -m pyflakes plugins/china-trip-weaver/src
  tests scripts` 0 行。带假 Key（`ANYSEARCH_API_KEY=... unittest`）跑全量同样
  690 OK，README 的 demo 与全部夹具重生成在有无 Key 两种环境下都零差异。已知边界：
  `VARIFLIGHT_API_KEY` 若以**环境变量**注入，`test_credentials` 会红一项——那条测试
  隔离了 credentials 文件却没隔离环境变量，而凭据解析是环境变量优先；0.20.1 上实测
  同样红，非本版引入。
- 0.21.0（第二十四波，四份并行：文档订正、检查基建、ADR、实网刷新）：健康审计查出的
  文档漂移七处改对——`references/provider-contracts.md` 的 12306 超时由不存在的
  「15s direct; 25s interline」改为真实的统一 `90s`、AnySearch 由 `10s` 改为
  `15s`、12306 与 AMap 两行删掉与文档自身「R1 disabled」矛盾的「cache →」一档；
  两份 README 补上从未被提及的 `demo/multicity-5d/`、`README.zh-CN.md` 把
  `docs/design/` 的语言由「英文」订正为「中文」；`search-china-lodging/SKILL.md`
  写明 `--keyless-trial` 只属于 `lodging`/`air`、`research-china-destination/SKILL.md`
  把 `exact_original_confirmed` 的处置由「manual review」订正为自动。新增
  `scripts/measure_coverage.py`：从系统解释器建一次性 venv、按 coverage.py 的
  子进程配方测量（套件有 82 处 `subprocess` 调真实 `ctw`），并在出具百分比前
  断言这一轮真的跑满了整个套件——健康审计里那个「可信却错误的 62%」正是这种
  残缺测量的产物（成因是共用解释器的 site-packages 里有第三方包自带的顶层
  `tests` 包，遮蔽了本仓库的 `tests/`）。CI 补 pyflakes 一步；`.coverage*` 进
  `.gitignore`。新增 `tests/test_rail_cli.py` 5 项，端到端覆盖此前零覆盖的
  `ctw rail`（`cli.py:_cmd_rail`），测试数 685 → 690，覆盖率 88% → 89%。
  新增 ADR-0020，为「某趟车已购并锁定」这类既成事实在初次规划中无处表达的
  缺口给出四个方向与推荐（Status: Proposed，待裁决）。真实 16 天行程的两条
  高铁腿同日实网刷新，产物按约定留在仓库外。
- 0.20.1（第二十三波，纯文档加一条测试）：`docs/design/` 四份现役设计文档追平
  0.16.0–0.20.0 的代码——04-providers §4.2 补 12306 直达行按到发站过滤
  （`_filter_direct_rows`、`station_rows_filtered:<n>`／`station_rows_all_filtered`）、
  `--limit` 默认 30 经 `limited_num` 转 MCP `limitedNum` 且过滤在其后、`num="*"` 属
  `NO_INVENTORY`；§4.3 补飞常准 `getFlightPriceByCities` 第二价源（非候选模式每路线一次、
  `_live_price` 按航班号取经济舱最低价、阈值 `max(PRICE_CONFLICT_MIN_DELTA, FlyAI 价×
  PRICE_CONFLICT_RATIO)` 即 max(20, 5%)，严格大于才 conflict）、`CITY_IATA` 24 城、
  `_live_error_class` 10→no_results／12→invalid_request／其余→upstream_5xx、FlyAI
  `status=1,data=null` 非空结果按 upstream_5xx；06-pipeline 新增 §5.4 汇合腿
  （`_validate_meeting_anchor` 在 FlyAI/VariFlight 之后、`_promote_meeting_flight_leg`
  同路线合规航班取最早到达、`MEETING_BUFFER_INSUFFICIENT` 报最早到达与实际缓冲），§7.2
  refresh 行补默认选车、`depart_at`/`arrive_at` 挑行、换腿删旧 claim；08-testing replan
  golden 4→7 并列全名；09-impl-map 补 `providers/anysearch_http.py` 与 `scripts/` 六个脚本、
  `journey.py` 行补 `_with_missing_budget_ledgers`。新增 tests/test_design_docs.py：运行时
  42 个模块加 scripts 6 个脚本共 48 个文件名都必须出现在 09-impl-map。管理者验收：逐句
  对码（两个 warning 的嵌套、阈值严格大于、经济舱 Y 最低价、24 城、错误码、汇合腿调用
  顺序与报错字段、anysearch 固定 origin 与 4 MB 上限）全部属实；docs/design 无 `/Users/`、
  无真实酒店名；删掉 09 的 `scan_secrets.py` 一行新测试立刻红。
- 0.20.0（第二十二波，一本事件新键加一本夹具卫生）：refresh 事件带 `service_number`
  时可再带 `depart_at`（完整 ISO 或 `HH:MM`，与 `arrive_at` 同款；
  `_disambiguate_service_matches` 先按 `depart_at` 再按 `arrive_at` 逐层过滤，
  `_matches_arrive_at` 改名 `_matches_time`），只剩一行即选中，否则
  `refresh_service_ambiguous` 文案按 `(depart_at, arrive_at)` 排序列出「出发→到达」，
  挑行键零命中时前缀 `no row matches depart_at=… arrive_at=…; `；默认选车、
  `_apply_refresh`、schema 未动；ADR-0015 追加 Amendment，README 两份与 replan Skill 各加
  半句。`build_scheduler_fixtures.py` `build_replans()` 现在生成全部 7 份 replan 金样（新增
  refresh、suspend、suspend-first-leg 三个字典字面量，refresh 的 `rail_result` 抽成
  `_refresh_rail_result()`），7 份逐字节不变，manifest `counts.replan` 4→7、files 32→35，
  `test_manifest_covers_every_replan_fixture` 锁住路径集合；README 两份与 09-impl-map 同步
  为 7。管理者验收：用 journey-r4 的 north 与 14:34 的真实 12306 结果回放，
  `depart_at=07:50` 选中 G1902 福州南 07:50→09:30（fs=FYS）、3 条 claim、校验通过；只带
  `arrive_at=09:30` 报歧义并列出 07:50→09:30 与 08:12→09:30 两对；`depart_at=07:55` 报
  `no row matches`；默认路径仍选 G1648 08:00；15:17 实测 9/26 十趟 40 个席别仍全是 `*`，
  真实行程未重刷、页面未重渲染（本波不改渲染）。AL2 执行者没写书名，合并时补上。
- 0.19.1（第二十一波，两本都是修正）：12306 余票 `num="*"` 判为未开售——
  `providers/rail12306.py` `NO_INVENTORY` 加入 `"*"`，`_has_inventory("*")` 为 False、
  `_seat` 写 `available=false`，claim 原文照旧保留 `*`；`render/html.py` `_rail_seat_line`
  按 claim 项 `availability` 原文分三档：`*`→「未开售」（en `not on sale yet`）、
  `候补`→「候补」（en `waitlist`）、其余按 `available` 显示「有／无」，Trip/Journey 两份
  labels 各加两键；新夹具 `presale_star`（四档 `*`，item_count 1，腿价仍二等座 300，四档
  `available` 全 False），夹具 85；provider-contracts 与 07-renderer 各加半句。refresh 换腿
  时清旧 claim——`replan._apply_refresh` 在复制新 claim 前按 `subject_ref == leg_id` 倒序
  pop 旧 claim 并逐条记 `/claims/<i>` remove，其它 subject 一条不动；金样 refresh.json
  `operation_count` 31→33；ADR-0015 Amendment、README 两份、replan Skill 各加一句。
  执行者纠出任务书两处失误：`build_scheduler_fixtures.py` 从不生成 refresh.json（它是
  手写金样，执行者用同脚本的 `write_group()` 重写、manifest 不变），且夹具只存
  `operation_count`、不存 patch 操作，`git grep remove` 永远为 0（按让步顺序保留「金样
  只改操作数」）；既有 rail 夹具是 16 份不是 15。AK2 执行者把书名写成 AK1，合并时改回。
  管理者验收：真实 Key 14:34 查 9/26 福州→武夷山 10 趟四档仍 `*`、`available` 全 False、
  腿价 128.5；用 journey-r4.json 渲染 `福建中秋国庆16天行程-0.19.1.html`，四处座位行都是
  「未开售」，校验零错误、QA 零失败；对 r4 的 north 默认刷新（G1648）后 9/26 腿从 8 条
  claim（3 条被引用）变成恰 3 条全被引用、其它 23 条逐字节不变、总 31→26，patch 8 条
  remove，第二轮默认刷新仍 3 条。新发现：G1902 在 12306 有两行（福州南 07:50 与福州 08:12，
  同到 09:30），指定车次加 `arrive_at` 仍报 `refresh_service_ambiguous`，文案还说「到达
  时间不同」——第二十二波加 `depart_at` 挑行。发版时管理者的脚本把 tag v0.19.1 先打在了
  未升版本号的合并提交上，一分钟内删除 tag 与 Release 后重打。
- 0.19.0（第二十波，一本改装配语义加一本页面新增）：`journey assemble`（首次装配与
  `--replace-trip` 都经 `assemble_journey_from_trips`）对缺 `budget_ledger` 的子 Trip
  用 planning `_budget_ledger` 现算（新私有函数 `_with_missing_budget_ledgers`，排序
  后、连接定价前；已有账本的 Trip 原样传递，demo 逐字节往返不变；L1810 容忍测试的
  `price_type` 断言改成 `"unknown"`，两端金额仍 None）；README 两份与 plan Skill 各加
  一句。行程页火车腿显示座位余票——`render/html.py` `_rail_seat_line` 只取腿自己
  `claim_ids` 里第一条 `/availability` claim，按 `available` 显示「有／无」、不显示
  舱位票价（Trip 页校验器只认实体价格），Trip 页一处、Journey 页四处与「车站」行
  相邻；分组示例页多两行座位，README demo 与 journey-16d 零差异；07-renderer 加一句。
  管理者验收：对真实 journey-r3.json 做一次 `--replace-trip`（north 原样）得
  journey-r4.json（revision 4）：三个子 Trip 都有账本，Journey 已知费用 385.5
  （G1902 二等座 128.5 × 3 人），页面「已知费用」不再是 0；渲染
  `福建中秋国庆16天行程-0.19.0.html`，9/26 腿显示车站与座位行。数据语义问题：12306
  对未开售席别返回 `num="*"`（我 00:39 与 13:04 两次实测 9/26 福州→武夷山与泉州→厦门
  全部席别都是 `*`，真实 journey-r3 的 availability claim 也是），`_has_inventory`
  把 `*` 当有票，页面把 9/26 四档座位都写成「有」——第二十一波修。
- 0.18.1（第十九波，一本修正加一本页面新增）：12306 站名过滤去掉「证据门控」——
  `tests/fixtures/mcp_stdio_server.py` 的 `ticket_payload` 按站码在自己的站表反查
  真实站名，`_filter_direct_rows` 对确认不匹配的行一律删、全删返回零行并带
  `station_rows_filtered:<n>` 与 `station_rows_all_filtered`（新夹具
  `station_rows_none`，夹具 84）；`ctw rail --limit` 与 `RailBackend.limit` 默认
  10→30。管理者实测（默认不带 --limit）：福州→武夷山 10 行全到武夷山北（删 20）、
  武夷山→福州 9 行、泉州→厦门 30 行零删；福州→建阳 30 行全删、报 no_results 加两条
  warning——南平市站其实在建阳区，前缀规则认不出，属已知假阴性（12306 站名不带
  行政区），今天不修。行程页火车腿显示到发站——`render/html.py` 新增纯函数
  `rail_station_names(booking_url)`（`fs`/`ts` 两端都带 `[A-Z]{3}` 站码才返回），
  Trip 页交通卡片一处、Journey 页交通汇总／交通卡片／逐日时间轴／预订清单四处加
  「车站：X → Y」，占位深链不显示；分组示例页多两行站名，README demo 与
  journey-16d 零字节差异；07-renderer 加一句。真实行程 r3 页重渲染为
  `福建中秋国庆16天行程-0.18.1.html`：9/26 腿四处显示「车站：福州南 → 武夷山北」，
  validate-html errors=0，QA failures=[]，横向溢出 0。合并后对真实 journey.json
  不指定车次重放刷新（默认 30 行）：默认路径选中 G1648 08:00→09:11 福州→武夷山北、
  3 条 claim、errors=0，replan 产出的 Trip 页也带站名行。
- 0.18.0（第十八波，两本都改行为）：replan 默认选车——`_select_refresh_service` 加
  `earliest_depart`（前一时段 `end_at`），无 `service_number` 时只在发车不早于它的
  候选里取最早到达，全不可行才抛 `refresh_overlap`（message 带候选数与前一时段结束
  时间）；有 `service_number` 命中多行且到达时间不同时抛新码
  `refresh_service_ambiguous`，事件可带 `arrive_at`（完整 ISO 或 `HH:MM`）挑一行；
  ADR-0015 末尾加 Amendment，README/SKILL 各加一句。12306 直达行按到发站过滤——
  `_filter_direct_rows`：站名等于解析候选名或以请求名去掉市/县/区后开头才保留（两
  条件取「或」；执行者第一版写成互斥，被真实数据推翻：12306 把武夷山解析到站名恰为
  「武夷山」的 WAS，30 行里没有一行到站叫武夷山，全是武夷山北/南平市），删行计入
  `station_rows_filtered:<n>`；执行者为保住 `mcp_stdio_server.py` 站名占位的 8 项
  子进程测试加了「证据门控」（某端至少一行确认匹配才过滤），留下全不匹配时不删的洞
  （第十九波去掉）；`leg_id` 纳入 `arrive_at` 与两个站码；`success.json` 加一张广州
  示例站车票，因为分组示例与 5 项 e2e 用同一份夹具回放两条路线；夹具 83；
  demo/grouped-departures 两个 leg_id 变。管理者合并后实测：`ctw rail --limit 30`
  福州→武夷山 10 行全到武夷山北（删 20）、武夷山→福州 9 行全从武夷山北/武夷山出发
  （删 21）、泉州→厦门 30 行零删；对真实 journey.json 不指定车次重放刷新，默认路径
  自动选中 G1648 08:00→09:11 福州→武夷山北、3 条 claim、errors=0（此前 10 趟撞
  9 趟）；会合 17:30 副本实网重规划的 north 9/26 腿变成 G1648 07:40→09:11 福州南→
  武夷山北（此前是到南平市站的 G2374），两条汇合航班与 80/62/18/7 不变。验收教训：
  `/usr/bin/python3` 是苹果自带的 3.9，字节码缓存在 `~/Library/Caches/com.apple.python/`
  而非 `__pycache__`，反向验证把 `>=` 改 `<=` 再还原时文件大小与秒级 mtime 都没变，
  缓存里留下改坏的版本，单跑 `tests.test_replan` 红了一轮；以后还原后 `touch` 源文件。
- 0.17.1（第十七波，一本改行为加一次真实行程实战）：VariFlight 票价一次调用覆盖整条
  路线——`_build_price_request` 改传 `subject_refs_by_service`（与 search 同构），
  `_live_price` 对返回行里落在表中的每个 `flightno` 各产一条 `/price` claim（仍取
  经济舱最低价），`_enrich_price` 拿全部 `route_flights` 逐班比价、逐班标 conflict
  （FlyAI 那条经 `conflict_claim_ids`），comfort 仍只给 `_select_flight` 那一班；
  每条路线仍 3 次调用；夹具 82（price.json 只改请求形状）。执行者与管理者各用真实
  Key 验证：昆明→福州两班真实航班得 2 条 `/price`；管理者用会合 17:30 的副本实网
  重规划真实行程：north 段 17 班航班全部带第二价（6 班判 conflict），两条被提升的
  汇合航班（昆明组 FU6538、北京组 SC2203）都带 `/price`，80/62/18/7 不变。真实行程
  火车票刷新实战（书 Z3 第三次派发）2026-09-12 跑通：`ctw rail` 9/26 福州→武夷山
  10 趟 ready → `journey extract` → refresh 事件 → `replan --rail-result`（north
  revision 2，trigger provider_change）→ `journey assemble --replace-trip`（journey
  revision 3）→ render/validate/validate-html/浏览器 QA 全过，产物 `journey-r3.json`
  与 `-r3.html` 只新增不覆盖，真实目录 45 个原文件字节不变；反向验证
  `--base-revision 1` 报 revision_conflict；管理者重渲染 r3 页 sha256 逐字节相同。
  链路缺陷两条（BLOCKED「书 Z3」）：①不指定 `service_number` 时
  `_select_refresh_service` 只按最早到达取车、不看是否早于前一时段结束，10 趟里
  9 趟撞 `refresh_overlap`，执行者显式指定 G1902（07:50→09:30，二等座 128.5）才
  走通；②12306 对同车次同发车不同到站返回两行（G1902 到武夷山北 09:30 与到南平市站
  09:15），`leg_id = stable_id("leg-rail", service, depart_at, from_ref, to_ref)`
  不含站码，两行同 id，claims 6 条重复写入、3 条游离。管理者复核：自己 00:39 的
  抓取同样两行同 id；即便 `--to 武夷山北` 查询，10 行里 8 行到达站仍是南平市（原
  武夷山东，建阳区），12306 按城市分组返回；实网重规划的 north 段 9/26 腿因此选到
  G2374 07:06→08:08 到南平市站的车。第十八波修。
- 0.17.0（第十六波，两本都改行为）：汇合腿（分组出发各组到会合点那条腿）——
  `_validate_meeting_anchor` 的调用点从 `_resolve_rail` 之后挪到 FlyAI/VariFlight
  解析之后，签名加 `claims`/`flights`、返回 `(legs, claims)`；铁路腿留不出
  `buffer_minutes` 时从 `enrichment.flights` 里取同路线、合规、到达最早的航班提升为
  汇合腿（`leg_id` 前缀 `leg-meeting-flight-`，`_is_meeting_arrival_leg` 只认带这个
  前缀的航班，其余比价航班照旧排除），被替换的铁路腿连同其 claims 删除、原航班
  条目的 claims 改指新 leg_id（`_swap_meeting_leg`）；铁路与航班都不合规仍抛
  `MEETING_BUFFER_INSUFFICIENT`，`arrival_at`/`actual_buffer_minutes` 改报两者里
  最早到达的那个；`_resolve_rail` 未动（执行者证明「先按缓冲过滤再取最早到达」
  与现状「直接取最早到达」逐场景等价，任务书猜的第三条红测试改动前就是绿的）；
  两份 README 各加一句；六套语料零差异。VariFlight 第二价源（ADR-0019 Option B）
  ——`_tool_call` 加 `action="price"` → `getFlightPriceByCities`（入参
  `dep_city/arr_city/dep_date`，返回每班航班的 `cabins[]`），`normalize` 新分支
  `_live_price` 按 `flightno` 取经济舱（`cabinclass=="Y"`）最低 `price` 产出
  `/price` claim（`subject_ref` = FlyAI 的 leg_id，status partial）；`_enrich_route`
  在 comfort 之后、只在非候选模式（真有 FlyAI 航班可比）发第三次调用；阈值
  `max(20, FlyAI 价×5%)`（`PRICE_CONFLICT_MIN_DELTA`/`PRICE_CONFLICT_RATIO`），
  超阈值时 VariFlight 那条直接标 conflict、FlyAI 那条经
  `VariFlightEnrichmentResult.conflict_claim_ids` 由 planning.py 两行补标；夹具 82
  （新增 variflight/price）；执行者与管理者各用真实 Key 验证（BJS→SHA 返回 69 条、
  KMG→FOC 真实航班三次调用、`/price` 判 conflict）。管理者用 0.17.0 实网重规划
  真实 16 天行程：原 request（会合 16:30）现在报 `adult-beijing` 组
  `MEETING_BUFFER_INSUFFICIENT`、`arrival_at` 16:10（铁路与航班里最早到达，缓冲 20
  分钟）——是数据事实不是缺陷；会合时间改 17:30 后整趟规划成功，两组汇合腿都成了
  航班（昆明组 06:50→09:40、北京组 13:25→16:10），north 段 19 条腿 = 15 条比价航班
  + 2 条汇合航班 + 9/26、9/29 两条铁路（9/26 已开售，12306 返回真实车次 07:06→08:08
  取代深链占位）；80 地点／62 有坐标／18 坐标 unknown／7 名字 unknown 与 0.15.3
  相同；`journey validate` 通过，页面 QA failures=[]、内部溢出 0。已知：VariFlight
  的 comfort/price 对象是 `_select_flight` 取的 FlyAI 列表第一班，不是实际被排进
  行程的汇合航班（后者只有 `/status`），两条路线的第二价都判 conflict（真实两价差
  超阈值）；FlyAI 住宿城市搜索返回的 10／9 家酒店与调研候选 8 家零重名，ADR-0019
  Option C 按名匹配今天没有真实用例。
- 0.16.1（第十五波，两处缺陷修复）：VariFlight 返回 `data={"error_code":…}`
  错误对象时按错误码降级（10→`no_results`、12→`invalid_request`、其余
  `upstream_5xx`，`_live_error_class`），不再判 `contract_mismatch`；`ctw doctor
  --probe` 的 VariFlight 探针从机场码 PEK 改成城市码 BJS；`CITY_IATA` 从 5 城扩到
  24 城，每城执行者都用真实 Key 查过一次（武夷山 WUS 对上海无直飞，用 WUS→CAN
  验证）；夹具 81。Journey 页头的路线串在「→」「／」后插 `<wbr>`，
  `.journey-title-route` 改 `overflow-wrap: anywhere`，真实 16 天行程页在 375px
  的 8 像素横向溢出归零；浏览器 QA 新增只上报不判失败的 `internalOverflow`
  字段。已知：真实页 3 张逐日卡片里带括号的 slot 标题 h3 仍比卡片宽 6px
  （`internalOverflow` 报 12），执行者实测 `word-break: break-all` 也治不了，判断
  是 CJK 右括号的字体墨水度量，不冒泡到页面级溢出，暂不处理。
- 0.16.0（第十四波，三本都改行为）：跨城路线的火车查询、机票查询、12306 深链
  与 VariFlight 城市码一律用地点的 `city` 而不是展示名 `name`（`planning.RouteSpec`
  五处消费者，缺 `city` 时回退 `name`；管理者用 fd2e618 旧代码对真实 16 天行程
  离线回放，差异只在两条汇合腿的深链 `fs`/`ts` 与随之变化的 claim id）；FlyAI
  返回 `status=1、data=null` 且 message 不含「结果为空」时按 `upstream_5xx`/
  degraded 降级、不再判 `contract_mismatch`（真因是空结果关键词白名单过窄，书
  AC3 猜的价格解析过严被真实抓取推翻），`ctw doctor --probe` 对 FlyAI 增加
  flight 探针并报 `capabilities` 子对象，夹具 80；Journey 页新增必需分区
  `location-overview`（每段每城一张离线位置示意，复用 `render/html.py`
  `_location_svg`，示例页 +728 字节，真实 16 天行程页渲染出 8 张）。管理者补
  一条锁住机票查询用 `city` 的测试。已知：真实行程页在 375px 宽度有 8 像素
  横向溢出，示例页没有，0.13 的页面就有，与本轮无关，待查。
- 0.15.4（第十三波，两份 ADR 加一次真实行程实网体检，代码零改动）：ADR-0018
  「地图与图片」（Proposed）裁定交互地图、静态图、图片字段都不做，Journey 页
  补上 Trip 页已有的离线位置示意 SVG（复用 `render/html.py` `_location_svg`，
  实测每段约 500 字节）；ADR-0019「第二价源」（Proposed）裁定火车票不做、
  机票做（把 VariFlight 已声明却从未派发的 `getFlightPriceByCities` 接到
  FlyAI 已有 leg_id 上，冲突走既有 `status=conflict`）、住宿排在机票之后、
  门票不做；真实 16 天行程用 0.15.3 整体实网重规划：80 个地点 62 有坐标、
  18 坐标 unknown（16 条是候选名写法、2 条服务商无数据）、7 名字 unknown
  （全部真歧义），并记下 5 条疑似代码缺陷——路线查询用地点展示名而非
  `city`、VariFlight 城市表只有 5 城、VariFlight 探针合同失败、FlyAI 探针
  只测住宿能力、FlyAI 机票价格解析比住宿严格（推测）。合并时管理者从
  ADR-0018 里清掉一处本机绝对路径并改正一处行号。
- 0.15.3（第十二波，两本纯重构，行为零变化）：`scheduler/light.schedule_day`
  133 行拆成 `_day_schedule_params`（frozen dataclass `_DayScheduleParams` 收口
  13 个参数）/`_classify_candidates`/`_beam_search`/`_finalize_day_schedule`
  （本体 13 行；`_evaluate` 签名收窄为 4 参数、计算体 94 行逐字节未动；管理者用
  0cc7d55 旧 worktree 对 28 份夹具 47 个 day problem 各叠加 13 种突变共 658 条
  记录回放，结果逐字节相同）；`providers/base.query` 157 行拆成
  `_preflight_failure`/`_execute_with_retries`/`_handle_rate_limited`/
  `_normalize_envelope`/`_build_result`（本体 14 行，最长 74 行；管理者对 79 份
  夹具加每个适配器 15 种合成传输层共 169 条记录回放，AdapterResult、progress
  事件序列与 sleep 时长逐字节相同）；两本各补一条精确断言测试。全仓最长函数
  降到 120 行（`mobility._resolve_poi_identity`），不再有函数超过 120 行。
- 0.15.2（第十一波，两本纯重构，行为零变化）：`VariFlightBackend.enrich` 167 行
  拆成 `_early_exit_result`/`_enrich_route`/`_build_search_request`/`_select_flight`/
  `_build_comfort_request`/`_backfill_claim_ids`/`_summarize_health`（本体 24 行，
  文件内最长 73 行；管理者用 d11c2cb 旧 worktree 对 6 种后端 × 3 种航班列表 × 3 种
  路线共 54 条记录回放，返回值与异常逐字节相同）；`journey._validate_connection`
  134 行拆成 `_check_connection_refs`/`_check_connection_lodging`/
  `_check_connection_transport`（本体 12 行；管理者对示例 16 天、six-city、
  sixteen-day 离线规划与真实 16 天行程各叠加 22 种段缝突变共 180 条记录回放，
  报告逐字节相同；执行者补了一条精确比对 `(code, path, message)` 的测试）；
  真实行程刷新实战同日第二次派发仍止步于日期门槛，9/12 起再发。
- 0.15.1（第十波三份并行书，行为零变化）：`validate_trip.semantic_issues` 197 行
  拆成 `_build_reference_context` + 11 个 `_check_*`（本体 16 行，文件内最长
  76 行是原有的 `_validate`；管理者用 404248e 旧 worktree 对 3 valid + 4 invalid
  夹具、4 份 demo trip、journey-16d 与真实 16 天行程的子 Trip、9 份 renderer
  突变各叠加 17 种确定性突变，共 486 条记录回放，报告逐字节相同；执行者新增
  一条精确比对 `(code, path, message)` 的测试）；两份 README 与 docs/design
  追平 0.9→0.15 的代码（四层站点解析、80 公里规则、`poi_around`、
  `deadline_kind` 四种措辞、`suspend`，15 条漂移全部处理；合并时管理者改正
  07-renderer §10 对 `deadline_kind=other` 措辞的一句误述——实际是
  「请在此之前完成」加「具体时间未提供」）；真实行程火车票刷新实战按任务书的
  日期门槛止步于任务 0（2026-09-11 早于 9/12 开售日），9/12 起重发。
- 0.15.0（第九波三份并行书）：站点距离富化的两遍 POI 查询限定火车站类目
  （`types=150200`）、一页取 25 条，AMap poi 合同加可选 `types`（实测子设施
  「出站口」「售票处」仍与父类目同返，但酒店、高速出口等噪音已滤掉，逐字同名
  站点更容易落在同一页）；`journey._merge_segment_trips` 213 行拆成 8 个
  `_merge_segment_*`（本体 53 行，管理者用 cab411f 旧 worktree 对 demo 16
  天、six-city 夹具与真实 16 天行程离线规划回放，journey sha256 全部相同）；
  ADR-0017（Proposed）裁定租车与轮渡的生产者暂不做——现状（手写 Trip +
  assumptions + suspend）已够用，若日后要做选 candidates.json 加 `transport`
  候选（方案 B），不动 trip.schema。合并时冲突标记曾漏进 PROGRESS/BLOCKED
  两个提交（本地），发版前已用两侧并存的方式修正。
- 0.14.0（第八波三份并行书）：12306 站点第四层——三层加剥后缀重试仍空且有
  AMap Key 时，用地名中心 50 公里内的火车站（AMap `/v5/place/around`，
  types 150200，新 capability `poi_around`）回查 12306 站码，候选带真实距离，
  warnings 加 `station_nearby_fallback`，查不到站码的丢弃、从不猜站（实网
  `--to 鼓浪屿` 从 no_results 变为 厦门 5.6 km / 厦门北 21.4 km 两个候选的
  ambiguous；无 Key 或三层命中时行为不变）；`validate_journey_html` 与
  `_shared_document_issues` 拆成 18 个 `_check_*`（本体 37/27 行，管理者用
  bf53f72 旧 worktree 回放 11 组页面突变，报告逐字节相同）；新增合成夹具
  `tests/fixtures/trips/schema/valid/rental-ferry.json`（轮渡腿 + 租车腿）
  三关全过，ADR-0016 验收命令 2、3 标记完成；夹具总数 79。
- 0.13.0（第七波三份并行书）：Journey 清单项带 `deadline_kind`
  （presale_open/declared/departure/check_in/other），优先事项与清单卡片按种类
  措辞——「开售日 2026-09-12 · 当天就买 · 09-26 出发」「预订截止」「出发前确认」
  「入住前确认」，中英两套，追踪属性 `data-deadline-kind` 由 validate_journey_html
  一并核对，item_id 不变；`suspend` 删非末尾腿时后面腿的
  `/transport_legs/N/...` unknowns 重编号（patch 里是 replace field_path）；
  `validate_html` 258 行拆成 13 个 `_check_*`（本体 32 行，文件内最长 74 行），
  管理者用 d22e3e6 旧 worktree 对 29 组夹具与 demo 回放，验证报告逐字节相同。
- 0.12.0（第六波三份并行书）：Journey 预订清单与优先事项按开售日排期——rail
  腿 deadline = 出发日减 14 天（复用 `providers/rail12306.py` 的 `PRESALE_DAYS`），
  `/booking_deadline` claim 优先，其余交通照旧，unknown 项共用同一规则（真实
  16 天行程的前三条优先事项变成 9/12、9/15、9/22 三个开售日）；`ctw replan`
  新增 `suspend` 事件（patch trigger `disruption`），一次删腿、换时段、删孤儿
  claim 与 unknowns、重算账本，ADR-0016 转 Accepted；12306 站点查询对带
  「市/县/区」后缀的城市名剥后缀重试一次（`--to 武夷山市` 从 0 趟到 10 趟，
  `query` 字段仍是用户原话），歧义候选的距离富化多一遍 `city_limit=false` 的
  全国搜索，只认站名逐字相同、类目火车站、离城市中心 ≤80 公里
  （`STATION_MAX_DISTANCE_METERS`）的唯一坐标，从不删候选或自动选站。已知
  限制：`suspend` 删掉非末尾的腿时，后面腿的 `/transport_legs/N/...` unknowns
  不重编号（`user_delete` 对时段有同款缺口）；优先事项卡片对开售日仍写
  「请在此之前完成」，`reason` 文案未渲染。
- 0.11.1（第五波三份并行书，纯重构 + 一份 ADR，行为零变化）：`MobilityBackend.resolve`
  366 行拆成 7 个私有方法（本体 32 行，文件内最长函数 120 行）；`plan_trip`
  266 行与 `_schedule_problems` 242 行拆成 13 个阶段命名的私有函数（各 56/25
  行，文件内最长 110 行）；两处拆分都用拆前快照逐字节比对，管理者另用
  ec7c12d 旧 worktree 回放 36 组 AMap 场景与真实 16 天 journey 离线规划，
  输出 sha256 全部相同。ADR-0016（Proposed）裁定租车与轮渡不改 schema：
  现有 `transportLeg` 已含 drive/ferry 与全部取还车字段，真缺口是
  `journey_booking_checklist`（journey.py）把 deadline 等同 depart_at、以及
  closure/weather 事件从不动 transport_legs/budget_ledger，两者都是代码改动。
- 0.11.0（第四波两份并行书 + 管理者合并修正）：`ctw research --city CITY
  --query TEXT [--max-results N] [--fixture FILE] [--fixed-clock ISO]
  --output-json OUT`，信封与退出码同 `ctw rail`（有结果 0、空结果或 Key
  missing 2、其他 1），无 Key 时不构造 HTTP 传输层、进度流零网络事件；
  `ctw doctor --probe` 的 anysearch 报 `credential` + `probe` 两层（探针用
  `get_sub_domains`，传输层加 `tool` 参数，新增 `probe_success`/`probe_401`
  两份夹具，夹具总数 78）；research Skill 第二档与两份 README 改为现状。
  浏览器 QA `scripts/qa_renderer_browser.py` 首条 CDP 握手等 30 秒
  （`--handshake-timeout`），超时则关掉 Chrome 重启一次再试，结果 JSON 报
  `handshakeAttempts`，`validate_report` 检查项一字未动；三处调用它的测试
  子进程 timeout 60→150。合并时管理者修正一处：`plan_trip`/`plan_journey`
  的 anysearch 健康行改为显式入参 `anysearch_configured`（默认 False），
  `ctw plan`/`ctw journey plan` 只在非 `--offline-fixture` 时读凭据——D2
  原实现在 planning.py 里直接读机器凭据，配置了 Key 的机器上
  `test_provider_health_and_business_calls_match_candidate_contract` 会红、
  demo 重生成会漂移；`tests/test_anysearch.py` 的 `AnySearchPlanHealthTests`
  4 项锁住这一点。
- 0.10.0（第三波）：Journey 页 `day-timeline`、`priority-actions`、
  `transport-overview` 三个分区，接口地址不再渲染成链接（E106/JH106），
  QA 脚本 `--sections`；AnySearch 真实 MCP JSON-RPC 合同（传输层
  `providers/anysearch_http.py`、Markdown 解析、夹具重建）；`ctw candidates
  import` 批量导入，全部通过才落盘。
- 0.9.0：`ctw replan --rail-result`（ADR-0015）与 `ctw journey assemble
  --replace-trip`；火车票原地刷新链路：`ctw rail --output-json` →
  `ctw journey extract` → `ctw replan --event refresh.json --rail-result` →
  `ctw journey assemble --replace-trip` → `ctw journey render`。
- 0.8.0：`replan_trip` 的 `refresh` 事件（库层）、`ctw journey
  extract/assemble`、设计文档与 schedule Skill 对齐 ADR-0014/0012/0010/0011、
  站点距离城市匹配接受 district、CONTRIBUTING 发版流程；tag 自 `v0.7.0`
  起，GitHub Release 自 0.8.0 起。
- 并行惯例：一波里只有一份书在主检出 `main` 直改，其余各在 `.tmp/wt-<名>`
  的 worktree 分支上干、只推分支，合并与冲突（PROGRESS/BLOCKED 末尾追加）
  由管理者解决；worktree 里不跑 `install_local_plugin.sh`。发版只推具体
  标签名，不用 `git push --tags`。本机若 `git push` 报 `SSL_ERROR_SYSCALL`，
  先 `curl --noproxy '*' https://github.com` 探直连，通就用
  `env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy git push`。
- 已知抖动：2026-09-10 GitHub CI 共四次在 `qa_renderer_browser.py` 起无头
  Chrome 时首条 CDP 命令 `Target.createTarget` 10 秒超时（3.9 两次；0.10.0
  发版提交 3.9 与 3.13 同时；D2 任务 3 提交 3.13 一次），`gh run rerun
  --failed` 即绿。0.11.0 起握手等 30 秒并重启一次，之后再出现请记在这里。
- 本机 Codex 与源码的差距：以 `bash scripts/install_local_plugin.sh --check`
  实时输出为准；`ctw doctor` 的 `runtime_root` 是缓存所在目录，可随时删除。

## 定位失败天花板

2026-09-06 用同一份真实福建 16 天行程反复重跑验证（78 个地点 = POI + 住宿）：

| 指标 | 数值 |
|---|---|
| 地点总数 | 78 |
| 定位成功 | 60 |
| 坐标 unknown | 12 |
| 名字 unknown | 6 |

坐标 unknown 的 12 条构成：`ambiguous_name_margin` 11 条（候选相距 300 米以上
的真歧义）、`geocode_ambiguous` 1 条（geocode 返回多个不同坐标；复现不稳定，
存疑）。另有 6 条名字 unknown：坐标已定位但名字仍存疑，`ctw candidates
fix-names` 会把它们列为人工项。

三条判定口径都在 `plugins/china-trip-weaver/src/china_trip_weaver/mobility.py`，
都是逐字/阈值的硬判断，历次任务书写成死规矩，不要在后续迭代里放宽：

- **行政区**：`_poi_admin_matches`——用户写的城市名与 provider 的 city 或
  district 之一剥后缀后逐字相等；POI 与 geocode 两条路共用。
- **名称歧义**：`_poi_name_is_ambiguous` + `POI_NAME_SIMILARITY_MARGIN`
  （0.15）+ `_name_similarity`，只放行「去重后唯一」与「首选逐字等于原名」。
- **坐标聚集**：`POI_COORDINATE_CLUSTER_MAX_METERS`（300 米）——同一次查询的
  全部候选两两都在 300 米内时，名字歧义不再阻断坐标，但名字仍留给人工。

放宽任何一条的代价都是假坐标，而假坐标比 unknown 更糟：用户会被导到错的地方。

## 已知短板

- **定位天花板**：见上节的 12 坐标 unknown + 6 名字 unknown，需要人工介入
  （`fix-names --export-manual` / `--apply-manual`）。
- **FlyAI 是唯一的价格来源**：住宿与航班的 AMap/VariFlight 兜底只发布
  `verify-on-click`，不给价格；FlyAI 本身是个人维护的第三方包装，可能停更。
- **12306 无官方站点距离**：站点候选靠 AMap geocode/POI 事后算距离兜底，命中
  同城精确站名才生效，未内置或跨城场景仍是 unknown 距离。
- **CI 的跳过口径**：没装 Codex 的 GitHub runner 会跳过三项 Codex 依赖测试（`OK (skipped=3)`），装了 Codex 的本机必须零跳过。2026-09-05 到 09-08 CI 曾因 Skill 解析 smoke 不跳过而连红 12 次，已于 2026-09-08 修复（提交 `b160501`，run 34217843374 全绿），经过见 `BLOCKED.md` 顶部条目。每次 push 后看一眼 `gh run list --limit 3`。

## 历史索引

- 2026-09-03 至 09-06 的完整逐轮任务书、实测证据与验收记录：
  [docs/history/progress-2026-09-03-to-06.md](docs/history/progress-2026-09-03-to-06.md)
  （原 `PROGRESS.md` 整体归档，一字未改，9119 行）。
- 2026-09-03/04 越界事实的唯一记录：`BLOCKED.md`（面向公众的产品未决问题，
  Open 区已于 2026-09-06 清零，现为存档）。
- 2026-09-08 至 09-12 的执行者逐轮记录（09-08 仓库瘦身与 0.7.0 发版、第一波到第二十二波 0.8.0 → 0.20.0）：
  [docs/history/progress-2026-09-08-to-12.md](docs/history/progress-2026-09-08-to-12.md)
  （2026-09-12 从本文件整体迁出，一字未改，7261 行）。

## 书 AM1「0.16.0–0.20.0 设计文档追平」任务 0（2026-09-12，main@2983165，≤10 行）

1. 目标：只把代码已实现且可 `git grep` 取证的铁路、航班、汇合腿、replan、Journey 账本与实现地图行为追平到四份现役设计文档，并用一条文档覆盖测试锁住 48 个运行时/脚本文件。
2. 顺序：任务 0 基线核对并提交 → 任务 1 新测试先红并提交 → 任务 2 逐条取证后写文档、反向验证、全量验收并提交 → push 与 CI。
3. 不改代码、README、Skill、ADR、schema；只写任务书白名单文件，拿不准的写 `BLOCKED.md` 后跳过。
4. 每句新增行为先把代码中的函数名、常量、warning、错误码和数字命中记录在本文件；查不到的不写。
5. 最大风险：设计文案把多个层次的真实行为压成一句后夸大适用范围，尤其 12306 双端过滤、VariFlight 错误分档、汇合腿候选顺序和 replan claim 清理。
6. 基线：HEAD=`2983165`、branch=`main`、worktree clean；全量 `Ran 684 tests in 46.488s`、`OK`、0 skipped；secret scan `0 finding(s) across 386 file(s)`。
7. 静态门：`uvx --from pyflakes pyflakes plugins/china-trip-weaver/src scripts tests` exit 0、诊断 0 行；系统 Python未预装 pyflakes，故用机器已有 uvx 临时运行，未改仓库或系统 Python 环境。
8. 漂移复现：四份目标文档逐份执行 `git grep -c` 查 `_filter_direct_rows|getFlightPriceByCities|_validate_meeting_anchor|refresh_overlap|anysearch_http.py`，均 exit 1、输出为空；`git grep -l -- '/Users/' -- docs/design` 同为 exit 1、输出为空。
9. 文件数现状：运行时 `*.py` 42 个、`scripts/*.py` 6 个，合计 48；当前无待裁决项。

## 书 AM1 任务 1：先写红测试（2026-09-12）

新增 `tests/test_design_docs.py`，且只有一个 `def test_`：枚举 `plugins/china-trip-weaver/src/china_trip_weaver/**/*.py` 与 `scripts/*.py`，硬断言总数为 48，并逐文件检查 basename 出现在 `docs/design/09-impl-map.md`。改文档前实测 `Ran 1 test in 0.005s`、`FAILED (failures=1)`，失败输出恰列 7 个缺名：`anysearch_http.py`、`build_plan_fixtures.py`、`build_provider_fixtures.py`、`build_renderer_fixtures.py`、`build_scheduler_fixtures.py`、`qa_renderer_browser.py`、`scan_secrets.py`；生产代码与设计文档尚未改。

## 书 AM1 任务 2：写文档前的代码证据（2026-09-12）

以下均在改四份设计文档前用 `git grep -n` 命中；行号属于 HEAD `91786dd` 的只读代码/测试：

```text
planning.py:73:    limit: int = 30
cli.py:345:    rail.add_argument("--limit", type=int, default=30)
cli.py:1229:                "limited_num": args.limit,
mcp_stdio.py:391:                            ticket_arguments["limitedNum"] = limited_num
rail12306.py:29:NO_INVENTORY = frozenset(("", "*", "无", "--", "候补", "售罄", "not available"))
rail12306.py:104:            raw_tickets, row_warnings = _filter_direct_rows(payload, station_candidates, request)
rail12306.py:372:def _filter_direct_rows(
rail12306.py:398:        warnings += ("station_rows_filtered:%d" % dropped,)
rail12306.py:400:            warnings += ("station_rows_all_filtered",)
mcp_stdio.py:746:        city_payload = _call_station_tool(client, body, "get-station-code-of-citys", city_arguments)
mcp_stdio.py:756:            payload = _call_station_tool(client, body, "get-stations-code-in-city", {"city": city})
```

`CITY_IATA` 的 `git grep -n -A25 'CITY_IATA = {'` 从 `variflight_enrichment.py:18` 命中到 `:43`，中间 `:19`–`:42` 恰为 24 条城市→IATA 映射；其余航空证据：

```text
variflight.py:24:    "getFlightPriceByCities",
variflight.py:112:                raise ProviderFailure(_live_error_class(rows.get("error_code")), ...)
variflight.py:287:    def _live_price(
variflight.py:326:def _live_error_class(error_code: Any) -> str:
variflight.py:327:    if error_code == 10:
variflight.py:328:        return "no_results"
variflight.py:329:    if error_code == 12:
variflight.py:330:        return "invalid_request"
variflight.py:331:    return "upstream_5xx"
variflight_enrichment.py:46:PRICE_CONFLICT_MIN_DELTA = 20.0
variflight_enrichment.py:47:PRICE_CONFLICT_RATIO = 0.05
variflight_enrichment.py:230:            self._enrich_price(
variflight_enrichment.py:235:    def _enrich_price(
variflight_enrichment.py:422:    threshold = max(PRICE_CONFLICT_MIN_DELTA, abs(flyai_amount) * PRICE_CONFLICT_RATIO)
flyai.py:34:        if body.get("status") in (401, 403):
flyai.py:36:        if body.get("status") == 429:
flyai.py:38:        if body.get("status") == 1 and body.get("data") is None and isinstance(body.get("message"), str):
flyai.py:40:            if "结果为空" in message or "no result" in message.lower():
flyai.py:42:            raise ProviderFailure("upstream_5xx", sanitize_text(message, 40))
```

流水线、replan 与 Journey 证据：

```text
planning.py:211:    transport_legs, claims = _validate_meeting_anchor(
planning.py:1503:_MEETING_FLIGHT_LEG_PREFIX = "leg-meeting-flight"
planning.py:1552:def _promote_meeting_flight_leg(
planning.py:1561:        if _meeting_leg_is_compliant(flight, meet_by, required_buffer)
planning.py:1564:    chosen = min(candidates, key=lambda item: (item["arrive_at"], item.get("depart_at") or ""))
planning.py:1594:def _validate_meeting_anchor(
planning.py:1648:            "code": "MEETING_BUFFER_INSUFFICIENT",
replan.py:349:def _select_refresh_service(
replan.py:371:        feasible = [item for item in same_day if str(item["depart_at"]) >= earliest_depart]
replan.py:374:            "refresh_overlap",
replan.py:377:    return min(feasible, key=lambda item: (item["arrive_at"], item["depart_at"]))
replan.py:380:def _disambiguate_service_matches(
replan.py:389:    requested_depart_at = event.get("depart_at")
replan.py:394:    requested_arrive_at = event.get("arrive_at")
replan.py:412:        "refresh_service_ambiguous",
replan.py:290:    claim_remove_indexes = sorted(
replan.py:291:        (index for index, claim in enumerate(trip["claims"]) if claim.get("subject_ref") == leg["leg_id"]),
journey.py:1665:def _with_missing_budget_ledgers(
journey.py:1672:        if "budget_ledger" in trip:
journey.py:1676:        ledger, budget_unknowns = _budget_ledger(
journey.py:1712:    ordered_trips = _with_missing_budget_ledgers(ordered_trips)
```

7 份 replan 名称由 `tests/fixtures/scheduler/manifest.json:121`–`:145` 的 `git grep -n` 命中：`closure.json`、`delay.json`、`refresh.json`、`suspend-first-leg.json`、`suspend.json`、`user-delete.json`、`weather.json`；`:5` 为 `"replan": 7`。实现地图缺失文件的代码/测试命中包括 `cli.py:1287`/`:1708` 的 `.providers.anysearch_http`，四个 builder 各自 `generated_by` 行，`tests/test_journey.py:1669` 的 `qa_renderer_browser.py`，以及 `tests/test_credentials.py:284` 的 `scan_secrets.py`。当前仍无待裁决项，现可开始写文档。

补充记录动笔前已查看的相邻命中：`rail12306.py:374`/`:375` 的 `station_candidates`/`request`、`:377`–`:380` 的 `from_resolved`/`to_resolved` 与 `from_prefix`/`to_prefix`、`:383`/`:384` 的 `from_station`/`to_station`；`planning.py:1537` 的 `meet_by` 缓冲计算、`:1545`/`:1546` 的同 `from_ref`/`to_ref` 过滤、`:1606` 的 `buffer_minutes`；`replan.py:234` 的 `_apply_refresh`、`:290`–`:296` 的旧 subject claims 倒序删除；`anysearch_http.py:29` 的 `AnySearchHTTPTransport`、`:76` 的 `method: "tools/call"`。这些行与上方主体证据一样均在写文档前只读核过，补录是为了让新文案里的标识符都有显式索引。

## 书 AM1 任务 2：文档与验收进度（2026-09-12）

- 四份文档已追平：04 增加 12306 行过滤/限量/未开售与飞常准第二价源/错误分档/FlyAI 空信封；06 增加 §5.4 汇合腿并补全 refresh 默认选车、消歧和旧 claim 清理；08 将 replan golden 改为 7 并列全名；09 补 `anysearch_http.py`、6 个脚本及 Journey 缺账本补算。
- 文档覆盖测试转绿：`Ran 1 test in 0.002s ... OK`。反向验证时先暂存 09，临时删其唯一 `scan_secrets.py` 行后 `Ran 1 ... FAILED (failures=1)`，missing 只列 `['scan_secrets.py']`；按任务书 `git checkout -- docs/design/09-impl-map.md` 还原后 `Ran 1 ... OK`。
- 14 个验收名的 `git grep -c -- <名> -- docs/design/0\*.md` 全部 exit 0：04 中 `_filter_direct_rows=2`、`station_rows_filtered=1`、`getFlightPriceByCities=1`、`PRICE_CONFLICT_MIN_DELTA=1`、`_live_error_class=1`、`CITY_IATA=1`；06 中 `_validate_meeting_anchor=1`、`MEETING_BUFFER_INSUFFICIENT=1`、`refresh_overlap=1`、`refresh_service_ambiguous=1`、`depart_at=2`；09 中 `_with_missing_budget_ledgers=1`、`anysearch_http.py=2`、`qa_renderer_browser.py=1`。
- 完整验收第 1 轮：`Ran 685 tests in 59.507s ... OK`，0 skipped；secret scan `0 finding(s) across 387 file(s)`；pyflakes exit 0、诊断 0 行；`git grep -l -- '/Users/' -- docs/design` exit 1、输出为空；`git diff --check` exit 0。
- 范围检查：`git diff 2983165 --name-only` 只列 `PROGRESS.md`、四份目标设计文档和 `tests/test_design_docs.py`；运行时 42 + scripts 6 = 48；新测试文件恰一个 `def test_`。当前无待裁决项。

## 书「文档订正：provider-contracts 与 README/SKILL 七处」任务 0（2026-09-15，worktree `.tmp/wt-docs` 分支 `docs-corrections`，≤10 行）

1. 目标：把 2026-09-15 健康审计查出的 7 处「文档写的」与「代码做的」不一致改对——`provider-contracts.md` 三处（12306 超时分档、AnySearch 10s、AMap/12306 降级链自相矛盾）+ README.md/README.zh-CN.md/两份 SKILL.md 共四处措辞。这一波四份书并行，我只做①文档订正，不碰代码/测试/脚本/CI/docs/design。
2. 顺序：任务 0 基线核对（本节）→ 任务 1 `provider-contracts.md` 三处 → 任务 2 README + 两份 SKILL.md 四处 → 全量测试与 secret scan 复跑 → `PROGRESS.md`/`BLOCKED.md` 收尾 → push `docs-corrections`（不合并 main）。
3. 最大风险：改动必须每处都有 `git grep` 证据支撑，不能凭感觉顺手改数字；两份 SKILL.md 被 `tests/test_skills.py` 校验 frontmatter 与路由，改动措辞后必须重跑全量确认没有撞上断言。误操作记录：任务 0 核对完成后第一次落笔时把 Edit 误写到了主检出（非 worktree）的 `PROGRESS.md`，已用 `git checkout -- PROGRESS.md` 在主检出还原、未提交、未影响 main，之后本节改在 worktree 自己的副本里；以后凡是写文件一律先确认路径含 `.tmp/wt-docs`。
4. 基线：worktree HEAD `5a7b071`、branch `docs-corrections`、clean；`/usr/bin/python3 -m unittest discover -s tests` → `Ran 685 tests in 117.311s`、`OK`，0 skipped；`scripts/scan_secrets.py` → `0 finding(s) across 388 file(s)`。与任务书给的审计基线（685 OK / 0 finding）一致，可以开工。

## 书「文档订正」任务 1：`provider-contracts.md` 三处（2026-09-15）

逐处先 `git grep` 核实再改，三处证据：① `interline` 全仓只出现在工具名/调用名上，从无独立超时分档；`cli.py:217`/`:251`/`:346` 三处 `--rail-deadline`/`--deadline` 默认值均 `default=90.0`（`git grep -n 'default=90.0' -- cli.py` 命中同三行）——12306 行「15s direct; 25s interline」改为「90s」。② `cli.py:358` `research.add_argument("--deadline", type=float, default=15.0)`，全仓无 AnySearch 相关的「10s」——AnySearch 行「10s」改为「15s」。③ `git grep -c 'cache_policy="bypass"'` 在 6 个源文件里合计 19，与 `git grep -c 'ProviderRequest('` 的 19 完全相等，`cache_policy="prefer"` 0 命中——12306 行与 AMap 行的「cache → 」前缀（与文档自身「R1 is disabled ... falls straight from R0 to R2」矛盾）一并删除。三处改完后 `git grep -n 'cache →' -- provider-contracts.md` exit 1（无命中），全量测试见下方任务 2 后统一跑一次。

## 书「文档订正」任务 2：README + 两份 SKILL.md 四处（2026-09-15）

1. `demo/multicity-5d/` 缺失：`git grep -c multicity README.md README.zh-CN.md` 改前 0/0；核实该目录已被 `git ls-files` 跟踪（request/candidates/trip.json/trip.html 四个文件都在）、`generated_at` 为 `2026-09-04T00:00:00+08:00`（与 base/guangzhou-shenzhen/grouped-departures 三组同源，非 journey-16d 的 `2026-09-05`），`tests/test_keyless_e2e.py:1456` 起的 `test_g1_multicity_cli_builds_ordered_one_way_transport_legs` 断言其交通腿严格单向（北京→上海→杭州→苏州，无回程腿）且每天精确对应一段覆盖当天的住宿。两份 README 在「grouped-departures 段」与「fifth example / 第五组示例」段之间各插入一段描述；插入后 `journey-16d` 段原有的「fifth example」/「其余四组 demo」措辞不必再改——这两处原文其实早就按「四组+第五组」计数写好了，只是缺这一段，插入后计数自动吻合。改后 `git grep -c multicity README.md README.zh-CN.md` 均为 1。
2. `README.zh-CN.md` 的 `docs/design/` 行「英文」→「中文」：`docs/design/00-README.md` 开头即中文「# ChinaTripWeaver 阶段二设计索引」。改后 `grep -n "docs/design/\`\](docs/design/00-README.md)" README.zh-CN.md` 命中该行且列「中文」。核对同一张表紧邻的 `docs/design/adr/` 行（任务书称其标注正确）时，发现该目录实际中英混合（`0001`–`0008` 共 8 个文件标题正文全中文，`0009`–`0019` 共 11 个全英文），这条不在任务书「7 处」授权范围内，按「顺手活不许做」原则未改动，已记入 `BLOCKED.md` 待裁决。
3. `search-china-lodging/SKILL.md`：`--keyless-trial` 原本紧跟在 `ctw plan` 示例句后，但 `git grep -n "keyless-trial" -- cli.py` 显示该 flag 只注册在 `lodging`（`:386`）与 `air`（`:397`）子命令，`plan` 没有。改法是把该句移到 `ctw lodging` 代码块之后、`ctw plan` 段落之前，并显式加一句「`ctw plan` has no such flag」消除歧义，而非仅在原位加限定语。
4. `research-china-destination/SKILL.md:48`：`candidates.py:59` 的 `automatic` 属性定义为 `replacement_name is not None`；`:658`-`:659`（`exact_original_confirmed` 分支）返回的 `preferred` 非 None（等于原名），故该分支 `automatic=True`，`cli.py:561` 循环据此打印 `CANDIDATE_NAME_AUTO` 而非 `MANUAL`。原句把「an unchanged normalized name」与「equally close alternatives」「conflicting Journey feedback」「malformed/unmatched feedback」并列成 manual-review 四件套，改法是把它从并列列表里摘出，单独说明「已匹配的名字自动确认、无需人工复核」。

全量验收：`/usr/bin/python3 -m unittest discover -s tests` → `Ran 685 tests in 213.317s`、`OK`，0 skipped（与任务 0 基线一致）；`scripts/scan_secrets.py` → `0 finding(s) across 388 file(s)`；`git diff main -- plugins/china-trip-weaver/src tests scripts .github docs demo` 为空；改动文件恰为 `PROGRESS.md`/`README.md`/`README.zh-CN.md`/`provider-contracts.md`/两份 `SKILL.md`（`BLOCKED.md` 随后追加）。7 处全部完成，1 处顺手撞见的 `docs/design/adr/` 混合语言问题已记入 `BLOCKED.md`，未在本书范围内改动。分支 `docs-corrections` 待 push。
## check-infrastructure（第二十五波四份并行书之一②检查基建，2026-09-15，worktree `.tmp/wt-infra`，分支 `check-infrastructure`）

**任务 0 核对**：HEAD `5a7b071`（含 09-15 健康审计记录）分出。三项基线逐字吻合：全量 `/usr/bin/python3 -m unittest discover -s tests` → `Ran 685 tests`、`OK`、0 skipped（152.5s，机器负载偏高不影响判断）；pyflakes 全仓（`plugins/china-trip-weaver/src tests scripts`）0 行；污染探针 `~/miniconda3/envs/core/bin/python -c "import tests; print(tests.__file__)"` 打出该环境 site-packages 里的路径而非仓库路径，确认任务书所述的命名空间包遮蔽问题属实。

**理解的目标／顺序／最大风险**：目标是把「没人会发现坏了」的三处报警器补齐并证明它们真会响，不是把已经绿的东西再刷绿一遍。顺序按任务书：先做任务 1（覆盖率脚本，最难），任务 2/3 与它互不依赖，之后并行推进。最大风险有二：覆盖率脚本必须能识别「跑不满」而非只看退出码；任务 3 的反向验证要求只在副本上改坏返回值、不碰仓库本体、不改 `_cmd_rail`。这两个风险在实际执行中都命中过一次真实教训，见任务 1/3 小节。

**任务 3 完成（`ctw rail` 端到端测试）**：新增 `tests/test_rail_cli.py`，5 个 `def test_`，走真实 CLI 子进程（`subprocess.run([str(CTW), "rail", ...])`，`CTW` 写法照抄 `tests/test_journey.py:61`），覆盖 `_cmd_rail`（`cli.py` 约 1190-1274 行）此前端到端零覆盖的全部退出码路径：`success.json`（exit 0，`item_count=1`，8 个输出字段齐全）、`empty.json`（exit 2，`error_class=no_results`）、`wrong_shape.json`（exit 1，`error_class=contract_mismatch`，证实 `Rail12306Adapter.query()` 内部已吞掉这类错误、不会让 `_cmd_rail` 走到未捕获异常分支）、`transfer.json`（exit 0，双腿结构）、指向不存在文件的 `--fixture`（exit 1，`RAIL_FAILED`，走 CLI 自身的 `OSError` 兜底分支）。5 项断言均先用真实子进程探测出实际退出码与字段，未凭空猜测。

反向验证：复制整份 `plugins/china-trip-weaver` 到 `.tmp/` 下的一次性副本，把副本 `cli.py` 里 `_cmd_rail` 成功分支的 `return 0` 改成 `return 3`（仓库本体全程未动一个字节）；用一个只在 `.tmp/` 下运行的驱动脚本把测试模块的 `CTW` 常量临时指向副本的 `ctw` 可执行文件重跑：5 项里精确 2 项（success、transfer，均依赖这一行）变红，另 3 项（empty、wrong_shape、missing-file，不依赖这一行）保持绿——证明测试确实在断言这个返回值，不是巧合。改回真实仓库路径重跑，5/5 绿。

**任务 2 完成（CI 补 pyflakes）**：`.github/workflows/ci.yml` 在 `Scan for secrets` 之后加一步 `Run pyflakes`：`pip install pyflakes==3.4.0`（与本机唯一已验证过的版本一致）后 `python -m pyflakes $(git ls-files '*.py')`。用 `git ls-files '*.py'`（75 个文件）而非历史上手动跑的 `plugins/china-trip-weaver/src tests scripts` 三目录范围，因为任务书明确点名前者；两者之差只有一个文件（`docs/design/schema/check_schema.py`），实测该文件本身 pyflakes 也是 0 行，扩大范围不会让 CI 意外变红。

反向验证：在 worktree 里给 `geo.py` 顶部临时插入一行未用导入，用 CI 里那条完整命令本地跑一次，得到该行的 `imported but unused` 报错、exit 1；`git checkout --` 还原并 `touch` 该文件后重跑，exit 0、零输出。

**任务 1 完成（覆盖率量法固化），含两处真实教训**：新增 `scripts/measure_coverage.py`，一条命令跑完：`/usr/bin/python3 -m venv` 建一次性隔离环境（固定用系统解释器，不提供任何在正常路径下切到别的解释器的开口）→ 装 `coverage`/`pyyaml` → 用官方 `sitecustomize.py` + `COVERAGE_PROCESS_START` 配方给子进程挂钩（测试里约 80 处 `subprocess.run` 直接调用真实 `ctw`，不挂这个钩子 `cli.py` 只能测到主进程自己直接 import 的部分）→ 全量跑 `unittest discover -s tests -v` → `coverage combine` → `coverage report --include="plugins/china-trip-weaver/src/*"`。落地前先用一条会经真实子进程调用 `ctw rail` 的用例单独探测过子进程追踪机制确实生效（仅那一条用例就能让 `cli.py` 测出 33%），才敢跑全量。

死规矩按要求实现：`assert_full_run()` 在打印任何覆盖率数字之前，同时检查「总数 ≥685」「报告 OK」「0 skipped」「磁盘上每一个 `tests/test_*.py` 文件都在这次跑的结果里至少出现过一次」，四条任一不满足就非零退出并点名具体是哪几个模块——不满足就不出报告，不猜、不放宽。已把 `.coverage*` 加进 `.gitignore`。

教训一（自己犯的 bug，当场发现当场改）：第一版用正则判断某模块是否跑过时要求形如 `tests.test_x` 的限定名前缀；实测对比 `discover -v` 与 `-m unittest tests.test_x -v` 两种调用方式的逐行输出后发现，`discover -s tests` 因为 `tests/` 没有 `__init__.py`（纯命名空间包），`-t` 缺省等于 `-s`，逐条结果统一只打裸模块名 `test_x`，从不带 `tests.` 前缀——按原正则会把全部 23 个测试文件都误判成「没跑过」，即使它们全部正常通过。改成同时接受裸名与限定名两种格式、按需补前缀后再比对，问题消失。

教训二（真实环境噪声，不是本脚本的缺陷）：第一次全量跑（389.8s，系统负载偏高）出现 3 个 FlyAI/VariFlight「live」用例因固定的极短 `deadline_ms`（100/1000/2000ms）超时失败——这几个用例会另起一个真实子进程充当假 MCP 服务端，`deadline_ms` 本就卡得很紧，子进程覆盖率追踪给每次子进程调用多付出的解释器启动开销偶尔会顶到这个上限。之后独立重跑三次（158.8s、204.6s，以及下方反向验证里污染解释器那次的 87.2s）均未再复现，确认是瞬时负载抖动，不是子进程覆盖率追踪方法论本身的系统性问题；`assert_full_run()` 按设计对这类抖动同样会正确拒绝出具报告，不会把偶发失败悄悄含混过去。

真实结果（把脚本临时整体移出 `scripts/` 做隔离验证时测得，原因见下方「已知冲突」）：`Ran 690 tests ... OK`、0 skipped，23 个测试模块全部确认跑过；`cli.py` 955 语句、miss 175、**82%**（比任务书基线 78% 高 32 行，恰好等于任务 3 新测试让 `_cmd_rail` 新增覆盖的行数）；总体 10642 语句、miss 1211、**89%**（比基线 88% 同样高 32 行，与 `cli.py` 的增量逐行对应，两者互相印证不是巧合）。

反向验证：`scripts/measure_coverage.py --force-interpreter` 指向被污染的解释器（跳过隔离与安装，直接裸跑该解释器，全程未写入其 site-packages 一个字节）→ `only 457 tests ran (need >= 685)`、精确点名 `tests.test_amap_live`、`tests.test_candidates`、`tests.test_journey`、`tests.test_keyless_e2e` 四个模块、退出码 1——与任务书记录的历史现象（452/685、同样这四个模块）精确吻合（457 = 452 + 本轮任务 3 新增且不受这个问题影响的 5 项）；捕获到的 traceback 里 `ModuleNotFoundError: No module named 'tests.test_providers'` 直接印证命名空间包遮蔽的真实机制。恢复默认调用方式重跑，得到上面「真实结果」一段的数字。

**已知冲突（写入 BLOCKED.md，非本书可解）**：新增的 `scripts/measure_coverage.py` 让 `tests/test_design_docs.py::test_runtime_modules_and_scripts_are_named_in_impl_map` 的硬编码计数从 48 变 49（该测试非递归枚举 `scripts/*.py`），且新文件名不在 `docs/design/09-impl-map.md` 里——两处修复点都在本书白名单之外（不许改现有测试、不许碰 docs/design），如实让这一项保持失败，未采用「塞进子目录绕开 glob」的取巧办法（那会让「每个脚本都要有文档」这条检查名存实亡，属绕过报警器而非解决问题）。因此：**交付状态下，不加任何参数跑 `scripts/measure_coverage.py` 会因这一个、且仅这一个原因正确拒绝出具覆盖率报告**——这是脚本按设计正常工作，不是它的缺陷；上面「真实结果」段的数字来自把脚本临时整体移出 `scripts/`（而非复制，避免两份文件同时被计数）单独验证，验证完毕已移回，`git status --short -- scripts` 确认只有这一个新文件、别无遗留。精确的两行修复点见 BLOCKED.md。

**全量最终校验**：`git diff main -- plugins README.md README.zh-CN.md docs demo` 为空；改动只有四处，均在白名单内：新增 `scripts/measure_coverage.py`、新增 `tests/test_rail_cli.py`、修改 `.github/workflows/ci.yml`、修改 `.gitignore`。

**管理者验收收尾（2026-09-15）**：上面那条「已知冲突」是任务书自身的内在矛盾——它既授权在 `scripts/` 下新建 `.py`，又禁止改现有测试、且要求测试数不许降，而 `test_design_docs.py` 把「运行时模块 + 脚本」的总数写死为 48，三条无法同时成立。执行者拒绝取巧、如实报红并给出精确修复点是正确处置。验收时由管理者解开：`tests/test_design_docs.py` 的计数 48 改 49，`docs/design/09-impl-map.md` 的 `scripts/` 树按字母序登记 `measure_coverage.py`（后者才是项目既有纪律——每个脚本都要在实现映射里有据可查）。收尾后实测：全量 `Ran 690 tests ... OK`；`scripts/measure_coverage.py` 直接跑通并出具报告，TOTAL 10642 语句 miss 1211 = **89%**（比健康审计基线 88% 高 1 点，来自新增的 5 项 `ctw rail` 端到端测试覆盖了原本零覆盖的 `_cmd_rail`）；CI 新增的 pyflakes 命令本地原样跑 exit 0；把 `RAIL_COMPLETE` 改成 `RAIL_DONE` 后 `test_rail_cli.py` 立刻变红、还原后复绿，确认新测试不是空转。
