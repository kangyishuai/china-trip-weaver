# Unresolved items

This file lists what is still undecided for this project. Items about a single
maintainer's machine, one-off development incidents, and internal process
deviations were removed when the repository was prepared for publication; they
were never product behaviour.

Two items that stood here before 2026-09-04 are now closed. Same-name Skill
detection became automatic once `codex plugin list --json` shipped; `ctw doctor`
reads it, walks each enabled plugin's `skills/` directory, and reports
`skill_conflicts`. Sample-data redistribution ended when `demo/` and
`tests/fixtures/providers/` became locally generated synthetic values, which a
regression test now enforces on every Git-tracked file.

## Public marketplace listing metadata

- Fact: this plugin installs from a local marketplace pointed at a clone. A
  public Codex marketplace listing would additionally require a privacy policy
  URL, a terms-of-service URL, a listing category, and an authentication policy
  that the maintainer must own and publish.
- Still to decide: whether to publish at all, and under whose name and policies.
- Impact: does not block local or self-hosted use. It does block a public
  marketplace listing.

## Commercial use requires provider licences the maintainer does not hold

- Fact: AMap requires a purchased technical service licence for any commercial
  purpose and forbids transferring or sublicensing it. VariFlight requires a
  written contract before its data may be redistributed, repackaged, or resold.
  See `THIRD_PARTY_NOTICES.md` for the cited clauses.
- Current position: the repository is documented as personal and
  non-commercial. No provider response is cached, and every contributing
  provider is named in the rendered page.
- Still to decide: nothing, unless someone intends commercial use, in which
  case they must obtain those licences themselves.
- Impact: does not block personal use. It does block commercial use.

## Fliggy/FlyAI wrapper terms were not located

- Fact: the pinned `@fly-ai/flyai-cli` is a third-party wrapper over Fliggy
  services. A terms page governing the wrapper itself was not found on
  2026-09-04, so its obligations are assumed rather than verified.
- Current position: its data is treated under the same no-cache,
  no-redistribution rule applied to AMap and VariFlight, which is the
  conservative reading.
- Still to verify: the wrapper's actual terms, if its authors publish them.
- Impact: does not block use under the conservative rule.
