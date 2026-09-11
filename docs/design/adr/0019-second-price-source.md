# ADR-0019: Whether a second price source is worth adding, per price category

- **Status:** Proposed
- **Date:** 2026-09-11

## Context

The roadmap has carried "第二价源" (a second price source, to cross-check
against the first) as an open item for three months, blocked on "needs a new
ADR." This ADR answers the question directly for each of the four price
categories this project ever produces a Trip price for — rail, flight,
lodging, admission tickets — using only what the code actually does today,
not what the design docs say it should do. No code, schema, or test file is
changed by this ADR.

### Every place a `/price` claim is written today

`git grep -n '"/price"' -- plugins/china-trip-weaver/src` returns exactly 10
call sites:

| Category | File:line | Producer | `price_type` outcome |
|---|---|---|---|
| Ticket (POI) | `candidates.py:951` | `_apply_poi_candidate` (via `add_poi_candidate`, `candidates.py:845`) | `"reference"` when a human supplies `--price`, else an `unknowns` entry (`candidates.py:967`) |
| Lodging (research) | `candidates.py:1081` | `add_lodging_candidate`, `candidates.py:1002` | `"reference"`/`"verify-on-click"` per `candidates.py:1119` |
| Lodging (AMap fallback) | `flyai_inventory.py:521` | `_amap_lodging_candidate`, `flyai_inventory.py:506` | always `"verify-on-click"`, `amount=None` |
| Flight (FlyAI) | `providers/flyai.py:85` | `FlyAIAdapter._flight` | `"partial"` when amount known, else `"unknown"` |
| Lodging (FlyAI) | `providers/flyai.py:127` | `FlyAIAdapter._lodging`, `providers/flyai.py:113` | depends on `_has_lodging_request_context` |
| Rail | `providers/rail12306.py:168` | `Rail12306Adapter.normalize` | `"live"`/`"unknown"` (`providers/rail12306.py:199`) |
| Flight (VariFlight, live tool path) | `providers/variflight.py:198` | `_live_candidates`, `providers/variflight.py:154` | hardcoded `value=None,status="unknown"` — see below |
| Flight (VariFlight, `kind`-shaped path) | `providers/variflight.py:76` | `normalize`, `providers/variflight.py:58-97` | can be non-null — but see below, this branch is unreachable from the live transport |
| Flight (planning-level fallback) | `planning.py:1615` | `_deep_link_leg` | `"unknown"`/`"hypothesis"` static deep-link fallback when no live match |

`providers/__init__.py:1-16` lists the entire adapter registry: `amap`,
`anysearch`, `flyai`, `host_web`, `rail12306`, `variflight` — six adapters,
no more.

### Whether a subject can carry two `/price` claims today, and whether that ever produces `status="conflict"`

`git grep -n 'claim\["status"\] = "conflict"'` (and its `_claims_with_status`
callers) finds **exactly two** production sites, both in `mobility.py`, and
neither is about price:

- `mobility.py:894-901` `_business_claims_with_conflict` — only touches
  `field_path in ("/provider_identity", "/business")`, i.e. a POI's business
  status disagreeing with an official source.
- `mobility.py:933-1002` `_semantic_location_checks` — geographic outliers:
  duplicate coordinates or a POI implausibly far from its claimed city.

`evidence.py:23` `make_claim` and `evidence.py:70` `validate_claim` (cited by
the task book at `evidence.py:1`/`evidence.py:14`) only construct and
shape-validate a single claim; neither compares it against any other claim.
`validate_trip.py:410` `_check_prices` is the only price-aware validator in
the codebase, and it checks internal consistency only — an `"unknown"` price
must carry `amount=null`, and a price's `claim_id` must point to a claim
whose `subject_ref` equals the item's own id (`validate_trip.py:418-422`).
It never compares one entity's price against a different entity's price.
**No code anywhere detects that two independently-produced price claims
describe the same real-world rail seat, flight, room, or ticket, and no
code anywhere sets `status="conflict"` for a price disagreement.** The
`status=conflict` machinery the schema defines (`trip.schema.json:736`) and
`render/html.py` is fully able to display (`_evidence_section`,
`render/html.py:677-695`, sorts by `CLAIM_RISK_ORDER`,
`render/html.py:100-103`, where `conflict` is the single highest-weighted
status) is real and working — it is simply never fed a price claim, because
no producer ever creates the two-claims-on-one-subject situation that would
trigger it.

