---
name: plan-china-trip
description: Plan, compare, or locally replan a read-only trip within mainland China for 1-7 days. Use when the user asks for a China itinerary, a city weekend, cross-city transport and lodging choices, an executable day schedule, a disruption-aware revision, or a sourced mobile trip page. Orchestrate the plugin's explicit-only research, provider, scheduling, replanning, and rendering Skills; never book, log in, submit identity, pay, cancel, or change an order.
---

# Plan China Trip

Own the full user request. Keep one schema-valid Trip as the only source of truth for 1-7 days, or one schema-valid Journey containing complete standalone Trips for a longer request.

## Boundaries

- Every standalone Trip covers 1-7 days. Follow `origin → D1 → D2 → …`; multi-city requests are one-way unless the user explicitly says round trip or the final destination is the origin. Never widen the Trip limit for a longer request.
- For a request longer than seven days, build one Journey with `ctw journey plan`. Split at cross-city days first and then at seven-day boundaries; retain every child as a complete Trip document, record adjacent dates, boundary lodging, cross-segment transport, and the aggregate budget, then validate with `ctw journey validate`. Do not create a separate overview page or booking checklist.
- For travelers, accept exactly one representation: legacy `origin + travelers`, or `traveler_groups[] + meeting_anchor`. Reject mixed input. Preserve every stable group id/count/origin at Journey scope, default meeting `buffer_minutes` to 60, and stop with a structured conflict if any group cannot reach the anchor by `meet_by` with that buffer.
- Require explicit `group_refs` on every grouped transport leg. Never infer a missing leg owner as the whole party. Keep per-group totals separate from the whole-party transport total in `transport_pricing`.
- Query, compare, schedule, replan, and provide dated official deep links. Never log in, collect identity, hold inventory, book, pay, cancel, or change an order.
- Do not request provider keys in chat. If a user pastes a credential or personal order data, do not repeat it; stop that provider path and ask them to remove and rotate it.
- Run `scripts/ctw doctor --probe` before the first provider call. Read `skill_conflicts` and each provider's separate `credential`, `contract`, `network`, and `business` status; a configured credential alone is never evidence that the provider works. On a Skill `conflict`, stop and show its `notice` verbatim with the reported plugin ids. On `unknown` no Codex CLI could be consulted, so fail closed the same way. Only `clear` may proceed.

## Workflow

1. Require ordered destinations and real dates/date range. Require either one shared `origin + travelers`, or one or more `traveler_groups` plus a meeting anchor; never accept both. Record conservative defaults for soft preferences in `request.assumptions`. Choose `ctw plan` for 1-7 days and `ctw journey plan` for longer ranges.
2. Invoke `$research-china-destination` for dated candidates and claims. Save one JSON object with exactly `candidates_version`, `pois`, `lodgings`, `claims`, and `unknowns`; never put transport legs in this file, and treat every lodging there as a candidate rather than an accepted stay.
3. Invoke only the providers the route needs: `$search-china-rail`, `$search-china-air`, `$search-china-lodging`, and `$resolve-china-mobility`. Preserve failures as provider health and use the documented degradation ladder.
4. Invoke `$schedule-china-trip` only after candidate and route-matrix data exist. Derive each day's city from ordered route legs, assigning a cross-city day to its arrival city. Select exactly one stay for every overnight date, or return a structured no-solution result; never leave a night empty, treat every candidate as selected, or drop a hard constraint. Whenever strict `slow` has no solution, try the fixed three-step ladder (daily POI cap, 70% POI/meal duration, balanced end time) in order and append every applied step to `request.assumptions`; preserve an unchanged hard conflict after all three attempts and never degrade silently.
5. Validate every Trip. For a Journey, also validate its segment connections and total ledger; invoke `$render-china-trip` only for a standalone Trip after its validation succeeds.
6. For an existing child Trip plus a disruption/edit, invoke `$replan-china-trip` with that Trip's current revision and locks; do not invent a second Journey-specific replanner.

## Command flow

From the plugin root, run:

```bash
scripts/ctw candidates init candidates.json
scripts/ctw candidates add-poi candidates.json --name "..." --city "..." --category "..." --source-url "https://..."
scripts/ctw candidates add-lodging candidates.json --name "..." --city "..." --check-in YYYY-MM-DD --check-out YYYY-MM-DD --source-url "https://..."
scripts/ctw validate-candidates candidates.json
scripts/ctw plan --progress ndjson --request request.json --candidates candidates.json --rail live --mobility live --lodging live --output-json trip.json --output-html trip.html
scripts/ctw validate trip.json
scripts/ctw validate-html trip.html trip.json
scripts/ctw journey plan --progress ndjson --request long-request.json --candidates candidates.json --rail live --mobility live --lodging live --output-json journey.json
scripts/ctw journey validate journey.json
```

`--progress ndjson` writes allowlisted probe/query/degrade/retry/completion events to stderr and never includes credentials or provider response bodies; omit it when progress is not needed. Use `--rail fixture:<file> --offline-fixture --fixed-clock <ISO-8601>` only for deterministic regression runs; use `--rail off` to force dated deep-link degradation without a rail call. For a local edit/disruption, use `scripts/ctw replan --trip trip.json --event event.json --base-revision <N> --output-json trip-r<N+1>.json --output-html trip-r<N+1>.html`.

Read `../../references/candidates.example.json` for the candidate file shape, `../../references/provider-contracts.md` when selecting or degrading providers, and `../../references/credentials.md` when explaining local configuration.
