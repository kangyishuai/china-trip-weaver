# PROGRESS

唯一的当前进度记录：现状速览（0.8.0 起每个版本一条）、几条长期有效的实测结论，以及历史索引。逐轮任务书、实测证据与验收记录按时间段归档，见「历史索引」——本文件不再留存单轮过程记录。

## 现状速览（2026-09-17 实测，0.24.0）

- 版本：`0.24.0`，唯一来源是
  `plugins/china-trip-weaver/.codex-plugin/plugin.json` 与
  `src/china_trip_weaver/__init__.py` 的 `__version__`，两处一致，仓库内其余
  代码与文档一律引用这两处之一；只有本节的逐版本条目和 git tag 以版本号作索引。
- 测试：仓库根 `/usr/bin/python3 -m unittest discover -s tests` 全量 `Ran 756 tests`，`OK`，0 skipped；
  `scripts/scan_secrets.py` 0 命中；
  `~/miniconda3/envs/core/bin/python -m pyflakes plugins/china-trip-weaver/src
  tests scripts` 0 行。带假 Key（`ANYSEARCH_API_KEY=... unittest`）跑全量同样
  756 OK，README 的 demo 与全部夹具重生成在有无 Key 两种环境下都零差异。0.21.0 记过的
  「环境变量注入会让 `test_credentials` 红一项」已在 0.22.0 修好：那个文件现在于 `setUp`
  里按 `FILE_ALLOWLIST` 剥掉凭据环境变量，四个 Key 全设与一个不设两种跑法结果相同。
- 覆盖率：`scripts/measure_coverage.py` 2026-09-17 发 0.24.0 前实测 11354 语句、miss 1270、**89%**（0.23.0 时 11154/1259/89%，0.22.1 时 10706/1210/89%）。
- 0.24.0（第三十一波一本＋第三十二波两本并行，2026-09-17，逐本验收合入）：**把预报折回既有行程**——
  新叶子模块 `weather_fold.py`：`fold_weather_into_trip(trip, result, clock, reason=None)` 逐天按「日期相同且
  结果行的 `query` 等于 `split_city_names(day.city)` 第一段」匹配 `ctw weather --output-json` 的 `forecasts[]`，
  `forecast` 行写 `day.weather`（claim 按 `value` 逐键匹配后改 `subject_ref` 为 day_id 搬入，找不到抛
  `weather_fold_claim_missing`），`no_forecast` 行写 `null` 加 `weather_no_results` unknown，`out_of_window` 或
  无匹配行的天一个字节不动；新旧值逐键相同不算改动，同一结果折两次返回 `None`；改动按 `replan_trip` 的 patch
  形状记账（`trigger=weather`，op 顺序：删旧 unknown→删旧 claim→天 add/replace→加 claim→改 AMap 健康行；健康行补
  `weather` 能力、非 ready/live 时改成 ready/live 以保证页脚署名高德）。`fold_weather_into_journey(journey, result,
  base_revision, clock, reason=None)` 把所有被改的子 Trip 交给 journey.py 新增的 `replace_trips_in_journey` 一次
  重组，Journey revision 只加一（AN8 首版逐个调 `replace_trip_in_journey`，两个 Trip 同时被改时版本 1 跳 3、
  `parent_revision` 指向从未落盘的 2，验收查出、AN8b 修）；`replace_trip_in_journey` 改为传单个 Trip 调它，行为不变。
  `ctw weather --output-json` 的每行多一个 `query` 键（原始查询名；forecast 行的 `city` 是高德解析名如「福州市」）。
  新命令 `ctw journey weather --journey J --weather-result W --base-revision N --output-json OUT [--reason]
  [--fixed-clock]`：没有任何一天被改打 `JOURNEY_WEATHER_NOOP` 退出 2 不写文件；成功打 `JOURNEY_WEATHER_COMPLETE
  json=… revision=… trips_changed=… journey_sha256=…` 退出 0；`revision_conflict`、claim 对不上、校验不过打
  `JOURNEY_WEATHER_FAILED` 退出 1；`--journey` 原文件永不写回。文档：README 两份用法行与段落、06-pipeline §7.6
  天气折回、03-trip-model `day.weather` 末句改为现状、09-impl-map 三行、ADR-0021 加 Implementation record、
  mobility SKILL 一条一命令。真实行程只读演练（距 9/25 还有 8 天）：`ctw weather --journey` 22 行全
  `out_of_window`、`ctw journey weather --base-revision 9` NOOP 退出 2、现役 journey.json sha 不变；管理者暗卷用手造
  9/25 福州预报折入副本：revision 10、只 north 段变、页面 16 行天气（1 有 15 暂无）、validate-html 0、署名高德、二折
  NOOP。测试 744→756（`test_weather_fold.py` 7、`test_journey_weather_cli.py` 4、`test_weather_cli.py` +1），
  运行时+脚本 `.py` 51→52。
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

## 第三十三波执行记录（2026-09-17，五本并行，美食推荐第一波）

### 书 AP1a「poi_around 综合排序与 distance_meters」（worktree `.tmp/wt-ap1a` 分支 `around-sortrule`）

**任务 0 核对**：目标——给 AMap `poi_around` 请求加可选 `sortrule`（`distance`/`weight`，缺省
`distance`，其它值报 `ContractMismatch`，按原名透传）；`_pois` 归一化项加 `distance_meters`
（`around-v5` 取 raw `distance` 转 int，文本搜索为 `None`）；新增 `around_dining` 夹具（6 家合成餐厅）、
`fixture_count` 88→89。顺序：先改 `amap_http.py` 的 `sortrule` 分支（独立、无下游依赖）并测试，
再改 `amap.py::_pois` 加 `distance_meters`，跑既有夹具回放确认「旧行为字节不变」，最后加
`around_dining` 夹具与测试。核对基线数字 5/6 项精确匹配；`git grep -n distance_meters --
plugins/.../providers` 不是 0 命中（实测 12 处，分布在 `amap.py:160`『`_route` 方法的路线距离
claim』与 `mcp_stdio.py`/`rail12306.py`『既有的 12306 站点候选靠 AMap 距离消歧功能』，均与本书要改
的 `_pois` 无关），判定非阻塞，继续任务 1；证据见 BLOCKED.md。**最大风险**（核对后命中，见下）：
`#/$defs/poi` 的 schema `additionalProperties:false` 且未声明 `distance_meters`，`_pois` 归一化项一
旦携带该键就会被 `run_fixture` 的强校验拦下，与「不许碰 schema」互斥。

**任务 1 完成情况**：checklist① 全部完成——`amap_http.py::_request_contract` 的 `poi_around` 分支
（[amap_http.py:388-405](plugins/china-trip-weaver/src/china_trip_weaver/providers/amap_http.py:388)）
把硬编码 `"sortrule": "distance"` 改成 `values.get("sortrule", "distance")` 并校验取值 ∈
`{"distance", "weight"}`，否则 `ContractMismatch`；新增
`tests.test_providers.PoiAroundRequestContractTests` 三个用例（缺省 distance／显式 weight
透传／rating 报错），`/usr/bin/python3 -m unittest tests.test_providers -v` 112 项全绿；反向验证——
删掉取值校验后 `test_request_contract_rejects_unsupported_sortrule` 变红
（`AssertionError: ContractMismatch not raised`），`cp` 还原并 `touch` 后三项复绿。

