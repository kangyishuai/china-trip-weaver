# PROGRESS

唯一的当前进度记录。2026-09-03 到 09-06 的逐轮任务书、实测证据、验收记录已归档，见「历史索引」。

## 现状速览（2026-09-10 实测，0.9.0）

- 版本：`0.9.0`，唯一来源是
  `plugins/china-trip-weaver/.codex-plugin/plugin.json` 与
  `src/china_trip_weaver/__init__.py` 的 `__version__`，两处一致，仓库内其余
  位置一律引用这两处之一，历史版本只以日期提及、不写字面值。
- 测试：仓库根 `/usr/bin/python3 -m unittest discover -s tests` 全量
  `Ran 534 tests`，`OK`，0 skipped；`scripts/scan_secrets.py` 0 命中；
  `~/miniconda3/envs/core/bin/python -m pyflakes plugins/china-trip-weaver/src
  tests scripts` 0 行。
- 0.9.0（第二波两份并行书）：`ctw replan --rail-result` 把 `refresh` 事件开放
  给命令行（ADR-0015）；`ctw journey assemble --replace-trip` 把改过的子 Trip
  换回原 Journey、版本加一、journey_id 不变。火车票原地刷新的完整链路：
  `ctw rail --output-json` → `ctw journey extract` → `ctw replan --event
  refresh.json --rail-result` → `ctw journey assemble --replace-trip` →
  `ctw journey render`。
- 0.8.0（第一波三份并行书）：`replan_trip` 的 `refresh` 事件（库层）、
  `ctw journey extract/assemble`、设计文档与 schedule Skill 对齐
  ADR-0014/0012/0010/0011、站点距离城市匹配接受 district、CONTRIBUTING
  发版流程；tag `v0.8.0` 与补打的 `v0.7.0`，GitHub Release 自 0.8.0 起。
- 并行惯例：一波里只有一份书在主检出 `main` 直改，其余各在 `.tmp/wt-<名>`
  的 worktree 分支上干、只推分支，合并与冲突（PROGRESS/BLOCKED 末尾追加）
  由管理者解决；worktree 里不跑 `install_local_plugin.sh`。发版只推具体
  标签名，不用 `git push --tags`。
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

## 本轮记录（2026-09-10，书 docs-drift：文档漂移清零 + 站点城市匹配接受区县，worktree `.tmp/wt-b` 分支 `docs-drift`）

- 任务 0（已完成）：`git worktree add .tmp/wt-b -b docs-drift`，HEAD `c9c9c15` 与任务书吻合；任务 1 五条 grep 当前均非零（确认漂移存在）、`adr`/`research` diff 为空，均与任务书吻合；`station_distance.py:261` 确为 `_city_matches`，只剥「市」且只比 `item.get("city")`；实测发现 POI 结果（`_station_point`）的 `district` 只在 claims 里（`providers/amap.py` 的 `_pois()` 把 `district` 塞进 `identity` claim value，item 本身无 `district` 键），geocode 结果（`_city_centre`）的 `district` 才是 item 顶层字段——任务书只说「同时比对 item 的 city 与 district」，未提这个不对称，动工前已核实清楚，不算对不上,不停。唯一数字出入是 pyflakes 全仓 10→11 行，已按「不停工只记录」写入 `BLOCKED.md`。
- 理解的目标：让文档说的与代码一致（任务 1）、测试代码零无用导入（任务 2）、火车站点距离对县级城市名不误判（任务 3）、发版流程写进 CONTRIBUTING（任务 4），四者独立无依赖。
- 顺序：任务 1 → 任务 2 → 任务 3 → 任务 4（任务书列出的顺序，互不依赖，按顺序省心）。
- 最大风险：任务 3 里 `_station_point` 的 district 藏在 claims 而非 item 顶层，直接照抄 `_city_centre` 的写法会拿到恒为 `None` 的 district、看似改了实则没变；对策是给 `_station_point` 补一次「先软取 identity（拿不到就 None，不 raise）→ 判 city-or-district → 通过后再走原有的严格 raise 校验」的改写，保证原有「城市匹配失败永不 raise、城市匹配成功后 claim 缺失才 raise」语义对两种情况（city 命中 / district 命中）都成立，不引入新的假阳性 raise。

任务 1（已完成，提交 `bee27e2`）：8 处文档漂移全部改成「现状＋依据」——license UNLICENSED→MIT（ADR-0012，3 处）、插件冲突检测从「宿主 source metadata 不确定」改成「`ctw doctor` 的 `skill_conflicts` 已用真实旧插件验证」（`BLOCKED.md` 2026-09-04 条目）、桌面/CLI 安装验证从「本阶段不执行」改成指向现役 `docs/manual-acceptance.md`/`scripts/install_local_plugin.sh`、非目标清单摘掉已实现的 Journey（>7 天）与 `traveler_groups`/`meeting_anchor`（README「Scope」）、语义验证标题从「阶段三需补」改成指向已实现的 `validate_trip.py:semantic_issues()`、AMap/12306 的「未实测/标 beta」改成指向 ADR-0011/ADR-0010 与仓库里没有 `beta` 标签的事实、OR-Tools 切换阈值三处（06-pipeline.md、08-testing.md、schedule Skill）改成指向 ADR-0014（已删除，不用第二引擎）。验收：五条 grep 全 0、`adr`/`research` 零改动、507 测试 OK。反向验证：把「7天/会合」现状注记误写成逐字引用原短语，grep 从 0 变回 1，改写措辞后再变回 0（真实的红→绿，非预演）。
任务 2（已完成，提交 `55ed68e`）：删 pyflakes 点名的 11 处无用导入/变量（5 个测试文件 + `scan_secrets.py` + 白名单外的 `build_plan_fixtures.py`，后者的越界判断记在 `BLOCKED.md`）。验收：pyflakes 0 行、507 测试 OK、`git diff main -- tests | grep 'def test_'` 0 行（此刻测出，晚于任务 3 提交后该数字会变为 2，属预期）。
任务 4（已完成）：两份 CONTRIBUTING 各加一节「Release」/「发版」，只写文档不执行：改 `plugin.json`+`__init__.py` 两处版本号 → 全量测试 → `bash scripts/install_local_plugin.sh` 装机 → `--check` 校验 → `git tag -a v<版本> -m "Release <版本>"` → `git push origin main --tags` → `gh release create v<版本> --generate-notes`；注明只有升版本号的改动才需要装机起的后续步骤。核对历史实际发版步骤时顺手发现 `0.7.0` 从未真正打过 tag 或建过 GitHub Release（`git tag -l`/`gh release list` 均无对应记录，只是提交信息以 `Release 0.7.0:` 开头），超出任务 4「只写不执行」的范围，记在 `BLOCKED.md` 供领导决定要不要补。验收：全量 509 测试 OK 0 skipped、secrets 0。

任务 3（已完成）：`geo.py` 新增 `administrative_area_key()`（照抄 `mobility.py` `_city_key` 的后缀剥离算法，未改动 `mobility.py` 本身）；`station_distance.py` 的 `_city_matches` 改用它，新增 `_city_or_district_matches()`；`_city_centre` 直接比对 item 的 `city`/`district`（geocode 结果两者都是顶层字段）；`_station_point` 因 POI 结果的 `district` 只在 `/provider_identity` claim 里，改成「先软取 identity（软取失败给 None，不 raise）→ 判 city-or-district → 通过后再走原有的严格 raise」，原有「city 不匹配永不 raise、city 匹配后 claim 缺失才 raise」语义对 district 命中的新路径同样成立。`tests/test_rail_station_fallback.py` 的 `StationAMapFixtureTransport` 加 `centre_city`/`centre_district`/`station_district` 三个可选参数（默认值＝原硬编码值，不影响已有 23 个测试);新增 2 个测试直接调 `AMapStationDistanceEnricher.enrich()`（不经 12306 fixture server，因为经它需要城市名与该 fixture server 硬编码的地名对上，不在本书白名单里）。验收：25 个 station 测试 OK、全量 509 测试 OK 0 skipped、pyflakes 0、secrets 0。反向验证：`git stash` 掉两处源码改动（用 `push -u -m` + 按 SHA `apply`+`drop` 的安全流程，不用裸 `stash`/`pop`）→ 正例测试红（`AssertionError: False is not true`）、负例测试仍绿（旧代码本来就更严格，不能反映回归）→ 恢复→ 25/25 绿。

## 本轮记录（2026-09-08，shim 合一 + doctor 运行时目录 + 0.7.0 发版）

- 目标：三个 provider 的 `*_home_shim.cjs` 合并为一个 `home_shim.cjs`（环境变量
  统一改 `CTW_ISOLATED_HOME`）；`ctw doctor` 报告加 `runtime_root` 字段；版本号
  升到 0.7.0 并跑 `install_local_plugin.sh` 刷进用户真实 Codex；清理仓库与
  已装缓存内约 1 GB 的 `.npm-cache`/`.tmp` 旧缓存。
- 顺序：任务 0 复核现状（已完成，逐条与任务书数字吻合）→ 任务 1 shim 合一 →
  任务 2 doctor 加字段 → 任务 3 升版本号并装机 → 任务 4 装机后清缓存、全量复测。
- 最大风险：三个 provider 目前各自硬编码不同的环境变量名与 shim 文件名，合并时
  漏改一处不一定报错（子进程会静默退回真实 HOME 而不是抛异常），需要靠反向
  验证（改错环境变量名跑测试应变红）而非只看正向全绿来确认；另外升版本号后
  安装脚本会真的执行 `codex plugin add` 写用户真实 Codex 配置，必须放在
  代码改完、测试全绿之后再做，避免把半成品刷进用户环境。
- 任务 1（已完成）：新建 `providers/home_shim.cjs`（环境变量统一
  `CTW_ISOLATED_HOME`），删除 `flyai_home_shim.cjs`/`rail_home_shim.cjs`/
  `variflight_home_shim.cjs`；`flyai_cli.py`/`mcp_stdio.py`/`variflight_mcp.py`
  各改两行（shim 文件名、环境变量名）；`tests/fixtures/{flyai_cli,mcp_stdio,
  variflight_mcp}_server.py` 各改两行同步校验；`docs/design/09-impl-map.md`
  的目录树三行合一行。验收：`git ls-files ".../providers/*.cjs"` 只剩
  `home_shim.cjs`；`git grep -nE 'CTW_(RAIL|FLYAI|VARIFLIGHT)_HOME|(flyai|
  rail|variflight)_home_shim' -- plugins tests docs/design` 0 行；全量
  `Ran 507 tests` `OK` 0 skipped（本次耗时 116.8s，机器负载所致，非回归）。
  反向验证：`mcp_stdio.py` 里 `CTW_ISOLATED_HOME` 临时改成
  `CTW_ISOLATED_HOM` → `tests.test_mcp_stdio` 报
  `test_rail_subprocess_receives_only_provider_environment` 失败（`'network'
  is not None`，红）→ 用 `sed` 备份还原 → `git diff --stat` 确认只剩两行
  预期改动 → 全绿（6/6 OK）。
