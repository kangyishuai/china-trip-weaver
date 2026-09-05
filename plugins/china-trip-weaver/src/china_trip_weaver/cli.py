"""Command-line interface for the dependency-free plugin runtime."""

from __future__ import annotations

import argparse
import json
import platform
import sys
import threading
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, TextIO

from . import SCHEMA_VERSION, __version__
from .contracts import canonical_json, read_json, write_canonical_json
from .validate_trip import default_schema_path, validate_file


PROGRESS_FIELDS = frozenset((
    "event", "provider", "capability", "scope", "status", "attempt",
    "delay_seconds", "command", "error_class", "items",
))
PROGRESS_EVENTS = frozenset(("probe", "query", "degrade", "retry", "completion"))


class _NDJSONProgress:
    """Thread-safe, allowlisted progress output that cannot serialize provider data."""

    def __init__(self, mode: Optional[str], stream: Optional[TextIO] = None) -> None:
        self.enabled = mode == "ndjson"
        self.stream = stream or sys.stderr
        self._lock = threading.Lock()

    def emit(self, event: Mapping[str, Any]) -> None:
        if not self.enabled or event.get("event") not in PROGRESS_EVENTS:
            return
        safe = {}
        for name in PROGRESS_FIELDS:
            value = event.get(name)
            if value is None or isinstance(value, bool):
                continue
            if isinstance(value, str):
                safe[name] = value[:80]
            elif isinstance(value, int):
                safe[name] = value
            elif isinstance(value, float):
                safe[name] = round(value, 3)
        safe["event"] = event["event"]
        line = canonical_json(safe)
        with self._lock:
            print(line, file=self.stream, flush=True)


