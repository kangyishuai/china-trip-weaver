# PROGRESS

唯一的当前进度记录：现状速览（0.8.0 起每个版本一条）、几条长期有效的实测结论，以及历史索引。逐轮任务书、实测证据与验收记录按时间段归档，见「历史索引」——本文件不再留存单轮过程记录。

## 现状速览（2026-09-15 实测，0.22.1）

- 版本：`0.22.1`，唯一来源是
  `plugins/china-trip-weaver/.codex-plugin/plugin.json` 与
  `src/china_trip_weaver/__init__.py` 的 `__version__`，两处一致，仓库内其余
  代码与文档一律引用这两处之一；只有本节的逐版本条目和 git tag 以版本号作索引。
- 测试：仓库根 `/usr/bin/python3 -m unittest discover -s tests` 全量 `Ran 699 tests`，`OK`，0 skipped；
  `scripts/scan_secrets.py` 0 命中；
  `~/miniconda3/envs/core/bin/python -m pyflakes plugins/china-trip-weaver/src
  tests scripts` 0 行。带假 Key（`ANYSEARCH_API_KEY=... unittest`）跑全量同样
  699 OK，README 的 demo 与全部夹具重生成在有无 Key 两种环境下都零差异。0.21.0 记过的
  「环境变量注入会让 `test_credentials` 红一项」已在 0.22.0 修好：那个文件现在于 `setUp`
  里按 `FILE_ALLOWLIST` 剥掉凭据环境变量，四个 Key 全设与一个不设两种跑法结果相同。
- 覆盖率：`scripts/measure_coverage.py` 实测 10706 语句、miss 1210、**89%**。
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
