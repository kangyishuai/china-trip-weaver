# China Trip Weaver

**English** · [简体中文](README.zh-CN.md)

China Trip Weaver is a Codex plugin for evidence-backed, read-only trips within mainland China. It turns an independent request plus researched candidates into one versioned Trip JSON, or a Journey containing complete Trips for a longer route; queries pinned 12306 rail, AMap route matrices, FlyAI lodging/flight inventory, and optional VariFlight status/comfort enrichment; schedules without conflating comparisons with selected legs; and renders deterministic phone-first HTML.

It never logs in, submits identity, holds inventory, books, pays, cancels, or changes an order. Provider credentials stay in process-local environments and never appear in argv, logs, fixtures, Trip, HTML, or Git.

## Scope

The planner supports existing one-day and single-city trips plus ordered multi-city trips lasting 2–7 days. For multiple destinations it follows `origin → D1 → D2 → …`; the default is one-way, and a return is added only when the request explicitly says round trip or the final destination is the origin. Each travel day belongs to the city reached by that day's route leg, and every overnight date must resolve to exactly one explicitly selected stay in that city. Researched lodging candidates are not selected stays; if no candidate can cover a night, planning returns a structured no-solution result.

Requests longer than seven days become one Journey whose complete, standalone child Trips each retain the 1–7 day limit. By default the split minimizes the number of child Trips while honoring the seven-day cap and the researched lodging chain. `ctw journey plan --expected-segment-days N` accepts an integer from 1 to 7 and prefers segment lengths near `N`, but never overrides those hard constraints. Adjacent dates, boundary lodging, cross-segment transport, and the aggregate budget remain explicit and validated. After a child Trip is replanned, Journey validation recomputes both sides of every seam and reports structured lodging or cross-segment transport gaps instead of silently shifting a later segment. The Journey overview shows the whole route, segment dates, total budget range, a deadline-ordered booking/verification checklist, and every degraded capability, conflicting claim, and unresolved unknown without exposing internal ids. Each checklist item carries a `deadline_kind`: a rail leg reads `presale_open` (the 12306 presale window opens 14 days before departure, so the item is due on the sale-open date, not the departure date) unless the Trip already carries an explicit `/booking_deadline` claim, in which case it reads `declared`; other transport reads `departure` and lodging reads `check_in`.

AMap calls in a Journey are budgeted per resulting Trip. The default Journey-wide allowance is 80 calls per Trip, with every Trip still capped at 80; `ctw journey plan --amap-total-max-calls N` sets a non-negative total ceiling and distributes it as evenly as possible across the resulting Trips. The ceiling never increases the default allowance.

When AMap actually attempts to locate a POI but cannot resolve its identity or coordinates, the Trip keeps an actionable coordinate record in `unknowns`, including sanitized reasons and name suggestions when available. Turning mobility off or lacking an AMap key does not manufacture these records.

POI search and geocoding use the same administrative-area rule: a researched city or district may match either the provider's city or its district. A district/county name on one side and its enclosing prefecture-level city on the other therefore do not create a false location mismatch, while unrelated administrative areas still fail closed.

Traveler input has two mutually exclusive forms: the existing `origin + travelers` form, or `traveler_groups[] + meeting_anchor`. Every group supplies a stable `group_id`, its own traveler count and origin, plus an optional mobility profile. The meeting anchor supplies a location and `meet_by`; `buffer_minutes` defaults to 60, and any group that cannot arrive with that much buffer produces a structured conflict. When the earliest-arriving rail candidate cannot meet that buffer, the meeting leg falls back to the earliest-arriving compliant flight from the same live flight search instead; a structured conflict is only raised when neither rail nor any flight candidate can meet it. Mixed input is rejected and the emitted Trip preserves only the selected representation. Validation, rendering, and inventory lookup consume the grouped form directly. Grouped transport legs carry explicit `group_refs`; `transport_pricing` exposes each group's total and the whole party's transport total separately.

