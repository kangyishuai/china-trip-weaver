# PROGRESS

唯一的当前进度记录：现状速览（0.8.0 起每个版本一条）加最近一波的执行者记录。2026-09-03 到 09-06 与 2026-09-08 到 09-12 的逐轮任务书、实测证据、验收记录已归档，见「历史索引」。

## 现状速览（2026-09-12 实测，0.20.1）

- 版本：`0.20.1`，唯一来源是
  `plugins/china-trip-weaver/.codex-plugin/plugin.json` 与
  `src/china_trip_weaver/__init__.py` 的 `__version__`，两处一致，仓库内其余
  代码与文档一律引用这两处之一；只有本节的逐版本条目和 git tag 以版本号作索引。
- 测试：仓库根 `/usr/bin/python3 -m unittest discover -s tests` 全量 `Ran 685 tests`，`OK`，0 skipped；
  `scripts/scan_secrets.py` 0 命中；
  `~/miniconda3/envs/core/bin/python -m pyflakes plugins/china-trip-weaver/src
  tests scripts` 0 行。带假 Key（`ANYSEARCH_API_KEY=... unittest`）跑全量同样
  685 OK，README 的 demo 与全部夹具重生成在有无 Key 两种环境下都零差异。
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

## 书 AM1「0.16.0–0.20.0 设计文档追平」任务 0（2026-09-12，main@2983165，≤10 行）

1. 目标：只把代码已实现且可 `git grep` 取证的铁路、航班、汇合腿、replan、Journey 账本与实现地图行为追平到四份现役设计文档，并用一条文档覆盖测试锁住 48 个运行时/脚本文件。
2. 顺序：任务 0 基线核对并提交 → 任务 1 新测试先红并提交 → 任务 2 逐条取证后写文档、反向验证、全量验收并提交 → push 与 CI。
3. 不改代码、README、Skill、ADR、schema；只写任务书白名单文件，拿不准的写 `BLOCKED.md` 后跳过。
4. 每句新增行为先把代码中的函数名、常量、warning、错误码和数字命中记录在本文件；查不到的不写。
5. 最大风险：设计文案把多个层次的真实行为压成一句后夸大适用范围，尤其 12306 双端过滤、VariFlight 错误分档、汇合腿候选顺序和 replan claim 清理。
6. 基线：HEAD=`2983165`、branch=`main`、worktree clean；全量 `Ran 684 tests in 46.488s`、`OK`、0 skipped；secret scan `0 finding(s) across 386 file(s)`。
7. 静态门：`uvx --from pyflakes pyflakes plugins/china-trip-weaver/src scripts tests` exit 0、诊断 0 行；系统 Python未预装 pyflakes，故用机器已有 uvx 临时运行，未改仓库或系统 Python 环境。
8. 漂移复现：四份目标文档逐份执行 `git grep -c` 查 `_filter_direct_rows|getFlightPriceByCities|_validate_meeting_anchor|refresh_overlap|anysearch_http.py`，均 exit 1、输出为空；`git grep -l -- '/Users/' -- docs/design` 同为 exit 1、输出为空。
9. 文件数现状：运行时 `*.py` 42 个、`scripts/*.py` 6 个，合计 48；当前无待裁决项。

## 书 AM1 任务 1：先写红测试（2026-09-12）

新增 `tests/test_design_docs.py`，且只有一个 `def test_`：枚举 `plugins/china-trip-weaver/src/china_trip_weaver/**/*.py` 与 `scripts/*.py`，硬断言总数为 48，并逐文件检查 basename 出现在 `docs/design/09-impl-map.md`。改文档前实测 `Ran 1 test in 0.005s`、`FAILED (failures=1)`，失败输出恰列 7 个缺名：`anysearch_http.py`、`build_plan_fixtures.py`、`build_provider_fixtures.py`、`build_renderer_fixtures.py`、`build_scheduler_fixtures.py`、`qa_renderer_browser.py`、`scan_secrets.py`；生产代码与设计文档尚未改。

## 书 AM1 任务 2：写文档前的代码证据（2026-09-12）

