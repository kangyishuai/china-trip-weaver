# PROGRESS

唯一的当前进度记录：现状速览（0.8.0 起每个版本一条）、几条长期有效的实测结论，以及历史索引。逐轮任务书、实测证据与验收记录按时间段归档，见「历史索引」——本文件不再留存单轮过程记录。

## 现状速览（2026-09-24，当前源码）

- 版本：`0.28.0`，源码版本由下列两处共同确定；正式发行以精确 git tag 与 GitHub Release 为准，本机安装状态以安装脚本 `--check` 为准。版本的唯一来源是
  `plugins/china-trip-weaver/.codex-plugin/plugin.json` 与
  `src/china_trip_weaver/__init__.py` 的 `__version__`，两处一致，仓库内其余
  代码与文档一律引用这两处之一；只有本节的逐版本条目和 git tag 以版本号作索引。
- 测试（0.27.0 当时测量）：仓库根 `/usr/bin/python3 -m unittest discover -s tests` 全量 `Ran 872 tests`，`OK`，0 skipped；
  `scripts/scan_secrets.py` 0 命中；
  `~/miniconda3/envs/core/bin/python -m pyflakes plugins/china-trip-weaver/src
  tests scripts` 0 行。带假 Key（`ANYSEARCH_API_KEY=... unittest`）跑全量同样
  872 OK，README 的 demo 与全部夹具重生成在有无 Key 两种环境下都零差异。0.21.0 记过的
  「环境变量注入会让 `test_credentials` 红一项」已在 0.22.0 修好：那个文件现在于 `setUp`
  里按 `FILE_ALLOWLIST` 剥掉凭据环境变量，四个 Key 全设与一个不设两种跑法结果相同。
- 覆盖率（0.27.0 当时测量）：`scripts/measure_coverage.py` 2026-09-18 发版前实测 12443 语句、miss 1347、**89%**（`contracts.py` 97%、`dining.py` 95%；0.26.0 时 12404/1344/89%，0.25.0 时 12005/1299/89%）。
- 0.28.0（2026-09-24）：**版本化 Trip/Journey 时间剖面**——现有 CLI 默认渲染 v2 单文件 HTML，将路线、优先决定、全程共同时间轴、当天安排和按主题归组的原始核验依据串成一条阅读路径；局部 +30 分钟交通试探可撤回，未知价格/服务仍按来源如实标注。完整 v1 事实正文、深链、条件署名和显式 v1 渲染/校验合同保留；固定资产摘要、CSP 与源 JSON 的规范化校验继续封闭。用户提供的限定合成 Trip 3 天/Journey 16 天中英屏幕与操作证据、中文 A4/Letter PDF 经独立核对，键盘焦点、无 JS 阅读、打印前后状态、时间条/刻度、完整来源和分页导航通过。本机逐方法选定 905/905 OK、0 skipped；四项真实浏览器测试未在本机执行，远端CI结果须按具体提交的Checks另行核对。真实触控、全部浏览器及自动网络/控制台探针未通测；不能把上版872项或89%冒充本版测量。
- 0.27.0（第三十七波两本并行，2026-09-18，逐本验收合入）：**行程文件改为默认原地更新**——领导改了版本规矩：
  重规划与各种折回默认在原文件上改（`--output-json` 就是 `--trip`/`--journey` 那个文件，页面原地重渲），只有
  新的一趟行程或用户明确要求另存时才写 `journey-r<N>.json` 之类新文件、旧文件不动。代码本来就允许同路径
  （旧版本号再跑报 `revision_conflict`、不写），这版补上**原子写入**：`write_canonical_json` 与新
  `write_text_atomic` 先写同目录临时文件再 `os.replace`，失败时删临时文件、原文件不动，命令行四处写页面都改走
  它；README 两份、plan/replan/mobility 三份 SKILL、02、06 §7.6–§7.8 全部改成原地约定（验收时管理者改正两处
  措辞：另存时是「旧文件不动」，`--output-json` 必填、没有默认值）。**晚餐以当晚住处兜底**：`dining.anchor_for`
  现有搜索找不到锚点时，晚餐、且之后当天没有 `transport`、且 `day.stay_id` 那家有坐标，就以当晚住处为圆心；
  午餐不兜底（午饭多在外面）。`ctw locate` 信封在没有 `provider_error` 行时 `health.status` 记 `ready`。
  现役行程已挪到调用方项目根的 `plans/福建中秋国庆16天/`，两份 `.gitignore` 挡住 `plans/`。验收：现役行程副本
  按新约定原地串跑补坐标（11→12）与餐饮（12→13）折回，旧版本号重跑被拒且字节不变，10/7 离岛后的晚餐锚到
  当晚住处、其余 21 个时段不变。测试 857→872。
