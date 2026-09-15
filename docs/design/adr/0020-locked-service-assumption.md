# ADR-0020: How should an already-booked/locked transport service be expressed before initial planning?

- **Status:** Accepted
- **Date:** 2026-09-15

## Context

The 2026-09-15 health audit ran a real `journey plan` against the live real
Fujian 16-day request and hit:

```
JOURNEY_PLAN_FAILED HTML validation failed: E003 rendered train fact is absent from Trip: G1902
```

Root cause, verified directly against the real, uncommitted trip directory
(`fujian-2026-09-25-to-10-10/request.json`, outside this repository, per
`CLAUDE.md`'s directory table):

```
$ sed -n '119,126p' fujian-2026-09-25-to-10-10/request.json
  "assumptions": [
    "9月25日两组人在福州长乐国际机场于16点30分前会合",
    ...
    "G1902车票已购并锁定：9月26日07:50福州南站出发、09:30抵达武夷山北站；9月25日晚住宿改为福州南站片区"
  ],
```

`assumptions` is free text a human writes to record facts about the trip.
Item 7 (index 6) records that train G1902 is already bought and locked. There
is no field anywhere in `request.json` or `candidates.json` that a rail
selector can read to honor that fact — confirmed below in Direction A. The
free text is carried untouched into `trip["request"]["assumptions"]`
(`plugins/china-trip-weaver/src/china_trip_weaver/planning.py:328-329`,
`journey.py:873-875` both only deduplicate-and-append; neither parses train
numbers out of it) and rendered verbatim as visible page text by
`render/html.py:493-510` (`_request_section`, the "默认假设" / "Assumptions"
list — the **only** two free-text `request` fields ever rendered as visible
Trip-page text are `constraints` and `assumptions`; `pasted_notes` is never
rendered — `git grep -n "pasted_notes" -- plugins/china-trip-weaver/src/china_trip_weaver/render/`
returns nothing).

Separately, `_resolve_rail` (`planning.py:1332-1441`) has no concept of a
pinned service: for each route it selects the same-day candidate with the
earliest arrival (`planning.py:1369-1373`, a bare `min(...)`), with no
`service_number` parameter at all. Whatever 12306 happens to return first for
that day becomes the leg — it does not have to be, and on a re-plan is not
guaranteed to be, G1902. When it isn't, the page still displays the
`assumptions` sentence claiming G1902 is booked, alongside a
`transport_legs` entry for a different service. `render/validate_html.py`'s
`_check_rendered_facts` exists precisely to catch this class of mismatch: it
concatenates every visible text node and user-facing attribute
(`validate_html.py:266-271`), scans the result for anything matching
`TRAIN_FACT_RE = re.compile(r"(?<![A-Z0-9])[GDCKTZ]\d{1,4}(?!\d)")`
(`validate_html.py:36`), and for any match not in
`{leg["service_number"] for leg in trip["transport_legs"]}`
(`validate_html.py:272`) raises `E003 rendered train fact is absent from
Trip: <token>` (`validate_html.py:273-275`). `plan_trip` calls this
synchronously through `_plan_validate_and_render`
(`planning.py:465-481`, raise at `planning.py:478`), and `plan_journey`
calls `plan_trip` once per one-to-seven-day segment with no isolating
`try/except` around the call (`journey.py:263-273`) — one segment's E003
aborts the **entire** Journey before `--output-json` is ever written, not
just the offending Trip.

### Task 0: offline reproduction

The task book's literal instruction — reproduce E003 via `ctw journey
validate-html` on `demo/journey-16d/`'s existing artifacts — **does not
reproduce it**. Evidence: doctoring a copy of `demo/journey-16d/journey.html`
to insert a stray `<p>G1902车票已购并锁定：...</p>` right after `<body>` and
validating it against the unmodified `demo/journey-16d/journey.json`:

```
$ /usr/bin/python3 plugins/china-trip-weaver/scripts/ctw journey validate-html \
    .tmp/e003-repro/journey-doctored.html demo/journey-16d/journey.json
JOURNEY HTML VALID .tmp/e003-repro/journey-doctored.html errors=0
```

Root cause of the miss: `ctw journey validate-html` runs
`render/validate_journey_html.py`'s `validate_journey_html`, which has **no**
train-fact/`TRAIN_FACT_RE` check at all —
`git grep -n "E003\|TRAIN_FACT_RE" -- plugins/china-trip-weaver/src/china_trip_weaver/render/validate_journey_html.py`
returns nothing. It only imports `AuditParser`, `DISALLOWED_TAGS`,
`HTMLIssue`, `HTMLValidationReport`, `SECRET_PATTERNS`, `_csp`,
`_css_contract`, `_number` from `validate_html.py`
(`validate_journey_html.py:14-23`) and defines its own, disjoint `JH0xx`
checks. This is itself worth noting as a real asymmetry: the Journey page's
own "journey-notes" section renders the exact same
`trip["request"]["assumptions"]` text again, deduplicated across every
sub-Trip (`render/journey_html.py:851-871`, `_notes_section`), with zero
guard against a hallucinated train number there.

The guard that actually fired in the real failure lives one level down, on
the Trip page, reached via `ctw validate-html` (Trip-level) — the same
function `plan_trip` calls internally. Reproduced offline, with zero network
calls, using only `demo/journey-16d/`'s existing `journey.json`:

```
$ /usr/bin/python3 plugins/china-trip-weaver/scripts/ctw journey extract \
    --journey demo/journey-16d/journey.json --trip-id trip-c5eba1b26542ed43 \
    --output-json .tmp/e003-repro/trip.json
JOURNEY_EXTRACT_COMPLETE json=.tmp/e003-repro/trip.json trip_id=trip-c5eba1b26542ed43

$ /usr/bin/python3 plugins/china-trip-weaver/scripts/ctw render \
    .tmp/e003-repro/trip.json --output .tmp/e003-repro/trip.html
RENDERED .tmp/e003-repro/trip.html sha256=cd01aa11e7... errors=0

# doctor trip.html: insert <p>G1902车票已购并锁定：9月26日07:50福州南站出发。</p> after <body>

$ /usr/bin/python3 plugins/china-trip-weaver/scripts/ctw validate-html \
    .tmp/e003-repro/trip-doctored.html .tmp/e003-repro/trip.json
E003 rendered train fact is absent from Trip: G1902
HTML INVALID .tmp/e003-repro/trip-doctored.html errors=1
```

(Control: the same command against the undoctored `trip.html` prints `HTML
VALID ... errors=0`, isolating the injected sentence as the sole cause.)
This is character-for-character the real failure text, confirming the
guard's real behavior matches what the task book asserted, even though the
named command to trigger it was wrong.

## Directions evaluated

### Direction A — add a structured "locked service" field

`candidates.schema.json`'s top level is exactly
`{candidates_version, pois, lodgings, claims, unknowns}` — no transport
representation exists there at all, so "candidates" is not a viable home; the
field can only go under `request`. `trip.schema.json`'s `#/$defs/request`
(`trip.schema.json:381-477`) has `"additionalProperties": false` but its
`"required"` list (`:384-395`) does not need to change for a new **optional**
property — adding one to `"properties"` is additive and does not invalidate
any document that omits it.

Fixture-compatibility check: the task book worried this would break "既有
20 份 golden 和 8 份 no-solution 夹具." Verified those live at
`tests/fixtures/scheduler/{golden,no_solution}/` (`find` counts: 20 and 8,
matching `CLAUDE.md`), and one sample
(`tests/fixtures/scheduler/golden/budget-hard-limit.json`) has the shape
`{case_id, days, expected, fixture_version, tags}` — pure day-scheduler
fixtures for `schedule_day`, a subsystem that never sees `request` or
`RouteSpec` at all. **They are structurally unrelated to `_resolve_rail` and
would be unaffected regardless of this field**, correcting the task book's
premise. The real fixture surface for this direction is
`tests/fixtures/providers/rail12306/*` (17 files) and whichever of the 42
`plan_trip(` call sites in `tests/*.py` exercise rail — none of those embed a
`request` document with this new field either, so none would need to change;
new fixtures would need to be **added**, not any existing one edited.

Implementation surface, traced concretely: `_resolve_rail`
(`planning.py:1332-1441`) would need, at its candidate-selection point
(`planning.py:1363-1378`, currently a bare `min(candidates, key=...)`), a
branch that first checks whether the current `RouteSpec` (keyed by
`travel_date` + `from_place`/`to_place`, `planning.py:45-50` — there is no
`leg_id` yet at this point, planning hasn't created legs) matches a locked
entry, and if so filters candidates by `service_number` (and optionally
`depart_at`/`arrive_at` for disambiguation) instead of taking the earliest
arrival. **This exact filtering logic already exists and is already
tested**: `replan.py:349-436` (`_select_refresh_service`,
`_disambiguate_service_matches`, `_matches_time`) solves precisely "pick one
row from a 12306 result set given `service_number` + optional
`depart_at`/`arrive_at`" — for the `refresh` replan event
(ADR-0015). It could be extracted into a shared helper both modules import,
rather than reimplemented. The genuinely new design work is what happens
when the locked service does **not** appear in that day's live results — no
existing analog decides whether that should be a hard failure (loud, but
regresses the current "always produce *something*, flag it in `unknowns`"
posture in `_resolve_rail`'s existing no-match path,
`planning.py:1391-1422`) or a softer `unknowns` entry naming the mismatch.
That choice needs product judgment this round is not scoped to make.

### Direction B — attribute the E003 message to its source

The task book asked whether "报错那一层还拿不拿得到 assumptions 的出处" — it
does, already, with no new plumbing. `_check_rendered_facts(parser, trip,
add)` (`validate_html.py:212`) already receives the full `trip` mapping that
`validate_html(html_text, trip)` was called with (`validate_html.py:153`),
and `trip["request"]["assumptions"]` is a required field of that same `trip`
(`trip.schema.json:392`). Nothing needs to be threaded through additional
layers. Combined with the Context finding that `assumptions` and
`constraints` are the **only** two free-text `request` fields ever rendered
as visible Trip-page text, `_check_rendered_facts`
(`validate_html.py:272-275`) could — after finding an unexpected token in the
whole-page scan it already does today — search only those two lists for the
matching substring and, if found, report which list and index (e.g. "...
absent from Trip: G1902 (found in request.assumptions[6])"), falling back to
today's generic message when the token isn't in either (meaning it leaked
from some other, likely renderer-side, source worth investigating
differently). This is the cheapest of the three: one function, no schema
change, no new failure mode, and it does not narrow what the whole-page scan
still catches. It does not fix the underlying gap — the Journey still fails
to plan — it only makes today's failure legible instead of cryptic.

### Direction C — keep `assumptions`/`constraints` text out of the scanned pool

Recommended against. `assumptions` and `constraints` are not decorative —
they are the one place a user's stated facts about the trip are echoed back
for them to verify, consistent with this project's evidence-first design
(ADR-0007). Exempting them from the scan does not, by itself, hide anything
from the user (the text would still render normally) — but it removes the
one check that would ever catch the **exact** failure mode this ADR exists
to discuss: a user's stated "already booked" fact silently diverging from
whatever service `_resolve_rail` actually picked. That is precisely the
highest-risk spot for such a mismatch (it is the one field reserved for
user-declared *fait accompli* facts), so exempting it trades away the guard
at the point it is most needed, not the point it is least needed. It is also
mechanically awkward to implement without a worse side effect: any way to
keep it "invisible to the parser but visible in a real browser" (e.g.
piping it through some non-text channel) creates a permanent gap between
what `validate_html` checks and what the page actually shows, undermining
the audit script's value as a proxy for what users see; the only way to keep
parser and browser in agreement is to genuinely hide the text, which **is**
"让用户看不到本该看到的信息" — the exact risk the task book asked to check.

### Direction D (proposed 4th option) — no code change: plan without the fact, then pin it with the existing refresh mechanism

`ctw replan --event refresh` already has a fully built, already-shipped,
already-tested mechanism for exactly "this specific service is locked in":
ADR-0015's `_select_refresh_service`, taking `service_number` and
`depart_at`/`arrive_at`. This is not hypothetical for this leg — the real
trip directory already contains
`fujian-2026-09-25-to-10-10/event-g1902-booked.json`:

```json
{
  "type": "refresh", "subject_ref": "leg-fuzhou-wuyi",
  "service_number": "G1902", "depart_at": "07:50",
  "reason": "用户确认已购买G1902：..."
}
```

confirming this exact pin was already applied successfully once (matching
`north-2-rail` being live-refreshed to G1902 per this project's own current
state). The zero-code path is: keep initial `journey plan` silent on the
booking (temporarily omit or neutralize that one `assumptions` sentence so
`_resolve_rail` picks whatever it picks and the Trip still validates), let
planning succeed, then `ctw journey extract` the affected Trip, `ctw replan
--event refresh --rail-result ...` to pin G1902 onto the correct leg, and
`ctw journey assemble --replace-trip` to reintegrate it — a documented,
tested, zero-new-code pipeline. Its limit: the fix lives in the *replanned
output*, not in `request.json`. `request.json`'s `assumptions[6]` is
permanent, user-authored source; every future **from-scratch** `journey
plan` re-run against the same `request.json` (this project re-plans this
real trip repeatedly across revisions — journey.json through journey-r5.json
per `CLAUDE.md`) will re-derive a fresh, unpinned rail selection and hit the
identical E003 again, forcing whoever re-plans to remember, by convention
alone, to defer this exact sentence and re-apply the same manual refresh
every time. It is a correct today-workaround, not a durable substitute for
Direction A.

## Decision

**2026-09-15 裁决：** Direction B 本轮实施（see the follow-up task book that shipped it: the E003
message now cites which `request.assumptions`/`constraints` entry a stray train fact came from when
it can find one). Direction A 认可为长期方向，下一波单独立项（其"锁定车次当天查无此车怎么办"这一失
败语义仍待设计，不在本轮范围）。Direction C 不采纳。Direction D 作为落地前的临时工作流（`ctw replan
--event refresh` 一直可用，写进后续操作指南）。

**结论提要（≤6 条，每条见上文 Context/Directions 的行号与命令）：**

1. 任务 0 按字面指令（`ctw journey validate-html`）复现不出 E003——
   `validate_journey_html.py` 没有任何 `TRAIN_FACT_RE`/E003 检查
   （`git grep` 零命中），必须改用 Trip 级 `ctw validate-html`（`plan_trip`
   内部实际调用的同一函数）才能复现；已offline 复现，输出与真实故障逐字一致。
2. Direction A（结构化锁定字段）可行：schema 改动是纯增量、`additionalProperties`
   不受影响；task 书担心的 20 golden/8 no-solution 夹具经核实是完全不相关的
   day-scheduler 子系统，不会因此失效；`_resolve_rail` 的候选匹配逻辑可直接
   复用 `replan.py` 里已经写好并测试过的 `_select_refresh_service` 家族，只有
   "锁定车次在当日实时结果里查无此车" 这一个全新的失败模式设计需要领导拍板。
3. Direction B（只改报错）比任务书设想的更便宜：`_check_rendered_facts` 早已
   拿到完整 `trip`（含 `request.assumptions`/`constraints`），无需新增任何
   跨层传参；`assumptions`/`constraints` 是仅有的两处会被原样渲染成可见文本的
   自由文本字段（`pasted_notes` 从不渲染），可精确回指。不解决根因，只降低
   诊断成本。
4. Direction C（隔离自由文本）不建议：这类文本恰恰是「用户声称的既成事实」
   最可能与实时选中结果不一致的地方，隔离掉护栏等于在风险最高处摘掉护栏；
   工程上也做不到「解析器看不见但浏览器看得见」而不产生「校验器与真实页面
   脱节」的新问题，唯一能保持两者一致的做法就是真的把文字藏起来，等于违反
   任务书自己要查的「用户看不到本该看到的信息」。
5. Direction D（提出的第四选项，零代码）：`ctw replan --event refresh` 机制
   已完整存在且已在真实的 G1902 这条腿上跑通过
   （`fujian-2026-09-25-to-10-10/event-g1902-booked.json`）；今天就能用，
   零成本；但只修补"这一次重规划的产物"，不修补 `request.json` 本身，每次
   从零重新 `journey plan` 都会再撞一次同一个 E003，不是长期解法。
6. **推荐**：Direction A 定为长期方向（下一波单独立项，重点是设计"锁定车次
   查无匹配"时的失败语义）；Direction B 无论 A 何时落地都值得独立先做，成本
   最低、零风险；Direction C 不采纳；Direction D 是今天就能用的正确临时
   工作流，写进任务书/操作指南供下一次重规划前使用，但不能替代 A。

## Consequences

If Direction A ships:

- `_resolve_rail`'s selection function gains a second responsibility (earliest
  arrival vs. honor a lock), and its no-match path needs a new, deliberately
  designed outcome for "locked service absent from today's live results" —
  this is genuine new failure-mode design, not a mechanical port of
  `_select_refresh_service`.
- `request` (and by extension `trip.schema.json`'s `#/$defs/request`,
  possibly `journey.schema.json`'s mirror) gains a new optional shape that
  every future reader of a `request`/`trip` document needs to be aware of,
  including this project's own `journey.py` segment-merge/dedup logic
  (`journey.py:141-142`, `:873-875` already do this for `assumptions`; an
  analogous merge would be needed for the new field across multi-day
  segments).
- New fixtures are required (rail provider fixtures plus `plan_trip`/
  `journey` test cases); none of today's fixtures need to change.

If Direction B ships alongside or before A:

- E003's message format changes (additive detail, not a code change) —
  any test asserting the exact current message text
  (`"rendered train fact is absent from Trip: %s"`) needs updating; a
  `git grep` for that literal string in `tests/` should be the first step of
  that book.
- The underlying capability gap (no way to honor a locked service at initial
  `journey plan` time) remains open regardless.

If Direction D is adopted as interim guidance only:

- Someone has to actually write and place that guidance (a skill, a
  CLAUDE.md-level note, or a section in this project's replan
  documentation) — this ADR does not do that; it only establishes that the
  mechanism it would point to already works.

## Still unresolved / not ruled out

- Whether a locked-service entry should be scoped per-route (date + city
  pair, the only key available before leg ids exist) or per-leg-index after
  a first successful plan — this round only traced the pre-leg-id case
  (`_resolve_rail`); it did not design the exact matching key shape.
- Whether Direction A's "locked service not found live" case should abort
  the Trip (loud, consistent with E003's own philosophy) or degrade to an
  `unknowns` entry (consistent with `_resolve_rail`'s existing no-live-match
  fallback) — flagged in Direction A above as needing product judgment, not
  resolved here.
- Whether `journey.schema.json`'s own top-level `assumptions`
  (`journey.schema.json:77,95`) would need a parallel change for Direction A
  in journeys assembled from independently-planned Trips
  (`journey assemble` build mode) rather than planned via `journey plan` in
  one pass — not traced in this round.
- No live network calls were made this round (per the task book's
  constraint); Direction A's design has not been validated against a live
  12306 response shape beyond what `replan.py`'s existing, already-live-
  tested code already assumes.

## Implementation record — Direction A shipped (2026-09-15)

`#/$defs/request` gained an optional `locked_rail_services` array
(`trip.schema.json`'s new `lockedRailService` def): `service_number` and
`travel_date` are required, `depart_time` (`HH:MM`) is optional and only
needed to disambiguate a `service_number` that resolves to more than one
same-day row — the same-city two-station clash this ADR's Context section
describes for G1902 (福州南站 07:50 vs. 福州站 08:12, both arriving 09:30).
`schema_version` stayed `"1.0.0"` and the new field was not added to
`request`'s `"required"` list, so every existing `request` document remains
valid unchanged.

`_resolve_rail` (`planning.py`) now checks, per route, whether any locked
entry shares that route's `travel_date` before falling back to the
pre-existing earliest-arrival `min(...)`; a match is applied via the new
`_locked_rail_candidate` helper, which mirrors `_select_refresh_service`'s
service-number filter plus `depart_at` disambiguation (as this ADR's
Direction A section anticipated) reimplemented locally rather than shared
across modules, since `replan.py` already imports from `planning.py` and
the reverse would have created a cycle. A leg selected this way is marked
`"locked": true` in the output Trip.

The failure semantics flagged as open above are now settled by a 2026-09-15
leadership ruling: **a locked service absent from, or not uniquely
resolvable within, the day's live results never aborts the Trip.** It falls
back to the existing `_deep_link_leg` placeholder-leg path, and the
resulting `unknowns`/`runtime_warnings` name the specific locked
`service_number` and date (`locked_service_not_found` /
`locked_service_ambiguous`), so a reader can tell "no train exists that day"
apart from "your locked train specifically wasn't found" — never a silently
substituted, unlocked service standing in for the one the traveler actually
booked.

The locked-service entry is scoped by `travel_date` alone rather than an
explicit city-pair key, resolving the first open question above: a
`RouteSpec`'s own 12306 query is already scoped to its city pair, so its
candidates cannot contain another route's service by coincidence in
practice; `_locked_rail_candidate` additionally tries every same-date lock
against a route's own candidates (not just the first), so two locked legs
that happen to share one calendar date on two different routes still each
resolve correctly without needing an explicit endpoint field on the entry.

## Update — shared helper extracted (2026-09-15)

The "reimplemented locally rather than shared across modules" choice recorded
above was revisited the same day. `_locked_rail_candidate`'s per-lock
service-number filter and depart-time disambiguation, and
`_select_refresh_service`'s equivalent branch, were both rewritten to call a
new `rail_selection.select_service(candidates, service_number,
requested_depart_at=None, requested_arrive_at=None)`. This is a third leaf
module neither `planning.py` nor `replan.py` needs to import from each
other for, so it avoids the import-cycle concern this ADR raised without
either module depending on the other. Each call site keeps its own failure
shape unchanged — `replan.py` still raises `ReplanError` and builds its
"multiple rail services match..." message text locally, `planning.py` still
returns the `(selected, service_names, failure)` triple — since that
contract was module-specific, not part of the duplicated matching logic.
