---
name: search-china-lodging
description: Produce dated mainland-China lodging areas, candidate properties, verifiable conditions, and deep links from the pinned FlyAI CLI or explicit degradation. Invoke explicitly from plan-china-trip when overnight stays are required; never claim room-level inventory, tax, cancellation, or total price unless the corresponding claim is verified.
---

# Search China Lodging

FlyAI is an optional, best-effort third-party wrapper. Treat its absence, drift, or failure as a degraded lodging capability, never as a reason to stop the plan or to invent inventory. When FlyAI returns no usable property, a configured AMap POI search may add accommodation-category candidates; AMap does not establish room inventory or price.

Require city/area, check-in, check-out, party, and lodging constraints.

- Carry `party`, `rooms`, `adult_count`, `occupancy`, `bed_config`, `parking_required`, and `cancellation_preference` into every lodging request. Keep any constraint the provider cannot verify in the Trip unknowns.
- Probe FlyAI before querying. With no usable inventory response, merge AMap accommodation POIs and researched candidates; never replace locked candidates or discard their claims and unknowns.
- A price is `live` only when dates, party, room, occupancy, tax, and cancellation context all match. A numeric lead price without that context is still `verify-on-click` with amount `null`.
- Preserve unknown coordinate CRS; do not guess WGS84/GCJ02.
- Return normalized lodging candidates, typed prices, conditions, claims, deep links, health, and explicit unknowns. Stop before checkout, login, or personal-data entry.

Query live read-only inventory directly with:

```bash
scripts/ctw lodging --city 上海 --check-in YYYY-MM-DD --check-out YYYY-MM-DD \
  --adults 3 --rooms 1 --room-constraint "3 adults in one room" \
  --bed-config "three-person room" --parking-required \
  --cancellation-preference "free cancellation" --output-json lodging.json
```

The parent consumes live inventory with `scripts/ctw plan --request request.json --candidates candidates.json --rail <mode> --lodging live --output-json trip.json --output-html trip.html`. Use `--keyless-trial` only for an explicit trial comparison. See `../../references/candidates.example.json` for the static candidate-file shape.
