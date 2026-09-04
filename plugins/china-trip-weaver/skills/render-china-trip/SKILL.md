---
name: render-china-trip
description: Render a schema-valid Trip as the single deterministic, phone-first HTML artifact and validate its structure, security, accessibility, and offline core. Invoke explicitly from plan-china-trip only after Trip validation; never research, reschedule, alter facts, or embed credentials.
---

# Render China Trip

Accept only a Trip that passes schema and semantic validation.

- Invoke the bundled commands and require the HTML validator to report zero errors before delivery:

  ```bash
  scripts/ctw render trip.json --output trip.html
  scripts/ctw validate-html trip.html trip.json
  ```

- Preserve Trip ordering and facts. Do not research, reschedule, add prices/times/service numbers, or convert unknown coordinates.
- Keep CSS, location SVG, and canonical Trip JSON inline. Remote executable/resource requests and provider credentials are fatal.
- Show mode, provider health, typed prices, unknown reasons, evidence, schematic-route labeling, and the read-only transaction boundary.
- Return structured validation errors instead of a partially trusted page.
