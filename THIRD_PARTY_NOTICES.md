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

Provider terms, runtime caching, map attribution, public marketplace metadata, and commercial use remain unresolved. The committed `demo/` and `tests/fixtures/providers/` artifacts are locally generated synthetic data: they preserve contract shapes and failure modes but contain no captured provider responses. Live results obtained with a user's own credentials remain provider-controlled and must not be committed. See `BLOCKED.md` before publishing to a public marketplace or using this commercially.