- 任务 2（已完成）：`_cmd_doctor` 的 `payload` 字典加
  `"runtime_root": str(_repo_root())`（复用既有辅助函数，未新增计算逻辑）；
  `test_packaging.py:86` 后加 `self.assertEqual(str(ROOT), payload
  ["runtime_root"])`；两份 README 第 48 行原「仓库内 npm 缓存」的表述改为
  npm 缓存与隔离家目录建在含 `plugins/` 的那一级目录下（本地市场安装后即
  已装插件的缓存目录），`ctw doctor` 以 `runtime_root` 报出、可随时删除。
  验收：仓库根跑 `plugins/china-trip-weaver/scripts/ctw doctor | ... 
  payload["runtime_root"]` 输出等于 `pwd`（仓库根绝对路径）；全量
  `Ran 507 tests` `OK` 0 skipped；pyflakes 0 行；`git diff HEAD -- tests |
  grep '^[-+]\s*def test_'` 0 行（只在既有测试内加了一条断言，未增减测试
  函数）。
- 任务 3（已完成）：`__init__.py:3` 与 `plugin.json:3` 的版本号
  `0.6.0` → `0.7.0`。验收：`git grep -n '0\.7\.0' -- ':!PROGRESS.md'
  ':!BLOCKED.md' ':!docs/history'` 恰 2 行，同一 grep 搜 `0\.6\.0` 0 行；
  全量 `Ran 507 tests` `OK` 0 skipped。不设 `CODEX_HOME` 跑 `bash scripts/
  install_local_plugin.sh`，输出含 `已执行 plugin add china-trip-weaver@
  china-trip-weaver-local`、`plugin list: installed, enabled 0.7.0`、
  `OK：china-trip-weaver@china-trip-weaver-local 0.7.0 已安装且缓存与源码
  一致`；`codex plugin list | grep china-trip-weaver` 含 `installed,
  enabled  0.7.0`；已装副本 `$C/china-trip-weaver/0.7.0/scripts/ctw doctor`
  的 `runtime_root` 等于 `$C`（`/Users/kangyishuai/.codex/plugins/cache/
  china-trip-weaver-local`）；随后 `install_local_plugin.sh --check`
  exit 0、零差异（硬指标一之一提前达成）。
- 任务 4（已完成）：`du -sh` 实测仓库 `.npm-cache` 428M、`.tmp` 76M、已装缓存
  同名目录 429M/75M（合计约 1 GB）；`rm -rf .npm-cache .tmp/* $C/.npm-cache
  $C/.tmp` 保留 `.tmp/.gitkeep`。验收：`test -f .tmp/.gitkeep && test !
  -e .npm-cache && test ! -e $C/.npm-cache` 输出 `CLEANED`；全量
  `Ran 507 tests` `OK` 0 skipped。「`git status --short` 为空」这条验收在
  任务 4 自身执行时刻不可能字面成立（任务 1/2/3 的源码改动尚未提交），判断
  与裁决记在 `BLOCKED.md`；本轮提交信息以 `Release 0.7.0` 开头、未 push
  后复查，`git status --short` 确已为空，字面要求最终也满足。
- 终验（提交后复核）：`codex plugin list` 含 `installed, enabled  0.7.0`；
  `install_local_plugin.sh --check` exit 0、`OK：...已安装且缓存与源码一致`；
  `CLEANED`；全量 `Ran 507 tests` `OK` 0 skipped；pyflakes 0 行；
  `git diff b1577b7 HEAD -- tests | grep '^[-+]\s*def test_'` 0 行（与任务书
  基线提交比较，测试函数数量不变）；shim grep 0 行；版本 grep `0.7.0` 恰 2、
  `0.6.0` 0 行。四项任务与硬指标一、二全部达成，任务书结束，无遗留阻塞项。

## 本轮记录（2026-09-08，书 C：cli.py 的 main 拆分）

- 目标：`cli.py` 的 `main`（706 行、13 个 `if args.command` 分支）拆成每个子
  命令一个 `_cmd_<name>` 函数加分发表，`_parser`（235 行）拆成每个子命令一个
  `_add_<name>_parser`，行为一个字节不变；`main`/`_parser`/`_probe_layers`/
  `_doctor_probe_report` 四个名字与签名原地不动（测试从
  `china_trip_weaver.cli` 导入并打补丁）。
- 顺序：任务 0 冻结 `--help`/`canonicalize`/`rail`/`validate` 四组金样
  （`.tmp/goldens/`，被 `.gitignore` 挡住不提交）并核对哈希，与任务书对照
  逐一吻合 → 任务 1 拆 `main` → 任务 2 拆 `_parser` → 终验两次反向验证。
- 最大风险：13 个分支里 `candidates`/`journey` 各自还有 4 个子子命令分支，
  且共享局部变量（如 `candidates` 分支的 `clock` 在 `add-poi`/`add-lodging`
  间共用）——直接摘取会漏传参数；用「把共享局部变量在分发函数里算好、经参数
  传给子函数」的方式规避，不改变计算时机与顺序。
- 任务 1（已完成）：`main` 拆成分发表 `main` （29 行）+ 13 个 `_cmd_<name>`
  函数；`candidates`/`journey` 两个有子子命令的分支各自再拆成 1 个分发函数
  + 4 个子函数（`_cmd_candidates_init/fix_names/add_poi/add_lodging`、
  `_cmd_journey_validate/render/validate_html/plan`）。搬移全程剪切—去缩进
  —把用到的局部变量或必须的上下文（`progress`、`credential_path`、
  `poi_name_transport`、`clock`）改成参数，不重写任何逻辑、不合并任何重复
  代码、不改任何消息文本；每个 `_cmd_*` 只声明自己实际用到的参数（不是所有
  函数塞同一组参数），`main` 里的分发表用闭包把不同函数的不同参数补齐——
  `{"validate": lambda: _cmd_validate(args), ...}`。额外实现了任务书标注为
  「建议」的一项：6 处重复的 `repo_root = Path(__file__).resolve().parents
  [4]` 合成 `_repo_root()` 辅助函数，计算内容不变（`__file__` 在同一模块内
  取值恒定，提取不影响结果）。验收：`py_compile` 通过；pyflakes 0 行；函数
  长度量表 `main` 29 行、最长函数（`_cmd_rail`/`_cmd_lodging_air`）85 行，
  均低于 50/120 的门槛（`_parser` 233 行是任务 2 的范围，尚未拆）；任务 0 的
  四组金样在拆分后重新生成到 `.tmp/after/`，`diff -r .tmp/goldens .tmp/after`
  空输出；全量 `/usr/bin/python3 -m unittest discover -s tests` `Ran 507
  tests` `OK` 0 skipped；`git diff HEAD --stat -- tests demo plugins/china-
  trip-weaver ':!*cli.py'` 为空，只有 `cli.py` 改动。
- 任务 2（已完成）：`_parser`（235 行）拆成 `_parser()`（21 行，只剩创建顶层
  parser、`--version`/`--progress`、`commands = parser.add_subparsers(...)`
  与按原注册顺序逐个调用）+ 14 个 `_add_<name>_parser(commands)`（对应 14 个
  `commands.add_parser(...)` 调用：validate、validate-candidates、
  candidates、canonicalize、doctor、plan、journey、replan、rail、mobility、
  lodging、air、render、validate-html）。`candidates`/`journey` 各自的 4 个
  子子命令解析没有像任务 1 那样再拆——任务书原文是「按子命令拆」，且两者单个
  函数分别只有 76/47 行，仍在 120 行门槛内，拆到子子命令一级不是任务书要求，
  按「不重写逻辑」的最小改动原则保留为一个函数。参数类型统一标 `commands:
  Any`（`Any` 已在文件顶部导入），未采用 `argparse._SubParsersAction`（真实
  存在但带下划线的半私有名字），降低无谓风险。验收：`py_compile` 通过；
  pyflakes 0 行；`main` 29 行、`_parser` 21 行、最长函数仍是 `_cmd_rail`/
  `_cmd_lodging_air` 85 行；任务 0 的四组金样重新生成，`diff -r .tmp/goldens
  .tmp/after` 空输出；全量 `Ran 507 tests` `OK` 0 skipped。
- 终验：README「Run the synthetic demo」里 `ctw plan --request
  demo/request.json ...` 那条命令原样跑完，`git status --short -- demo` 为
  空（重新生成的 `demo/trip.json`/`demo/trip.html` 与已提交内容字节相同）；
  `git diff --check`、`git diff --cached --check` 均空；`git diff HEAD
  --stat` 只有 `PROGRESS.md`、`cli.py` 两个文件。反向验证一：给
  `_add_canonicalize_parser` 的 help 文案尾部加一个 `X` → 重生成
  `.tmp/after` → `diff -r .tmp/goldens .tmp/after` 在 `help.txt` 报出该行
  差异（红）→ 还原 → 重生成 → 空输出（绿）。反向验证二：把
  `_cmd_validate_candidates` 的形参 `args` 改名为 `args_renamed` 而不改函数体
  用法 → pyflakes 报 3 处 `undefined name 'args'`（红）→ 还原 → pyflakes 0
  行（绿）。`BLOCKED.md` 本轮追加「无待裁决项」记录（书 C 小节）。

## 本轮记录（2026-09-08，仓库瘦身第二轮）

- 目标：`docs/design/` 内与 `plugins/`、`tests/fixtures` 字节相同的 7 份 schema
  副本、13 行本机路径、14 处幽灵模块名/旧 Skill 名归零；改正第一轮
  （commit `5faedf6`）留下的三处记录错误。完成后设计文档没有需手工同步的副本。
- 顺序：任务 0 基线复核（507 测试 OK、secrets 0、残留 grep 13、幽灵 grep 14、
  重复对 10、`--check` 真实差异 15，全部与任务书吻合）→ 任务 1 删 schema 副本
  并改校验器指向真身 → 任务 2 替换幽灵模块名/旧 Skill 名 → 任务 3 改正
  `BLOCKED.md`/`PROGRESS.md`/`install_local_plugin.sh` 的记错与截断。
- 最大风险：删 `docs/design/schema/` 后遗留死链或 `test_packaging.py` 断言与
  真实目录不符；改动仅限 `.md` 与两行脚本/测试，不碰 `plugins/`、
  `tests/fixtures` 源文件本身。
