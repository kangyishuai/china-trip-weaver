# China Trip Weaver

**English** · [简体中文](README.zh-CN.md)

China Trip Weaver is a Codex plugin for evidence-backed, read-only trips within mainland China. It turns an independent request plus researched candidates into one versioned Trip JSON; queries pinned 12306 rail, AMap route matrices, FlyAI lodging/flight inventory, and optional VariFlight status/comfort enrichment; schedules without conflating comparisons with selected legs; and renders a deterministic phone-first HTML file.

It never logs in, submits identity, holds inventory, books, pays, cancels, or changes an order. Provider credentials stay in process-local environments and never appear in argv, logs, fixtures, Trip, HTML, or Git.

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

The live path uses `AMAP_WEBSERVICE_KEY`, `FLYAI_API_KEY`, and `VARIFLIGHT_API_KEY` (`X_VARIFLIGHT_KEY` remains read compatibility). AnySearch stays disabled in this release. Every Node provider gets a repository-local npm cache, temp/config/cache directories, and provider-specific isolated `os.homedir()`.

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

The expected result is `china-trip-weaver@china-trip-weaver-local`, version `0.2.0`, status `installed, enabled`. Use a fresh Codex task after installing or updating so its nine Skills and MCP configuration are reloaded.

For Codex Desktop UI installation, add this repository as a local marketplace, ensure `china-travel-assistant` is disabled, install China Trip Weaver Local, restart, and create a new task. The two plugins must not be enabled together because both expose `plan-china-trip`.

## Candidate input

`candidates.json` contains exactly `candidates_version`, `pois`, `lodgings`, `claims`, and `unknowns`. It does not contain transport legs. Its entity shapes reuse the frozen Trip `$defs`, and every entity/price/opening-window claim reference must resolve.

```bash
plugins/china-trip-weaver/scripts/ctw validate-candidates demo/candidates.json
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

Railway/network/provider failure never becomes fake success. Each capability preserves its own health and either uses a labeled fallback or stops at a typed unknown. AMap is capped at 80 calls per plan and no more than 2 QPS. FlyAI masked prices such as `¥4xx` are always `verify-on-click`; only exact numeric prices are `live`. FlyAI coordinates remain `provider-unknown` and are never converted or mapped.

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
ctw canonicalize TRIP.json
ctw rail --date YYYY-MM-DD --from CITY --to CITY --output-json rail-result.json
ctw mobility --candidates CANDIDATES.json --modes transit,walking --output-json mobility.json
ctw lodging --city CITY --check-in YYYY-MM-DD --check-out YYYY-MM-DD --output-json lodging.json
ctw air --origin CITY --destination CITY --date YYYY-MM-DD --output-json air.json
ctw replan --trip TRIP.json --event EVENT.json --base-revision N --output-json TRIP-rN.json --output-html TRIP-rN.html
ctw render TRIP.json --output TRIP.html
ctw validate-html TRIP.html TRIP.json
```

The runtime uses no third-party Python package. `render` refuses an invalid Trip, and `validate-html` blocks structural, CSP, remote-resource, unsafe-link, secret, fact-mapping, degradation, and transaction-action violations.

## Tests

```bash
/usr/bin/python3 -m unittest discover -s tests -v
/usr/bin/python3 scripts/scan_secrets.py
/usr/bin/python3 scripts/scan_secrets.py --credential-values
/usr/bin/python3 scripts/scan_secrets.py --credential-values --git-history
```

The suite has zero skips. It covers the frozen Trip schema, candidate validation, credential/process/home isolation, exact-value and captured-data scans, evidence/cache/coordinates, 79 unmistakably synthetic provider fixtures with AMap/FlyAI/VariFlight contract shapes, 20 scheduling goldens, 8 no-solution cases, 4 replan goldens, renderer adversarial cases and offline browser viewports, Skill/package metadata, and deterministic plus live-path integration scenarios.

Design authority lives in [`docs/design/`](docs/design/00-README.md). Implementation-only additions are [ADR-0009](docs/design/adr/0009-rename-rail-air-skills.md), [ADR-0010](docs/design/adr/0010-candidate-file-planning-and-live-rail.md), and [ADR-0011](docs/design/adr/0011-live-amap-flyai-variflight-boundaries.md); [ADR-0012](docs/design/adr/0012-open-source-under-mit.md) records the MIT licensing decision and [ADR-0013](docs/design/adr/0013-stay-off-the-public-marketplace.md) records why this plugin is not listed on a public marketplace. See [`docs/manual-acceptance.md`](docs/manual-acceptance.md) for Codex Desktop acceptance.

## Contributing and security

Read [`CONTRIBUTING.md`](CONTRIBUTING.md) before opening a pull request, and
[`SECURITY.md`](SECURITY.md) before reporting anything credential-related. The
read-only transaction boundary and the credential isolation rules are enforced
by tests, not by convention.