checklist②③ 里 `distance_meters` 那一条**被真实 schema 冲突阻塞，未实现**：只改 `_pois` 加一行
`"distance_meters": int(raw["distance"]) if body.get("api") == "around-v5" else None`（未碰 schema、
未加新夹具），跑 `tests.test_providers` 立刻 5 项从绿变红（`test_fixture_amap_around_stations`／
`boundary_hk`／`malicious`／`pagination_page2`／`success`，`Ran 112 tests ... FAILED (failures=5)`），
失败文本逐字：`AssertionError: Lists differ: [] != ['S_ADDITIONAL /distance_meters additional
property is not allowed']`。根因：`#/$defs/poi`
（[trip.schema.json:733-747](plugins/china-trip-weaver/schema/trip.schema.json:733)）
`"additionalProperties": false` 且 10 个 `required` 键里没有 `distance_meters`；
`run_fixture`（[test_providers.py:84-96](tests/test_providers.py:84)）对每个 POI 类夹具的每个归一化
项都用 `SchemaSubsetValidator.validate_fragment("#/$defs/poi", item)` 强校验，`additionalProperties`
分支（[validate_trip.py:163-166](plugins/china-trip-weaver/src/china_trip_weaver/validate_trip.py:163)）
逐键比对，未声明的键一律 `S_ADDITIONAL`。这不是只命中 `around_stations` 一处的偶然——`around_dining`
新夹具回放时会被同一条规则拦下。三条硬约束互斥（板上「`_pois` 加键 `distance_meters`」／界限「不许碰
schema」／完成条件「全部既有夹具回放结论不变、`tests.test_providers` 与全量绿」），任何两条可同时满
足，三条凑不齐。按任务书「让步顺序：旧行为字节不变 > 合同严格 > 省事」，`_pois`/`amap.py` 的改动已
`git checkout` 撤销，`distance_meters` 键至今不存在于任何归一化项上。

checklist②**除 `distance_meters` 外的部分已实现**：`distance_meters` 是否可加只取决于 schema，与夹具
本身是否存在是两件独立的事——夹具的原始 JSON（`pois[].distance`）不经过 `#/$defs/poi` 校验，只有
`_pois()` 归一化后的 item 才会。于是仍在界限内（只改 `build_provider_fixtures.py`／`tests/fixtures/
providers/`（脚本重生成）／`tests/test_providers.py`（只加））补上了 `around_dining` case：新增
`amap_dining_poi()` 助手＋6 家合成餐厅（distance 820/1240/310/1480/640/960，不按升序；4 家 business
齐全 rating/cost/tag/keytag/rectag/opentime_today/opentime_week/business_area；1 家『示例快餐店』缺
`rating`；1 家『示例火锅店』只给 rating/cost/tag/keytag=火锅，不进「齐全」那 4 家避免与「1 家 keytag
为火锅」重复计数），request 用 `sortrule: "weight"`。`/usr/bin/python3 scripts/build_provider_fixtures.py`
重生成后 `manifest.json` 的 `fixture_count` 88→89，`tests/test_providers.py:118` 的断言同步改 89。新增
`AroundDiningFixtureTests`（3 个用例：夹具记录的请求确实用了 `sortrule=weight`；raw `distance` 不是升
序；回放 6 项且 4 条 `/business` claim 齐全 8 键、1 条缺 `rating`、1 条 `keytag=="火锅"`），类文档字符
串明确写明 `distance_meters` 未测、指向 BLOCKED.md。`around_stations.json`/`station_distance.py` 相对
main 零改动（`git diff main -- 两文件` 为空）。最终态：`/usr/bin/python3 -m unittest discover -s tests`
`Ran 763 tests`（759 + 1 条自动生成的 `test_fixture_amap_around_dining` + 3 条 `AroundDiningFixtureTests`）
`OK` 0 skipped；`scan_secrets` 0 finding(s) across 408 file(s)；pyflakes 0；`git status -- demo` 空。

checklist③（`around_stations` 带 `distance_meters=5883`、文本搜索夹具 `distance_meters` 为 None）**完全
未实现**：它不像②那样有「不依赖 schema 的部分」可拆出来——`around_stations` 是既有夹具，这条验收唯一
要做的事就是断言 `_pois()` 归一化后的 item 携带 `distance_meters`，而这正是被 schema 挡住的那部分代
码，没有独立于 `distance_meters` 键存在的东西可以先测。

供裁决的最小修复方向（详见 BLOCKED.md，已 `spawn_task` 提醒管理者）：给 `#/$defs/poi` 加一个**可选**
属性 `"distance_meters": {"type": ["integer", "null"]}`（不进 `required`）。这对现有全部夹具零影响——
`validate_trip.py` 的 `properties` 校验只在键存在于被测值里才递归（[validate_trip.py:167-169](plugins/china-trip-weaver/src/china_trip_weaver/validate_trip.py:167)），不存在的可选键不触发任何检查；
`required` 列表不变意味着没有该键的旧数据也仍然合法。

**裁决落地（2026-09-17，管理者通过 AskUserQuestion 当场选择「授权本书直接改 schema」）**：Stop hook 连
续三轮反馈都确认 checklist②③ 的 `distance_meters` 子项在结构上无法在不碰 schema 的前提下满足，
问了管理者后拿到明确授权，豁免本书界限里「不许碰 schema」这一条。落地：`trip.schema.json` 的
`#/$defs/poi.properties` 按上面的方案原样加了 `distance_meters`（不进 `required`，其余 9 个键逐字不
改）；`amap.py::_pois` 补回 `"distance_meters": int(raw["distance"]) if body.get("api") == "around-v5"
else None`；`AroundDiningFixtureTests` 补两个真断言（每项 `distance_meters` 为 int 且等于夹具
`distance`；第 5 项 business 无 `rating`）；新增 `DistanceMetersByApiTests`（`around_stations` 回放项
`distance_meters == 5883`；`success.json` 文本搜索回放项 `distance_meters is None`）。四条 checklist
全部转绿。三处反向验证红→绿：①（见上）；②③——`_pois` 的 `distance_meters` 临时改回硬编码 `None`
后 `test_each_item_carries_distance_meters_equal_to_fixture_distance`（`None is not an instance of
<class 'int'>`）与 `test_around_stations_item_carries_the_fixture_distance`（`5883 != None`）红，还原
后绿；单独删掉 schema 里那条 `distance_meters` 属性，`tests.test_providers` 从 120 全绿变回 6 项
`S_ADDITIONAL`（`around_dining`／`around_stations`／`boundary_hk`／`malicious`／`pagination_page2`／
`success`），还原后绿。最终态：`/usr/bin/python3 -m unittest discover -s tests` `Ran 767 tests OK`
0 skipped；`scan_secrets` 0 finding(s) across 408 file(s)；pyflakes 0；`git status -- demo` 空；
`around_stations.json`/`station_distance.py` 相对 main 仍零改动。`git diff main --name-only` 现含
`plugins/china-trip-weaver/schema/trip.schema.json`——这是管理者当场明确授权的唯一一处超出原始白名
单的改动，界限里其余文件（`render/`/`cli.py`/`planning.py`/`station_distance.py`）仍未碰。详见
BLOCKED.md「书 AP1a」的管理者裁决记录。

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
- 2026-09-17 的执行者逐轮记录（第二十九波到第三十二波：高德天气端到端、锁定车次两处缺陷、refresh 标题、
  天气折回库函数与 `ctw journey weather` 命令，对应 0.23.0、0.24.0）：
  [docs/history/progress-2026-09-17.md](docs/history/progress-2026-09-17.md)
  （2026-09-17 发 0.24.0 时从本文件整体迁出，一字未改，按合入顺序）。

