# 旅织 China Trip Weaver

[English](README.md) · **简体中文**

旅织是一个 Codex 插件，为中国大陆境内的行程做**有据可查、只读**的规划。它把一份出行需求和一份调研候选，织成一个带版本的 Trip JSON；长行程则织成一个内含完整 Trip 的 Journey。它查询固定版本的 12306 铁路、高德路线矩阵、飞猪（FlyAI）住宿与航班库存，以及可选的飞常准状态与舒适度增强；排程时不会把「比较用的候选」混进「已选定的行程段」；最后渲染成确定性的、手机优先的单文件 HTML。

它永远不会登录、提交身份信息、占位库存、下单、支付、取消或改签。服务商凭据只存在于各自的进程环境里，不会出现在命令行参数、日志、测试夹具、Trip、HTML 或 Git 中。

## 范围

planner 继续支持既有的一日游与单城市行程，并支持 2–7 天的有序多城市行程。多个目的地严格按 `origin → D1 → D2 → …` 行进；默认单向，只有用户明确写往返，或最后一个目的地本来就是 origin，行程才包含返程。跨城当天归到到达城市，每个过夜日期都必须在该城市明确选中且仅选中一个 stay。调研得到的住宿候选不等于已选 stay；任一晚没有可覆盖的候选时，规划会返回结构化无解结果。

超过 7 天的请求会生成一个 Journey；其中每个完整、可独立使用的子 Trip 仍严格限制在 1–7 天。缺省拆分会在服从七天上限与已调研住宿链的前提下尽量减少子 Trip 数；`ctw journey plan --expected-segment-days N` 接受 1–7 的整数，优先把各段长度靠近 `N`，但不会突破这些硬约束。相邻日期、边界住宿、跨段交通和全程预算都会显式记录并校验。某个子 Trip 被 replan 后，Journey validator 会从完整子 Trip 重新核对段缝两侧，结构化报告住宿或跨段交通断裂，而不会静默顺延后段。Journey 总览页展示全程路线、各段日期、总预算区间、按截止时间排序的预订／核验清单，以及全部降级能力、冲突 claim 与未解决 unknown，同时不向可见文本暴露内部 id。

Journey 的高德调用额度按最终子 Trip 分配。缺省总额度是每个 Trip 80 次、且单个 Trip 仍封顶 80；`ctw journey plan --amap-total-max-calls N` 设置非负的全程总上限，并在最终各段之间尽可能均分。该上限不会反向扩大缺省额度。

高德真正尝试定位 POI 却无法确认身份或坐标时，Trip 的 `unknowns` 会留下可照着改的坐标记录；可用时也会带经过脱敏的失败原因与候选名称。关闭 mobility 或没有高德 Key 时，不会凭空制造这类记录。

POI 搜索与 geocode 采用同一套行政区匹配口径：调研候选写的是城市或区县，都可以与服务商返回的城市或区县相匹配。因此一边写区县、另一边写其所属地级市（或反过来）不会被误判成两个地点；真正无关的行政区仍会严格判为不匹配。

旅客输入有两种互斥写法：既有 `origin + travelers`，或 `traveler_groups[] + meeting_anchor`。每组提供稳定的 `group_id`、本组人数与 origin，可另带 mobility profile；会合锚点提供地点和 `meet_by`，`buffer_minutes` 缺省为 60。任何一组无法留出足够缓冲都会得到结构化冲突；混合输入会被拒绝，输出 Trip 也只保留被选中的那一种写法。验证、渲染与 inventory 查询都会原生消费分组写法。分组交通腿必须有明确 `group_refs`；`transport_pricing` 分别给出每组交通总价与全团交通总价。

`pace=slow` 先按严格慢节奏排程。只要无解，就累计尝试：降低每日 POI 上限、把 POI／餐点时长压到推荐值的 70%、最后把当日结束时间放宽到 balanced 的 21:30。排得出的第一步就停止，实际采用的每一步都会追加到 `request.assumptions`；三步无法改变的硬冲突保留原结构化冲突，并列出全部已尝试降配。

