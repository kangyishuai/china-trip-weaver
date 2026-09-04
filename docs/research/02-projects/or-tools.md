# OR-Tools 项目解剖

## 版本锁定

- 官方文档：`https://developers.google.com/optimization/install/`、`https://developers.google.com/optimization/routing/vrptw`，抓取日期 `2026-09-03`。
- 包：`https://pypi.org/project/ortools/`，实装 `ortools==9.15.6755`；wheel 上传 `2026-01-14T15:39:10.584140Z`。
- task 0 仓库 HEAD（仅连通证据，未 clone/未据此读代码）：`google/or-tools@98c165af62df62b3056c2ee0fca66b24e79097cb`。
- 类型：Google C++/Python/Java/.NET 运筹优化 library；本研究只用 Python binary wheel，不是 Skill/Plugin/MCP/旅行应用。
- 许可证：Apache 2.0。

## 1. 定位与触发

不是 Agent Skill，没有自然语言 trigger。官方首页 description 原文：

> OR-Tools is fast and portable software for combinatorial optimization.

PyPI/pip summary 原文：

> Google OR-Tools python libraries and modules

调用方式是代码显式 import。对旅行问题最相关的触发条件：需要在候选点之间优化顺序，同时满足 opening/appointment time windows、service/dwell time、travel matrix、等待、起终点、车辆/天数等硬约束；普通 POI search/数据抓取不应触发它。

## 2. 输入、输出与数据结构

官方 VRPTW（Vehicle Routing Problem with Time Windows）模型：

- `time_matrix[i][j]`：点 i→j 的离散 travel time；OR-Tools 不自己查地图。
- `time_windows[i]=(earliest,latest)`：到达/开始服务窗口。
- `num_vehicles`/`depot`，旅行场景可把每一天/旅行者抽象为 route，但是否合理要另建模。
- `RoutingIndexManager` 负责 node/index 映射；`RoutingModel` 负责 arc/next variables。
- transit callback 可以是 travel，或在 Time dimension 中用 `service[from]+travel[from][to]`。
- `AddDimension(transit, slack_max, horizon, fix_start, "Time")` 建累计时间；`CumulVar(index).SetRange()` 加时间窗。
- search parameters 选择 first-solution/local-search 策略，`SolveWithParameters` 返回 assignment 或 `None`。

输出不只是 route order，还能读每点 `assignment.Min/Max(Time.CumulVar)` 的 solution window、objective/travel time、waiting slack。官方说明 solution window 位于 constraint window 内，min<max 表示可以等待。

本研究的 6 点输入在 `evidence/or-tools-vrptw.py`（调研期中间产物，未收入本仓库）：Hotel depot、Palace/Museum/Lunch/Garden/Viewpoint；6×6 travel matrix；09:00–18:00 分段 windows；service 45–75 分钟；一辆车。输出和 assertions 验证每点只访问一次且 arrival 在 window 内。

## 3. 脚本与依赖

官方建议 `python -m pip install ortools` 且使用 virtualenv。本研究严格安装在 `research/.venv/`：

- Python `3.13.12` arm64；OR-Tools `9.15.6755`。
- dependencies：absl-py 2.5.0、immutabledict 4.3.1、numpy 2.5.2、pandas 3.0.5、protobuf 6.33.6、python-dateutil 2.9.0.post0、six 1.17.0、typing-extensions 4.16.0。
- wheel：`ortools-9.15.6755-cp313-cp313-macosx_11_0_arm64.whl`，`21,914,246` bytes（约 21.9MB），SHA-256 `076565b803c85c4f87863e0616f537dd37f99c03e6f092e4068404f7b425d2b0`，与 PyPI JSON 完全一致。
- 安装 wall time `25.68s`（Aliyun 配置镜像下载；hash 用 PyPI 官方 metadata 复核）。
- venv 总体 188MB，`site-packages/ortools` 67MB/454 files；对 Skill plugin 是明显体积/冷启动成本。

完整原始下载、hash、install、version/pip show：[`../evidence/or-tools-install.txt`](../evidence/or-tools-install.txt)。

## 4. 外部服务、Key、配额与费用

solver runtime 完全本地，不需要 API Key、网络 quota 或按次费用。开源 wheel 免费；PyPI 安装是唯一网络步骤。

但旅行系统必须从别处提供：POI、开放时间、service duration、AMap travel-time matrix、pinned/optional status、用户偏好。输入过时/错误时，solver 只会稳定优化错误模型。若需要商业第三方 solver，官方说明可能要源码构建；本研究不涉及。