`pace=slow` first uses the strict slow profile. If that schedule has no solution, the planner cumulatively tries a smaller daily POI cap, 70% POI/meal durations, and finally the balanced 21:30 day end. It stops at the first feasible result and appends every applied step to `request.assumptions`; hard conflicts that none of those steps can change keep their original structured conflict and report all attempted relaxations.

## Requirements

- Codex Desktop's bundled CLI or a compatible Codex CLI.
- System Python 3.9 or newer for the runtime.
- Node/npm only when a pinned MCP/CLI provider is actually invoked; nothing is installed globally.
- Google Chrome is used only by the optional renderer QA script, not by the plugin runtime.

The plugin installs from a local marketplace pointed at a clone of this repository. It is not published to a public Codex marketplace: provider terms, data caching and redistribution, map attribution, and listing metadata are still unresolved. See [`BLOCKED.md`](BLOCKED.md) before changing that.

Licensed under the [MIT License](LICENSE). The licence covers this repository's own code and documentation. It grants no rights over data returned by AMap, Fliggy/FlyAI, VariFlight, or China Railway. Those providers forbid caching and redistributing their data and require a paid licence or written contract for commercial use, so this repository is for personal, non-commercial use unless you obtain those licences yourself; see [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

## Local credentials

FlyAI is an optional, best-effort source. It is an unofficial third-party wrapper around Fliggy whose command surface has drifted before, so `--lodging` defaults to `off` and any FlyAI failure degrades only lodging and flight inventory, never the plan.

`ctw doctor` reports only `configured` or `missing` for AMap, FlyAI, VariFlight, and AnySearch. It never prints a value, prefix, suffix, hash, or length. It also reports `skill_conflicts`, which detects another enabled plugin exposing a Skill of the same name and exits non-zero on a conflict.

Credentials come from the launching environment first, then from `~/.config/china-trip-weaver/credentials.env`. On POSIX that file must be a current-user-owned regular file at mode exactly `0600`. Do not pass a value on a command line or paste it into chat.

```bash
plugins/china-trip-weaver/scripts/ctw doctor
```

The live path uses `AMAP_WEBSERVICE_KEY`, `FLYAI_API_KEY`, `VARIFLIGHT_API_KEY` (`X_VARIFLIGHT_KEY` remains read compatibility), and `ANYSEARCH_API_KEY`. AnySearch is called only by the explicit `ctw research` command and `ctw doctor`'s probe; `ctw plan` never calls it. Every Node provider gets its own temp/config/cache directories and an isolated `os.homedir()`; those and the npm cache live under the directory that contains `plugins/` (the installed plugin's cache directory when installed from the local marketplace). `ctw doctor` reports that location as `runtime_root`; it can be deleted at any time and is rebuilt automatically on the next live call.

## Install or refresh into the local Codex (automated)

Clone this repository first; every path below is relative to the clone.


Every iteration or version bump must end by refreshing the plugin installed in the local Codex. One script does the whole thing: it registers the local marketplace if needed, runs `codex plugin add` (which refreshes the cached copy from this repository, including version changes), and verifies that `codex plugin list` reports `installed, enabled` with the manifest version and that the cache matches the source byte for byte.

```bash
scripts/install_local_plugin.sh          # install or refresh, then verify
scripts/install_local_plugin.sh --check  # verify only, change nothing
```

Set `CODEX_BIN` if `codex` is not on PATH (the script falls back to the Codex Desktop embedded CLI). Set `CODEX_HOME` to a temporary directory to exercise the script against an isolated Codex home instead of the real one. After a refresh, start a new Codex task so the new Skills and MCP configuration load; restart Codex Desktop if a Skill does not appear.

## Install from the local marketplace

From this repository root:

