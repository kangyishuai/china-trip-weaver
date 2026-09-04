# Codex 插件与 Skill 规范核查

抓取日期：2026-09-03（Asia/Shanghai）。本报告锁定 `openai/plugins@1e285826e604f66f7208f7ac4dba0fe8341d1f57`、`openai/skills@49f948faa9258a0c61caceaf225e179651397431`；在线页面原文、最终重定向 URL 与 SHA-256 见 [`evidence/task1-source-lock.txt`](evidence/task1-source-lock.txt)。

## 1. 证据口径

- `https://developers.openai.com/codex/plugins` 最终落到 `https://learn.chatgpt.com/docs/plugins`。证据（抓取 2026-09-03），原文：“Plugins bundle capabilities into reusable workflows.”
- `https://developers.openai.com/codex/plugins/build` 最终落到 `https://developers.openai.com/plugins/build/plugins`。证据（抓取 2026-09-03），原文：“Every plugin has a `.codex-plugin/plugin.json` manifest.”
- `https://developers.openai.com/codex/skills` 最终落到 `https://learn.chatgpt.com/docs/build-skills`。证据（抓取 2026-09-03），原文：“The `SKILL.md` file must include `name` and `description`.”
- `https://developers.openai.com/codex/mcp` 最终落到 `https://learn.chatgpt.com/docs/extend/mcp?surface=cli`。证据（抓取 2026-09-03），原文：“Codex stores MCP configuration in `config.toml`.”
- `https://developers.openai.com/codex/sandbox` 最终落到 `https://learn.chatgpt.com/docs/agent-approvals-security`。证据（抓取 2026-09-03），原文：“By default, the agent runs with network access turned off.”
- `https://developers.openai.com/codex/config-reference` 的无后缀入口三次 `curl` 失败，但 `.md` 入口重试后成功落到 `https://learn.chatgpt.com/docs/config-file/config-reference`。证据（抓取 2026-09-03），原文：“Enable or disable an MCP server bundled by an installed plugin.”
- `https://agentskills.io/specification`。证据（抓取 2026-09-03），原文：“The `SKILL.md` file must contain YAML frontmatter.”
- `https://github.com/openai/plugins`。证据（克隆 2026-09-03），原文：“This repository contains a curated collection of Codex plugin examples.”
- `https://github.com/openai/skills`。证据（克隆 2026-09-03），原文：“This repository is deprecated.” 因而把它当历史/Skill 样本，不把它当当前插件封装规范；当前样本以 `openai/plugins` 为准。

## 2. 插件目录与 `plugin.json`

最小可分发单元：插件根目录内必须存在 `.codex-plugin/plugin.json`；`skills/`、`hooks/`、`assets/`、`.mcp.json`、`.app.json` 都在插件根目录，不放进 `.codex-plugin/`。证据：`https://developers.openai.com/codex/plugins/build`（抓取 2026-09-03），原文：“Only `plugin.json` belongs in `.codex-plugin/`.”

### 2.1 字段清单

| 字段 | 规范判定 | 结构/语义 |
|---|---|---|
| `name` | 必填 | 稳定插件标识，kebab-case，并作为组件 namespace；官方脚手架额外限制 ≤64 字符。 |
| `version` | 必填（最小示例与所有本机样本均有） | 语义版本字符串。公开页面没有提供可执行 JSON Schema。 |
| `description` | 必填（最小示例与所有本机样本均有） | 插件用途摘要。 |
| `author` | 可选 | `{name,email,url}`；`email`、`url` 可缺。 |
| `homepage`、`repository`、`license`、`keywords` | 可选 | 发布、法律与发现元数据。 |
| `skills` | 可选 | 指向 Skill 集合，通常 `./skills/`。 |
| `mcpServers` | 可选 | 指向 `./.mcp.json`。 |
| `apps` | 可选兼容字段 | 指向 `./.app.json`，映射已注册 MCP/app 连接。 |
| `hooks` | 可选 | 路径、路径数组、内联 hooks 对象或内联对象数组；缺省还会探测 `./hooks/hooks.json`。 |
| `interface` | 可选 | 安装界面元数据，字段见下。 |

