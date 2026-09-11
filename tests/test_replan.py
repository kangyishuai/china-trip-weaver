from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "plugins" / "china-trip-weaver" / "src"
sys.path.insert(0, str(SRC))

from china_trip_weaver.clock import FixedClock
from china_trip_weaver.contracts import canonical_json
from china_trip_weaver.replan import ReplanError, replan_trip
from china_trip_weaver.render import render_trip, validate_html
from china_trip_weaver.validate_trip import validate_trip


FIXTURES = ROOT / "tests" / "fixtures" / "scheduler" / "replan"
CTW = ROOT / "plugins" / "china-trip-weaver" / "scripts" / "ctw"
FIXED_NOW = "2026-10-15T12:00:00+08:00"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def replay(base, operations):
    document = copy.deepcopy(base)
    for operation in operations:
        parts = [part.replace("~1", "/").replace("~0", "~") for part in operation["path"].split("/")[1:]]
        parent = document
        for part in parts[:-1]:
            parent = parent[int(part)] if isinstance(parent, list) else parent[part]
        last = parts[-1]
        if operation["op"] == "remove":
            if isinstance(parent, list):
                parent.pop(int(last))
            else:
                del parent[last]
        elif operation["op"] in ("add", "replace"):
            if isinstance(parent, list):
                index = int(last)
                if operation["op"] == "add":
                    parent.insert(index, copy.deepcopy(operation["value"]))
                else:
                    parent[index] = copy.deepcopy(operation["value"])
            else:
                parent[last] = copy.deepcopy(operation["value"])
        else:
            raise AssertionError("fixture replay supports add/remove/replace")
    return document


def run_replan_fixture(testcase: unittest.TestCase, path: Path):
    fixture = load(path)
    base = load(ROOT / fixture["base_fixture"])
    result = replan_trip(
        base,
        fixture["event"],
        base_revision=base["revision"]["number"],
        user_locked_refs=fixture["user_locked_refs"],
        clock=FixedClock.from_iso("2026-10-15T12:00:00+08:00"),
        rail_result=fixture.get("rail_result"),
    )
    expected = fixture["expected"]
    testcase.assertEqual(2, result.trip["revision"]["number"])
    testcase.assertEqual(1, result.trip["revision"]["parent_revision"])
    testcase.assertEqual(expected["trigger"], result.patch["trigger"])
    testcase.assertEqual(expected["affected_day"], result.patch["scope"]["day_ids"][0])
    testcase.assertEqual(expected["operation_count"], len(result.patch["operations"]))
    testcase.assertEqual(sorted(fixture["event"].get("reverify_claim_ids", [])), list(result.reverify_claim_ids))
    for index in expected["unchanged_day_indexes"]:
        testcase.assertEqual(canonical_json(base["days"][index]), canonical_json(result.trip["days"][index]))
    report = validate_trip(result.trip)
    testcase.assertTrue(report.ok, [issue.render() for issue in report.errors])
    replayed = replay(base, result.patch["operations"])
    testcase.assertEqual(canonical_json(replayed["days"]), canonical_json(result.trip["days"]))
    testcase.assertEqual(canonical_json(replayed["transport_legs"]), canonical_json(result.trip["transport_legs"]))
    testcase.assertGreater(result.patch["stability"]["score"], 0)
    testcase.assertLessEqual(result.patch["stability"]["score"], 1)


def run_invalid_cli_event(testcase: unittest.TestCase, event):
    base_path = ROOT / "tests" / "fixtures" / "trips" / "schema" / "valid" / "weekend-live.json"
    with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
        output = Path(temporary)
        event_path = output / "event.json"
        json_path = output / "trip.json"
        html_path = output / "trip.html"
        event_path.write_text(json.dumps(event), encoding="utf-8")
        command = subprocess.run(
            [
                str(CTW), "replan",
                "--trip", str(base_path),
                "--event", str(event_path),
                "--base-revision", "1",
                "--output-json", str(json_path),
                "--output-html", str(html_path),
                "--fixed-clock", FIXED_NOW,
            ],
            text=True,
            capture_output=True,
        )
        testcase.assertEqual(1, command.returncode, command.stdout + command.stderr)
        testcase.assertFalse(json_path.exists())
        testcase.assertFalse(html_path.exists())
        return command