- 任务 1：删 `docs/design/schema/` 下 7 个与 `plugins/`、`tests/fixtures` 字节
  相同的文件（`trip.schema.json` + `examples/valid` 2 个 + `examples/invalid`
  4 个），只留 `check_schema.py`。`00-README.md`、`03-trip-model.md` 的校验
  命令与相对链接改指向 `plugins/china-trip-weaver/schema/trip.schema.json`、
  `tests/fixtures/trips/schema/{valid,invalid}`，注明需 `pip install
  jsonschema`，不写个人路径；`00-README.md` §4.1/4.3 里裸 `design`/`research`
  路径一并改成 `docs/design`/`docs/research`（原样不可运行，改后逐条实测通过）。
  `tests/test_packaging.py:103` 的字节比对改为断言目录只剩 `check_schema.py`。
  执行中发现任务书未列的隐藏依赖：`tests/test_contracts.py` 另有两个测试用
  `ROOT / "docs" / "design" / "schema" / ...` 分段拼路径引用同一批被删文件
  （字面量 grep 搜不到），删除后全量测试炸出 1 个 `FileNotFoundError`。该文件
  不在任务书「只允许改」名单内，但删除 7 个文件本身是任务书明确要求、507 测试
  全绿是写明的最终门，两者字面冲突且无人可问；判断按 `test_packaging.py:103`
  同款手法（断言真实状态，不放宽不 mock 不删测试）就地改掉这两个测试更接近
  「说的与代码一致」，已完整记录取舍与红→绿证据在 `BLOCKED.md`。反向验证：
  `touch docs/design/schema/x.json` → `test_packaging` 红 → 删除 → 绿；
  `docs/design/schema/{ghost.json,examples/x.json}` → `test_contracts` 两处
  分别红 → 删除 → 绿。
- 任务 2：`docs/design` 非 ADR 的 `.md` 里 `search-china-trains`→
  `search-china-rail`、`search-china-flights`→`search-china-air` 全部替换
  （`02-plugin-skills.md` 7 处、`09-impl-map.md` 4 处，ADR-0009 原文不动）；
  `02-plugin-skills.md:140/141/143` 的 `degrade.py`/`scheduler/ortools.py`/
  `renderer.py`+`validate_html.py` 改指向 `mobility.py`/`planning.py`、
  ADR-0014、`render/html.py`+`render/validate_html.py`。`09-impl-map.md` 顶部
  加「实际目录树（2026-09-08）」（`git ls-files plugins/china-trip-weaver/src
  tests/test_*.py` 的真实结果），原「未来目录树」标题改为「阶段三设计稿，
  实现前所写」，说明模块名与今日代码的出入是历史设计稿而非现状。
- 任务 3：`BLOCKED.md` 里书 36「`docs/design` 重复文件与本机路径清理……没有
  复现」在文末追加更正——实测 13 行／10 对，错在 grep 模式
  `/Users/[a-zA-Z]+` 与只在 `docs/design` 内查重，本书任务 1/2 已清零；同时把
  该项从本文件「不做的技术债」清单里摘掉。`现状速览` 里写死的过时文件计数
  改为「以 `--check` 实时输出为准」并列出实测的 13 个 differ + 2 个
  only-in-cache；「已知短板」删掉过时的 `pace=slow` 遇紧凑行程直接结构化无解、
  不做梯度降级的条目（书 8 任务 3 早已实现三步降级压缩）。
  `scripts/install_local_plugin.sh:112` 去掉 `| head -5`，改为先打「共 N 处
  差异」再列全部，实测 N=15、无截断。
- 最终门：全量 `Ran 507 tests` `OK` 0 skipped；`scan_secrets.py` 0 命中；四个
  `build_*_fixtures.py` 跑完 `git status --short -- tests/fixtures demo` 为
  空；`--skill-smoke` 输出 `SKILL parser smoke: OK`；`git diff --check` 与
  `git diff --cached --check` 均空；`git diff HEAD -- tests | grep '^[-+]\s*
  def test_'` 0 行；`git diff HEAD --stat -- plugins tests/fixtures .github
  README.md` 为空。硬指标一逐项复核：残留 grep 0、幽灵 grep 0、重复对 3、
  `--check` 差异行 15、任务 3 要清空的两条过时表述均已清零（本段落本身避免
  逐字复述那两个短语，以免自己把 grep 计数顶回非零）。

## 本轮记录（2026-09-08，仓库瘦身）

- 任务 1：`git mv PROGRESS.md docs/history/progress-2026-09-03-to-06.md`，
  内容与哈希不变；重写本文件（本节持续更新）。
- 任务 2：删 `cache.py`、`scheduler/ortools_bridge.py`；从 `evidence.py`、
  `contracts.py`、`errors.py` 分别删 `EvidenceLedger`、`MatrixCell`、
  `ValidationFailure`；`tests/test_evidence.py`/`test_scheduler.py`/
  `test_providers.py` 按点删除对应用例与断言行（净删 9 个 `def test_`）。
  过程中发现 `planning.py` 对 `credentials.SUPPORTED_KEY_NAMES` 的导入虽自身
  不用，却被 `keyless.py`（生产兼容导出层）与 `test_keyless_e2e.py` 经
  `china_trip_weaver.planning` 二次导入；直接删会破坏生产代码
  `keyless.py`。改为照抄仓库既有惯例（`keyless.py`/`scheduler/__init__.py`
  同款写法）给 `planning.py` 加 `__all__ = ["SUPPORTED_KEY_NAMES"]` 显式
  再导出，行为不变、pyflakes 归零。新增
  [ADR-0014](docs/design/adr/0014-remove-ortools-bridge.md)，
  ADR-0005 状态改为 Superseded by ADR-0014。
- 任务 3：版本号单源到 `__init__.py` 的 `__version__` 与 `plugin.json`。
  `providers/mcp_stdio.py` 改 `from .. import __version__`；
  `test_credentials.py`/`test_packaging.py`（两处）/`test_skills.py` 的字面量
  改成 `__version__`（`test_skills.py` 原本不导入包，补了 `sys.path` 与
  import，照抄同目录其他测试文件的既有写法）；`test_contracts.py` 改
  `assertRegex(__version__, r"^\d+\.\d+\.\d+$")`；README 两份的 0.6.0 那句
  改成"版本与 `plugin.json` 的 `version` 一致"。版本 grep 恰 2
  （`plugin.json:3`、`__init__.py:3`）。反向验证：`__version__` 改 0.6.1 →
  `FAILED (failures=2)`（`test_packaging`、`test_skills` 各一处，均因与真实
  `plugin.json` 的 0.6.0 对不上）→ 改回 → `Ran 507 tests` `OK`。
- 任务 4：`test_plugin_conflicts.py` 的 `HOME=/nonexistent-ctw-home` 改用本文件
  已有的 `TemporaryPluginRoot`（内部即 `tempfile.TemporaryDirectory(dir=ROOT
  / ".tmp")`），子进程写脏的目录变成随用例结束自动清理的临时目录。反向验证：
  `git stash push tests/test_plugin_conflicts.py` 复现污染（`nonexistent-
  ctw-home/` 重新出现）→ `git stash pop` 恢复 → 全量 `Ran 507 tests` `OK`，
  `nonexistent-ctw-home` 不再出现。

## 本轮记录（2026-09-10，`ctw replan --rail-result` 命令行接线；main 直改，第二波并行之一）

任务 0 核对（HEAD `7fc66ec`）：525 测试 OK 0 skip、`scan_secrets` 0、pyflakes 0
行；`replan.py:25` `replan_trip` 已带 `rail_result: Optional[Mapping[str, Any]]
= None`；`cli.py:272` `_add_replan_parser`、`1156` `_cmd_replan` 均无
`--rail-result`；`test_replan.py:221` 的 CLI 循环测试 docstring 明写
refresh.json 因 CLI 未接线被排除，`run_replan_fixture`（59 行）已透传
`rail_result=fixture.get("rail_result")`；README.md 第 182 行、README.zh-CN.md
第 181 行均为 `ctw replan` 用法行；`docs/design/adr/0015-refresh-event.md`
尚不存在。全部与任务书吻合，不停工。额外核实：`_apply_refresh`
（replan.py:232）内 `_find_rail_leg` 先于 `rail_result is None` 判断执行，
`refresh.json` 夹具的 `rail_result` 顶层含 `provider="12306-mcp"`+
`transport_legs`+`claims`+`health`，与 `_cmd_rail`（cli.py:1121 的
`output` 字典）写出的真实形状逐字段对应。
理解的目标：给 `_add_replan_parser` 加 `--rail-result`，`_cmd_replan` 按事件
type 决定必填/禁止、只查文件顶层形状（provider/transport_legs/claims/
health），其余深度校验交给既有 `replan_trip`；成功/失败沿用
REPLAN_COMPLETE/REPLAN_FAILED 与失败不写输出文件的既有保证；测试扩到 5 夹具
+2 条新负向、README/SKILL/ADR-0015 同步。
顺序：任务 1（parser+`_cmd_replan`接线）→ 硬指标一四条命令验收 → 任务 2
（测试+文档+ADR）→ 反向验证 → 最终门。
最大风险：非 refresh 事件禁止 `--rail-result`是`replan_trip`本身不做的校验
（它只在 `event_type=="refresh"` 分支才用得到这个参数），必须在 CLI 层新增
判断，用普通 `ValueError` 走既有 `except (OSError, ...) ` 分支即可，不需要
新的 `ReplanError` 码;而"refresh 缺 `--rail-result`"已经是
`replan_trip`/`_apply_refresh` 的既有行为（`refresh_result_required`），
CLI 只需把 `rail_result=None` 照常传下去，不必重复判断。

任务 1（已完成，提交见下）：`_add_replan_parser` 加 `--rail-result`（`type=Path,
default=None`），`--event` 的 help 追加 refresh 与 `--rail-result` 的搭配说明。
`_cmd_replan` 在读完 event 之后、校验 base Trip 之前插入两步：① 判
`event.get("type")=="refresh"`，非 refresh 却给了 `--rail-result` 直接
`raise ValueError`；② 给了 `--rail-result` 就 `read_json` 读入并只查顶层
形状（`provider=="12306-mcp"` 且 `transport_legs`/`claims` 为 list、`health`
为 dict），不做更深校验；随后原样传给 `replan_trip(..., rail_result=rail_result)`
（refresh 缺 `--rail-result` 时 `rail_result=None`，交给 `replan_trip` 已有的
`refresh_result_required` 校验，CLI 不重复判断，与开工笔记的风险预判一致）。
`read_json` 已保证返回 dict 且非 dict 会 `raise ValueError`，故未在 CLI 侧
重复 `isinstance(rail_result, dict)` 判断（照抄 `_cmd_rail` 校验 `--fixture`
顶层形状时的同款写法，不判外层类型只判内层字段）。
硬指标一实测（2026-09-10）：正向命令
`ctw replan --trip demo/trip.json --event .tmp/refresh.json --rail-result
.tmp/rail.json --base-revision 1 --fixed-clock 2026-10-15T12:00:00+08:00
--output-json .tmp/trip-r2.json --output-html .tmp/trip-r2.html` → exit 0，
`REPLAN_COMPLETE ... trigger=provider_change ...`；`ctw validate
.tmp/trip-r2.json` → `VALID`；`ctw validate-html .tmp/trip-r2.html
.tmp/trip-r2.json` → `HTML VALID ... errors=0`；`grep -c G1001
.tmp/trip-r2.html` → 2；`git status --short -- demo` 空。反向 1（refresh 缺
`--rail-result`）→ exit 1，stderr `REPLAN_FAILED refresh_result_required
refresh requires a rail_result`，两个输出文件均不存在。反向 2（`delay.json`
事件 + `--rail-result`）→ exit 1，stderr `REPLAN_FAILED --rail-result is
only valid when --event has type refresh`。
连带发现并修复：改 `--event` help 文案后，既有测试
`test_cli_kind_field_reports_type_contract`（`test_replan.py:292`）对
`--help` 输出做逐字 `assertIn`，命中旧文案而失败——这是任务书明确要求的
文案变更的直接连带后果，不是放宽断言，已把该测试期望的字符串同步改成新
文案（结构与断言强度不变，仍是逐字匹配）。全量
`/usr/bin/python3 -m unittest discover -s tests` → `Ran 525 tests` `OK`
0 skipped；`scripts/scan_secrets.py` 0 命中；pyflakes（src+tests+scripts）
0 行；`git diff --stat` 只有 `PROGRESS.md`/`cli.py`/`tests/test_replan.py`
三个文件，均在白名单内。任务 1 单独一次 `git commit`（`4216c59`）。