```bash
CODEX_HOME=/path/to/an/isolated/codex-home \
  /Applications/ChatGPT.app/Contents/Resources/codex \
  plugin marketplace add "$PWD"

CODEX_HOME=/path/to/an/isolated/codex-home \
  /Applications/ChatGPT.app/Contents/Resources/codex \
  plugin add china-trip-weaver@china-trip-weaver-local

CODEX_HOME=/path/to/an/isolated/codex-home \
  /Applications/ChatGPT.app/Contents/Resources/codex \
  plugin list
```

The expected result is `china-trip-weaver@china-trip-weaver-local`, with the version matching `plugin.json`'s `version` field, status `installed, enabled`. Use a fresh Codex task after installing or updating so its nine Skills and MCP configuration are reloaded.

For Codex Desktop UI installation, add this repository as a local marketplace, ensure `china-travel-assistant` is disabled, install China Trip Weaver Local, restart, and create a new task. The two plugins must not be enabled together because both expose `plan-china-trip`.

## Candidate input

`candidates.json` contains exactly `candidates_version`, `pois`, `lodgings`, `claims`, and `unknowns`. It does not contain transport legs. Its entity shapes reuse the frozen Trip `$defs`, and every entity/price/opening-window claim reference must resolve.

`ctw candidates add-poi ... --verify-name` checks the POI name with AMap before writing. It reports a sanitized `unique`, `ambiguous`, or `unavailable` result with at most three candidate-name suggestions, never writes a coordinate from this check, and still writes the candidate when the key is missing or the provider check fails.

`ctw candidates fix-names` reads the AMap unknowns a Trip or Journey records against a place — a coordinate that could not be settled, and a coordinate that did resolve while its name stayed unsettled — and reports canonical names that can be sent back to the matching researched candidates. It only reports by default; add `--apply` to write uniquely determined names to the candidate file. Ambiguous, conflicting, unchanged, or malformed suggestions are left for manual review and are never changed automatically.

For those manual results, `--export-manual NAME-REVIEW.json` writes a human-fillable JSON list and never changes the candidate file. Fill any entry's `chosen` field, then pass that list to `--apply-manual NAME-REVIEW.json`; every non-empty choice must exactly equal one of that entry's current `suggested_names`, while empty or missing choices are skipped. An unknown `ref_id` or any other choice aborts the whole apply and leaves the candidate file byte-for-byte unchanged. To use a completely custom name, edit the candidate file directly and run `validate-candidates` instead.

```bash
plugins/china-trip-weaver/scripts/ctw validate-candidates demo/candidates.json
plugins/china-trip-weaver/scripts/ctw candidates fix-names CANDIDATES.json --trip TRIP_OR_JOURNEY.json
plugins/china-trip-weaver/scripts/ctw candidates fix-names CANDIDATES.json --trip TRIP_OR_JOURNEY.json --apply
plugins/china-trip-weaver/scripts/ctw candidates fix-names CANDIDATES.json --trip TRIP_OR_JOURNEY.json --export-manual NAME-REVIEW.json
plugins/china-trip-weaver/scripts/ctw candidates fix-names CANDIDATES.json --trip TRIP_OR_JOURNEY.json --apply-manual NAME-REVIEW.json
```

See [`candidates.example.json`](plugins/china-trip-weaver/references/candidates.example.json) and the machine contract [`candidates.schema.json`](plugins/china-trip-weaver/schema/candidates.schema.json).

## Run the synthetic demo

The checked-in Beijing→Shanghai demo is deterministic synthetic output. It is generated from repository fixtures with every remote provider disabled; the rail fixture returns a synthetic empty result so the plan exposes only labeled 12306 public-query fallbacks.