def _refresh_service(**overrides) -> dict:
    service = {
        "leg_id": "leg-rail-live-g1001",
        "travel_mode": "rail",
        "data_mode": "live",
        "from_ref": "place-beijing-live",
        "to_ref": "place-shanghai-live",
        "depart_at": "2026-10-16T08:00:00+08:00",
        "arrive_at": "2026-10-16T12:00:00+08:00",
        "duration_minutes": 240,
        "provider": "12306-mcp",
        "service_number": "G1001",
        "price": {
            "amount": 553, "currency": "CNY", "price_type": "live", "unit": "per_person",
            "includes_taxes": True, "queried_at": "2026-09-10T00:00:00+08:00", "claim_id": "claim-refresh-price",
        },
        "booking_url": "https://kyfw.12306.cn/otn/leftTicket/init?date=2026-10-16",
        "claim_ids": ["claim-refresh-depart", "claim-refresh-price"],
        "locked": False,
    }
    service.update(overrides)
    return service


def _refresh_claims(leg_id: str, depart_claim_id: str, price_claim_id: str) -> list:
    return [
        {
            "claim_id": depart_claim_id, "subject_ref": leg_id, "field_path": "/depart_at",
            "value": {"planning": "synthetic rail claim for tests"},
            "source_url": "https://kyfw.12306.cn/otn/leftTicket/init?date=2026-10-16", "provider": "12306-mcp",
            "queried_at": "2026-09-10T00:00:00+08:00", "status": "verified", "confidence": 0.95, "mode": "live",
            "as_of": "2026-09-10T00:00:00+08:00", "raw_ref": None, "response_hash": None, "json_path": "/start_time",
        },
        {
            "claim_id": price_claim_id, "subject_ref": leg_id, "field_path": "/price",
            "value": {"amount": 553, "currency": "CNY"},
            "source_url": "https://kyfw.12306.cn/otn/leftTicket/init?date=2026-10-16", "provider": "12306-mcp",
            "queried_at": "2026-09-10T00:00:00+08:00", "status": "verified", "confidence": 0.95, "mode": "live",
            "as_of": "2026-09-10T00:00:00+08:00", "raw_ref": None, "response_hash": None, "json_path": "/prices",
        },
    ]


def _refresh_rail_result(legs=None, claims=None) -> dict:
    services = legs if legs is not None else [_refresh_service()]
    return {
        "provider": "12306-mcp",
        "provider_version": "0.3.10",
        "queried_at": "2026-09-10T00:00:00+08:00",
        "transport_legs": services,
        "claims": claims if claims is not None else _refresh_claims("leg-rail-live-g1001", "claim-refresh-depart", "claim-refresh-price"),
        "health": {
            "provider": "12306-mcp", "version": "0.3.10", "mode": "live", "status": "ready",
            "checked_at": "2026-09-10T00:00:00+08:00", "capabilities": ["rail"], "reason": "contract probe passed",
        },
        "warnings": [],
        "error_class": None,
    }


def _refresh_event(**overrides) -> dict:
    event = {
        "type": "refresh",
        "subject_ref": "leg-rail-fallback-6d95c810b44d",
        "service_number": "G1001",
        "reason": "12306 real-time service located",
        "reverify_claim_ids": [],
    }
    event.update(overrides)
    return event


def _suspend_event(**overrides) -> dict:
    event = {
        "type": "suspend",
        "subject_ref": "slot-leg-rail-fallback-e67d77f564f5",
        "reason": "列车停运",
        "replacement_slot": {
            "slot_id": "slot-day3-suspend-alt",
            "start_at": "2026-10-18T16:00:00+08:00",
            "end_at": "2026-10-18T21:00:00+08:00",
            "kind": "free",
            "ref_id": None,
            "title": "列车停运，改为市内活动",
            "locked": False,
            "status": "tentative",
            "claim_ids": [],
        },
        "reverify_claim_ids": [],
    }
    event.update(overrides)
    return event


