# Third-party notices and service provenance

China Trip Weaver's own code and documentation are released under the MIT License (see `LICENSE`). This file records third-party integrations; it grants no rights to provider data and does not override any provider's terms.

| Integration | Locked version / endpoint family | Upstream code license evidence | Use in this repository |
|---|---|---|---|
| 12306 MCP | `12306-mcp@0.3.10` | MIT in locked upstream research snapshot | Invoked via pinned `npx`; no vendored upstream code. |
| FlyAI CLI | `@fly-ai/flyai-cli@1.0.16` | npm metadata reports MIT; implementation is not copied | Optional pinned CLI invocation after runtime probe. |
| AMap Web Service | v5 POI; v3/v4 route/geocode families | Service API, not copied source | Optional user-configured read-only HTTP calls; data/cache terms remain provider-controlled. |
| VariFlight MCP | `@variflight-ai/variflight-mcp@1.0.3` | package declares ISC; locked repository lacked the linked license text | Optional pinned MCP enrichment; no vendored upstream code. |
| AnySearch | Runtime API fingerprint | Service terms not established for redistribution | Optional and default-off; auto-registration rejected. |
| Google Chrome | Local installed browser | External QA tool only | Used only for repository-local offline renderer QA; not distributed or required at plugin runtime. |

Provider terms were reviewed on 2026-09-04 and the findings below are enforced in code and documentation.

- AMap, https://lbs.amap.com/home/terms/ (updated 2025-12-03). Section 3.5 forbids directly storing, caching, or scraping its service data. Section 7.7 requires naming 高德地图 as the source wherever its data is displayed. Section 3.2.2 requires a purchased technical service licence for any commercial purpose, and section 3.4 forbids using the data for model or algorithm training or dataset construction.
- VariFlight, https://dataworks.variflight.com/terms-of-use/. Absent a written contract its APIs may not be scraped, cached for redistribution or repackaging, or commercially resold; permitted non-commercial sharing carries an attribution mandate.
- Fliggy/FlyAI. The pinned CLI is a third-party wrapper and no authoritative terms page for the wrapper itself was located, so its data is treated under the same no-cache, no-redistribution rule.

Consequently no provider response is cached, and the rendered page attributes every provider that actually contributed. This repository is for personal, non-commercial use unless you obtain the relevant provider licences yourself. Public marketplace listing metadata remains unresolved. The committed `demo/` and `tests/fixtures/providers/` artifacts are locally generated synthetic data: they preserve contract shapes and failure modes but contain no captured provider responses. Live results obtained with a user's own credentials remain provider-controlled and must not be committed. See `BLOCKED.md` before publishing to a public marketplace or using this commercially.