def _add_progress_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--progress", choices=("ndjson",), default=argparse.SUPPRESS,
        help="write allowlisted progress events as NDJSON to stderr",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ctw", description="Read-only mainland-China trip planning")
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
    parser.add_argument("--progress", choices=("ndjson",), default=None)
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate", help="validate a Trip JSON document")
    validate.add_argument("trip", type=Path)
    validate.add_argument("--schema", type=Path, default=None)
    validate.add_argument("--schema-only", action="store_true")

    validate_candidates = commands.add_parser("validate-candidates", help="validate a researched candidates JSON document")
    validate_candidates.add_argument("candidates", type=Path)

    candidates = commands.add_parser("candidates", help="initialize or append to a researched candidates file")
    candidate_commands = candidates.add_subparsers(dest="candidate_command", required=True)
    candidates_init = candidate_commands.add_parser("init", help="create an empty five-key candidate skeleton")
    candidates_init.add_argument("path", type=Path)
    candidates_init.add_argument("--force", action="store_true")

    add_poi = candidate_commands.add_parser("add-poi", help="append one researched POI candidate")
    add_poi.add_argument("path", type=Path)
    add_poi.add_argument("--name", required=True)
    add_poi.add_argument("--city", required=True)
    add_poi.add_argument("--category", required=True)
    add_poi.add_argument("--source-url", required=True)
    add_poi.add_argument("--provider", default="user-pasted-only")
    add_poi.add_argument("--confidence", type=float, default=0.55)
    add_poi.add_argument("--duration-minutes", type=int, default=None)
    add_poi.add_argument("--opens-at", default=None)
    add_poi.add_argument("--closes-at", default=None)
    add_poi.add_argument(
        "--opening-status", choices=("verified", "tentative", "closed", "unknown"),
        default="tentative",
    )
    add_poi.add_argument("--price", dest="price_amount", type=float, default=None)
    add_poi.add_argument("--queried-at", default=None)
    add_poi.add_argument(
        "--verify-name", action="store_true",
        help="check the POI name with AMap before writing; failure never blocks the write",
    )

    add_lodging = candidate_commands.add_parser("add-lodging", help="append one researched lodging candidate")
    add_lodging.add_argument("path", type=Path)
    add_lodging.add_argument("--name", required=True)
    add_lodging.add_argument("--city", required=True)
    add_lodging.add_argument("--area", default=None)
    add_lodging.add_argument("--check-in", required=True)
    add_lodging.add_argument("--check-out", required=True)
    add_lodging.add_argument("--source-url", required=True)
    add_lodging.add_argument("--provider", default="user-pasted-only")
    add_lodging.add_argument("--confidence", type=float, default=0.55)
    add_lodging.add_argument("--nightly-price", type=float, default=None)
    tax_group = add_lodging.add_mutually_exclusive_group()
    tax_group.add_argument("--includes-taxes", dest="includes_taxes", action="store_true")
    tax_group.add_argument("--excludes-taxes", dest="includes_taxes", action="store_false")
    add_lodging.set_defaults(includes_taxes=None)
    add_lodging.add_argument("--locked", action="store_true")
    add_lodging.add_argument("--queried-at", default=None)

    canonicalize = commands.add_parser("canonicalize", help="print canonical JSON")
    canonicalize.add_argument("trip", type=Path)

    doctor = commands.add_parser("doctor", help="show local runtime and schema status")
    _add_progress_argument(doctor)
    doctor.add_argument(
        "--probe", action="store_true",
        help="run bounded read-only provider contract, network, and business probes",
    )
    plan = commands.add_parser("plan", help="build a candidate-file driven read-only Trip and HTML")
    _add_progress_argument(plan)
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

    journey = commands.add_parser("journey", help="plan or validate a multi-Trip Journey")
    journey_commands = journey.add_subparsers(dest="journey_command", required=True)
    journey_plan = journey_commands.add_parser(
        "plan", help="split a long request into complete one-to-seven-day Trips",
    )
    _add_progress_argument(journey_plan)
    journey_plan.add_argument("--request", type=Path, required=True)
    journey_plan.add_argument("--candidates", type=Path, required=True)
    journey_plan.add_argument("--rail", default="live")
    journey_plan.add_argument("--mobility", choices=("live", "off"), default="off")
    journey_plan.add_argument("--lodging", choices=("live", "off"), default="off")
    journey_plan.add_argument("--aviation", choices=("auto", "off"), default="auto")
    journey_plan.add_argument(
        "--expected-segment-days",
        type=int,
        default=None,
        help="preferred Trip length in days (1-7); segmentation still obeys the 7-day cap and the lodging chain",
    )
    journey_plan.add_argument(
        "--amap-total-max-calls",
        type=int,
        default=None,
        help="Journey-wide AMap call ceiling; default is 80 per resulting Trip and each Trip remains capped at 80",
    )
    journey_plan.add_argument("--output-json", type=Path, default=Path("journey.json"))
    journey_plan.add_argument("--offline-fixture", action="store_true")
    journey_plan.add_argument("--fixed-clock", default=None)
    journey_plan.add_argument("--rail-deadline", type=float, default=90.0)
    journey_plan.add_argument("--mobility-deadline", type=float, default=12.0)
    journey_plan.add_argument("--flyai-deadline", type=float, default=25.0)
    journey_plan.add_argument("--variflight-deadline", type=float, default=15.0)
    journey_validate = journey_commands.add_parser(
        "validate", help="validate a Journey and every embedded Trip",
    )
    journey_validate.add_argument("journey", type=Path)
    journey_validate.add_argument("--schema", type=Path, default=None)
    journey_render = journey_commands.add_parser(
        "render", help="render a validated Journey as a deterministic overview page",
    )
    journey_render.add_argument("journey", type=Path)
    journey_render.add_argument("--output", "-o", type=Path, default=None)
    journey_validate_html = journey_commands.add_parser(
        "validate-html", help="validate a Journey overview page against its Journey",
    )
    journey_validate_html.add_argument("html", type=Path)
    journey_validate_html.add_argument("journey", type=Path)

    replan = commands.add_parser("replan", help="apply a versioned local replan event and render the result")
    replan.add_argument("--trip", type=Path, required=True)
    replan.add_argument(
        "--event",
        type=Path,
        required=True,
        help=(
            "path to a JSON event file; required fields: type (closure, weather, delay, or "
            "user_delete) and subject_ref (the target slot's slot_id, or the ref_id it schedules); delay also requires "
            "delta_minutes; closure and weather also require replacement_slot; example delay "
            'event: {"type": "delay", "subject_ref": "slot-2", "delta_minutes": 15}'
        ),
    )
    replan.add_argument("--base-revision", type=int, required=True)
    replan.add_argument("--output-json", type=Path, required=True)
    replan.add_argument("--output-html", type=Path, required=True)
    replan.add_argument("--fixed-clock", default=None)
    replan.add_argument("--locked-ref", action="append", default=[])

    rail = commands.add_parser("rail", help="query read-only live 12306 inventory through the pinned MCP")
    _add_progress_argument(rail)
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
    _add_progress_argument(mobility)
    mobility.add_argument("--candidates", type=Path, required=True)
    mobility.add_argument("--modes", default="transit,walking")
    mobility.add_argument("--deadline", type=float, default=12.0)
    mobility.add_argument("--output-json", type=Path, default=None)

    lodging = commands.add_parser("lodging", help="query FlyAI lodging inventory without booking")
    _add_progress_argument(lodging)
    lodging.add_argument("--city", required=True)
    lodging.add_argument("--check-in", required=True)
    lodging.add_argument("--check-out", required=True)
    lodging.add_argument("--adults", type=int, default=1)
    lodging.add_argument("--rooms", type=int, default=1)
    lodging.add_argument("--room-constraint", default=None)
    lodging.add_argument("--bed-config", default=None)
    lodging.add_argument("--parking-required", action="store_true")
    lodging.add_argument("--cancellation-preference", default=None)
    lodging.add_argument("--deadline", type=float, default=25.0)
    lodging.add_argument("--keyless-trial", action="store_true")
    lodging.add_argument("--output-json", type=Path, default=None)

    air = commands.add_parser("air", help="query FlyAI flight comparisons without booking")
    _add_progress_argument(air)
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


