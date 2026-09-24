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
python3 -m pyflakes $(git ls-files '*.py')
```

The full suite must end with `OK` and zero failures. CI runs these same three steps
on Python 3.9 and 3.13. If a local host policy bars a browser-backed test, collect
the exact method IDs, run an explicit selection of the allowed methods, and report
both the selected and excluded counts; do not delete or skip the tests, call that
a full local run, or treat it as a replacement for the target commit's CI.
Coverage is not part of CI and not a merge gate; measure it on demand with
`python3 scripts/measure_coverage.py`, which builds a
throwaway virtualenv, tracks subprocesses, and refuses to print a percentage
unless the run actually exercised the whole suite. Three tests depend on a local
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
repeating the literal; only the per-version entries in `PROGRESS.md` and the
git tags carry version numbers as an index.

1. Bump both version sources together and prepare reviewed Release notes.
2. Run the applicable local checks. Record any browser methods excluded by the
   current host policy; do not weaken the repository's CI workflow.
3. Commit the release candidate and push `main` without force. Wait for the
   **exact pushed commit** to pass the unchanged Python 3.9 and 3.13 CI jobs,
   including tests, secret scan, and pyflakes.
4. From the final `main` checkout, run `bash scripts/install_local_plugin.sh`
   and then `bash scripts/install_local_plugin.sh --check` (exit 0, zero cache
   differences). Confirm the installed-cache CLI version and synthetic renders.
5. Create an annotated tag at that same CI-approved commit:
   `git tag -a v<version> -m "Release <version>"`. Push **only** that tag by name:
   `git push origin v<version>`. Never use `--tags`; it could publish a local
   backup tag.
6. Publish the formal, non-draft GitHub Release from the remote tag with the
   reviewed notes file: `gh release create v<version> --notes-file <path> --verify-tag`.
   Read back remote `main`, the tag's peeled commit, Release status and URL,
   and installation parity before reporting completion.

Only a release that bumps the version uses the tagging, Release, and installation
steps. Other changes still run their applicable checks and follow the project's
normal CI gate when pushed.