## 第三十三波 AP1b 执行记录（2026-09-17，`dining-rules` 分支，worktree `.tmp/wt-ap1b`）

任务 0 核对：main `6378f80`（0.24.0）全量 `Ran 756 tests` OK 0 skipped；`test_design_docs.py` 写死 52；
`git grep -i -c dining -- plugins tests` 0 命中。三项与任务书基线一致，未见偏差。

理解的目标：把「附近餐饮参考」的选址/筛选/文案规则写成一个不碰网络、不 import cli/planning/providers 的
纯函数模块 `dining.py`，供命令、规划器、折回三个后续调用方共用；本书只交付模块与其自测，不接线。
顺序：先读 `weather_fold.py`/`weather.py` 定风格，再读 `contracts.py`/`evidence.py`/`providers/amap.py::_pois`
定数据形状（claim `/provider_identity` 的 `value.business`、归一化 item 的 `coordinates.gcj02`/`claim_ids`），
最后读 `docs/design/03-trip-model.md` 与 `trip.schema.json` 定 slot/poi/lodging 的 `kind`/`ref_id` 合同。
最大风险：`select_options` 怎么把一个 item 关联到「它的」`/provider_identity` claim 没有先例可抄——选了
`item["claim_ids"]` 成员匹配（比 `subject_ref == poi_id` 更贴合 amap.py 真实产出，不依赖 subject_ref 默认值
这一隐藏假设）。另一个风险是 `search_url`/marker 深链里「美食」「china-trip-weaver」等字面文本会被
`urllib.parse.urlencode` 整体转义、破坏任务书给的逐字格式串——改成只对 `name` 这一项单独 `urllib.parse.quote`，
其余按字面拼接，`search_url` 含 `keyword=美食` 的验收因此能过。

任务 1 完成：新增 `plugins/china-trip-weaver/src/china_trip_weaver/dining.py`（8 个公开函数：
`meal_type_for`/`meal_slots`/`anchor_for`/`query_parameters`/`select_options`/`option_from`/`search_url`/
`format_option`，只 import stdlib）与 `tests/test_dining.py`（13 例，覆盖任务书①-④四组验收）；
`tests/test_design_docs.py` 52→53，`docs/design/09-impl-map.md` 登记 `dining.py`（树与表各一处）。

验收证据（实际命令输出，2026-09-17）：
- `python3 -m unittest tests.test_dining -v` → `Ran 13 tests ... OK`（13 例名单见测试文件，覆盖 demo 首日
  两餐分类、free 标题两例、meal 无字样按小时兜底、anchor_for 三例、select_options 三例、format_option/
  search_url 三例）。
- 反向验证：把 `select_options` 里 `if not business.get("rating"): continue` 两行注释掉，
  `python3 -m unittest tests.test_dining.SelectOptionsTests -v` → `FAILED (failures=3)`（`无评分小馆`
  混进结果、`provider_poi_id` 断言错位）；还原并 `touch dining.py` 后重跑同组 → `OK`。
- `python3 -m unittest discover -s tests -v` → `Ran 769 tests ... OK`（756 基线 + 13 新增，0 skipped）。
- `pyflakes $(git ls-files '*.py')` → 0 行输出。
- `python3 scripts/scan_secrets.py` → `secret scan: 0 finding(s) across 409 file(s)`。
- `git status --porcelain -- demo` → 空。
- `git diff main --name-only` + 未跟踪文件 → 仅 `docs/design/09-impl-map.md`、`tests/test_design_docs.py`
  （改动）与 `plugins/china-trip-weaver/src/china_trip_weaver/dining.py`、`tests/test_dining.py`（新建），
  与任务书「界限」白名单一致。

未使用 `contracts.py`/`evidence.py`：任务书写的是「只 import stdlib 与 contracts/evidence」这一允许清单，
不是强制项——`dining.py` 的八个函数都只读调用方已经造好的 claim/item 字典，不需要 `make_claim` 造新证据，
也不需要 `canonical_json` 序列化，所以最终只 import 了 stdlib（`urllib.parse`、`datetime`、`typing`），更省。
未合并到 main，只推送 `dining-rules` 分支等待管理者合并。
## AP2 附近餐饮参考渲染与校验（2026-09-17，第三十三波，worktree `.tmp/wt-ap2` 分支 `slot-dining-render`，进行中）

任务 0 已核对：main `6378f80`，全量 `Ran 756 tests` OK、0 skipped；`git grep -i -c dining -- plugins tests` 0 命中；
slot 的 `additionalProperties` 是 false、`kind` 枚举含 `meal`。README demo 命令与 `build_renderer_fixtures.py`
重跑后 `git status --short` 为空。

理解的目标／顺序／最大风险（≤10 行）：

- 目标：`slot.dining`（`diningReference`/`diningOption` 两个新 `$defs`）进 schema；两页每个带 `dining` 键的
  时段渲染一块「附近餐饮参考」；两个校验器逐字核对页面与 Trip 数据一致，不符报 E007/JH007。数据从哪来是
  AP1a/AP1b 的事，本书只管形状、显示与校验，和天气行（AN2/E006/JH006）同一套路。
- 顺序：任务 1 schema+夹具在先（`meal` 时段的 `ref_id` 必须落在 `poi_map` 里，`_check_day_slots` 逐字硬性要求，
  夹具要先想清楚再落笔）→ 任务 2 渲染函数+校验规则+文档在后。
- 风险①：`_render_day_slots` 被 Trip 页与 Journey 页共用，但两页的 `labels` 字典来自各自独立的
  `_labels`/`_journey_labels`（两份互不派生的字面量字典）；本书白名单只有 `render/html.py`，不含
  `render/journey_html.py`。若把新标签塞进 `_labels()` 返回值（如天气行的做法），Journey 页调用
  `_render_day_slots` 时会因 `_journey_labels` 缺键而 `KeyError` 崩溃，且我不能去补那个字典。
- 风险②：`diningOption.deep_links` 若不加 `minItems:1`，渲染器 `deep_links[0]` 可能越界；`patch.trigger`
  加 `dining` 后，`validate_trip.py` 用 `SchemaSubsetValidator` 动态读 schema 的 `enum`，没有需要同步的
  硬编码副本（白名单里「仅同步 trigger 枚举」这条实测不需要动这个文件）。