def _check_candidate_poi_name(
    name: str,
    city: str,
    clock: Any,
    credential_path: Optional[Path],
    transport: Optional[Any],
) -> Any:
    from .credentials import resolve_credentials
    from .errors import CTWError
    from .mobility import POINameCheck, check_poi_name_identity
    from .providers.amap_http import AMapCallBudget, AMapHTTPTransport, MAX_QPS

    try:
        credentials = resolve_credentials(credential_path=credential_path)
    except CTWError:
        return POINameCheck("unavailable", ("credential_error",))
    active_transport = transport
    if credentials.get("AMAP_WEBSERVICE_KEY") and active_transport is None:
        active_transport = AMapHTTPTransport(
            credentials,
            budget=AMapCallBudget(max_calls=2, qps=MAX_QPS),
        )
    try:
        return check_poi_name_identity(
            name,
            city,
            clock,
            credentials,
            active_transport,
        )
    except Exception:
        return POINameCheck("unavailable", ("check_failed",))


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    credential_path: Optional[Path] = None,
    poi_name_transport: Optional[Any] = None,
) -> int:
    args = _parser().parse_args(argv)
    progress = _NDJSONProgress(getattr(args, "progress", None))
    if args.command == "validate":
        report = validate_file(args.trip, schema_path=args.schema, semantic=not args.schema_only)
        if report.ok:
            print("VALID %s" % args.trip)
            return 0
        for issue in report.errors:
            print(issue.render(), file=sys.stderr)
        print("INVALID %s (%d error%s)" % (args.trip, len(report.errors), "" if len(report.errors) == 1 else "s"), file=sys.stderr)
        return 1
    if args.command == "candidates":
        from .candidates import add_lodging_candidate, add_poi_candidate, initialize_candidates
        from .clock import FixedClock, SystemClock

        try:
            if args.candidate_command == "init":
                initialize_candidates(args.path, overwrite=args.force)
                print("CANDIDATES_INITIALIZED %s" % args.path)
                return 0
            clock = FixedClock.from_iso(args.queried_at) if args.queried_at else SystemClock()
            if args.candidate_command == "add-poi":
                name_check = None
                if args.verify_name:
                    name_check = _check_candidate_poi_name(
                        args.name,
                        args.city,
                        clock,
                        credential_path,
                        poi_name_transport,
                    )
                entity = add_poi_candidate(
                    args.path,
                    name=args.name,
                    city=args.city,
                    category=args.category,
                    source_url=args.source_url,
                    provider=args.provider,
                    clock=clock,
                    confidence=args.confidence,
                    duration_minutes=args.duration_minutes,
                    opens_at=args.opens_at,
                    closes_at=args.closes_at,
                    opening_status=args.opening_status,
                    price_amount=args.price_amount,
                )
                if name_check is not None:
                    print(name_check.render())
                print("CANDIDATE_POI_ADDED %s id=%s" % (args.path, entity["poi_id"]))
                return 0
            entity = add_lodging_candidate(
                args.path,
                name=args.name,
                city=args.city,
                area=args.area,
                check_in=args.check_in,
                check_out=args.check_out,
                source_url=args.source_url,
                provider=args.provider,
                clock=clock,
                confidence=args.confidence,
                nightly_price=args.nightly_price,
                includes_taxes=args.includes_taxes,
                locked=args.locked,
            )
            print("CANDIDATE_LODGING_ADDED %s id=%s" % (args.path, entity["lodging_id"]))
            return 0
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            print("CANDIDATES_FAILED %s" % exc, file=sys.stderr)
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
        payload = {
            "plugin_version": __version__,
            "providers": dict(provider_credential_status(credentials)),
            "python": platform.python_version(),
            "schema_exists": default_schema_path().is_file(),
            "schema_version": SCHEMA_VERSION,
            "skill_conflicts": conflicts,
        }
        if args.probe:
            repo_root = Path(__file__).resolve().parents[4]
            payload["probes"] = _doctor_probe_report(credentials, repo_root, progress)
            progress.emit({"event": "completion", "command": "doctor", "status": "ok"})
        print(canonical_json(payload))
        return 1 if conflicts["status"] == "conflict" else 0
    if args.command == "journey":
        from .journey import plan_journey, validate_journey_file

        if args.journey_command == "validate":
            report = validate_journey_file(args.journey, schema_path=args.schema)
            if report.ok:
                value = read_json(args.journey)
                print("JOURNEY VALID %s trips=%d" % (args.journey, len(value["trips"])))
                return 0
            for issue in report.errors:
                print(issue.render(), file=sys.stderr)
            print("JOURNEY INVALID %s (%d error%s)" % (
                args.journey,
                len(report.errors),
                "" if len(report.errors) == 1 else "s",
            ), file=sys.stderr)
            return 1

        if args.journey_command == "render":
            import hashlib

            from .render import (
                RendererError,
                render_journey,
                safe_output_name,
                validate_journey_html,
            )

            try:
                journey_value = read_json(args.journey)
                rendered = render_journey(journey_value)
                report = validate_journey_html(rendered, journey_value)
                if not report.ok:
                    for issue in report.errors:
                        print(issue.render(), file=sys.stderr)
                    return 1
                output = args.output or Path.cwd() / safe_output_name(
                    journey_value["journey_id"]
                )
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(rendered, encoding="utf-8")
                digest = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
                print("JOURNEY_RENDERED %s sha256=%s errors=0" % (output, digest))
                return 0
            except (
                OSError,
                UnicodeError,
                ValueError,
                json.JSONDecodeError,
                RendererError,
            ) as exc:
                print("JOURNEY_RENDER_FAILED %s" % exc, file=sys.stderr)
                return 1

        if args.journey_command == "validate-html":
            from .render import validate_journey_html

            try:
                journey_value = read_json(args.journey)
                rendered = args.html.read_text(encoding="utf-8")
                report = validate_journey_html(rendered, journey_value)
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
                print("JOURNEY_HTML_INVALID %s" % exc, file=sys.stderr)
                return 1
            if report.ok:
                print("JOURNEY HTML VALID %s errors=0" % args.html)
                return 0
            for issue in report.errors:
                print(issue.render(), file=sys.stderr)
            print(
                "JOURNEY HTML INVALID %s errors=%d" % (
                    args.html,
                    len(report.errors),
                ),
                file=sys.stderr,
            )
            return 1

        from .clock import FixedClock, SystemClock
        from .flyai_inventory import AMapLodgingBackend, FlyAIBackend
        from .mobility import MobilityBackend
        from .planning import RailBackend
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
            rail_backend = RailBackend.from_spec(
                args.rail, repo_root, deadline_seconds=args.rail_deadline,
            )
            mobility_backend = MobilityBackend.from_spec(
                args.mobility, repo_root, deadline_seconds=args.mobility_deadline,
            )
            flyai_backend = FlyAIBackend.from_spec(
                args.lodging, repo_root, deadline_seconds=args.flyai_deadline,
            )
            amap_lodging_backend = AMapLodgingBackend.from_spec(
                "auto" if args.lodging == "live" else "off",
                repo_root,
                deadline_seconds=args.mobility_deadline,
            )
            aviation_mode = "off" if args.offline_fixture else args.aviation
            variflight_backend = VariFlightBackend.from_spec(
                aviation_mode, repo_root, deadline_seconds=args.variflight_deadline,
            )
            for backend in (
                rail_backend, mobility_backend, flyai_backend,
                amap_lodging_backend, variflight_backend,
            ):
                _attach_progress(backend, progress)
            result = plan_journey(
                request_value,
                candidates_value,
                clock,
                rail_backend,
                mobility_backend,
                flyai_backend,
                variflight_backend,
                amap_lodging_backend,
                expected_segment_days=args.expected_segment_days,
                amap_total_max_calls=args.amap_total_max_calls,
            )
            args.output_json.parent.mkdir(parents=True, exist_ok=True)
            write_canonical_json(args.output_json, result.journey)
            trip_days = [len(item["days"]) for item in result.journey["trips"]]
            print(
                "JOURNEY_PLAN_COMPLETE json=%s trips=%d days=%d max_trip_days=%d calls=%s journey_sha256=%s errors=0"
                % (
                    args.output_json,
                    len(trip_days),
                    sum(trip_days),
                    max(trip_days),
                    ",".join(result.business_calls),
                    result.journey_sha256,
                )
            )
            progress.emit({
                "event": "completion", "command": "journey-plan", "status": "ok",
                "items": len(trip_days),
            })
            return 0
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            _progress_failed(progress, "journey-plan")
            print("JOURNEY_PLAN_FAILED %s" % exc, file=sys.stderr)
            return 1
    if args.command == "plan":
        from .clock import FixedClock, SystemClock
        from .flyai_inventory import AMapLodgingBackend, FlyAIBackend
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
            amap_lodging_backend = AMapLodgingBackend.from_spec(
                "auto" if args.lodging == "live" else "off",
                repo_root,
                deadline_seconds=args.mobility_deadline,
            )
            aviation_mode = "off" if args.offline_fixture else args.aviation
            variflight_backend = VariFlightBackend.from_spec(
                aviation_mode, repo_root, deadline_seconds=args.variflight_deadline,
            )
            for backend in (
                rail_backend, mobility_backend, flyai_backend,
                amap_lodging_backend, variflight_backend,
            ):
                _attach_progress(backend, progress)
            result = plan_trip(
                request_value, candidates_value, clock, rail_backend, mobility_backend,
                flyai_backend, variflight_backend, amap_lodging_backend,
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
            progress.emit({"event": "completion", "command": "plan", "status": "ok"})
            return 0
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            _progress_failed(progress, "plan")
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
            _attach_progress(backend, progress)
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
            progress.emit({
                "event": "completion", "command": "mobility",
                "status": "ok" if result.cells and result.health["status"] == "ready" else "degraded",
                "items": len(result.cells),
            })
            return 0 if result.cells and result.health["status"] == "ready" else 1
        except CTWError as exc:
            _progress_failed(progress, "mobility", exc.error_class)
            print("MOBILITY_FAILED %s %s" % (exc.error_class, exc.code), file=sys.stderr)
            return 1
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            _progress_failed(progress, "mobility")
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
            _attach_progress(backend, progress)
            clock = SystemClock()
            if args.command == "lodging":
                result = backend.query_lodging(
                    args.city,
                    args.check_in,
                    args.check_out,
                    clock,
                    party={"adults": args.adults, "children": 0},
                    rooms=args.rooms,
                    adult_count=args.adults,
                    occupancy=args.room_constraint,
                    bed_config=args.bed_config,
                    parking_required=args.parking_required,
                    cancellation_preference=args.cancellation_preference,
                )
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
            progress.emit({
                "event": "completion", "command": args.command,
                "provider": result.provider,
                "status": "ok" if items else "degraded", "items": len(items),
            })
            return 0 if items else 1
        except CTWError as exc:
            _progress_failed(progress, args.command, exc.error_class)
            print("%s_FAILED %s %s" % (args.command.upper(), exc.error_class, exc.code), file=sys.stderr)
            return 1
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            _progress_failed(progress, args.command)
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
            _attach_progress(transport, progress)
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
            progress.emit({
                "event": "completion", "command": "rail", "provider": result.provider,
                "status": "ok" if result.normalized_items else "degraded",
                "items": len(result.normalized_items),
            })
            if result.normalized_items:
                return 0
            return 2 if result.error_class == "no_results" else 1
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            _progress_failed(progress, "rail")
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


def _attach_progress(target: Any, progress: _NDJSONProgress) -> None:
    if not progress.enabled or target is None:
        return
    transport = getattr(target, "transport", target)
    if transport is None:
        return
    try:
        transport.progress = progress.emit
    except (AttributeError, TypeError):
        return


def _progress_failed(progress: _NDJSONProgress, command: str, error_class: str = "internal") -> None:
    progress.emit({
        "event": "degrade", "command": command,
        "status": "error", "error_class": error_class,
    })
    progress.emit({"event": "completion", "command": command, "status": "error"})


def _doctor_probe_report(credentials: Any, repo_root: Path, progress: _NDJSONProgress) -> Mapping[str, Any]:
    import concurrent.futures

    from .credentials import provider_credential_status

    credential_status = dict(provider_credential_status(credentials))
    probes = {
        "amap": lambda: _probe_amap(credentials, repo_root, credential_status["amap"], progress),
        "flyai": lambda: _probe_flyai(credentials, repo_root, credential_status["flyai"], progress),
        "variflight": lambda: _probe_variflight(
            credentials, repo_root, credential_status["variflight"], progress,
        ),
    }
    report = {
        "anysearch": {
            "credential": credential_status["anysearch"],
            "contract": "unsupported",
            "network": "unsupported",
            "business": "unsupported",
        },
    }
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(probes)) as executor:
        futures = {provider: executor.submit(run) for provider, run in probes.items()}
        for provider, future in futures.items():
            try:
                report[provider] = future.result()
            except Exception:
                report[provider] = {
                    "credential": credential_status[provider],
                    "contract": "failed",
                    "network": "failed",
                    "business": "not_run",
                }
    return report


