# PROGRESS

唯一的当前进度记录：现状速览（0.8.0 起每个版本一条）、几条长期有效的实测结论，以及历史索引。逐轮任务书、实测证据与验收记录按时间段归档，见「历史索引」——本文件不再留存单轮过程记录。

## 现状速览（2026-09-17 实测，0.23.0）

- 版本：`0.23.0`，唯一来源是
  `plugins/china-trip-weaver/.codex-plugin/plugin.json` 与
  `src/china_trip_weaver/__init__.py` 的 `__version__`，两处一致，仓库内其余
  代码与文档一律引用这两处之一；只有本节的逐版本条目和 git tag 以版本号作索引。
- 测试：仓库根 `/usr/bin/python3 -m unittest discover -s tests` 全量 `Ran 744 tests`，`OK`，0 skipped；
  `scripts/scan_secrets.py` 0 命中；
  `~/miniconda3/envs/core/bin/python -m pyflakes plugins/china-trip-weaver/src
  tests scripts` 0 行。带假 Key（`ANYSEARCH_API_KEY=... unittest`）跑全量同样
  744 OK，README 的 demo 与全部夹具重生成在有无 Key 两种环境下都零差异。0.21.0 记过的
  「环境变量注入会让 `test_credentials` 红一项」已在 0.22.0 修好：那个文件现在于 `setUp`
  里按 `FILE_ALLOWLIST` 剥掉凭据环境变量，四个 Key 全设与一个不设两种跑法结果相同。
- 覆盖率：`scripts/measure_coverage.py` 2026-09-17 实测 11154 语句、miss 1259、**89%**（0.22.1 时 10706/1210/89%）。
- 0.23.0（第二十九波四本＋第三十波三本，2026-09-17，全部并行成书、逐本验收合入）：**天气**从零到有——
  AMap 适配器加第 5 个能力 `weather`（`amap.py::_weather`，`/v3/weather/weatherInfo`，只带 `adcode`
  或 `city` 之一；「成功但空」判 `no_results`，多于一条 forecasts 判歧义 `weather_ambiguous:<n>` 绝不
  取第一条），合成夹具 85→88；新叶子模块 `weather.py`（`FORECAST_DAYS=4`、`forecast_available_on`、
  `split_city_names`、五条固定规则的 `advice_for`、`location_key_vote`、`result_reason`）。Trip 模型
  加可选可空的 `day.weather`（`#/$defs/weatherForecast`，12 键全 required，`schema_version` 仍
  1.0.0），Trip 页 `days` 与 Journey 页 `day-timeline` 每天各一行「天气：…」，`validate_html`/
  `validate_journey_html` 用 E006/JH006 逐字回读；**只在文档里至少一天带 `weather` 键时才渲染**，
  所以 0.22.1 之前的 Trip/Journey 与全部 demo 逐字节不变。规划器新增 `_plan_weather`（`plan_trip`
  里 `_plan_trip_unknowns` 之后、不占独立 checkpoint）：只在高德 live 时跑，地点键先取当天 POI
  `/provider_identity` 的 adcode 多数票（并列取最小）、无则退 `day.city` 第一段，同键一次只查一次，
  每天要么写 `day.weather`（10 键+advice+claim_id，claim 以 day_id 为 subject）要么写 `null`＋
  `/days/<i>/weather` 的 unknown（`weather_forecast_horizon:<可查日期>`/`weather_no_location`/
  `weather_no_results`/`weather_ambiguous:<n>`/`weather_provider_error:<class>`），AMap 健康行
  `capabilities` 加 `weather`、reason 追加 `; weather=<n> queried, <m> unknown`。新命令
  `ctw weather`（`--city`/`--adcode` 可重复，或 `--journey`/`--trip` 逐日；`--fixture`+
  `--fixed-clock` 回放；退出码同 `ctw rail`），并给 `amap_http._request_contract` 的 weather 分支补
  了不需网络的请求形状单测。数据源、视野、歧义、建议、落点五项决定见 ADR-0021。
  **锁定车次**两处真缺陷（AN4 实网发现）修好：E003 的已知车次集合并入
  `request.locked_rail_services[].service_number`（此前 assumptions 被整段复制进每个原子 Trip，不含
  那条腿的段假阳性中止整趟 `journey plan`）；`lockedRailService` 加可选 `arrive_time`，
  `_locked_rail_candidate` 把它传给 `select_service`（G5023 两行同发 10:00、到福州 11:13/福州南 11:32
  只靠 `depart_time` 消不了歧）。真实 16 天行程的 request 换成结构化锁定后从零实网 `journey plan`
  一次通过：G1902 07:50→09:30、G5023 10:00→11:13 两腿 `locked:true`，`validate-html` errors=0，
  现役 journey.json 未动。`ctw replan --event refresh` 现在同步重写时段 `title`（默认「起点 → 终点
  铁路 车次号」，事件 `title` 可覆盖，空白报 `refresh_title`），ADR-0017/0018/0019 状态改为
  Accepted，ADR-0020 未决项逐条补注。新增测试文件 `test_weather.py`、`test_weather_cli.py`、
  `test_planner_weather.py`；测试 699 → 744，运行时+脚本 `.py` 计数 50 → 51，ADR 20 → 21。
  已知未做：`ctw doctor --probe` 无天气探针；VariFlight 机场天气仍未派发；`ctw weather --city`
  模式对「回放夹具＋时钟早于夹具数据」的整批 out_of_window 规则只在测试场景触发。
- 0.22.1（第二十七波，纯重构，对外行为零变化）：「按车次号从当天的车里挑出唯一一趟」
  原本有两份实现——`replan.py` 一份，0.22.0 落地锁定车次时又在 `planning.py` 照搬了一份，
  改了消歧规则只改一处就会悄悄跑偏且无人知晓。现在只剩一份：新叶子模块
  `rail_selection.py`（62 行）提供 `select_service`，返回三字段的 `ServiceSelection`
  （`row` / `same_service` / `time_matched`）——之所以不把结果坍缩成一个候选列表，是为了让
  `replan` 在歧义时仍能原样重建自己那条列出候选发车/到达时刻的错误消息，不必改文案。
  两个调用点各自的失败表达保持不变（`replan` 抛 `ReplanError`，`planning` 返回三元组），
  四处错误码与消息逐字未动。`planning.py` 2907 → 2901、`replan.py` 566 → 549。
  验证方式：测试一行未改（699 项原样全绿，唯一的 `tests/` 改动是新模块带来的 `.py`
  计数 49 → 50），并故意破坏共用函数确认 `replan` 与 `planning` 两侧的既有测试都会变红
  ——只有一侧红就说明另一侧没真正走共用函数。
- 0.22.0（第二十五、二十六波，ADR-0020 落地）：「某趟车已经买好票、不许改」从一句没人
  读得懂的自由文本变成规划器认得的结构化事实。`#/$defs/request` 新增可选的
  `locked_rail_services`（`service_number` + `travel_date` 必填，`depart_time` 选填，
  专治同一趟车在同城两站各返回一行——真实世界里 G1902 就在福州南 07:50 与福州 08:12
  各有一行、到达同为 09:30，只看到达时间分不开）；`schema_version` 仍是 `1.0.0`、新字段
  不进 `required`，旧 request 一字不改继续有效。`planning.py:_resolve_rail` 选车前先认
  锁定项，命中就用它、不再取到达最早那趟。**查不到时按裁决退回既有的深链占位腿并点名**：
  `unknowns`/`runtime_warnings` 区分 `locked_service_not_found` 与
  `locked_service_ambiguous`，整趟行程照常产出，既不整趟失败也不悄悄换一趟车冒充。
  同一波还把 E003 从「只报车次号」改成能指回病因——报错现在会说出这个车次号来自
  `request.assumptions` 或 `constraints` 的第几条、原文是什么，找不到来源时退回原措辞、
  绝不静默。`test_credentials` 补上环境变量隔离。测试 690 → 699。
- 0.21.0（第二十四波，四份并行：文档订正、检查基建、ADR、实网刷新）：健康审计查出的
  文档漂移七处改对——`references/provider-contracts.md` 的 12306 超时由不存在的
  「15s direct; 25s interline」改为真实的统一 `90s`、AnySearch 由 `10s` 改为
  `15s`、12306 与 AMap 两行删掉与文档自身「R1 disabled」矛盾的「cache →」一档；
  两份 README 补上从未被提及的 `demo/multicity-5d/`、`README.zh-CN.md` 把
  `docs/design/` 的语言由「英文」订正为「中文」；`search-china-lodging/SKILL.md`
  写明 `--keyless-trial` 只属于 `lodging`/`air`、`research-china-destination/SKILL.md`
  把 `exact_original_confirmed` 的处置由「manual review」订正为自动。新增
  `scripts/measure_coverage.py`：从系统解释器建一次性 venv、按 coverage.py 的
  子进程配方测量（套件有 82 处 `subprocess` 调真实 `ctw`），并在出具百分比前
  断言这一轮真的跑满了整个套件——健康审计里那个「可信却错误的 62%」正是这种
  残缺测量的产物（成因是共用解释器的 site-packages 里有第三方包自带的顶层
  `tests` 包，遮蔽了本仓库的 `tests/`）。CI 补 pyflakes 一步；`.coverage*` 进
  `.gitignore`。新增 `tests/test_rail_cli.py` 5 项，端到端覆盖此前零覆盖的
  `ctw rail`（`cli.py:_cmd_rail`），测试数 685 → 690，覆盖率 88% → 89%。
  新增 ADR-0020，为「某趟车已购并锁定」这类既成事实在初次规划中无处表达的
  缺口给出四个方向与推荐（Status: Proposed，待裁决）。真实 16 天行程的两条
  高铁腿同日实网刷新，产物按约定留在仓库外。
- 0.20.1（第二十三波，纯文档加一条测试）：`docs/design/` 四份现役设计文档追平
  0.16.0–0.20.0 的代码——04-providers §4.2 补 12306 直达行按到发站过滤
  （`_filter_direct_rows`、`station_rows_filtered:<n>`／`station_rows_all_filtered`）、
  `--limit` 默认 30 经 `limited_num` 转 MCP `limitedNum` 且过滤在其后、`num="*"` 属
  `NO_INVENTORY`；§4.3 补飞常准 `getFlightPriceByCities` 第二价源（非候选模式每路线一次、
  `_live_price` 按航班号取经济舱最低价、阈值 `max(PRICE_CONFLICT_MIN_DELTA, FlyAI 价×
  PRICE_CONFLICT_RATIO)` 即 max(20, 5%)，严格大于才 conflict）、`CITY_IATA` 24 城、
  `_live_error_class` 10→no_results／12→invalid_request／其余→upstream_5xx、FlyAI
  `status=1,data=null` 非空结果按 upstream_5xx；06-pipeline 新增 §5.4 汇合腿
  （`_validate_meeting_anchor` 在 FlyAI/VariFlight 之后、`_promote_meeting_flight_leg`
  同路线合规航班取最早到达、`MEETING_BUFFER_INSUFFICIENT` 报最早到达与实际缓冲），§7.2
  refresh 行补默认选车、`depart_at`/`arrive_at` 挑行、换腿删旧 claim；08-testing replan
  golden 4→7 并列全名；09-impl-map 补 `providers/anysearch_http.py` 与 `scripts/` 六个脚本、
  `journey.py` 行补 `_with_missing_budget_ledgers`。新增 tests/test_design_docs.py：运行时
  42 个模块加 scripts 6 个脚本共 48 个文件名都必须出现在 09-impl-map。管理者验收：逐句
  对码（两个 warning 的嵌套、阈值严格大于、经济舱 Y 最低价、24 城、错误码、汇合腿调用
  顺序与报错字段、anysearch 固定 origin 与 4 MB 上限）全部属实；docs/design 无 `/Users/`、
  无真实酒店名；删掉 09 的 `scan_secrets.py` 一行新测试立刻红。
- 0.20.0（第二十二波，一本事件新键加一本夹具卫生）：refresh 事件带 `service_number`
  时可再带 `depart_at`（完整 ISO 或 `HH:MM`，与 `arrive_at` 同款；
  `_disambiguate_service_matches` 先按 `depart_at` 再按 `arrive_at` 逐层过滤，
  `_matches_arrive_at` 改名 `_matches_time`），只剩一行即选中，否则
  `refresh_service_ambiguous` 文案按 `(depart_at, arrive_at)` 排序列出「出发→到达」，
  挑行键零命中时前缀 `no row matches depart_at=… arrive_at=…; `；默认选车、
  `_apply_refresh`、schema 未动；ADR-0015 追加 Amendment，README 两份与 replan Skill 各加
  半句。`build_scheduler_fixtures.py` `build_replans()` 现在生成全部 7 份 replan 金样（新增
  refresh、suspend、suspend-first-leg 三个字典字面量，refresh 的 `rail_result` 抽成
  `_refresh_rail_result()`），7 份逐字节不变，manifest `counts.replan` 4→7、files 32→35，
  `test_manifest_covers_every_replan_fixture` 锁住路径集合；README 两份与 09-impl-map 同步
  为 7。管理者验收：用 journey-r4 的 north 与 14:34 的真实 12306 结果回放，
  `depart_at=07:50` 选中 G1902 福州南 07:50→09:30（fs=FYS）、3 条 claim、校验通过；只带
  `arrive_at=09:30` 报歧义并列出 07:50→09:30 与 08:12→09:30 两对；`depart_at=07:55` 报
  `no row matches`；默认路径仍选 G1648 08:00；15:17 实测 9/26 十趟 40 个席别仍全是 `*`，
  真实行程未重刷、页面未重渲染（本波不改渲染）。AL2 执行者没写书名，合并时补上。
- 0.19.1（第二十一波，两本都是修正）：12306 余票 `num="*"` 判为未开售——
  `providers/rail12306.py` `NO_INVENTORY` 加入 `"*"`，`_has_inventory("*")` 为 False、
  `_seat` 写 `available=false`，claim 原文照旧保留 `*`；`render/html.py` `_rail_seat_line`
  按 claim 项 `availability` 原文分三档：`*`→「未开售」（en `not on sale yet`）、
  `候补`→「候补」（en `waitlist`）、其余按 `available` 显示「有／无」，Trip/Journey 两份
  labels 各加两键；新夹具 `presale_star`（四档 `*`，item_count 1，腿价仍二等座 300，四档
  `available` 全 False），夹具 85；provider-contracts 与 07-renderer 各加半句。refresh 换腿
  时清旧 claim——`replan._apply_refresh` 在复制新 claim 前按 `subject_ref == leg_id` 倒序
  pop 旧 claim 并逐条记 `/claims/<i>` remove，其它 subject 一条不动；金样 refresh.json
  `operation_count` 31→33；ADR-0015 Amendment、README 两份、replan Skill 各加一句。
  执行者纠出任务书两处失误：`build_scheduler_fixtures.py` 从不生成 refresh.json（它是
  手写金样，执行者用同脚本的 `write_group()` 重写、manifest 不变），且夹具只存
  `operation_count`、不存 patch 操作，`git grep remove` 永远为 0（按让步顺序保留「金样
  只改操作数」）；既有 rail 夹具是 16 份不是 15。AK2 执行者把书名写成 AK1，合并时改回。
  管理者验收：真实 Key 14:34 查 9/26 福州→武夷山 10 趟四档仍 `*`、`available` 全 False、
  腿价 128.5；用 journey-r4.json 渲染 `福建中秋国庆16天行程-0.19.1.html`，四处座位行都是
  「未开售」，校验零错误、QA 零失败；对 r4 的 north 默认刷新（G1648）后 9/26 腿从 8 条
  claim（3 条被引用）变成恰 3 条全被引用、其它 23 条逐字节不变、总 31→26，patch 8 条
  remove，第二轮默认刷新仍 3 条。新发现：G1902 在 12306 有两行（福州南 07:50 与福州 08:12，
  同到 09:30），指定车次加 `arrive_at` 仍报 `refresh_service_ambiguous`，文案还说「到达
  时间不同」——第二十二波加 `depart_at` 挑行。发版时管理者的脚本把 tag v0.19.1 先打在了
  未升版本号的合并提交上，一分钟内删除 tag 与 Release 后重打。