任务 2（已完成）：`test_all_four_replan_fixtures_run_through_cli_and_render`
（`test_replan.py:221`）循环夹具从 4 个扩到 5 个（新增 `refresh.json`）；
`"rail_result" in fixture` 时把该字段写到临时目录下的兄弟文件、传
`--rail-result` 给子进程，其余 4 个夹具不带该参数（沿用既有行为字节不变）；
断言从 `assertEqual(4, ...)` 改 `assertEqual(5, ...)`。方法名本身刻意
**不改**——`test_all_four_...` 现在覆盖 5 个夹具、名字与内容不再一致，但
本任务书「规矩」明写 `git diff 7fc66ec -- tests | grep '^-\s*def test_'`
须 0 行，改名等价于删一行旧签名、加一行新签名，会让该 grep 非空；用
docstring 首句说明「方法名早于 refresh.json 接线、故意不改」替代改名，
字面合规优先于名字准确。新增 2 个 `def test_`：
`test_cli_refresh_without_rail_result_fails_without_outputs`（用
`refresh.json` 整份夹具直接当 `--event`，不给 `--rail-result` → exit 1、
stderr 含 `refresh_result_required`、两输出文件均不存在）、
`test_cli_non_refresh_event_with_rail_result_fails`（`closure.json` 事件 +
`_refresh_rail_result()` 写临时文件当 `--rail-result` → exit 1、stderr 含
新增的 CLI 校验文案、两输出文件均不存在）。两份 README「Other commands」
块只改 `ctw replan` 那一行（加 `[--rail-result RAIL.json]`），说明性文字加
在代码块之外，紧跟既有「运行时不使用第三方包」那句之后，不触碰块内其余行
（遵守本书与 A2b 书的接缝约定）。`replan-china-trip/SKILL.md` 在既有单命令
示例后加一段「先 `ctw rail --output-json` 再 `ctw replan --rail-result`」
的两步示例与必填/禁止说明。新建
[docs/design/adr/0015-refresh-event.md](docs/design/adr/0015-refresh-event.md)，
记「只换证据不改结构、离线、火车腿先行」三条边界（对应任务书「我替领导
拍的板」）。
验收：`git grep -n 'rail-result' -- README.md README.zh-CN.md
plugins/china-trip-weaver/skills/replan-china-trip/SKILL.md` 三个文件各
≥1 行（实际 2+2+3）；`test -f docs/design/adr/0015-refresh-event.md`
存在。全量 `Ran 527 tests` `OK` 0 skipped（525 基线 + 本任务 2 个新
`def test_`）；`scan_secrets.py` 0 命中；pyflakes 0 行。
`git diff 7fc66ec --stat -- plugins ':!*cli.py'` **非空**（只有
`SKILL.md` 一行 9 处新增）——与白名单、任务 2 正文的明文要求直接冲突，
判断为任务书自身遗漏，已保留 `SKILL.md` 编辑，完整取舍与证据记在
`BLOCKED.md` 顶部（书「ctw replan --rail-result」任务 2 条目）。
反向验证（终端记录）：临时把 `_cmd_replan` 里
`replan_trip(..., rail_result=rail_result)` 改成
`replan_trip(..., rail_result=None)  # TEMP-REVERSE-VERIFY` →
`test_all_four_replan_fixtures_run_through_cli_and_render` 的 `refresh.json`
子测试报 `AssertionError: 0 != 1 : REPLAN_FAILED refresh_result_required
refresh requires a rail_result`（红）→ 还原 → `git diff 7fc66ec -- cli.py |
grep -c TEMP-REVERSE-VERIFY` 为 0（残留标记已清零）→ 重跑同一测试转
`ok`（绿）。任务 2 单独一次 `git commit`（提交见下）。

最终门（2026-09-10 实测）：`/usr/bin/python3 -m unittest discover -s
tests` → `Ran 527 tests` `OK` 0 skipped；`scripts/scan_secrets.py` 0
命中；`~/miniconda3/envs/core/bin/python -m pyflakes
plugins/china-trip-weaver/src tests scripts` 0 行；`git diff 7fc66ec --
tests | grep -E '^-\s*def test_'` 0 行；`git diff 7fc66ec --stat --
tests/fixtures` 空（一字未改）。硬指标一、硬指标二（除已记录并说明的
`SKILL.md` 一处例外）均达成。BLOCKED.md 本轮追加一条判断记录（书
「ctw replan --rail-result」任务 2），无其他待裁决项。

任务 1（`4216c59`）、任务 2（`f2b0f34`）各一次 `git commit` 后
`git push origin main`；`gh run list --limit 3` 三条全 `success`
（`f2b0f34` 对应 run `34454031335`，1m4s；此前两条 `7fc66ec`/
`c208ba0`+`f27989b` 一线也都是 `success`）。任务书结束，硬指标一、
硬指标二全部达成（硬指标二的 `SKILL.md` 例外已在 BLOCKED.md 完整记录取
舍与证据），无遗留阻塞项，止损轮次未触发（1 轮验收即全绿，未连败）。

## 本轮记录（2026-09-10，`replan` 支持 `refresh` 事件；main 直改，三书并行之一）

任务 0 核对（HEAD `c9c9c15`）：507 测试 OK 0 skip、`scan_secrets` 0、
`provider_change` 仅见于 `trip.schema.json:819`、`ctw rail --fixture`
回放腿的 `depart_at` 不随 `--date` 变、demo/trip.json 两条 12306-deep-link
腿各带 `service_number`+`price/amount` 两条 unknown 且有 `budget_ledger`，
均与任务书一致。唯一出入：任务书写路径 `src/china_trip_weaver/replan.py`，
实际是 `plugins/china-trip-weaver/src/china_trip_weaver/replan.py`（
`tests/test_replan.py` 的 `SRC` 常量可证，仓库内唯一一份，无歧义，按实际
路径改，不算待裁决）。目标：给 `replan_trip` 加 `rail_result` 关键字参数与
`refresh` 事件分支，离线把 `ctw rail --output-json` 形状的候选车次接回某条
火车腿，只碰 `replan.py`/`test_replan.py`/新增夹具。顺序：先读
`_resolve_rail`/`_budget_ledger`/`V_TOP_MODE`/既有 4 金样，再写
`_apply_refresh` 与配套小函数，最后负向测试与反向验证。最大风险：
demo/trip.json 首个午餐 POI 的 `opening_windows` 与原排程零余量，`_shift_
slots` 顺延分支容易撞违规（后已验证：只影响"晚到"分支自身的 `validate_
trip`，与 refresh 主逻辑无关，处理见下）。

