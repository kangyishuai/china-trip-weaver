---
name: plan-china-trip
description: Plan, compare, or locally replan a read-only trip within mainland China for 1-7 days. Use when the user asks for a China itinerary, a city weekend, cross-city transport and lodging choices, an executable day schedule, a disruption-aware revision, or a sourced mobile trip page. Orchestrate the plugin's explicit-only research, provider, scheduling, replanning, and rendering Skills; never book, log in, submit identity, pay, cancel, or change an order.
---

# Plan China Trip

Own the full user request and keep one schema-valid Trip as the only source of truth.

## Boundaries

- Support existing one-day and single-city requests plus ordered multi-city mainland-China trips lasting 2–7 days. Follow `origin → D1 → D2 → …`; multi-city requests are one-way unless the user explicitly says round trip or the final destination is the origin.
- Trips longer than seven days are not supported. For travelers, accept exactly one representation: legacy `origin + travelers`, or `traveler_groups[] + meeting_anchor`. Reject mixed input. Preserve every stable group id/count/origin, default meeting `buffer_minutes` to 60, and stop with a structured conflict if any group cannot reach the anchor by `meet_by` with that buffer.
- Require explicit `group_refs` on every grouped transport leg. Never infer a missing leg owner as the whole party. Keep per-group totals separate from the whole-party transport total in `transport_pricing`.
- Query, compare, schedule, replan, and provide dated official deep links. Never log in, collect identity, hold inventory, book, pay, cancel, or change an order.
- Do not request provider keys in chat. If a user pastes a credential or personal order data, do not repeat it; stop that provider path and ask them to remove and rotate it.
- Run `scripts/ctw doctor --probe` before the first provider call. Read `skill_conflicts` and each provider's separate `credential`, `contract`, `network`, and `business` status; a configured credential alone is never evidence that the provider works. On a Skill `conflict`, stop and show its `notice` verbatim with the reported plugin ids. On `unknown` no Codex CLI could be consulted, so fail closed the same way. Only `clear` may proceed.

## Workflow

1. Require ordered destinations and real dates/date range. Require either one shared `origin + travelers`, or one or more `traveler_groups` plus a meeting anchor; never accept both. Record conservative defaults for soft preferences in `request.assumptions`.
2. Invoke `$research-china-destination` for dated candidates and claims. Save one JSON object with exactly `candidates_version`, `pois`, `lodgings`, `claims`, and `unknowns`; never put transport legs in this file, and treat every lodging there as a candidate rather than an accepted stay.
3. Invoke only the providers the route needs: `$search-china-rail`, `$search-china-air`, `$search-china-lodging`, and `$resolve-china-mobility`. Preserve failures as provider health and use the documented degradation ladder.
4. Invoke `$schedule-china-trip` only after candidate and route-matrix data exist. Derive each day's city from ordered route legs, assigning a cross-city day to its arrival city. Select exactly one stay for every overnight date, or return a structured no-solution result; never leave a night empty, treat every candidate as selected, or drop a hard constraint. Whenever strict `slow` has no solution, try the fixed three-step ladder (daily POI cap, 70% POI/meal duration, balanced end time) in order and append every applied step to `request.assumptions`; preserve an unchanged hard conflict after all three attempts and never degrade silently.
5. Validate the Trip. Invoke `$render-china-trip` only after validation succeeds.
6. For an existing Trip plus a disruption/edit, invoke `$replan-china-trip` with its current revision and locks; do not restart the whole plan.

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
```

`--progress ndjson` writes allowlisted probe/query/degrade/retry/completion events to stderr and never includes credentials or provider response bodies; omit it when progress is not needed. Use `--rail fixture:<file> --offline-fixture --fixed-clock <ISO-8601>` only for deterministic regression runs; use `--rail off` to force dated deep-link degradation without a rail call. For a local edit/disruption, use `scripts/ctw replan --trip trip.json --event event.json --base-revision <N> --output-json trip-r<N+1>.json --output-html trip-r<N+1>.html`.

Read `../../references/candidates.example.json` for the candidate file shape, `../../references/provider-contracts.md` when selecting or degrading providers, and `../../references/credentials.md` when explaining local configuration.
