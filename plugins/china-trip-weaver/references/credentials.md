# Credential configuration

China Trip Weaver completes its keyless baseline without provider credentials. Optional keys only improve individual capabilities.

| Provider | Environment variable | Keyless behavior |
|---|---|---|
| AMap Web Service | `AMAP_WEBSERVICE_KEY` | No AMap API call; use cached/static/deep-link/unknown route degradation. |
| FlyAI | `FLYAI_API_KEY` | Probe the documented keyless trial; if unavailable, use dated deep links and unknown prices. |
| VariFlight | `VARIFLIGHT_API_KEY` (`X_VARIFLIGHT_KEY` read compatibility) | List/probe only; no business call. |
| AnySearch | `ANYSEARCH_API_KEY` | Disabled; host web remains preferred. |

Never paste a value into chat or pass it on a command line. Configure it in the launching process environment or, only when explicitly chosen by the user, in:

```text
~/.config/china-trip-weaver/credentials.env
```

On POSIX this must be a regular, current-user-owned, non-symlink file with mode exactly `0600`. Its grammar is `NAME=VALUE`, blank lines, and `#` comments only. The runtime does not evaluate shell syntax, expand variables, echo values, or modify global environment variables.

Environment variables win per name; the file only fills missing allowlisted names. Each provider process receives only its own variables. Railway, host web, scheduler, and renderer receive none of them.

If a provider reports missing, expired, forbidden, rate-limited, or contract-mismatch health, rotate/configure locally and restart that provider process. Never send the value to the assistant.
