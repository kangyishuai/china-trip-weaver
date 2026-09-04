---
name: research-china-destination
description: Build date-bound destination and POI claims for a mainland-China city from authoritative web sources and user-pasted notes. Invoke explicitly from plan-china-trip when candidate places, current events, opening information, seasonal constraints, food, or local cautions are missing; do not create or render a full itinerary.
---

# Research China Destination

Return structured candidates and claim-level evidence, not an itinerary or prose template.

- Bind every query and result to the requested city and business dates. Prefer government, venue, operator, and other first-party pages.
- Cover only dimensions relevant to the user's interests plus opening/closure, current events, seasonal conditions, transport cautions, food, and preparation. Do not insert fixed brands or “top ten” sections.
- Every external fact needs source URL, provider, query time, status, confidence, and mode. Preserve conflicting facts as conflicts.
- Treat user-pasted notes as hypothesis/partial evidence. Do not fetch Xiaohongshu links or retain pasted personal data.
- Stop after candidates, claims, conflicts, and unknowns. The parent Skill owns provider selection and scheduling.

Write `candidates.json` with exactly `candidates_version`, `pois`, `lodgings`, `claims`, and `unknowns`; entity, price, and opening-window claim IDs must resolve. Do not add `transport_legs`. Validate it without provider calls:

```bash
scripts/ctw validate-candidates candidates.json
```

Use `../../schema/candidates.schema.json` as the contract and read `../../references/candidates.example.json` when an example is needed.
