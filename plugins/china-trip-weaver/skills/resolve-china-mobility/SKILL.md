---
name: resolve-china-mobility
description: Resolve mainland-China POIs, geocodes, coordinate provenance, and walking, transit, driving, or cycling route-time matrix cells through the AMap adapter. Invoke explicitly from plan-china-trip after candidates exist or when affected hops need revalidation; do not schedule a trip or treat straight lines as routes.
---

# Resolve China Mobility

Resolve only the candidate endpoints supplied by the parent Skill.

- Preserve provider-native coordinates and explicitly derive WGS84/GCJ02 at most once. AMap requests always consume GCJ02.
- Resolve POI identity with AMap v5 text search scoped by `city_limit=true` before geocoding. Preserve the provider POI id, matched name, formatted address, district, adcode, type, and business fields as claims; geocode only a complete address.
- Treat a first/second name-similarity margin below `0.15`, or any provider administrative city that disagrees with the candidate city, as `identity_conflict`. Keep coordinates unknown and never replace the provider's city with the candidate city.
- Build a bounded directed matrix for plausible adjacency, locked anchors, transport endpoints, and lodging; do not issue an unbounded all-pairs query.
- Emit `semantic_outlier` for isolated same-city points, distinct entities sharing a coordinate, or same-day adjacent POIs over 50 km apart. These warnings do not block planning, but implicated claims must not remain `verified`.
- A live/cached cell needs route evidence and query time. A static cell needs an explicit method and conservative buffer. Missing or unreachable cells are not routes.
- Fail closed on endpoint/pagination/response drift and return health plus degradation rung. Do not choose the daily order.

Inspect a bounded live matrix directly or return its normalized cells to the parent. When AMap is unavailable, `ctw plan` builds only labeled static estimates:

```bash
scripts/ctw mobility --candidates candidates.json --modes transit,walking --output-json mobility.json
scripts/ctw plan --request request.json --candidates candidates.json --rail off --mobility live --output-json trip.json --output-html trip.html
scripts/ctw validate trip.json
```

Never turn an AMap fixture response into live output outside an explicit offline fixture test.
