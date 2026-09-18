---
name: resolve-china-mobility
description: Resolve mainland-China POIs, geocodes, coordinate provenance, and walking, transit, driving, or cycling route-time matrix cells through the AMap adapter. Invoke explicitly from plan-china-trip after candidates exist or when affected hops need revalidation; do not schedule a trip or treat straight lines as routes.
---

# Resolve China Mobility

Resolve only the candidate endpoints supplied by the parent Skill.

- Preserve provider-native coordinates and explicitly derive WGS84/GCJ02 at most once. AMap requests always consume GCJ02.
- Resolve POI and lodging identity with AMap v5 text search scoped by `city_limit=true` before geocoding. Preserve the provider POI id, matched name, formatted address, district, adcode, type, and business fields as claims; geocode only a complete address. A lodging is never geocoded by its bare city and name.
- Treat a first/second name-similarity margin below `0.15`, or any provider administrative city that disagrees with the candidate city, as `identity_conflict`. Keep coordinates unknown and never replace the provider's city with the candidate city. The conflict reason includes at most three sanitized provider candidate names, their city/district, and copyable suggested names; it never includes the raw response.
- Before appending a human-written POI name, `ctw candidates add-poi ... --verify-name` may run one bounded AMap name-check step. Report `unique`, `ambiguous`, or `unavailable` with the same sanitized candidate projection. Missing credentials and lookup failures never block the candidate write or populate coordinates.
- Build a bounded directed matrix for plausible adjacency, locked anchors, transport endpoints, and lodging; do not issue an unbounded all-pairs query.
- Emit `semantic_outlier` for isolated same-city points, distinct entities sharing a coordinate, or same-day adjacent POIs over 50 km apart. These warnings do not block planning, but implicated claims must not remain `verified`.
- A live/cached cell needs route evidence and query time. A static cell needs an explicit method and conservative buffer. Missing or unreachable cells are not routes.
- Fail closed on endpoint/pagination/response drift and return health plus degradation rung. Do not choose the daily order.
- Do not substitute host search or AnySearch for an unavailable AMap capability. Keep mobility degradation separate from the destination-search rung recorded by `$research-china-destination`.
- A city, district, or adcode's current AMap forecast is available separately through `ctw weather`; it only covers today-plus-3-days and reports `out_of_window` rather than guessing further out. This command is informational only — it does not attach weather to a Trip or Journey and is not part of the candidate-resolution matrix below.
- A `ctw weather --output-json` result can be folded back into an existing Journey with `ctw journey weather`: it matches each `forecasts[]` row to a day by date and `query`, writes `day.weather` (or a `weather_no_results` unknown), and advances the Journey's revision by exactly one no matter how many child Trips changed. A run that changes no day exits 2 and writes nothing; this command never modifies the `--journey` input file.
- A meal slot's AMap-ranked nearby-dining reference is available the same way through `ctw dining`, anchored on the nearest same-day slot with known coordinates (searching backward then forward, never across a `transport` slot) within a 1500 m default radius, keeping up to 3 rated venues in AMap's own `sortrule=weight` order; `ctw journey dining` folds its result back into an existing Journey exactly like `ctw journey weather` — a `trigger=dining` patch per changed child Trip, revision advanced by exactly one, `JOURNEY_DINING_NOOP` exit 2 when nothing changes, and the `--journey` input never modified.
- A POI or lodging still missing coordinates can be resolved on its own with `ctw locate` (skipping the planner's `poi-routine-meal-*` placeholders, at most 12 POIs per child Trip with lodgings uncapped, the same identity and coordinate-cluster checks as candidate resolution above); `ctw journey locate` folds its result back into an existing Journey the same way — filling in only the entities that were still missing coordinates, a `trigger=provider_change` patch per changed child Trip, revision advanced by exactly one, `JOURNEY_LOCATE_NOOP` exit 2 when nothing changes, and the `--journey` input never modified. Locate a lodging's coordinates before the arrival day's `ctw dining` so its dinner slot has an anchor; each fold writes the next `journey-rN.json` and never overwrites an earlier one, as in the commands below.

Inspect a bounded live matrix directly or return its normalized cells to the parent. When AMap is unavailable, `ctw plan` builds only labeled static estimates. Files for one trip live together under `plans/<name>/` in the project root that invoked this plugin:

```bash
scripts/ctw candidates add-poi plans/<name>/candidates.json --name "景点全名" --city "城市" --category poi --source-url https://example.invalid/source --verify-name
scripts/ctw mobility --candidates plans/<name>/candidates.json --modes transit,walking --output-json plans/<name>/mobility.json
scripts/ctw plan --request plans/<name>/request.json --candidates plans/<name>/candidates.json --rail off --mobility live --output-json plans/<name>/trip.json --output-html plans/<name>/trip.html
scripts/ctw validate plans/<name>/trip.json
scripts/ctw weather --city "城市" --output-json plans/<name>/weather.json
scripts/ctw journey weather --journey plans/<name>/journey.json --weather-result plans/<name>/weather.json --base-revision 1 --output-json plans/<name>/journey-r2.json
scripts/ctw locate --journey plans/<name>/journey-r2.json --output-json plans/<name>/locate.json
scripts/ctw journey locate --journey plans/<name>/journey-r2.json --locate-result plans/<name>/locate.json --base-revision 2 --output-json plans/<name>/journey-r3.json
scripts/ctw dining --journey plans/<name>/journey-r3.json --output-json plans/<name>/dining.json
scripts/ctw journey dining --journey plans/<name>/journey-r3.json --dining-result plans/<name>/dining.json --base-revision 3 --output-json plans/<name>/journey-r4.json
```

Never turn an AMap fixture response into live output outside an explicit offline fixture test.