任务 1：`replan_trip` 尾部加 `rail_result: Optional[Mapping] = None`；
`VALID_EVENT_TYPES` 元组加 `"refresh"`（同步给事件类型报错文案，仅此一处
按任务书允许扩成含 refresh）；`_TRIGGER_BY_EVENT_TYPE` 把 `refresh` 映射到
`provider_change`。新增 `_apply_refresh`/`_find_rail_leg`/`_select_
refresh_service`/`_recompute_rail_health`/`_recompute_top_mode` 五个函数。
规则均照任务书：只认 rail 腿，否则 `refresh_not_rail`（任务书未点名的
错误码，判为"目标未解析出火车腿"这一类，与"缺 rail 结果"等五个既定码同款
命名风格）；给了 `service_number` 精确匹配同日车次，否则取同日最早到达；
跨日到达 `refresh_unsupported`；与上一槽重叠 `refresh_overlap`；晚到复用
既有 `_shift_slots(trip, day, slot_index+1, delta, ...)` 顺延（沿用其"起始
槽不做锁前置检查"的既有语义，与 `delay` 对被顺延目标槽本身的豁免同款，
非五个必测负向场景之一，未额外改 `_shift_slots` 本身）；有 `budget_ledger`
按 `journey.py:1230` 同款调用 `_budget_ledger` 重算；`12306-mcp` 的
`provider_health` 按 `_resolve_rail` 口径重算（trip 内全部 rail 腿
`data_mode=="live"` → ready/live，否则 degraded/static），`reason` 文案为
本轮自撰而非逐字复刻 `_resolve_rail` 内部原始 errors 列表（那份列表来自
运行期 `AdapterResult`，replan 侧拿不到，判为可自主选择的措辞）；顶层
`mode` 按 `V_TOP_MODE` 的不等式方向只在当前值不够保守时才上调，不做无条件
覆盖（避免把与本次刷新无关的既有更保守 `mode` 意外拉低，超出"重算"本意）。
日程槽位的 `claim_ids` 同步成新腿的 `claim_ids`（任务书未列，但与仓库内
"槽位 claim_ids 镜像腿 claim_ids"的既有模式一致，不同步会导致日程与证据
脱节）；旧的两条 claim 不删，只 append 新证据（`validate_trip` 未见"claim
必须被引用"的规则，任务书原文只说"追加"）。新增 `tests/fixtures/scheduler/
replan/refresh.json`（base=demo/trip.json，G1001 早到 08:00→12:00、票价
553，走既有 `run_replan_fixture`）；`run_replan_fixture` 加 `rail_result`
透传（4 个既有夹具无此键，默认值不受影响）；`test_all_four_replan_
fixtures_run_through_cli_and_render` 从 glob 改成显式 4 个 CLI 已支持
文件名单——`ctw replan` CLI 还不认 `rail_result`（接线是下一本书、`cli.py`
只读），把 refresh.json 塞进这个跑 CLI 子进程的循环必然失败，属被迫的
必要改动，四个既有断言力度未变（仍要求恰好 4 个、逐个跑通 CLI+渲染+
`validate_trip`）。

任务 1 门（2026-09-10 实测）：`/usr/bin/python3 -m unittest discover -s
tests` → `Ran 509 tests` `OK` 0 skipped（507 基线 + `test_replan_refresh`
+ `test_replan_refresh_resolves_to_live_service`）；硬指标一（demo/
trip.json 一条深链腿经 refresh 后 provider=12306-mcp、service_number
非空、两条 unknown 消失、`validate_trip`/`validate_html` 全过、补丁可
回放）由这两个测试共同覆盖，均通过；既有 4 个金样字节不变。单独一次
`git commit` 提交（`c208ba0`）。

任务 2：新增 8 个测试，覆盖必测 5 项（`refresh_no_same_day_service_
fails`/`refresh_requested_service_number_not_found_fails`/`refresh_
cross_day_arrival_unsupported`/`refresh_locked_leg_rejected`/`refresh_
requires_rail_result`）+ 3 项补充（`refresh_rejects_non_rail_subject`/
`refresh_rejects_overlap_with_previous_slot`/`refresh_later_arrival_
shifts_subsequent_same_day_slots`，覆盖 `refresh_not_rail`/`refresh_
overlap`/顺延机制本身；最后一项不经 `run_replan_fixture`、不断言
`validate_trip`，因为如上"最大风险"所述，任何晚到都会把首个午餐槽顶出
其零余量 `opening_windows`，与 refresh 逻辑正确性无关，只断言操作产生的
槽位时间本身）。反向验证两次，终端记录：①临时把"删 unknown"的两行改成
`pass` → `test_replan_refresh`/`_resolves_to_live_service` 均
`AssertionError: 31 != 17` → 还原 → 两测试转 `ok`；②临时把 `_TRIGGER_BY_
EVENT_TYPE["refresh"]` 改成 `"delay"` → 两测试均
`AssertionError: 'provider_change' != 'delay'` → 还原 → 转 `ok`；两次均
额外用 `git diff c9c9c15 -- plugins/.../replan.py | grep -c TEMP-REVERSE`
确认改动已完整撤回（0 行残留）。

最终门（2026-09-10 实测）：`/usr/bin/python3 -m unittest discover -s tests`
→ `Ran 517 tests` `OK` 0 skipped；`scan_secrets.py` 0 命中；
`~/miniconda3/envs/core/bin/python -m pyflakes plugins/china-trip-weaver/
src` 0 行输出；`git status --short` 只有本轮改的文件；`git diff c9c9c15
--stat -- plugins ':!*replan.py'` 空；`git diff c9c9c15 -- tests | grep -E
'^-\s*def test_'` 0 行；既有 4 个金样（`closure`/`weather`/`delay`/`user-
delete.json`）单独 `git diff c9c9c15 --stat` 为空，一字未改。任务 1、任务 2
各一次 `git commit` 直接提交 main（任务 1 为 `c208ba0`，任务 2 为
`f27989b`）。BLOCKED.md 本轮无新增待裁决条目。

`git push` 后 `gh run list --limit 3` 首次显示 `f27989b` 那条
`completed failure`：Python 3.9 矩阵在
`test_keyless_html_opens_offline_with_no_remote_requests`
（`test_keyless_e2e.py`，走 `scripts/qa_renderer_browser.py` 起无头
Chrome 做离线 QA）上 `TimeoutError: CDP pipe read timed out`；同一提交的
Python 3.13 矩阵全绿，本机单独重跑该测试也是 `ok`，且该测试与 `replan`/
`refresh` 无任何依赖关系（不在本轮允许改动的文件之列）。判断为 CI runner
偶发的无头浏览器启动超时，`gh run rerun 34447222187 --failed` 重跑后两条
矩阵均转 `success`（`gh run list --limit 3` 三条全 `success`）。

## 书 A2：journey extract/assemble（2026-09-10，分支 journey-assemble）

本书在 `.tmp/wt-a2`（分支 `journey-assemble`）里干，只推分支不合并，界限见
任务书「界限」节。与并行的书 B（`docs-drift`）、书 A1（main 直接改
`replan.py`）地界不重叠。

- 任务 0 核对：HEAD `c9c9c15` 与任务书一致；全量 `Ran 507 tests` `OK` 0
  skipped，`scan_secrets.py` 0 命中，均与任务书数字吻合。`journey.py` 行号
  核对：`_bridge_segment_lodgings` 1181、`_ensure_boundary_lodging` 1283、
  `_segment_connections` 1339、`assemble_journey` 1408，与任务书完全一致。
  「两份 README」实指根目录 `README.md`+`README.zh-CN.md`（没有
  `plugins/china-trip-weaver/README.md` 这个文件）。`_segment_connections`
  硬取 `right["budget_ledger"]["items"]`：Trip 缺账本会 `KeyError`，属实——
  但 `journey_budget_ledger`（1485）与 `_validate_connection`（2160，读
  `right.get("budget_ledger")` 后判断 `isinstance`）都已经对缺账本 Trip 容
  错，全仓库只有 `_segment_connections` 这一处没有容错，这是「账本缺失时价
  格字段置 None」唯一需要动的地方。README 第 134 行段落（journey-16d 固定
  时钟/revision）逐字核对通过；`expected_segment_days` 实际嵌套在
  `journey["segmentation"]["expected_segment_days"]` 而非顶层字段，但值确
  为 `null`，与任务书表述一致（只是路径写得粗略）。
- 理解的目标：给 `journey.py` 加两个只读的新函数——
  `extract_trip_from_journey`（从 Journey 按 `trip_id` 取子 Trip，deepcopy
  后返回，找不到就 `ValueError`，不碰任何既有函数）与
  `assemble_journey_from_trips`（按 `start_date` 排序 Trip，住宿连接从 Trip
  自身 `lodgings` 直接判定「是否已覆盖边界夜」，交通连接复用改过的
  `_segment_connections`），CLI 各包一层 `journey extract`/`journey
  assemble` 子命令，不改任何既有子命令的行为。
- 顺序：Task 0 核对 → Task 1 extract → Task 2 assemble → Task 3 补测试，与
  任务书顺序一致——assemble 的验收（往返 `cmp`）依赖 extract 先能跑。
- 最大风险：`assemble_journey` 结尾本来就会调用 `validate_journey` 做穷尽
  性校验（`J_DATE_GAP`/`J_LODGING_STATUS`/`J_TRANSPORT_*` 等 20+ 种结构化
  错误），所以「相邻段日期必须首尾相接」这类断裂检查不需要在 assemble 入口
  重复手写，可以直接依赖这个既有校验兜底；核对下来这个判断成立（任务 2 的
  反向验证——把住宿 check_in 改晚一天——命中的正是 `validate_journey` 里的
  `J_LODGING_HANDOFF`，不是我自己写的检查）。真正必须手写的断裂只有一处：
  左段自己找不到覆盖边界夜的已选住宿时，没有下游校验能替我发现，只能在
  `assemble_journey_from_trips` 自己的住宿匹配循环里直接 `raise`。
- 任务 1（extract）：`extract_trip_from_journey(journey, trip_id)` 遍历
  `journey["trips"]` 按 `trip_id` 精确匹配，`copy.deepcopy` 后返回；找不到
  `raise ValueError("Journey does not contain Trip %s" % trip_id)`。CLI
  `ctw journey extract --journey J.json --trip-id T --output-json T.json`，
  失败路径在 `write_canonical_json` 之前就 `raise`，不会写文件。验收：对
  `demo/journey-16d/journey.json` 的三个 trip_id 各取到
  `.tmp/t{1,2,3}.json`，`ctw validate` 三份均打 `VALID`；未知 trip-id 打
  `JOURNEY_EXTRACT_FAILED Journey does not contain Trip
  trip-does-not-exist`，exit 1，`.tmp/bad.json` 未生成。
- 任务 2（assemble）：新函数 `assemble_journey_from_trips(trips, request,
  clock, expected_segment_days=None)`——按 `request["start_date"]` 排序 Trip
  （原文用 `request`，这里等价于按 `trip["request"]["start_date"]` 排序）后
  依次调用三步：① 新写的 `_assembled_lodging_links`（`_bridge_segment_
  lodgings` 第二段循环的只读版：左段末日城市里找自己 `lodgings` 中
  `check_in <= overnight < check_out` 的已选住宿当 `outgoing`，右段按
  `check_in == next_start` 找 `incoming`，比 `candidate_ref` 得
  continued/changed/departing；找不到 `outgoing` 时用
  `_no_stay_conflict(overnight, final_city, left["lodgings"])` 抛结构化
  `ValueError`——`_no_stay_conflict` 本身就是通用的"候选池找不到覆盖某夜的
  住宿"诊断，改传 Trip 自己的 `lodgings` 当"候选池"完全适配，不用另造错误
  形状）；② 复用（未复制）改过的 `_segment_connections`——唯一改动是
  `right["budget_ledger"]["items"]` 硬取改成 `right.get("budget_ledger")` +
  `isinstance` 判断，账本缺失时 `budget_item=None` 从而
  `price_type`/`amount_min_cny`/`amount_max_cny` 均为 `None`，这个改动对
  `plan_journey` 现有调用方零影响（原来的 Trip 一定有账本）；③ 复用未改的
  `assemble_journey` 做最终组装与校验。刻意不在入口手写"相邻日期必须首尾
  相接"检查——`assemble_journey` 结尾必然调用的 `validate_journey` 已经
  穷尽性覆盖 `J_DATE_GAP`/`J_DATE_OVERLAP`/`J_LODGING_*`/`J_TRANSPORT_*`
  20+ 种断裂，重复手写是造轮子；任务书要求的反向验证也证实了这一点，命中
  的正是这条已有校验。CLI `ctw journey assemble --request R --trip T1
  [--trip T2 ...] [--expected-segment-days N] [--fixed-clock ISO]
  --output-json J.json`，`--trip` 用 `action="append"` 支持重复。验收
  （往返一致）：`ctw journey assemble --request demo/journey-16d/request.json
  --trip .tmp/t1.json --trip .tmp/t2.json --trip .tmp/t3.json --fixed-clock
  2026-09-05T09:00:00+08:00 --output-json .tmp/j.json` 后
  `ctw canonicalize .tmp/j.json` 与 `ctw canonicalize
  demo/journey-16d/journey.json` 的输出 `cmp` 无差异（`journey_sha256` 与
  demo 原文一致）。反向验证：把 t2 第一晚（Hangzhou，check_in
  2026-10-06）改成 2026-10-07 → `JOURNEY_ASSEMBLE_FAILED Journey validation
  failed: J_LODGING_HANDOFF /segment_connections/0/lodging_continuity/
  to_lodging_id the following multi-day Trip must name its first selected
  stay`，exit 1，`.tmp/j-broken.json` 未生成 → 还原 t2 → 重新 assemble →
  cmp 再次无差异。额外手测（非任务书要求，为任务 3 的账本缺失场景探路）：
  从 t2 删掉 `budget_ledger` 并同步删除指向 `/budget_ledger/` 的
  `unknowns`（否则 `validate_trip` 报 `J_TRIP_V_UNKNOWN_PATH`——纯删
  `budget_ledger` 键会留下指向它的 unknown 指针，这不是"缺账本 Trip"的正确
  构造方式，必须两者一起删）——assemble 后连接 0 的
  `cross_segment_transport` 三个价格字段均为 `None`，`ctw journey validate`
  打 `VALID`。
- 任务 3（测试收口）：`tests/test_journey.py` 新增 `JourneyExtractAssembleTests`
  类，6 个 `def test_`（任务书要求至少 5 个）：
  `test_extract_returns_each_trip_as_an_independently_valid_standalone_document`
  （extract 成功，三段各自 `validate_trip` 通过）、
  `test_extract_unknown_trip_id_is_a_structured_error`（extract 未知
  id）、`test_extract_then_assemble_round_trips_the_checked_in_demo_byte_for_byte`
  （往返一致，Python API 层面用 `canonical_json` 比对，等价于任务书要求的
  CLI `cmp`）、`test_a_boundary_lodging_gap_between_extracted_trips_is_a_structured_j_error`
  （断裂报错，复用任务 2 验收里已证实会命中 `J_LODGING_HANDOFF` 的同一个
  变异——把 t2 第一晚住宿 check_in 改晚一天——断言异常消息含 `"J_"`）、
  `test_assemble_tolerates_a_trip_without_a_budget_ledger`（缺账本 Trip 可
  拼，断言连接价格三字段为 `None` 且 `validate_journey` 通过）；第 6 个
  `test_cli_journey_extract_and_assemble_round_trip_the_checked_in_demo` 是
  任务书未强制要求的额外补充，走真实 `ctw` 子进程（而不是直接调 Python
  函数）把 extract→assemble 全链路过一遍，顺带验证 CLI 层"失败不写文件"
  （对未知 trip-id 断言 `missing_path.exists()` 为 `False`）——这一层任务
  2/3 的纯 Python 测试都覆盖不到，因为 `write_canonical_json` 调用点在
  `cli.py` 里，不在 `journey.py` 的函数体内。`from china_trip_weaver.journey
  import (...)` 顶层导入块按字母序插入 `assemble_journey_from_trips`、
  `extract_trip_from_journey`；新增 `from china_trip_weaver.contracts import
  canonical_json`。反向验证：`git stash push -u -m
  "wt-a2-reverse-verify-journeypy" -- .../journey.py`（只挪 journey.py，
  未触碰 cli.py/tests，遵循环境提示"禁止裸 stash"的要求，用 tag 定位、
  `apply` 不用 `pop`）→ `python -m unittest tests.test_journey` 整个模块
  `ImportError: cannot import name 'assemble_journey_from_trips'`（顶层
  import 失败会让全文件 51 个测试一起报错，不止新增的 6 个，属于比"新测试
  红"更强的证据）→ `git stash apply <sha>` 恢复 → 重跑
  `Ran 51 tests ... OK` → `git stash drop <sha>` 清理，`git stash list`
  确认为空。全量 `Ran 513 tests`（507 + 新增 6）`OK` 0 skipped。

## 书 A2b：journey assemble --replace-trip（2026-09-10，分支 journey-replace）

任务 0 核对（worktree `.tmp/wt-a2b`，HEAD `7fc66ec`）：全量 `Ran 525 tests` `OK`
0 skipped、`scan_secrets.py` 0 命中（368 文件）、pyflakes 0 行，均与任务书吻合；
journey.py:1551 `extract_trip_from_journey`、:1563
`assemble_journey_from_trips(trips, request, clock, expected_segment_days=None)`
行号精确吻合；cli.py:259 assemble 解析器 `--request`/`--trip` 确为 required；
demo/journey-16d/journey.json 的 revision.number=1、三段、journey_id
`journey-d7d147568550c48c`；delay.json 的 event 为
`{"type":"delay","subject_ref":"slot-2","delta_minutes":15,...}`，无
`base_trip` 键，需另配 extract 出的 trip 文件跑 `ctw replan`。全部核对一致，
无出入。

理解的目标：`journey assemble --replace-trip` 把 replan 后的子 Trip 放回原
Journey，连接/账本靠 `assemble_journey_from_trips` 重算，revision 加一、
journey_id 不变。
顺序：任务 1（`replace_trip_in_journey` + CLI 接线，两条反向验证）→ 任务 2
（≥4 新测试 + 文档，红→绿反向验证）。
最大风险：`assemble_journey_from_trips` 强制完整 `#/$defs/request` schema
校验（`destinations`/`interests`/`pace`/`constraints`/`assumptions`/`locale`/
`pasted_notes` 等 Journey 文档本身不存储的字段），但下游真正读取内容的
`assemble_journey` 只用 origin/travelers/traveler_groups/meeting_anchor/
budget_cny 四类字段算身份与账本，其余字段只过 schema 门、不进 journey_id
哈希（哈希只取 start/end_date+身份+分段天数+trip_ids）。
对策（非空白裁决，任务书未提及此实现细节）：用 Journey 自身可恢复字段（已
实测 `budget_ledger.budget_cny`==20000，与 demo 原 request.json 一致；
`segmentation.expected_segment_days`）重建一个 schema 合法的 request，其余
字段取中性占位值（pace=balanced、locale=zh-CN、interests/constraints/
assumptions=[]、pasted_notes=null），不影响 journey_id 或任何输出内容。

