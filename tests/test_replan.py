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
from china_trip_weaver.render import validate_html
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
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            output = Path(temporary)
            fixture_paths = sorted(FIXTURES.glob("*.json"))
            self.assertEqual(4, len(fixture_paths))
            for path in fixture_paths:
                with self.subTest(path=path.name):
                    fixture = load(path)
                    base = load(ROOT / fixture["base_fixture"])
                    json_path = output / (path.stem + ".json")
                    html_path = output / (path.stem + ".html")
                    command = subprocess.run(
                        [
                            str(CTW), "replan",
                            "--trip", str(ROOT / fixture["base_fixture"]),
                            "--event", str(path),
                            "--base-revision", str(base["revision"]["number"]),
                            "--output-json", str(json_path),
                            "--output-html", str(html_path),
                            "--fixed-clock", FIXED_NOW,
                        ],
                        text=True,
                        capture_output=True,
                    )
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
            "(closure, weather, delay, or user_delete) and subject_ref (the target slot's "
            "slot_id); delay also requires delta_minutes; closure and weather also require "
            'replacement_slot; example delay event: {"type": "delay", "subject_ref": '
            '"slot-2", "delta_minutes": 15}',
            normalized_help,
        )
        event = load(FIXTURES / "closure.json")["event"]
        event["kind"] = event.pop("type")
        command = run_invalid_cli_event(self, event)
        self.assertEqual(
            'REPLAN_FAILED event_type event type must use the field "type" with one of: '
            "closure, weather, delay, user_delete\n",
            command.stderr,
        )

    def test_cli_ref_id_field_reports_subject_slot_id_contract(self):
        event = load(FIXTURES / "closure.json")["event"]
        event["ref_id"] = event.pop("subject_ref")
        command = run_invalid_cli_event(self, event)
        self.assertEqual(
            "REPLAN_FAILED event_subject event subject_ref is required and must be the "
            "target slot's slot_id, not a poi or lodging ref_id\n",
            command.stderr,
        )

    def test_cli_minutes_field_reports_delta_minutes_contract(self):
        event = load(FIXTURES / "delay.json")["event"]
        event["minutes"] = event.pop("delta_minutes")
        command = run_invalid_cli_event(self, event)
        self.assertEqual(
            'REPLAN_FAILED delay_value delay requires a positive number in the "delta_minutes" '
            'field, not "minutes"\n',
            command.stderr,
        )


def _make_replan(path: Path):
    def test(self):
        run_replan_fixture(self, path)
    return test


for _path in sorted(FIXTURES.glob("*.json")):
    setattr(ReplanTests, "test_replan_" + _path.stem.replace("-", "_"), _make_replan(_path))


if __name__ == "__main__":
    unittest.main()
