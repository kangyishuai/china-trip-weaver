"""Command-line interface for the dependency-free plugin runtime."""

from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path
from typing import Mapping, Optional, Sequence

from . import SCHEMA_VERSION, __version__
from .contracts import canonical_json, read_json, write_canonical_json
from .validate_trip import default_schema_path, validate_file


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ctw", description="Read-only mainland-China trip planning")
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate", help="validate a Trip JSON document")
    validate.add_argument("trip", type=Path)
    validate.add_argument("--schema", type=Path, default=None)
    validate.add_argument("--schema-only", action="store_true")

    validate_candidates = commands.add_parser("validate-candidates", help="validate a researched candidates JSON document")
    validate_candidates.add_argument("candidates", type=Path)

    canonicalize = commands.add_parser("canonicalize", help="print canonical JSON")
    canonicalize.add_argument("trip", type=Path)

    commands.add_parser("doctor", help="show local runtime and schema status")
    plan = commands.add_parser("plan", help="build a candidate-file driven read-only Trip and HTML")
    plan.add_argument("--request", type=Path, required=True)
    plan.add_argument("--candidates", type=Path, required=True)
    plan.add_argument("--rail", default="live")
    plan.add_argument("--mobility", choices=("live", "off"), default="off")
    plan.add_argument("--lodging", choices=("live", "off"), default="off")
    plan.add_argument("--aviation", choices=("auto", "off"), default="auto")
    plan.add_argument("--output-json", type=Path, default=Path("trip.json"))
    plan.add_argument("--output-html", type=Path, default=Path("trip.html"))
    plan.add_argument("--offline-fixture", action="store_true")
    plan.add_argument("--fixed-clock", default=None)
    plan.add_argument("--rail-deadline", type=float, default=90.0)
    plan.add_argument("--mobility-deadline", type=float, default=12.0)
    plan.add_argument("--flyai-deadline", type=float, default=25.0)
    plan.add_argument("--variflight-deadline", type=float, default=15.0)
    replan = commands.add_parser("replan", help="apply a versioned local replan event and render the result")
    replan.add_argument("--trip", type=Path, required=True)
    replan.add_argument("--event", type=Path, required=True)
    replan.add_argument("--base-revision", type=int, required=True)
    replan.add_argument("--output-json", type=Path, required=True)
    replan.add_argument("--output-html", type=Path, required=True)
    replan.add_argument("--fixed-clock", default=None)
    replan.add_argument("--locked-ref", action="append", default=[])

    rail = commands.add_parser("rail", help="query read-only live 12306 inventory through the pinned MCP")
    rail.add_argument("--date", required=True)
    rail.add_argument("--from", dest="from_name", required=True)
    rail.add_argument("--to", dest="to_name", required=True)
    rail.add_argument("--train-filter-flags", default="")
    rail.add_argument("--limit", type=int, default=10)
    rail.add_argument("--deadline", type=float, default=90.0)
    rail.add_argument("--fixture", type=Path, default=None)
    rail.add_argument("--fixed-clock", default=None)
    rail.add_argument("--output-json", type=Path, default=None)

    mobility = commands.add_parser("mobility", help="build a bounded live AMap route matrix for candidates")
    mobility.add_argument("--candidates", type=Path, required=True)
    mobility.add_argument("--modes", default="transit,walking")
    mobility.add_argument("--deadline", type=float, default=12.0)
    mobility.add_argument("--output-json", type=Path, default=None)

    lodging = commands.add_parser("lodging", help="query FlyAI lodging inventory without booking")
    lodging.add_argument("--city", required=True)
    lodging.add_argument("--check-in", required=True)
    lodging.add_argument("--check-out", required=True)
    lodging.add_argument("--deadline", type=float, default=25.0)
    lodging.add_argument("--keyless-trial", action="store_true")
    lodging.add_argument("--output-json", type=Path, default=None)

    air = commands.add_parser("air", help="query FlyAI flight comparisons without booking")
    air.add_argument("--origin", required=True)
    air.add_argument("--destination", required=True)
    air.add_argument("--date", required=True)
    air.add_argument("--deadline", type=float, default=25.0)
    air.add_argument("--keyless-trial", action="store_true")
    air.add_argument("--output-json", type=Path, default=None)

    render = commands.add_parser("render", help="render a validated Trip as deterministic HTML")
    render.add_argument("trip", type=Path)
    render.add_argument("--output", "-o", type=Path, default=None)

    validate_html_command = commands.add_parser("validate-html", help="validate rendered HTML against its Trip")
    validate_html_command.add_argument("html", type=Path)
    validate_html_command.add_argument("trip", type=Path)
    return parser


