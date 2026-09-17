# ADR-0022: Nearby dining references — source, anchor, radius, and presentation

- **Status:** Accepted（2026-09-17 领导裁决；第三十三波 AP1a/AP1b/AP2 已落地适配器参数、规则与页面，`ctw dining`/`ctw journey dining` 命令、折回与规划器接线在第三十四波）
- **Date:** 2026-09-17

## Context

The real 16-day Fujian itinerary lists 「地方饮食」 among its interests, yet every
lunch and dinner is a bare `free` or `meal` slot（「午餐（地点待定）」）with no venue,
and the candidate file carries no restaurant at all. The leader asked whether
高德扫街榜 (AMap's behaviour-based venue ranking launched 2025-09-10) could feed
recommendations.

Facts established on 2026-09-17:

- 扫街榜 has no developer interface. The AMap Web Service documentation
  (updated 2026-07), the AMap MCP Server capability list (2026-03) and the
  空间智能开放平台 expose no ranking endpoint; the only known integration is
  Alibaba's own 千问 app. Scraping the consumer app is outside this project's
  read-only, pinned-contract boundary (ADR-0004).
- The already-pinned POI search v5 returns, with `show_fields=business`, a
  `business` object whose `rating`, `cost`, `tag`（特色菜）, `keytag`/`rectag`
  （菜系）, `opentime_today`/`opentime_week` fields are populated for 餐饮 POIs.
  A live `/v5/place/around` query with `sortrule=weight` around 三坊七巷
  (radius 1500 m, types `050100|050200|050400`) returned eight rated venues
  with 人均 in AMap's own 综合排序 order; the same query sorted by distance
  surfaced lower-rated or unrated shops first.
- The AMap URI API opens a venue (`https://uri.amap.com/marker?position=…`)
  or a keyword search around a point (`https://uri.amap.com/search?keyword=美食&center=…`)
  in the AMap app, where 扫街榜 badges are visible to the user.
- The curated journey's nine lodgings carry no coordinates; its 31 POIs do.

## Decision

1. **Source: AMap POI-around search, AMap's own ranking, no ranking of ours.**
   `poi_around` gains an optional `sortrule` (`distance` | `weight`, default
   `distance` so station lookups are unchanged); normalized POI items gain
   `distance_meters` (optional in `#/$defs/poi`). Dining queries use
   `sortrule=weight`, `types=050100|050200|050400`, `keywords` from
   `request.dining_preferences.cuisine` or 「餐厅」, radius 1500 m, page size 10.
2. **Which slots and where the circle is centred.** A slot is a meal when its
   `kind` is `meal`, or its `kind` is `free`/`rest` and its title contains
   「午餐」/「晚餐」. The anchor is the nearest same-day slot with a known GCJ02
   coordinate — searching backwards first, then forwards — taken from the POI
   or lodging it references; planner meal placeholders never anchor. A day with
   no such slot gets `dining: null` and an `unknown` whose reason is
   `dining_no_anchor`; nothing is guessed.
3. **Selection is mechanical.** Keep AMap's order, drop venues without a
   `rating`, drop venues whose name/tag/keytag/rectag contains any word from
   `request.dining_preferences.avoid`, keep the first three. Each option carries
   the AMap identity claim that backs it (`subject_ref` = the slot), the marker
   deep link and the web link; the slot carries a `search_url` for 「在高德 App
   看附近美食」.
4. **Where it lives and how it shows.** Optional, nullable `slot.dining`
   (`#/$defs/diningReference` with up to three `#/$defs/diningOption`);
   `schema_version` stays 1.0.0. Both pages render a `slot-dining` block only
   for slots that carry the key, so every pre-existing document renders
   byte-identically; validators read the block back word for word (`E007`,
   `JH007`) and fold dining 人均 into the E003 known-price set.
5. **Two entry points, same rules.** `ctw dining` writes a result envelope
   (one row per meal slot) and `ctw journey dining` folds it into an existing
   Journey as a `trigger=dining` patch per changed child Trip, revision +1 via
   `replace_trips_in_journey`, NOOP exit 2 when nothing changes; `plan_trip`
   fills placeholders the same way when AMap mobility is live. Both reuse
   `dining.py`, which never touches the network.

## Consequences

- Budget: two AMap calls per travel day at most, inside the existing 80-calls
  ceiling and 2 QPS gate; attribution in the footer follows from the AMap
  health row (terms §7.7); the Trip document is the only place the data lives
  (§3.5, no cache).
- Ratings and 人均 are AMap facts at `queried_at`, never a promise; the page
  says 「高德综合排序」 and nothing about 扫街榜 itself.
- Deferred: cuisine-aware re-ranking, breakfast, and lodging geocoding for the
  curated journey (its dinners anchor on the preceding attraction instead).

## Evidence

- Live probes and acceptance runs: BLOCKED.md「AP1a」「AP1b」「AP2」rulings and the
  workspace record of 2026-09-17.
- Fixture `tests/fixtures/providers/amap/around_dining.json`; rule tests
  `tests/test_dining.py`; schema fixtures `tests/fixtures/trips/schema/valid/dining-references.json`
  and `invalid/dining-option-missing-rating.json`; renderer/validator tests in
  `tests/test_renderer.py` and `tests/test_journey.py` (E007/JH007).
- Schema: `plugins/china-trip-weaver/schema/trip.schema.json` `#/$defs/diningOption`,
  `#/$defs/diningReference`, `slot.dining`, `request.dining_preferences`.