```bash
plugins/china-trip-weaver/scripts/ctw plan \
  --request demo/request.json \
  --candidates demo/candidates.json \
  --rail fixture:tests/fixtures/providers/rail12306/empty.json \
  --mobility off \
  --lodging off \
  --aviation off \
  --offline-fixture \
  --fixed-clock 2026-09-04T00:00:00+08:00 \
  --output-json demo/trip.json \
  --output-html demo/trip.html

plugins/china-trip-weaver/scripts/ctw validate demo/trip.json
plugins/china-trip-weaver/scripts/ctw validate-html demo/trip.html demo/trip.json
/usr/bin/python3 scripts/scan_secrets.py demo/trip.json demo/trip.html
```

Use your own credentials to run the same planning command with `--rail live --mobility live --lodging live --aviation auto`, omit the two fixture-only options, and write the result under `.tmp/`; that produces current live results without putting them back into Git. A credentialed acceptance run has demonstrated the following capability counts: two dated rail legs, 20 route cells, ten lodging candidates, twenty flight comparisons, plus status and comfort enrichment. Those counts describe capability only; no provider items from that run are redistributed here.

The one-day round trip under [`demo/guangzhou-shenzhen/`](demo/guangzhou-shenzhen/) is generated with the same synthetic empty-result fixture. A no-overnight request makes no lodging query, and the demo never invents provider inventory.

The grouped-departure example under [`demo/grouped-departures/`](demo/grouped-departures/) sends two synthetic traveler groups from Beijing and Guangzhou to a Shanghai meeting anchor. Its checked-in Trip keeps the strict grouped request shape and visibly shows each origin, the three-person total, group-owned transport legs, and per-group/whole-party transport pricing.

The fifth example under [`demo/journey-16d/`](demo/journey-16d/) is a fully synthetic 16-day Shanghai → Hangzhou → Suzhou Journey split into three complete Trips. Its checked-in files are owned exclusively by `scripts/build_renderer_fixtures.py`, whose fixed clock `2026-09-05T09:00:00+08:00` intentionally differs from the `2026-09-04T00:00:00+08:00` clock used by the other four demos; do not hand-run the fifth demo separately. Regenerate it with `/usr/bin/python3 scripts/build_renderer_fixtures.py`, then validate both artifacts with:

```bash
plugins/china-trip-weaver/scripts/ctw journey validate demo/journey-16d/journey.json
plugins/china-trip-weaver/scripts/ctw journey validate-html demo/journey-16d/journey.html demo/journey-16d/journey.json
```

Railway/network/provider failure never becomes fake success. Each capability preserves its own health and either uses a labeled fallback or stops at a typed unknown. AMap is capped at 80 calls per Trip and no more than 2 QPS; a Journey follows the total allocation described above. FlyAI masked prices such as `¥4xx` are always `verify-on-click`; only exact numeric prices are `live`. FlyAI coordinates remain `provider-unknown` and are never converted or mapped.

VariFlight partial enrichment is reported truthfully. If flight search or status data succeeds but a later comfort query fails, the usable flights and status claims are retained while VariFlight health becomes `degraded`; it is never shown as fully healthy.

When 12306 returns multiple possible stations and AMap is available, the plugin uses the city center and exact-match railway-station POIs to attach straight-line distance signals. It preserves every station candidate, orders known distances nearest-first and unknown distances last, and never chooses a station for the user; failure to obtain a distance does not degrade an otherwise successful railway result.

Station name resolution itself runs up to four layers before giving up, and never guesses a station on the caller's behalf: an exact station name, the city's representative station, then every station 12306 lists for that city; if all three come back empty, the request is retried once with the city name's administrative suffix (市/县/区/…) stripped. When an ambiguous result still needs distances and AMap is configured, a same-city POI search (`city_limit=true`) is tried first, then a nationwide search (`city_limit=false`) capped at 80 km from the city center fills in a same-named station that actually sits in a neighboring administrative area. If all four 12306-side attempts are still empty and an AMap key is configured, one last best-effort call to AMap's `poi_around` capability searches real train stations within 50 km of the place's center and cross-checks each one against 12306's own station table before offering it as a distance-annotated candidate; the result carries the `station_nearby_fallback` warning, and a name 12306 does not recognize is dropped rather than guessed.

