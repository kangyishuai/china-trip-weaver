# Contributing

**English** · [简体中文](CONTRIBUTING.zh-CN.md)

## Ground rules

This is a read-only travel planning plugin. Two rules are not negotiable.

1. **Never add a transaction capability.** No login, identity submission,
   inventory hold, booking, payment, cancellation, or change. Query, compare,
   and link out to the official page.
2. **Never let a credential escape the provider process.** It must not reach
   `argv`, logs, fixtures, a Trip document, rendered HTML, or Git. See
   [`SECURITY.md`](SECURITY.md).

## Running the checks

The runtime is Python standard library only and targets Python 3.9. Node is used
only to launch pinned MCP and CLI providers through `npx`; nothing is installed
globally.

```bash
python3 -m unittest discover -s tests -v
python3 scripts/scan_secrets.py
```

The suite must end with `OK` and zero failures. Two tests exercise the Codex
bundled Skill and plugin validators; they skip when Codex is not installed on
the machine and must pass when it is.

## What a change has to come with

- A test that fails before the change and passes after it. Do not weaken an
  existing assertion, delete a test, or add a skip to get to green.
- Provider fixtures for every failure mode you touch: success, empty, auth,
  rate limit, timeout, and wrong shape. A provider that only has a success
  fixture is not covered.
- Truthful degradation. A static estimate is never presented as a live route, a
  masked price is never presented as a number, and an unknown is never zero.

## Architecture decisions

`docs/design/` holds the accepted architecture and `docs/design/adr/` holds the
decision records. If a change contradicts one, add a new numbered ADR that
supersedes it rather than editing the implementation silently.

## Provider credentials

Credentials are optional. The keyless baseline must keep working without them.
Never commit a credential file, and never paste a value into an issue, a pull
request, or an agent conversation.