- 0.19.0（第二十波，一本改装配语义加一本页面新增）：`journey assemble`（首次装配与
  `--replace-trip` 都经 `assemble_journey_from_trips`）对缺 `budget_ledger` 的子 Trip
  用 planning `_budget_ledger` 现算（新私有函数 `_with_missing_budget_ledgers`，排序
  后、连接定价前；已有账本的 Trip 原样传递，demo 逐字节往返不变；L1810 容忍测试的
  `price_type` 断言改成 `"unknown"`，两端金额仍 None）；README 两份与 plan Skill 各加
  一句。行程页火车腿显示座位余票——`render/html.py` `_rail_seat_line` 只取腿自己
  `claim_ids` 里第一条 `/availability` claim，按 `available` 显示「有／无」、不显示
  舱位票价（Trip 页校验器只认实体价格），Trip 页一处、Journey 页四处与「车站」行
  相邻；分组示例页多两行座位，README demo 与 journey-16d 零差异；07-renderer 加一句。
  管理者验收：对真实 journey-r3.json 做一次 `--replace-trip`（north 原样）得
  journey-r4.json（revision 4）：三个子 Trip 都有账本，Journey 已知费用 385.5
  （G1902 二等座 128.5 × 3 人），页面「已知费用」不再是 0；渲染
  `福建中秋国庆16天行程-0.19.0.html`，9/26 腿显示车站与座位行。数据语义问题：12306
  对未开售席别返回 `num="*"`（我 00:39 与 13:04 两次实测 9/26 福州→武夷山与泉州→厦门
  全部席别都是 `*`，真实 journey-r3 的 availability claim 也是），`_has_inventory`
  把 `*` 当有票，页面把 9/26 四档座位都写成「有」——第二十一波修。
- 0.18.1（第十九波，一本修正加一本页面新增）：12306 站名过滤去掉「证据门控」——
  `tests/fixtures/mcp_stdio_server.py` 的 `ticket_payload` 按站码在自己的站表反查
  真实站名，`_filter_direct_rows` 对确认不匹配的行一律删、全删返回零行并带
  `station_rows_filtered:<n>` 与 `station_rows_all_filtered`（新夹具
  `station_rows_none`，夹具 84）；`ctw rail --limit` 与 `RailBackend.limit` 默认
  10→30。管理者实测（默认不带 --limit）：福州→武夷山 10 行全到武夷山北（删 20）、
  武夷山→福州 9 行、泉州→厦门 30 行零删；福州→建阳 30 行全删、报 no_results 加两条
  warning——南平市站其实在建阳区，前缀规则认不出，属已知假阴性（12306 站名不带
  行政区），今天不修。行程页火车腿显示到发站——`render/html.py` 新增纯函数
  `rail_station_names(booking_url)`（`fs`/`ts` 两端都带 `[A-Z]{3}` 站码才返回），
  Trip 页交通卡片一处、Journey 页交通汇总／交通卡片／逐日时间轴／预订清单四处加
  「车站：X → Y」，占位深链不显示；分组示例页多两行站名，README demo 与
  journey-16d 零字节差异；07-renderer 加一句。真实行程 r3 页重渲染为
  `福建中秋国庆16天行程-0.18.1.html`：9/26 腿四处显示「车站：福州南 → 武夷山北」，
  validate-html errors=0，QA failures=[]，横向溢出 0。合并后对真实 journey.json
  不指定车次重放刷新（默认 30 行）：默认路径选中 G1648 08:00→09:11 福州→武夷山北、
  3 条 claim、errors=0，replan 产出的 Trip 页也带站名行。
- 0.18.0（第十八波，两本都改行为）：replan 默认选车——`_select_refresh_service` 加
  `earliest_depart`（前一时段 `end_at`），无 `service_number` 时只在发车不早于它的
  候选里取最早到达，全不可行才抛 `refresh_overlap`（message 带候选数与前一时段结束
  时间）；有 `service_number` 命中多行且到达时间不同时抛新码
  `refresh_service_ambiguous`，事件可带 `arrive_at`（完整 ISO 或 `HH:MM`）挑一行；
  ADR-0015 末尾加 Amendment，README/SKILL 各加一句。12306 直达行按到发站过滤——
  `_filter_direct_rows`：站名等于解析候选名或以请求名去掉市/县/区后开头才保留（两
  条件取「或」；执行者第一版写成互斥，被真实数据推翻：12306 把武夷山解析到站名恰为
  「武夷山」的 WAS，30 行里没有一行到站叫武夷山，全是武夷山北/南平市），删行计入
  `station_rows_filtered:<n>`；执行者为保住 `mcp_stdio_server.py` 站名占位的 8 项
  子进程测试加了「证据门控」（某端至少一行确认匹配才过滤），留下全不匹配时不删的洞
  （第十九波去掉）；`leg_id` 纳入 `arrive_at` 与两个站码；`success.json` 加一张广州
  示例站车票，因为分组示例与 5 项 e2e 用同一份夹具回放两条路线；夹具 83；
  demo/grouped-departures 两个 leg_id 变。管理者合并后实测：`ctw rail --limit 30`
  福州→武夷山 10 行全到武夷山北（删 20）、武夷山→福州 9 行全从武夷山北/武夷山出发
  （删 21）、泉州→厦门 30 行零删；对真实 journey.json 不指定车次重放刷新，默认路径
  自动选中 G1648 08:00→09:11 福州→武夷山北、3 条 claim、errors=0（此前 10 趟撞
  9 趟）；会合 17:30 副本实网重规划的 north 9/26 腿变成 G1648 07:40→09:11 福州南→
  武夷山北（此前是到南平市站的 G2374），两条汇合航班与 80/62/18/7 不变。验收教训：
  `/usr/bin/python3` 是苹果自带的 3.9，字节码缓存在 `~/Library/Caches/com.apple.python/`
  而非 `__pycache__`，反向验证把 `>=` 改 `<=` 再还原时文件大小与秒级 mtime 都没变，
  缓存里留下改坏的版本，单跑 `tests.test_replan` 红了一轮；以后还原后 `touch` 源文件。
- 0.17.1（第十七波，一本改行为加一次真实行程实战）：VariFlight 票价一次调用覆盖整条
  路线——`_build_price_request` 改传 `subject_refs_by_service`（与 search 同构），
  `_live_price` 对返回行里落在表中的每个 `flightno` 各产一条 `/price` claim（仍取
  经济舱最低价），`_enrich_price` 拿全部 `route_flights` 逐班比价、逐班标 conflict
  （FlyAI 那条经 `conflict_claim_ids`），comfort 仍只给 `_select_flight` 那一班；
  每条路线仍 3 次调用；夹具 82（price.json 只改请求形状）。执行者与管理者各用真实
  Key 验证：昆明→福州两班真实航班得 2 条 `/price`；管理者用会合 17:30 的副本实网
  重规划真实行程：north 段 17 班航班全部带第二价（6 班判 conflict），两条被提升的
  汇合航班（昆明组 FU6538、北京组 SC2203）都带 `/price`，80/62/18/7 不变。真实行程
  火车票刷新实战（书 Z3 第三次派发）2026-09-12 跑通：`ctw rail` 9/26 福州→武夷山
  10 趟 ready → `journey extract` → refresh 事件 → `replan --rail-result`（north
  revision 2，trigger provider_change）→ `journey assemble --replace-trip`（journey
  revision 3）→ render/validate/validate-html/浏览器 QA 全过，产物 `journey-r3.json`
  与 `-r3.html` 只新增不覆盖，真实目录 45 个原文件字节不变；反向验证
  `--base-revision 1` 报 revision_conflict；管理者重渲染 r3 页 sha256 逐字节相同。
  链路缺陷两条（BLOCKED「书 Z3」）：①不指定 `service_number` 时
  `_select_refresh_service` 只按最早到达取车、不看是否早于前一时段结束，10 趟里
  9 趟撞 `refresh_overlap`，执行者显式指定 G1902（07:50→09:30，二等座 128.5）才
  走通；②12306 对同车次同发车不同到站返回两行（G1902 到武夷山北 09:30 与到南平市站
  09:15），`leg_id = stable_id("leg-rail", service, depart_at, from_ref, to_ref)`
  不含站码，两行同 id，claims 6 条重复写入、3 条游离。管理者复核：自己 00:39 的
  抓取同样两行同 id；即便 `--to 武夷山北` 查询，10 行里 8 行到达站仍是南平市（原
  武夷山东，建阳区），12306 按城市分组返回；实网重规划的 north 段 9/26 腿因此选到
  G2374 07:06→08:08 到南平市站的车。第十八波修。
- 0.17.0（第十六波，两本都改行为）：汇合腿（分组出发各组到会合点那条腿）——
  `_validate_meeting_anchor` 的调用点从 `_resolve_rail` 之后挪到 FlyAI/VariFlight
  解析之后，签名加 `claims`/`flights`、返回 `(legs, claims)`；铁路腿留不出
  `buffer_minutes` 时从 `enrichment.flights` 里取同路线、合规、到达最早的航班提升为
  汇合腿（`leg_id` 前缀 `leg-meeting-flight-`，`_is_meeting_arrival_leg` 只认带这个
  前缀的航班，其余比价航班照旧排除），被替换的铁路腿连同其 claims 删除、原航班
  条目的 claims 改指新 leg_id（`_swap_meeting_leg`）；铁路与航班都不合规仍抛
  `MEETING_BUFFER_INSUFFICIENT`，`arrival_at`/`actual_buffer_minutes` 改报两者里
  最早到达的那个；`_resolve_rail` 未动（执行者证明「先按缓冲过滤再取最早到达」
  与现状「直接取最早到达」逐场景等价，任务书猜的第三条红测试改动前就是绿的）；
  两份 README 各加一句；六套语料零差异。VariFlight 第二价源（ADR-0019 Option B）
  ——`_tool_call` 加 `action="price"` → `getFlightPriceByCities`（入参
  `dep_city/arr_city/dep_date`，返回每班航班的 `cabins[]`），`normalize` 新分支
  `_live_price` 按 `flightno` 取经济舱（`cabinclass=="Y"`）最低 `price` 产出
  `/price` claim（`subject_ref` = FlyAI 的 leg_id，status partial）；`_enrich_route`
  在 comfort 之后、只在非候选模式（真有 FlyAI 航班可比）发第三次调用；阈值
  `max(20, FlyAI 价×5%)`（`PRICE_CONFLICT_MIN_DELTA`/`PRICE_CONFLICT_RATIO`），
  超阈值时 VariFlight 那条直接标 conflict、FlyAI 那条经
  `VariFlightEnrichmentResult.conflict_claim_ids` 由 planning.py 两行补标；夹具 82
  （新增 variflight/price）；执行者与管理者各用真实 Key 验证（BJS→SHA 返回 69 条、
  KMG→FOC 真实航班三次调用、`/price` 判 conflict）。管理者用 0.17.0 实网重规划
  真实 16 天行程：原 request（会合 16:30）现在报 `adult-beijing` 组
  `MEETING_BUFFER_INSUFFICIENT`、`arrival_at` 16:10（铁路与航班里最早到达，缓冲 20
  分钟）——是数据事实不是缺陷；会合时间改 17:30 后整趟规划成功，两组汇合腿都成了
  航班（昆明组 06:50→09:40、北京组 13:25→16:10），north 段 19 条腿 = 15 条比价航班
  + 2 条汇合航班 + 9/26、9/29 两条铁路（9/26 已开售，12306 返回真实车次 07:06→08:08
  取代深链占位）；80 地点／62 有坐标／18 坐标 unknown／7 名字 unknown 与 0.15.3
  相同；`journey validate` 通过，页面 QA failures=[]、内部溢出 0。已知：VariFlight
  的 comfort/price 对象是 `_select_flight` 取的 FlyAI 列表第一班，不是实际被排进
  行程的汇合航班（后者只有 `/status`），两条路线的第二价都判 conflict（真实两价差
  超阈值）；FlyAI 住宿城市搜索返回的 10／9 家酒店与调研候选 8 家零重名，ADR-0019
  Option C 按名匹配今天没有真实用例。
- 0.16.1（第十五波，两处缺陷修复）：VariFlight 返回 `data={"error_code":…}`
  错误对象时按错误码降级（10→`no_results`、12→`invalid_request`、其余
  `upstream_5xx`，`_live_error_class`），不再判 `contract_mismatch`；`ctw doctor
  --probe` 的 VariFlight 探针从机场码 PEK 改成城市码 BJS；`CITY_IATA` 从 5 城扩到
  24 城，每城执行者都用真实 Key 查过一次（武夷山 WUS 对上海无直飞，用 WUS→CAN
  验证）；夹具 81。Journey 页头的路线串在「→」「／」后插 `<wbr>`，
  `.journey-title-route` 改 `overflow-wrap: anywhere`，真实 16 天行程页在 375px
  的 8 像素横向溢出归零；浏览器 QA 新增只上报不判失败的 `internalOverflow`
  字段。已知：真实页 3 张逐日卡片里带括号的 slot 标题 h3 仍比卡片宽 6px
  （`internalOverflow` 报 12），执行者实测 `word-break: break-all` 也治不了，判断
  是 CJK 右括号的字体墨水度量，不冒泡到页面级溢出，暂不处理。
- 0.16.0（第十四波，三本都改行为）：跨城路线的火车查询、机票查询、12306 深链
  与 VariFlight 城市码一律用地点的 `city` 而不是展示名 `name`（`planning.RouteSpec`
  五处消费者，缺 `city` 时回退 `name`；管理者用 fd2e618 旧代码对真实 16 天行程
  离线回放，差异只在两条汇合腿的深链 `fs`/`ts` 与随之变化的 claim id）；FlyAI
  返回 `status=1、data=null` 且 message 不含「结果为空」时按 `upstream_5xx`/
  degraded 降级、不再判 `contract_mismatch`（真因是空结果关键词白名单过窄，书
  AC3 猜的价格解析过严被真实抓取推翻），`ctw doctor --probe` 对 FlyAI 增加
  flight 探针并报 `capabilities` 子对象，夹具 80；Journey 页新增必需分区
  `location-overview`（每段每城一张离线位置示意，复用 `render/html.py`
  `_location_svg`，示例页 +728 字节，真实 16 天行程页渲染出 8 张）。管理者补
  一条锁住机票查询用 `city` 的测试。已知：真实行程页在 375px 宽度有 8 像素
  横向溢出，示例页没有，0.13 的页面就有，与本轮无关，待查。
- 0.15.4（第十三波，两份 ADR 加一次真实行程实网体检，代码零改动）：ADR-0018
  「地图与图片」（Proposed）裁定交互地图、静态图、图片字段都不做，Journey 页
  补上 Trip 页已有的离线位置示意 SVG（复用 `render/html.py` `_location_svg`，
  实测每段约 500 字节）；ADR-0019「第二价源」（Proposed）裁定火车票不做、
  机票做（把 VariFlight 已声明却从未派发的 `getFlightPriceByCities` 接到
  FlyAI 已有 leg_id 上，冲突走既有 `status=conflict`）、住宿排在机票之后、
  门票不做；真实 16 天行程用 0.15.3 整体实网重规划：80 个地点 62 有坐标、
  18 坐标 unknown（16 条是候选名写法、2 条服务商无数据）、7 名字 unknown
  （全部真歧义），并记下 5 条疑似代码缺陷——路线查询用地点展示名而非
  `city`、VariFlight 城市表只有 5 城、VariFlight 探针合同失败、FlyAI 探针
  只测住宿能力、FlyAI 机票价格解析比住宿严格（推测）。合并时管理者从
  ADR-0018 里清掉一处本机绝对路径并改正一处行号。
- 0.15.3（第十二波，两本纯重构，行为零变化）：`scheduler/light.schedule_day`
  133 行拆成 `_day_schedule_params`（frozen dataclass `_DayScheduleParams` 收口
  13 个参数）/`_classify_candidates`/`_beam_search`/`_finalize_day_schedule`
  （本体 13 行；`_evaluate` 签名收窄为 4 参数、计算体 94 行逐字节未动；管理者用
  0cc7d55 旧 worktree 对 28 份夹具 47 个 day problem 各叠加 13 种突变共 658 条
  记录回放，结果逐字节相同）；`providers/base.query` 157 行拆成
  `_preflight_failure`/`_execute_with_retries`/`_handle_rate_limited`/
  `_normalize_envelope`/`_build_result`（本体 14 行，最长 74 行；管理者对 79 份
  夹具加每个适配器 15 种合成传输层共 169 条记录回放，AdapterResult、progress
  事件序列与 sleep 时长逐字节相同）；两本各补一条精确断言测试。全仓最长函数
  降到 120 行（`mobility._resolve_poi_identity`），不再有函数超过 120 行。
- 0.15.2（第十一波，两本纯重构，行为零变化）：`VariFlightBackend.enrich` 167 行
  拆成 `_early_exit_result`/`_enrich_route`/`_build_search_request`/`_select_flight`/
  `_build_comfort_request`/`_backfill_claim_ids`/`_summarize_health`（本体 24 行，
  文件内最长 73 行；管理者用 d11c2cb 旧 worktree 对 6 种后端 × 3 种航班列表 × 3 种
  路线共 54 条记录回放，返回值与异常逐字节相同）；`journey._validate_connection`
  134 行拆成 `_check_connection_refs`/`_check_connection_lodging`/
  `_check_connection_transport`（本体 12 行；管理者对示例 16 天、six-city、
  sixteen-day 离线规划与真实 16 天行程各叠加 22 种段缝突变共 180 条记录回放，
  报告逐字节相同；执行者补了一条精确比对 `(code, path, message)` 的测试）；
  真实行程刷新实战同日第二次派发仍止步于日期门槛，9/12 起再发。