### Rail: one producer, and no natural second one

`docs/design/04-providers.md:105` scopes rail to "只读
schedule/seat/price/deep link" against 12306. `providers/rail12306.py:168`
is the only `/price` writer; its value is chosen from the *seat classes
inside that same 12306 response* (business/first/second class each has its
own price), not compared against an independent source. No other adapter in
the six-entry registry touches rail. Unlike flights or hotels, there is no
second commercial channel that resells the identical 12306 seat at a
different price — 12306 **is** the price for a specific train and seat
class.

### Flight: the contract promises a cross-price; the wiring to deliver one does not exist

`docs/design/04-providers.md:111` states the intended contract plainly:
"FlyAI 提供候选/deep link，VariFlight 只补
status/comfort/weather/cross-price... 冲突写两个 claims 和
`status=conflict`，不做平均。" Tracing the actual call chain shows this
promise is not wired up:

- `providers/variflight_mcp.py:141-154` `_tool_call` is the only place that
  picks a real MCP tool name; it supports exactly two `action`s —
  `"search"` → tool `searchFlightsByDepArr`, `"comfort"` → tool
  `flightHappinessIndex`. Any other action raises
  `ContractMismatch("unsupported VariFlight action")`.
- `providers/variflight_mcp.py:59-72` `execute()`: `tool_name` can only
  come from `_tool_call`, and it is echoed verbatim into the response body
  (`"tool": tool_name`, L72) that `normalize()` later reads.
- `providers/variflight.py:35-44` `normalize()` dispatches to
  `_live_payload` whenever `tool in ("searchFlightsByDepArr",
  "flightHappinessIndex")` — which, per the two points above, is *always*
  true for a real response.
- `providers/variflight.py:114-152` `_live_payload`'s non-candidate branch
  (used whenever FlyAI already found a flight number, i.e. the normal
  case) issues only a `/status` claim, keyed to FlyAI's own `leg_id` via
  `subject_refs_by_service` (`providers/variflight.py:117,125`). It never
  emits `/price`.
- `providers/variflight.py:154-221` `_live_candidates` (used only when
  FlyAI found nothing at all, so VariFlight becomes the sole flight
  source) hardcodes its `/price` claim to `value=None,
  status="unknown", confidence=0` (`providers/variflight.py:198`) — always,
  regardless of what the row actually contains.
- The **only** place `VariFlightAdapter.normalize` can emit a real,
  non-null `/price` value is the `kind in ("flights", "raw_price")` branch
  at `providers/variflight.py:58-97` (price at L75-80). Reaching it requires
  a response body whose `"tool"` key is *not*
  `"searchFlightsByDepArr"`/`"flightHappinessIndex"` — which the real
  transport never produces (see the two points above). The only thing that
  reaches this branch is
  `tests/fixtures/providers/variflight/raw_price.json` (registered at
  `tests/fixtures/providers/manifest.json:296`), replayed by this
  project's generic fixture-replay test harness, which hands `normalize()`
  a canned body directly and never goes through `_tool_call`.
- `variflight_enrichment.py:125-197` `_enrich_route` — the only caller that
  actually drives `VariFlightAdapter` during planning — issues exactly two
  `adapter.query()` calls per route (search, then comfort). It never builds
  a request that would reach the dead branch above, live or otherwise.