`interface` 的公开字段：`displayName`、`shortDescription`、`longDescription`、`developerName`、`category`、`capabilities`、`websiteURL`、`privacyPolicyURL`、`termsOfServiceURL`、`defaultPrompt`、`brandColor`、`composerIcon`、`logo`、`screenshots`。`defaultPrompt` 最多 3 条、每条 128 字符；路径从插件根解析，以 `./` 开头且不得逃出根目录。证据：`https://github.com/openai/plugins/blob/1e285826e604f66f7208f7ac4dba0fe8341d1f57/.agents/skills/plugin-creator/references/plugin-json-spec.md`（克隆 2026-09-03），原文：“Entries after the first 3 are ignored.”

公开页面称其余 manifest 字段可选；本机最小的 `codex-app-tools` 也只有 `name/version/description/author/license`，印证组件与 `interface` 并非装载必需。证据：`https://developers.openai.com/codex/plugins/build`（抓取 2026-09-03），原文：“The other manifest fields are optional.”

## 3. Skill：目录、触发与前置字段

Skill 最小目录只有 `SKILL.md`；约定目录为 `scripts/`、`references/`、`assets/`，可另加 `agents/openai.yaml`。宿主先载入 `name/description`，匹配后才载入全文；显式调用在 Codex 用 `$skill` 或 `/skills`，隐式调用依赖 `description`。证据：`https://developers.openai.com/codex/skills`（抓取 2026-09-03），原文：“Skills use progressive disclosure.”

### 3.1 `SKILL.md` YAML frontmatter

| 字段 | 必填 | 约束 |
|---|---|---|
| `name` | 是 | 1–64 字符；`a-z0-9-`；不能首尾为 `-`、不能 `--`；必须与父目录同名。 |
| `description` | 是 | 1–1024 字符；同时描述做什么、何时触发，含可匹配关键词。 |
| `license` | 否 | 许可证名或仓库内许可证文件。 |
| `compatibility` | 否 | 1–500 字符；产品、系统包、网络等环境要求。 |
| `metadata` | 否 | string→string 的任意映射。 |
| `allowed-tools` | 否、实验性 | 空格分隔的预批准工具；客户端支持可能不同。 |

证据：`https://agentskills.io/specification`（抓取 2026-09-03），原文：“Support for this field may vary between agent implementations.”

### 3.2 `agents/openai.yaml`

这是 Codex/ChatGPT 专用的可选扩展，不是开放 Agent Skills 必填项。已公开的结构为：

```yaml
interface:
  display_name: "用户可见名称"
  short_description: "短描述"
  icon_small: "./assets/small-logo.svg"
  icon_large: "./assets/large-logo.png"
  brand_color: "#3B82F6"
  default_prompt: "默认提示"
policy:
  allow_implicit_invocation: false
dependencies:
  tools:
    - type: "mcp"
      value: "server-id"
      description: "用途"
      transport: "streamable_http"
      url: "https://example.com/mcp"
```

`allow_implicit_invocation` 默认 `true`；设为 `false` 只禁隐式触发，不禁 `$skill`。证据：`https://developers.openai.com/codex/skills`（抓取 2026-09-03），原文：“explicit `$skill` invocation still works.”

## 4. 生命周期 hooks

- 默认文件是 `hooks/hooks.json`；manifest 写 `hooks` 时覆盖默认发现。事件配置的外层是 `{"hooks": {"SessionStart": [...]}}` 一类映射。证据：`https://developers.openai.com/codex/plugins/build`（抓取 2026-09-03），原文：“The default plugin hook file is `hooks/hooks.json`.”
- 插件安装/启用不等于信任 hook；用户审核并信任当前定义前，Codex 跳过插件 hook。hook 命令可读 `PLUGIN_ROOT` 与可写数据目录 `PLUGIN_DATA`，另设 `CLAUDE_PLUGIN_ROOT/DATA` 做兼容。证据同上（抓取 2026-09-03），原文：“Codex skips them until the user reviews.”
- 本机 `browser`、`chrome` 使用 `plugin.json` 内联 `Stop`→`mcp_tool` hook，说明公开规范列出的“内联对象”路径真实落地；见 `~/.codex/.tmp/bundled-marketplaces/openai-bundled/plugins/browser/.codex-plugin/plugin.json`。

