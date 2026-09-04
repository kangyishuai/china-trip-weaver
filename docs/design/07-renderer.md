# HTML Renderer 合同

v1 只有一个确定性 renderer。它以通过 Schema 与语义校验的 Trip 为**唯一数据输入**，输出手机优先单文件 HTML；不得联网查事实、重排、补价、转换未知坐标或修改 Trip。[依据：研究决策 16](../research/04-design-insights.md#16-采用v1-只做一个-deterministic-手机-html-renderer)

## 1. 输入、输出与确定性

接口语义：

```text
render(validated_trip, renderer_version="1") -> trip.html
validate_html(trip.html, validated_trip) -> report
```

- 数据输入只有 `trip.schema.json` 实例；颜色、布局、文案模板和 CSP 是 renderer version 内部常量，不能另传 provider/page model。
- 相同 canonical Trip bytes + renderer version 必须输出完全相同 bytes；不读取当前时间、随机数、locale 环境、网络、credentials 或 provider。
- `generated_at`、query time、版本等都来自 Trip；renderer 不写“刚刚”“实时”等不可复现文本。
- 输出为 UTF-8、单文件、无 sidecar。文件名由 `trip_id` 安全化得到 `<trip_id>.html`。
- HTML 内嵌 canonical Trip：`<script id="trip-data" type="application/json">…</script>`；`<`, `>`, `&`, U+2028/U+2029 安全转义，确保用户文本不能闭合标签。

一个内嵌 Trip 让后续 revision 从结构数据继续，不反解析 DOM；页面与规划不能有两套事实。[依据：研究决策 4](../research/04-design-insights.md#4-采用一个版本化-itineraryjson-是所有层的唯一事实源)

## 2. 页面信息架构

按固定顺序渲染，空 section 仍以“无/未提供”表达关键状态，不能删去未知：

1. `header`：标题（由 destinations/dates 生成）、日期、人数、revision、mode badge。
2. `.truth-banner`：动态数据时点、最差 provider health、unknown 数量、交易边界。
3. `nav`：按 day 的 anchor links；无 JavaScript也可跳转。
4. `request-summary`：origin/destinations、预算、兴趣、节奏、constraints/assumptions。
5. `transport-summary`：跨城腿、时刻、typed price、状态、官方/booking deep link。
6. `lodging-summary`：片区/候选、入住日期、typed price/unknown、条件与 deep links。
7. `days`：每一天的线性 timeline；slot 展示时间、类型、标题、status/lock、移动时长与 claim badges。
8. `location-overview`：只用 Trip 中已存在的 WGS84/GCJ02 点画内联 SVG **位置示意**；醒目标注“非真实路线”，另给 AMap/官方 `https` deep links。
9. `alternatives-and-unknowns`：未排候选原因、unknown field/reason/下一步。
10. `evidence`：按 claim 分组的 source/provider/queried_at/status/confidence；不嵌 raw payload。
11. `provider-health`：所有 provider version/mode/status/check time/reason。
12. `footer`：只读/不保证库存价格/不下单实名支付退改声明，schema/renderer version。

每个展示的时间、价格、车次、开放状态、路线时长必须能从 embedded Trip 精确定位；模板不得引入经验数字。

## 3. 手机优先与可访问性

硬合同：

- viewport meta 为 `width=device-width, initial-scale=1`；基线宽 320–430 CSS px，无横向滚动。
- 单列为默认；≥768px 才可两列 summary，timeline 仍保持阅读顺序。
- 正文字号至少 16px、line-height ≥1.45；可点区域至少 44×44 CSS px；不能只用颜色表达 mode/status。
- 语义元素：一个 `main`、有序 `h1→h2→h3`、`nav` label、time `datetime`、列表/表格正确表头；每个 SVG 有 title/desc。
- `:focus-visible` 清晰；色彩达到 WCAG AA 对比；支持 `prefers-reduced-motion`（v1 实际不含 motion）。
- print stylesheet 展开 details、隐藏纯导航、保留 URL/unknown/evidence，避免 timeline 被 page break 截断。
- `lang` 取 `request.locale`；日期显示 Asia/Shanghai，机器值保留 ISO 8601。

## 4. 离线、地图与图片降级

只承诺**核心离线可读**，不声称完整离线地图。[依据：研究决策 17](../research/04-design-insights.md#17-采用只承诺核心离线可读地图图片显式降级)

### 4.1 核心离线

断网/airplane mode 必须仍可读：header、request、全部 day/slot、交通住宿摘要、prices/unknowns、claims 的文字/URL、provider health、交易声明和内嵌 Trip。CSS、icons、位置 SVG 均内联；不依赖 CDN/font/tiles。

### 4.2 地图

- v1 不加载 AMap JS、Leaflet、OSM tiles 或任何 remote map script；因此不需要/不接受 JS Key/security code。
- 有点位时按 WGS84 做归一化画布，或在中国境内用 GCJ02 画相对示意；同一 SVG 不混 CRS。图上只画 markers/访问序号，连接线若存在必须标“日程顺序示意，非道路路线”。
- 每个点可给已存在的安全 `https://uri.amap.com/...`/官方链接；链接离线时自然不可用，但文字地址/坐标仍可复制。
- coordinates unknown 时显示“位置未核验”，不放 `(0,0)` 或默认城市中心。

### 4.3 图片

Trip v1 Schema 没有 image 字段，renderer 不请求远程图片；用纯 CSS category block/initials。未来若加图必须先升 Schema 并定义 license/source/alt/offline placeholder，不得在模板私自抓图。

这比把 Leaflet/CDN/remote image 包装成完全离线更诚实，也把 AMap secret 排除出共享文件。[依据：开放问题 Q12](../research/05-open-questions.md#q12-手机单文件-html-能否同时做到-secret-free核心离线与地图可用)

## 5. 安全合同

### 5.1 Remote resource policy

v1 **远程脚本为零**，也不加载远程 CSS、font、iframe、analytics、pixel、service worker、form action 或 fetch/XHR。唯一远程行为是用户主动点击的 `https` 链接。

HTML 必须含等价 CSP：

```text
default-src 'none';
img-src data:;
style-src 'unsafe-inline';
script-src 'none';
font-src data:;
connect-src 'none';
frame-src 'none';
object-src 'none';
base-uri 'none';
form-action 'none'
```

非执行 `application/json` data block 是唯一允许的 `<script>` 元素，无 `src`；validator 必须确认它不包含可执行 MIME 或标签逃逸。若目标 browser 的 CSP 对 data block 行为有差异，embedded JSON 改用转义 `<template>`，不能放宽 `script-src`。这是阶段三浏览器兼容测试项。

### 5.2 Escape 与 URL

- 所有 text/attribute/JSON contexts 分别 escape；不得把 provider HTML、Markdown 或 `systemMessage` 当 trusted HTML。
- 只允许 `https` 外链；拒绝 `javascript:`, `data:`（用户链接）、`file:`, `blob:`, protocol-relative、embedded credentials、非白名单 query key 名。
- 外链使用 `rel="noopener noreferrer"`；不使用 `<base>`。
- 无 form/input/contenteditable；页面只读。

### 5.3 Zero-secret

renderer 进程不接收 provider env，Trip Schema 没有 credential 字段；输出扫描实际 canary 与 `api[_-]?key|token|secret|authorization|AMAP_SECURITY` 等模式。命中即 fatal，不尝试“遮住后发布”。HTML 中保存 Key 是硬禁令。[依据：研究决策 18](../research/04-design-insights.md#18-不采用聊天cli-参数源码目录html-中保存-key)

## 6. 数据到 UI 的精确映射

| Trip | UI | 规则 |
|---|---|---|
| top `mode` | header badge | mock 必须同时显示 mock_notice；cached/static 不可标“实时” |
| `revision/patches` | revision badge/change details | 当前 revision 与最后 patch reason；不重建不存在的 diff |
| `days[].slots[]` | timeline | 严格输入顺序；不自动排序，以便暴露 validator bug |
| entity `claim_ids` | fact badges/source links | 每个动态 fact 至少一个 claim；conflict/unknown 显眼 |
| `price` | price token | 同时显示 amount/unknown、currency、unit、price_type、queried_at |
| `coordinates` | SVG/deep link | AMap link 用 GCJ02；位置示意不得冒充 route |
| `provider_health` | health table/banner | status/reason 原义，不把 missing 变 warning-only |
| `unknowns` | dedicated section + inline marker | 页面不能只在 footer 笼统免责声明 |
| `locked` | lock label | 只表示 replan 稳定性，不表示已付款，除非 claim 明确 |

## 7. 生成后 validator 规则

所有检查产生 `error|warning` 和稳定 code；任一 error 使 render command exit 1，文件不得交付。

### 7.1 结构/一致性 errors

- E001：缺 doctype/charset/viewport/lang/唯一 main/h1。
- E002：`trip-data` 缺失、超过 1 个、不能 parse，或 parse 后不与输入 canonical-equal。
- E003：任一 day/slot/entity ID 未恰好渲染一次；或 UI 出现 Trip 中不存在的时间/价格/service number。
- E004：内部 ID 重复、anchor 断裂、heading 顺序错误。
- E005：claim/unknown/provider-health 必要 section 缺失。

### 7.2 安全 errors

- E101：任何可执行/remote script、remote CSS/font/image/iframe/object/form/fetch hook。
- E102：CSP 缺失或比本合同更宽。
- E103：未 escape HTML/attribute/JSON，或危险 URL scheme/embedded credentials/query key。
- E104：secret/canary/credential variable value 命中。
- E105：链接不是 `https` 或缺 `rel`。

### 7.3 事实/降级 errors

- E201：mock 无 notice；cached/static/estimate 被称“实时/已验证路线/可购买总价”。
- E202：动态 fact 无 claim link；price 无 price_type；unknown 未展示原因。
- E203：位置顺序连线未标 schematic，或 unknown coordinate 被替换为默认点。
- E204：renderer 输出包含登录、购买、支付、取消、改签 action/form 文案，而不是只读 deep link。

### 7.4 视觉/可访问性门禁

- 解析 CSS/DOM：320/375/430px 无横向 overflow；touch target/font/heading/landmark/time/contrast/print rules 检查。
- headless browser 在 network denied 下打开：核心 12 sections 有内容、无 failed resource request、无 console error。
- 375×812 与 1440×900 截图对 golden layout 做结构阈值/人工审阅；动态文字变化不做脆弱像素全等。
- 所有 SVG 有 title/desc；纯装饰元素 aria-hidden。

## 8. 降级显示矩阵

| 情况 | 页面表现 |
|---|---|
| AMap ready/live | 显示 route duration claim、点位示意、AMap deep link；仍不画道路 geometry |
| AMap missing | 位置可来自其他有 CRS 来源；route estimate/unknown 明示，deep link 可保留 |
| coordinates unknown | 不画 marker，显示地址/名称与“位置未核验” |
| price unknown | 显示“价格未知/点击核验”+ price type，绝不显示 ¥0 |
| remote link offline | 核心文字仍在；链接保留可复制，不出现空白卡片 |
| provider degraded | truth banner + health table；对应事实 inline badge |
| no feasible schedule | **不生成正常行程 HTML**；交付 structured no-solution Markdown/JSON 由主入口解释 |

## 9. Renderer acceptance

用 valid schema fixtures、keyless E2E Trip、含危险文本/URL/secret canary 的 adversarial fixtures 验证：确定性 bytes、embedded Trip equal、所有 section/count、zero remote scripts/resources、zero secret、offline core、mobile/print/a11y、claim/price/unknown truthfulness。renderer 只在全部 errors 为 0 时返回 success。[依据：研究决策 21](../research/04-design-insights.md#21-采用四层测试不把能启动能打印当测试)
