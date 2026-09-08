# PROGRESS

唯一的当前进度记录。2026-09-03 到 09-06 的逐轮任务书、实测证据、验收记录已归档，见「历史索引」。

## 现状速览（2026-09-08 实测）

- 版本：`0.6.0`，唯一来源是
  `plugins/china-trip-weaver/.codex-plugin/plugin.json` 与
  `src/china_trip_weaver/__init__.py` 的 `__version__`，两处一致，仓库内其余
  位置一律引用这两处之一，不再有第三处字面量。
- 测试：仓库根 `/usr/bin/python3 -m unittest discover -s tests` 全量
  `Ran 507 tests`，`OK`，0 skipped；`scripts/scan_secrets.py` 0 命中。
- 本机 Codex 与源码的差距：以 `bash scripts/install_local_plugin.sh --check`
  的实时输出为准，不写死数字——2026-09-08 实测是 13 个文件内容不同
  （`candidates.py`、`contracts.py`、`credentials.py`、`errors.py`、
  `evidence.py`、`geo.py`、`matrix.py`、`mobility.py`、`pipeline.py`、
  `planning.py`、`providers/amap.py`、`providers/base.py`、
  `providers/mcp_stdio.py`）加 2 个仅本机缓存独有（`cache.py`、
  `scheduler/ortools_bridge.py`——书 36 已从源码删除，旧缓存里还留着）。这些是
  书 33/34/35 的定位修复加书 36/书 B 的瘦身，尚未刷入用户真实 Codex（本机仍是
  0.6.0 旧缓存）。这是预期状态：只有**升版本号**的那一轮才跑该脚本刷新本机
  Codex，中间环节不装。

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
- **不做的技术债**：见 `BLOCKED.md`——三个 `*_home_shim.cjs` 合并、两处各约
  500 MB 的 `.npm-cache`/`.tmp` 清理或迁移、`cli.py` 706 行 `main` 拆分，均判
  断为超出本轮范围，留待专门一轮（`docs/design` 内重复文件与本机路径清理已
  由本书任务 1/2 完成，不再属于这份清单）。

## 历史索引

- 2026-09-03 至 09-06 的完整逐轮任务书、实测证据与验收记录：
  [docs/history/progress-2026-09-03-to-06.md](docs/history/progress-2026-09-03-to-06.md)
  （原 `PROGRESS.md` 整体归档，一字未改，9119 行）。
- 2026-09-03/04 越界事实的唯一记录：`BLOCKED.md`（面向公众的产品未决问题，
  Open 区已于 2026-09-06 清零，现为存档）。

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