## 5. MCP 的两种接入方式

### 5.1 用户/项目配置：`config.toml`

在 `~/.codex/config.toml` 或可信项目的 `.codex/config.toml` 写 `[mcp_servers.<name>]`。STDIO 必填 `command`，可选 `args/env/env_vars/cwd`；Streamable HTTP 必填 `url`，可选 OAuth、bearer token 环境变量、静态/环境 header。证据：`https://developers.openai.com/codex/mcp`（抓取 2026-09-03），原文：“Configure each MCP server with a `[mcp_servers.<server-name>]` table.”

### 5.2 插件内：`.mcp.json`

manifest 的 `mcpServers` 指向根目录 `.mcp.json`。文件既可直接是 server map，也可包在 `mcp_servers`；当前 OpenAI 样本普遍使用 camelCase 顶层 `mcpServers`，Codex 也接受它。安装后不改 manifest，用户仍可在 `[plugins."<plugin>".mcp_servers.<server>]` 控制 enabled、工具 allow/deny 与 approval。证据：`https://developers.openai.com/codex/plugins/build`（抓取 2026-09-03），原文：“either a direct server map or a wrapped `mcp_servers` object.”

插件 HTTP MCP 的 OAuth 字段使用 camelCase：`clientId/callbackUrl/callbackPort`。证据：`https://developers.openai.com/codex/mcp`（抓取 2026-09-03），原文：“Plugin manifests use the camelCase field names.”

## 6. `.app.json`

`.app.json` 是兼容标识，声明已注册的 MCP/app 连接；manifest 用 `"apps": "./.app.json"` 指向它。官方仓库与本机样本的最小形状为：

```json
{"apps":{"sites":{"id":"connector_..."}}}
```

证据：`https://developers.openai.com/codex/plugins/build`（抓取 2026-09-03），原文：“references a registered MCP server connection.” 静态样本：`openai/plugins@1e285.../plugins/figma/.app.json`、本机 `plugins/sites/.app.json`。

重要边界：`.app.json` 只声明依赖/映射，不证明当前用户已安装、授权或可调用；运行时仍需检查可用工具与登录状态。

## 7. Marketplace、位置与 Claude 兼容

Marketplace 是 JSON 目录。两种当前主位置：repo/team 的 `$REPO_ROOT/.agents/plugins/marketplace.json`，personal 的 `~/.agents/plugins/marketplace.json`；另兼容读取 repo 根的 `$REPO_ROOT/.claude-plugin/marketplace.json`。证据：`https://developers.openai.com/codex/plugins/build`（抓取 2026-09-03），原文：“a legacy-compatible marketplace at `$REPO_ROOT/.claude-plugin/marketplace.json`.”

兼容范围要按文字收窄：公开规范只承诺读取 `.claude-plugin/marketplace.json` 这个 legacy marketplace 位置，没有说 `.claude-plugin/plugin.json` 可以替代插件根的 `.codex-plugin/plugin.json`。因此 Claude marketplace 可以作为 repo 入口兼容，实际 plugin package 仍必须补 `.codex-plugin/plugin.json`；`flyai-skill` 只有 `.claude-plugin/plugin.json`，不能据此判定为 Codex-ready。

基本结构：顶层 `name`、可选 `interface.displayName`、有序 `plugins[]`。每个本地条目应含 `name`、`source:{source:"local",path:"./plugins/<name>"}`、`policy.installation`、`policy.authentication`、`category`。安装策略可为 `NOT_AVAILABLE/AVAILABLE/INSTALLED_BY_DEFAULT`；认证时机为 `ON_INSTALL/ON_USE`。相对路径以 marketplace 根解析，不以 `.agents/plugins/` 目录解析。证据：`https://github.com/openai/plugins/blob/1e285826e604f66f7208f7ac4dba0fe8341d1f57/.agents/skills/plugin-creator/references/plugin-json-spec.md`（克隆 2026-09-03），原文：“Always include it.”