任务 1（已完成）：journey.py 新增 `replace_trip_in_journey(journey, trip,
base_revision, clock, reason=None)` 与私有辅助 `_journey_identity_request`
（按上面「对策」重建 request）；cli.py 的 assemble 解析器把 `--request`/
`--trip` 从 required 改 `default=None`，新增 `--journey`/`--replace-trip`/
`--base-revision`/`--reason`，`_cmd_journey_assemble` 按
replace_mode/build_mode 互斥分流，错误全部经既有
`ValueError`→`JOURNEY_ASSEMBLE_FAILED` 路径，失败不写文件。

验收（实测命令与输出）：
- extract：`ctw journey extract --journey demo/journey-16d/journey.json
  --trip-id trip-c5eba1b26542ed43 --output-json .tmp/t1.json` →
  `JOURNEY_EXTRACT_COMPLETE`，exit 0。
- replan：delay.json 的 `subject_ref="slot-2"` 在 t1.json 里不存在（t1 的
  slot_id 全是描述性长名，如 `slot-poi-routine-meal-2acb635f18d4`；实测
  直接传 delay.json 得 `REPLAN_FAILED subject_not_found`）——改用同形状
  （`type=delay`、`delta_minutes=15`、`reason` 逐字复用 delay.json 的
  "接驳晚点 15 分钟"）但 `subject_ref` 换成 t1 里真实存在的
  `slot-poi-routine-meal-2acb635f18d4`（day-3 当天最后一槽，同日无下游槽
  联动风险）：`ctw replan --trip .tmp/t1.json --event .tmp/delay-event.json
  --base-revision 1 --fixed-clock 2026-10-15T12:00:00+08:00 --output-json
  .tmp/t1-r2.json --output-html .tmp/t1-r2.html` → `REPLAN_COMPLETE
  revision=2 ... errors=0`，exit 0。
- assemble --replace-trip：`ctw journey assemble --journey
  demo/journey-16d/journey.json --replace-trip .tmp/t1-r2.json
  --base-revision 1 --fixed-clock 2026-10-15T12:00:00+08:00 --output-json
  .tmp/j-r2.json` → `JOURNEY_ASSEMBLE_COMPLETE trips=3 days=16 errors=0`，
  exit 0；`ctw journey validate .tmp/j-r2.json` → `JOURNEY VALID trips=3`。
  python 断言：journey_id 两边均为 `journey-d7d147568550c48c`（不变）；
  revision = `{number:2, parent_revision:1, created_by:"user",
  reason:"接驳晚点 15 分钟"}`（未传 `--reason`，取自子 Trip 最新
  `revision.reason`）；`trips[0].revision.number`=2，`trips[1]`/`trips[2]`
  仍为 1。`ctw journey render` 与 `journey validate-html` 均
  errors=0、exit 0。`git status --short -- demo` 空输出。
- 反向验证一：`--base-revision 9` → `JOURNEY_ASSEMBLE_FAILED
  revision_conflict: Journey is at revision 1, not 9`，exit 1，
  `.tmp/j-bad-revision.json` 未生成。
- 反向验证二：把 t1-r2.json 的 `trip_id` 改成 `"trip-does-not-exist"` →
  `JOURNEY_ASSEMBLE_FAILED trip_not_found: Journey does not contain Trip
  trip-does-not-exist`，exit 1，`.tmp/j-bad-tripid.json` 未生成。
- 额外手测（非任务书要求，防止改坏既有路径）：同时传 `--replace-trip` 与
  `--request`/`--trip` → `JOURNEY_ASSEMBLE_FAILED ... mutually
  exclusive`，exit 1；既有 build-mode 的 extract→assemble 往返（demo 三段）
  重新走一遍，`ctw canonicalize` 的输出与 demo 原 journey.json 的
  canonicalize 输出 `cmp` 无差异，确认 `--request`/`--trip` 改成
  `default=None` 未改变原有语义下的实际行为。`py_compile`+pyflakes 单独对
  journey.py/cli.py 两文件全程 0 行。单独一次 `git commit`。

任务 2（已完成）：`tests/test_journey.py` 新增 `JourneyReplaceTripTests` 类
（导入块按字母序插入 `replace_trip_in_journey`），7 个 `def test_`（任务书要求
至少 4 个）：替换成功且 journey_id 不变+revision 字段齐全、显式 `--reason`
覆盖子 Trip 自身 reason、`revision_conflict`、`trip_not_found`、
`journey_identity_changed`（见下）、CLI 混用 `--replace-trip` 与
`--request`/`--trip` 被拒、CLI 全链路（真实 `ctw journey extract` →
`ctw replan` → `ctw journey assemble --replace-trip` 子进程）往返。
`journey_identity_changed` 一条：真实数据很难在不先撞
`assemble_journey` 自身结构校验（日期缺口/住宿续接等）的前提下单独构造出
「trip_id 存在但会改变 journey_id」的合法输入，改用
`mock.patch("china_trip_weaver.journey.assemble_journey_from_trips",
return_value=...)` 隔离测 `replace_trip_in_journey` 自己的身份校验分支——
`assemble_journey_from_trips` 是被测函数的协作对象而非被测对象本身，且
`test_flyai_live.py`（`mock.patch.object(FlyAIBackend, "from_spec", ...)`）等
已有先例证明本仓库测试套件接受这种"隔离协作对象"的 mock 用法，不算违反
"不许 mock 被测对象"。plan-china-trip/SKILL.md 第 27 行（Workflow 第 6 条，
原文正是"替现有子 Trip 调 replan"那条）末尾加一句：属于 Journey 的子 Trip 先
`ctw journey extract` 取出，replan 后用 `ctw journey assemble
--replace-trip` 放回。两份 README 的 `ctw journey assemble` 行后各加一行
替换形式的命令签名。

