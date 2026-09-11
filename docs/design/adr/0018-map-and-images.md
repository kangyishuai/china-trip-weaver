# ADR-0018: Maps and images on the mobile page

- **Status:** Proposed
- **Date:** 2026-09-11

## Context

The roadmap has parked "interactive map" and "images" for three months with
the same reason each time: "needs a new ADR." This ADR is that answer. It
changes no code, schema, or test file — only this document plus the two
progress logs.

### The renderer's existing map/image contract

- `docs/design/07-renderer.md:63`: "v1 不加载 AMap JS、Leaflet、OSM tiles 或
  任何 remote map script；因此不需要/不接受 JS Key/security code。"
- `docs/design/07-renderer.md:61-67` (§4.2 地图): points are normalized onto
  a WGS84-or-GCJ02 canvas (never mixed in one SVG), only markers and visit
  order are drawn, any connecting line must be labelled "日程顺序示意，非
  道路路线", and an unlocated point must show "位置未核验" — never `(0,0)`
  or a city-centre fallback.
- `docs/design/07-renderer.md:70` (§4.3 图片): "Trip v1 Schema 没有 image
  字段，renderer 不请求远程图片……未来若加图必须先升 Schema 并定义
  license/source/alt/offline placeholder，不得在模板私自抓图。"
- `docs/design/07-renderer.md:33` (§2 页面架构，第 8 条): the single-Trip
  page's fixed section order includes `location-overview`: "只用 Trip 中
  已存在的 WGS84/GCJ02 点画内联 SVG **位置示意**；醒目标注'非真实路线'，
  另给 AMap/官方 `https` deep links。"
- `docs/design/07-renderer.md:76-95` (§5.1 CSP): the mandatory CSP includes
  `img-src data:` (inline images only) and `connect-src 'none'`; the only
  permitted remote behaviour anywhere on the page is a user's own click on
  an `https` link.
- `docs/design/07-renderer.md:172-176` (§10 Journey renderer): states that
  the Journey renderer (`render/journey_html.py`) "与上述单 Trip renderer
  共享同一套安全/CSP/离线/mobile 合同" — it does not, in as many words,
  say the Journey page also inherits §2's 12-section list itself (§2 is
  written for "Trip", the single-itinerary page).
- `docs/research/05-open-questions.md:82` (Q12): "手机单文件 HTML 能否同时
  做到 secret-free、核心离线与地图可用？"，未决理由写着 "AMap JS 需
  key/security，Leaflet/tiles 非离线；KML/SVG 可离线但交互弱。" §4.2/4.3
  的现行合同是这个问题当时给出的答案；本 ADR 的证据没有推翻它。

### What `_location_svg` already does, and where it does not run

