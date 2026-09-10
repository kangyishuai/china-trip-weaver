---
name: research-china-destination
description: Build date-bound destination and POI claims for a mainland-China city from authoritative web sources and user-pasted notes. Invoke explicitly from plan-china-trip when candidate places, current events, opening information, seasonal constraints, food, or local cautions are missing; do not create or render a full itinerary.
---

# Research China Destination

Return structured candidates and claim-level evidence, not an itinerary or prose template.

- Use this search ladder in order and stop at the first available rung:
  1. Use the host's built-in network search first.
  2. Only when host search is absent or unavailable, fall back to AnySearch with an already configured key and a passing contract probe; never create, request, print, or persist a key.
  3. When neither search tool is available, use only material the user already pasted, mark destination research `degraded`, and leave unsupported facts unknown. Never silently skip evidence collection.
- Return provider health separately to the parent Skill without adding it to `candidates.json`. Record the rung actually used in `provider` and `reason`: `host-web`, `anysearch`, or `user-pasted-only`; keep `mode`, `status`, and check time truthful.
- Bind every query and result to the requested city and business dates. Prefer government, venue, operator, and other first-party pages.
- Cover only dimensions relevant to the user's interests plus opening/closure, current events, seasonal conditions, transport cautions, food, and preparation. Do not insert fixed brands or “top ten” sections.
- Every external fact needs source URL, provider, query time, status, confidence, and mode. Preserve conflicting facts as conflicts.
- Treat user-pasted notes as hypothesis/partial evidence. Do not fetch Xiaohongshu links or retain pasted personal data.
- Stop after candidates, claims, conflicts, and unknowns. The parent Skill owns provider selection and scheduling.

Build `candidates.json` with the candidate editor so entity/claim IDs and zero-based array JSON Pointers are generated rather than hand-written. The file still has exactly `candidates_version`, `pois`, `lodgings`, `claims`, and `unknowns`; entity, price, and opening-window claim IDs must resolve. Do not add `transport_legs`. Initialize, append, and validate it without provider calls:

```bash
scripts/ctw candidates init candidates.json
scripts/ctw candidates add-poi candidates.json --name "..." --city "..." --category "..." --source-url "https://..."
scripts/ctw candidates add-lodging candidates.json --name "..." --city "..." --check-in YYYY-MM-DD --check-out YYYY-MM-DD --source-url "https://..."
scripts/ctw validate-candidates candidates.json
```

Use `--force` with `candidates init` only when replacement is intentional. Add commands preserve unknown values explicitly and generate `/pois/<index>/...` or `/lodgings/<index>/...` pointers from the actual append index; never substitute an entity ID for an array index.

When many candidates are already researched, append them all in one atomic call instead of one `add-poi`/`add-lodging` subprocess per candidate:

```bash
scripts/ctw candidates import candidates.json --items items.json --queried-at 2026-09-10T12:00:00+08:00
```

`items.json` is a JSON array of `{"kind": "poi"|"lodging", ...}` objects; every other key matches `add-poi`'s or `add-lodging`'s own flags (snake_case, e.g. `source_url`, `duration_minutes`). Every item is checked (unrecognized kind, unknown key, missing required key, or wrong-typed value) before any is applied; a business-rule failure (bad dates, negative price, duplicate identity, ...) during the append itself also aborts the whole batch. Either way `candidates.json` is left byte-for-byte unchanged and the failing 1-based item number and reason are reported. Add `--dry-run` to validate the whole list without writing.

After a Trip or Journey run reports AMap coordinate identity conflicts, review its bounded name feedback before editing the researched file. The first command is report-only and must leave `candidates.json` byte-for-byte unchanged; add `--apply` only after reviewing every automatic and manual item:

```bash
scripts/ctw candidates fix-names candidates.json --trip trip-or-journey.json
scripts/ctw candidates fix-names candidates.json --trip trip-or-journey.json --apply
scripts/ctw validate-candidates candidates.json
```

`fix-names` binds feedback to candidate entities by the reason's `ref_id`, never by a Trip or Journey array index. It changes only uniquely determined names. Items with equally close alternatives, conflicting Journey feedback, an unchanged normalized name, or malformed/unmatched feedback remain unchanged and are printed for manual review.

Use `../../schema/candidates.schema.json` as the contract, read `../../references/provider-contracts.md` for the shared search ladder, and read `../../references/candidates.example.json` when an example is needed.
