# ADR-0009: Rename the rail and air Skills

- **Status:** Accepted
- **Date:** 2026-09-03

## Context

The accepted design names two explicit-only Skills `search-china-trains` and
`search-china-flights`. Those names can collide with Skills from an older
travel plugin. The implementation objective explicitly permits only these two
name changes while freezing the accepted design and schema files.

## Decision

The v0.1 package uses `search-china-rail` instead of
`search-china-trains`, and `search-china-air` instead of
`search-china-flights`. Their responsibilities, descriptions, read-only
boundary, provider routing, and explicit-only invocation policy are unchanged.

The accepted design remains copied byte-for-byte. This ADR is the only added
file under `docs/design/`; implementation code, Skill directories,
frontmatter names, UI metadata, tests, and user-facing references use the new
names.

## Consequences

- The package avoids another avoidable selector collision with the older
  plugin.
- Reviewers must apply this two-name mapping when comparing implementation to
  `docs/design/02-plugin-skills.md` and `docs/design/09-impl-map.md`.
- Reverting the decision requires only renaming the two Skill directories and
  their metadata/tests; no Trip or provider contract changes.

## Evidence

- Implementation objective default: rename the two child Skills to avoid the
  known older-plugin names.
- `docs/design/02-plugin-skills.md`, sections 3 and 11.
- `docs/design/09-impl-map.md`, sections 1 and 2.
