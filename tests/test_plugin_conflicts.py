from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "china-trip-weaver"
sys.path.insert(0, str(PLUGIN / "src"))

from china_trip_weaver.plugin_conflicts import NOTICE, find_conflicts, skill_names


def listing(*entries):
    return {"installed": list(entries), "available": []}


def entry(plugin_id, path, enabled=True, installed=True):
    return {
        "pluginId": plugin_id,
        "name": plugin_id.split("@")[0],
        "enabled": enabled,
        "installed": installed,
        "source": {"source": "local", "path": str(path)},
    }


def make_plugin(root: Path, name: str, skills):
    for skill in skills:
        directory = root / name / "skills" / skill
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "SKILL.md").write_text("---\nname: %s\n---\n" % skill, encoding="utf-8")
    return root / name


class PluginConflictTests(unittest.TestCase):
    def test_skill_names_reads_this_plugin(self):
        names = skill_names(PLUGIN)
        self.assertIn("plan-china-trip", names)
        self.assertEqual(9, len(names))

    def test_no_conflict_when_this_plugin_is_alone(self):
        self.assertEqual({}, find_conflicts(listing(entry("china-trip-weaver@local", PLUGIN))))

    def test_conflict_is_reported_with_the_other_plugin_id(self):
        with TemporaryPluginRoot() as root:
            other = make_plugin(root, "china-travel-assistant", ["plan-china-trip", "search-china-trains"])
            found = find_conflicts(listing(
                entry("china-trip-weaver@local", PLUGIN),
                entry("china-travel-assistant@old", other),
            ))
            self.assertEqual({"plan-china-trip": ("china-travel-assistant@old",)}, found)

    def test_disabled_or_uninstalled_conflicting_plugin_is_ignored(self):
        with TemporaryPluginRoot() as root:
            other = make_plugin(root, "china-travel-assistant", ["plan-china-trip"])
            self.assertEqual({}, find_conflicts(listing(
                entry("china-trip-weaver@local", PLUGIN),
                entry("china-travel-assistant@old", other, enabled=False),
            )))
            self.assertEqual({}, find_conflicts(listing(
                entry("china-trip-weaver@local", PLUGIN),
                entry("china-travel-assistant@old", other, installed=False),
            )))

    def test_unrelated_plugin_sharing_no_skill_name_is_not_a_conflict(self):
        with TemporaryPluginRoot() as root:
            other = make_plugin(root, "some-other-plugin", ["write-a-poem"])
            self.assertEqual({}, find_conflicts(listing(
                entry("china-trip-weaver@local", PLUGIN),
                entry("some-other-plugin@x", other),
            )))

    def test_doctor_reports_conflict_status_and_keeps_credentials_opaque(self):
        result = subprocess.run(
            [str(PLUGIN / "scripts" / "ctw"), "doctor"],
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent-ctw-home", "CODEX_BIN": "/nonexistent-ctw-codex"},
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual("unknown", report["skill_conflicts"]["status"])
        self.assertEqual({}, report["skill_conflicts"]["conflicts"])
        self.assertNotIn("notice", report["skill_conflicts"])

    def test_notice_names_no_specific_plugin_and_stops_provider_calls(self):
        self.assertIn("不会合并同名 Skill", NOTICE)
        self.assertIn("未运行任何行程查询", NOTICE)


class TemporaryPluginRoot:
    def __enter__(self):
        import tempfile

        self._temporary = tempfile.TemporaryDirectory(dir=ROOT / ".tmp")
        return Path(self._temporary.name)

    def __exit__(self, *exc):
        self._temporary.cleanup()
        return False


if __name__ == "__main__":
    unittest.main()