## 运行环境

- Codex 桌面版自带的命令行，或兼容的 Codex CLI。
- 系统 Python 3.9 或更高版本作为运行时。
- 只有真正调用固定版本的 MCP／CLI 服务商时才需要 Node 和 npm，且不会全局安装任何东西。
- Google Chrome 仅供可选的渲染质检脚本使用，插件运行时不需要它。

插件从一个指向本仓库克隆目录的本地市场安装。它没有发布到公开的 Codex 市场：服务商条款、数据缓存与再分发、地图署名和上架元数据都还没有结论。改变这一点之前请先读 [`BLOCKED.md`](BLOCKED.md)。

本项目采用 [MIT 许可证](LICENSE)。该许可证只覆盖本仓库自己的代码和文档，不授予任何对高德、飞猪／FlyAI、飞常准或中国铁路返回数据的权利。这些服务商禁止缓存和再分发其数据，商业用途需另行购买许可或签订书面合同，因此除非你自行取得相应许可，本仓库仅供个人非商业使用；详见 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。

## 本地凭据

FlyAI 是可选的尽力而为来源。它是飞猪服务的非官方第三方包装器，命令接口曾经漂移过，因此 `--lodging` 默认为 `off`，FlyAI 的任何失败只降级住宿与航班库存，不会影响整份行程。

`ctw doctor` 对高德、FlyAI、飞常准和 AnySearch 只报告 `configured`（已配置）或 `missing`（未配置），永远不打印值、前缀、后缀、哈希或长度。它同时报告 `skill_conflicts`：自动检测是否有另一个已启用插件暴露同名 Skill，发现冲突时退出码非零。

凭据优先取自启动进程的环境变量，其次是 `~/.config/china-trip-weaver/credentials.env`。在 POSIX 系统上，该文件必须是当前用户拥有的普通文件，权限恰为 `0600`。不要把值写在命令行上，也不要粘贴进对话。

```bash
plugins/china-trip-weaver/scripts/ctw doctor
```

实网路径使用 `AMAP_WEBSERVICE_KEY`、`FLYAI_API_KEY` 和 `VARIFLIGHT_API_KEY`（`X_VARIFLIGHT_KEY` 保留读取兼容）。本版本中 AnySearch 保持关闭。每个 Node 服务商都会拿到仓库内的 npm 缓存、独立的临时／配置／缓存目录，以及各自隔离的 `os.homedir()`。

## 安装或刷新到本机 Codex（自动化）

先克隆本仓库，下面所有路径都相对于克隆目录。

每次迭代或版本更新，都应以「把本机 Codex 里已安装的插件刷新一遍」收尾。一个脚本完成全部动作：必要时注册本地市场，执行 `codex plugin add`（对本地市场插件是幂等的，会用仓库源码刷新缓存，版本号变了也会切到新版本），然后校验 `codex plugin list` 报告 `installed, enabled` 且版本与清单一致、缓存与源码逐字节相同。

```bash
scripts/install_local_plugin.sh          # 安装或刷新，然后校验
scripts/install_local_plugin.sh --check  # 只校验，不改任何配置
```

如果 `codex` 不在 PATH 上，用 `CODEX_BIN` 指定（脚本会回退到 Codex 桌面版内嵌的命令行）。把 `CODEX_HOME` 指向临时目录，可以在隔离环境里试跑而不动真实配置。刷新之后，在 Codex 里新建一个任务才会加载新版本；如果 Skill 没出现，重启 Codex 桌面版。

## 从本地市场安装（手动）

在仓库根目录执行：

```bash
CODEX_HOME=/path/to/an/isolated/codex-home \
  /Applications/ChatGPT.app/Contents/Resources/codex \
  plugin marketplace add "$PWD"

CODEX_HOME=/path/to/an/isolated/codex-home \
  /Applications/ChatGPT.app/Contents/Resources/codex \
  plugin add china-trip-weaver@china-trip-weaver-local

CODEX_HOME=/path/to/an/isolated/codex-home \
  /Applications/ChatGPT.app/Contents/Resources/codex \
  plugin list
```

