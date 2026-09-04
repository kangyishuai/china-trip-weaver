---
name: resolve-china-mobility
description: Resolve mainland-China POIs, geocodes, coordinate provenance, and walking, transit, driving, or cycling route-time matrix cells through the AMap adapter. Invoke explicitly from plan-china-trip after candidates exist or when affected hops need revalidation; do not schedule a trip or treat straight lines as routes.
---

# Resolve China Mobility

Resolve only the candidate endpoints supplied by the parent Skill.

- Preserve provider-native coordinates and explicitly derive WGS84/GCJ02 at most once. AMap requests always consume GCJ02.
- Build a bounded directed matrix for plausible adjacency, locked anchors, transport endpoints, and lodging; do not issue an unbounded all-pairs query.
- A live/cached cell needs route evidence and query time. A static cell needs an explicit method and conservative buffer. Missing or unreachable cells are not routes.
- Fail closed on endpoint/pagination/response drift and return health plus degradation rung. Do not choose the daily order.

Inspect a bounded live matrix directly or return its normalized cells to the parent. When AMap is unavailable, `ctw plan` builds only labeled static estimates:

```bash
scripts/ctw mobility --candidates candidates.json --modes transit,walking --output-json mobility.json
scripts/ctw plan --request request.json --candidates candidates.json --rail off --mobility live --output-json trip.json --output-html trip.html
scripts/ctw validate trip.json
```

Never turn an AMap fixture response into live output outside an explicit offline fixture test.