验收：`JourneyReplaceTripTests` 单独跑 `Ran 7 tests OK`；`test_journey`
整模块 `Ran 57 tests OK`（51 基线 + 6 已有 + 新增均计入，与前一轮书 A2 的
51 相加吻合）。反向验证：把 `replace_trip_in_journey` 里
`if reassembled["journey_id"] != journey["journey_id"]:` 临时改成
`if False and ...:`（加 `# TEMP-REVERSE-VERIFY` 标记）→ 单独跑
`test_replace_trip_rejects_a_reassembly_that_changes_the_journey_identity`
→ `FAILED`（`AssertionError: ValueError not raised`，红）→ 还原 →
`git diff plugins/.../journey.py | grep -c TEMP-REVERSE` 为 0（改动已完整
撤回）→ 同一测试重跑 `ok`（绿）。

最终门（2026-09-10 实测）：`/usr/bin/python3 -m unittest discover -s tests`
→ `Ran 532 tests` `OK` 0 skipped（525 基线 + 新增 7）；`scan_secrets.py` 0
命中（368 文件）；`~/miniconda3/envs/core/bin/python -m pyflakes
plugins/china-trip-weaver/src tests scripts` 0 行；`git status --short --
demo` 空。`git diff main --stat -- plugins/china-trip-weaver/schema demo`
空——但 `git diff main -- tests | grep -E '^-\s*def test_'` 此刻并非 0 行
（打出两条 `test_cli_refresh_without_rail_result_fails_without_outputs`/
`test_cli_non_refresh_event_with_rail_result_fails`）。查明原因：并行的
A1b 书（`ctw replan --rail-result` 接线，在 main 上直改）已在本书任务 1/2
执行期间合入 main（提交 `4216c59`、`f2b0f34`，`git log main` 可见），本分支
仍从任务书指定的 `7fc66ec` 分出、未合并 main 的后续提交（任务书明令
"不碰 main，合并由管理者做"）；这两条测试属于 A1b 书新增，本书从未接触过
`test_replan.py`。改用本分支真实的分出点 `7fc66ec` 重新比较——
`git diff 7fc66ec -- tests | grep -E '^-\s*def test_'` 0 行、
`git diff 7fc66ec --stat -- plugins/china-trip-weaver/schema demo` 同样为
空——证实本书确实 0 行删测试、0 行碰 schema/demo，任务书这条验收命令写在
"main 不动"的假设下，未预见另一本并行书会话内合入 main；按"跳过做别的，
继续"处理，不算待裁决，只记录供合并时核对。单独一次 `git commit`。

终验（提交后复核，2026-09-10）：任务 1 的替换命令与两条反向验证全部重新
跑了一遍（extract→replan→assemble --replace-trip→validate→render→
validate-html，均 exit 0；`--base-revision 9` 与 trip_id 改错两条均
exit 1、不产文件），结果与任务 1 首次验收逐字一致。全量
`Ran 532 tests` `OK` 0 skipped、`scan_secrets.py` 0 命中（368 文件）、
pyflakes 0 行、`git diff main --stat -- plugins/china-trip-weaver/schema
demo` 与 `git diff 7fc66ec --stat`（分支真实分出点）均为空。`git push -u
origin journey-replace` 成功（远端已建 `journey-replace` 分支）。硬指标
一、二均达标，BLOCKED.md 随本次提交带一条非空白裁决记录，任务书结束。

## 书：`ctw candidates import` 批量导入（2026-09-10，worktree `.tmp/wt-c` 分支 `candidates-import`）

本书在 `.tmp/wt-c`（新建）干，只推分支不合并，界限见任务书「界限」节。与并行
的书「渲染页可读性」（main 直改）、书 D「AnySearch 接通」（`.tmp/wt-d` 分支
`anysearch-contract`，已存在）地界不重叠。

任务 0 核对（HEAD `1f1e966`，与任务书一致）：全量 `Ran 534 tests` `OK`
0 skipped；`scan_secrets.py` 0 命中（369 文件）；pyflakes（src+tests+scripts）
0 行；均与任务书数字吻合。唯一路径出入：任务书写
`src/china_trip_weaver/candidates.py`，实际是
`plugins/china-trip-weaver/src/china_trip_weaver/candidates.py`（`git ls-files
'*candidates.py'` 只有这一份 + `tests/test_candidates.py`，无歧义）——与此前
`replan.py`/`journey.py` 的同类路径出入（历次记录判过不算待裁决）同款处理，
按实际路径改，不停工。函数签名逐字核对：`add_poi_candidate`
（candidates.py:845）、`add_lodging_candidate`（candidates.py:968）行号精确
吻合；两者实际都是仅关键字参数（`path, *, name, ...`），任务书写成位置参数
形式但明确说"其余键与参数同名"，只是描述粗略，参数名与默认值完全一致，不算
偏差。`cli.py:95` `_add_candidates_parser` 确有 init/add-poi/add-lodging/
fix-names 四个子命令，`_cmd_candidates`（464 行）用统一 `except (OSError,
UnicodeError, ValueError, json.JSONDecodeError)` 兜底打印
`CANDIDATES_FAILED %s`。核实关键实现事实：`_editable_candidates(path)`
读文件到内存 dict（1066 行）、`_write_valid_when_complete(path, document)`
（1079 行，仅当 `document["pois"]` 非空才跑 `validate_candidates`，随后
`write_canonical_json`）是"读→内存改→写"三段式的唯二入口，`add_poi_candidate`/
`add_lodging_candidate` 内部逻辑（不含首尾读写两行）可以原样抽成
`_apply_poi_candidate(document, ...)`/`_apply_lodging_candidate(document,
...)` 两个不做文件 I/O 的函数，两个 add 函数改成"读→apply→写"三行调用，
输出逐字节不变。`contracts.read_json` 强制顶层必须是 JSON object（不接受
数组），所以 `--items ITEMS.json`（顶层是数组）不能复用它，读取与"必须是
数组"校验放在 cli.py 的 `_cmd_candidates_import` 里，`import_candidates`
本身只收已解析好的 Python list，不做文件 I/O（`path` 参数仍是唯一涉及磁盘
的路径）。

理解的目标：给 `candidates.py` 加 `import_candidates(path, items, clock, *,
dry_run=False)`——先对 items 逐项做结构校验（kind 是否合法、键集合是否吻合
该 kind 的必填+可选键、每个已提供字段的顶层类型是否匹配，三类问题都在这一
遍全部查完，带 1-based 序号，任何一条不对整体失败、不读不写候选文件、不
触碰内存 document）；结构校验全过后读入内存副本，按 items 数组原始顺序（不
按 kind 分组）逐条调用 `_apply_poi_candidate`/`_apply_lodging_candidate`（
与现有 add_poi_candidate/add_lodging_candidate 共享的同一段逻辑，直接复用
不重写），任一条业务规则失败（如日期格式、金额为负）整体失败、不写盘，
两种失败都以同一个 `CandidatesImportError(item_number, reason)` 异常携带
序号与原因；全部成功后跑一次与 `_write_valid_when_complete` 相同的收尾
校验，`dry_run=True` 到此为止不写盘，否则 `write_canonical_json` 一次性
落盘。CLI 包一层 `ctw candidates import PATH --items ITEMS.json
[--queried-at ISO] [--dry-run]`，`_cmd_candidates_import` 自己 catch
`CandidatesImportError` 打印 `CANDIDATES_IMPORT_FAILED item=N reason=...`
（exit 1），其余异常（`--items` 文件本身缺失/非法 JSON/顶层非数组）交给
`_cmd_candidates` 外层统一 catch 走既有 `CANDIDATES_FAILED` 通道，不重复
判断类型；成功打印 `CANDIDATES_IMPORT_COMPLETE pois=N lodgings=M`（N/M 是
本批次新增计数，非文件累计总数——任务书未点名，判为对用户更有信息量的
选择）。

顺序：任务 1（`_apply_*_candidate` 拆分 + `import_candidates` + CLI 接线 +
硬指标一四条命令）→ 任务 2（5 个新测试 + Skill/README 文档 + 反向验证）→
最终门两项硬指标。

最大风险：`write_canonical_json` 只对 dict 的 key 排序（`sort_keys=True`），
不改变 list 内部元素顺序，所以 `pois`/`lodgings`/`claims`/`unknowns` 四个
数组各自的元素顺序完全由处理顺序决定——import 必须严格按 items.json 数组
的原始顺序逐条应用（不能先归类再按 kind 分组处理），否则和"手工逐条追加"
生成的文件顺序不同、`cmp` 必然不相等；量表选定的应对是不对 items 做任何
排序或分组，直接 `enumerate` 原始序列。次要风险：`_editable_candidates`
的类型注解是 `Dict[str, Any]`（可变），需确认 `_apply_*_candidate` 在同一个
`document` 引用上原地追加多次不会因为共享引用产生意外别名问题——核实
`_apply_poi_candidate`/`_apply_lodging_candidate` 内部只 `.append()`/
`.extend()` 顶层四个列表，不重新赋值 `document` 本身，多次调用天然安全。

任务 1（已完成）：`candidates.py` 把 `add_poi_candidate`/`add_lodging_candidate`
的"读→改内存→写"三段拆成"读→调用 `_apply_poi_candidate`/
`_apply_lodging_candidate`（新增，只做内存改动，不读不写文件，返回未
deepcopy 的新条目引用）→写"，两个 add 函数改成三行调用，函数体一字不落
原样搬进 `_apply_*` 里；`_write_valid_when_complete` 同理拆出
`_validate_document_when_complete`（只做"pois 非空才 validate_candidates"
这一步，不写盘），供 `import_candidates` 的 dry-run 复用。新增
`CandidatesImportResult`（frozen dataclass，`pois`/`lodgings` 两个计数）、
`CandidatesImportError(ValueError)`（带 `item_number`/`reason` 属性，
message 已是 `item=N reason=...` 形状）、`_POI_IMPORT_FIELDS`/
`_LODGING_IMPORT_FIELDS`（键名→(是否必填, 类型校验函数) 的映射表，area 在
lodging 里标记必填但类型校验放行 None，因为函数签名 `area: Optional[str]`
本身无默认值必须显式传、值可以是 null）、`_import_item_kind`（对单个 item
做 kind 合法性→未知键→缺必填键→类型 四层校验，任何一层失败立即
`raise CandidatesImportError`）、`import_candidates(path, items, clock, *,
dry_run=False)`（先对全部 items 跑 `_import_item_kind` 拿到 kind 列表，
全过后才 `_editable_candidates(path)` 读入内存，再按 items 原始顺序逐条
`_apply_poi_candidate`/`_apply_lodging_candidate`，业务规则失败同样包装成
`CandidatesImportError`；全部成功后 `_validate_document_when_complete`，
`dry_run` 为真到此为止，否则 `write_canonical_json` 一次性落盘，返回
`CandidatesImportResult`）。`cli.py` 加 `candidates import PATH --items
ITEMS.json [--queried-at ISO] [--dry-run]` 子命令；分发函数 `_cmd_candidates`
从"最后一支用 return 兜底 add-lodging"改成三个显式分支（init/fix-names 不
变，add-poi/add-lodging/import 各自判断），新增 `_cmd_candidates_import`
自读 `--items` 文件（`json.load` + 顶层必须是 list，否则 raise ValueError
交给外层 `CANDIDATES_FAILED` 通道，不单独处理——items.json 本身的问题与
"第几条数据"无关）、catch `CandidatesImportError` 打印
`CANDIDATES_IMPORT_FAILED item=%d reason=%s`（exit 1），成功打印
`CANDIDATES_IMPORT_COMPLETE pois=%d lodgings=%d`（N/M 是本批次新增计数）。
`import_candidates` 本身不做 `--items` 文件的读取（`contracts.read_json`
强制顶层必须是 object，不适用于数组清单；读取放在 cli.py，未碰
`contracts.py`，符合白名单）。