期望结果是 `china-trip-weaver@china-trip-weaver-local`、版本 `0.6.0`、状态 `installed, enabled`。安装或更新后请新建一个 Codex 任务，让它的 9 个 Skill 与 MCP 配置重新加载。

用 Codex 桌面版界面安装时：把本仓库添加为本地市场，确认 `china-travel-assistant` 已禁用，安装 China Trip Weaver Local，重启，再新建任务。两个插件不能同时启用，因为它们都暴露 `plan-china-trip`。

## 候选输入

`candidates.json` 恰好包含 `candidates_version`、`pois`、`lodgings`、`claims` 和 `unknowns` 五个字段，不包含交通段。它的实体形状复用冻结的 Trip `$defs`，每个实体、价格和开放时段的证据引用都必须能解析到。

`ctw candidates add-poi ... --verify-name` 会在写入前用高德核对 POI 名称。它只报告经过脱敏的 `unique`、`ambiguous` 或 `unavailable` 结果并最多给出三个候选名称建议，不会凭这次核名写入坐标；缺 Key 或 provider 核名失败都不会阻断候选写入。

`ctw candidates fix-names` 读取 Trip 或 Journey 里的高德坐标 unknown，把可采用的规范名报告给对应的调研候选。它默认只报告；只有加 `--apply` 才会把唯一确定的名称写回候选文件。歧义、冲突、同名或格式异常的建议都留给人工确认，绝不自动修改。

处理这些人工项时，`--export-manual NAME-REVIEW.json` 会导出一份可填写的 JSON 清单，绝不修改候选文件。给任意条目的 `chosen` 填值后，再用 `--apply-manual NAME-REVIEW.json` 应用；每个非空值都必须与该条当前 `suggested_names` 中的一个名字逐字相等，空值或缺失值会跳过。只要出现未知 `ref_id` 或建议外名字，整次应用就失败，候选文件字节不变。若要使用完全自定义的名字，请直接编辑候选文件，再运行 `validate-candidates`。

```bash
plugins/china-trip-weaver/scripts/ctw validate-candidates demo/candidates.json
plugins/china-trip-weaver/scripts/ctw candidates fix-names CANDIDATES.json --trip TRIP_OR_JOURNEY.json
plugins/china-trip-weaver/scripts/ctw candidates fix-names CANDIDATES.json --trip TRIP_OR_JOURNEY.json --apply
plugins/china-trip-weaver/scripts/ctw candidates fix-names CANDIDATES.json --trip TRIP_OR_JOURNEY.json --export-manual NAME-REVIEW.json
plugins/china-trip-weaver/scripts/ctw candidates fix-names CANDIDATES.json --trip TRIP_OR_JOURNEY.json --apply-manual NAME-REVIEW.json
```

参见示例 [`candidates.example.json`](plugins/china-trip-weaver/references/candidates.example.json) 和机器合同 [`candidates.schema.json`](plugins/china-trip-weaver/schema/candidates.schema.json)。

## 运行合成演示

仓库内的北京→上海演示是确定性的合成输出。生成时关闭全部远程服务商；铁路夹具返回合成的空结果，因此成品只展示带明确标记的 12306 公开查询回退。

```bash
plugins/china-trip-weaver/scripts/ctw plan \
  --request demo/request.json \
  --candidates demo/candidates.json \
  --rail fixture:tests/fixtures/providers/rail12306/empty.json \
  --mobility off \
  --lodging off \
  --aviation off \
  --offline-fixture \
  --fixed-clock 2026-09-04T00:00:00+08:00 \
  --output-json demo/trip.json \
  --output-html demo/trip.html

plugins/china-trip-weaver/scripts/ctw validate demo/trip.json
plugins/china-trip-weaver/scripts/ctw validate-html demo/trip.html demo/trip.json
/usr/bin/python3 scripts/scan_secrets.py demo/trip.json demo/trip.html
```