### 任务 1 完成（schema + 夹具）

`$defs` 新增 `diningPreferences`（`cuisine: string|null`、`avoid: stringList`，两键都 required）、`diningOption`
（11 键全 required、`additionalProperties:false`，比对照的板子多加了 `deep_links` 的 `minItems:1`——渲染器要
无条件取 `deep_links[0]`，schema 兜底比渲染器里加防御式判空更对，原因见下）、`diningReference`（6 键全
required：`queried_at`/`anchor_ref`/`anchor_name`/`radius_m`/`search_url`/`options`，`options` 数组
`maxItems:3`）。`slot.dining` 是 `oneOf [$ref diningReference, null]`，不进 `slot` 的 `required`（比照
`day.weather`）。`request.dining_preferences` 是可选的 `$ref`。`patch.trigger` 枚举加 `"dining"`。三个新
`$defs` 放在 `lockedRailService` 和 `request` 之间（`request`/`slot` 都会引用它们，`$ref` 不依赖文本顺序，
放在被引用者之前只是可读性考虑）。

新增 valid 夹具 `dining-references.json`：2 天行程，day-1 一个 `poi` 锚点时段 + 一个 `meal` 时段（`ref_id`
指向新建的 `poi-lunch-spot`，`dining` 带 2 家 options——一家 11 键全非空，一家 `cuisine`/`tag`/`cost_cny`/
`opentime_today`/`address` 全 `null`，用来同时覆盖「缺项跳过」渲染分支），day-2 一个 `free` 时段
`dining: null`；`request.dining_preferences: {"cuisine": "闽菜", "avoid": ["动物内脏"]}`；`revision` 从 1 到
2 的一条 `trigger: "dining"` 的 `patch`（`op: "add"`，照抄 `weather_fold.py` 里「首次写入用 add、已有键才用
replace」的既有惯例）。2 个 `diningOption.claim_id` 各配一条真实 claim（`subject_ref` 指向 `slot-2`——
`_iter_claim_ids` 没有遍历 `diningOption.claim_id` 这条新路径，和 AN2 时 `weatherForecast.claim_id` 一样不被
交叉校验，但补真实 claim 更接近实际数据，成本很低）。新增 invalid 夹具 `dining-option-missing-rating.json`：
唯一缺陷是 options[0] 缺 `rating`。

**执行中发现并处置一个白名单相关的偏离**：`tests/test_contracts.py::test_accepted_examples_are_unchanged_in_test_fixtures`
把 valid/invalid 夹具数量硬编码成 3／4；书面白名单写的是「valid/invalid 各加一份」+ `test_contracts.py`
（都只加），但两者字面上打架——加了新夹具不改这两个数字，这条测试必然由 3/4 变成 4/5 而失败，且这个失败
与任何真实缺陷无关。参照 CLAUDE.md「验收教训」里同类先例（新增 `.py` 必须同步改 `test_design_docs.py`
的计数），把这两个数字改成 4／5，视为「新增夹具」这个被明确批准的动作的必然机械结果，不是放宽断言（等式
严格度不变，只是期望值随批准的新增而更新）。`git diff main --stat -- tests/test_contracts.py` 目前只有
这一处改动。

证据：
```
$ /usr/bin/python3 -m unittest tests.test_contracts -v 2>&1 | tail -3
Ran 20 tests in 1.620s
OK
$ /usr/bin/python3 -c "... validate_trip(dining-references.json) ..."
valid fixture ok: True
$ /usr/bin/python3 -c "... validate_trip(dining-option-missing-rating.json) ..."
invalid fixture ok (should be False): False
  S_ONE_OF /days/0/slots/0/dining must match exactly one allowed shape
$ /usr/bin/python3 -m unittest tests.test_renderer -v 2>&1 | tail -3
Ran 53 tests in 2.339s
OK
```
（`test_valid_examples_render_deterministically_with_zero_errors` 会自动把新 valid 夹具也渲染一遍并跑
`validate_html`；此时渲染器和校验器都还没认识 `dining` 键，新夹具照常渲染通过，证明任务 1 的 schema
改动是纯附加、没有动到既有路径。）

### 任务 2 完成（渲染 + 校验 + 文档）

`html.py` 新增模块级 `DINING_LABELS`（按 `locale` 查表，不折进 `_labels()`/`_journey_labels()`——原因见
下）与纯函数 `slot_dining_block(slot, labels)`：`"dining" not in slot` 时返回空字符串（旧时段一个字节不
多渲染）；`dining` 为 `null` 渲染 `<div class="slot-dining" data-dining-slot="slot_id"><p
class="dining-none">附近餐饮参考：暂无</p></div>`；否则渲染标题行「附近餐饮参考（高德综合排序 · 距<锚点>
≤<半径/1000，1 位小数> km）」+ 每家一条 `<li class="dining-option" data-poi-id data-rating data-cost
data-distance>` （名·菜系·评分·人均·距离·今日营业时间，缺项按 `if` 跳过整段，不留空分隔符）+ 高德深链
+ 结尾一条「在高德 App 看附近美食」搜索深链。`_render_day_slots` 每个 `<li>` 末尾多插一个 `%s` 调它，
Trip 页与 Journey 页的 `days`/`day-timeline` 两个 section 因为共用这一个函数而同时获得渲染，零改动
`journey_html.py`。

**执行中发现并处置一个真实碰撞（非裁决分叉，写法收窄）**：任务书模板字面写 `data-slot-id="…"`，但这个
属性名在 `validate_html.py::AuditParser`/`_check_rendered_facts`（E003）里已经被占用，专门标记 `<li>`
时段节点、并核对其 `start_at`/`end_at`/`kind`/`status`。照抄会让渲染出的 `<div>` 被同一套通用逻辑误认成
「又一个同 id 的时段节点」，因为它没有那些属性字段而立刻触发 E003（渲染出的 slot-2/slot-3 各计数两次、
且缺失字段判定为「与 Trip 不符」）。改用 `data-dining-slot` 承载同样的「指回哪个 slot」语义，问题消失。
另发现既有 E003 的「已知 CNY 价格」集合只收 `transport_legs`/`lodgings`/`pois` 的 `price.amount`，会把
页面上真实存在的「人均 ¥32」误判成臆造事实；把 `slot.dining.options[].cost_cny` 并入 `known_prices`
后消失（`render/validate_html.py::_check_rendered_facts`，07-renderer.md §7.1 的 E003 条目已补一句）。

`validate_html.py` 新增 `_check_dining_blocks(html_text, days, code, add)`（照抄 `_check_weather_blocks`
的正则抠块思路：`DINING_BLOCK_RE` 抠出每个 `.slot-dining` 块与其 `data-dining-slot`，块数与「带 `dining`
键的 slot 数」核对；`dining=null` 的块核对含「暂无」文案；有 options 的块用 `DINING_OPTION_RE` 逐条抠出
`data-poi-id`/`data-rating`/`data-cost`/`data-distance` 与可见文本首段（名），与 `slot.dining.options[]`
逐字比对），`_check_slot_dining` 包一层传入 `"E007"`。`validate_journey_html.py` 直接从 `.validate_html`
导入 `_check_dining_blocks` 复用同一份逻辑，摊平 `[day for trip in journey["trips"] for day in
trip["days"]]` 后传入 `"JH007"`，零改动共用函数本身。

