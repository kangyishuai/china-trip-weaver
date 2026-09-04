# China Trip Weaver：研究阶段索引与复现

研究日期：2026-09-03（Asia/Shanghai）。本阶段只研究/记录，没有创建 `china-trip-weaver` 产品目录、产品代码、Git 仓库或远程仓库。

## 结论先行

- 最近先例 `china-travel-assistant` 已占用目标入口 `plan-china-trip`；新旧插件不能无提示共同启用。
- 可落地的最小架构是：一个主编排 Skill，窄 provider/presenter explicit-only；`itinerary.json` + claim-level evidence 为中心。
- 交通主线：12306-mcp（实测可用）+ FlyAI inventory（待 pin CLI contract）+ VariFlight optional enrichment + 自写 AMap 薄 adapter。
- 坐标不二选一：保留 provider-native、WGS-84、GCJ-02 与 conversion provenance；AMap route/render 用 GCJ，KML/OSM 用 WGS。
- 排程先用真实 route-time matrix，再加 opening/service windows；OR-Tools 作为复杂 case 的可选 solver，不默认承担 188MB venv。
- v1 只做一个 deterministic 手机 HTML renderer，核心离线可读、地图/图片优雅降级，不嵌任何 Key/security。
- 已知死路：当前 `12306-skill` 连 `list-tools` 也失败；`amap-lbs-skill` 的 `travelPlanner` 丢 route/map result；FlyAI Skill 严格 frontmatter 校验失败。

完整取舍：[`04-design-insights.md`](04-design-insights.md)；未决验证：[`05-open-questions.md`](05-open-questions.md)。

## 交付文件

### 官方规范与汇总（5 份）

| 文件 | 内容 |
|---|---|
| [`01-codex-spec.md`](01-codex-spec.md) | Codex plugin/Skill/MCP/hooks/app/marketplace/沙箱/CLI，本机 bundled 对照与脚手架实测。 |
| [`03-capability-matrix.md`](03-capability-matrix.md) | 12 项能力 × 11 项目；每格链接到项目证据锚点。 |
| [`04-design-insights.md`](04-design-insights.md) | 23 条采用/不采用；重名、坐标、无 Key 专题。 |
| [`05-open-questions.md`](05-open-questions.md) | 14 个待验证问题，每项含方法与前置条件。 |
| `00-README.md` | 本索引与复现说明。 |

### 逐项目解剖（11 份）

| 项目 | 锁定版本 | 文档 |
|---|---|---|
| china-travel-assistant | `c258614293535a2713e1d2311060219107327790` | [`02-projects/china-travel-assistant.md`](02-projects/china-travel-assistant.md) |
| travel-plan-viz | `07d0155080f72607a6f0a74e063bd05c850dcf01` | [`02-projects/travel-plan-viz.md`](02-projects/travel-plan-viz.md) |
| trip-planner-skill | `624196a743327d310e07a7888ebe60f406716525` | [`02-projects/trip-planner-skill.md`](02-projects/trip-planner-skill.md) |
| 12306-mcp | `ff6439da6f63d7d72181abea4568abd69878c600` | [`02-projects/12306-mcp.md`](02-projects/12306-mcp.md) |
| 12306-skill | `9942ae99c9517b70c946429426d67d680199913d` | [`02-projects/12306-skill.md`](02-projects/12306-skill.md) |
| amap-lbs-skill | `cc418173bed7eaad7f40b67a46a09fce69be84eb` | [`02-projects/amap-lbs-skill.md`](02-projects/amap-lbs-skill.md) |
| flyai-skill | `f89974d2bd4822e79cf16d1906c9c2a7c900f979` | [`02-projects/flyai-skill.md`](02-projects/flyai-skill.md) |
| weekend-city-trip | `f8e3efb9a30350a4935b775be288e984f7c81008` | [`02-projects/weekend-city-trip.md`](02-projects/weekend-city-trip.md) |
| variflight-mcp | `d515d56204684b3179a75fb9cdd3f4600a0cb128` | [`02-projects/variflight-mcp.md`](02-projects/variflight-mcp.md) |
| trippick | `dbdf53c19fc69a466137471c9f9eb7cfdaa0cd6e` | [`02-projects/trippick.md`](02-projects/trippick.md) |
| OR-Tools | PyPI `9.15.6755` + docs 2026-09-03；不 clone | [`02-projects/or-tools.md`](02-projects/or-tools.md) |

锁定原始汇总：[`evidence/task2-source-locks.txt`](evidence/task2-source-locks.txt)。

## Evidence 索引

### 前提与官方规范