用你自己的凭据运行同一条规划命令，把 provider 参数换成 `--rail live --mobility live --lodging live --aviation auto`，去掉两个仅夹具使用的参数，并把输出写到 `.tmp/`，即可得到当前实网结果而不把它重新放回 Git。带凭据的验收曾证明以下能力数量：2 条日期铁路行程、20 个路线单元、10 个住宿候选、20 个航班对比，以及状态与舒适度增强。这里仅保留数量说明，不再分发该次运行的任何服务商条目。

[`demo/guangzhou-shenzhen/`](demo/guangzhou-shenzhen/) 下的一日往返也由同一份合成空结果夹具生成。不过夜的请求不查询住宿，演示也不会编造服务商库存。

[`demo/grouped-departures/`](demo/grouped-departures/) 下的分组出发示例让两组合成旅客分别从北京、广州前往上海会合点。提交的 Trip 保持严格的分组 request 形状，并可见地展示各组出发地、3 人总数、分组归属交通腿，以及分组/全团交通价格。

第五组示例位于 [`demo/journey-16d/`](demo/journey-16d/)：一份完全合成的上海→杭州→苏州 16 天 Journey，拆成三个完整 Trip。它的已提交文件由 `scripts/build_renderer_fixtures.py` 独占写入；该生成器固定使用 `2026-09-05T09:00:00+08:00`，有意不同于其余四组 demo 使用的 `2026-09-04T00:00:00+08:00`，不要单独手工重跑第五组。用 `/usr/bin/python3 scripts/build_renderer_fixtures.py` 可重复生成，再运行：

```bash
plugins/china-trip-weaver/scripts/ctw journey validate demo/journey-16d/journey.json
plugins/china-trip-weaver/scripts/ctw journey validate-html demo/journey-16d/journey.html demo/journey-16d/journey.json
```

铁路、网络或服务商失败，永远不会变成假成功。每项能力保留自己的健康状态，要么使用带标记的降级方案，要么停在一个有类型的 unknown 上。高德对每个 Trip 最多调用 80 次、不超过 2 QPS；Journey 服从上文说明的总额度分配。FlyAI 的遮罩价（例如 `¥4xx`）一律是 `verify-on-click`，只有精确数字才是 `live`。FlyAI 的坐标始终是 `provider-unknown`，不做转换也不上图。

飞常准的部分增强失败也会如实呈现：如果航班搜索或状态数据已经成功，但后续舒适度查询失败，可用的航班和状态证据仍会保留，同时飞常准健康状态变为 `degraded`，不会再显示为完全正常。

当 12306 返回多个可能车站且高德可用时，插件会用城市中心与精确匹配的铁路车站 POI 附加直线距离信号。它保留全部候选，已知距离按近到远、未知距离排在最后，绝不替用户选站；距离无法取得也不会把原本成功的铁路结果降级。

## 不配任何 Key 也能跑

无 Key 运行时，从启动环境里移除服务商变量，并确认本地凭据文件不存在。使用 `--mobility off --lodging off --aviation off`；铁路仍是公开的实网查询，也可以设为 `off`。静态估算和深链都会被明确标记。

确定性的离线开发运行：

```bash
plugins/china-trip-weaver/scripts/ctw plan \
  --request tests/fixtures/e2e/beijing-shanghai-3d/request.json \
  --candidates tests/fixtures/e2e/beijing-shanghai-3d/candidates.json \
  --rail fixture:tests/fixtures/e2e/beijing-shanghai-3d/rail.json \
  --mobility off \
  --lodging off \
  --aviation off \
  --offline-fixture \
  --fixed-clock 2026-09-04T00:00:00+08:00 \
  --output-json .tmp/trip.json \
  --output-html .tmp/trip.html
```

