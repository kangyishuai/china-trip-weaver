# Unresolved items

## Book 8: standalone Trip validation cannot yet consume the exclusive grouped request shape (2026-09-04)

- Status: blocked by this book's explicit write whitelist. A grouped plan itself completes, its actual request contains only `traveler_groups + meeting_anchor`, its schema validation and planner-side semantic projection pass, and its generated HTML passes fact validation. However, calling the existing public `validate_trip(result.trip)` on that same in-memory Trip produces the raw output `KeyError: 'origin'`.
- Cause: `plugins/china-trip-weaver/src/china_trip_weaver/validate_trip.py` directly indexes `trip["request"]["origin"]` and only adds that one origin plus destinations to the endpoint reference set. It does not read `traveler_groups[].origin`. The renderer and FlyAI consumer also still read aggregate legacy fields, but `planning.py` can safely confine compatibility projections to those call boundaries.
- Constraint: `validate_trip.py`, `cli.py`, and `render/` are outside Book 8's allowed paths. Persisting derived `origin + travelers` beside `traveler_groups` would make the public validator get farther, but would violate the explicit rule that the two request representations must never coexist and would still leave the second group origin unknown to semantic endpoint validation.
- Safe delivery in scope: `planning.py` validates the actual grouped Trip against the public schema, then runs all existing release-critical semantic checks against a temporary projection that adds the group-origin refs only for validation. G6 asserts the actual Trip and HTML facts. A later book must authorize updating `validate_trip.py` (and preferably renderer request presentation) so `ctw validate` can natively validate a serialized grouped Trip without any projection.

## Book 3: ordered multi-city planning

- Status: 无新增阻塞（no new blocker）。The implementation, compatibility, reverse-validation, demo, and schema gates all have an in-scope path to completion.

## Book 1: AMap place identity

- Status: 无新增阻塞（no new blocker）。POI identity, administrative consistency, business conflict preservation, semantic outliers, reverse validation, and synthetic fixtures all have in-scope implementations and passing tests.

## Book 2: live 12306 station candidates have no distance signal

- Status: blocked on 2026-09-04 for physical-distance ordering only; the remaining station fallback and error-classification work continues.
- Evidence: pinned `12306-mcp@0.3.10` implements `get-stations-code-in-city` as a list containing only `station_code` and `station_name`. The current rail `ProviderRequest` likewise carries names/refs/date but no station coordinates or candidate-to-endpoint distances.
- Constraint: `planning.py`, `mobility.py`, and AMap providers are explicitly owned by other books and may not be changed here. Querying every candidate for tickets would produce duration, not physical distance, and could still silently choose the wrong station.
- Safe delivery: return every candidate without selecting one; sort ascending when a synthetic/forward-compatible candidate supplies `distance_meters`, with unknown distances last and deterministic ties. Live candidates without a distance remain deterministic but are not claimed to be physically ranked.

No product-level item is open. Standing constraints are not listed here, because a list of unresolved items
should mean pending work. They live where they are enforced:

- Provider terms, attribution, caching, and the licences commercial use would
  require: `THIRD_PARTY_NOTICES.md`.
- Provider pins, deadlines, degradation, and FlyAI's optional status:
  `plugins/china-trip-weaver/references/provider-contracts.md`.
- Architecture decisions, including why this plugin is not listed on a public
  marketplace: `docs/design/adr/`.

## Lodging and flight inventory have a single upstream source (closed)

- Status: closed on 2026-09-04, superseded by the tested independent fallbacks
  recorded under Book 4 above. Kept here for provenance; the facts below
  describe the situation before those fallbacks existed.
- Fact: `@fly-ai/flyai-cli` is the only source for both lodging and flight
  inventory. It is an unofficial third-party wrapper published by an individual
  maintainer, it last shipped on 2026-04-21, and its command surface already
  drifted once between releases. If it is abandoned or changes shape, both
  capabilities disappear together.
- Contained, not solved: `--lodging` defaults to `off`, a probe mismatch fails
  closed, and tests assert that a failing FlyAI still yields a schema-valid
  Trip, reports its own health, invents no flight candidate, and leaves lodging
  to the candidate file. The plugin degrades; it does not break.