def _probe_flyai(
    credentials: Any,
    repo_root: Path,
    credential_status: str,
    progress: _NDJSONProgress,
) -> Mapping[str, str]:
    from datetime import timedelta

    from .clock import SystemClock
    from .contracts import ProviderRequest
    from .providers.base import ProviderContext, stable_id
    from .providers.flyai import FlyAIAdapter
    from .providers.flyai_cli import FlyAISubprocessTransport

    progress.emit({"event": "probe", "provider": "flyai", "scope": "doctor", "status": "started"})
    clock = SystemClock()
    check_in = (clock.now().date() + timedelta(days=7)).isoformat()
    check_out = (clock.now().date() + timedelta(days=8)).isoformat()
    request = ProviderRequest(
        request_id=stable_id("doctor-flyai", check_in),
        capability="lodging",
        parameters={"city": "北京", "check_in": check_in, "check_out": check_out},
        deadline_ms=8000,
        as_of=check_in,
        cache_policy="bypass",
        trace={"stage": "doctor"},
    )
    transport = FlyAISubprocessTransport(
        credentials,
        cache_dir=repo_root / ".npm-cache",
        temp_root=repo_root / ".tmp" / "doctor-flyai",
        cwd=repo_root,
        progress=progress.emit if progress.enabled else None,
    )
    result = FlyAIAdapter().query(request, ProviderContext(clock, credentials, transport))
    return _probe_layers(credential_status, result)