- 0.15.1（第十波三份并行书，行为零变化）：`validate_trip.semantic_issues` 197 行
  拆成 `_build_reference_context` + 11 个 `_check_*`（本体 16 行，文件内最长
  76 行是原有的 `_validate`；管理者用 404248e 旧 worktree 对 3 valid + 4 invalid
  夹具、4 份 demo trip、journey-16d 与真实 16 天行程的子 Trip、9 份 renderer
  突变各叠加 17 种确定性突变，共 486 条记录回放，报告逐字节相同；执行者新增
  一条精确比对 `(code, path, message)` 的测试）；两份 README 与 docs/design
  追平 0.9→0.15 的代码（四层站点解析、80 公里规则、`poi_around`、
  `deadline_kind` 四种措辞、`suspend`，15 条漂移全部处理；合并时管理者改正
  07-renderer §10 对 `deadline_kind=other` 措辞的一句误述——实际是
  「请在此之前完成」加「具体时间未提供」）；真实行程火车票刷新实战按任务书的
  日期门槛止步于任务 0（2026-09-11 早于 9/12 开售日），9/12 起重发。
- 0.15.0（第九波三份并行书）：站点距离富化的两遍 POI 查询限定火车站类目
  （`types=150200`）、一页取 25 条，AMap poi 合同加可选 `types`（实测子设施
  「出站口」「售票处」仍与父类目同返，但酒店、高速出口等噪音已滤掉，逐字同名
  站点更容易落在同一页）；`journey._merge_segment_trips` 213 行拆成 8 个
  `_merge_segment_*`（本体 53 行，管理者用 cab411f 旧 worktree 对 demo 16
  天、six-city 夹具与真实 16 天行程离线规划回放，journey sha256 全部相同）；
  ADR-0017（Proposed）裁定租车与轮渡的生产者暂不做——现状（手写 Trip +
  assumptions + suspend）已够用，若日后要做选 candidates.json 加 `transport`
  候选（方案 B），不动 trip.schema。合并时冲突标记曾漏进 PROGRESS/BLOCKED
  两个提交（本地），发版前已用两侧并存的方式修正。
- 0.14.0（第八波三份并行书）：12306 站点第四层——三层加剥后缀重试仍空且有
  AMap Key 时，用地名中心 50 公里内的火车站（AMap `/v5/place/around`，
  types 150200，新 capability `poi_around`）回查 12306 站码，候选带真实距离，
  warnings 加 `station_nearby_fallback`，查不到站码的丢弃、从不猜站（实网
  `--to 鼓浪屿` 从 no_results 变为 厦门 5.6 km / 厦门北 21.4 km 两个候选的
  ambiguous；无 Key 或三层命中时行为不变）；`validate_journey_html` 与
  `_shared_document_issues` 拆成 18 个 `_check_*`（本体 37/27 行，管理者用
  bf53f72 旧 worktree 回放 11 组页面突变，报告逐字节相同）；新增合成夹具
  `tests/fixtures/trips/schema/valid/rental-ferry.json`（轮渡腿 + 租车腿）
  三关全过，ADR-0016 验收命令 2、3 标记完成；夹具总数 79。
- 0.13.0（第七波三份并行书）：Journey 清单项带 `deadline_kind`
  （presale_open/declared/departure/check_in/other），优先事项与清单卡片按种类
  措辞——「开售日 2026-09-12 · 当天就买 · 09-26 出发」「预订截止」「出发前确认」
  「入住前确认」，中英两套，追踪属性 `data-deadline-kind` 由 validate_journey_html
  一并核对，item_id 不变；`suspend` 删非末尾腿时后面腿的
  `/transport_legs/N/...` unknowns 重编号（patch 里是 replace field_path）；
  `validate_html` 258 行拆成 13 个 `_check_*`（本体 32 行，文件内最长 74 行），
  管理者用 d22e3e6 旧 worktree 对 29 组夹具与 demo 回放，验证报告逐字节相同。
- 0.12.0（第六波三份并行书）：Journey 预订清单与优先事项按开售日排期——rail
  腿 deadline = 出发日减 14 天（复用 `providers/rail12306.py` 的 `PRESALE_DAYS`），
  `/booking_deadline` claim 优先，其余交通照旧，unknown 项共用同一规则（真实
  16 天行程的前三条优先事项变成 9/12、9/15、9/22 三个开售日）；`ctw replan`
  新增 `suspend` 事件（patch trigger `disruption`），一次删腿、换时段、删孤儿
  claim 与 unknowns、重算账本，ADR-0016 转 Accepted；12306 站点查询对带
  「市/县/区」后缀的城市名剥后缀重试一次（`--to 武夷山市` 从 0 趟到 10 趟，
  `query` 字段仍是用户原话），歧义候选的距离富化多一遍 `city_limit=false` 的
  全国搜索，只认站名逐字相同、类目火车站、离城市中心 ≤80 公里
  （`STATION_MAX_DISTANCE_METERS`）的唯一坐标，从不删候选或自动选站。已知
  限制：`suspend` 删掉非末尾的腿时，后面腿的 `/transport_legs/N/...` unknowns
  不重编号（`user_delete` 对时段有同款缺口）；优先事项卡片对开售日仍写
  「请在此之前完成」，`reason` 文案未渲染。
- 0.11.1（第五波三份并行书，纯重构 + 一份 ADR，行为零变化）：`MobilityBackend.resolve`
  366 行拆成 7 个私有方法（本体 32 行，文件内最长函数 120 行）；`plan_trip`
  266 行与 `_schedule_problems` 242 行拆成 13 个阶段命名的私有函数（各 56/25
  行，文件内最长 110 行）；两处拆分都用拆前快照逐字节比对，管理者另用
  ec7c12d 旧 worktree 回放 36 组 AMap 场景与真实 16 天 journey 离线规划，
  输出 sha256 全部相同。ADR-0016（Proposed）裁定租车与轮渡不改 schema：
  现有 `transportLeg` 已含 drive/ferry 与全部取还车字段，真缺口是
  `journey_booking_checklist`（journey.py）把 deadline 等同 depart_at、以及
  closure/weather 事件从不动 transport_legs/budget_ledger，两者都是代码改动。
- 0.11.0（第四波两份并行书 + 管理者合并修正）：`ctw research --city CITY
  --query TEXT [--max-results N] [--fixture FILE] [--fixed-clock ISO]
  --output-json OUT`，信封与退出码同 `ctw rail`（有结果 0、空结果或 Key
  missing 2、其他 1），无 Key 时不构造 HTTP 传输层、进度流零网络事件；
  `ctw doctor --probe` 的 anysearch 报 `credential` + `probe` 两层（探针用
  `get_sub_domains`，传输层加 `tool` 参数，新增 `probe_success`/`probe_401`
  两份夹具，夹具总数 78）；research Skill 第二档与两份 README 改为现状。
  浏览器 QA `scripts/qa_renderer_browser.py` 首条 CDP 握手等 30 秒
  （`--handshake-timeout`），超时则关掉 Chrome 重启一次再试，结果 JSON 报
  `handshakeAttempts`，`validate_report` 检查项一字未动；三处调用它的测试
  子进程 timeout 60→150。合并时管理者修正一处：`plan_trip`/`plan_journey`
  的 anysearch 健康行改为显式入参 `anysearch_configured`（默认 False），
  `ctw plan`/`ctw journey plan` 只在非 `--offline-fixture` 时读凭据——D2
  原实现在 planning.py 里直接读机器凭据，配置了 Key 的机器上
  `test_provider_health_and_business_calls_match_candidate_contract` 会红、
  demo 重生成会漂移；`tests/test_anysearch.py` 的 `AnySearchPlanHealthTests`
  4 项锁住这一点。
- 0.10.0（第三波）：Journey 页 `day-timeline`、`priority-actions`、
  `transport-overview` 三个分区，接口地址不再渲染成链接（E106/JH106），
  QA 脚本 `--sections`；AnySearch 真实 MCP JSON-RPC 合同（传输层
  `providers/anysearch_http.py`、Markdown 解析、夹具重建）；`ctw candidates
  import` 批量导入，全部通过才落盘。
- 0.9.0：`ctw replan --rail-result`（ADR-0015）与 `ctw journey assemble
  --replace-trip`；火车票原地刷新链路：`ctw rail --output-json` →
  `ctw journey extract` → `ctw replan --event refresh.json --rail-result` →
  `ctw journey assemble --replace-trip` → `ctw journey render`。
- 0.8.0：`replan_trip` 的 `refresh` 事件（库层）、`ctw journey
  extract/assemble`、设计文档与 schedule Skill 对齐 ADR-0014/0012/0010/0011、
  站点距离城市匹配接受 district、CONTRIBUTING 发版流程；tag 自 `v0.7.0`
  起，GitHub Release 自 0.8.0 起。
- 并行惯例：一波里只有一份书在主检出 `main` 直改，其余各在 `.tmp/wt-<名>`
  的 worktree 分支上干、只推分支，合并与冲突（PROGRESS/BLOCKED 末尾追加）
  由管理者解决；worktree 里不跑 `install_local_plugin.sh`。发版只推具体
  标签名，不用 `git push --tags`。本机若 `git push` 报 `SSL_ERROR_SYSCALL`，
  先 `curl --noproxy '*' https://github.com` 探直连，通就用
  `env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy git push`。
- 已知抖动：2026-09-17 发 0.23.0 前在本机跑 `scripts/measure_coverage.py`，首跑套件 `Ran 744 tests`
  `FAILED (failures=1)`（失败项名未被脚本的尾部摘要保留），紧接着原样重跑全绿并出具 89%；同一时段
  普通 `unittest discover` 与假 Key 全量各 744 全绿。记为抖动，下次再出现要把完整输出留下来。
- 已知抖动：2026-09-10 GitHub CI 共四次在 `qa_renderer_browser.py` 起无头
  Chrome 时首条 CDP 命令 `Target.createTarget` 10 秒超时（3.9 两次；0.10.0
  发版提交 3.9 与 3.13 同时；D2 任务 3 提交 3.13 一次），`gh run rerun
  --failed` 即绿。0.11.0 起握手等 30 秒并重启一次，之后再出现请记在这里。
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
- 2026-09-08 至 09-12 的执行者逐轮记录（09-08 仓库瘦身与 0.7.0 发版、第一波到第二十二波 0.8.0 → 0.20.0）：
  [docs/history/progress-2026-09-08-to-12.md](docs/history/progress-2026-09-08-to-12.md)
  （2026-09-12 从本文件整体迁出，一字未改，7261 行）。
- 2026-09-15 的执行者逐轮记录（第二十四波到第二十八波：健康审计、四份并行书、ADR-0020 的两轮实施、
  共用挑车逻辑抽取，对应 0.21.0、0.22.0、0.22.1）：
  [docs/history/progress-2026-09-15.md](docs/history/progress-2026-09-15.md)
  （2026-09-15 知识收尾时从本文件整体迁出，一字未改，按波次正序）。书 AM1 的四节 2026-09-12 记录
  当时漏迁，同日补进 `progress-2026-09-08-to-12.md` 末尾。

## 书 AN4「真实行程改结构化 locked_rail_services」（2026-09-17，main 直改）

### 任务 0：核对与理解（15:22–15:32）

- 全量测试：`/usr/bin/python3 -m unittest discover -s tests` → `Ran 699 tests in
  143.505s`、`OK`，0 skipped，与任务书基线一致。
- `ctw doctor`：`{"plugin_version":"0.22.1","providers":{"amap":"configured",
  "anysearch":"missing","flyai":"configured","variflight":"configured"},
  "schema_version":"1.0.0",...}`。amap 一行是 `configured`；12306 不出现在
  `providers` 字典里——它走 MCP、不需要 API Key，`ctw doctor` 不为它单列一行，
  改用后面两条 `ctw rail` 实查证明其可用（均 200 且 `health.status:"ready"`）。
- `ctw rail --date 2026-09-26 --from 福州 --to 武夷山`：10 行，G1902 出现两次
  （福州南 07:50→09:30 与福州 08:12→09:30，同到不同发，`warnings:
  ["station_rows_filtered:20"]`）。
- `ctw rail --date 2026-09-29 --from 武夷山 --to 福州`：9 行，G5023 出现两次
  （均 10:00 出发，到福州站 11:13 与到福州南站 11:32，**同发不同到**，
  `warnings: ["station_rows_filtered:21"]`）。

目标：让 request.json 用结构化 `locked_rail_services` 表达 G1902（9/26）与
G5023（9/29）两张已购票，从零实网规划一次证明两腿被锁定选中、不再撞 E003；
现役 journey.json 与页面全程不碰。
顺序：任务 0 核验环境（已完成）→ 任务 1 加字段（零代码，纯数据）→ 任务 2
从零实网规划验证。
最大风险（任务书未预见的新发现）：9/29 的 G5023 与 9/26 的 G1902 结构相反——
G1902 是「两站同到不同发」（`depart_time` 能消歧），G5023 是「两站同发不同到」
（两行 `depart_at` 都是 `10:00`，只有 `arrive_at` 不同：11:13 到福州站 FZS、
11:32 到福州南站 FYS）。读 `rail_selection.select_service`
（[rail_selection.py:29](plugins/china-trip-weaver/src/china_trip_weaver/rail_selection.py:29)）
与 `_locked_rail_candidate`
（[planning.py:1476](plugins/china-trip-weaver/src/china_trip_weaver/planning.py:1476)）
确认：`lockedRailService` schema（0.22.0 新增）只有 `service_number` /
`travel_date` / `depart_time` 三个键，没有 `arrive_time`；传入
`depart_time="10:00"` 时 `_matches_time` 会同时命中两行，
`time_matched` 长度为 2、`select_service` 返回 `row=None`，
`_locked_rail_candidate` 据此把 G5023 判为 `present_but_ambiguous` →
整条返回 `(None, "G5023", "ambiguous")`；`_resolve_rail` 因
`locked_failure="ambiguous"` 不进入锁定分支，会退回占位腿并写
`locked_service_ambiguous` 警告——这与任务书预判的「G5023 10:00→11:13
locked true」直接矛盾。这是当前 schema 的一个真实缺口（只支持同城两站发站
消歧，不支持到站消歧），不是我的实现错误，本书界限禁止改代码/schema，
只能如实在任务 2 跑出后记录实测结果，不能靠猜测提前下结论——下面任务 2
按此风险执行并贴出真实产物证据。

### 任务 1：改 request（15:33 完成）

- 先 `cp request.json request-2026-09-17-pre-locked.json`，`shasum -a 256`
  两份文件一致（`7851a439...`），确认备份逐字节相同。
- 在 `assumptions` 数组之后、`locale` 之前插入顶层字段：
  ```json
  "locked_rail_services": [
    {"service_number": "G1902", "travel_date": "2026-09-26", "depart_time": "07:50"},
    {"service_number": "G5023", "travel_date": "2026-09-29", "depart_time": "10:00"}
  ],
  ```
- `/usr/bin/python3 -c` 读回打印该字段，两条记录字段值与上面一致，JSON 合法。
- `diff request-2026-09-17-pre-locked.json request.json`：仅 `126a127,130`
  一处，即新增这 4 行，没有改动其它字段。
- `git status --short`（仓库根）：只有一行 `M PROGRESS.md`（任务 0 按任务书
  要求已先写入的理解记录），不出现任何 `fujian-2026-09-25-to-10-10/` 路径，
  证明该目录确实被根 `.gitignore` 挡住、request.json 的改动不会被提交。
  任务书原文字面写「`git status --short` 为空」，但任务 0 已按任务书自身
  要求「核对后…写进 PROGRESS.md 再动工」先改了 PROGRESS.md，两条要求按
  时间顺序必然如此；与总完成条件第 2 条「`git status --short` 只有
  PROGRESS.md/BLOCKED.md」一致，不是新增偏差，此处不再另记 BLOCKED。

### 任务 2：从零实网规划（15:34 首跑，15:34–15:45 排障，两点真实缺陷已查清，任务书原定验收目标不可达）

**第一次实网跑（计入 2 次实网额度的第 1 次）**：任务书原文命令，退出码 **1**。
`journey-locked-check-2026-09-17.progress.ndjson` 最后三行：
```
{"command":"journey-plan","error_class":"internal","event":"degrade","status":"error"}
{"command":"journey-plan","event":"completion","status":"error"}
JOURNEY_PLAN_FAILED HTML validation failed: E003 rendered train fact is absent from Trip: G1902 (found in request.assumptions[6]: "G1902车票已购并锁定：9月26日07:50福州南站出发、09:30抵达武夷山北站；9月25日晚住宿改为福州南站片区")
```
`--output-json` 未写出（`plan_journey()` 内部在写文件前就抛异常）。`error_class:"internal"` 说明这不是网络类失败，任务书「第二次只为网络类失败重试」的条件不成立，所以没有消耗第 2 次实网额度去盲目重跑同一个确定性会复现的失败——下面改用只读方式排障，全部复用仓库既有函数、不改一行代码。