验收证据（①②③④）：
```
$ /usr/bin/python3 -c "render dining-references.json -> validate_html"
ok: True []
$ /usr/bin/python3 -c "... .count('class=\"slot-dining\"') ..."
2   # 1 家带 2 options、1 家 dining:null
$ grep -o 'uri.amap.com/marker[^"]*' rendered.html | head -1   # 命中
$ grep -c '在高德 App 看附近美食' rendered.html               # 1
② 篡改评分 4.7→4.9：validate_html -> ['E007 slot-dining option facts differ from Trip: slot-2']
   删除一整块 <div class="slot-dining">…</div>：validate_html -> ['E007 slot-dining block count differs from source slots']
③ 同一 Trip 经 assemble_journey_from_trips 装进 Journey：
   render_journey(journey) 含 2 个 slot-dining、1 个 dining-none；validate_journey_html -> ok: True []
   篡改评分：validate_journey_html -> ['JH007 slot-dining option facts differ from Trip: slot-2']
④ /usr/bin/python3 scripts/build_renderer_fixtures.py   # journey_sha256/html_sha256 与开工基线一致
   ctw plan（demo/trip.json+html 全部参数）重新生成后 git status --short 不含 demo/ 任何一行
   全量 tests.test_keyless_e2e / tests.test_journey 里绑定其余三个 demo 目录字节相等的用例照常 OK
```

反向验证（红→绿）：临时注释掉 `_check_dining_blocks` 里 `or match.group("rating") != option["rating"]`
这一行逐字比对，重跑「把评分从 4.7 改成 4.9」场景：`validate_html` 从「命中 E007」变成 `ok: True []`
（检测失效，证明这行是必需的、不是摆设）；还原该行、`touch validate_html.py` 避开 CPython 秒级字节码
缓存后重跑，恢复「命中 E007」（绿，见下方证据块）。

`docs/design/03-trip-model.md` 在 `day.weather` 段后加一段讲 `slot.dining`/`diningOption`/
`request.dining_preferences` 的字段与「纯增量、不进 required」的形状规则，链到 07 §2/§7.1。
`docs/design/07-renderer.md` §2 第 7 条追加一句餐饮块的显示规则，§7.1 追加 E007 一条并给 E003 补一句
CNY 集合的联动说明。两篇里新写的每个标识符/字面串（`diningReference`/`diningOption`/
`dining_preferences`/`slot_dining_block`/`slot-dining`/`data-poi-id`/`data-rating`/`data-cost`/
`data-distance`/「附近餐饮参考：暂无」/「在高德 App 看附近美食」/`E007`/`JH007` 等）逐一 `git grep`
核对，全部在代码里命中。

收尾全量：
```
$ /usr/bin/python3 -m unittest discover -s tests 2>&1 | tail -3
Ran 761 tests in ~50s
OK
$ ~/miniconda3/envs/core/bin/python -m pyflakes $(git ls-files '*.py')   # 0 行
$ /usr/bin/python3 scripts/scan_secrets.py                              # 0 finding(s)
$ git diff main --name-only
PROGRESS.md docs/design/03-trip-model.md docs/design/07-renderer.md
plugins/china-trip-weaver/schema/trip.schema.json
plugins/china-trip-weaver/src/china_trip_weaver/render/html.py
plugins/china-trip-weaver/src/china_trip_weaver/render/validate_html.py
plugins/china-trip-weaver/src/china_trip_weaver/render/validate_journey_html.py
tests/test_contracts.py tests/test_journey.py tests/test_renderer.py
$ git ls-files --others --exclude-standard
tests/fixtures/trips/schema/invalid/dining-option-missing-rating.json
tests/fixtures/trips/schema/valid/dining-references.json
```
全部落在白名单内；未碰 `providers/`、`planning.py`、`cli.py`、`demo/`。三处非阻塞判断（`DINING_LABELS`
不进 `_labels()`、`data-dining-slot` 改名、`test_contracts.py` 两个计数）与一处联动（E003 的
`known_prices`）已记入 BLOCKED.md 供管理者核对，均非产品语义裁决。
## 书 AP3「健康行去重与探针三能力」（2026-09-17，第三十三波，worktree `.tmp/wt-ap3` 分支 `fold-health-probe`）

任务 0 核对：main `6378f80` 全量 756 项 OK。新增
`test_health_reason_keeps_only_one_weather_fold_note_after_two_folds`（对 demo/journey-16d
第一个 Trip 折两次不同 `reported_at` 的 10-01 预报），现状确认红：amap 健康行 reason 里
`days folded` 出现 2 次（期望 1 次）。核对通过，动工。

目标：①`_fold_amap_health` 追加新段前正则删掉 reason 里所有既有同类段，其余文字一字不动；
②`_probe_amap` 从只探 `poi` 一项改为共用一个 `AMapCallBudget(max_calls=4)` 顺序探
`poi`/`weather`/`poi_around` 三项，行里新增 `capabilities` 三键，`business` 取三者最差、
`contract`/`network` 取三者中第一个非 passed。

顺序：先任务 1（纯字符串处理，风险小）转绿并跑存量 weather_fold/journey_weather_cli 测试；
再任务 2（新建 test_doctor_probe.py，脚本传输层按 capability 回放 success/weather/around_stations
fixture body）；两项都绿后跑全量 + 反向验证 + pyflakes + scan_secrets，最后实网
`ctw doctor --probe` 贴 amap 行。

最大风险：`_probe_amap` 外部签名（4 个位置参数）不能变，因为调用方 `_doctor_probe_report`
不在改动白名单内；三个子请求任一抛异常都要吞住记 `business=failed`，不能让并发探针整体崩。

**任务 1 完成**：`_fold_amap_health` 追加新段前，先用 `re.sub(r"; weather=\d+ days folded
\([^)]*\)", "", updated["reason"])` 删掉既有同类段（其余文字含规划器写的
`; weather=<n> queried, <m> unknown` 逐字不动），再接新段。任务 0 那条测试转绿，
`reason` 里的 `(…)` 确认是第二次的 `queried_at`；`test_weather_fold`（8 项）与
`test_journey_weather_cli`（4 项）全绿。反向验证：把正则那行还原成直接拼接
（`base_reason = updated["reason"]`），任务 0 那条测试红（`1 != 2`）；`cp` 回备份 +
`touch` 后复跑绿（8 项 `test_weather_fold` 全绿）。