以下均在改四份设计文档前用 `git grep -n` 命中；行号属于 HEAD `91786dd` 的只读代码/测试：

```text
planning.py:73:    limit: int = 30
cli.py:345:    rail.add_argument("--limit", type=int, default=30)
cli.py:1229:                "limited_num": args.limit,
mcp_stdio.py:391:                            ticket_arguments["limitedNum"] = limited_num
rail12306.py:29:NO_INVENTORY = frozenset(("", "*", "无", "--", "候补", "售罄", "not available"))
rail12306.py:104:            raw_tickets, row_warnings = _filter_direct_rows(payload, station_candidates, request)
rail12306.py:372:def _filter_direct_rows(
rail12306.py:398:        warnings += ("station_rows_filtered:%d" % dropped,)
rail12306.py:400:            warnings += ("station_rows_all_filtered",)
mcp_stdio.py:746:        city_payload = _call_station_tool(client, body, "get-station-code-of-citys", city_arguments)
mcp_stdio.py:756:            payload = _call_station_tool(client, body, "get-stations-code-in-city", {"city": city})
```

`CITY_IATA` 的 `git grep -n -A25 'CITY_IATA = {'` 从 `variflight_enrichment.py:18` 命中到 `:43`，中间 `:19`–`:42` 恰为 24 条城市→IATA 映射；其余航空证据：

```text
variflight.py:24:    "getFlightPriceByCities",
variflight.py:112:                raise ProviderFailure(_live_error_class(rows.get("error_code")), ...)
variflight.py:287:    def _live_price(
variflight.py:326:def _live_error_class(error_code: Any) -> str:
variflight.py:327:    if error_code == 10:
variflight.py:328:        return "no_results"
variflight.py:329:    if error_code == 12:
variflight.py:330:        return "invalid_request"
variflight.py:331:    return "upstream_5xx"
variflight_enrichment.py:46:PRICE_CONFLICT_MIN_DELTA = 20.0
variflight_enrichment.py:47:PRICE_CONFLICT_RATIO = 0.05
variflight_enrichment.py:230:            self._enrich_price(
variflight_enrichment.py:235:    def _enrich_price(
variflight_enrichment.py:422:    threshold = max(PRICE_CONFLICT_MIN_DELTA, abs(flyai_amount) * PRICE_CONFLICT_RATIO)
flyai.py:34:        if body.get("status") in (401, 403):
flyai.py:36:        if body.get("status") == 429:
flyai.py:38:        if body.get("status") == 1 and body.get("data") is None and isinstance(body.get("message"), str):
flyai.py:40:            if "结果为空" in message or "no result" in message.lower():
flyai.py:42:            raise ProviderFailure("upstream_5xx", sanitize_text(message, 40))
```

流水线、replan 与 Journey 证据：

```text
planning.py:211:    transport_legs, claims = _validate_meeting_anchor(
planning.py:1503:_MEETING_FLIGHT_LEG_PREFIX = "leg-meeting-flight"
planning.py:1552:def _promote_meeting_flight_leg(
planning.py:1561:        if _meeting_leg_is_compliant(flight, meet_by, required_buffer)
planning.py:1564:    chosen = min(candidates, key=lambda item: (item["arrive_at"], item.get("depart_at") or ""))
planning.py:1594:def _validate_meeting_anchor(
planning.py:1648:            "code": "MEETING_BUFFER_INSUFFICIENT",
replan.py:349:def _select_refresh_service(
replan.py:371:        feasible = [item for item in same_day if str(item["depart_at"]) >= earliest_depart]
replan.py:374:            "refresh_overlap",
replan.py:377:    return min(feasible, key=lambda item: (item["arrive_at"], item["depart_at"]))
replan.py:380:def _disambiguate_service_matches(
replan.py:389:    requested_depart_at = event.get("depart_at")
replan.py:394:    requested_arrive_at = event.get("arrive_at")
replan.py:412:        "refresh_service_ambiguous",
replan.py:290:    claim_remove_indexes = sorted(
replan.py:291:        (index for index, claim in enumerate(trip["claims"]) if claim.get("subject_ref") == leg["leg_id"]),
journey.py:1665:def _with_missing_budget_ledgers(
journey.py:1672:        if "budget_ledger" in trip:
journey.py:1676:        ledger, budget_unknowns = _budget_ledger(
journey.py:1712:    ordered_trips = _with_missing_budget_ledgers(ordered_trips)
```