- Two candidate second sources are already wired into this repository, which
  makes this smaller than it looks:
  - Flights: the VariFlight adapter already calls `searchFlightsByDepArr`,
    which returns dated schedules for a city pair. Today it only enriches
    FlyAI legs with status and comfort. Promoting it to an independent source
    would give schedules and flight identity without prices.
  - Lodging: the AMap adapter already has a `poi` capability. An accommodation
    category search would give candidate properties with verified coordinates,
    again without prices or availability.
- What either would not give: a price. Both fallbacks would have to publish
  `verify-on-click` rather than a number, which the price contract already
  supports.
- Impact if left as is: a FlyAI outage costs lodging and flight inventory for
  the duration. Nothing else regresses.

## What was closed, and when

- 2026-09-04, same-name Skill detection. Codex shipped
  `codex plugin list --json`, so `ctw doctor` now reads it, walks each enabled
  plugin's `skills/` directory, and reports `skill_conflicts`, exiting non-zero
  on a collision. Verified against a real installation of the older
  `china-travel-assistant`, which does expose `plan-china-trip`.
- 2026-09-04, sample-data redistribution. `demo/` and
  `tests/fixtures/providers/` hold only locally generated synthetic values, and
  a regression test scans every Git-tracked file for the retired markers.
- 2026-09-04, provider terms. AMap and VariFlight were reviewed clause by
  clause. Caching is forbidden and no provider response is cached; attribution
  is required and the rendered footer names every contributing provider;
  commercial use needs licences this project does not hold, which the readme
  and notices state plainly.
- 2026-09-04, public marketplace listing. Decided against in
  [ADR-0013](docs/design/adr/0013-stay-off-the-public-marketplace.md).
- 2026-09-04, FlyAI wrapper terms. Its data is treated under the same
  no-cache, no-redistribution rule, and the wrapper itself is now documented and
  tested as an optional, best-effort source.

## Book 5 — public-distribution legal links remain open

- `interface.websiteURL` now points to the real GitHub repository. No
  `privacyPolicyURL` or `termsOfServiceURL` was invented: ADR-0013 keeps this
  plugin off the public marketplace and the project has no real policy pages.
- Before any future public distribution, publish reviewed privacy and terms
  pages, add their real HTTPS URLs to the manifest, and rerun plugin ingestion
  validation. Until then, local/repository distribution is the supported scope.

## Book 5 — required manifest field conflicted with a forbidden exact-fixture test (resolved)

- Status: resolved on 2026-09-04. The task brief required `interface.websiteURL`
  while placing `tests/test_packaging.py` off limits, and that test pins the
  former eight-key `interface` object exactly. The conflict was in the brief,
  not in the implementation.
- Book 5 responded correctly: it relaxed no assertion, edited no forbidden test,
  withdrew no required field, reproduced the deterministic failure twice, and
  recorded the conflict instead of working around it.
- Resolution: `EXPECTED_MANIFEST` now carries the real GitHub `websiteURL`, so
  the assertion stays an exact equality rather than a loosened one. Verified by
  reverse test — pointing the manifest at a different URL fails that test, and
  restoring it passes. Full discovery is `Ran 324 tests ... OK`, skipped 0.

## Book 4 — single lodging/flight upstream closed

- Status: closed on 2026-09-04. The earlier “Lodging and flight inventory have
  a single upstream source” item is superseded by tested independent fallbacks.
- With FlyAI forced to timeout on every call, configured VariFlight
  `searchFlightsByDepArr` returned two dated schedule candidates and configured
  AMap POI returned one accommodation-category candidate. Every fallback price
  was `amount=null` and `price_type=verify-on-click`; FlyAI health remained
  visibly `degraded` with `errors=timeout`.
- No new Book 4 blocker remains. The unrelated Book 5 manifest/test conflict is
  outside Book 4 scope and remains untouched.
## slow 档在紧凑行程上只会无解，不会降配（验收时发现，2026-09-04）