**任务 2 完成**：`_probe_amap` 改为构造一个共用的 `AMapHTTPTransport(credentials,
budget=AMapCallBudget(max_calls=4))`，顺序调新帮手 `_probe_amap_capability`（新建，
每次单独 try/except 包住 `AMapAdapter().query(...)`，异常记
`{business:"failed", contract:"failed", network:"failed"}` 不外抛）三次
（`poi`/`weather`/`poi_around`，`poi` 参数与原来的天安门查询逐字不变），再用新帮手
`_combine_amap_capability_layers` 汇总：`capabilities` 三键各取该请求的 `business`；
行的 `business` 取三者最差（`business_rank` passed<not_run<degraded<failed）；
`contract`/`network` 取三者中第一个非 passed，否则 passed。新建
`tests/test_doctor_probe.py`（4 项，`ScriptedCapabilityTransport` 用
`mock.patch.object(AMapHTTPTransport, "execute", ...)` 按 capability 回放
`success.json`/`weather.json`/`weather_empty.json`/`around_stations.json` 的
`transport.body`）：①三个都成功→`capabilities` 三项 passed、`business`/`contract`/
`network` 全 passed、行仍含四键+`capabilities`；②`weather_empty.json`→`weather`
degraded、`business` degraded、其余 passed；③`poi_around` 抛 `RuntimeError`→
`poi_around` failed、`business` failed、探针不崩（另两项仍 passed）；④凭据缺失→
原样 `_not_run_probe`（不含 `capabilities` 键）。四项全绿。反向验证：把汇总函数的
`business` 改成直接取 `capability_layers["poi"]["business"]`（去掉最差判断），
②③两项都转红（②`degraded != passed`、③`failed != passed`，符合预期——两者的
异常/降级都不在 `poi` 上）；`cp` 回备份 + `touch` 后复跑，`test_doctor_probe`
（4 项）与 `test_credentials`（22 项，含逐字未改的
`test_doctor_probe_reports_credential_contract_network_and_business_only` 等）全绿。

**验收结果**：全量 `Ran 761 tests`（756 + 1 + 4）OK、0 skipped；四个假 Key
（`AMAP_WEBSERVICE_KEY`/`FLYAI_API_KEY`/`VARIFLIGHT_API_KEY`/`ANYSEARCH_API_KEY`
全设 `ctw-canary-fake-*`）复跑全量同样 761 OK；`pyflakes $(git ls-files '*.py')`
0 行；`scripts/scan_secrets.py` 0 finding / 408 file；`git status --porcelain --
demo` 空。实网 `plugins/china-trip-weaver/scripts/ctw doctor --probe` 的 amap 行：
`{"business":"passed","capabilities":{"poi":"passed","poi_around":"passed",
"weather":"passed"},"contract":"passed","credential":"configured",
"network":"passed"}`——三项能力全部 passed。`git diff main --name-only` 只有
`PROGRESS.md`/`cli.py`/`weather_fold.py`/`tests/test_weather_fold.py`（纯新增）+
新建 `tests/test_doctor_probe.py`，均在白名单内；`test_credentials.py` 逐字未改。
BLOCKED.md：无裁决分叉，全程未遇到需要管理者裁决的真实二义性。
## 书 AP4「产物目录约定文档」（2026-09-17，第三十三波五本并行之一，worktree `.tmp/wt-ap4` 分支 `plans-dir-docs`）：无裁决分叉，只改文案

**任务 0 核对记录**：`git worktree add .tmp/wt-ap4 -b plans-dir-docs main` 后核对与任务书一致——`/usr/bin/python3 -m unittest discover -s tests` `Ran 756 tests ... OK`（0 skipped）；`git grep -c "plans/" -- plugins/china-trip-weaver/skills README.md README.zh-CN.md docs/design/02-plugin-skills.md` 0 命中（exit 1，无匹配行）。目标：把领导 2026-09-17 拍板的「行程文件放 `<调用方项目根>/plans/<可读名称>/`」约定写进三份 SKILL 正文与两份 README、`docs/design/02-plugin-skills.md` §4，命令示例里的裸文件名统一加 `plans/<name>/` 前缀。顺序：先改三份 SKILL（任务 1，含新增「Where a plan lives」一节），再改 README/设计文档（任务 2），每步做完就跑对应 `git grep`/diff 验收。最大风险：README.md 与 README.zh-CN.md 用 `grep -c` 按「命中行数」而不是「出现次数」比对，若中英文各写成不同行数的段落会导致两侧计数不等——按每份都写成单一长段落（与仓库现有段落风格一致）规避。

**任务 1（三份 SKILL）完成**：`plan-china-trip/SKILL.md` 在「## Workflow」与「## Command flow」之间新增「## Where a plan lives」一节，并把 Command flow 代码块与其后一句 replan 示例里的 `candidates.json`/`request.json`/`trip.json`/`trip.html`/`long-request.json`/`journey.json`/`journey.html`/`event.json`/`trip-r<N+1>.json`/`trip-r<N+1>.html` 全部加上 `plans/<name>/` 前缀；`../../references/*` 三个插件自身参考文档路径不属于「每趟行程的文件」，未改。`replan-china-trip/SKILL.md`、`resolve-china-mobility/SKILL.md` 未加新标题，只把两份文件三个代码块里的 `trip.json`/`event.json`/`trip-r2.json`/`trip-r2.html`/`rail-result.json`/`refresh-event.json`/`suspend-event.json`/`candidates.json`/`mobility.json`/`request.json`/`weather.json`/`journey.json`/`journey-r2.json` 同样加前缀，各补一句「Files for one trip live together under `plans/<name>/`…」。取「路径统一」优先于「少改」：凡是命令示例里出现的、随一趟行程产生的文件路径全部加前缀，不止任务书举例的几个文件名；`weather-<date>.json`/`dining-<date>.json` 目前无 Skill 正文直接给出这两个具体命令示例，只在新增段落的行文里提到作为约定范围的一部分。验收：`/usr/bin/python3 -m unittest tests.test_skills -v` 11 项全绿（含本机真实跑的 `test_all_skills_pass_bundled_validator`、`test_codex_skill_parser_smoke_runs_standalone`，未跳过）；`git grep -n "plans/" -- plugins/china-trip-weaver/skills` 三个文件均命中；`git diff main -- plugins/china-trip-weaver/skills | grep -c -E "^\+.*(/Users/|0\.2[0-9]\.[0-9])"` = 0；三份 frontmatter 的 `git diff main -U0 -- <文件> | grep -E "^[-+](name|description):"` 均无输出。

**任务 2（README 与设计文档）完成**：README.md 在「## Install from the local marketplace」与「## Candidate input」之间插入「## Where a plan lives」单段；README.zh-CN.md 在对应位置插入「## 行程文件放哪」单段，两段各写成一整行，内容互译、文件列举顺序一致。`docs/design/02-plugin-skills.md` §4 表格与其后原有说明段之后追加一段「领导裁决补充（2026-09-17）：…」，说明表格「输入」列列出的文件不再假定散落当前目录，并点名受影响的三个 Skill 与两份 README。frontmatter 未涉及（该文档无 YAML frontmatter）。验收：`diff <(grep -c "plans/" README.md) <(grep -c "plans/" README.zh-CN.md)` 输出为空（两份都恰好 1 行命中）；`docs/design/02-plugin-skills.md` 第 147 行命中 `plans/`；`git diff main -- README.md README.zh-CN.md docs/design/02-plugin-skills.md | grep -E "^\+" | grep -E "(/Users/|0\.2[0-9]\.[0-9])"` 无输出；`/usr/bin/python3 -m unittest discover -s tests` 二次全量复跑仍 `Ran 756 tests ... OK`。

