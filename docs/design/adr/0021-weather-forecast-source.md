# ADR-0021: Weather forecasts — source, horizon, advice, and where they live

- **Status:** Accepted（2026-09-17 领导裁决；第二十九波 AN1/AN2 已落地数据层与页面层，规划器接线与 `ctw weather` 命令在第三十波）
- **Date:** 2026-09-17

## Context

Until 0.22.1 the plugin had no weather query at all. `04-providers.md` listed
`weather` as a capability name, VariFlight declared `getFutureWeatherByAirport`
(airport weather, never dispatched), `replan` accepted a user-triggered
`weather` event with a hand-written replacement slot, and the research query
template mentioned 季节天气 as a text dimension — but no forecast ever reached
a Trip, and every real itinerary carried the line 「天气待官方确认」 as a
permanent unknown. The real 16-day Fujian trip (2026-09-25 to 10-10, typhoon
season, two ferry legs) is the first user of whatever this ADR decides.

Live facts measured on 2026-09-17 with the existing `AMAP_WEBSERVICE_KEY`
(`GET https://restapi.amap.com/v3/weather/weatherInfo?city=<adcode|name>&extensions=all`):

- province/city/county/district adcodes (350000/350100/350782/350102/350128/350627)
  and bare Chinese names (福州, 武夷山, 平潭, 南靖, 泉州, 上海) all return
  `forecasts[0].casts` with exactly 4 entries — today plus three days;
- every value is a string (`daytemp: "32"`, `daypower: "1-3"`); `*_float`
  duplicates exist and are ignored;
- an invalid adcode, a non-administrative name (鼓浪屿) and a composite name
  (福州／平潭) return `status=1, infocode=10000, count=0, forecasts=[]` — a
  *successful empty* answer that must be read as `no_results`;
- an ambiguous name (鼓楼区) returns `count=4` with four forecasts from four
  provinces;
- eight requests fired without pacing tripped `infocode=10021` (concurrency
  limit) from the sixth call on.

Open-Meteo (keyless, 16-day horizon) was evaluated as a second source and
rejected: it is an overseas service with no pinned version, unverified terms,
and it would break the project's "no provider without a pinned contract"
convention (ADR-0004, `provider-contracts.md`).

## Decision

1. **Source: AMap weather only.** The existing key, the existing HTTP
   transport (`amap_http.py`), the existing budget/QPS gate, and the existing
   error ladder. No new credential, no new provider. `weather` becomes the
   AMap adapter's fifth capability (`amap.py::_weather`), requesting either a
   6-digit `adcode` or a Chinese `city` name — exactly one of the two.
2. **Horizon is the provider's: today + 3 days.** A travel date outside that
   window is not guessed; it is an `unknown` whose reason names the first day
   the forecast becomes available (`weather.forecast_available_on(date)` =
   `date − 3 days`). Refreshing closer to departure is the user's normal
   workflow, not a failure.
3. **Ambiguity is never resolved by picking the first hit.** More than one
   forecast in the answer → `no_results` plus warning `weather_ambiguous:<n>`.
   Name lookups stay allowed for the CLI (the real curated journey has no AMap
   identity claims to derive adcodes from), but the planner prefers adcodes
   taken from `/provider_identity` claims when it has them.
4. **Advice is a fixed rule table, and it never changes the schedule.** POIs
   carry no indoor/outdoor attribute, so the planner cannot know which slot a
   rainy afternoon hurts. `weather.advice_for` emits at most five sentences
   (rain/thunder/typhoon, snow/ice, ≥35 ℃, ≤5 ℃, wind level ≥6 with a ferry
   warning) in a fixed order with fixed wording; the scheduler stays untouched.
5. **Where it lives.** One claim per forecast day (`provider=amap`,
   `field_path=/weather`, `subject_ref`=the day it belongs to), and an optional,
   nullable `day.weather` object (`#/$defs/weatherForecast`, twelve required
   keys, `additionalProperties:false`) that carries the forecast, the advice
   list and the backing `claim_id`. `schema_version` stays 1.0.0 because the
   field is purely additive; a day without the key is a legacy day.
6. **Pages show it, validators re-read it.** Both renderers print one
   `天气：` line per day card (Trip `days`, Journey `day-timeline`) and the
   validators check it back against `day.weather` word for word (`E006`,
   `JH006`). The line is rendered only when at least one day in the document
   carries a `weather` key, so every pre-0.23 Trip, Journey and checked-in
   demo renders byte-identically.

## Consequences

- AMap call budgets now also pay for weather: at most one query per distinct
  adcode/name per planning run, memoised, inside the existing 80-calls-per-Trip
  ceiling and 2 QPS gate. Attribution in the footer follows automatically from
  `provider_health` (AMap terms §7.7), and nothing is cached (§3.5).
- A forecast is a dated fact like any other claim: it is only true at
  `queried_at`, it is never a promise, and it degrades to `unknown` — never to
  a guess — when the provider is off, unconfigured, rate-limited, ambiguous or
  out of horizon.
- Deferred, with reasons: VariFlight airport weather stays undispatched (a
  second, airport-scoped source would need its own conflict rule); the
  `_request_contract` weather branch has no request-shape unit test yet (the
  fixture corpus replays transports and never builds the URL) — the next wave
  adds one; Open-Meteo can be reconsidered only with a pinned contract and
  verified terms.

## Evidence

- Live probes and the AN1 acceptance run: PROGRESS.md「第二十九波 AN1」and the
  workspace record of 2026-09-17 (adcode/name/ambiguity/QPS results quoted above).
- Contract fixtures `tests/fixtures/providers/amap/weather.json`,
  `weather_empty.json`, `weather_ambiguous.json`; rule tests
  `tests/test_weather.py`; renderer/validator tests in `tests/test_renderer.py`
  and `tests/test_journey.py` (E006/JH006).
- Schema: `plugins/china-trip-weaver/schema/trip.schema.json`
  `#/$defs/weatherForecast` and `day.weather`; docs `03-trip-model.md`,
  `07-renderer.md` §2/§7.1.
