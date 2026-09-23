# China Trip Weaver

**English** · [简体中文](README.zh-CN.md)

Planning an independent trip in mainland China? China Trip Weaver turns your route, dates, and researched options into a phone-friendly itinerary with timed days, selected stays, budget status, and things to verify. It is a read-only Codex plugin; you make every booking yourself.

## Start with Codex

You need Codex Desktop or a compatible Codex CLI, and Python 3.9 or newer. Clone the repository and install the local marketplace plugin:

```bash
git clone https://github.com/kangyishuai/china-trip-weaver.git
cd china-trip-weaver
scripts/install_local_plugin.sh
```

The script registers, installs or refreshes, and checks the plugin in your Codex installation. `scripts/install_local_plugin.sh --check` inspects the existing installation without refreshing it. Start a **new Codex task** after installation so the Skills load. If another enabled plugin exposes `plan-china-trip` (notably `china-travel-assistant`), disable that conflicting plugin first; `ctw doctor` reports conflicts.

In the new task, describe the trip in one message. For example:

> Use China Trip Weaver to plan a five-day, one-way trip for two from Beijing through Shanghai, Hangzhou, and Suzhou, 16–20 October 2026. We like architecture, gardens, and food. Keep a moderate daily pace and use CNY 8,000 as our budget target. Put the files under `plans/江南五日/`. Show me the resulting HTML and list costs, train services, and bookings I still need to verify. Do not log in or book anything.

Open the resulting `.html` file in `plans/江南五日/` and check its source labels and unknowns before making your own bookings. The JSON alongside it is the versioned plan. Optional live provider lookups may need your own credentials; if a source is unavailable, the plugin marks a fallback or unknown instead of presenting it as confirmed. The [planning Skill](plugins/china-trip-weaver/skills/plan-china-trip/SKILL.md) describes how Codex handles the request.

## Scope

A Trip can cover one day or an ordered route of up to seven days, including multiple cities. Longer routes become a Journey of complete Trips, each within that limit. Separate traveler groups can start in different cities and meet at a specified place and time. Every overnight night needs a selected stay covering that date and destination; missing coverage produces a structured no-solution result.

The output separates selected plans from comparisons, cites supporting claims, and marks static estimates, provider failures, and unresolved facts. It never invents a price, train service, or coordinate to fill a gap. For your own travel, keep the request, candidates, JSON, HTML, and follow-up results together under `plans/<name>/` in the project where you invoked the plugin. Replanning and weather, dining, or location updates normally write a new revision to the same JSON path and render to the same HTML path; choose a different output name only when you want a separate copy. Revision conflicts fail without writing.

The plugin **never** logs in, submits identity, holds inventory, books, pays, cancels, or changes an order. It is not listed on a public Codex marketplace. Live AMap, FlyAI, VariFlight, and AnySearch capabilities are optional. Credentials belong in the launching environment or a current-user-owned `~/.config/china-trip-weaver/credentials.env` file with mode `0600`, never in a prompt, command argument, plan, or repository. `plugins/china-trip-weaver/scripts/ctw doctor` shows configuration status and Skill conflicts without revealing credential values. [Credential guide](plugins/china-trip-weaver/references/credentials.md) · [Provider contracts and degradation](plugins/china-trip-weaver/references/provider-contracts.md)

## Reproduce a synthetic result (optional)

This deterministic example needs no provider key or live provider query. It writes to a Git-ignored directory from the repository root; Node/npm is needed only when a pinned live MCP or CLI provider is invoked.

```bash
mkdir -p .tmp/first-trip
plugins/china-trip-weaver/scripts/ctw plan \
  --request demo/request.json \
  --candidates demo/candidates.json \
  --rail fixture:tests/fixtures/providers/rail12306/empty.json \
  --mobility off --lodging off --aviation off \
  --offline-fixture --fixed-clock 2026-09-04T00:00:00+08:00 \
  --output-json .tmp/first-trip/trip.json \
  --output-html .tmp/first-trip/trip.html
```

Open `.tmp/first-trip/trip.html` locally. The fixture deliberately contains no train inventory, so service, fare, and availability remain unverified. You can also download the checked-in [synthetic Trip HTML](demo/trip.html) and open that file locally; this repository link points to a file, not a hosted interactive demo. Its source is [Trip JSON](demo/trip.json). Other synthetic cases are in [`demo/`](demo/).

## Go deeper

- [CLI help](plugins/china-trip-weaver/scripts/ctw): run `plugins/china-trip-weaver/scripts/ctw --help` and the relevant subcommand's `--help` for planning, validation, rendering, Journey updates, and provider lookups.
- [Architecture and data contracts](docs/design/00-README.md), [Trip schema](plugins/china-trip-weaver/schema/trip.schema.json), and [Journey schema](plugins/china-trip-weaver/schema/journey.schema.json): implementation details and exact document shapes.
- [Maintainer acceptance checklist](docs/manual-acceptance.md), [contributing](CONTRIBUTING.md), [security](SECURITY.md), and [current status](PROGRESS.md).

The [MIT License](LICENSE) covers this repository's own code and documentation. It grants no rights over provider data. This repository is for personal, non-commercial use unless you obtain the applicable provider licences yourself; live results must not be redistributed here. Read the [third-party notices](THIRD_PARTY_NOTICES.md) before using provider data or considering commercial use.