- `render/html.py:627` `_location_svg(plotted, crs, city, group_index,
  labels)`: normalizes each located point's `lng`/`lat` into a `viewBox="0
  0 100 100"` canvas (`x = 10 + (lng-min)/(max-min)*80`, `y = 90 -
  (lat-min)/(max-min)*80`), draws a numbered `<circle>`+`<text>` marker per
  point, a `<polyline class="route-line">` when there is more than one
  point, and a `schematic-note` paragraph carrying the "日程顺序示意"
  wording §4.2 requires.
- `render/html.py:601`, inside `_location_section`: `_location_svg` is only
  called when `plotted` (the city's located points) is non-empty; otherwise
  the page renders `<p class="empty-state">位置未核验</p>` — the §4.2
  "coordinates unknown" rule, already implemented.
- `render/journey_html.py`: `git grep -c` for both `_location_svg` and
  `<svg` returns exit code 1 (zero hits) — the Journey page, the one
  rendered by `ctw journey render` and read on a phone across multiple
  trips, has no location visualization of any kind today.
- `render/journey_html.py:267-277` (`_render_journey`'s section list) has
  11 sections — route, day-timeline, budget, priority-actions, checklist,
  risk, segments, connections, transport-overview, provider-health, notes —
  none of them a location/map section.
- `render/journey_html.py:482` `_route_section`: builds only
  `origin_text`/`destination_text` strings and an `<ol class="journey-route">`
  list of city names; it carries no coordinates and draws nothing visual.
- `render/journey_html.py:13-22` already does `from .html import
  (PROVIDER_ATTRIBUTION, RendererError, _enum_label, _field_label,
  _health_reason, _number, _price, _provider_label, _render_day_slots)` —
  cross-module import of seven underscore-private functions from `html.py`
  is the file's existing convention, not a new pattern a future book would
  have to introduce.
- `schema/journey.schema.json:60`: `"trips": {"items": {"$ref":
  "trip.schema.json"}}` — each `journey["trips"][i]` is a complete Trip,
  carrying its own `pois`/`lodgings`/`coordinates`. The data `_location_svg`
  needs is already present; nothing new would need to flow into the Journey
  document to reuse it.

### Provider and licensing facts a static-map or image option would run into

- `THIRD_PARTY_NOTICES.md:16`: AMap's terms — section 3.5 "forbids directly
  storing, caching, or scraping its service data"; section 7.7 "requires
  naming 高德地图 as the source wherever its data is displayed"; section
  3.2.2 requires a purchased commercial licence; section 3.4 forbids
  training/dataset use.
- `plugins/china-trip-weaver/references/provider-contracts.md:26`: "R1 is
  disabled and no provider response is cached today. AMap's terms section
  3.5 forbid storing or caching its service data..." — this rung is
  already off for every existing AMap capability (POI, geocode, route
  matrix), for exactly this reason.
- `plugins/china-trip-weaver/references/provider-contracts.md`'s AMap row
  lists its capability as "POI (`poi`, optional `types`/`city_limit`),
  nearby search (`poi_around`), geocode, route matrix" — no static-map
  capability exists in the contract today.
- `plugins/china-trip-weaver/src/china_trip_weaver/providers/amap.py`:
  `git grep -in "static"` is zero hits; the adapter implements exactly
  three capabilities — `_pois` (L45), `_geocodes` (L113), `_route` (L135).
  A static-map fetch would be new adapter surface, not a reuse of existing
  code.
- `providers/anysearch.py` and `providers/host_web.py`: `git grep -in
  "image\|photo\|picture"` is zero hits in both. None of the project's six
  provider adapters (`amap`, `anysearch`, `flyai`, `host_web`,
  `rail12306`, `variflight`) can supply an image today.
- `render/validate_html.py:315`: `if tag == "img" and attrs.get("src") and
  not attrs["src"].startswith("data:"): add("E101", "remote image is
  forbidden")` — any future `<img>` pointing outside `data:` already fails
  validation, on both pages: `render/validate_journey_html.py:14-15`
  imports `AuditParser` from `validate_html`, so the Journey page's
  validator runs the identical `E101`/CSP checks (`_check_csp` at
  `validate_journey_html.py:483`), not a separate, possibly laxer, ruleset.

### Size

- `demo/trip.html` is 88906 bytes; `demo/journey-16d/journey.html` is
  287673 bytes (`ls -l`). Both demo fixtures are synthetic and carry zero
  located points by design, so neither has ever actually triggered
  `_location_svg` once.
- Measured (calling the existing `render_trip()` against three coordinate-
  bearing fixtures under `tests/fixtures/trips/schema/valid/` —
  `multicity-static.json`, `weekend-live.json`, `rental-ferry.json` — no
  code changed): 4 `_location_svg` instances, sizes `458`, `463`, `464`,
  `666` bytes. Mean ≈ 500 bytes, i.e. roughly +0.17% of a 287673-byte
  Journey page per trip section.
- A 640×400 PNG static map is commonly 50–150 KB (**assumption, not
  verified** — no such fetch exists anywhere in this repository or was run
  on this machine); base64 inflates that by ~33%, to roughly 67–200 KB per
  image. That is two to three orders of magnitude heavier than the
  measured SVG cost above.

### The real-world geolocation ceiling this all sits on top of

The workspace notes kept outside this repository (not a tracked file;
they record a 2026-09-06 nine-round live run of a real 16-day itinerary) say:
"78 个地点定位成功 60，坐标 unknown 12……名字 unknown 6", and that the
three matching thresholds behind that number (`_poi_admin_matches`,
`_poi_name_is_ambiguous`+`POI_NAME_SIMILARITY_MARGIN`,
`POI_COORDINATE_CLUSTER_MAX_METERS`) are deliberately strict and "不要在
后续迭代里放宽" — a real itinerary's location visualization, whatever form
it takes, will always have to render a meaningful fraction of its points as
unlocated. `_location_svg`'s empty-state path already covers this; a
map-image approach would need the same per-point fallback.

## Options

### Option 1 — status quo

Change nothing. No interactive map, no static map, no image field, no
Journey-page location visual.

- **Files touched:** none.
- **Who benefits:** nobody gains a feature; the project keeps its current
  zero-remote-request, zero-secret, fully offline-readable posture with no
  new engineering surface.
- **Contract/clause conflicts:** none — this is the literal current state
  of §4.2/§4.3/§5.1.
- **Size/offline cost:** zero.
- **What stays broken:** the Journey page (the one read on a phone across a
  multi-city trip) still has zero location visualization even though the
  single-Trip renderer has had one since before this ADR, and even though
  §2's `location-overview` section is already-accepted, already-compliant
  design — Option 1 leaves that gap unaddressed for no compliance reason,
  only inertia.

### Option 2 — offline SVG overview, extended to the Journey page

Reuse `_location_svg` (`render/html.py:627`) from `render/journey_html.py`,
one location group per `journey["trips"][i]`, the same way
`_location_section` (`render/html.py:581`) already groups a single Trip's
`pois`/`lodgings` by city.

- **Files touched:** `render/journey_html.py` only (add `_location_svg`,
  and whatever minimal grouping helper it needs, to the existing `from
  .html import (...)` block at L13-22; add one new section function; add
  one line to the `_render_journey` section list at L267-277). No schema
  change, no `SCHEMA_VERSION` bump, no new provider capability.
- **Who benefits:** a Journey-page reader gets the same "日程顺序示意"
  visual the single-Trip page already gives, per city per trip segment,
  instead of the current plain-text route list.
- **Contract/clause conflicts:** none found. §4.2's rules (CRS normalization,
  markers + visit order only, mandatory schematic-note wording, "位置未
  核验" fallback) are already implemented by the function being reused, not
  redesigned. The one open point is that §10's own wording ("共享同一套
  安全/CSP/离线/mobile 合同") does not explicitly say the Journey page
  must carry §2's `location-overview` section — so Option 2 is a contract
  *extension* by choice, not a currently-mandated fix. This ADR does not
  reinterpret §10 to mean more than it says; it only notes the gap exists
  and that closing it is fully compliant with §4.2 if chosen.
- **Size/offline cost:** measured ≈500 bytes per trip section (§ Context
  above) — for the demo's own three-trip Journey page, roughly +1500 bytes
  on a 287673-byte file if every trip had located points (today's demo has
  none, so the actual demo diff would be zero unless its fixtures also
  gained coordinates). No new remote request, no new secret, no CSP change
  needed (an inline `<svg>` is not an `<img>` and is not touched by the
  `E101` remote-image rule at all).

### Option 3 — fetch an AMap static map at plan time, embed as a data URI

A new `amap.py` capability calls AMap's static-map REST endpoint at `ctw
plan` time and embeds the returned PNG as a `data:image/png;base64,...`
`<img>` inside the rendered page.

- **Files touched:** `providers/amap.py` (new capability, new HTTP call
  shape, new fixture family under `tests/fixtures/providers/amap/`),
  `schema/trip.schema.json` (a new `$defs` entry for an image field, and
  therefore a deliberate `SCHEMA_VERSION` bump per
  `tests/test_contracts.py:68`'s existing frozen-version guard),
  `render/html.py` and `render/journey_html.py` (new rendering branch),
  `render/validate_html.py` (new checks for the license/source/alt/offline-
  placeholder fields §4.3 already requires *before* any image field is
  added), `references/provider-contracts.md` and
  `THIRD_PARTY_NOTICES.md` (a new capability row and a new terms review).
- **Who benefits:** a richer, recognizable map backdrop instead of a
  schematic; arguably easier for a traveler to orient against a real
  street layout.
- **Contract/clause conflicts:** this is the option that actually breaks
  things. Embedding the fetched PNG bytes as a `data:` URI inside a Trip or
  Journey HTML file that is then saved, copied, and shared is a more
  durable form of "directly storing" AMap's service data than the R1
  in-memory response cache the project already refuses to build
  (`provider-contracts.md:26`) — a process-lifetime cache at least dies
  with the process; a data URI is a permanent copy that outlives it and
  travels with every copy of the file. That is squarely what
  `THIRD_PARTY_NOTICES.md:16`'s section 3.5 forbids. Section 7.7's
  attribution requirement ("高德地图" must be named wherever the data is
  shown) would also need new, currently nonexistent, on-page UI. And
  `07-renderer.md:63`'s "不需要/不接受 JS Key/security code" is written
  about the *JS* SDK specifically because v1 loads no remote map script at
  all; a static-map *REST* call is a different API family but still
  requires an AMap Web Service key end to end, the same "optional
  user-configured" key class `provider-contracts.md`'s Keyless-behavior
  column already marks as "No API call" without one — so a keyless
  install could never produce a map image, while a keyed one would be
  producing exactly the stored copy section 3.5 forbids.
- **Size/offline cost:** assumption, not verified: ~50–150 KB per PNG,
  ~67–200 KB after base64 — 100-400× the measured Option 2 cost per
  location group, working directly against §4.1's "只承诺核心离线可读，
  不声称完整离线地图" posture (依据研究决策 17,
  `docs/research/04-design-insights.md:87`, "### 17. 采用：只承诺
  '核心离线可读'，地图/图片显式降级"). The image is also a
  point-in-time snapshot: a later `replan`/`suspend` event does not
  refresh it, so it can go stale in a way the coordinate-driven SVG (which
  is regenerated from the current Trip every render) cannot.

## Decision

Four questions, four independent answers:

1. **交互地图（AMap JS/Leaflet/OSM tiles）：不做。** `07-renderer.md:63` is
   the project's own existing, deliberate contract — it was set to answer
   exactly Q12 (`05-open-questions.md:82`) and nothing found while writing
   this ADR is new evidence against it. This ADR does not reinterpret or
   loosen that line; per this book's own boundary rule, a contract clause
   is not something an ADR gets to relitigate without new evidence, and
   there is none here.
2. **静态图（plan 期取高德静态图嵌成 data URI）：不做。** Option 3's own
   analysis above is the reason: embedding fetched provider bytes into a
   saved, shareable file is a stronger form of storage than the in-memory
   cache the project already refuses for the same legal reason
   (`THIRD_PARTY_NOTICES.md:16` §3.5), it needs a new attribution UI
   (§7.7), a new provider capability that does not exist today
   (`amap.py` has none), a `SCHEMA_VERSION` bump, and it costs 100-400×
   the offline-size budget of the alternative that already ships
   (`_location_svg`), for a visual that goes stale on replan.
3. **图片字段（Schema 加 image）：不做。** `07-renderer.md:70` already
   conditions this on having "license/source/alt/offline placeholder"
   defined first, which in turn needs a real, licensable image source.
   None of the six provider adapters has one (`anysearch.py`/`host_web.py`
   are zero hits for image/photo/picture; `amap.py` has no static-map
   capability); the one candidate source this ADR examined (Option 3) is
   independently rejected above. The project's own read-only,
   no-login/no-upload posture (`CLAUDE.md` "这是什么") leaves no second
   candidate source. Adding a schema field with no compliant producer
   behind it would only create a field that is permanently empty or
   permanently `unknown` — worse than not having the field.
4. **Journey 页位置示意：做。** Unlike the other three, this is not a new
   feature request: `07-renderer.md:33` (§2, point 8) already made
   `location-overview` a mandatory section of the single-Trip page, built
   entirely from data and rules (§4.2) this ADR re-verified are unchanged.
   `journey.schema.json:60` confirms the Journey document already carries
   full Trip objects, so the data is present; `journey_html.py:13-22`
   already imports seven private helpers from `html.py`, so importing
   `_location_svg` the same way is not a new pattern; and the measured
   cost is ≈500 bytes per trip section, three orders of magnitude below
   the rejected Option 3. Closing this gap violates no clause found in
   this ADR's research — it only extends an already-compliant mechanism
   to a page that happens not to call it yet.

### Minimal plan for point 4, if greenlit

- Add `_location_svg` (and whatever minimal per-city point-grouping helper
  it needs — reusing `_location_section`'s grouping logic at
  `render/html.py:581-601` (function signature through the
  `_location_svg` call site) rather than re-deriving it) to
  `render/journey_html.py`'s existing `from .html import (...)` block
  (L13-22).
- Add one new section function, e.g. `_location_overview_section(journey,
  labels)`, iterating `journey["trips"]` and emitting one `_location_svg`
  group per trip (or per city within a trip, mirroring
  `_location_section`'s own per-city loop) — same `"日程顺序示意，非道路
  路线"` wording and same "位置未核验" empty-state §4.2 already requires.
- Insert it into `_render_journey`'s section list (`journey_html.py:267-
  277`), placed after `_route_section` so "where things are" follows
  "what the route is" in reading order.
- Leave `07-renderer.md` §10 wording as a follow-up documentation edit in
  the execution book, not this ADR: either state explicitly that the
  Journey page now also carries a location-overview section, or fold it
  into §2's own list with a note that it applies to both renderers.

## Consequences

If Decision point 4 is accepted, the next execution book is scoped
narrowly: extend `render/journey_html.py` per the minimal plan above, with
draft acceptance commands (none of these should pass yet — they describe
the target):

1. A new test in `tests/test_journey.py` (the file that already holds
   every `render_journey`/`validate_journey_html` test, e.g. the existing
   `JourneyContinuityTests` class at L734) asserting that a Journey
   fixture with at least one located POI/lodging renders a `<svg
   class="location-svg"...>` block whose byte size is in the 400-700 byte
   range measured by this ADR, not an order of magnitude off.
2. `ctw journey render <fixture>.json -o <out>.html` against a synthetic
   multi-trip Journey fixture, then `ctw journey validate-html <out>.html
   <fixture>.json` → `errors=0`, in particular no new `E101` (an inline
   `<svg>` is not an `<img>`, so the existing remote-image check does not
   need modification).
3. `/usr/bin/python3 -m unittest discover -s tests` → same `OK`, 0-skipped
   baseline this ADR measured (`Ran 632 tests`), plus whatever new
   assertions the execution book adds.
4. `git status -- demo` after regenerating both demo artifacts → empty,
   *unless* that execution book also deliberately adds synthetic
   coordinates to a demo fixture to make the new section visible in the
   shipped demo (today's demo fixtures carry zero coordinates by design,
   so the new code path would otherwise sit untriggered in the demo
   output — the execution book should say explicitly which of these two
   outcomes it intends, rather than leaving it as a silent side effect).
5. `scripts/scan_secrets.py` → unchanged `0 finding(s)` (no new remote
   endpoint, no new key, nothing to leak).

If points 1-3 stand as decided (不做/不做/不做), the roadmap's "交互地图"
and "图片" parking items can be closed with this ADR as the citation —
not "still needs an ADR" but "has one, decision is 不做, revisit only on
new evidence": a change in AMap's terms (§3.5 specifically), a second
provider gaining an image capability, or a project-scope change that
allows user-supplied images (none of which exist today).