**收尾核对**：`/usr/bin/python3 scripts/scan_secrets.py` → `secret scan: 0 finding(s)`；`git status --porcelain -- demo` 空；`git diff main --name-only` 恰好等于界限白名单里允许改动的六个文件（三份 SKILL + 两份 README + 02 设计文档）加本文件与 `BLOCKED.md`。未碰任何 `.py`、schema、demo、夹具或其它 Skill。BLOCKED.md 本书追加「无」。只提交并 push 分支 `plans-dir-docs`，未合并 main。
## 书 AP5a「`ctw dining` 命令」（2026-09-17，第三十四波四本并行之一，worktree `.tmp/wt-ap5a` 分支 `dining-cli`）：任务 0 核对记录与动工前理解

**任务 0 核对**：`git worktree add .tmp/wt-ap5a -b dining-cli main` 后核对与任务书一致——`/usr/bin/python3 -m unittest discover -s tests` `Ran 790 tests ... OK`（0 skipped）；`git grep -c -E "_cmd_dining|DINING_COMPLETE" -- plugins tests` 0 命中（exit 1）；`scan_secrets` 0、pyflakes 0。

**理解的目标**：实现只读命令 `ctw dining`，对一份 Journey/Trip 的每个午/晚餐时段查高德 `poi_around`，产出结果信封；折回 journey 是另一本书（AP5b）不归本书管。

**顺序**：①先改 `dining.py::meal_type_for`，让 `rest` 与 `free` 同规则——真实行程有 3 个「午餐与完整午休」类 `rest` 时段，不然漏计（用旧规则实测真实 journey 只数出 19 个用餐时段，加 `rest` 规则后变 22，与任务书验收数字吻合，已验证）；②再在 cli.py 加 `_add_dining_parser`+`_cmd_dining`，仿 `_cmd_weather` 的结构：逐 Trip 读 `request.dining_preferences`（CLI 参数逐字段覆盖）、对每个 meal slot 找 anchor、按 (location, keywords) 去重后查 `poi_around`、`select_options` 筛选、拼 JSON 信封或文本行。

**最大风险**：demo 第一个 Trip 只有 1 处住宿，给它贴坐标后，day0 的午餐（slot 1）与晚餐（slot 5）会通过 `anchor_for` 的双向搜索找到同一个 checkin 时段坐标（已用真实数据验证），必须让「同一坐标＋关键词只查一次」的缓存生效，否则 `ReplayTransport.calls` 会变 2 次——这正是任务书要求的反向验证断言点，实现时缓存键要建在实际发起查询之前。

**任务 1 完成**：`dining.py::meal_type_for` 把 `if kind == "free":` 改成 `if kind in ("free", "rest"):`，docstring 同步更新；diff 只有这一处判断加一段 docstring 用词，未碰其它函数。`tests/test_dining.py` 加两条：`test_rest_slot_with_lunch_wording_classifies_as_lunch`（kind `rest`、标题「午餐与完整午休」→`lunch`）、`test_rest_slot_without_meal_wording_is_none`（标题「午休」的 `rest`→`None`）；`/usr/bin/python3 -m unittest tests.test_dining -v` 15 项全绿（含新增 2 项与既有 13 项，一字未改）。用真实 journey 验证过这处修复的必要性：旧规则下 `dining.meal_slots` 数真实 16 天行程只数出 19 个用餐时段，三个「午餐与完整午休」「午餐与休息」×2 的 `rest` 时段被漏计；改完后变 22，与任务书验收数字（`slots=22`）吻合。

**任务 2 完成**：cli.py 加 `_add_dining_parser`（`--journey`/`--trip` 互斥必填组，`--radius`/`--limit`/`--cuisine`/`--avoid`/`--deadline`/`--fixture`/`--fixed-clock`/`--output-json`，另按同类命令惯例加了 `--progress`）+ `_cmd_dining`（结构仿 `_cmd_weather`：先按 Trip 读 `request.dining_preferences` 并用 CLI 参数逐字段覆盖、收集每个 meal slot 的 `anchor_for` 结果为 target 列表；再按 `(location, keywords)` 去重建查询参数表，只在有去重后的查询时才 `resolve_credentials`；`--fixture` 走 `ReplayTransport` 回放，实网走 `AMapHTTPTransport`+`AMapCallBudget(max_calls=80)`；每个唯一查询的 `claims`/`warnings` 只累加一次，避免共享同一 anchor 的多个时段把 claims 数出重复——开发中先犯过这个错，见下）+ `_parser()`/`main()` 各一行注册与分派。信封字段按任务书拍板的形状（`radius_m`/`keywords`/`search_url` 三个「查询会用到的参数」在 `no_anchor`（没发起查询）时置 `null`，理由已写入 BLOCKED.md）。

**踩坑记录**：第一版实现把 `all_claims.extend(result.claims)` 放在「逐时段建行」的循环里，而不是「逐唯一查询」的循环里；由于 day0 午餐/晚餐共享同一 anchor 只查一次，但两个时段都会引用同一个 `result` 对象，claims 被累加了两次（6 家 fixture POI ×2 claim = 12，误算成 24）。用测试①的 `self.assertEqual(12, len(data["claims"]))` 断言抓到，改为只在「触发唯一查询」那次 `adapter.query(...)` 之后立即 extend 一次即修复。

**测试与验收**：新建 `tests/test_dining_cli.py`（5 项，子进程为主）：①`test_anchored_slots_return_three_rated_options_with_int_distance_and_matching_claims`——给 demo 第一个 Trip 的住宿贴坐标、`--fixture tests/fixtures/providers/amap/around_dining.json --fixed-clock 2026-09-04T00:00:00+08:00 --output-json`：退出 0、2 个有锚点的时段均 `status=options` 且 3 家、`distance_m` 为 `int`、每个 option 的 `claim_id` 都能在信封 `claims` 里找到、`claims` 总数 12（去重生效的直接证据）；②`test_avoid_word_excludes_matching_restaurant_from_every_anchored_slot`——加 `--avoid 火锅` 后两个时段的 options 都不含「火锅」（连 `tag` 字段里带「火锅」二字的那一家也被过滤掉，不只是名字里带的）；③`test_journey_without_coordinates_reports_no_anchor_and_exits_two`——对未改动的 demo journey（32 个用餐时段）跑，文本模式与 JSON 模式都退出 2、全部 `no_anchor`、`with_options=0`；④`test_text_mode_prints_one_line_per_slot_with_arrow_marker`——不带 `--output-json` 时行数等于 `dining.meal_slots(trip)` 的时段数，有锚点的行都含「←」；⑤`test_shared_anchor_dedupes_the_amap_query_to_one_call`——进程内调用 `cli.main([...])`，用 `mock.patch.object(providers_base.ReplayTransport, "execute", counting_execute)` 包一层调用计数，断言只发生 1 次 `ReplayTransport.execute`（是任务书要求的「反向验证」信号本身，做成了永久回归测试而非一次性验证，多写这一条测试判断为「建议」而非违反白名单，因为它落在允许新建的 `tests/test_dining_cli.py` 里）。反向验证：把 `unique_parameters` 的 key 从 `(location, keywords)` 改成 `(location, keywords, 序号)`（等于关闭去重），`test_dining_cli` 里两项转红——claims 断言 `12 != 24`、调用计数断言 `1 != 2`；`diff` 确认改回后文件与备份逐字节相同、`touch` 后复跑 5 项全绿。

