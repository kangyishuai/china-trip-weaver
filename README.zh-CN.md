# 旅织 China Trip Weaver

[English](README.md) · **简体中文**

准备规划中国大陆自由行？旅织把路线、日期和调研候选整理成适合手机查看的行程：带时间的逐日安排、已选住宿、预算状态，以及需要核验的事项。它是只读的 Codex 插件；所有预订都由你自己完成。

## 在 Codex 中开始

需要 Codex 桌面版或兼容的 Codex CLI，以及 Python 3.9 或更新版本。克隆仓库，从本地市场安装插件：

```bash
git clone https://github.com/kangyishuai/china-trip-weaver.git
cd china-trip-weaver
scripts/install_local_plugin.sh
```

脚本会在你的 Codex 安装中注册本地市场、安装或刷新插件，并完成校验。`scripts/install_local_plugin.sh --check` 只检查现有安装，不刷新。安装后**新建一个 Codex 任务**，让 Skill 生效。如果其他已启用插件也提供 `plan-china-trip`（尤其是 `china-travel-assistant`），先禁用冲突插件；`ctw doctor` 会报告冲突。

在新任务中用一句话说明行程，例如：

> 请用旅织规划两人从北京出发，2026 年 10 月 16 日至 20 日依次去上海、杭州、苏州的五天单向行程。我们喜欢建筑、园林和美食，每天节奏适中，以 8000 元为预算目标。把文件统一放在 `plans/江南五日/`。请展示生成的 HTML，并列出还需要我核验的费用、车次和预订。不要登录或代下单。

打开 `plans/江南五日/` 中生成的 `.html` 文件，先查看来源标签和未知项，再自行预订。旁边的 JSON 是带版本的行程。可选的服务商实网查询可能需要你自己的凭据；来源不可用时，插件会标注降级或未知，不会把结果说成已确认。[规划 Skill](plugins/china-trip-weaver/skills/plan-china-trip/SKILL.md)说明 Codex 如何处理需求。

## 范围

一个 Trip 可覆盖一天或最多七天的有序路线，包括多城市。更长的路线会成为由多个完整 Trip 组成的 Journey，每段仍遵守七天上限。不同旅客组可以从不同城市出发，在指定地点和时间会合。每个过夜日期都必须有覆盖对应日期和目的地的已选住宿；缺少住宿会返回结构化无解结果。

输出会区分已选方案与比较候选，列出支撑事实的证据，并标明静态估算、服务商失败和待核实信息。不会为了补齐空白而编造价格、车次或坐标。你自己的行程应把需求、候选、JSON、HTML 和后续结果统一放在调用插件的项目里的 `plans/<名称>/`。重规划以及天气、餐饮、定位折回通常对同一路径的 JSON 写入新修订，并把 HTML 原地重渲；只有希望另存时才使用新文件名。修订冲突会失败且不写文件。

插件**绝不**登录、提交身份信息、占库存、下单、支付、取消或退改。它尚未在公开 Codex 市场上架。高德、FlyAI、飞常准、AnySearch 的实网能力都是可选的。凭据应放在启动进程的环境中，或当前用户拥有、权限为 `0600` 的 `~/.config/china-trip-weaver/credentials.env`，绝不能放进对话、命令参数、行程或仓库。运行 `plugins/china-trip-weaver/scripts/ctw doctor` 可查看配置状态和 Skill 冲突，但不会显示凭据值。[凭据说明](plugins/china-trip-weaver/references/credentials.md) · [服务商合同与降级规则](plugins/china-trip-weaver/references/provider-contracts.md)

## 复现合成结果（可选）

这个确定性示例不需要服务商 Key，也不发起服务商实网查询。在仓库根运行，输出写入 Git 忽略的目录；只有调用固定版本的实网 MCP／CLI 服务商时才需要 Node/npm。

```bash
mkdir -p .tmp/first-trip
plugins/china-trip-weaver/scripts/ctw plan \
  --request demo/request.json \
  --candidates demo/candidates.json \
  --rail fixture:tests/fixtures/providers/rail12306/empty.json \
  --mobility off --lodging off --aviation off \
  --offline-fixture --fixed-clock 2026-09-04T00:00:00+08:00 \
  --output-json .tmp/first-trip/trip.json \
  --output-html .tmp/first-trip/trip.html
```

在本地浏览器打开 `.tmp/first-trip/trip.html`。夹具刻意不提供车次库存，因此车次、价格和余票仍待核验。也可下载仓库中的[合成 Trip HTML 文件](demo/trip.html)后在本地打开；这个链接是文件入口，不是已部署的在线交互演示。对应数据是 [Trip JSON](demo/trip.json)，其他合成案例在 [`demo/`](demo/) 中。

## 深入了解

- [CLI 入口](plugins/china-trip-weaver/scripts/ctw)：运行 `plugins/china-trip-weaver/scripts/ctw --help` 及相应子命令的 `--help`，查看规划、校验、渲染、Journey 更新和服务商查询。
- [架构与数据合同](docs/design/00-README.md)、[Trip Schema](plugins/china-trip-weaver/schema/trip.schema.json)和[Journey Schema](plugins/china-trip-weaver/schema/journey.schema.json)：实现细节与精确的文档形状。
- [维护者人工验收清单](docs/manual-acceptance.zh-CN.md)、[贡献指南](CONTRIBUTING.zh-CN.md)、[安全说明](SECURITY.zh-CN.md)和[当前状态](PROGRESS.md)。

[MIT 许可证](LICENSE)只覆盖本仓库自己的代码和文档，不授予第三方服务商数据的使用权。除非自行取得相应服务商许可，否则本仓库仅供个人、非商业用途；实网结果不能在此再分发。使用服务商数据或考虑商业用途前，请读[第三方权利说明](THIRD_PARTY_NOTICES.md)。