So: today, a flight leg has at most **one** non-null price claim (FlyAI's).
VariFlight contributes `/status`, `/weather`, `/comfort` — genuinely a
second source for those fields — but never a second price. This is why the
conflict forensics above find zero price conflicts in production: there has
never been a second flight price claim for `status="conflict"` to apply to.

### Lodging: two producers exist, but they never recognize each other as the same property

Unlike flights, a lodging candidate from research (`candidates.json`) and a
lodging item FlyAI resolves live **can** both exist in the same planning run
for what a human would call the same hotel — nothing gates that. But:

- `candidates.py:1074` builds the researched lodging's id as
  `stable_id("lodging", entity_city, entity_name, check_in, check_out)`.
- `providers/flyai.py:118` builds FlyAI's own lodging id as
  `stable_id("lodging-flyai", raw.get("shId"), name, request.parameters["check_in"])`.
- `planning.py:794-829` `_merge_lodging_candidates` is the only place these
  two lists meet. It merges `locked + flyai_items + amap_items + unlocked`
  and deduplicates **only** by exact `lodging_id` string equality
  (`planning.py:810-816`). Because the two id schemes use different
  stable-id prefixes (`"lodging"` vs. `"lodging-flyai"`), the *same*
  physical hotel named identically by both sources produces two different
  ids and is never recognized as one entity, merged, or compared.
- `flyai_inventory.py:506-548` `_amap_lodging_candidate` is a third
  lodging producer (AMap POI search, used only as an identity fallback,
  never a price source: `amount` is always `None`). `planning.py:189`
  (`if not inventory.lodgings and active_flyai.mode == "live":`) shows it
  only runs when FlyAI found nothing, so it is mutually exclusive with the
  FlyAI path and irrelevant to the research-vs-FlyAI question.

This was verified by calling the real function directly, not by reading the
code and assuming:

```
$ /usr/bin/python3 lodging_merge_probe.py
merged count: 2
lodging-flyai-demo001-samplehotel-2026-10-16 示例酒店 720.0 live
lodging-demo-city-samplehotel-2026-10-16-2026-10-18 示例酒店 680.0 reference
```

(Script constructs one synthetic researched-candidate lodging item and one
synthetic FlyAI-shaped lodging item, both named "示例酒店", same city and
check-in/check-out, deliberately priced ¥680 vs. ¥720, and passes them to
the unmodified `planning._merge_lodging_candidates`.) Both survive as
separate entities. No dedup, no comparison, no conflict — the two prices for
what the fixture models as one hotel simply appear as two unrelated
itinerary rows.

### Tickets (POI admission price): one source, entered by hand, no live producer exists

`candidates.py:881` `_apply_poi_candidate` writes a `/price` claim with
`price_type="reference"` **only** when a human passes `--price` while
researching (source cited via `source_url`, itself normally the same
official page a researcher would check to cross-verify); otherwise it
records an `unknowns` entry (`candidates.py:967`). None of the three
adapters that research a POI ever populate a price at all —
`providers/amap.py:106`, `providers/amap.py:173`,
`providers/anysearch.py:67`, and `providers/host_web.py:50` all hardcode
`"price": None` in the items they produce. There is no live or API-based
ticket-price producer anywhere in `providers/` to cross-check against.

## Options

### Option A — status quo, no change

Nothing is built. Each category keeps exactly the shape described above.

### Option B — wire VariFlight's already-declared cross-price onto the existing FlyAI leg (flight only)

`_enrich_route` (`variflight_enrichment.py:125`) already proves the pattern
this needs: its comfort request explicitly reuses FlyAI's own `leg_id` as
`subject_ref` (`variflight_enrichment.py:258`,
`"subject_ref": selected["leg_id"]`) so the resulting claim attaches to the
*existing* flight entity instead of creating a new one. A price request
built the same way — `action="price"` (a new `_tool_call` branch calling
`getFlightPriceByCities`, which is already declared in `EXPECTED_TOOLS`,
`providers/variflight.py:15-25`, just never dispatched), with
`subject_ref=selected["leg_id"]` — would let `VariFlightAdapter` emit a
*second* `/price` claim on the *same* `subject_ref` FlyAI's price claim
already uses. That is the one precondition every other piece of this
project's `status=conflict` design already assumes: two claims, one
subject, one field path. No schema change — the `price`/claim shapes
already exist and are already validated (`trip.schema.json:196-222`,
`:736`). The remaining design question this option does not resolve here —
left to the execution book — is the comparison rule itself: how large a
disagreement between FlyAI's and VariFlight's numbers should flip both
claims to `status="conflict"` per `04-providers.md:111`'s "不做平均"
instruction, versus being within normal quote noise.

### Option C — build an identity-matching step for lodging before merging

Replace `_merge_lodging_candidates`'s exact-`lodging_id` dedup
(`planning.py:810-816`) with a matching step that can recognize a
researched candidate and a FlyAI item as the same property — by name
similarity plus same city plus overlapping stay dates, the same shape of
signal `mobility.py`'s POI identity checks already use elsewhere in this
codebase (`mobility.py:904` `_business_conflict`,
`mobility.py:933-1002` `_semantic_location_checks`, though for POIs, not
lodgings). Once matched, the merged lodging entity would carry both price
claims, and only then could a real price disagreement produce
`status="conflict"`. This is strictly more work than Option B: it is new
matching logic with a real false-positive risk (merging two different
hotels that happen to share a common name fragment) and a real
false-negative risk (missing a genuine match because of name-phrasing
differences), neither of which Option B's flight case faces — a flight's
identity is already exact (`flight_no + airports + local date`,
`04-providers.md:111`), so nothing needs to be "matched," only re-keyed
onto FlyAI's existing subject.

### Option D — build a new official-source adapter for ticket prices

Add a seventh provider adapter that queries an official ticketing source
per POI and emits a second `/price` claim keyed to the *same* `poi_id`
research already assigns (`poi_id = stable_id("poi", city, name, category)`,
`candidates.py:914`, is deterministic and adapter-independent, so — unlike
lodging — no new matching step would be needed here). The cost is that no
such adapter, or precedent for one, exists anywhere in this repository
today: `providers/` has no ticketing-API integration, and per
`04-providers.md`'s own POI section this project's POI research already
runs through host-web/AnySearch, general-purpose search tools with no
structured price field (confirmed above — all three POI adapters hardcode
`price: None`). Building this is a new external integration from zero, the
same category of work the "AnySearch real contract" book
(`docs/history/progress-2026-09-03-to-06.md`, cited in ADR-0017) took an
entire development wave to land for a *research* capability, not even a
price one.

## Decision

**Per category:**

1. **火车票 (rail): 不做。** There is no independent second channel that
   resells an identical 12306 seat at a different price to cross-check
   against — 12306's own price *is* the answer for a given train and seat
   class. Option A (status quo) stands.

2. **机票 (flight): 做 — Option B.** This is the cheapest of the three
   real options here and the only one with an already-shipped pattern to
   copy (`variflight_enrichment.py:258`'s comfort-request re-keying). The
   contract already promises this (`04-providers.md:111`), the schema
   already supports it, the tool is already declared
   (`providers/variflight.py:15-25`) — the only thing genuinely missing is
   a `_tool_call` branch and one more `adapter.query()` call inside
   `_enrich_route`, plus a comparison rule for when to flip both claims to
   `status="conflict"`.

3. **住宿 (lodging): 做，但排在机票之后 — Option C.** The value is real
   (two producers already independently research the same city on the same
   dates), but the cost is categorically higher than flight's: it requires
   new identity-matching logic this codebase has never built for lodgings
   specifically, with real false-positive/false-negative risk that Option
   B does not carry. Recommend sequencing this as the next book *after*
   Option B ships and its comparison-rule design is proven out, not in
   parallel with it.

4. **门票 (POI admission): 不做.** The "second source" a human already
   consults is the official page they cite as `source_url` when entering
   the reference price by hand — that check already happens, just not
   automated. Automating it needs Option D, a brand-new external
   integration with zero precedent in `providers/` today, for a category
   where research has never needed more than a single cited number. Lowest
   benefit-to-cost ratio of the four.

## Consequences

Draft acceptance commands for whichever book the leader greenlights next.
None of these should pass yet — they describe the target, not today's
state:

**If Option B (flight) is greenlit:**

1. `git diff main --stat -- plugins/china-trip-weaver/schema` → empty
   (the claim/price shapes already exist; no schema change).
2. `/usr/bin/python3 -m unittest tests.test_variflight_live -v` → a new
   test asserts that, given a route FlyAI already resolved, the enriched
   flight's `claim_ids` includes a VariFlight-provenance `/price` claim
   whose `subject_ref` equals the FlyAI `leg_id` — not a separate
   `leg-vf-*` subject.
3. A fixture pair where FlyAI and VariFlight disagree by more than the
   comparison rule's threshold → both price claims end up
   `status="conflict"`; a pair within tolerance → both stay at their
   original status (no false conflict).
4. `/usr/bin/python3 -m unittest discover -s tests` → `OK`, same skip
   count as this book's baseline (regression gate).

**If Option C (lodging) is greenlit, after B:**

1. `git diff main --stat -- plugins/china-trip-weaver/schema` → empty
   (matching is a planning-time step; no new fields required beyond
   reusing `status="conflict"`).
2. A fixture pair — one researched candidate, one FlyAI item, same name/
   city/overlapping dates, different prices — merges into **one** lodging
   entity carrying two price claims with `status="conflict"`, not two rows
   (the regression this ADR's probe demonstrated).
3. A fixture pair with genuinely different hotels in the same city keeps
   two separate lodging entities (false-positive guard).
4. `/usr/bin/python3 -m unittest discover -s tests` → `OK`, same skip
   count as this book's baseline.