这个模式只用于回归测试，会把预售期外和夹具结果标记为降级的静态数据，绝不会当作实时库存展示。另有夹具覆盖「上海本地两日、零铁路调用」和「北京→杭州四日」两种请求。

## 其他命令

```text
ctw doctor
ctw validate TRIP.json
ctw validate-candidates CANDIDATES.json
ctw candidates add-poi CANDIDATES.json --name NAME --city CITY --category CATEGORY --source-url URL [--verify-name]
ctw candidates fix-names CANDIDATES.json --trip TRIP_OR_JOURNEY.json [--apply | --export-manual NAME-REVIEW.json | --apply-manual NAME-REVIEW.json]
ctw canonicalize TRIP.json
ctw rail --date YYYY-MM-DD --from CITY --to CITY --output-json rail-result.json
ctw mobility --candidates CANDIDATES.json --modes transit,walking --output-json mobility.json
ctw lodging --city CITY --check-in YYYY-MM-DD --check-out YYYY-MM-DD --output-json lodging.json
ctw air --origin CITY --destination CITY --date YYYY-MM-DD --output-json air.json
ctw replan --trip TRIP.json --event EVENT.json --base-revision N --output-json TRIP-rN.json --output-html TRIP-rN.html
ctw render TRIP.json --output TRIP.html
ctw validate-html TRIP.html TRIP.json
ctw journey plan --request REQUEST.json --candidates CANDIDATES.json [--expected-segment-days N] [--amap-total-max-calls N] --output-json JOURNEY.json
ctw journey validate JOURNEY.json
ctw journey render JOURNEY.json --output JOURNEY.html
ctw journey validate-html JOURNEY.html JOURNEY.json
```

运行时不使用任何第三方 Python 包。Trip 与 Journey renderer 都会拒绝无效输入；两套 HTML validator 都会拦截结构、CSP、远程资源、危险链接、密钥、事实映射、追溯缺口和交易动作等违规。

## 测试

```bash
/usr/bin/python3 -m unittest discover -s tests -v
/usr/bin/python3 scripts/scan_secrets.py
/usr/bin/python3 scripts/scan_secrets.py --credential-values
/usr/bin/python3 scripts/scan_secrets.py --credential-values --git-history
```

本机不应出现任何跳过。测试覆盖冻结的 Trip Schema、Journey 拆分与连续性、候选校验、凭据与进程／家目录隔离、精确值与抓取数据门禁、证据／缓存／坐标、带高德／FlyAI／飞常准合同形状的 79 个一眼可辨合成服务商夹具、20 个排程 golden、8 个无解用例、4 个局部重排 golden、Trip/Journey 渲染器对抗用例与离线浏览器视口、Skill 与打包元数据，以及确定性和实网两条集成路径。

## 文档导航

| 位置 | 语言 | 内容 |
|---|---|---|
| [`docs/design/`](docs/design/00-README.md) | 英文 | 架构设计与决策记录，是实现的权威依据 |
| [`docs/design/adr/`](docs/design/adr/) | 英文 | 编号的架构决策记录；与之冲突的改动要新增 ADR 取代，而不是悄悄改实现 |
| [`docs/research/`](docs/research/00-README.md) | 中文 | 立项前对 11 个参考项目和 Codex 官方规范的调研与证据 |
| [`docs/manual-acceptance.zh-CN.md`](docs/manual-acceptance.zh-CN.md) | 中文 | 在 Codex 桌面版用自然语言做人工验收的清单 |
| [`BLOCKED.md`](BLOCKED.md) | 英文 | 仍未决的问题与演示／夹具合成数据边界 |

## 参与贡献与安全

提交 Pull Request 前请读 [`CONTRIBUTING.zh-CN.md`](CONTRIBUTING.zh-CN.md)；报告任何与凭据相关的问题前请读 [`SECURITY.zh-CN.md`](SECURITY.zh-CN.md)。只读的交易边界和凭据隔离规则由测试强制，不靠约定。