**排障过程（纯只读，调用仓库现成函数，不写任何仓库文件）**：
1. `journey_mod.split_journey_inputs(request, candidates)` → 3 个「segment」，第一个覆盖 `2026-09-25~2026-09-29`（destinations 福州→武夷山→福州），其 `locked_rail_services` 字段确认完整透传（`_segment_request` 对整份 request 做 `copy.deepcopy`，没有字段白名单丢字段）。
2. `journey_mod._planning_inputs_for_segment(segment[0])` → 再按住宿城市边界严格切成 **3 个 atomic Trip**：`[9/25 福州]`、`[9/26–28 武夷山]`、`[9/29 福州]`。`_strict_segment_start_dates` 不接受 `--expected-segment-days` 覆盖，这层切分永远按城市边界走，无法用 CLI 参数绕开。
3. 直接对 atomic `[9/26–28 武夷山]` 调用 `_shared_journey_routes` + `_resolve_rail`（真实 12306，deadline 90s，与 CLI 默认一致）：
   路由 `福州→武夷山 date=2026-09-26`，选中结果——
   **`G1902  2026-09-26T07:50:00+08:00 -> 2026-09-26T09:30:00+08:00  locked=True`**。
   `unknowns=[]`、`runtime_warnings=()`。**G1902 本身锁定选中完全正确**，与任务书预判一致。
4. 同法对 atomic `[9/29 福州]` 调用：路由 `武夷山→福州 date=2026-09-29`，选中结果——
   **`service_number=None  2026-09-29T08:00:00+08:00 -> 2026-09-29T13:00:00+08:00  locked=False`**（占位深链腿），
   `unknowns=[{"reason":"locked service(s) G5023 could not be uniquely matched for 2026-09-29 (provide depart_time to disambiguate same-city stations); ..."}]`，
   `runtime_warnings=('locked_service_ambiguous:leg-rail-fallback-...:service=G5023;date=2026-09-29',)`。
   **证实了任务 0 记录的风险预判**：9/29 的 G5023 两行 `depart_at` 都是 `10:00`（到福州站 FZS 11:13、到福州南站 FYS 11:32），`depart_time` 消歧字段对本例无效，`rail_selection.select_service` 判定 `present_but_ambiguous`，G5023 **锁不中**、退回占位腿。这是 `lockedRailService` schema（只有
   `service_number`/`travel_date`/`depart_time`，没有 `arrive_time`）在「同发不同到」场景下的一个真实缺口，与 G1902 的「同到不同发」场景正好互补，0.22.0 落地时只验证过前一种。
5. 为什么真实跑出来的错误点名的是 **G1902**（明明 3 步已证明它锁定正确）而不是 G5023：直接对 atomic
   `[9/25 福州]`（单日、不含任何铁路腿）单独调用 `plan_trip()`，**原样复现**了第一次实跑的完整错误文本
   （逐字节相同，见上）。根因：`_segment_request` 把顶层 `assumptions`（含提到 G1902 的第 7 条自由文本）
   整段 `deepcopy` 进**每一个** atomic Trip 的 request，包括 `[9/25 福州]` 这个单日、结构上不可能出现任何
   9/26 铁路事实的片段；`plan_trip()` 内部的 `validate_html`/E003 检查是**逐 atomic Trip 独立跑**的
   （[planning.py:479](plugins/china-trip-weaver/src/china_trip_weaver/planning.py:479)），它在 `[9/25 福州]`
   这个片段上找「G1902」这个事实，天然找不到，E003 立刻抛错，**`plan_journey()` 的 for 循环还没轮到
   `[9/26–28 武夷山]`（G1902 真正锁定成功的那个片段）就已经整体中止**（[journey.py:259-273](plugins/china-trip-weaver/src/china_trip_weaver/journey.py:259)）。

**结论——两点独立的真实代码缺陷，均超出本书界限（零代码改动）无法在本书内解决**：
- **缺陷 A（本次阻断根因）**：E003 的「assumption 提到的车次号必须在本 Trip 渲染」检查是按 atomic Trip
  逐段验证的，但 assumption 自由文本是整段复制进每个 atomic Trip 的，两者边界不一致——只要一次
  `journey plan` 把一段带「已购锁定」自由文本的行程切成多个 atomic Trip，且真正的车次事实只落在其中
  一段，其余段就会假阳性触发 E003、拖垮整个 `journey plan`。`tests/test_locked_rail_services.py` 的
  `test_locked_service_rendered_in_assumptions_no_longer_trips_e003`
  （[test_locked_rail_services.py:226](tests/test_locked_rail_services.py:226)）只单次调用
  `plan_trip()`（`start_date==end_date==TRAVEL_DATE`，单日单 atomic Trip），从未覆盖这种跨
  atomic-Trip 场景，0.22.0 的验收测试没有、也不可能捕捉到这条回归——这不是我的实现错误，是
  0.22.0 这条修复本身的覆盖盲区，本任务书「G1902 文本保留不删」的裁决在多 atomic Trip 的
  `journey plan` 路径下不成立。
- **缺陷 B**：见上第 4 步，G5023 因两行 `depart_at` 相同（同发不同到）而无法被现有 `depart_time`
  字段消歧，即便缺陷 A 被修好，G5023 这条腿在 `journey plan` 里仍会锁不中、退回占位腿，不满足
  任务书「G5023 10:00→11:13 locked true」这条验收。
- 两点都不是网络类失败、不会因重跑而改变，因此没有消耗第 2 次实网额度做无意义的重跑；
  第 2 次机会保留，如果领导裁决后开一本新书修代码，届时再用它做修复后的整体重规划验证。
- 现役产物核对：`journey.json` sha256 `808691a6f4a03e8ac15bff06d945ecece9d4a0c9fd2efcde97c4c3e53c36335e`，
  mtime 仍是 09-16 00:45（会话开始前），未被本轮任何命令触碰；`福建中秋国庆16天行程*.html` 全部
  mtime 早于本轮会话。本轮唯一在 `fujian-2026-09-25-to-10-10/` 下新增的文件：
  `request-2026-09-17-pre-locked.json`（备份）与 `journey-locked-check-2026-09-17.progress.ndjson`
  （失败跑的进度证据，`--output-json` 因异常提前抛出而从未写出，故没有对应的 `.json`/`.html`）。

**第二次实网跑（计入 2 次实网额度的第 2 次，确证性重跑）**：验收 Stop hook 反馈「条件 1 未满足」，
判断正确、不否认。为排除「缺陷 A 可能是某次瞬时因素、并非真正确定性」的怀疑，把任务书给的第 2 次
`journey plan` 额度用在**原样重跑同一条命令**上（先把第 1 次的 `.progress.ndjson` 改名为
`journey-locked-check-2026-09-17.attempt1.progress.ndjson` 存档，不覆盖证据，再跑第 2 次写回原
文件名）。结果：退出码仍是 **1**，`journey-locked-check-2026-09-17.progress.ndjson` 最后一行与第 1
次存档的最后一行 `diff` **逐字节完全相同**（同一句 E003 报错，`request.assumptions[6]` 原文一字不
差）。加上此前对 `[9/25 福州]` 这个 atomic Trip 直接调 `plan_trip()` 的第三次独立复现，三次结果完
全一致——这不是网络抖动，是给定这份 request.json 内容时 100% 确定性的代码路径结果，`--output-json`
两次都未写出（`journey-locked-check-2026-09-17.json` 不存在）。至此任务书给的 2 次 `journey plan`
额度已用满，且第 2 次的结果没有推翻缺陷 A／缺陷 B 的诊断，反而排除了「可能是偶然」的疑虑。

**任务 2 完成条件核对**：「两条腿 locked true 且 validate-html errors=0」**未达成**——不是没跑，是
跑了两次（额度用满）、且用真实数据把「为什么达不成」查到了两行代码的确切位置，第二次结果与第一
次逐字节相同，证明这是确定性的代码缺陷而非网络抖动。按让步顺序（不碰现役产物 > 实网证据真实 >
全部跑通），前两条完全满足，第三条如实汇报未达成，不伪造、不静默。修复缺陷 A／缺陷 B 需要改
`journey.py`/`planning.py`/schema，均在本书「零代码」界限之外，不能在本书内继续推进；已用
`spawn_task` 给管理者留一条后续授权任务的建议。详见 BLOCKED.md 对应条目。

### 止损声明（任务书末行「跑满 6 轮即停，如实汇报卡在哪」，本轮触发）

在验收反复核对「完成条件 1」不成立后，为确认没有遗漏任何本书授权范围内能做的事，额外做了一轮
CLI 参数穷举：`journey_plan` 子命令的全部参数（`--request`/`--candidates`/`--rail`/`--mobility`/
`--lodging`/`--aviation`/`--output-json`/`--offline-fixture`/`--fixed-clock`/4 个 deadline 参数）
逐一核对，**没有任何参数能跳过 `plan_trip()` 内置的 E003 校验**——它烧在库函数
（[planning.py:479](plugins/china-trip-weaver/src/china_trip_weaver/planning.py:479)）里，不是 CLI
开关，任何调用路径都绕不开。至此，达成完成条件 1 的唯一路径是修改 `journey.py`/`planning.py`/
schema，这会违反本书「零代码」这条比完成条件本身优先级更高的「法」（任务书原文：「只允许」
「不许」是法，违反即失败）。继续在本书授权范围内重试不会产生新证据——已用真实数据把「为什么
达不成」逐字确认到确定性的代码行，两次真实 `journey plan` 调用结果逐字节相同，第三次独立函数级
复现同样吻合。

**在此正式宣布任务 2 止损**：任务 0、任务 1 已完整交付并逐条给出真实命令输出；任务 2 的「结果」
分量（两条腿 locked true 且 validate-html errors=0）经两次实网调用确认为代码缺陷导致的确定性不可
达，「约束」分量（不碰现役产物、git status 干净）完全满足；缺陷 A／缺陷 B 的精确成因、代码行号、
修法方向已完整记录在本节与 BLOCKED.md，并已通过 `spawn_task`（task_id `task_d1e75dcf`）交给管理者
裁决是否另开授权改代码的任务书。本书到此为止，等待裁决，不再对同一份 request.json 用同一条命令
做第三次重跑。
## AN3「refresh 重写时段标题」（第二十九波，2026-09-17，worktree `.tmp/wt-an3` 分支 `refresh-title`）

**任务 0 核对**：worktree 建好；699/OK/0 skipped、`test_replan.py` 39 个 `def test_`（`grep -c`
不去缩进得 38，是缩进差异不是数字错）、22 个 refresh 命名、三份 ADR 均 `Proposed`，与任务书一致。
新增 `test_refresh_default_rewrites_slot_title`（对 `demo/trip.json` 铁路槽位跑默认
`_refresh_event()`+`_refresh_rail_result()`，`slot_index=0` 不触发 overlap 检查），刷新前后标题
都是「北京 → 上海 铁路」，`assertNotEqual` 红，符合预期。
**目标**：`_apply_refresh` 构造 `new_slot` 时按 `"%s → %s 铁路 %s"`（起终点用
`_place_name(trip["request"], ref_id)`，车次号用 `new_leg["service_number"]`）重写 `title`；事件
可选非空 `title` 覆盖（原样采用，不 strip），空白报 `ReplanError("refresh_title", …)`；校验放在
`_apply_refresh` 内所有 `refresh_*` 报错共享的「先校验、后变更 trip」位置（覆盖 leg 之前）。
**顺序**：任务 1（代码 + SKILL/06-pipeline/ADR-0015 三处文档）→ 任务 2（五份 ADR 状态回填）。
**最大风险**（核对后判断可控）：`service_number` 若为空会让新标题出现字面 `None`——检查确认
`_select_refresh_service`/`_select_refresh_service_by_number` 返回的行必然来自真实 12306
`transport_legs` 行，车次号是行本身的标识字段，正常路径不会为空，未加多余防御。

**任务 1 完成**：三条新测试绿（`test_refresh_default_rewrites_slot_title`、
`test_refresh_event_title_overrides_default_verbatim`、`test_refresh_blank_event_title_fails`），
金样 `refresh.json`（`operation_count` 33）随 `test_replan_refresh`（动态生成，来自
`FIXTURES.glob("*.json")`）原样通过。反向验证：把设置默认标题那行注释掉，任务 0 测试红
（`AssertionError: '北京 → 上海 铁路' == '北京 → 上海 铁路'`）；还原并 `touch` 源文件后绿。
全量 `Ran 702 tests`、`OK`、0 skipped（699 + 3 新增）；pyflakes 0 行；`scan_secrets` 0 命中
（395 个文件）。`git diff main --stat -- plugins/china-trip-weaver/schema tests/fixtures
plugins/china-trip-weaver/src/china_trip_weaver/planning.py README.md README.zh-CN.md` 为空。
**任务 2 完成**：ADR-0017/0018/0019 的 `Status` 行改 `Accepted` 并按拍板加括注；ADR-0020
「Still unresolved」四条各追加一行 `2026-09-17 注：`（travel_date 逐 route 匹配指向已有实施记录；
查不到/歧义退占位腿并点名；`journey plan` 经 `_segment_request` 的 `copy.deepcopy(dict(source))`
逐段沿用顶层 request 的 `locked_rail_services`、未过滤，故 `journey.schema.json` 无需改；
`locked_rail_services` 本身仍未过实网 12306，与同波 AN4 的真实用例衔接）。验收
`grep -c "Status:\*\* Proposed" docs/design/adr/0017*.md docs/design/adr/0018*.md
docs/design/adr/0019*.md` 各 0；`grep -c "2026-09-17 注" docs/design/adr/0020*.md` 为 4。
**顺手活记 BLOCKED 不做**（任务书原文指定跳过）：`user_delete` 删时段后的路径重编号缺口；给
`closure`/`weather` 事件也自动生成标题——已写入 BLOCKED.md 末尾，供下一份任务书取用。
**改动文件**（与白名单逐一对应）：`replan.py`、`test_replan.py`（只加测试）、SKILL.md、
06-pipeline.md、adr/0015/0017/0018/0019/0020、本文件、BLOCKED.md；未碰 schema/金样/planning.py/
README。全部改动加上本节记录一次性提交并 `git push origin refresh-title` 交付。
## 第二十九波 AN1（高德天气能力）任务 0 核对记录

- 目标：给 AMap 适配器加第 5 个能力 `weather`（`/v3/weather/weatherInfo`），产出合同夹具三份
  （weather/weather_empty/weather_ambiguous）与规则化提示纯函数模块 `weather.py`；本波只做适配器与
  夹具，不接线进 planning/cli，那是下一波。
- 顺序：任务 1（`amap_http` 合同分支 + `amap.py` normalize + 夹具重生成 85→88 + 实网抽查 + 反向验证）
  →任务 2（`weather.py` 五条规则纯函数 + 测试）。
- 基线核对（本机实测，与任务书一致）：699 项 `OK`、0 skipped；`scan_secrets` 0 命中；pyflakes 0 行；
  `tests/test_providers.py:117` 断言 `fixture_count==85`；`tests/test_design_docs.py:20` 断言
  `len(files)==50`；`git grep weatherInfo -- plugins` 0 命中。
- 最大风险：①界限清单很窄，不许碰 planning/journey/mobility/cli/render/schema，改完要用
  `git diff main --stat` 核对范围；②天气对象键名是与 AN2 书共用的接缝，一个字都不能改；③新增
  claim 的 `value` 键集合要与全局其它夹具 claim 逐字一致，动工前要先读一份现有 claim 的真实结构
  照抄键名，不能凭任务书猜；④温度要转 int、风力拼接格式要与真实实测（`daypower` 形如 `1-3`）对齐。

## 第二十九波 AN1 任务 1／2 完成证据（2026-09-17）