7 份 replan 名称由 `tests/fixtures/scheduler/manifest.json:121`–`:145` 的 `git grep -n` 命中：`closure.json`、`delay.json`、`refresh.json`、`suspend-first-leg.json`、`suspend.json`、`user-delete.json`、`weather.json`；`:5` 为 `"replan": 7`。实现地图缺失文件的代码/测试命中包括 `cli.py:1287`/`:1708` 的 `.providers.anysearch_http`，四个 builder 各自 `generated_by` 行，`tests/test_journey.py:1669` 的 `qa_renderer_browser.py`，以及 `tests/test_credentials.py:284` 的 `scan_secrets.py`。当前仍无待裁决项，现可开始写文档。

补充记录动笔前已查看的相邻命中：`rail12306.py:374`/`:375` 的 `station_candidates`/`request`、`:377`–`:380` 的 `from_resolved`/`to_resolved` 与 `from_prefix`/`to_prefix`、`:383`/`:384` 的 `from_station`/`to_station`；`planning.py:1537` 的 `meet_by` 缓冲计算、`:1545`/`:1546` 的同 `from_ref`/`to_ref` 过滤、`:1606` 的 `buffer_minutes`；`replan.py:234` 的 `_apply_refresh`、`:290`–`:296` 的旧 subject claims 倒序删除；`anysearch_http.py:29` 的 `AnySearchHTTPTransport`、`:76` 的 `method: "tools/call"`。这些行与上方主体证据一样均在写文档前只读核过，补录是为了让新文案里的标识符都有显式索引。

## 书 AM1 任务 2：文档与验收进度（2026-09-12）

- 四份文档已追平：04 增加 12306 行过滤/限量/未开售与飞常准第二价源/错误分档/FlyAI 空信封；06 增加 §5.4 汇合腿并补全 refresh 默认选车、消歧和旧 claim 清理；08 将 replan golden 改为 7 并列全名；09 补 `anysearch_http.py`、6 个脚本及 Journey 缺账本补算。
- 文档覆盖测试转绿：`Ran 1 test in 0.002s ... OK`。反向验证时先暂存 09，临时删其唯一 `scan_secrets.py` 行后 `Ran 1 ... FAILED (failures=1)`，missing 只列 `['scan_secrets.py']`；按任务书 `git checkout -- docs/design/09-impl-map.md` 还原后 `Ran 1 ... OK`。
- 14 个验收名的 `git grep -c -- <名> -- docs/design/0\*.md` 全部 exit 0：04 中 `_filter_direct_rows=2`、`station_rows_filtered=1`、`getFlightPriceByCities=1`、`PRICE_CONFLICT_MIN_DELTA=1`、`_live_error_class=1`、`CITY_IATA=1`；06 中 `_validate_meeting_anchor=1`、`MEETING_BUFFER_INSUFFICIENT=1`、`refresh_overlap=1`、`refresh_service_ambiguous=1`、`depart_at=2`；09 中 `_with_missing_budget_ledgers=1`、`anysearch_http.py=2`、`qa_renderer_browser.py=1`。
- 完整验收第 1 轮：`Ran 685 tests in 59.507s ... OK`，0 skipped；secret scan `0 finding(s) across 387 file(s)`；pyflakes exit 0、诊断 0 行；`git grep -l -- '/Users/' -- docs/design` exit 1、输出为空；`git diff --check` exit 0。
- 范围检查：`git diff 2983165 --name-only` 只列 `PROGRESS.md`、四份目标设计文档和 `tests/test_design_docs.py`；运行时 42 + scripts 6 = 48；新测试文件恰一个 `def test_`。当前无待裁决项。