桌面应用把安装副本缓存到 `~/.codex/plugins/cache/$MARKETPLACE_NAME/$PLUGIN_NAME/$VERSION/`；本地版本名为 `local`，运行的是缓存副本而非 source 原目录。证据：`https://developers.openai.com/codex/plugins/build`（抓取 2026-09-03），原文：“ChatGPT loads the installed copy.”

## 8. `codex plugin marketplace` 命令

官方命令：

```text
codex plugin marketplace add owner/repo [--ref main] [--sparse PATH]
codex plugin marketplace add ./local-marketplace-root
codex plugin marketplace list
codex plugin marketplace upgrade [marketplace-name]
codex plugin marketplace remove marketplace-name
```

来源支持 GitHub shorthand、HTTPS/SSH Git URL、local root；`--sparse` 只适用于 Git source。证据：`https://developers.openai.com/codex/plugins/build`（抓取 2026-09-03），原文：“Use `--ref` to pin a Git ref.” 本机 `codex plugin marketplace --help` 与 `list` 的原始输出见 [`evidence/task1-cli-scaffold.txt`](evidence/task1-cli-scaffold.txt)。

## 9. 凭据、环境变量与沙箱网络

- STDIO MCP 的 `env` 注入显式值，`env_vars` 只转发已存在环境变量；remote source 需 remote executor。HTTP 凭据优先级包括显式 bearer/OAuth，推荐用 `bearer_token_env_var` 或 `env_http_headers` 引用环境变量，不把 secret 写进仓库。证据：`https://developers.openai.com/codex/mcp`（抓取 2026-09-03），原文：“values pulled from the environment.”
- 外部连接仍服从服务自身 auth/access；插件含 connector/MCP 时，安装或首次使用可能再登录。证据：`https://developers.openai.com/codex/plugins`（抓取 2026-09-03），原文：“Connections to external services use that service's own authentication.”
- 本地默认 `workspace-write` 不开放命令网络；开启需 `[sandbox_workspace_write] network_access=true`。`features.network_proxy` 只约束已经开放的命令网络，不能单独授予网络。证据：`https://developers.openai.com/codex/sandbox`（抓取 2026-09-03），原文：“it does not grant network access by itself.”
- 命令网络代理不覆盖 web search、apps/connectors、MCP、browser/Computer Use、cloud task；这些是不同控制面。对 china-trip-weaver 的含义是：不能把 sandbox allowlist 当成远程 MCP 或 App 的凭据/出站控制。证据同上（抓取 2026-09-03），原文：“It does not filter web search.”

## 10. 桌面应用无 CLI 时的本地安装与验证

不依赖 CLI 的官方路径：

1. 在允许位置准备插件目录与 `.codex-plugin/plugin.json`。
2. repo 方案写 `$REPO_ROOT/.agents/plugins/marketplace.json`；personal 方案写 `~/.agents/plugins/marketplace.json`，使 `source.path` 指向插件目录。
3. 完全退出并重启 ChatGPT desktop app。
4. 打开 Plugins Directory，切换到该 marketplace source，安装插件。
5. 新建 chat/Codex task，再验证 Skill 是否可被 `$name` 显式触发、description 是否隐式命中、MCP 是否列出并能完成只读调用；更改插件后同步 source 并再次重启。

证据：`https://developers.openai.com/codex/plugins/build`（抓取 2026-09-03），原文：“restart the ChatGPT desktop app and verify that the plugin appears.” 通用插件页还要求安装后新开会话，原文：“start a new session.”（`https://developers.openai.com/codex/plugins`，抓取 2026-09-03）。

本阶段没有照此实际安装，因为两种路径都会修改任务明令只读的 `~/.agents`/`~/.codex` 或工作区 `.agents`。实际完成的是 research 内脚手架与静态验证；见下一节。

## 11. 本机版本与官方脚手架/校验实测