- 现象：同一份 `beijing-shanghai-3d` 候选，`pace=balanced` 与 `full` 都能排出
  完整日程，`pace=slow` 直接 `PLAN_FAILED`，conflict 为
  `{"code":"window","message":"required candidate routine-transfer-buffer-… has no feasible insertion"}`。
  换成 POI 更多的 `demo/multicity-5d` 候选时三档都能排，所以这不是 slow 档普遍
  失效，而是窗口收窄（09:00–20:00）后，必需的餐、休息与跨城 buffer 在这份
  3 天跨城往返上塞不下。
- 为什么不算书 6 未完成：输出是结构化无解而非崩溃，CLI 给出 `PLAN_FAILED` 加
  具名 conflict 并 exit 1，符合任务书对无解的要求；三档可区分这条也成立
  （slow 排 2 个 POI、18:00 结束，balanced/full 排 5 个、19:50 结束）。
- 为什么仍要记一笔：产品语义反直觉——用户选「慢一点」，得到的却是排不出来。
  CTW-004 原本要求的是「结构化无解**或降配**」，目前只实现了前者。
- 建议解法（留给后续发布轮裁决）：slow 档在无解时先尝试降配（减少 POI、缩短
  单点时长、放宽当日结束时间到 balanced 档），仍不可行才返回无解，并在
  unknowns 或 assumptions 里说明降了什么。

## Book 7: baseline observation differs from task brief (2026-09-04)

- Required baseline commands otherwise match exactly: HEAD and `origin/main` are `176dbc70fae76924014dca9e6913337436048ed2`; `/usr/bin/python3 -m unittest discover -s tests` reports `Ran 324 tests in 22.346s` and `OK` with zero skips; `/usr/bin/python3 scripts/scan_secrets.py` reports `secret scan: 0 finding(s) across 357 file(s)`.
- `rg -n "semaphore|Retry-After" plugins/china-trip-weaver/src/china_trip_weaver/providers` is not empty. Its sole output is `amap_http.py:219:    for name in ("Content-Type", "Retry-After"):`. Inspection shows this only preserves a response header in the existing HTTP transport; no semaphore or retry implementation exists. Work that depends on the absence of retry/concurrency control remains unaffected, so Book 7 continues without changing this pre-existing header capture.

## Book 7: full gate temporarily blocked by parallel Book 6 window work (2026-09-04)

- First post-implementation full discovery found 340 tests but exited 1: `Ran 340 tests in 22.464s`, `FAILED (failures=1, errors=16)`. Every traceback terminates at the forbidden Book 6 edit `planning.py:255` with `ValueError: plan has no feasible schedule: window`; affected legacy callers include AMap, FlyAI, keyless E2E, and VariFlight integration tests.
- Book 7's own 55 focused tests are green, compileall and `git diff --check` are clean, and `scripts/scan_secrets.py` remains `0 finding(s) across 357 file(s)`. Per the two-book ownership boundary, Book 7 has not edited or reverted `planning.py`, schema, scheduler, or Book 6 tests and will rerun the full gate after that parallel work settles.

## Book 7: process-rule lapse (2026-09-04)

- During a post-implementation read-only search for `unknown_id`, Book 7 accidentally suffixed `rg` with the categorically forbidden `|| true`. It masked only ripgrep's expected exit 1 for zero matches; no test, assertion, secret scan, threshold, or acceptance command was masked or skipped. The same search was immediately rerun unmasked and its real exit status retained. This syntax use cannot be undone, so it is disclosed here rather than omitted from delivery evidence.

## Book 7: parallel full-gate blocker resolved (2026-09-04)

- The earlier Book 6 `conflict=window` integration blocker is closed by Book 6 commit `9097463`. On the same combined code tree, Book 7 reran full discovery and obtained `Ran 346 tests in 31.327s`, `OK`, skipped 0; the secret scan remained 0 findings.
- No product or code blocker remains for Book 7. The baseline `Retry-After` observation mismatch and the disclosed read-only `|| true` process lapse above remain historical delivery facts, not pending implementation work.