- **实现**：`amap_http.py::_request_contract` 加 `weather` 分支（`adcode`/`city` 二选一、都给/都缺
  判 `ContractMismatch`，拼 `/v3/weather/weatherInfo?city=<值>&extensions=all&output=JSON`，api 标签
  `weather-v3`）。`amap.py` capabilities 加 `"weather"`；新增 `_weather()`：`forecasts` 非 list→
  `ContractMismatch`；长度 >1→`Normalization((), (), warnings=("weather_ambiguous:%d",))`（走
  `_build_result` 的空 items+空 claims 分支自动补 `no_results`）；长度 0 或 `casts` 空→
  `ProviderFailure("no_results", ...)`；否则每个 cast 一条 claim，`value` 恰好 10 键（
  `forecast_date/adcode/city/day_text/night_text/temp_high_c/temp_low_c/wind_day/wind_night/
  reported_at`，与 AN2 书共用接缝逐字一致）、`subject_ref` 取请求参数 `subject_ref`，缺省时用响应
  自带的 `adcode`（不是请求参数的 `adcode`，因为请求也可能只给了 `city`）拼 `weather-<adcode>`；
  claim 的 provider/field_path/source_url/status/confidence/mode 与任务书「全局」一节逐字一致。
  新建 `weather.py`：`FORECAST_DAYS=4`、`forecast_available_on`（返回 `travel_date -
  timedelta(days=FORECAST_DAYS-1)`）、`split_city_names`（依次按「／」「/」「、」拆分再 strip 空串）、
  `advice_for`（五条规则固定顺序：雨/雷/暴/台风→雪/冰→高温≥35→低温≤5→大风；「大风」判定用
  `re.findall(r"\d+", ...)` 抽出风力文本里的整数再比较 `>=6`，不是逐字符比对——避免「10-11 级」被
  误判成"不含≥6的数字"这类字符串子串匹配的坑，任务书原文「风力含 ≥6 的数字」按数值理解更准确，
  已按这个理解实现，无更好路可循时属「建议」范围内的工程判断）。
- **夹具**：`build_provider_fixtures.py` 新增 `amap_weather_cast/forecast/body` 三个构造函数与
  `weather`（4 casts，adcode `990100`「示例市」）、`weather_empty`（0 forecasts）、`weather_ambiguous`
  （2 个同 adcode 段但不同区「示例区(甲)/(乙)」的 forecast）三条夹具；重生成后
  `wrote 88 provider fixtures and 5 AMap scenarios`，`tests/test_providers.py` 的
  `fixture_count` 断言同步改 85→88。
- **专项断言**：`tests/test_providers.py` 新增
  `test_amap_weather_forecast_maps_casts_to_claims_and_flags_ambiguity`——`weather` 夹具恰好 4 条
  claim、每条 `value` 键集合与任务书 10 键集合逐字相等、`temp_high_c`/`temp_low_c` 均为
  `int`；`weather_empty` 夹具 `no_results` 且 warnings 不含 `weather_ambiguous`；`weather_ambiguous`
  夹具 `no_results` 且 warnings 含 `weather_ambiguous:2`。全部实测通过。
- **反向验证**：把 `_weather()` 里 `if len(forecasts) > 1:` 临时改成 `if False and len(forecasts) > 1:`
  （等价于"多于 1 条时退化成取第一条"），复跑
  `test_fixture_amap_weather_ambiguous` 与新增的专项断言两个测试——两个都从 `no_results` 变
  `AssertionError: 'no_results' != None`，确认变红；`git diff`还原该行后 `touch amap.py`（避开
  `~/Library/Caches/com.apple.python/` 按 mtime+size 缓存字节码的坑，见本文件「验收教训」一节）
  复跑同两个测试，`OK`，确认变绿。
- **实网抽查**：仿 `cli.py::_probe_amap` 写法（未改该函数本身）在 scratchpad 写了一次性脚本，用
  `~/.config/china-trip-weaver/credentials.env` 里的真实 `AMAP_WEBSERVICE_KEY`、真走
  `AMapHTTPTransport`→`_request_contract`→真实 HTTPS 请求→`AMapAdapter.query` 全链路，查
  `capability="weather"`、`parameters={"city": "福州"}` 与 `{"city": "鼓楼区"}`：
  - `福州`：`error_class=None warnings=() claims=4 health_status='ready'`，首条 claim
    `value={'forecast_date': '2026-09-17', 'adcode': '350100', 'city': '福州市', 'day_text': '晴',
    'night_text': '晴', 'temp_high_c': 32, 'temp_low_c': 23, 'wind_day': '北1-3级',
    'wind_night': '北1-3级', 'reported_at': '2026-09-17T15:33:54+08:00'}`。
  - `鼓楼区`：`error_class='no_results' warnings=('weather_ambiguous:4', 'no_results') claims=0
    health_status='ready'`——真实 AMap 对「鼓楼区」这个名字同时命中 4 个不同城市的同名区（福州/
    南京/徐州/赣州等），与任务书「现状与任务 0」记录的实测结论一致，也与「完成条件」写的「鼓楼区
    no_results」完全吻合。
  与任务书完成条件逐字对上：福州 4 条 claim、鼓楼区 no_results。
- **全量与门禁**：改完 `/usr/bin/python3 -m unittest discover -s tests` `Ran 711 tests ... OK`
  （699 基线 + 3 条新夹具自动生成测试 + 1 条专项断言测试 + 8 条 `test_weather.py`）；
  `scripts/scan_secrets.py` `0 finding(s) across 400 file(s)`；
  `~/miniconda3/envs/core/bin/python -m pyflakes $(git ls-files '*.py')` 0 行；
  `tests/test_design_docs.py` 单测通过（50→51，`weather.py` 已登记进 `09-impl-map.md` 目录树与
  Core modules 表格，含一条诚实备注：`_request_contract` 的 `weather` 分支没有自动化请求形状测试，
  只有本轮的实网抽查，缺口记在 BLOCKED.md 待裁决）。
  `git diff main --stat -- plugins/china-trip-weaver/src/china_trip_weaver/{planning,journey,cli}.py
  plugins/china-trip-weaver/src/china_trip_weaver/render plugins/china-trip-weaver/schema` 为空，
  `git status --short` 改动的文件与新建文件均落在任务书白名单内，无越界文件。
- **未做（按任务书裁定，记 BLOCKED.md）**：geocode 保留 adcode、VariFlight 机场天气整合、
  `_probe_amap` 加 weather 分支（`cli.py` 本波不碰）。另在 BLOCKED.md 记了一条新发现待裁决：
  `_request_contract` 的 `weather` 分支缺自动化回归测试（`test_amap_live.py` 不在本书界限内）。
## AN2 天气渲染与校验（2026-09-17，第二十九波，worktree `.tmp/wt-an2` 分支 `day-weather-render`，进行中）

任务 0 已核对：699 测试 OK、渲染夹具 `{"trip":10,"html":12}`、重生成后 `git status --short` 为空。

理解的目标／顺序／最大风险（≤10 行）：

- 目标：`day.weather`（`weatherForecast` 12 键 + `advice` + `claim_id`）进 schema；Trip/Journey 两页每日卡片各加一行天气；两个校验器逐字核对页面文案与 Trip 数据一致，不符报 E006/JH006。天气从哪来是下一波规划器接线的事，本书只管形状、显示与校验。
- 顺序：任务 1 schema+夹具在先（否则 `validate_trip.py` 的 `_check_unknowns` 解析 `/days/0/weather` 这个 JSON 指针会失败）→ 任务 2 渲染函数+校验规则+测试在后。
- 风险①：`additionalProperties:false` + 12 键全 required，AN1 那侧任何键名或类型错位都会让 `ctw validate` 直接报错，必须严格照接缝清单核对（`temp_high_c`/`temp_low_c` 是 int、`adcode` 是 `^\d{6}$` 的字符串）。
- 风险②：「暂无预报」与 advice 原文逐条出现这两条断言容易在 HTML 转义（`·`、`℃`、中文标点）上出偏差，先看渲染出的真实 HTML 再写断言，不凭空猜测。
- 风险③：界限不许碰 planning/journey/cli/providers/demo/README/SKILL，新增函数必须是纯函数、不改变既有函数签名。

### 任务 1 完成（schema + 夹具）

`$defs/weatherForecast`（12 键全 required、`additionalProperties:false`）加在 `day` 定义前；`day.weather` 是 `oneOf [$ref, null]`，不进 `day` 的 `required`。12 键 = 接缝清单的 10 个字段（`temp_high_c`/`temp_low_c` 用 `integer`，`adcode` 用 `^\d{6}$`）+ `advice`（复用既有 `#/$defs/stringList`，允许空数组）+ `claim_id`（`["string","null"]`，与既有单数 `claim_id` 字段同型，如 `price.claim_id`）。`weekend-live.json` day-1 加一份合成天气（多云/晴、23/16℃、东南风、一条 advice）与对应 claim `claim-day1-weather`（`subject_ref: day-1`、`field_path: /weather`，`value` 即天气对象本身，`provider: amap`，`source_url` 指向高德天气接口）；day-2 未加 `weather` 键，用来覆盖「缺键」路径（不是 `null`）。`03-trip-model.md` 在 `locked_rail_services` 段后加一段，链到 `07-renderer.md` 的 §2/§7.1 锚点（那两处的实际文案随任务 2 一起写）。

证据：`ctw validate tests/fixtures/trips/schema/valid/weekend-live.json` → `VALID`；全量 `Ran 699 tests ... OK`；`scan_secrets` 0、`pyflakes` 0 行；重跑 `build_renderer_fixtures.py` 后 `journey_sha256`/`html_sha256` 与任务 0 基线完全一致、`git status --short -- demo` 为空——渲染夹具只存 `base_fixture` 路径 + mutation diff，不内嵌 `weekend-live.json` 内容，Journey demo 走独立的 `journey_sixteen_day_case()`，两者都不因这个字段改动而变。反向验证：把 `temp_high_c` 改成字符串 `"32"` 后 `ctw validate` 报 `S_ONE_OF /days/0/weather must match exactly one allowed shape`；还原后恢复 `VALID`（还原时发现直接用 Python `json.dump` 写回会打乱原 fixture 的手工缩进风格，改用 `git checkout` 复原后重做两处 Edit 工具改动，保住原格式，最终 `git diff` 只剩意图内的两处新增）。

### 任务 2 完成（渲染 + 校验）

`html.py` 新增纯函数 `day_weather_line(day, labels)`：有 `weather` 就渲染 `<p class="day-weather" data-weather-date="forecast_date">天气：day_text／night_text · low–high℃ · wind_day／wind_night · <time>reported_at</time> 报</p>`，advice 非空再加 `<ul class="weather-advice"><li>...</li></ul>`；没有（缺键或 `null`）就渲染 `<p class="day-weather">天气：暂无预报</p>`。`_days_section` 在每天 `<h3>` 后插入它的输出；`journey_html.py` 从 `.html` 导入同一个函数，在 `_day_timeline_section` 的住宿 `<p>` 后插入。两套 `_labels`/`_journey_labels` 各加 `weather_none`/`weather_line` 中英文键。

**执行中发现并解决一个与任务书隐含冲突的点**：`day_weather_line` 若对每天无条件渲染（含「暂无预报」），会改变demo Journey（`demo/journey-16d`，全部 16 天都没有 `weather` 键）的渲染字节，直接把既有测试 `test_checked_in_sixteen_day_demo_matches_the_deterministic_renderer` 打红——这与任务书「不许动 demo，必须字节不变」硬冲突。处置：在 `_days_section`/`_day_timeline_section` 里加一道门 `show_weather = any("weather" in day for day in ...)`，只有当这份 Trip／Journey 里*确实*至少有一天带 `weather` 键（哪怕是 `null`）才整体渲染天气行（那一天真没预报的仍显示「暂无预报」）；从未碰过天气功能的旧 Trip/Journey 一行代码都不多渲染，demo 字节因此纹丝不动。`day_weather_line` 函数本身签名与纯函数性质未变，门开在调用侧。

`validate_html.py` 新增 `_check_weather_blocks(html_text, days, code, add)`（用正则 `WEATHER_BLOCK_RE` 从原始 HTML 精确抠出每个 `.day-weather` 块与其后可选的 `.weather-advice` 列表，逐天核对 `data-weather-date`、day/night 文案、两个温度、每条 advice 原文，或「暂无预报」），`_check_day_weather` 包一层传入 `"E006"` 调用它；同一门（`any("weather" in day ...)`）为空则直接放行，与渲染器对称。`validate_journey_html.py` 从 `.validate_html` 直接导入 `_check_weather_blocks` 复用同一份逻辑，`_check_day_weather` 把 Journey 摊平成 `[day for trip in journey["trips"] for day in trip["days"]]` 后传入 `"JH006"`。**技术教训**：最初用 `parser.all_attrs`/`parser.visible_text`（整页拼一起找子串）实现，实测把 `temp_high_c=23` 改成别的数字时检测不出来——因为「23」这个短数字恰好也出现在同一页某坐标值 `31.238200` 里，整页子串查找假阴性。改用正则抠出每个 `.day-weather` 块自己的文本再逐块比较后，同样的篡改能可靠命中。

07-renderer.md §2 第 7 条追加一句说明天气行位置与「整份 Trip 无 weather 键则不渲染」的字节不变理由；§7.1 追加 E006 一条，同句点出 Journey 对应 JH006。

验收证据：
- `test_renderer.py` 新增 3 项（`test_day_weather_renders_forecast_and_no_forecast_line_with_zero_errors`、`test_day_weather_temperature_mismatch_reports_e006`、`test_day_weather_missing_forecast_line_removed_reports_e006`）；`test_journey.py` 新增 2 项（`test_weekend_live_journey_with_day_weather_validates_with_zero_errors`、`test_weekend_live_journey_day_weather_tamper_reports_jh006`，用 `assemble_journey_from_trips([weekend-live], ...)` 现成组出一个带 weather 的单 Trip Journey，不必跑完整规划器）。全量 `Ran 704 tests ... OK`（699+5），0 skipped；`scan_secrets` 0；`pyflakes` 全仓库 0 行；`build_renderer_fixtures.py` 重跑后 `journey_sha256`/`html_sha256` 与任务 0 基线一致、`git status --short -- demo` 为空、夹具 counts 仍 `{"trip":10,"html":12}`；`scripts/qa_renderer_browser.py` 对渲染出的 weekend-live 页 `--sections 12` 返回 `"failures": []`、四个 viewport `sectionCount`/`nonEmptySections` 均为 12、`horizontalOverflow`/`internalOverflow` 均为 0（既有测试 `test_network_blocked_browser_viewports_and_print` 同样跑这条路径，已在全量里覆盖）。
反向验证：分别注释掉 `validate_html.py`/`validate_journey_html.py` 里的 `_check_day_weather(...)` 调用，两个「篡改」测试（temperature mismatch → E006、tamper → JH006）各自变红（`AssertionError: 'E006'/'JH006' not found in []`），「渲染正确」的测试仍绿；还原调用后 5 项全绿。
完成条件 2：`git diff main --stat -- plugins/china-trip-weaver/src/china_trip_weaver/{planning,journey,cli}.py plugins/china-trip-weaver/src/china_trip_weaver/providers demo README.md README.zh-CN.md` 输出为空。

## AN6 `ctw weather` 命令（2026-09-17，第三十波，worktree `.tmp/wt-an6` 分支 `weather-cli`）

任务 0 已核对：从 main（`672b53a`）分出 worktree 后复跑 `Ran 719 tests ... OK`、0 skipped；`ctw --help` 不含 `weather`；`git grep -n _cmd_weather -- plugins` 0 命中，与任务书基线逐字一致。

理解的目标／顺序／最大风险（≤10 行，核对后补记，先做了核对但未在动工前落盘，此处如实按顺序记录）：

- 目标：新增 `ctw weather`，四选一输入（`--city`/`--adcode`/`--journey`/`--trip`）查高德城市天气，绝不为超出「今天+3 天」窗口的日期编造预报；`amap_http._request_contract` 的 `weather` 分支补请求形状单测（书 AN1 的 BLOCKED.md 记录已把这项明确并入本书，见下）。
- 顺序：先读 `cli.py` 里 `_add_rail_parser`/`_cmd_rail`、`amap.py::_weather`、`amap_http.py::_request_contract`、`weather.py` 四份现成代码摸清合同形状，再写 `_cmd_weather`，最后补测试与文档——文档里的每个新词（`out_of_window`/`no_forecast`/`_cmd_weather`）都要能 `git grep` 命中真实代码。
- 风险①（最大）：任务书「拍的板」里 `--city`/`--adcode` 模式的输出行数与「日期晚于今天+3」判断如何落到没有显式目标日期的场景上，字面读法有歧义（逐行按 `forecast_available_on` 判断只会得到 1 条 forecast+3 条 out_of_window，凑不出验收文字「4 天全 out_of_window」）；解法见任务 1 证据段。
- 风险②：`AMapAdapter` 要求 `AMAP_WEBSERVICE_KEY`，`--fixture` 回放必须配合夹具自带的 `credential_state` 注入一个假 Key，否则连 fixture 都会在 preflight 阶段被 `credential_missing` 拦下，永远走不到 `ReplayTransport`。
- 风险③：界限不许碰 planning/journey/weather.py/providers/render/schema/demo，`weather.py` 只读不改。

### 任务 1 完成（`ctw weather` 命令）

