---
name: search-china-lodging
description: Produce dated mainland-China lodging areas, candidate properties, verifiable conditions, and deep links from the pinned FlyAI CLI or explicit degradation. Invoke explicitly from plan-china-trip when overnight stays are required; never claim room-level inventory, tax, cancellation, or total price unless the corresponding claim is verified.
---

# Search China Lodging

Require city/area, check-in, check-out, party, and lodging constraints.

- Probe FlyAI before querying. With no usable inventory response, return appropriate areas and dated official/deep links rather than invented properties or rates.
- A price is `live` only when dates, party, room, tax, and cancellation context match. Otherwise use `verify-on-click` or `unknown` with amount `null`.
- Preserve unknown coordinate CRS; do not guess WGS84/GCJ02.
- Return normalized lodging candidates, typed prices, conditions, claims, deep links, health, and explicit unknowns. Stop before checkout, login, or personal-data entry.

Query live read-only inventory directly with:

```bash
scripts/ctw lodging --city 上海 --check-in YYYY-MM-DD --check-out YYYY-MM-DD --output-json lodging.json
```

The parent consumes live inventory with `scripts/ctw plan --request request.json --candidates candidates.json --rail <mode> --lodging live --output-json trip.json --output-html trip.html`. Use `--keyless-trial` only for an explicit trial comparison. See `../../references/candidates.example.json` for the static candidate-file shape.
