# ADR-0012: Publish the project's own code under MIT

- **Status:** Accepted
- **Date:** 2026-09-04

## Context

ADR-0011 completed the live provider boundaries while the package still carried
a placeholder identity. `02-plugin-skills.md` section 2 fixed `license` to
`UNLICENSED` and `author` to `ChinaTripWeaver contributors`, and
`05-credentials.md` section 6 tied the credential lifecycle to a local-only
status, because neither the distribution form nor the third-party terms had been
decided.

The maintainer has now decided to publish the repository on GitHub. That
resolves the distribution question for this repository's own code, but not the
separate question of what rights exist over data returned by AMap,
Fliggy/FlyAI, VariFlight, or China Railway.

## Decision

This repository's own code and documentation are released under the MIT License.
`plugin.json` carries `"license": "MIT"`, a real author, and the repository URL.
This supersedes the `UNLICENSED` placeholder in `02-plugin-skills.md` section 2
and the `UNLICENSED`/local-only wording in `05-credentials.md` section 6.

The licence covers only this project's own work. It grants no rights over
provider data, and it does not resolve caching, redistribution, map attribution,
or the metadata a public Codex marketplace listing would need. Those stay open
in `BLOCKED.md`, and the plugin continues to install from a local marketplace
pointed at a clone rather than from a public marketplace.

Content that belonged to a single maintainer's machine was removed before
publication: verbatim copies of third-party specification pages, absolute local
paths, and one-off development incident records. They were provenance for the
research phase, never product behaviour.

## Consequences

- Anyone may use, modify, and redistribute this project's code under MIT.
- The read-only transaction boundary of ADR-0008 and the credential rules of
  `05-credentials.md` are unchanged; MIT is a licensing decision, not a
  permission to transact or to expose credentials.
- Provider data terms remain the user's responsibility. Committed samples under
  `demo/` and `tests/fixtures/providers/` stay flagged in `BLOCKED.md`.
- Publishing to a public Codex marketplace still needs a separate decision.

## Evidence

- `LICENSE`, `plugins/china-trip-weaver/.codex-plugin/plugin.json`
- `BLOCKED.md`, `THIRD_PARTY_NOTICES.md`
- Superseded: `docs/design/02-plugin-skills.md` section 2,
  `docs/design/05-credentials.md` section 6