def _probe_amap(
    credentials: Any,
    repo_root: Path,
    credential_status: str,
    progress: _NDJSONProgress,
) -> Mapping[str, str]:
    del repo_root
    if credential_status == "missing":
        return _not_run_probe(credential_status)
    from .clock import SystemClock
    from .contracts import ProviderRequest
    from .providers.amap import AMapAdapter
    from .providers.amap_http import AMapCallBudget, AMapHTTPTransport
    from .providers.base import ProviderContext, stable_id

    progress.emit({"event": "probe", "provider": "amap", "scope": "doctor", "status": "started"})
    clock = SystemClock()
    request = ProviderRequest(
        request_id=stable_id("doctor-amap", "北京", "天安门"),
        capability="poi",
        parameters={"city": "北京", "keywords": "天安门", "page_size": 1, "page_num": 1},
        deadline_ms=6000,
        as_of=clock.now().date().isoformat(),
        cache_policy="bypass",
        trace={"stage": "doctor"},
    )
    transport = AMapHTTPTransport(credentials, budget=AMapCallBudget(max_calls=2))
    _attach_progress(transport, progress)
    result = AMapAdapter().query(request, ProviderContext(clock, credentials, transport))
    return _probe_layers(credential_status, result)


def _probe_variflight(
    credentials: Any,
    repo_root: Path,
    credential_status: str,
    progress: _NDJSONProgress,
) -> Mapping[str, str]:
    from datetime import timedelta

    from .clock import SystemClock
    from .contracts import ProviderRequest
    from .providers.base import ProviderContext, stable_id
    from .providers.variflight import VariFlightAdapter
    from .providers.variflight_mcp import VariFlightMCPTransport

    progress.emit({"event": "probe", "provider": "variflight", "scope": "doctor", "status": "started"})
    transport = VariFlightMCPTransport(
        credentials,
        cache_dir=repo_root / ".npm-cache",
        temp_root=repo_root / ".tmp" / "doctor-variflight",
        cwd=repo_root,
    )
    _attach_progress(transport, progress)
    if credential_status == "missing":
        try:
            transport.probe(deadline_seconds=8.0)
        except Exception as exc:
            return _probe_exception_layers(credential_status, exc)
        return {
            "credential": credential_status,
            "contract": "passed",
            "network": "passed",
            "business": "not_run",
        }
    clock = SystemClock()
    travel_date = (clock.now().date() + timedelta(days=7)).isoformat()
    request = ProviderRequest(
        request_id=stable_id("doctor-variflight", travel_date),
        capability="flight",
        parameters={
            "action": "search", "dep_city": "PEK", "arr_city": "SHA",
            "date": travel_date, "from_ref": "doctor-pek", "to_ref": "doctor-sha",
            "candidate_mode": True,
        },
        deadline_ms=8000,
        as_of=travel_date,
        cache_policy="bypass",
        trace={"stage": "doctor"},
    )
    result = VariFlightAdapter().query(request, ProviderContext(clock, credentials, transport))
    return _probe_layers(credential_status, result)