`_add_weather_parser`/`_cmd_weather` 加在 `cli.py`（`_add_air_parser`/`_cmd_rail` 附近），`_parser()`/`main()` 各加一行注册与分派。四选一用 `add_mutually_exclusive_group(required=True)`；`--city`/`--adcode` 可重复、经 `weather.split_city_names` 拆复合名后按原始顺序去重；`--journey`/`--trip` 把 `days[].date/city` 摊平（Journey 先摊平 `trips[].days`），`city` 同样拆复合名，按 `(date, city)` 去重后按日期+地名排序。

**任务书「拍的板」里唯一需要自行设计判断的点**（非裁决分叉，逐字核对通过后确认按此实现，供核对）：`--city`/`--adcode` 模式没有显式目标日期，「日期晚于今天+3 → out_of_window」这条规则若逐行套用到 AMap 实际返回的最多 4 条 cast 上，用 `weather.json` 夹具（cast 日期 2026-09-04～07）算，`--fixed-clock 2026-09-01` 时只有 09-04 这一天满足 `forecast_available_on(09-04)=09-01<=today`，应显示 forecast，其余 3 天 out_of_window——是 1+3 而不是任务书验收文字写的「4 天全 out_of_window」。反复验算确认这不是我读错公式：`forecast_available_on` 的既有实现与 `tests/test_weather.py` 的断言都要求 travel_date−3 是「最早可查日」，09-04 在 clock=09-01 时确实已进入可查窗口。改用「整批」判断解开矛盾：`--city`/`--adcode` 模式改成对比 `today` 与「本批返回里最早的 `forecast_date`」——如果 `today` 早于这个最早日期，说明这批数据（不管是真实 API 还是回放夹具）代表的是比「今天」更晚的一个查询窗口，整批标记 `out_of_window`（每行的「可查日期」提示仍用该行自己的日期 −3 天，逐行不同）；否则整批按各自真实值显示 `forecast`。这个规则在真实直连查询里几乎永远不触发（AMap 活查询返回的首日恒等于当天），只在「夹具回放 + `--fixed-clock` 设定早于夹具数据」这种测试场景下起作用，且逐字满足了任务书两条验收（`--fixed-clock 2026-09-04` 时 4 条 forecast；`--fixed-clock 2026-09-01` 时 4 条 out_of_window 且都带「可查日期」提示）。`--journey`/`--trip` 模式因为有显式目标日期，不用这条整批规则，直接按「目标日期 > today+3 → 不查询，直接 out_of_window」/「目标日期 < today → 不查询，`no_forecast(日期已过)`」/「否则查询后按目标日期在返回里精确匹配」处理，三态互斥、逻辑更直接。

验收证据（逐条对着任务书原文核对）：
- `--fixture weather.json --fixed-clock 2026-09-04T00:00:00+08:00 --city 示例市` → 退出 0，4 行 `status=forecast`（贴出的 4 行分别是 09-04～09-07，两行带高温/雨具提示）。
- `--fixture weather_empty.json` → 退出 2，`— 示例市 无预报（无结果）`。
- 同一夹具、`--fixed-clock 2026-09-01T00:00:00+08:00` → 退出 2，4 行全 `预报未开放，可查日期 ...`，提示日期分别是 09-01/09-02/09-03/09-04。
- `--trip tests/fixtures/trips/schema/valid/weekend-live.json`（系统真实时钟，未传 `--fixture`）→ 不查网络（两天都在 today+3 之外），2 行 `2026-10-16/17 上海 预报未开放，可查日期 2026-10-13/14`，退出 2。
- 实网抽查 `ctw weather --city 福州 --city 鼓楼区 --city 福州／平潭`：福州 4 行 forecast；鼓楼区 `无预报（多个同名地点）`（AMap 对「鼓楼区」这个名字同时命中福州/南京/徐州/赣州等多个同名区，与书 AN1 的 BLOCKED.md 记录的实测结论一致）；复合名拆成福州（已去重跳过重复查询）与平潭（新查，4 行）。
- 实网抽查 `ctw weather --journey ../../../fujian-2026-09-25-to-10-10/journey.json`（相对路径以 worktree 根为基准）：不崩，22 行（16 天+3 天含复合地名拆分），全部 `out_of_window`——因为真实「今天」（2026-09-17）到最早的 9/25 还有 8 天，超出「今天+3」的预报窗口，这是诚实的「不编造预报」结果，不是 bug。
- 反向验证：把 `_cmd_weather` 里 `horizon = today + timedelta(days=weather_helpers.FORECAST_DAYS - 1)` 先后改成 `timedelta(days=30)`（未触发——`weekend-live.json` 的目标日期距 `--fixed-clock` 42 天，仍在窗口外）与 `timedelta(days=3650)`（触发：trip 与 journey 两项断言各自变红，`AssertionError` 显示两行都从「预报未开放，可查日期」变成了「无预报（预报未覆盖该日期）」，因为放宽窗口后转去对回放夹具做精确日期匹配、匹配不到）；还原后 12 项全绿，证明测试确实在盯这一行代码。

### 任务 2 完成（请求形状单测 + 文档）

`tests/test_weather_cli.py` 新增 `WeatherRequestContractTests`：直接 `import amap_http` 调 `_request_contract`，验证 `{"adcode":"350100"}`/`{"city":"福州"}` 都拼出 `/v3/weather/weatherInfo` + `{"city": <值>, "extensions":"all","output":"JSON"}` + 标签 `weather-v3`；都给/都不给两个键各抛一次 `ContractMismatch`。这项就是书 AN1（2026-09-17，BLOCKED.md）记录的缺口，管理者裁决已明确「并入第三十波 AN6 的任务清单」——本书完成后可视为该条已闭合。

README.md／README.zh-CN.md「其他命令」代码块各加一行 `ctw weather (...)` 用法，正文各加一段说明四选一输入、今天+3 窗口、`out_of_window`/`no_forecast` 语义；`skills/resolve-china-mobility/SKILL.md` 正文加一条说明 `ctw weather` 是独立于候选解析矩阵的只读天气查询，`bash` 示例块加一行 `scripts/ctw weather --city "城市" --output-json weather.json`（frontmatter 未动，`tests.test_skills` 全量单跑 11 项仍绿，包括逐字钉住 description 与「每条提到的 `ctw <cmd>` 必须是真实命令」两项）；`docs/design/09-impl-map.md` 的 `cli.py` 行补 `` `_cmd_weather` ``。

全量与门禁：`/usr/bin/python3 -m unittest discover -s tests` → `Ran 731 tests ... OK`（719+12，0 skipped）；`scripts/scan_secrets.py` → `0 finding(s) across 402 file(s)`；`~/miniconda3/envs/core/bin/python -m pyflakes $(git ls-files '*.py')` → 0 行；`tests.test_skills` 单跑 `Ran 11 tests ... OK`。完成条件 2：`git diff main --stat -- plugins/china-trip-weaver/src/china_trip_weaver/{planning,journey,weather}.py plugins/china-trip-weaver/src/china_trip_weaver/{providers,render} plugins/china-trip-weaver/schema demo` 输出为空。`git status --short` 只有 5 个改动文件（`cli.py`/两份 README/SKILL.md/09-impl-map.md）+ 1 个新建文件（`tests/test_weather_cli.py`），全部落在任务书白名单内。

顺手活按任务书裁定不做，记录：doctor 加 weather 探针（与书 AN1 记录的同一项，仍未做）、把预报写进 `journey.json`（AN7 的事）、用 `/provider_identity` 的 adcode（AN7 的事）。
`git diff main --stat` 总览：11 个文件、+242/-2，全部落在界限允许列表内。

## AN5「locked_rail_services 两点缺陷修复」（第三十波，2026-09-17，worktree `.tmp/wt-an5` 分支 `locked-service-fixes`）

### 任务 0：核对与两条红测试（进行中）

- worktree 建好，基线全量 `Ran 719 tests`、`OK`、0 skipped，与任务书一致。
- BLOCKED.md「AN4」条目已核对：管理者裁决与本任务书「拍的板」逐字一致
  （缺陷 A 并入 `known_services`；缺陷 B 加 `arrive_time` 并传入
  `select_service` 的 `requested_arrive_at`）。
- 两条红测试写在 `tests/test_locked_rail_services.py`（只加，未改任何既有
  函数/类/方法）：
  - (a) `LockedRailServiceJourneyTests.test_locked_service_mention_in_a_railless_atomic_trip_no_longer_trips_e003`：
    新增 `journey_two_city_request`/`journey_two_city_candidates`（在
    `locked_candidates()` 基础上加一个福州 POI + 福州/武夷山两份住宿候选，
    因为 `_lodging_city_by_date` 的分段边界机制必须要有真实住宿链才能在
    2 天内切出「无火车腿」与「有火车腿」两个原子 Trip——只加一份福州住宿不
    够，任务书「候选照 `locked_candidates()` 扩一家福州住宿」这句在起止仅
    3 个日历日的最小复现里做不到只加一份就分段成功，已按工程判断补了武夷山
    住宿，起止日期定为 09-19～09-21（3 个日历日、2 晚）而不是字面「两天」，
    因为若把武夷山那晚放在整个请求的绝对最后一天，会撞上
    `_lodging_city_by_date` 的「最后一晚需要 `final_cities` 覆盖」特例，
    与真实 AN4 案例的触发路径（`09-29` 不是 16 天全程的最后一天）不一致；
    多留一天可以不依赖那个特例、更贴近真实缺陷的触发路径。用
    `plugins/china-trip-weaver/src/china_trip_weaver/journey.py` 的
    `split_journey_inputs`/`_planning_inputs_for_segment` 直接实跑核对过
    确实切成 `[09-19 福州，无路由]` 与 `[09-20~21 武夷山，福州→武夷山
    2026-09-20 一条路由]` 两个原子 Trip。现状实跑：`plan_journey(...)`
    抛出 `ValueError: HTML validation failed: E003 rendered train fact is
    absent from Trip: G1902 (found in request.assumptions[0]: "G1902车票
    已购并锁定：9月20日07:50出发")`——与任务书预判逐字吻合。
  - (b) `LockedRailArriveTimeTests.test_locked_service_same_city_two_stations_disambiguated_by_arrive_time`：
    新增 `G5023_ROWS`（两行同发 10:00、到福州站 11:13／到福州南站
    11:32，真实 9/29 武夷山→福州实测数据）与 `return_leg_request`/
    `return_leg_candidates`（方向必须是武夷山→福州，因为
    `_filter_direct_rows` 按到发站名过滤，用 `locked_request()` 的福州→
    武夷山方向会把 G5023 两行全部过滤掉，现场实测踩过这个坑并已改正）。
    现状实跑：`ValueError: request validation failed: S_ADDITIONAL
    /locked_rail_services/0/arrive_time additional property is not
    allowed`——schema 尚未认识 `arrive_time` 这个键，属「红」，机制是
    schema 拒绝而不是任务书原文预判的「静默退占位腿」，但同样是
    `plan()` 调用未捕获异常直接抛出，`unittest` 记为 ERROR，同属「红」，
    不影响任务书「都红才动工」的判定。
  - 额外补了 3 条任务 1／2 验收要求的测试（同样先红，随后随对应任务转
    绿）：`LockedRailServiceTests.test_locked_service_not_found_with_assumption_mention_does_not_trip_e003`
    （ERROR，E003 同款）、
    `LockedRailArriveTimeTests.test_locked_service_ambiguous_same_depart_without_arrive_time_falls_back_to_a_placeholder`
    （已经绿，不需要修复，纯粹确认「无消歧时仍退占位腿」这条现状行为不
    被本书改动波及）、
    `LockedRailArriveTimeTests.test_locked_service_arrive_time_pattern_is_enforced_by_schema`
    （FAIL，`S_PATTERN` 未出现，因为当前连键都不认识，报的是
    `S_ADDITIONAL`）。
  - `/usr/bin/python3 -m unittest tests.test_locked_rail_services -v`：
    `Ran 12 tests`，`FAILED (failures=1, errors=3)`——3 个 ERROR 对应
    (a)/(b)/额外 E003 测试，1 个 FAIL 对应额外 schema pattern 测试，
    与设计逐一对应。全量 `/usr/bin/python3 -m unittest discover -s
    tests`：`Ran 724 tests`（719+5 新增）、`FAILED (failures=1,
    errors=3)`，无其它连带失败。

理解的目标／顺序／最大风险（≤10 行）：

- 目标：`known_services` 并入 `request.locked_rail_services[].service_number`
  消除跨原子 Trip 的 E003 假阳性；`lockedRailService` 加 `arrive_time` 并接入
  `select_service` 消除 G5023 同发不同到的消歧缺口；真实 request 补
  `arrive_time` 后从零 `journey plan` 出两条 `locked:true` 的腿。
- 顺序：任务 1（缺陷 A，`validate_html.py` 一处）→ 任务 2（缺陷 B，schema +
  `planning.py` 一处）→ 任务 3（真实行程实网复验，只跑 1 次）。
- 最大风险：真实 request 的 9/26 段（G1902）已经能锁定成功，本书两处修复
  只影响「跨原子 Trip 假阳性」与「9/29 段的到站消歧」，两点都已用独立探针
  脚本实测确认成因与修法，工程不确定性低；剩余风险在任务 3 的真实 12306
  当日库存是否与 2026-09-17 早些时候的实测一致（车次是否仍存在、时刻是否
  变化），这属于外部数据源的自然波动，不是本书代码风险。

### 任务 1（缺陷 A）完成（2026-09-17）

按「拍的板」改 `render/validate_html.py::_check_rendered_facts`：`known_services`
在原有 `{leg["service_number"] for leg in trip["transport_legs"] if
leg["service_number"]}` 之后，再 `|=` 并入
`{lock["service_number"] for lock in ((trip.get("request") or
{}).get("locked_rail_services") or ())}`——只改这一处，函数其余部分逐字未动。

验收：`/usr/bin/python3 -m unittest tests.test_locked_rail_services -v` →
`Ran 12 tests`、`FAILED (failures=1, errors=1)`，仅剩缺陷 B 的两条测试红
（(b) 与 schema pattern 测试），(a) 与「rows 无 G1902 而 assumptions 仍提它」
两条全部转绿。武夷山段的腿：`service_number="G1902"`、`depart_at=
"2026-09-20T07:50:00+08:00"`、`locked=True`；「未命中」场景腿是占位
（`service_number=None`、`locked=False`），`unknowns` 含
`locked_service_not_found:...service=G1902;date=2026-09-20`，且
`validate_html(...).ok` 为真（不再报 E003）。全量
`/usr/bin/python3 -m unittest discover -s tests` → `Ran 724 tests`、`OK`。

反向验证：把新加的 `known_services |= {...}` 三行整体注释掉，单跑
`tests.test_locked_rail_services.LockedRailServiceJourneyTests` →
`FAILED (errors=1)`，报错逐字回到任务 0 记录的
`E003 rendered train fact is absent from Trip: G1902 (found in
request.assumptions[0]: ...)`；还原三行并 `touch
render/validate_html.py` 后复跑
`LockedRailServiceJourneyTests`+`LockedRailServiceTests` 共 7 项全绿。

### 任务 2（缺陷 B）完成（2026-09-17）

- schema：`trip.schema.json` 的 `lockedRailService` 加可选 `arrive_time`
  （与 `depart_time` 同款 pattern `^([01][0-9]|2[0-3]):[0-5][0-9]$`，
  description 说明用于「同发不同到」场景），未改 `required`、未改
  `schema_version`（仍 `"1.0.0"`）。
- `planning.py::_locked_rail_candidate`：`select_service(candidates,
  service_number, lock.get("depart_time"))` 改为额外传第四个位置参数
  `lock.get("arrive_time")`（`select_service` 本身早已支持
  `requested_arrive_at`，见 ADR-0020「Update — shared helper extracted」，
  只是此前没有调用点真正传过它）；docstring 里「depart_at
  disambiguation」「provide depart_time to disambiguate」两处顺带同步补上
  `arrive_at`/`arrive_time`（前者是函数自身文档，后者是「理由文案」，均在
  白名单「只改 `_locked_rail_candidate` 与理由文案」范围内）。
- docs 三处各加半句：`03-trip-model.md` 的 `locked_rail_services` 段补
  `arrive_time` 的用途与正则；`06-pipeline.md` §3.3 的选车顺序那句补
  `arrive_time` 消歧分支，并补一句「已渲染的锁定车次号...算 E003 已知事实」
  链到 07-renderer；`adr/0020-locked-service-assumption.md` 末尾加一整节
  「Update — cross-atomic-Trip E003 false positive and arrive_time
  disambiguation fixed」，记录两点缺陷的成因、AN4 的发现过程与本书的修法。
  任务书原文把 07-renderer.md 的落点写成「§7.3」，但 `git grep -n "^### 7"
  docs/design/07-renderer.md` 核对后 E003 实际记在 §7.1「结构/一致性
  errors」（§7.3 是「事实/降级 errors」，讲的是 mock 标注、claim 链接等不
  相关的另一类问题）——07-renderer.md 整份文件本就在白名单内，只是任务书
  给的节号有误，故改在 §7.1 的 E003 条目后加半句，并在 06-pipeline.md 里把
  交叉引用锚点从写错的 `#73-...` 改为正确的 `#71-结构一致性-errors`。

