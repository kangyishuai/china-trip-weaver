# Codex Desktop manual acceptance

**English** · [简体中文](manual-acceptance.zh-CN.md)

This checklist validates the installed plugin through natural language and
confirms the checked-in artifacts. Never paste a provider credential into the
task.

## Preconditions

1. Open a clone of this repository in Codex Desktop. `ctw doctor` detects a
   competing plugin automatically and exits non-zero, so no manual check is
   needed; act on its `skill_conflicts` report if it is not `clear`.
2. Install or refresh `china-trip-weaver@china-trip-weaver-local`, then create a
   new task.
3. In the repository terminal run `plugins/china-trip-weaver/scripts/ctw doctor`.
   AMap, FlyAI, and VariFlight should say only `configured`; no value or length
   may appear. If a provider is missing, accept only that provider's documented
   keyless/off behavior.
4. Confirm the local credential file is a regular mode-`600` file. Do not open
   or display its values during acceptance.

## Natural-language acceptance: Beijing to Shanghai

Send this in a fresh Codex task:

> Use China Trip Weaver to read `demo/request.json` and
> `demo/candidates.json`. Run the read-only live plan with rail, mobility, and
> lodging enabled. Do not book or log in. Validate the Trip and HTML, then tell
> me the provider health, number of live rail legs, lodging candidates, flight
> comparisons, and whether AMap reached MATRIX_READY. Do not display any
> credential.

Pass criteria:

- the task uses the `plan-china-trip` Skill from this plugin and runs
  `--rail live --mobility live --lodging live`;
- Trip and HTML validation both report zero errors;
- two dated rail legs are live with typed fares and availability claims;
- AMap is `ready/live`, its reason contains a call count no greater than 80,
  and the pipeline includes `MATRIX_READY`;
- at least one live lodging candidate and one flight comparison exist;
- configured FlyAI and VariFlight are not `missing`; VariFlight has status and
  comfort claims when matching flights exist;
- no transaction action or credential value appears.

## Natural-language acceptance: Guangzhou to Shenzhen day trip

Send:

> Use China Trip Weaver to run the one-day round trip described by
> `demo/guangzhou-shenzhen/request.json` and its `candidates.json`. Use live
> rail, mobility, and lodging mode, but do not invent an overnight stay or a
> flight when the provider returns no results. Validate both outputs and report
> the outbound/return rail services and AMap live-cell count.

Pass criteria:

- exactly one itinerary day and two live rail legs on that date;
- AMap is `ready/live` with at least one live cell and `MATRIX_READY`;
- no lodging candidate or hotel call for the no-overnight request;
- FlyAI may be `ready/no_results` for this short-haul flight market, and
  VariFlight may make zero business calls when no flight candidate exists;
- Trip/HTML/secret gates all pass.

## Reproducible terminal gates

```bash
plugins/china-trip-weaver/scripts/ctw validate demo/trip.json
plugins/china-trip-weaver/scripts/ctw validate-html demo/trip.html demo/trip.json
plugins/china-trip-weaver/scripts/ctw validate-candidates demo/candidates.json

plugins/china-trip-weaver/scripts/ctw validate demo/guangzhou-shenzhen/trip.json
plugins/china-trip-weaver/scripts/ctw validate-html demo/guangzhou-shenzhen/trip.html demo/guangzhou-shenzhen/trip.json
plugins/china-trip-weaver/scripts/ctw validate-candidates demo/guangzhou-shenzhen/candidates.json

/usr/bin/python3 scripts/scan_secrets.py
/usr/bin/python3 scripts/scan_secrets.py --credential-values
/usr/bin/python3 scripts/scan_secrets.py --credential-values --git-history
/usr/bin/python3 -m unittest discover -s tests
```

Any nonzero validator/scanner result, skipped test, static route presented as
live, masked price presented as numeric, missing configured provider, or
credential value in output is a failure.