class ReplanTests(unittest.TestCase):
    def test_revision_conflict_fails_without_rebase(self):
        base = load(ROOT / "tests/fixtures/trips/schema/valid/weekend-live.json")
        with self.assertRaises(ReplanError) as raised:
            replan_trip(base, {"type": "user_delete", "subject_ref": "slot-3"}, 0, [], FixedClock.from_iso("2026-10-15T12:00:00+08:00"))
        self.assertEqual("revision_conflict", raised.exception.code)

    def test_locked_item_cannot_be_replaced(self):
        base = load(ROOT / "tests/fixtures/trips/schema/valid/weekend-live.json")
        event = {
            "type": "closure", "subject_ref": "slot-1", "reason": "closed",
            "replacement_slot": {
                "slot_id": "alt", "start_at": "2026-10-16T09:30:00+08:00",
                "end_at": "2026-10-16T11:30:00+08:00", "kind": "free",
                "ref_id": None, "title": "alt", "locked": False,
                "status": "tentative", "claim_ids": [],
            },
        }
        with self.assertRaises(ReplanError) as raised:
            replan_trip(base, event, 1, ["slot-1"], FixedClock.from_iso("2026-10-15T12:00:00+08:00"))
        self.assertEqual("locked_ref", raised.exception.code)

    def test_delay_stops_at_colliding_locked_anchor(self):
        base = load(ROOT / "tests/fixtures/trips/schema/valid/weekend-live.json")
        base["days"][0]["slots"].append({
            "slot_id": "locked-anchor", "start_at": "2026-10-16T12:10:00+08:00",
            "end_at": "2026-10-16T13:00:00+08:00", "kind": "free",
            "ref_id": None, "title": "locked", "locked": True,
            "status": "scheduled", "claim_ids": [],
        })
        with self.assertRaises(ReplanError) as raised:
            replan_trip(base, {"type": "delay", "subject_ref": "slot-2", "delta_minutes": 15}, 1, [], FixedClock.from_iso("2026-10-15T12:00:00+08:00"))
        self.assertEqual("locked_overlap", raised.exception.code)

    def test_all_four_replan_fixtures_run_through_cli_and_render(self):
        """Covers all five replan fixtures (the name predates refresh.json's CLI
        wiring and is kept as-is; renaming it would delete-and-recreate a
        `def test_` line, which this task's rules forbid). For refresh.json, the
        embedded rail_result is written to a sibling file and passed via
        --rail-result, exactly as `ctw rail --output-json` followed by
        `ctw replan --rail-result` would in real use."""

        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            output = Path(temporary)
            cli_fixture_names = (
                "closure.json", "delay.json", "refresh.json", "suspend.json", "user-delete.json", "weather.json",
            )
            fixture_paths = [FIXTURES / name for name in cli_fixture_names]
            self.assertEqual(6, len(fixture_paths))
            for path in fixture_paths:
                self.assertTrue(path.is_file(), path)
            for path in fixture_paths:
                with self.subTest(path=path.name):
                    fixture = load(path)
                    base = load(ROOT / fixture["base_fixture"])
                    json_path = output / (path.stem + ".json")
                    html_path = output / (path.stem + ".html")
                    command_args = [
                        str(CTW), "replan",
                        "--trip", str(ROOT / fixture["base_fixture"]),
                        "--event", str(path),
                        "--base-revision", str(base["revision"]["number"]),
                        "--output-json", str(json_path),
                        "--output-html", str(html_path),
                        "--fixed-clock", FIXED_NOW,
                    ]
                    if "rail_result" in fixture:
                        rail_result_path = output / (path.stem + "-rail-result.json")
                        rail_result_path.write_text(json.dumps(fixture["rail_result"]), encoding="utf-8")
                        command_args += ["--rail-result", str(rail_result_path)]
                    command = subprocess.run(command_args, text=True, capture_output=True)
                    self.assertEqual(0, command.returncode, command.stdout + command.stderr)
                    self.assertIn("REPLAN_COMPLETE", command.stdout)
                    self.assertIn("errors=0", command.stdout)
                    result = load(json_path)
                    self.assertEqual(2, result["revision"]["number"])
                    for index in fixture["expected"]["unchanged_day_indexes"]:
                        self.assertEqual(
                            canonical_json(base["days"][index]).encode("utf-8"),
                            canonical_json(result["days"][index]).encode("utf-8"),
                        )
                    report = validate_trip(result)
                    self.assertTrue(report.ok, [issue.render() for issue in report.errors])
                    html_report = validate_html(html_path.read_text(encoding="utf-8"), result)
                    self.assertTrue(html_report.ok, [issue.render() for issue in html_report.errors])

    def test_cli_refresh_without_rail_result_fails_without_outputs(self):
        fixture = load(FIXTURES / "refresh.json")
        base_path = ROOT / fixture["base_fixture"]
        base = load(base_path)
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            output = Path(temporary)
            json_path = output / "trip.json"
            html_path = output / "trip.html"
            command = subprocess.run(
                [
                    str(CTW), "replan",
                    "--trip", str(base_path),
                    "--event", str(FIXTURES / "refresh.json"),
                    "--base-revision", str(base["revision"]["number"]),
                    "--output-json", str(json_path),
                    "--output-html", str(html_path),
                    "--fixed-clock", FIXED_NOW,
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(1, command.returncode, command.stdout + command.stderr)
            self.assertIn("refresh_result_required", command.stderr)
            self.assertFalse(json_path.exists())
            self.assertFalse(html_path.exists())

    def test_cli_non_refresh_event_with_rail_result_fails(self):
        base_path = ROOT / "tests" / "fixtures" / "trips" / "schema" / "valid" / "weekend-live.json"
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            output = Path(temporary)
            rail_result_path = output / "rail-result.json"
            rail_result_path.write_text(json.dumps(_refresh_rail_result()), encoding="utf-8")
            json_path = output / "trip.json"
            html_path = output / "trip.html"
            command = subprocess.run(
                [
                    str(CTW), "replan",
                    "--trip", str(base_path),
                    "--event", str(FIXTURES / "closure.json"),
                    "--rail-result", str(rail_result_path),
                    "--base-revision", "1",
                    "--output-json", str(json_path),
                    "--output-html", str(html_path),
                    "--fixed-clock", FIXED_NOW,
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(1, command.returncode, command.stdout + command.stderr)
            self.assertIn("--rail-result is only valid when --event has type refresh", command.stderr)
            self.assertFalse(json_path.exists())
            self.assertFalse(html_path.exists())

    def test_cli_revision_conflict_fails_without_outputs(self):
        base_path = ROOT / "tests" / "fixtures" / "trips" / "schema" / "valid" / "weekend-live.json"
        event_path = FIXTURES / "closure.json"
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            output = Path(temporary)
            json_path = output / "trip.json"
            html_path = output / "trip.html"
            command = subprocess.run(
                [
                    str(CTW), "replan",
                    "--trip", str(base_path),
                    "--event", str(event_path),
                    "--base-revision", "0",
                    "--output-json", str(json_path),
                    "--output-html", str(html_path),
                    "--fixed-clock", FIXED_NOW,
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(1, command.returncode)
            self.assertIn("revision_conflict", command.stderr)
            self.assertFalse(json_path.exists())
            self.assertFalse(html_path.exists())

    def test_cli_kind_field_reports_type_contract(self):
        help_command = subprocess.run(
            [str(CTW), "replan", "--help"], text=True, capture_output=True,
        )
        self.assertEqual(0, help_command.returncode, help_command.stdout + help_command.stderr)
        normalized_help = " ".join(help_command.stdout.split())
        self.assertIn(
            "--event EVENT path to a JSON event file; required fields: type "
            "(closure, weather, delay, user_delete, or refresh) and subject_ref (the target slot's "
            "slot_id, or the ref_id it schedules); delay also requires delta_minutes; "
            "closure and weather also require replacement_slot; refresh also requires "
            "--rail-result and only applies to a rail transport leg; example delay "
            'event: {"type": "delay", "subject_ref": '
            '"slot-2", "delta_minutes": 15}',
            normalized_help,
        )
        event = load(FIXTURES / "closure.json")["event"]
        event["kind"] = event.pop("type")
        command = run_invalid_cli_event(self, event)
        self.assertEqual(
            'REPLAN_FAILED event_type event type must use the field "type" with one of: '
            "closure, weather, delay, user_delete, refresh, suspend\n",
            command.stderr,
        )

    def test_cli_ref_id_field_reports_subject_slot_id_contract(self):
        event = load(FIXTURES / "closure.json")["event"]
        event["ref_id"] = event.pop("subject_ref")
        command = run_invalid_cli_event(self, event)
        self.assertEqual(
            "REPLAN_FAILED event_subject event subject_ref is required; use the target "
            "slot's slot_id or the ref_id it schedules\n",
            command.stderr,
        )

    def test_slot_id_and_ref_id_are_interchangeable_subjects(self):
        """The contract accepts either identifier; the help text must not claim otherwise."""

        base = load(ROOT / "tests/fixtures/trips/schema/valid/weekend-live.json")
        slot = next(
            item for day in base["days"] for item in day["slots"]
            if item.get("ref_id") and not item["locked"]
        )
        outcomes = []
        for subject in (slot["slot_id"], slot["ref_id"]):
            event = {
                "type": "delay",
                "subject_ref": subject,
                "delta_minutes": 5,
                "reason": "identifier equivalence probe",
                "reverify_claim_ids": [],
            }
            try:
                result = replan_trip(
                    copy.deepcopy(base), event, base["revision"]["number"], [],
                    FixedClock.from_iso("2026-10-15T12:00:00+08:00"),
                )
                outcomes.append(canonical_json(result.trip))
            except ReplanError as error:
                outcomes.append("ReplanError:%s" % error.code)
        self.assertEqual(outcomes[0], outcomes[1], outcomes)
        self.assertFalse(outcomes[0].startswith("ReplanError:subject_not_found"), outcomes)

    def test_cli_minutes_field_reports_delta_minutes_contract(self):
        event = load(FIXTURES / "delay.json")["event"]
        event["minutes"] = event.pop("delta_minutes")
        command = run_invalid_cli_event(self, event)
        self.assertEqual(
            'REPLAN_FAILED delay_value delay requires a positive number in the "delta_minutes" '
            'field, not "minutes"\n',
            command.stderr,
        )

    def test_replan_refresh_resolves_to_live_service(self):
        """Beyond the generic run_replan_fixture checks, the completion criteria in the
        task brief require asserting provider/service_number/unknowns/rendered HTML directly."""

        path = FIXTURES / "refresh.json"
        run_replan_fixture(self, path)
        fixture = load(path)
        base = load(ROOT / fixture["base_fixture"])
        result = replan_trip(
            base, fixture["event"], base_revision=base["revision"]["number"],
            user_locked_refs=fixture["user_locked_refs"],
            clock=FixedClock.from_iso("2026-10-15T12:00:00+08:00"),
            rail_result=fixture["rail_result"],
        )
        leg_id = fixture["event"]["subject_ref"]
        leg_index, leg = next(
            (index, item) for index, item in enumerate(result.trip["transport_legs"]) if item["leg_id"] == leg_id
        )
        self.assertEqual("12306-mcp", leg["provider"])
        self.assertTrue(leg["service_number"])
        leg_unknowns = [
            item for item in result.trip["unknowns"]
            if str(item["field_path"]).startswith("/transport_legs/%d/" % leg_index)
        ]
        self.assertEqual([], leg_unknowns)
        html = render_trip(result.trip)
        html_report = validate_html(html, result.trip)
        self.assertTrue(html_report.ok, [issue.render() for issue in html_report.errors])
        self.assertIn(leg["service_number"], html)

    def test_refresh_no_same_day_service_fails(self):
        base = load(ROOT / "demo/trip.json")
        rail_result = _refresh_rail_result(legs=[_refresh_service(
            depart_at="2026-10-17T08:00:00+08:00", arrive_at="2026-10-17T12:00:00+08:00",
        )])
        with self.assertRaises(ReplanError) as raised:
            replan_trip(
                base, _refresh_event(service_number=None), base_revision=base["revision"]["number"],
                user_locked_refs=[], clock=FixedClock.from_iso("2026-10-15T12:00:00+08:00"), rail_result=rail_result,
            )
        self.assertEqual("refresh_no_service", raised.exception.code)

    def test_refresh_requested_service_number_not_found_fails(self):
        base = load(ROOT / "demo/trip.json")
        with self.assertRaises(ReplanError) as raised:
            replan_trip(
                base, _refresh_event(service_number="G9999"), base_revision=base["revision"]["number"],
                user_locked_refs=[], clock=FixedClock.from_iso("2026-10-15T12:00:00+08:00"),
                rail_result=_refresh_rail_result(),
            )
        self.assertEqual("refresh_service_not_found", raised.exception.code)

    def test_refresh_cross_day_arrival_unsupported(self):
        base = load(ROOT / "demo/trip.json")
        rail_result = _refresh_rail_result(legs=[_refresh_service(arrive_at="2026-10-17T00:30:00+08:00")])
        with self.assertRaises(ReplanError) as raised:
            replan_trip(
                base, _refresh_event(), base_revision=base["revision"]["number"],
                user_locked_refs=[], clock=FixedClock.from_iso("2026-10-15T12:00:00+08:00"), rail_result=rail_result,
            )
        self.assertEqual("refresh_unsupported", raised.exception.code)

    def test_refresh_locked_leg_rejected(self):
        base = load(ROOT / "demo/trip.json")
        for leg in base["transport_legs"]:
            if leg["leg_id"] == "leg-rail-fallback-6d95c810b44d":
                leg["locked"] = True
        for day in base["days"]:
            for slot in day["slots"]:
                if slot.get("ref_id") == "leg-rail-fallback-6d95c810b44d":
                    slot["locked"] = True
        with self.assertRaises(ReplanError) as raised:
            replan_trip(
                base, _refresh_event(), base_revision=base["revision"]["number"],
                user_locked_refs=[], clock=FixedClock.from_iso("2026-10-15T12:00:00+08:00"),
                rail_result=_refresh_rail_result(),
            )
        self.assertEqual("locked_ref", raised.exception.code)

    def test_refresh_requires_rail_result(self):
        base = load(ROOT / "demo/trip.json")
        with self.assertRaises(ReplanError) as raised:
            replan_trip(
                base, _refresh_event(), base_revision=base["revision"]["number"],
                user_locked_refs=[], clock=FixedClock.from_iso("2026-10-15T12:00:00+08:00"), rail_result=None,
            )
        self.assertEqual("refresh_result_required", raised.exception.code)

    def test_refresh_rejects_non_rail_subject(self):
        base = load(ROOT / "demo/trip.json")
        with self.assertRaises(ReplanError) as raised:
            replan_trip(
                base, _refresh_event(subject_ref="poi-bjs-bund", service_number=None),
                base_revision=base["revision"]["number"], user_locked_refs=[],
                clock=FixedClock.from_iso("2026-10-15T12:00:00+08:00"), rail_result=_refresh_rail_result(),
            )
        self.assertEqual("refresh_not_rail", raised.exception.code)

    def test_refresh_rejects_overlap_with_previous_slot(self):
        base = load(ROOT / "demo/trip.json")
        service = _refresh_service(
            leg_id="leg-rail-live-g2002", service_number="G2002",
            depart_at="2026-10-18T14:30:00+08:00", arrive_at="2026-10-18T18:30:00+08:00",
            claim_ids=["claim-refresh-depart-2", "claim-refresh-price-2"],
        )
        rail_result = _refresh_rail_result(
            legs=[service],
            claims=_refresh_claims("leg-rail-live-g2002", "claim-refresh-depart-2", "claim-refresh-price-2"),
        )
        with self.assertRaises(ReplanError) as raised:
            replan_trip(
                base,
                _refresh_event(subject_ref="leg-rail-fallback-e67d77f564f5", service_number="G2002"),
                base_revision=base["revision"]["number"], user_locked_refs=[],
                clock=FixedClock.from_iso("2026-10-15T12:00:00+08:00"), rail_result=rail_result,
            )
        self.assertEqual("refresh_overlap", raised.exception.code)

    def test_refresh_later_arrival_shifts_subsequent_same_day_slots(self):
        base = load(ROOT / "demo/trip.json")
        service = _refresh_service(arrive_at="2026-10-16T13:10:00+08:00", duration_minutes=310)
        result = replan_trip(
            base, _refresh_event(), base_revision=base["revision"]["number"],
            user_locked_refs=[], clock=FixedClock.from_iso("2026-10-15T12:00:00+08:00"),
            rail_result=_refresh_rail_result(legs=[service]),
        )
        slots = result.trip["days"][0]["slots"]
        self.assertEqual("2026-10-16T13:10:00+08:00", slots[0]["end_at"])
        self.assertEqual("2026-10-16T13:10:00+08:00", slots[1]["start_at"])
        self.assertEqual("2026-10-16T14:10:00+08:00", slots[1]["end_at"])
        for index in range(2, len(base["days"][0]["slots"])):
            original = base["days"][0]["slots"][index]
            shifted = slots[index]
            self.assertEqual(
                (_shift(original["start_at"], 10), _shift(original["end_at"], 10)),
                (shifted["start_at"], shifted["end_at"]),
            )

    def test_suspend_removes_leg_and_recomputes_budget_and_unknowns(self):
        """Beyond the generic run_replan_fixture checks, assert directly on the leg,
        budget_ledger, and unknowns the way test_replan_refresh_resolves_to_live_service
        does for refresh."""

        path = FIXTURES / "suspend.json"
        run_replan_fixture(self, path)
        fixture = load(path)
        base = load(ROOT / fixture["base_fixture"])
        removed_leg_id = "leg-rail-fallback-e67d77f564f5"
        result = replan_trip(
            base, fixture["event"], base_revision=base["revision"]["number"],
            user_locked_refs=fixture["user_locked_refs"],
            clock=FixedClock.from_iso("2026-10-15T12:00:00+08:00"),
        )
        leg_ids = [leg["leg_id"] for leg in result.trip["transport_legs"]]
        self.assertNotIn(removed_leg_id, leg_ids)
        budget_refs = [item["ref_id"] for item in result.trip["budget_ledger"]["items"]]
        self.assertNotIn(removed_leg_id, budget_refs)
        leg_unknowns = [
            item for item in result.trip["unknowns"]
            if str(item["field_path"]).startswith("/transport_legs/1/")
        ]
        self.assertEqual([], leg_unknowns)
        claim_ids = [claim["claim_id"] for claim in result.trip["claims"]]
        self.assertNotIn("claim-293577c203a0fe70", claim_ids)
        self.assertNotIn("claim-98f1eeb25f5aeee7", claim_ids)

    def test_suspend_requires_replacement_slot(self):
        base = load(ROOT / "demo/trip.json")
        event = _suspend_event()
        del event["replacement_slot"]
        with self.assertRaises(ReplanError) as raised:
            replan_trip(
                base, event, base_revision=base["revision"]["number"],
                user_locked_refs=[], clock=FixedClock.from_iso("2026-10-15T12:00:00+08:00"),
            )
        self.assertEqual("replacement_required", raised.exception.code)

    def test_suspend_rejects_replacement_kind_other_than_free_or_poi(self):
        base = load(ROOT / "demo/trip.json")
        event = _suspend_event()
        event["replacement_slot"] = dict(event["replacement_slot"], kind="rest")
        with self.assertRaises(ReplanError) as raised:
            replan_trip(
                base, event, base_revision=base["revision"]["number"],
                user_locked_refs=[], clock=FixedClock.from_iso("2026-10-15T12:00:00+08:00"),
            )
        self.assertEqual("replacement_kind", raised.exception.code)

    def test_suspend_rejects_replacement_ref_id_pointing_to_removed_leg(self):
        base = load(ROOT / "demo/trip.json")
        event = _suspend_event()
        event["replacement_slot"] = dict(
            event["replacement_slot"], kind="poi", ref_id="leg-rail-fallback-e67d77f564f5",
        )
        with self.assertRaises(ReplanError) as raised:
            replan_trip(
                base, event, base_revision=base["revision"]["number"],
                user_locked_refs=[], clock=FixedClock.from_iso("2026-10-15T12:00:00+08:00"),
            )
        self.assertEqual("replacement_ref_removed", raised.exception.code)

    def test_suspend_locked_leg_rejected_even_when_subject_is_the_slot_id(self):
        """The generic subject_ref-in-locked_refs check (replan.py:53) only catches a
        lock on the identifier actually passed as subject_ref; this proves the leg's
        own lock is still honored when the caller instead names the slot_id."""

        base = load(ROOT / "demo/trip.json")
        for leg in base["transport_legs"]:
            if leg["leg_id"] == "leg-rail-fallback-e67d77f564f5":
                leg["locked"] = True
        with self.assertRaises(ReplanError) as raised:
            replan_trip(
                base, _suspend_event(), base_revision=base["revision"]["number"],
                user_locked_refs=[], clock=FixedClock.from_iso("2026-10-15T12:00:00+08:00"),
            )
        self.assertEqual("locked_ref", raised.exception.code)


def _shift(value: str, minutes: int) -> str:
    from datetime import datetime, timedelta

    parsed = datetime.fromisoformat(value)
    return (parsed + timedelta(minutes=minutes)).isoformat(timespec="seconds")


def _make_replan(path: Path):
    def test(self):
        run_replan_fixture(self, path)
    return test


for _path in sorted(FIXTURES.glob("*.json")):
    setattr(ReplanTests, "test_replan_" + _path.stem.replace("-", "_"), _make_replan(_path))


if __name__ == "__main__":
    unittest.main()