- `evidence/task0-ls.txt`：初始空目录。
- `evidence/task0-repo-connectivity.txt`：11 个 repo `ls-remote` HEAD 与 URL。
- `evidence/task0-url-connectivity.txt`：9 个规范 URL，含三次 TLS 失败。
- `evidence/spec-sources/`：抓取的 Codex plugins/build/skills/MCP/sandbox/config 与 Agent Skills 原文。
- `evidence/task1-source-lock.txt`：官方 docs SHA-256、OpenAI repo commits、desktop/CLI version。
- `evidence/task1-cli-scaffold.txt`：Codex CLI help/list、官方 plugin scaffold、Skill validator 原始输出。
- `evidence/task1-bundled-comparison.txt`：本机 10 个 bundled manifest 字段计数、MCP/app/marketplace 形状。
- `evidence/scaffold-output/`、`evidence/scaffold-marketplace/`：官方脚手架的研究用输出，不是产品代码。

### 项目实测

- `evidence/china-travel-assistant-tests.txt`：103 tests，OK。
- `evidence/travel-plan-viz-tests.txt`：21 tests，pass 21。
- `evidence/trip-planner-skill-render-qc.txt` + `evidence/trip-planner-skill/`：plain/theme render 与 QC PASS。
- `evidence/12306-mcp-build-query.txt`、`evidence/12306-mcp-work/probe.mjs`：build/start/tools/list/北京 station call。
- `evidence/12306-skill-list-tools.txt`：三次失败、Python 3.13 复现与 root cause。
- `evidence/amap-lbs-skill-tests.txt`：自带 `npm test` 占位失败。
- `evidence/flyai-skill-validation.txt`：CLI 未安装、官方 Skill validator 失败。
- `evidence/weekend-city-trip-local-checks.txt`、`evidence/weekend-city-trip-report.html`：58 点 map validation + Python version compatibility。
- `evidence/trippick-test-parse-xhs.txt`：5 个 XHS parser smoke case。
- `evidence/or-tools-install.txt`、`or-tools-vrptw.py`、`or-tools-vrptw-output.txt`、`or-tools-wheel/`：wheel/hash/install/time-window solver。

### 研究运行环境与缓存

- `research/.venv/`：唯一 OR-Tools 安装，Python 3.13.12；188MB。
- `evidence/12306-mcp-work/`：commit archive 的 build/query test copy，不是 reference clone。
- `evidence/12306-skill-work/`：dead-path diagnostic copy。
- `evidence/npm-cache/`、`evidence/pip-cache/`：为避免写用户全局 cache 而定向到 research 的安装缓存。
- `evidence/*-source.tar`：对应 commit 的无 `.git` test snapshot。

## Reference 目录

所有上游只读 clone 位于 `research/refs/<name>/`：10 个项目 repo + `openai-plugins` + `openai-skills`。OR-Tools 按要求没有 clone。`openai/plugins` 锁 `1e285826e604f66f7208f7ac4dba0fe8341d1f57`；`openai/skills` 锁 `49f948faa9258a0c61caceaf225e179651397431`，且该仓库 README 已标 deprecated。

## 复现前提

- macOS arm64；当前 desktop `26.901.20858` build `7658`；内嵌 `codex-cli 0.153.0-alpha.5`。
- Node 24；系统 `python3` 实际 3.9.6；Python 3.13.12 在 `~/miniconda3/bin/python3.13`。
- 网络需能访问 GitHub、OpenAI docs、12306、PyPI/镜像；TLS 可能抖动，同项失败最多重试 3 次。
- 不要设置或粘贴任何真实 provider Key；下面只复现 keyless/静态部分。
- 从 workspace 根 `<workspace>` 执行。

## 复现步骤

### 1. 前提核验

```bash
ls -A
git ls-remote -q https://github.com/19Chris19/china-travel-assistant.git HEAD
git ls-remote -q https://github.com/google/or-tools.git HEAD
curl -sL -o /dev/null -w '%{http_code}\n' https://developers.openai.com/codex/plugins
curl -sL -o /dev/null -w '%{http_code}\n' https://agentskills.io/specification
```

其余 URL/仓库完整列表与精确结果见 task 0 evidence；失败需逐 URL 重试，而不是把 TLS 超时判成不存在。

### 2. 官方规范证据

```bash
curl --retry 2 --retry-all-errors -sSLo research/evidence/spec-sources/plugins-build.md \
  https://developers.openai.com/codex/plugins/build.md
git -C research/refs/openai-plugins rev-parse HEAD
git -C research/refs/openai-skills rev-parse HEAD
codex --version
codex plugin marketplace --help
codex plugin marketplace list
python3 research/refs/openai-plugins/.agents/skills/plugin-creator/scripts/create_basic_plugin.py \
  "Spec Probe" --path research/evidence/scaffold-output --with-skills --with-hooks \
  --with-scripts --with-assets --with-mcp --with-apps --with-marketplace \
  --marketplace-path research/evidence/scaffold-marketplace/marketplace.json
```