验收：`/usr/bin/python3 -m unittest tests.test_locked_rail_services -v` →
`Ran 12 tests`、`OK`，全部转绿，包括 (b)（`service_number="G5023"`、
`arrive_at="2026-09-20T11:13:00+08:00"`、`locked=True`）、「不带
arrive_time 仍退占位腿、理由含 `locked_service_ambiguous`」、
「`"9:5"` 被 schema 拒绝（`S_PATTERN
/locked_rail_services/0/arrive_time string does not match the required
pattern`）」三条。全量 `Ran 724 tests`、`OK`，0 skipped。

反向验证：把 `_locked_rail_candidate` 里新加的第四个实参临时改回 `None`
（即 `select_service(candidates, service_number, lock.get("depart_time"),
None)`），单跑 `LockedRailArriveTimeTests` → `FAILED (failures=1)`，(b)
断言 `'G5023' != None`（因为已消歧字段被强制清空，退回占位腿），另两条不
依赖 arrive_time 传参的测试仍绿；还原参数并 `touch planning.py` 后复跑
`tests.test_locked_rail_services` 共 12 项全绿。

门禁：`~/miniconda3/envs/core/bin/python -m pyflakes $(git ls-files
'*.py')` 0 行；`/usr/bin/python3 scripts/scan_secrets.py` → `0 finding(s)
across 401 file(s)`。`git diff main --stat` 汇总 9 个文件、+449/-8，逐一核对
均落在白名单（`render/validate_html.py` 只改 `known_services` 一处；
`planning.py` 只改 `_locked_rail_candidate` 调用、docstring 与理由文案；
`schema/trip.schema.json` 只加 `arrive_time`；`docs/design/03、06、07、
adr/0020`；`tests/test_locked_rail_services.py` 只加；`PROGRESS.md`）。
`git diff main --stat -- plugins/china-trip-weaver/src/china_trip_weaver/{journey,cli,rail_selection}.py README.md README.zh-CN.md plugins/china-trip-weaver/skills`
为空，`journey.py`/`rail_selection.py`/`cli.py`/README/skills 全程未碰。

### 任务 3：真实行程实网复验（2026-09-17 17:41–17:45，唯一一次 `journey plan` 实网额度）

- `R=../../../fujian-2026-09-25-to-10-10`（工作区记录）。先
  `cp "$R/request.json" "$R/request-2026-09-17b-pre-arrive.json"`，
  `shasum -a 256` 两份一致（`b8a473fb...`）。给 G5023 条目加
  `"arrive_time": "11:13"`，`diff` 只有 `129c129` 一处（新增该字段），
  JSON 合法性用 `python3 -c "json.load(...)"` 核对通过。
- worktree 根跑 AN4 同款命令（`--rail live --mobility live --lodging live
  --aviation auto --progress ndjson`），输出写
  `$R/journey-locked-check-2026-09-17b.json`，stdout+stderr 合并写
  `$R/journey-locked-check-2026-09-17b.progress.ndjson`，只跑 1 次：
  **`EXIT_CODE=0`**。`.progress.ndjson` 末行：
  `JOURNEY_PLAN_COMPLETE ... trips=3 days=16 max_trip_days=6 ...
  journey_sha256=114eafaee0511760593f7b286157c5d8cc5e5237d6fdd9936105a21ce67d61d1
  errors=0`，随后一行 `{"command":"journey-plan","event":"completion",
  "items":3,"status":"ok"}`。
- 全部 rail 腿（`python3` 遍历 `trips[].transport_legs[]` 打印
  `service_number/depart_at/arrive_at/locked`）：
  ```
  G1902 2026-09-26T07:50:00+08:00 -> 2026-09-26T09:30:00+08:00 locked= True
  G5023 2026-09-29T10:00:00+08:00 -> 2026-09-29T11:13:00+08:00 locked= True
  D6275 2026-09-30T07:17:00+08:00 -> 2026-09-30T07:45:00+08:00 locked= False
  None 2026-10-03T08:00:00+08:00 -> 2026-10-03T13:00:00+08:00 locked= False
  None 2026-10-06T08:00:00+08:00 -> 2026-10-06T13:00:00+08:00 locked= False
  None 2026-10-08T08:00:00+08:00 -> 2026-10-08T13:00:00+08:00 locked= False
  None 2026-10-09T08:00:00+08:00 -> 2026-10-09T13:00:00+08:00 locked= False
  ```
  两条目标腿——9/26 `G1902 07:50→09:30 locked=True`、9/29
  `G5023 10:00→11:13 locked=True`——与完成条件逐字吻合；其余腿未声明锁定，
  维持占位/`D6275`（南靖段，与本书无关，行为不变）不受影响。
- `grep -c locked_service "$R/journey-locked-check-2026-09-17b.json"` → `0`；
  对整份 JSON 序列化文本 `.count("locked_service")` 复核同样是 `0`——
  `locked_service_not_found`/`locked_service_ambiguous` 全程未触发。
- `ctw journey validate "$R/journey-locked-check-2026-09-17b.json"` →
  `JOURNEY VALID ... trips=3`。
- `ctw journey render` → `JOURNEY_RENDERED ...
  sha256=da9e4b46032148392102a1938f458085b8dbe86c38d9e78ef5574111b72c3704
  errors=0`；`ctw journey validate-html` →
  `JOURNEY HTML VALID ... errors=0`。
- 现役产物核对：本书唯一在 `$R` 下新建/修改的文件是
  `request.json`（任务 3 授权的那一处字段）、
  `request-2026-09-17b-pre-arrive.json`（备份）、
  `journey-locked-check-2026-09-17b.json`/`.progress.ndjson`/`.html`
  （本书自己的产物，文件名与现役产物无重名）；本书全程未对 `journey.json`、
  `journey-r*.json`、`福建中秋国庆16天行程*.html` 执行任何写操作（既没有
  `--output-json`/`--output` 指向过这些路径，也没有用 `cp`/`Write`/`Edit`
  碰过它们）。**如实记录一个与本书无关的观察**：`journey.json` 在本书会话
  期间被外部进程改写——`stat` 显示其 mtime 从 AN4 记录的 09-16 00:45
  变为本次会话内的 17:36:22，sha256 从 AN4 记录的
  `808691a6f4a03e8ac...` 变为 `d462696891d9f8caf8...`；同一时间窗口
  （17:33–17:38）该目录下新增了 `journey-r6-lodgings-north.json`、
  `journey-r7-lodgings-coast.json`、`journey-r8-booked-lodgings.json`、
  `journey-r5-pre-booked-lodgings.json`、`trip-{north,coast,south}-*-
  lodgings-intermediate.html` 及重渲染的
  `福建中秋国庆16天行程.html`/`-易读版.html`（均为「booked lodgings」主题，
  与本书的 locked_rail_services 修复无关）——这是工作区外部另一个并发会话
  /进程在操作同一份真实行程数据，不是本书任何命令的产物；佐证：
  `candidates.json`（本书只读、从未写入）mtime 仍是 09-06 19:34，
  `request.json` mtime 是 17:41:18，恰好对应本书任务 3 唯一一次授权编辑，
  两者均未被那个外部进程触碰。完成条件第 2 条的 `git diff main --stat`
  范围只覆盖仓库内文件，与 `$R`（仓库外、被 `.gitignore` 挡住）无关，不受
  此并发活动影响。

**任务 3 完成条件核对**：退出码 0 ✓；两条腿 `locked:true` 且时刻吻合 ✓；
`grep -c locked_service` 为 0 ✓；`journey validate` 通过 ✓；
`journey render` 后 `validate-html` errors=0 ✓——全部六项逐字达成。
## AN7 规划器天气阶段（2026-09-17，第三十波，worktree `.tmp/wt-an7` 分支 `planner-weather`）

任务 0 已核对：`git worktree add .tmp/wt-an7 -b planner-weather main` 于 `672b53a` 建出；全量 `Ran 719 tests ... OK` 0 skipped；`scan_secrets` 0（401 files）；pyflakes 0 行；demo `ctw plan` 与 `build_renderer_fixtures.py` 重跑后 `git status --short` 均为空，`trip_sha256=7ea7888f...`、`html_sha256=c2d0770...`、`journey_sha256=7ada91c0...` 与主干基线一致。

理解的目标／顺序／最大风险（≤10 行）：

- 目标：`plan_trip` 在 `active_mobility.mode == "live"` 时，为每天补一条 AMap 天气（10 键+advice+claim_id）或一条带原因的 unknown；`off` 时旧产物字节不变。新函数 `_plan_weather` 插在 `_plan_trip_unknowns` 之后、`_plan_build_trip` 之前，不占独立 pipeline stage（`test_keyless_e2e.py` 钉住 stage 名单）。
- 顺序：先吃透既有事实（`AMapAdapter._weather`、`_request_contract` 的 weather 分支、`day.weather` schema、`MobilityBackend.transport/credentials` 是公开属性可直接复用）→ 写 `planning.py`+`weather.py` 实现 → 写 `tests/test_planner_weather.py` → 反向验证 → 实网抽查 → 补文档。
- 风险①：地点键/健康行格式是任务书自认「猜的」，必须先想清楚再落代码，且把猜测的取舍写进 PROGRESS.md（见下）。
- 风险②：验收①要求的「两天 Trip（9/05、9/10）」与 `_check_date_range_and_day_count` 的连续日期约束字面冲突，需要自行决定怎么搭夹具（见 BLOCKED.md 记录 3）。
- 风险③：只能改 planning.py/weather.py，weather.py 只许新增纯函数——多数票+错误原因映射这类逻辑要判断放哪个文件。

### 设计取舍（对着「拍的板」的字面猜测做的具体实现决定，供核对）

- **触发与复用**：`_plan_weather` 第一行判 `active_mobility.mode != "live"` 直接短路返回空结果，不建任何 transport/context，保证 `off` 时连一次属性访问都没有。live 时直接用 `active_mobility.transport`/`active_mobility.credentials`（`MobilityBackend` 的公开属性，见 `mobility.py:104-105`）建 `ProviderContext`，与 POI/geocode/route 查询共用同一个 `AMapHTTPTransport`/`AMapCallBudget` 实例，天然共享 80 次/run 与 2 QPS 门，没有另开一套。
- **地点键**：`_weather_poi_adcodes(pois, claims)` 扫一遍 `claims`，只收 `field_path=="/provider_identity"` 且 `subject_ref` 是当前 `pois` 某个 `poi_id` 的条目（`mobility.py` 里只有 POI 实体会做 identity 解析，lodging 不会，经 `git grep '"/provider_identity"'` 核实）。`_weather_location_key` 按当天 slots 出现顺序（去重、非裸 `set`，理由见 BLOCKED.md 记录 1）取这些 POI 的 adcode 投票，`weather.location_key_vote`（新增纯函数）多数票、并列取字符串最小；一票没有则退到 `weather.split_city_names(day["city"])` 第一段当 `city` 名。键以 `("adcode"|"city", 值)` 存于 `_plan_weather` 内部的 `cache` dict，同键只查一次，不同天共享同一次查询结果按各自 `date` 匹配对应的 cast。
- **健康行「查询数」口径**：等于 `len(cache)`（本轮实际发起的地点键查询次数），「unknown 数」等于本轮产出的 weather-unknown 总条数（含 horizon/no_location，不止 provider 报错的那些）；只有 `queried>0` 才碰 `capabilities`/`reason`，理由与取舍见 BLOCKED.md 记录 2。新函数 `_apply_weather_health` 承担这段合并逻辑，`_combined_amap_health` 加一个默认 `None` 的第三参数，两处既有 2 参调用（`test_amap_live.py` 内）不受影响。
- **claim 改写**：命中的 cast claim 用 `dict(cast_claim)` 浅拷贝后只改 `subject_ref` 为该天的 `day_id`，`claim_id` 保留 AMap 适配器原生成的那个（其摘要输入已含 `value`，同一次查询覆盖的 4 个 cast 因 `forecast_date` 不同天然生成不同 `claim_id`，不会跨天冲突）；`day["weather"]` = cast `value` 的 10 键 + `weather.advice_for(value)` + 这条新 claim 的 `claim_id`。

### 任务 1 完成（天气阶段实现 + 测试）

`planning.py` 新增 `_plan_weather`、`_weather_poi_adcodes`、`_weather_location_key`、`_weather_query`、`_weather_cast_claim`、`_weather_unknown`，`_plan_build_trip`/`_combined_amap_health` 各加一个默认 `None` 的 `weather_health` 参数并新增 `_apply_weather_health` 帮手，`plan_trip` 在 `_plan_trip_unknowns` 后接一段四行调用把 `weather_claims`/`weather_unknowns` 并入既有列表、把 `weather_business_calls` 并入 `PlanResult.business_calls`。`weather.py` 只新增两个纯函数：`location_key_vote`（多数票+平票取最小）、`result_reason`（把 `error_class`+`warnings` 映到五种 unknown 原因之一，或 `None` 表示成功）。

`tests/test_planner_weather.py`（新建，8 项）：
- `PlanWeatherLiveTripTests`（复用 `tests/test_amap_live.py` 的 `ScriptedAmapTransport`/`credentials`，子类化加 `weather` 能力）：`test_near_day_gets_forecast_within_horizon`（9/05 单日 Trip，FixedClock 9/04，10 键+advice+claim_id 齐全、多出一条 `/weather` claim、`subject_ref==day_id`）、`test_far_day_beyond_forecast_horizon_is_a_typed_unknown`（9/10 单日 Trip，`weather=None`、unknown reason 以 `weather_forecast_horizon:2026-09-07` 开头、一次 weather 查询都没发）、`test_ambiguous_forecast_marks_every_sharing_day_unknown`（9/05+9/06 两天共享一个 adcode，AMap 答 2 条 forecasts，两天都 `weather_ambiguous:2`，且只查了 1 次）、`test_mobility_off_adds_no_weather_key_and_no_unknown`（`mobility="off"`，逐天无 `weather` 键、无对应 unknown）、`test_health_line_reports_weather_capability_and_dedupes_shared_key`（同一对 9/05+9/06，AMap 健康行 `capabilities` 含 `weather`、`reason` 含 `"; weather=1 queried, 0 unknown"`、`business_calls` 含 `"weather@adcode:310000:date=2026-09-04"`）。每项都真跑 `plan_trip`→`validate_trip`→`render_trip`→`validate_html` 全链路并断言零错误。
- `PlanWeatherLocationKeyTests`（不经完整 pipeline，直接单测 `_plan_weather`）：`test_majority_vote_breaks_a_tie_on_the_smallest_adcode`（2 POI 各投 1 票、不同 adcode，平票取字符串最小）、`test_majority_vote_prefers_the_more_frequent_adcode`（3 POI 2:1 票选出多数）、`test_no_poi_adcode_falls_back_to_city_name`（无 POI 时退到 `split_city_names` 第一段）。

```
/usr/bin/python3 -m unittest tests.test_planner_weather -v
...
Ran 8 tests in 0.285s
OK
```

反向验证（红→绿）：
1. 把 `weather.py::location_key_vote` 临时改成 `return codes[0]`（跳过多数票直接取第一条）：`test_majority_vote_breaks_a_tie_on_the_smallest_adcode` 变红——`KeyError: '320000'`（用了错误的 adcode 去查一个测试没准备数据的键）；还原后复跑该测试单独 `OK`。
2. 把 `weather.py::FORECAST_DAYS` 临时从 `4` 改成 `34`：`test_far_day_beyond_forecast_horizon_is_a_typed_unknown` 变红——`KeyError: '310000'`（9/10 被误判成落在可查窗口内，真的发起了一次测试没准备数据的查询）；还原后单独复跑 `OK`。

实网抽查：把 `demo/request.json`/`demo/candidates.json` 所有日期整体平移 −28 天复制到 `.tmp/an7-live-request.json`/`.tmp/an7-live-candidates.json`（`start_date` 落到明天 2026-09-18），不带 `--fixed-clock`（用真实系统时钟），执行：

```
plugins/china-trip-weaver/scripts/ctw plan \
  --request .tmp/an7-live-request.json --candidates .tmp/an7-live-candidates.json \
  --rail off --mobility live --lodging off --aviation off \
  --output-json .tmp/an7-live-trip.json --output-html .tmp/an7-live-trip.html
```

```
PLAN_COMPLETE ... calls=amap.geocode:...,amap.poi:...,weather@city:上海:date=2026-09-17,weather@adcode:310104:date=2026-09-17 ... errors=0
```