def _probe_layers(credential_status: str, result: Any) -> Mapping[str, str]:
    error_class = result.error_class
    if error_class == "contract_mismatch":
        contract, network, business = "failed", "passed", "not_run"
    elif error_class in ("network", "timeout"):
        contract, network, business = "not_run", "failed", "not_run"
    else:
        contract, network = "passed", "passed"
        if error_class is None:
            business = "passed"
        elif error_class in ("no_results", "rate_limited", "upstream_5xx"):
            business = "degraded"
        else:
            business = "failed"
    return {
        "credential": credential_status,
        "contract": contract,
        "network": network,
        "business": business,
    }


def _probe_exception_layers(credential_status: str, exc: Exception) -> Mapping[str, str]:
    from .providers.base import ContractMismatch, ProviderNetworkError, ProviderTimeout

    if isinstance(exc, ContractMismatch):
        contract, network = "failed", "passed"
    elif isinstance(exc, (ProviderNetworkError, ProviderTimeout, OSError)):
        contract, network = "not_run", "failed"
    else:
        contract, network = "failed", "failed"
    return {
        "credential": credential_status,
        "contract": contract,
        "network": network,
        "business": "not_run",
    }


def _not_run_probe(credential_status: str) -> Mapping[str, str]:
    return {
        "credential": credential_status,
        "contract": "not_run",
        "network": "not_run",
        "business": "not_run",
    }


if __name__ == "__main__":
    raise SystemExit(main())