硬指标一实测（`.tmp/manual-check/`，脚本化不落盘任何仓库内文件）：①对
同一份 `candidates init` 骨架，`import`（4 项：2 POI + 2 lodging，含
`opens_at/closes_at/price_amount/duration_minutes`、`nightly_price/
includes_taxes`、`area: null` 等可选字段）与逐条 `add-poi`/`add-lodging`（
同一 `--queried-at 2026-09-04T12:00:00+08:00`）产出的文件
`cmp manual.json import.json` 零差异（`IDENTICAL`）；②把第 4 项（lodging）
删掉 `source_url` → `CANDIDATES_IMPORT_FAILED item=4 reason=missing
required key(s): source_url`、exit 1、`cmp` 确认文件与导入前逐字节相同；
③`--dry-run` 跑同一份合法 items → `CANDIDATES_IMPORT_COMPLETE pois=2
lodgings=2`、exit 0、`cmp` 确认文件与导入前逐字节相同；④`ctw
validate-candidates` 对 import 产物报 `CANDIDATES VALID`。反向验证（终端
记录）：在业务应用阶段的 `except (ValueError, TypeError)` 块里临时插入
`write_canonical_json(Path(path), document)  # TEMP-REVERSE-VERIFY`（写盘
后再 raise）→ 用一条能通过结构校验但触发业务规则失败的 item（lodging
`check_out` 早于 `check_in`，"lodging check-out must be after check-in"）
触发 → 文件确实被改写（`FILE_CHANGED`，红，证明"失败不写盘"这条保证在
没有该行为时会被打破）→ 用第一阶段的"缺 source_url"场景重试时未触发
写盘（因为结构校验在 `_editable_candidates(path)` 之前就失败，根本不进
循环体，判断为"两阶段设计"的预期表现，非误判）→ 删除 TEMP-REVERSE-VERIFY
一行还原 → `git diff main -- .../candidates.py | grep -c TEMP-REVERSE`
为 0（无残留）→ 同一失败场景重跑，`FILE_UNCHANGED`（绿）。全量
`/usr/bin/python3 -m unittest discover -s tests` → `Ran 534 tests` `OK`
0 skipped（与任务 0 基线相同，任务 1 本身不新增测试函数，测试留给任务 2）；
`scan_secrets.py` 0 命中（369 文件）；pyflakes 0 行；`git diff main --stat
-- plugins/china-trip-weaver/schema demo` 空；改动文件只有
`candidates.py`/`cli.py`/`PROGRESS.md` 三个，均在白名单内。单独一次
`git commit`（`f70df0f`）。

任务 2（已完成）：新建 `tests/fixtures/candidate-import/items.json`（3 POI +
2 lodging，含 `duration_minutes`/`opens_at`/`closes_at`/`opening_status`/
`price_amount`/`nightly_price`/`includes_taxes`/`area: null` 等可选字段）。
`test_candidates.py` 新增 5 个 `def test_`（均在
`test_generator_refuses_overwrite_and_duplicate_without_changing_file` 之
后插入）：`test_import_candidates_matches_sequential_add_poi_and_add_lodging`
（对同一份 items.json，`import_candidates` 一次调用与逐条
`add_poi_candidate`/`add_lodging_candidate`（同一 `FixedClock`）产出的文件
字节相同，且 `CandidatesImportResult(pois=3, lodgings=2)`）、
`test_import_candidates_does_not_write_on_item_failure`（第 4 项 lodging
`check_out` 改到 `check_in` 之前，触发业务规则失败，`item_number==4`、
文件与调用前逐字节相同）、`test_import_candidates_rejects_unknown_key`（第
2 项加一个未知键，`item_number==2`、`reason` 含 "unknown key" 与键名、
文件不变）、`test_import_candidates_dry_run_leaves_file_untouched`
（`dry_run=True` 返回正确计数且文件不变）、
`test_cli_import_subcommand_succeeds_and_validates`（子进程跑
`candidates init`→`candidates import`→`validate-candidates` 三条真实命令，
逐条 `returncode==0`，stdout 含 `CANDIDATES_IMPORT_COMPLETE pois=3
lodgings=2` 与 `CANDIDATES VALID`）。`research-china-destination/SKILL.md`
在 add-poi/add-lodging 代码块之后、fix-names 段之前加一段 import 用法（清单
格式、键名对应关系、双阶段失败都不写盘且报"第几项+原因"、`--dry-run`
说明）。两份 README「Other commands」各只加一行
`ctw candidates import CANDIDATES.json --items ITEMS.json [--queried-at ISO]
[--dry-run]`（紧跟 add-poi 那行之后），未改动块内其余行。

反向验证（终端记录，因 candidates.py 的任务 1 改动已单独提交，不是未提交
状态，"stash 掉改动"无法照字面顺序执行——`git stash push` 只能保存未提交
差异且 push 后工作区总是回到 HEAD，与"push 后应处于失败态"字面冲突；
采用等价且更贴合 git 语义的操作序列，push/apply/drop 三个动作全部用上，
理由记在此处供合并时核对）：①`git show 1f1e966:.../candidates.py` 覆盖
工作区文件，制造"HEAD→旧版本"的未提交差异；②`git stash push -u -m
"import-check" -- .../candidates.py`（只限定这一个文件的 pathspec，任务 2
其余未提交改动如 `test_candidates.py`/新 fixture 不受影响）保存这份差异，
工作区随之恢复为 HEAD（新版本）——`git stash list --format='%H %gs'` 记录
SHA `f69e52686e1c983a84fdc051c67db68688c923ff`；③`git stash apply <SHA>`
把该差异重新应用到当前工作区，使其变回旧版本（`grep -c "def
import_candidates"` 变 0）——此时是本次反向验证真正的"红"检查点；跑 5 个
新测试 → `ImportError: cannot import name 'CandidatesImportError'`，
`FAILED (errors=5)`；④`git checkout HEAD -- .../candidates.py` 恢复为新
版本（`grep -c` 变回 1）→ 重跑同 5 个测试 → `Ran 5 tests OK`（绿）；
⑤`git rev-parse stash@{0}` 核对等于步骤②记录的 SHA 后，用
`git stash drop stash@{0}`（非裸 `pop`）清理，`git stash list` 确认为空，
`git status --short` 确认其余未提交改动原样保留。全量
`/usr/bin/python3 -m unittest discover -s tests` → `Ran 539 tests` `OK`
0 skipped（534 基线 + 本任务 5 个新 `def test_`）；`scan_secrets.py` 0 命中
（370 文件）；pyflakes 0 行。

发现：写本节时 `main` 已被并行的「渲染页可读性」书推进（新增/删除了
`render/`、`tests/test_journey.py`、`tests/test_renderer.py` 等与本书无关
的内容），此刻字面执行任务书写的 `git diff main ...` 会把那些改动也混进
比对结果（例如误报删除了 4 个不属于本书的 `def test_`）。按此前
`journey-replace`/`docs-drift` 等书的同款先例（分支已分出后 main 前进，
验收改用分支真实分出点），本书统一改用 `git merge-base HEAD main` 核实的
真实分出点 `1f1e966` 做比对，不算待裁决：`git diff 1f1e966 -- tests |
grep -E '^-\s*def test_'` 0 行；`git diff 1f1e966 --stat --
plugins/china-trip-weaver/schema demo` 空；`git diff 1f1e966 --stat`
只有 7 个文件（`PROGRESS.md`/两份 README/`SKILL.md`/`candidates.py`/
`cli.py`/`test_candidates.py`），全部在白名单内。单独一次 `git commit`
（`2bba4ba`）。

终验（提交 BLOCKED.md 后复核，2026-09-10）：`BLOCKED.md` 记录一条本书
小节（`eef9bea`，无需要停工请示领导的裁决项，五点判断记录见上）后，清空
`.tmp/manual-check/` 临时验证文件，`git status --short` 为空。硬指标一
四项在最终代码上重新完整跑了一遍（非任务 1 阶段的旧结果复述）：①对同一份
`candidates init` 骨架，`candidates import`（用
`tests/fixtures/candidate-import/items.json`，同一
`--queried-at 2026-09-04T12:00:00+08:00`）与逐条 `add-poi`×3/`add-lodging`×2
（参数逐条照抄 fixture 内容）产出的文件 `cmp` 零差异（`IDENTICAL`）；
②把第 4 项（lodging "合成酒店"）删掉 `source_url` →
`CANDIDATES_IMPORT_FAILED item=4 reason=missing required key(s):
source_url`、exit 1、`cmp` 确认文件与导入前逐字节相同；③`--dry-run`
→ `CANDIDATES_IMPORT_COMPLETE pois=3 lodgings=2`、exit 0、`cmp` 确认文件
与导入前逐字节相同；④`ctw validate-candidates` 报 `CANDIDATES VALID`。
硬指标二：`/usr/bin/python3 -m unittest discover -s tests` → `Ran 539
tests` `OK` 0 skipped（≥539 达标；本次机器负载较高单跑 88.6s，非同一时刻
对照，不判定为回归——沿用「机器负载会让全量测试从 33 秒飘到 85 秒」的既有
经验）；`scan_secrets.py` 0 命中（370 文件）；pyflakes（src+tests+scripts）
0 行；`git diff 1f1e966 --stat -- plugins/china-trip-weaver/schema demo`
空；分支真实分出点核实为 `git merge-base HEAD main` = `1f1e966`（写本节时
`main` 已被并行的「渲染页可读性」书推进，字面 `git diff main` 会混入无关
改动，按既有先例改用真实分出点，见 `BLOCKED.md` 第 5 点）；`git diff
1f1e966 --stat` 最终 9 个文件（`BLOCKED.md`/`PROGRESS.md`/两份
README/`SKILL.md`/`candidates.py`/`cli.py`/新建的
`tests/fixtures/candidate-import/items.json`/`test_candidates.py`），全部
在「只允许改」白名单内；`git diff 1f1e966 -- tests | grep -E
'^-\s*def test_'` 0 行（未删除任何测试函数）。`git push -u origin
candidates-import` 成功（远端已建 `candidates-import` 分支，PR 未开——
任务书只要求推分支、合并由管理者做，未要求开 PR）。任务 1、任务 2、
`BLOCKED.md` 各一次独立 `git commit`（`f70df0f`/`2bba4ba`/`eef9bea`），
`main` 分支未被本书触碰。硬指标一、二全部达成，止损轮次未触发（每项任务
一次验收即通过，未出现连败），任务书结束，无遗留阻塞项。
