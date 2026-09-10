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

The suite must end with `OK` and zero failures. Three tests depend on a local
Codex install (the bundled Skill and plugin validators, and the Skill parser
smoke through `scripts/install_local_plugin.sh --skill-smoke`); they skip when
Codex is not installed on the machine and must pass when it is.

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

## Release

The version literal lives in exactly two files, and they must always agree:
`plugins/china-trip-weaver/.codex-plugin/plugin.json` (the `version` field) and
`plugins/china-trip-weaver/src/china_trip_weaver/__init__.py` (`__version__`).
Every other reference in the repository imports `__version__` rather than
repeating the literal.

1. Bump the version in both files to the same new value.
2. Run the full check suite from [Running the checks](#running-the-checks)
   above and confirm it ends `OK` with zero failures.
3. Run `bash scripts/install_local_plugin.sh` to install/refresh the new
   version into your own real Codex installation, then
   `bash scripts/install_local_plugin.sh --check` to confirm the installed
   cache and the source tree now agree (exit 0, zero differences).
4. Commit the version bump, then tag it:
   `git tag -a v<version> -m "Release <version>"`.
5. Push the commit and the tag: `git push origin main --tags`.
6. Publish the GitHub Release from the tag:
   `gh release create v<version> --generate-notes`.

Only a change that bumps the version needs steps 3–6. A change that does not
touch the version literal skips this whole section.