重复执行脚手架需先使用新名称/新空目录；不要加 `--force` 覆盖现有 evidence。不要运行 marketplace add/install，它会修改用户配置。

### 3. 项目测试/验证

```bash
# china-travel-assistant
cd research/refs/china-travel-assistant
PYTHONPATH=plugins/china-travel-assistant/src python3 -m unittest discover -s tests -v

# travel-plan-viz
cd ../travel-plan-viz
node --test test/*.test.js

# trip-planner-skill（输出仍放 evidence）
cd ../trip-planner-skill
python3 scripts/render_plan.py examples/kyoto-sample.plan.geo.json \
  -o ../../evidence/trip-planner-skill/kyoto.html
python3 themes/render_clay2.py examples/china-2026/china.geo.json \
  -o ../../evidence/trip-planner-skill/china-clay.html
python3 themes/qc.py ../../evidence/trip-planner-skill/china-clay.html

# 12306-mcp test copy（已安装后）
cd ../../evidence/12306-mcp-work
npm_config_cache=../npm-cache npm run build
node probe.mjs

# 12306-skill 当前死路（预期 exit 1）
cd ../12306-skill-work
PYTHONDONTWRITEBYTECODE=1 ~/miniconda3/bin/python3.13 scripts/12306_apis.py list-tools

# amap-lbs-skill 自带占位（预期 exit 1: no test specified）
cd ../../refs/amap-lbs-skill
npm_config_cache=../../evidence/npm-cache npm test

# FlyAI format validation（预期 exit 1）
cd ../flyai-skill
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/flyai

# weekend-city-trip
cd ../weekend-city-trip
python3 scripts/validate_map.py example/*地图_Anysearch版.html --verbose
~/miniconda3/bin/python3.13 scripts/md_to_html.py \
  example/*调查报告_Anysearch版.md ../../evidence/weekend-city-trip-report.html

# trippick smoke
cd ../trippick
node scripts/test-parse-xhs.mjs

# OR-Tools
cd ../../..
research/.venv/bin/python research/evidence/or-tools-vrptw.py
```

`variflight-mcp` 无 tests 且业务需 Key；按本阶段规则只做静态分析。FlyAI CLI 不在 repo、本机未安装且 README 要全局安装，因此没有执行在线 verify。

### 4. 从零重建 OR-Tools 环境

```bash
~/miniconda3/bin/python3.13 -m venv research/.venv
mkdir -p research/evidence/or-tools-wheel research/evidence/pip-cache
PIP_CACHE_DIR="$PWD/research/evidence/pip-cache" \
  research/.venv/bin/python -m pip download --no-deps \
  --dest research/evidence/or-tools-wheel ortools==9.15.6755
/usr/bin/time -p env PIP_CACHE_DIR="$PWD/research/evidence/pip-cache" \
  research/.venv/bin/python -m pip install \
  research/evidence/or-tools-wheel/ortools-9.15.6755-cp313-cp313-macosx_11_0_arm64.whl
research/.venv/bin/python research/evidence/or-tools-vrptw.py
```

其他平台 wheel filename 不同，需以 PyPI 对应 tag 为准并核对 SHA-256。

## 未做与边界

- 未用任何真实 AMap/FlyAI/VariFlight/OpenRouter/Gemini Key；未调用付费接口。
- 未跑 AnySearch anonymous query：额度耗尽可能返回自动注册凭据，不符合本阶段“不申请/不暴露 Key”。
- 未做真实酒店 checkout、航班/余票购买、实名、下单、支付或退改。
- 未安装任何全局工具；没有修改 reference clone、`~/.codex` 或 `~/.agents`。
- 一个越界 npm debug log 与 config URL TLS 失败已如实置顶记录在 [`BLOCKED.md`](../../BLOCKED.md)，未自行删除/掩盖。

## 研究完整性自检

- 11 份项目文档 + 5 份规范/汇总 + 本 README 齐全。
- 设计启示 23（≤25）；待验证问题 14（≤15）。
- 所有矩阵格链接 02 文档的显式 evidence anchor。
- task 2 必做实测均有原始输出：CTA tests、travel-plan-viz tests、12306 MCP build/start/query、OR-Tools wheel/install/time-window example。
- 本目录顶层仅 `research/`、`PROGRESS.md`、`BLOCKED.md`。