def main(argv: Optional[Sequence[str]] = None, *, credential_path: Optional[Path] = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "validate":
        report = validate_file(args.trip, schema_path=args.schema, semantic=not args.schema_only)
        if report.ok:
            print("VALID %s" % args.trip)
            return 0
        for issue in report.errors:
            print(issue.render(), file=sys.stderr)
        print("INVALID %s (%d error%s)" % (args.trip, len(report.errors), "" if len(report.errors) == 1 else "s"), file=sys.stderr)
        return 1
    if args.command == "canonicalize":
        try:
            print(canonical_json(read_json(args.trip)))
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            print("J_INVALID / %s" % exc, file=sys.stderr)
            return 1
        return 0
    if args.command == "validate-candidates":
        from .candidates import validate_candidates_file

        report = validate_candidates_file(args.candidates)
        if report.ok:
            print("CANDIDATES VALID %s" % args.candidates)
            return 0
        for issue in report.errors:
            print(issue.render(), file=sys.stderr)
        print("CANDIDATES INVALID %s (%d error%s)" % (
            args.candidates,
            len(report.errors),
            "" if len(report.errors) == 1 else "s",
        ), file=sys.stderr)
        return 1
    if args.command == "doctor":
        from .credentials import provider_credential_status, resolve_credentials
        from .errors import CTWError

        try:
            credentials = resolve_credentials(credential_path=credential_path)
        except CTWError as exc:
            print(canonical_json({
                "credential_error": {
                    "code": exc.code,
                    "status": exc.error_class,
                },
            }), file=sys.stderr)
            return 1
        from .plugin_conflicts import conflict_report

        conflicts = conflict_report()
        print(canonical_json({
            "plugin_version": __version__,
            "providers": dict(provider_credential_status(credentials)),
            "python": platform.python_version(),
            "schema_exists": default_schema_path().is_file(),
            "schema_version": SCHEMA_VERSION,
            "skill_conflicts": conflicts,
        }))
        return 1 if conflicts["status"] == "conflict" else 0
    if args.command == "plan":
        from .clock import FixedClock, SystemClock
        from .flyai_inventory import FlyAIBackend
        from .mobility import MobilityBackend
        from .planning import RailBackend, plan_trip
        from .variflight_enrichment import VariFlightBackend

        try:
            request_value = read_json(args.request)
            candidates_value = read_json(args.candidates)
            if args.fixed_clock and not args.offline_fixture:
                raise ValueError("--fixed-clock is allowed only with --offline-fixture")
            if args.offline_fixture and args.rail == "live":
                raise ValueError("--offline-fixture requires --rail off or fixture:<file>")
            if args.offline_fixture and args.mobility != "off":
                raise ValueError("--offline-fixture requires --mobility off")
            if args.offline_fixture and args.lodging != "off":
                raise ValueError("--offline-fixture requires --lodging off")
            clock = FixedClock.from_iso(args.fixed_clock) if args.fixed_clock else SystemClock()
            repo_root = Path(__file__).resolve().parents[4]
            rail_backend = RailBackend.from_spec(args.rail, repo_root, deadline_seconds=args.rail_deadline)
            mobility_backend = MobilityBackend.from_spec(
                args.mobility, repo_root, deadline_seconds=args.mobility_deadline,
            )
            flyai_backend = FlyAIBackend.from_spec(
                args.lodging, repo_root, deadline_seconds=args.flyai_deadline,
            )
            aviation_mode = "off" if args.offline_fixture else args.aviation
            variflight_backend = VariFlightBackend.from_spec(
                aviation_mode, repo_root, deadline_seconds=args.variflight_deadline,
            )
            result = plan_trip(
                request_value, candidates_value, clock, rail_backend, mobility_backend,
                flyai_backend, variflight_backend,
            )
            args.output_json.parent.mkdir(parents=True, exist_ok=True)
            args.output_html.parent.mkdir(parents=True, exist_ok=True)
            write_canonical_json(args.output_json, result.trip)
            args.output_html.write_text(result.html, encoding="utf-8")
            print("PLAN_COMPLETE json=%s html=%s mode=%s stages=%s calls=%s trip_sha256=%s html_sha256=%s errors=0" % (
                args.output_json,
                args.output_html,
                result.trip["mode"],
                ",".join(result.stages),
                ",".join(result.business_calls),
                result.trip_sha256,
                result.html_sha256,
            ))
            return 0
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            print("PLAN_FAILED %s" % exc, file=sys.stderr)
            return 1
    if args.command == "mobility":
        from .clock import SystemClock
        from .errors import CTWError
        from .mobility import MobilityBackend, normalize_modes

        try:
            if args.deadline <= 0:
                raise ValueError("--deadline must be positive")
            candidates_value = read_json(args.candidates)
            modes = normalize_modes(tuple(part for part in args.modes.split(",") if part.strip()))
            repo_root = Path(__file__).resolve().parents[4]
            backend = MobilityBackend.from_spec("live", repo_root, deadline_seconds=args.deadline)
            result = backend.resolve(candidates_value, SystemClock(), modes)
            output = result.as_dict()
            if args.output_json is not None:
                args.output_json.parent.mkdir(parents=True, exist_ok=True)
                write_canonical_json(args.output_json, output)
                print("MOBILITY_COMPLETE output=%s cells=%d locations=%d status=%s calls=%d" % (
                    args.output_json,
                    len(result.cells),
                    len(result.locations),
                    result.health["status"],
                    len(result.business_calls),
                ))
            else:
                print(canonical_json(output))
            return 0 if result.cells and result.health["status"] == "ready" else 1
        except CTWError as exc:
            print("MOBILITY_FAILED %s %s" % (exc.error_class, exc.code), file=sys.stderr)
            return 1
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            print("MOBILITY_FAILED %s" % exc, file=sys.stderr)
            return 1
    if args.command in ("lodging", "air"):
        from .clock import SystemClock
        from .errors import CTWError
        from .flyai_inventory import FlyAIBackend

        try:
            if args.deadline <= 0:
                raise ValueError("--deadline must be positive")
            repo_root = Path(__file__).resolve().parents[4]
            backend = FlyAIBackend.from_spec(
                "live",
                repo_root,
                deadline_seconds=args.deadline,
                keyless_trial=args.keyless_trial,
            )
            clock = SystemClock()
            if args.command == "lodging":
                result = backend.query_lodging(args.city, args.check_in, args.check_out, clock)
                items = list(result.normalized_items)
                output_key = "lodgings"
            else:
                result = backend.query_flight(
                    args.origin,
                    args.destination,
                    args.date,
                    "city-" + args.origin,
                    "city-" + args.destination,
                    clock,
                )
                items = list(result.normalized_items)
                output_key = "transport_legs"
            price_types = _price_type_counts(items)
            transport = backend.transport
            output = {
                "provider": result.provider,
                "provider_version": result.provider_version,
                output_key: items,
                "claims": list(result.claims),
                "health": result.health,
                "warnings": list(result.warnings),
                "error_class": result.error_class,
                "stats": {
                    "items": len(items),
                    "price_types": price_types,
                    "business_calls": int(getattr(transport, "calls", 0)),
                    "probe_calls": int(getattr(transport, "probe_calls", 0)),
                    "credential": "configured" if backend.credentials.get("FLYAI_API_KEY") else "keyless-trial",
                },
            }
            if args.output_json is not None:
                args.output_json.parent.mkdir(parents=True, exist_ok=True)
                write_canonical_json(args.output_json, output)
                print("%s_COMPLETE output=%s items=%d status=%s price_types=%s" % (
                    args.command.upper(), args.output_json, len(items), result.health["status"],
                    ",".join("%s:%d" % pair for pair in sorted(price_types.items())) or "none",
                ))
            else:
                print(canonical_json(output))
            return 0 if items else 1
        except CTWError as exc:
            print("%s_FAILED %s %s" % (args.command.upper(), exc.error_class, exc.code), file=sys.stderr)
            return 1
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            print("%s_FAILED %s" % (args.command.upper(), exc), file=sys.stderr)
            return 1
    if args.command == "rail":
        from .clock import FixedClock, SystemClock
        from .contracts import ProviderRequest
        from .credentials import resolve_credentials
        from .providers.base import ProviderContext, ReplayTransport, stable_id
        from .providers.mcp_stdio import RailMCPStdioTransport
        from .providers.rail12306 import Rail12306Adapter

        try:
            if args.limit <= 0 or args.deadline <= 0:
                raise ValueError("--limit and --deadline must be positive")
            if args.fixed_clock and args.fixture is None:
                raise ValueError("--fixed-clock is allowed only with --fixture")
            repo_root = Path(__file__).resolve().parents[4]
            if args.fixture is not None:
                fixture = read_json(args.fixture)
                if fixture.get("provider") != "rail12306" or not isinstance(fixture.get("transport"), dict):
                    raise ValueError("--fixture must be a rail12306 provider fixture")
                clock = FixedClock.from_iso(args.fixed_clock or fixture["captured_at"])
                transport = ReplayTransport(fixture["transport"], raw_ref=args.fixture.as_posix())
            else:
                clock = SystemClock()
                credentials = resolve_credentials({}, repo_root / ".tmp" / "rail-no-credentials")
                transport = RailMCPStdioTransport(
                    cache_dir=repo_root / ".npm-cache",
                    credentials=credentials,
                    cwd=repo_root,
                )
            request = ProviderRequest(
                request_id=stable_id("rail-query", args.date, args.from_name, args.to_name, args.train_filter_flags, args.limit),
                capability="rail",
                parameters={
                    "date": args.date,
                    "from_name": args.from_name,
                    "to_name": args.to_name,
                    "from_ref": stable_id("place", "city", args.from_name),
                    "to_ref": stable_id("place", "city", args.to_name),
                    "train_filter_flags": args.train_filter_flags,
                    "limited_num": args.limit,
                },
                deadline_ms=int(args.deadline * 1000),
                as_of=args.date,
                cache_policy="bypass",
                trace={"stage": "rail-cli"},
            )
            context = ProviderContext(
                clock=clock,
                credentials=resolve_credentials({}, repo_root / ".tmp" / "rail-no-credentials"),
                transport=transport,
            )
            result = Rail12306Adapter().query(request, context)
            output = {
                "provider": result.provider,
                "provider_version": result.provider_version,
                "queried_at": result.queried_at,
                "transport_legs": list(result.normalized_items),
                "claims": list(result.claims),
                "health": result.health,
                "warnings": list(result.warnings),
                "error_class": result.error_class,
            }
            if args.output_json is not None:
                args.output_json.parent.mkdir(parents=True, exist_ok=True)
                write_canonical_json(args.output_json, output)
                print("RAIL_COMPLETE output=%s legs=%d status=%s error=%s" % (
                    args.output_json,
                    len(result.normalized_items),
                    result.health["status"],
                    result.error_class or "none",
                ))
            else:
                print(canonical_json(output))
            if result.normalized_items:
                return 0
            return 2 if result.error_class == "no_results" else 1
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            print("RAIL_FAILED %s" % exc, file=sys.stderr)
            return 1
    if args.command == "replan":
        import hashlib

        from .clock import FixedClock, SystemClock
        from .render import render_trip, validate_html
        from .replan import ReplanError, replan_trip
        from .validate_trip import validate_trip

        try:
            trip = read_json(args.trip)
            event_document = read_json(args.event)
            event = event_document.get("event", event_document)
            locked_refs = list(event_document.get("user_locked_refs", ())) + list(args.locked_ref)
            if not isinstance(event, dict) or not isinstance(locked_refs, list):
                raise ValueError("event document has the wrong shape")
            base_report = validate_trip(trip)
            if not base_report.ok:
                raise ValueError("base Trip is invalid: " + "; ".join(item.render() for item in base_report.errors))
            clock = FixedClock.from_iso(args.fixed_clock) if args.fixed_clock else SystemClock()
            result = replan_trip(trip, event, args.base_revision, locked_refs, clock)
            report = validate_trip(result.trip)
            if not report.ok:
                raise ValueError("replanned Trip is invalid: " + "; ".join(item.render() for item in report.errors))
            rendered = render_trip(result.trip)
            html_report = validate_html(rendered, result.trip)
            if not html_report.ok:
                raise ValueError("replanned HTML is invalid: " + "; ".join(item.render() for item in html_report.errors))
            args.output_json.parent.mkdir(parents=True, exist_ok=True)
            args.output_html.parent.mkdir(parents=True, exist_ok=True)
            write_canonical_json(args.output_json, result.trip)
            args.output_html.write_text(rendered, encoding="utf-8")
            print("REPLAN_COMPLETE json=%s html=%s revision=%d patch=%s trigger=%s reverify=%d trip_sha256=%s html_sha256=%s errors=0" % (
                args.output_json,
                args.output_html,
                result.trip["revision"]["number"],
                result.patch["patch_id"],
                result.patch["trigger"],
                len(result.reverify_claim_ids),
                hashlib.sha256(canonical_json(result.trip).encode("utf-8")).hexdigest(),
                hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
            ))
            return 0
        except ReplanError as exc:
            print("REPLAN_FAILED %s %s" % (exc.code, exc), file=sys.stderr)
            return 1
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            print("REPLAN_FAILED %s" % exc, file=sys.stderr)
            return 1
    if args.command == "render":
        import hashlib

        from .render import RendererError, render_trip, safe_output_name, validate_html

        try:
            trip = read_json(args.trip)
            rendered = render_trip(trip)
            report = validate_html(rendered, trip)
            if not report.ok:
                for issue in report.errors:
                    print(issue.render(), file=sys.stderr)
                return 1
            output = args.output or Path.cwd() / safe_output_name(trip["trip_id"])
            output.write_text(rendered, encoding="utf-8")
            digest = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
            print("RENDERED %s sha256=%s errors=0" % (output, digest))
            return 0
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError, RendererError) as exc:
            print("RENDER_FAILED %s" % exc, file=sys.stderr)
            return 1
    if args.command == "validate-html":
        from .render import validate_html

        try:
            trip = read_json(args.trip)
            rendered = args.html.read_text(encoding="utf-8")
            report = validate_html(rendered, trip)
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            print("HTML_INVALID %s" % exc, file=sys.stderr)
            return 1
        if report.ok:
            print("HTML VALID %s errors=0" % args.html)
            return 0
        for issue in report.errors:
            print(issue.render(), file=sys.stderr)
        print("HTML INVALID %s errors=%d" % (args.html, len(report.errors)), file=sys.stderr)
        return 1
    print("%s is not available until its implementation milestone" % args.command, file=sys.stderr)
    return 3


def _price_type_counts(items: Sequence[Mapping[str, object]]) -> Mapping[str, int]:
    counts = {}
    for item in items:
        price = item.get("price")
        if not isinstance(price, dict):
            continue
        price_type = price.get("price_type")
        if isinstance(price_type, str):
            counts[price_type] = counts.get(price_type, 0) + 1
    return counts


if __name__ == "__main__":
    raise SystemExit(main())