全量 `/usr/bin/python3 -m unittest discover -s tests` → `Ran 797 tests`（790+2+5）OK、0 skipped；四个假 Key（`AMAP_WEBSERVICE_KEY`/`FLYAI_API_KEY`/`VARIFLIGHT_API_KEY`/`ANYSEARCH_API_KEY` 全设 `ctw-canary-fake-*`）复跑全量同样 797 OK（`_cmd_dining` 新增了一处 `resolve_credentials` 调用点，按验收教训必须带假 Key 复跑）；`pyflakes $(git ls-files '*.py')` 0 行；`scripts/scan_secrets.py` 0 finding / 415 file；`git status --porcelain -- demo` 空。

**实网抽查**（凭据已配置，`ctw doctor` 显示 amap configured）：`ctw dining --journey ../../../fujian-2026-09-25-to-10-10/journey.json --output-json .tmp/dining-real.json` → 退出 0、`DINING_COMPLETE output=.tmp/dining-real.json slots=22 with_options=19`；状态分布 `options=19 no_results=2 no_anchor=1`；9/25 晚餐那一行确认是 `no_anchor`（行程第一天到达日，还没有可用坐标的锚点）；`claims` 340 条、`warnings=["no_results"]`、`error_class=None`。`.tmp/dining-real.json` 未提交（`.gitignore` 第 1 行 `.tmp/*` 挡住）；真实 journey 目录 `fujian-2026-09-25-to-10-10/` 下用 `shasum` 核对未新增/未修改任何文件。

`git diff main --name-only` = `PROGRESS.md`、`plugins/china-trip-weaver/src/china_trip_weaver/cli.py`、`plugins/china-trip-weaver/src/china_trip_weaver/dining.py`、`tests/test_dining.py`（`git status --porcelain` 另有新建 `tests/test_dining_cli.py`、`BLOCKED.md`），逐一核对均在界限白名单内；dining.py diff 只有 `meal_type_for` 一处判断+docstring；cli.py diff 只新增 `_add_dining_parser`/`_cmd_dining` 两个函数与 `_parser()`/`main()` 各一行。BLOCKED.md 本书追加「无」（唯一一处需要说明的判断——`no_anchor` 时三个查询参数字段置 `null`——写清了理由，不算需要管理者裁决的二义性）。只提交并 push 分支 `dining-cli`，未合并 main。

## 书 AP5b「dining 结果折回 Journey」（2026-09-18，第三十四波四本并行之一，worktree `.tmp/wt-ap5b` 分支 `dining-fold`）

**任务 0 核对记录**：从 `main`（`d11f469`）新建 worktree/分支后，全量 `Ran 790 tests in 48.980s`、`OK`、0 skipped；`tests/test_design_docs.py` 写死 53；`git grep -c -E "dining_fold|_cmd_journey_dining" -- plugins tests` exit 1 且无输出（0 命中）。目标：让 `ctw dining` 结果按 `trip_id + slot_id` 折回现役 Trip/Journey，并提供永不原地覆写的 `ctw journey dining`。顺序：先按 `weather_fold.py` 骨架实现折回库和六类验收，再接 CLI/设计映射和三类子进程验收，最后做反向验证、回归、全量、静态/秘密/白名单检查及提交推送。最大风险：替换 dining 时必须先删除旧 option claims 和旧 unknown，否则重复折回会泄漏陈旧证据或破坏幂等；以 claim 总数不变的替换测试和删代码后必红的反向验证锁住。

**任务 1 折回库完成**：新建 `dining_fold.py`，逐 Trip 以 `trip_id + slot_id` 匹配；`options` 复制 option 指向的 identity claim、改 `subject_ref` 为 slot_id 并写入完整 `slot.dining`，`no_anchor`/`no_results` 写 null 与 typed unknown，`provider_error`/缺行不动；变更前删除同路径旧 unknown 与旧 option claims；patch 固定 `trigger=dining`、精确 day/slot scope，AMap health 去旧 dining note 后追加本轮 note/capability；Journey 只调用一次 `replace_trips_in_journey(..., created_by="system")`。`/usr/bin/python3 -m unittest tests.test_dining_fold -v`：6 项、`Ran 6 tests in 0.244s`、OK，覆盖三选项折入与 HTML 0 errors、二折 None、换一家且 claims 总数不变、no_anchor unknown、缺 claim/revision 冲突、两 Trip 仅一次 Journey 升版。

**任务 2 命令与设计登记完成**：`cli.py` 只在 `_add_journey_parser` 增 `journey dining` 参数、`_cmd_journey` 增一行分派并新增 `_cmd_journey_dining`；成功/NOOP/异常分别输出 `JOURNEY_DINING_COMPLETE`/`NOOP`/`FAILED`，成功只写指定 OUT、永不回写 J。`tests.test_journey_dining_cli` 3 项 `Ran 3 tests in 0.826s`、OK，实际子进程覆盖 revision 2 + `journey validate` + render/`validate-html errors=0`、二折 exit 2 无文件、revision 7 exit 1。09-impl-map 树/表登记 `dining_fold.py` 与 `dining`/`journey dining`，design-doc 数量 53→54。合并 focused + 原 weather 回归：22 项、`Ran 22 tests in 1.992s`、OK。

**反向验证红→绿**：临时把 `fold_dining_into_trip` 的 `_remove_stale_claims(...)` 调用注释后，只跑替换用例，按预期红：`AssertionError: 17 != 20`、`FAILED (failures=1)`；立即还原调用并 `touch dining_fold.py`，同一用例 `Ran 1 test in 0.020s`、OK。证明换一家时 claims 总数不变的断言确实锁住删旧 claim 行为。

**收尾验收**：最终改动后 `/usr/bin/python3 -m unittest discover -s tests` → `Ran 799 tests in 50.431s`、OK、0 skipped（≥790+9）；`/Users/kangyishuai/miniconda3/bin/pyflakes $(git ls-files '*.py')` exit 0、0 行；`/usr/bin/python3 scripts/scan_secrets.py` → `secret scan: 0 finding(s) across 417 file(s)`；`git status --porcelain -- demo` 空。`git diff main --name-only`（暂存新文件后复核）只允许任务书白名单中的 8 个实现/测试/文档/记录文件；BLOCKED.md 本书追加「无」。只提交并 push `dining-fold`，不合并。
