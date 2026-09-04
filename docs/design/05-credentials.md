# 凭据设计

MVP 的 Key 都是可选增强；无 Key 必须仍能完成 `01-product-scope.md` 的 baseline。凭据只通过环境引用或权限受控的本地文件进入单一 provider process，不进入 Trip、对话、命令参数、日志、HTML 或版本控制。[依据：研究决策 18](../research/04-design-insights.md#18-不采用聊天cli-参数源码目录html-中保存-key)、[官方凭据规范](../research/01-codex-spec.md#9-凭据环境变量与沙箱网络)

## 1. 支持的变量

| Provider | canonical 变量 | 兼容/非 secret 配置 | 是否必需 | 注入范围 |
|---|---|---|---|---|
| AMap Web Service | `AMAP_WEBSERVICE_KEY` | 不接受旧 `AMAP_KEY`，避免脚本歧义 | 可选 | 仅 `providers/amap.py` 子进程/调用上下文 |
| FlyAI | `FLYAI_API_KEY` | 无 | 可选增强；trial 另 probe | 仅 FlyAI CLI 子进程 |
| VariFlight | `VARIFLIGHT_API_KEY` | `X_VARIFLIGHT_KEY` 只作读取兼容；`VARIFLIGHT_API_URL` 非 secret | 可选 | 仅 `variflight` MCP |
| AnySearch | `ANYSEARCH_API_KEY` | 禁止 anonymous auto-save/auto-register | 可选且默认关闭 | 仅 AnySearch adapter |
| 12306 / host web | 无 | 无 | 不适用 | 不接收任何上述 Key |

AMap JS 的 `AMAP_JSAPI_KEY/AMAP_SECURITY_CODE` 不在 MVP 支持表，因为可分享 HTML 禁止嵌 secret；interactive map 只能是无 secret deep link/白名单在线增强。[依据：开放问题 Q12](../research/05-open-questions.md#q12-手机单文件-html-能否同时做到-secret-free核心离线与地图可用)

## 2. 来源与优先级

从高到低：

1. **当前进程环境变量**：包括用户/宿主 secret store 安全注入的 env；同名值存在即使用，不读取文件覆盖。
2. **本地文件**：`~/.config/china-trip-weaver/credentials.env`，仅在对应 env 未设置时按变量逐项补齐。
3. **missing**：不弹出粘贴框、不猜值、不自动注册，写 provider health 后走降级。

这是 value priority；`.mcp.json`/配置只允许写变量名，不写实际值。MCP 与命令网络是不同控制面，启用 sandbox network/allowlist 不能替代 provider auth，也不能证明 remote MCP 没有 secret。[依据：官方凭据与沙箱边界](../research/01-codex-spec.md#9-凭据环境变量与沙箱网络)

### 2.1 `0600` 本地文件合同

阶段三 setup 命令可在用户**明确执行**时创建：

```text
~/.config/china-trip-weaver/credentials.env
```

硬规则：

- POSIX 上必须是当前用户拥有的普通文件、不是 symlink、mode 精确 `0600`；父目录建议 `0700`。不满足即拒绝读取并标 `forbidden`，不得自动放宽权限。
- 最大 64 KiB；UTF-8；每行只允许 `NAME=VALUE`、空行或 `#` 注释；不执行 shell、不展开 `$VAR`、反引号、转义命令、`export` 或 include。
- 只接受上表 canonical/兼容 allowlist；未知变量报 warning，不转发。
- 文件读取后只把某 provider 的值放入该 provider 的短生命周期 env mapping；不修改全局 `os.environ`，不传给 renderer/scheduler/12306。
- setup 输出只列 `configured/missing`，绝不回显长度、前后缀或 hash。删除/轮换由用户编辑/删除该文件并重启 provider process。

本设计阶段不会创建或读取该用户文件。

## 3. 五条禁令与检测手段

| 禁令 | 实现控制 | 可复现检测 |
|---|---|---|
| **不进对话** | Skill 永不要求“粘贴 Key”；只提示变量名、文件路径和本机配置命令。用户误贴时不复述，要求撤销/轮换并停止 provider 调用。 | 对 Skill/prompt 文本做 fixture 检查；安全测试输入假 Key，断言回复不包含值且不调用工具。 |
| **不进命令行参数** | subprocess 只通过最小 env mapping 注入；禁止 `flyai config set KEY ...`、URL query key、shell 拼接。 | 捕获 argv/`ps` 快照，断言 canary secret 不出现；adapter 单测检查 `shell=False` 与 argv 常量。 |
| **不进日志** | 结构日志使用字段 allowlist；异常只记 class/status/request_id；stderr 先 redaction 再持久化，默认不保存 provider raw stderr。 | 用每个 secret canary 跑 success/error/timeout，再对 logs/evidence 执行 exact/entropy/known-prefix scan，必须 0 命中。 |
| **不进 HTML** | Trip Schema 无 credential 字段；renderer 不读取 credential store/env；远程 URL 先剥 credential/query denylist。 | 对 HTML 搜索 canary、变量名、`key=`, `token=`, `secret=`, auth header；解析所有 URL 并断言无 denylist 参数。 |
| **不进 Git** | 凭据路径位于用户 config；未来仓库只提供无值的 `credentials.env.example` 并 ignore `.env`/credential patterns。 | CI/提交前 gitleaks 或等价 secret scanner + canary test；tracked-files 检查禁止 `credentials.env`。 |

以上五项任一失败都是 release blocker，不允许用“已 redacted 大部分”降级通过。[依据：研究决策 18](../research/04-design-insights.md#18-不采用聊天cli-参数源码目录html-中保存-key)

## 4. Provider-specific 注入

```text
credential resolver
  ├─ amap process       ← AMAP_WEBSERVICE_KEY only
  ├─ flyai process      ← FLYAI_API_KEY only
  ├─ variflight MCP     ← VARIFLIGHT_API_KEY (+ URL config)
  ├─ anysearch process  ← ANYSEARCH_API_KEY only
  ├─ 12306 MCP          ← no project credentials
  ├─ scheduler          ← none
  └─ renderer           ← none
```

- 子进程环境从最小 allowlist 构造，不盲目复制凭据文件或所有 provider secrets。
- MCP `env_vars` 只声明变量名；实际值由宿主/当前环境提供。无 Key 时 VariFlight 可完成 tools/list，但主入口不得发业务调用。
- provider stderr 可能自行泄露值；因此 error path 必须先内存 redaction，且 contract tests 使用 canary 验证。
- `FLYAI_API_KEY` 不写 FlyAI 自有全局 config；CLI 每次由 adapter 环境注入，避免未知权限/存储路径。[依据：FlyAI 漂移开放项](../research/05-open-questions.md#q3-fly-aiflyai-cli-的当前-commandschemakeyless-trial-到底是什么)

## 5. 缺失、错误、过期与限额 UX

主入口只展示状态与修复位置，不显示值：

| health | 用户文案含义 | 行为 |
|---|---|---|
| `missing` | “未配置 `AMAP_WEBSERVICE_KEY`；已使用无 Key 降级” | 继续 baseline，给本地配置路径 |
| `expired` | “凭据被 provider 判为过期” | 停止该 provider，建议轮换，不自动重试 |
| `forbidden` | “凭据/账户/权限被拒绝” | 停止该 provider，不推断是余额还是封禁 |
| `rate_limited` | “已达限额或 QPS” | 按 Retry-After/缓存/深链降级，不建议立即反复运行 |
| `contract_mismatch` | “凭据可能有效，但返回合同已变化” | 禁止把问题误报为 Key 错误，需更新 adapter |

任何状态都不得诱导用户把 Key 发进聊天。服务 quota/计费只链接当前官方控制台，不把 research 快照硬编码成产品常量。

## 6. 生命周期、轮换与事故处理

1. 值只在 provider process 生命周期内驻留；query 完成后释放 adapter env mapping，不写 Trip/cache。
2. 轮换后必须重启对应 MCP/CLI process；health 记录新 probe 时间，不记录 key identity/hash。
3. 用户误贴或 scanner 命中：停止相关 provider、不要复述 secret、建议立刻在 provider 控制台吊销/轮换；删除本地生成物前先列出确切目标并遵守用户授权。
4. fixtures 必须使用明显 canary 假值；真实响应先脱敏并经 scanner 才可入未来测试目录。
5. 公开发布前完成 provider 条款、缓存/再分发和 marketplace metadata 审核；未完成保持 `UNLICENSED`/local-only。[依据：开放问题 Q14](../research/05-open-questions.md#q14-发布前许可证服务条款与-marketplace-metadata-还缺什么)

## 7. 凭据验收

- 环境变量覆盖文件；文件只补缺，不覆盖环境。
- 文件 mode `0644`、symlink、非 owner、非法语法均拒绝读取。
- 四个 provider 各只能看到自己的 canary；12306/scheduler/renderer 一个也看不到。
- success/auth error/timeout/contract mismatch 路径的 argv、logs、Trip、HTML、fixtures、tracked files 全部 secret scan 0 命中。
- 无任何 Key 时，任务 1 的 keyless E2E 仍生成 schema-valid Trip 与 HTML；provider health 如实降级。