- 0.26.0（第三十五波四本＋第三十六波两本并行，2026-09-18，逐本验收合入）：**给缺坐标的景点与住宿补坐标**——
  新命令 `ctw locate`：mobility.py 新增 `MobilityBackend.locate`（`resolve` 的前半段，只解析坐标、不查路线），
  新模块 `locate.py` 跳过用餐占位、住宿按 `#/$defs/lodging` 投影、只缺住宿的 Trip 借一个已定位景点凑候选文档
  （零调用、不进信封）、同一 `ref_id` 只查一次，信封每个实体一行 `located`/`unresolved`/`provider_error`，退出
  0/2/1；`ctw journey locate`（新模块 `locate_fold.py`）只给缺坐标的实体补坐标、已有坐标一个字节不动，
  `unresolved` 记成带原因的 unknown，每个被改的子 Trip 一个 `trigger=provider_change` 补丁、Journey 版本只加一，
  没变化打 `JOURNEY_LOCATE_NOOP` 退出 2 不写文件。**住宿与景点同一套名称核对**：`_resolve_entity` 不再让住宿
  跳过 `_resolve_poi_identity`，住宿按身份的完整地址编码，不再拿「城市+店名」直接编码（公开店名「7天酒店
  （上海人民广场店）」「如家酒店（上海南京东路步行街店）」原先都被编成上海市中心点）。**高德错误码按官方表
  归类**：2 开头与 3 开头为 `invalid_request`、10016/10017 为 `upstream_5xx`、限流码为 `rate_limited`，单条查询
  失败不再被当作致命的 `forbidden` 连累同段后面的实体；合成夹具 89→93。**餐饮锚点不越过换乘**：
  `dining.anchor_for` 两个方向遇到 `transport` 时段即停（验收查出；离岛后的晚餐锚在岛上、从土楼开回城的晚餐
  锚在土楼，这两类在 0.25.0 就有），ADR-0022 追加修订段。**健康行说真话**：`calls=<n>/<上限>` 改记整次规划
  对高德的真实调用数，含天气与餐饮查询（实网 12 = stderr 里 12 条 query 事件）。验收：现役 16 天行程副本实网
  9 家住宿定位 7 家、0 错点（改前 4 家里 2 家落错），18 次调用；折回副本 revision 10、validate-html 0、二折
  NOOP；重跑餐饮后换乘日午餐回到到达城市、两顿原本锚错城市的晚餐改记 `dining_no_anchor`；现役 journey.json
  哈希不变。测试 820→857，运行时+脚本 `.py` 54→56，design docs 56，ADR 22。
- 0.25.0（第三十三波五本＋第三十四波四本并行，2026-09-17 至 18，逐本验收合入）：**附近餐饮参考**——高德扫街榜
  没有开放接口（Web 服务、MCP、空间智能平台都没有榜单能力），改用高德周边搜索自己的综合排序，决定与理由见
  ADR-0022。适配器：`poi_around` 加 `sortrule`（`distance`/`weight`，缺省 `distance`，车站查询不变），归一化
  POI 项加 `distance_meters`（`#/$defs/poi` 加同名可选属性），合成夹具 88→89（`around_dining`）。新叶子模块
  `dining.py`：`meal_type_for`/`meal_slots`（kind `meal`，或 `free`/`rest` 且标题含「午餐」「晚餐」）、
  `anchor_for`（同一天先向前再向后找最近一个有坐标的景点或住宿时段，餐位占位 POI 不当锚点）、
  `query_parameters`（半径 1.5 km、types `050100|050200|050400`、`sortrule=weight`）、`select_options`（按高德
  顺序取前 3 家有评分的，`request.dining_preferences.avoid` 命中名称/tag/keytag/rectag 即跳过）、`option_from`、
  `search_url`、`format_option`。模型：`slot.dining`（`#/$defs/diningReference`，最多 3 个
  `#/$defs/diningOption`）、`request.dining_preferences`、patch trigger `dining`，`schema_version` 仍 1.0.0；
  两页的 `slot_dining_block` 只在带 `dining` 键的时段渲染，旧产物逐字节不变，E007/JH007 逐字回读，人均并入
  E003 已知价格集合。命令：`ctw dining`（每个用餐时段一行，同一锚点＋关键词只查一次，退出 0/2/1）与
  `ctw journey dining`（照天气折回：每个被改的子 Trip 一个 `trigger=dining` 补丁、Journey 版本只加一、没变化
  打 `JOURNEY_DINING_NOOP` 退出 2 不写文件；每个时段一份 claim 副本，编号由信封编号与 slot_id 派生——验收查出
  两餐共用一份结果时会重复编号，管理者修正）。规划器 `_plan_dining` 紧跟 `_plan_weather`，只在高德 live 时跑，
  健康行加 `poi_around` 与 `; dining=<n> queried, <m> unknown`（验收时补了两个脚本传输层对 `poi_around` 的应答，
  6 处写死的调用总数拆成「原调用数不变＋餐饮调用数」）。顺手：天气折回健康行 reason 不再逐次累积；
  `ctw doctor --probe` 的高德行分别探 poi/weather/poi_around 并给出 `capabilities`；三份 SKILL、README 两份与
  02 写明产物目录 `plans/<可读名称>/`。验收：现役 16 天行程实网 22 个用餐时段、19 个有参考、20 次查询，折回
  副本 revision 10、validate-html 0、二折 NOOP、现役 journey.json sha 不变。测试 756→820，运行时+脚本 `.py`
  52→54，ADR 21→22。
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

- **名称核对只比相对差**：`_poi_name_is_ambiguous` 只看第一、第二名相似度之差，高德没有目标分店时会把
  最像的别家分店当身份（2026-09-18 实测「7天酒店（上海人民广场店）」→上海大学店，相似度 0.70；正确匹配
  0.82–0.90，同楼邻居 0.76–0.79），这次靠后面的地址编码歧义才没落错点。样本太少，未加绝对阈值。
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
- 2026-09-17 至 18 的执行者逐轮记录（第三十三波到第三十七波：高德周边搜索综合排序、`dining.py`、
  `slot.dining` 与两页、天气折回健康行去重、`doctor --probe` 三能力、`plans/<可读名称>/` 约定、
  `ctw dining` 与 `ctw journey dining`、规划器 `_plan_dining`，对应 0.25.0；健康行真实调用数、
  `ctw locate` 与 `ctw journey locate`、住宿名称核对、高德错误码归类，对应 0.26.0；晚餐当晚住处兜底、
  原子写入与原地更新约定，对应 0.27.0）：
  [docs/history/progress-2026-09-18.md](docs/history/progress-2026-09-18.md)
  （分别在 2026-09-18 发 0.25.0、0.26.0、0.27.0 时从本文件整体迁出，一字未改，按合入顺序）。
