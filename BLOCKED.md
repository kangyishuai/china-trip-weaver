# Unresolved items

This file lists what is still undecided or unverified for this project. Items
about a single maintainer's machine, one-off development incidents, and internal
process deviations were removed when the repository was prepared for
publication; they were never product behaviour.

## Same-name `plan-china-trip` source detection has no stable public contract

- Fact: Codex does not merge Skills that share a name, so two plugins exposing
  `plan-china-trip` both appear in the selector. The runtime interface for
  identifying which plugin a Skill came from is not publicly specified.
- Current design: installation and `ctw doctor` prefer supported
  `codex plugin list` information, and the session layer uses the host-visible
  Skill catalogue. When either layer cannot uniquely identify the entry point,
  the plugin fails closed, shows a fixed mutual-exclusion notice, and makes zero
  provider calls.
- Still to verify: whether a machine-readable plugin listing exists, whether the
  Skill catalogue carries source paths, and what the desktop selector actually
  shows. Until then, only "installation instructions plus fail-closed manual
  acceptance" is promised, never fully automatic detection of an older plugin.
- Impact: does not block use. `china-trip-weaver` and `china-travel-assistant`
  must not be enabled at the same time.

## Provider terms, caching, redistribution, and marketplace metadata

- Fact: AMap, FlyAI/Fliggy, VariFlight, AnySearch, and public 12306 data each
  carry independent terms. A clause-by-clause review has not been completed.
- Current design: only minimal normalized claims may enter a user-local runtime
  cache; committed fixtures are locally generated synthetic values. Raw
  provider payloads, cookies, headers, and account metadata never enter Git.
- Still to decide: data caching and redistribution rights, map attribution,
  privacy and terms URLs, and the metadata a public Codex marketplace listing
  would require.
- Impact: does not block local or self-hosted use. It does block publishing to a
  public Codex marketplace and any commercial use.

## Demonstrations and fixtures are synthetic data

- Fact: `demo/` and `tests/fixtures/providers/` contain only locally generated,
  unmistakably synthetic values. They preserve provider contract shapes and
  failure modes without redistributing captured responses.
- Current decision: public landmarks and government or venue source URLs may
  remain in candidate files. Provider names, inventory, prices, schedules,
  coordinates, route measurements, and tokenized deep links do not.
- Status: no sample-data redistribution decision remains blocked. A regression
  test scans every Git-tracked file for the retired domains and hotel-name list;
  the broader provider-terms question above remains separate.
