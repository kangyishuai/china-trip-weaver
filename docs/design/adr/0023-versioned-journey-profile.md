# ADR-0023：版本化旅程剖面候选

- **Status:** Proposed for independent review; no production rollout or visual acceptance
- **Date:** 2026-09-23

## Context

[ADR-0006](0006-single-deterministic-renderer.md) 定义了 v1 的无执行脚本单文件 Trip 页面。长 Journey 的日期、交通、住宿和核验项在旧页分散；隔离的 Victor 原型把路线、共同时间尺度、所选日上下文及可撤回的局部 +30 分钟试探放在同一阅读路径。用户真实截图揭示标题断字、焦点内部滚动和价格枚举外露；原型已按源数据修正，但修复后的浏览器画面尚未验收。

## Candidate decision

同一 `ctw render`／`ctw journey render` CLI 入口生成带 `data-renderer-version="2"` 和 `ctw-renderer` meta 的 v2。旧 v1 HTML 继续由原校验器按原合同验证。Python `render_trip(..., renderer_version="1")`／`render_journey(..., renderer_version="1")` 保留原公开调用与字节行为；v2 可显式传入 `renderer_version="2"`。CLI 与规划/重规划输出选 v2。没有第二个面向用户的 `explore` 命令。

v2 首屏是路线、优先决定、共同时间轴和所选日；在页面下方的“完整行程与来源记录”折叠区复用 **同一份 v1 渲染函数**输出的可读事实，不从 JSON 隐藏恢复。这样迁移期可逐项审查能力覆盖，避免复制运输、天气、餐饮、位置、预算、风险等生成逻辑。代价是 v2 页面较大，展开完整记录后会看到部分重复信息；这是待独立视觉与信息架构验收的明确限制，不能据此宣布最终设计通过。

交互脚本是插件 `assets/profile.js` 的固定版本字节。v2 CSP 仅放行该字节的 SHA-256，仍禁止默认资源、网络连接、表单、frame、object 与外部脚本；CSS 与源 JSON 都内联，离线单文件。校验器用受信插件资产和输入 JSON **重新确定性生成整个页面并逐字节比较**，还单独核对执行脚本与嵌入 source。这会拒绝脚本和 CSP 同时改写、伪造可见金额/时段、删来源或改链接。该合同刻意只接受本版本生成的规范化页面；人为重排空白也须重新生成。v1 的 E/JH 安全断言不因此放松。

无 JS 时全部日程节点和完整事实记录可读，前后一天及试探按钮由 CSS 隐藏；启用受信 JS 后只切换所选日、显示局部预计算后果和撤回，不写输入或持久化。试探仅允许未锁定、无真实车次的 `static`/`mock` 草案交通，排除未生效/自由时段、异组同时出发的交通以及跨日安排；半开区间交集同时记录原草案已有重叠和试算后总重叠。没有来源依据的车次、票价或后续重排不推断。

## Boundaries and review gates

此 ADR 只记录当前分支候选，**不替换 v1 已接受合同的历史含义**。它不修改 Trip/Journey schema、provider、planner、发布版本或已安装插件。生产 CSP 迁移、页面视觉和 390/1440 响应、键盘/触控、浏览器 CSP 实际执行、打印、真实截图仍需获准浏览器的独立复核；本轮非浏览器测试不能替代这些门。若否决 v2，CLI 输出版本切回 v1，旧 validator 与 JSON 无需迁移。