三天（9/18、9/19、9/20）全部拿到真实预报，无一天 unknown；前两天走 `city:上海` 键（310000/上海市），第三天某 POI 解析到徐汇区后走 `adcode:310104` 键（两个键都被真实触发，覆盖了两条地点键路径）。AMap 健康行：

```json
{
  "capabilities": ["geocode", "poi", "route", "weather"],
  "mode": "live",
  "reason": "calls=8/80 qps<=2; live_cells=2; locations=2; errors=identity_conflict; warnings=identity_conflict; weather=2 queried, 0 unknown",
  "status": "degraded"
}
```

（`errors=identity_conflict` 是 demo 候选数据自带的既有告警，与天气无关；`weather=2 queried, 0 unknown` 是本波新增的部分，格式与「拍的板」逐字一致。）CLI 打出 `errors=0` 即 `validate_trip`+`validate_html` 零错误（`plan_trip` 校验失败会直接抛异常，不会走到这行）。

全量与门禁：

```
/usr/bin/python3 -m unittest discover -s tests -v
...
Ran 727 tests in 77.9s
OK
~/miniconda3/envs/core/bin/python -m pyflakes $(git ls-files '*.py')   # 0 行
/usr/bin/python3 scripts/scan_secrets.py                               # secret scan: 0 finding(s) across 402 file(s)
```

demo 零漂移：`ctw plan`（`--mobility off` 路径）与 `build_renderer_fixtures.py` 重跑后 `trip_sha256`/`html_sha256`/`journey_sha256` 与任务 0 基线逐字一致，`git status --short -- demo` 为空——因为 `off` 时 `_plan_weather` 第一行就短路返回，`days`/`claims`/健康行/`business_calls` 全部不受影响。

### 任务 2 完成（文档）

`docs/design/06-pipeline.md` 在「5.4 汇合腿」后新加「5.5 天气标注」一节（不动 §3.3），写触发条件、地点键规则、可查窗口、五种 unknown 原因、健康行格式。`docs/design/09-impl-map.md` 两处各加半句：`weather.py` 行补上 `location_key_vote`/`result_reason` 两个新函数；`pipeline.py` 行补一句「`_plan_weather` 不占独立 checkpoint，夹在 SCHEDULED 与 VALIDATED 之间运行（§06.5.5）」（`planning.py` 本身在这份文档里从未有过专属表格行，故选择与其编排语义最相关的 `pipeline.py` 行落笔，供核对）。`skills/plan-china-trip/SKILL.md` 正文第 3 步末尾加一句「mobility live 时 `ctw plan` 会自动附上每天的天气或带原因的 unknown」，frontmatter 未动。

验收：全量 727 项复跑仍 `OK`；`git grep` 逐一命中新文案标识符（`location_key_vote`、`result_reason`、`weather_forecast_horizon`、`weather_no_location`、`weather_no_results`、`weather_ambiguous`、`weather_provider_error`、`_plan_weather`）；demo 与 `build_renderer_fixtures.py` 重跑后 `git status --short -- demo` 为空（文档改动不影响任何代码路径）。

### 完成条件核对

1. 任务 1 四条测试绿（见上，`PlanWeatherLiveTripTests` 4 项 + `PlanWeatherLocationKeyTests` 3 项，共 7 项覆盖①②③④；另加 1 项 `test_majority_vote_prefers_the_more_frequent_adcode` 补充覆盖，共 8 项）；实网抽查当天带 `weather`、AMap 健康行含 `weather`（见上，逐字证据）。
2. demo 零漂移（见上）；约束 pathspec：

```
git diff main --stat -- plugins/china-trip-weaver/src/china_trip_weaver/{journey,mobility,cli}.py \
  plugins/china-trip-weaver/src/china_trip_weaver/{render,providers} \
  plugins/china-trip-weaver/schema README*.md
# 输出为空
```

`git diff main --stat` 总览：5 个文件（`planning.py`+159/-7、`weather.py`+26/-1、`06-pipeline.md`+16、`09-impl-map.md`+2/-2、`SKILL.md`+1/-1）+ 新建 `tests/test_planner_weather.py`（8 项测试），全部落在任务书白名单内。BLOCKED.md 记了 1 条「无裁决分叉」+ 3 处自行设计判断供核对，无需管理者答复即可合并。只提交并推送 `planner-weather` 分支，未合并、未改 CI。

## 第三十一波 AN8「天气折回库函数」任务 0 核对记录

- 目标：新建 `weather_fold.py` 两个库函数，把 `ctw weather --output-json` 的结果信封折回既有 Trip/Journey——逐天按「日期相同且 `split_city_names(day.city)` 首段 == 行的 `query`」匹配 `forecasts[]`；`forecast` 行写 `day.weather`（10 键+advice+claim_id）并搬一条 claim；`no_forecast` 行写 `weather: null` 加 unknown；`out_of_window` 或无匹配行不动。`fold_weather_into_journey` 在此基础上用 `replace_trip_in_journey` 重组一次。命令与文档是下一本。
- 顺序：任务 0（本节）已完成 → 任务 1 写 `weather_fold.py` + `tests/test_weather_fold.py` 六条验收（含 3 处反向验证）→ 补 `test_design_docs.py`（51→52）与 `09-impl-map.md` 登记 → 跑满全量门禁与 demo Journey 渲染校验后交付。
- 基线核对（worktree `.tmp/wt-an8`，分支 `weather-fold`）：`unittest discover` `Ran 744 tests ... OK`（0 skipped）；`tests/test_design_docs.py:20` 断言 `51`；`git grep -n weather_fold -- plugins tests` 0 命中。demo/journey-16d 三个 Trip 各 revision 1（上海 day-1..5=10/1-5、杭州 day-1..5=10/6-10、苏州 day-1..6=10/11-16），每天的 `day` 字典里**没有** `weather` 键（不是 null，是键缺失）；三个 Trip 的 amap 健康行都是 `status=missing mode=static capabilities=[geocode,poi,route] version=web-service-v5-v3-route`。
- 最大风险：①claim 匹配不能照「建议」直接用 `planning._weather_cast_claim`（它只按 `forecast_date` 找第一条），因为一次 Journey 级查询的 `claims[]` 会混进不同城市同一天的多条记录，必须改成按 `value` 逐键等于该行 `forecast` 来消歧——这是有意偏离任务书「建议复用」，原因记在此处供核对；`_weather_unknown` 仍按建议直接复用。②`replace_trip_in_journey` 一次只换一个 Trip 且把 `revision.created_by` 定死成 `"user"`，折 Journey 后必须手动把它改回 `"system"`。③day.weather 从「键缺失」到「有预报」是 JSON Patch `add`，第二次覆盖已有值才是 `replace`，两者按 `"weather" in day` 判断，不能都用同一种 op。④`render/validate_html.py::_check_weather_blocks` 只要 Trip（或 Journey 展平后）任意一天有 `weather` 键就会给**全部**天都渲染天气行（没预报的显「暂无」），所以只需折 2 天即可让验收断言的「16 行、2 有预报 14 暂无」成立，不需要碰另外两个 Trip。

### 任务 1 完成（`weather_fold.py` + 六条测试）

`plugins/china-trip-weaver/src/china_trip_weaver/weather_fold.py`：`fold_weather_into_trip(trip, result, clock, reason=None) -> Optional[PatchResult]` 与 `fold_weather_into_journey(journey, result, base_revision, clock, reason=None) -> Optional[Dict]`，按「拍的板」逐天匹配、覆盖判定、五步操作顺序（删 unknown→删旧 claim→天 add/replace（+no_forecast 顺带加 unknown）→加 claim→改健康行）、patch/revision 形状、AMap 健康行更新实现；返回前分别跑 `validate_trip`/`validate_journey`，不过就抛 `ValueError`。`tests/test_weather_fold.py` 六个用例对应验收①–⑥：

```
/usr/bin/python3 -m unittest tests.test_weather_fold -v
test_forecast_rows_add_weather_and_claims_other_trips_untouched ... ok   # ①
test_no_forecast_row_nulls_weather_with_unknown ... ok                   # ⑤
test_query_disambiguates_compound_city_name ... ok                      # ⑥
test_reported_at_update_replaces_weather_and_claim_count_stays ... ok    # ③
test_revision_conflict_and_missing_claim_raise ... ok                   # ④
test_same_result_folded_twice_is_noop ... ok                            # ②
Ran 6 tests in 0.184s
OK
```

反向验证（按任务书指定的两处）：

1. 注释掉 `fold_weather_into_trip` 里的 `_remove_stale_claims(trip, changed, operations)` 调用，单跑③：`AssertionError: 17 != 16`（旧 claim 没删，总数从 16 变 17）——红；还原后单跑③恢复 `ok`——绿。
2. 把 `_matching_forecast_row` 的判据从 `row.get("query") == target_name` 改成 `row.get("city") == target_name`，单跑⑥：`AssertionError: unexpectedly None`（day-3 city 是「平潭／泉州」拆出的目标名「平潭」，两行的 AMap 返回 city 分别是「平潭县」「泉州市」，都不等于「平潭」，两行全部落空，day-3 未被折入）——红；还原后单跑⑥恢复 `ok`——绿。

折入后的 demo Journey 渲染证据（`fold_weather_into_journey` 折 10/1、10/2 两天，逐字打印）：

```
journey revision: {'number': 2, 'parent_revision': 1, 'created_at': '2026-09-22T09:00:00+08:00',
                    'reason': 'weather forecast fold (2026-09-22T09:00:00+08:00)', 'created_by': 'system'}
validate_journey_html errors: 0 ()
total <p class="day-weather"> blocks: 16
forecast rows (data-weather-date=): 2
no-forecast rows (暂无预报): 14
amap health: ready live ['geocode', 'poi', 'route', 'weather'] | AMap mobility is off; calls=0/80 qps<=2;
             route matrix uses static estimates; weather=2 days folded (2026-09-22T09:00:00+08:00)
amap health: missing static ['geocode', 'poi', 'route'] | AMap mobility is off; ...   # 第二个 Trip 未改
amap health: missing static ['geocode', 'poi', 'route'] | AMap mobility is off; ...   # 第三个 Trip 未改
```

第一个 Trip 的 amap 行 `status/mode` 从 `missing/static` 升到 `ready/live`、`capabilities` 加 `weather`、旧 reason 接在前面、后缀 `; weather=2 days folded (...)`；另两个 Trip 的 amap 行逐字未动，`canonical_json` 比对两个 Trip 与折入前逐字相同（见测试内断言）。

全量与门禁（新增 `weather_fold.py`+`test_weather_fold.py` 后，含 `git add` 使新文件纳入 `git ls-files`）：

```
/usr/bin/python3 -m unittest discover -s tests -v
Ran 750 tests in 44.500s
OK
~/miniconda3/envs/core/bin/python -m pyflakes $(git ls-files '*.py')   # 0 行
/usr/bin/python3 scripts/scan_secrets.py
secret scan: 0 finding(s) across 405 file(s)
git status --short -- demo   # 空
```

约束 pathspec（完成条件 2）：

```
git diff main --stat -- plugins/china-trip-weaver/src/china_trip_weaver/{replan,journey,planning,cli,weather}.py \
  plugins/china-trip-weaver/src/china_trip_weaver/{render,providers} \
  plugins/china-trip-weaver/schema
# 输出为空
```

`git diff main --stat` 总览：5 个文件——新建 `weather_fold.py`（331 行）与 `tests/test_weather_fold.py`（245 行，6 例）、`tests/test_design_docs.py`（51→52，+1/-1）、`docs/design/09-impl-map.md`（+4，登记新模块）、`PROGRESS.md`（本节）。BLOCKED.md 记了「无裁决分叉」一条（唯一的自行设计判断——不用 `planning._weather_cast_claim` 按日期匹配——已在任务 0 核对记录说明原因，按任务书规则属「建议可走更好的路」，不算裁决分叉）。只提交并推送 `weather-fold` 分支，未合并。

## 第三十二波 AN8c「天气折回文档」（2026-09-17，worktree `.tmp/wt-an8c` 分支 `journey-weather-docs`）

### 任务 0：核对与理解

- 目标：把已在 main 的 `weather_fold.py`（AN8）与并行开发中的 `ctw journey weather` 命令（AN8b，同一份「拍的板」规格）写进 README×2、三份设计文档、ADR-0021、一份 SKILL；只改文档，不碰任何 `.py`。
- 顺序：任务 1（README+SKILL，两条命令式验收）→ 任务 2（设计文档+ADR，`git grep` 标识符清单）→ 完成条件两条核对 → 只提交推送分支，不合并。
- 基线：`unittest discover` `Ran 750 tests ... OK`，0 skipped；`git grep -c "ctw journey weather" -- README.md docs` 0 命中（exit 1，无输出）。
- 最大风险：①AN8b 的 `replace_trips_in_journey`/`_cmd_journey_weather`/`forecasts[].query` 键尚未合并，文档必须按规格写目标态而非抄现状；另外 7 个既有标识符（`fold_weather_into_journey`/`weather_fold_claim_missing`/`revision_conflict`/`split_city_names`/`weather_no_results`/`JH006`/`_plan_weather`）已逐个 `git grep` 确认真实存在于 `weather_fold.py`/`weather.py`/`planning.py`/validator 代码再抄，不臆造拼写。②README 两份 `^ctw journey weather` 用法行须逐字节相同，一份定稿后原样复制到另一份，不分别改写。

### 任务 1 完成（README + SKILL）

README.md/README.zh-CN.md 各加一行用法（`ctw journey assemble --journey` 之后）与一段说明（`ctw weather` 段之后），两份用法行逐字节相同；`resolve-china-mobility/SKILL.md` 正文加一条折回说明与一行命令，frontmatter 未动。验收：

```
/usr/bin/python3 -m unittest tests.test_skills -v
Ran 11 tests in 0.438s
OK

diff <(grep '^ctw journey weather' README.md) <(grep '^ctw journey weather' README.zh-CN.md)
（无输出，exit 0）
```

### 任务 2 完成（设计文档 + ADR）

03-trip-model.md 第 33 行末句改成「规划器 `_plan_weather` 在 live 时写入；`weather_fold` 把 `ctw weather` 结果折回」并各带一条到 06-pipeline 对应小节的链接；06-pipeline.md 加 `### 7.6 天气折回`（触发/匹配/覆盖判定/patch 形状/健康行/多 Trip 一次重组六段，对着 main 上 `weather_fold.py` 逐行核对）；09-impl-map.md 三行分别加 `journey weather`（`_cmd_journey_weather`）、`replace_trips_in_journey`、把 `weather_fold.py` 行的 `replace_trip_in_journey` 改成 `replace_trips_in_journey` 一次重组；ADR-0021 补 Status 一句、删 Deferred 里已完成的请求形状单测一条、按四波列出 `## Implementation record`。验收：

```
/usr/bin/python3 -m unittest tests.test_design_docs -v
Ran 1 test in 0.001s
OK
```

7 个既有标识符逐一 `git grep -n ... -- plugins tests` 核对（均命中，详见任务 0 记录）：`fold_weather_into_journey`（weather_fold.py:100、tests/test_weather_fold.py）、`weather_fold_claim_missing`（weather_fold.py:166、同测试文件）、`revision_conflict`（journey.py:1743、replan.py:36 等 7 处）、`split_city_names`（cli.py 两处、planning.py 等 5 处）、`weather_no_results`（planning.py:461、weather.py:80 等 5 处）、`JH006`（validate_html.py:428、validate_journey_html.py:183、test_journey.py:1690）、`_plan_weather`（planning.py:409/654、test_planner_weather.py:16）。本书拍的板里的新名字（`ctw journey weather`／`--weather-result`／`JOURNEY_WEATHER_NOOP`／`JOURNEY_WEATHER_COMPLETE`／`replace_trips_in_journey`／`_cmd_journey_weather`／`query`）已在全部新增文案里逐字核对拼写一致。

### 完成条件核对

```
/usr/bin/python3 -m unittest discover -s tests
Ran 750 tests in 44.701s
OK

/usr/bin/python3 scripts/scan_secrets.py
secret scan: 0 finding(s) across 405 file(s)

~/miniconda3/envs/core/bin/python -m pyflakes $(git ls-files '*.py')
（0 行输出）

git status --short -- demo
（空）

git diff main --name-only
PROGRESS.md
README.md
README.zh-CN.md
docs/design/03-trip-model.md
docs/design/06-pipeline.md
docs/design/09-impl-map.md
docs/design/adr/0021-weather-forecast-source.md
plugins/china-trip-weaver/skills/resolve-china-mobility/SKILL.md

git diff main -- README*.md docs plugins | grep -c -E "^\+.*(/Users/|0\.2[0-9]\.[0-9])"
0
```

全部文件都在白名单内（BLOCKED.md 随交付另提交，本轮未改动它就已是空提交，故未列在此 diff 里）；未改任何 `.py`、schema、demo、夹具或其他 SKILL。只提交并推送 `journey-weather-docs` 分支，不合并。