无网络降级：只要 wheel 已安装与输入 matrix 在本地，继续可解；如果候选/route data 无法获取，不能用直线距离偷偷替代而不标 estimate。

## 5. 测试现状与实测

按任务要求运行 ≤8 点、带 time windows 的最小例子：

```bash
/usr/bin/time -p research/.venv/bin/python research/evidence/or-tools-vrptw.py
```

实测 exit `0`，OR-Tools `9.15.6755`：

```text
route=Hotel -> Palace -> Museum -> Lunch -> Garden -> Viewpoint -> Hotel
visited=6/6 unique=6
travel_minutes=115
elapsed_minutes=535
0:Hotel return=17:25..17:25
real 5.07
```

各点 arrival range 均打印并由 assertion 验证落在 window 内；完整原始输出：[`../evidence/or-tools-vrptw-output.txt`](../evidence/or-tools-vrptw-output.txt)。首次进程还经历约 30s native load/solve，第二次 warm run 5.07s；本例搜索 time limit 5s，生产应按规模设更小/可取消 budget。

## 6. 优点、缺点与职责边界

### 优点

- 真正 deterministic 的 feasibility/optimization，能把 opening windows、预约、service、waiting、start/end 变成硬约束。
- VRPTW 输出可解释的 arrival ranges，不只是“看起来顺路”的顺序。
- 本地、无 Key、成熟、Apache 2.0、Python 3.13 arm64 wheel 可用。
- 约束可扩到 multiple days/vehicles、optional nodes/penalties、precedence/capacity，适合复杂日程内核。

### 缺点

- 21.9MB wheel、188MB venv、native cold start 对一次性 Skill 很重；简单 6 点 heuristic/DP 可能更划算。
- 不提供 travel times/POI/hours/content/source，必须有可信 provider/data contract。
- VRP 原语不是旅行体验语义；meal、energy、pinned、雨备、住宿、跨日、用户“宁愿少去”都需额外建模。
- solver route 可行不等于现实可走；matrix 需 mode/time-of-day，交通班次/拥堵变化要重新 query。
- local replan 是重新求解；如果不加 stability penalty，微小输入变化可能大幅改整天，伤害用户已接受计划。
- 整数时间与 search budget/heuristic 可能是可行但非全局最优；需保存 objective/limit/status，不声称“最优”除非证据成立。

### 职责边界

只负责给定候选/matrix/windows/constraints 后的 route & schedule feasibility/optimization。完全不负责研究、库存、地图 API、凭据、来源证据、UI/HTML 或交易。

## 7. 可搬走什么、为什么不搬

### 采用其思想

- 采用 time dimension、arrival window、service time、waiting slack、depot/end 与 explicit no-solution。
- 用它做“候选数/约束复杂时”的可选 scheduler；输出 arrival ranges/solver status/objective 写入 evidence。
- 局部重排加入 stability penalty/locked nodes，仅对受影响 day 重新求解。

### 不直接默认搬入 runtime

- 不因“专业”就把 188MB venv 作为每次 plugin 必需依赖；先 benchmark 旅行常见 5–12 POI 的轻量算法 vs OR-Tools。
- 不让 solver 猜 matrix/dwell/windows；所有输入必须带 source/estimate status。
- 不把 feasibility 当 content quality，也不把 heuristic solution 无条件叫 global optimum。
- 不在本阶段 clone 1.3GB repo；wheel + official docs 已足够验证能力。

## 8. 能力矩阵证据

<a id="cap-destination-research"></a>
- 目的地调研：**无**。

<a id="cap-train"></a>
- 火车：**无**。

<a id="cap-flight"></a>
- 航班：**无**。

<a id="cap-lodging"></a>
- 住宿：**无**。

<a id="cap-poi-geocode"></a>
- POI 与地理编码：**无**。

<a id="cap-route-validation"></a>
- 路线校验：**有**。给定 matrix/windows 后校验并优化完整 route，No Solution 可显式返回。

<a id="cap-hourly-schedule"></a>
- 逐时排程：**有**。time windows/service/waiting/arrival range；6 点实测通过。

<a id="cap-local-replan"></a>
- 局部重排：**部分**。可重解受影响模型，但没有 built-in plan diff/stability 语义。

<a id="cap-html"></a>
- HTML 交付：**无**。

<a id="cap-credentials"></a>
- 凭据管理：**无**。solver 不需要凭据。

<a id="cap-tests"></a>
- 测试：**有**。官方有完整 examples；本研究 6 点 time-window 程序 assertions/exit 0。

<a id="cap-source-evidence"></a>
- 来源证据：**无**。只消费输入数据，不保存事实来源。