- ChatGPT/Codex desktop：`26.901.20858`，build `7658`，bundle id `com.openai.codex`。
- 内嵌 CLI：`/Applications/ChatGPT.app/Contents/Resources/codex`，`codex-cli 0.153.0-alpha.5`。这与任务前置信息“PATH 无 codex”不同；当前会话 PATH 已暴露桌面应用内嵌二进制。
- 官方脚手架：运行 `openai/plugins/.agents/skills/plugin-creator/scripts/create_basic_plugin.py`，成功把 `Spec Probe` 归一化为 `spec-probe`，并在 `research/evidence/` 生成 manifest、`.mcp.json`、`.app.json`、可选目录与 marketplace。
- Skill 校验：用本机官方 `quick_validate.py` 校验上述 `plugin-creator`，输出 `Skill is valid!`。
- `codex plugin --help` 只列 `add/list/marketplace/remove`，未发现独立的 `plugin validate` 子命令；官方脚手架会生成 `[TODO]`，不等同发布校验。Agent Skills 官方另给出 `skills-ref validate ./my-skill`，本阶段没有另装该工具以避免额外全局/venv 依赖。

全部实际命令与原始输出：[`evidence/task1-cli-scaffold.txt`](evidence/task1-cli-scaffold.txt)。脚手架本身：`https://github.com/openai/plugins/blob/1e285826e604f66f7208f7ac4dba0fe8341d1f57/.agents/skills/plugin-creator/scripts/create_basic_plugin.py`（克隆 2026-09-03），原文输出：“Created plugin scaffold”.

## 12. 与本机 `openai-bundled` 逐字段对照

本机只读样本根：`~/.codex/.tmp/bundled-marketplaces/openai-bundled/`；10 个 manifest 的字段计数、MCP/app/marketplace 结构原始汇总见 [`evidence/task1-bundled-comparison.txt`](evidence/task1-bundled-comparison.txt)。

| 检查项 | 规范 | 本机样本 | 结论 |
|---|---|---|---|
| manifest 位置 | `.codex-plugin/plugin.json` | 10/10 一致 | 一致。 |
| `name/version/description` | 最小身份字段 | 10/10 都有 | 一致。 |
| `author/license` | 公开文档归为可选 | 10/10 都有 | 样本更严格，但不证明格式必填。 |
| 组件字段 | `skills/mcpServers/apps/hooks` 均可选 | 分别 8/4/1/2 | 一致。 |
| `interface` | 可选 | 9/10；`codex-app-tools` 无 | 一致。 |
| `.mcp.json` | 接受 server map 或 wrapper | 4/4 使用 `mcpServers` wrapper | 属于接受形状之一。 |
| `.app.json` | `apps` map → registered id | `sites` 为 `connector_...` | 结构一致。 |
| marketplace | `name/interface/plugins[]` + policy/category | 10/10 条目齐 | 一致。 |
| hooks | 默认文件或 manifest 路径/内联 | browser/chrome 内联 `Stop` hook | 一致。 |
| manifest 路径 | 相对根、`./` 开头 | `skills`, `mcpServers`, `apps` 均如此 | 一致。 |

### 12.1 不一致或公开规范未覆盖处

1. 本机 2 个 manifest 有未在公开字段表出现的 `bundledContentVariant`；这是 bundled 内部扩展，不应复制进第三方插件，除非后续官方文档明确。
2. 本机 `interface` 有未在公开字段表列出的 `logoDark`；公开 GitHub 样本还出现 `brandColorDark`。可视为前向兼容/内部 UI 字段，当前产品不依赖。
3. build 文档让开发者从浏览器 URL 复制以 `plugin_asdk_app` 开头的技术 ID，但本机 `.app.json` 是 `connector_...`，GitHub 样本则同时出现 `connector_...` 与 `asdk_app_...`。脚手架不验证/转换 ID；注册 UI 返回值与落盘 ID 的映射需要在真正接入 App 时复核，不能猜前缀。
4. 官方页面没有提供 `plugin.json` JSON Schema 或 `codex plugin validate`；`name/version/description` 的“必填”来自最小示例、文字语义和 10/10 本机样本的交叉证据，而非可执行 schema。发布前仍需用当时的提交/安装流程做最终校验。
5. `/codex/config-reference` 无后缀入口三次 TLS 失败，但 `.md` 入口取得同一官方页面；该替代证据已保留，原失败仍留在 `BLOCKED.md`，没有伪装成原 URL 成功。