12306's `get-tickets` groups results by city, so a resolved query can still return direct rows that actually depart from or arrive at an unrelated station sharing the same city group. Each row is kept only if its `from_station`/`to_station` matches the resolved station (or, when no station resolution is present, starts with the requested place name after stripping a trailing 市/县/区); non-matching rows are dropped and counted in a `station_rows_filtered:<n>` warning, and a result left with zero rows adds `station_rows_all_filtered` on top of the existing no-results path. `get-interline-tickets` connections are never filtered this way. Because filtering runs after 12306's own row limit, `ctw rail` requests the provider maximum of 30 rows by default, but can still return fewer legs after filtering.

## Run without provider keys

For a keyless run, remove provider variables from the launching environment and ensure the local credential file is absent. Use `--mobility off --lodging off --aviation off`; rail remains a public live query or can also be `off`. Static estimates and deep links stay explicitly labeled.

For a deterministic offline developer run:

```bash
plugins/china-trip-weaver/scripts/ctw plan \
  --request tests/fixtures/e2e/beijing-shanghai-3d/request.json \
  --candidates tests/fixtures/e2e/beijing-shanghai-3d/candidates.json \
  --rail fixture:tests/fixtures/e2e/beijing-shanghai-3d/rail.json \
  --mobility off \
  --lodging off \
  --aviation off \
  --offline-fixture \
  --fixed-clock 2026-09-04T00:00:00+08:00 \
  --output-json .tmp/trip.json \
  --output-html .tmp/trip.html
```

This mode is for regression testing only and labels outside-presale/fixture results as degraded static data; it is never presented as live inventory. Separate fixtures also cover a two-day Shanghai-local request with zero railway calls and a four-day Beijing-to-Hangzhou request.

## Other commands

```text
ctw doctor
ctw validate TRIP.json
ctw validate-candidates CANDIDATES.json
ctw candidates add-poi CANDIDATES.json --name NAME --city CITY --category CATEGORY --source-url URL [--verify-name]
ctw candidates import CANDIDATES.json --items ITEMS.json [--queried-at ISO] [--dry-run]
ctw candidates fix-names CANDIDATES.json --trip TRIP_OR_JOURNEY.json [--apply | --export-manual NAME-REVIEW.json | --apply-manual NAME-REVIEW.json]
ctw canonicalize TRIP.json
ctw rail --date YYYY-MM-DD --from CITY --to CITY --output-json rail-result.json
ctw research --city CITY --query TEXT [--max-results N] --output-json research.json
ctw mobility --candidates CANDIDATES.json --modes transit,walking --output-json mobility.json
ctw lodging --city CITY --check-in YYYY-MM-DD --check-out YYYY-MM-DD --output-json lodging.json
ctw air --origin CITY --destination CITY --date YYYY-MM-DD --output-json air.json
ctw replan --trip TRIP.json --event EVENT.json --base-revision N --output-json TRIP-rN.json --output-html TRIP-rN.html [--rail-result RAIL.json]
ctw render TRIP.json --output TRIP.html
ctw validate-html TRIP.html TRIP.json
ctw journey plan --request REQUEST.json --candidates CANDIDATES.json [--expected-segment-days N] [--amap-total-max-calls N] --output-json JOURNEY.json
ctw journey validate JOURNEY.json
ctw journey render JOURNEY.json --output JOURNEY.html
ctw journey validate-html JOURNEY.html JOURNEY.json
ctw journey extract --journey JOURNEY.json --trip-id TRIP_ID --output-json TRIP.json
ctw journey assemble --request REQUEST.json --trip TRIP.json [--trip TRIP.json ...] [--expected-segment-days N] [--fixed-clock ISO] --output-json JOURNEY.json
ctw journey assemble --journey JOURNEY.json --replace-trip TRIP-rN.json --base-revision N [--reason REASON] [--fixed-clock ISO] --output-json JOURNEY.json
```

