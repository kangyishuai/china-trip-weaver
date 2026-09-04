# Security policy

**English** · [简体中文](SECURITY.zh-CN.md)

## Reporting a vulnerability

Open a private security advisory through the GitHub repository's Security tab.
Do not open a public issue for a vulnerability, and never include a real API
key, token, cookie, or personal travel booking in a report.

## Credential handling in this project

This plugin treats provider credentials as write-only inputs.

- Values are read only from the launching process environment or from
  `~/.config/china-trip-weaver/credentials.env`, which must be a regular file
  owned by the current user at mode exactly `0600`.
- Each provider subprocess receives only its own variables. The scheduler, the
  renderer, and the rail provider receive none.
- Credentials never appear in `argv`, logs, cached fixtures, a Trip document,
  rendered HTML, or Git. `ctw doctor` prints only `configured` or `missing`,
  never a value, prefix, suffix, hash, or length.
- `scripts/scan_secrets.py` enforces this. Run it with `--credential-values` to
  check the working tree against your own configured values, and add
  `--git-history` to check every committed blob. Both must report zero findings.

If you find a path that leaks a credential into any of those surfaces, treat it
as a vulnerability and report it privately.

## Scope of the plugin

The plugin is read-only by design. It never logs in, submits identity documents,
holds inventory, books, pays, cancels, or changes an order. A change that adds
a transaction capability is a security-relevant change and needs its own
architecture decision record.