The runtime uses no third-party Python package. Trip and Journey renderers refuse invalid input; both HTML validators block structural, CSP, remote-resource, unsafe-link, secret, fact-mapping, traceability, and transaction-action violations.

`ctw replan`'s `refresh` event replaces one rail leg with a freshly queried service: run `ctw rail --output-json` first, then pass that file's path as `--rail-result`. `--rail-result` is required for a `refresh` event and rejected for every other event type. When the event omits `service_number`, the default selection only considers same-day services that depart no earlier than the previous slot's end before picking the earliest arrival, raising `refresh_overlap` (naming the candidate count and that end time) only when none qualify; an explicit `service_number` that still matches more than one same-day row with different arrival times raises `refresh_service_ambiguous` unless the event's `arrive_at` (a full ISO timestamp or a bare `HH:MM`) picks one. A `suspend` event removes a leg that stopped running (a cancelled train, a suspended ferry crossing) together with its slot, budget-ledger line, and any now-orphaned claims in one patch, swapping the slot for a `free`- or `poi`-kind `replacement_slot`; the patch `trigger` is `disruption`.

## Tests

```bash
/usr/bin/python3 -m unittest discover -s tests -v
/usr/bin/python3 scripts/scan_secrets.py
/usr/bin/python3 scripts/scan_secrets.py --credential-values
/usr/bin/python3 scripts/scan_secrets.py --credential-values --git-history
```

On a machine with Codex installed the suite has zero skips; CI runners without Codex skip the three Codex-dependent tests. It covers the frozen Trip schema, Journey segmentation and continuity, candidate validation, credential/process/home isolation, exact-value and captured-data scans, evidence/coordinates, 84 unmistakably synthetic provider fixtures with AMap/FlyAI/VariFlight contract shapes, 20 scheduling goldens, 8 no-solution cases, 4 replan goldens, Trip/Journey renderer adversarial cases and offline browser viewports, Skill/package metadata, and deterministic plus live-path integration scenarios.

Design authority lives in [`docs/design/`](docs/design/00-README.md). Implementation-only additions are [ADR-0009](docs/design/adr/0009-rename-rail-air-skills.md), [ADR-0010](docs/design/adr/0010-candidate-file-planning-and-live-rail.md), and [ADR-0011](docs/design/adr/0011-live-amap-flyai-variflight-boundaries.md); [ADR-0012](docs/design/adr/0012-open-source-under-mit.md) records the MIT licensing decision, [ADR-0013](docs/design/adr/0013-stay-off-the-public-marketplace.md) records why this plugin is not listed on a public marketplace, and [ADR-0014](docs/design/adr/0014-remove-ortools-bridge.md) records the 2026-09-08 removal of the never-wired OR-Tools bridge. [ADR-0015](docs/design/adr/0015-refresh-event.md) records wiring `--rail-result` to the `refresh` event, [ADR-0016](docs/design/adr/0016-rental-car-and-ferry.md) records treating rental cars and ferries as first-class, hand-written transport legs, [ADR-0017](docs/design/adr/0017-transport-candidates.md) records deferring a rental-car/ferry candidate producer, [ADR-0018](docs/design/adr/0018-map-and-images.md) records why the page carries no interactive map, static map, or image field and why the Journey page should gain the same offline location schematic the Trip page has, and [ADR-0019](docs/design/adr/0019-second-price-source.md) records, per price category, whether a second price source is worth adding. See [`docs/manual-acceptance.md`](docs/manual-acceptance.md) for Codex Desktop acceptance.

## Contributing and security

Read [`CONTRIBUTING.md`](CONTRIBUTING.md) before opening a pull request, and
[`SECURITY.md`](SECURITY.md) before reporting anything credential-related. The
read-only transaction boundary and the credential isolation rules are enforced
by tests, not by convention.
