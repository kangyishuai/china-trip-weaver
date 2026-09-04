from __future__ import annotations

import copy
import hashlib
import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "china-trip-weaver"
SRC = PLUGIN / "src"
sys.path.insert(0, str(SRC))

from china_trip_weaver.contracts import canonical_json
from china_trip_weaver.credentials import SUPPORTED_KEY_NAMES
from china_trip_weaver.render import RendererError, render_trip, safe_output_name, validate_html
from china_trip_weaver.validate_trip import validate_trip


VALID = ROOT / "tests" / "fixtures" / "trips" / "schema" / "valid"
FIXTURES = ROOT / "tests" / "fixtures" / "renderer"
TRIP_MUTATIONS = FIXTURES / "trip"
HTML_MUTATIONS = FIXTURES / "html"
CTW = PLUGIN / "scripts" / "ctw"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def set_pointer(document, pointer, value):
    parts = [part.replace("~1", "/").replace("~0", "~") for part in pointer.split("/")[1:]]
    parent = document
    for part in parts[:-1]:
        parent = parent[int(part)] if isinstance(parent, list) else parent[part]
    last = parts[-1]
    if isinstance(parent, list):
        parent[int(last)] = value
    else:
        parent[last] = value


def mutate_trip(fixture):
    trip = load(ROOT / fixture["base_fixture"])
    for mutation in fixture["mutations"]:
        value = "".join(mutation["value_parts"]) if "value_parts" in mutation else mutation.get("value")
        set_pointer(trip, mutation["path"], value)
    return trip


def run_trip_mutation(testcase: unittest.TestCase, path: Path):
    fixture = load(path)
    trip = mutate_trip(fixture)
    trip_report = validate_trip(trip)
    expected = fixture["expected"]
    if expected["outcome"] == "reject-trip":
        testcase.assertFalse(trip_report.ok)
        codes = {item.code for item in trip_report.errors}
        testcase.assertTrue(set(expected["codes"]).issubset(codes), (expected["codes"], codes))
        with testcase.assertRaises(RendererError):
            render_trip(trip)
        return
    testcase.assertTrue(trip_report.ok, [item.render() for item in trip_report.errors])
    rendered = render_trip(trip)
    html_report = validate_html(rendered, trip)
    testcase.assertTrue(html_report.ok, [item.render() for item in html_report.errors])
    testcase.assertNotIn("</script><script>", rendered)


def run_html_mutation(testcase: unittest.TestCase, path: Path):
    fixture = load(path)
    trip = load(ROOT / fixture["base_fixture"])
    rendered = render_trip(trip)
    replacement = fixture["replace"]
    testcase.assertIn(replacement["old"], rendered)
    new_value = "".join(replacement["new_parts"]) if "new_parts" in replacement else replacement["new"]
    mutated = rendered.replace(replacement["old"], new_value, replacement["count"])
    report = validate_html(mutated, trip)
    testcase.assertFalse(report.ok)
    codes = {item.code for item in report.errors}
    testcase.assertTrue(set(fixture["expected"]["codes"]).issubset(codes), (fixture["expected"]["codes"], codes))


def contrast(foreground: str, background: str) -> float:
    def luminance(color: str) -> float:
        values = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        channels = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in values]
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]
    left, right = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (left + 0.05) / (right + 0.05)


class RendererTests(unittest.TestCase):
    def test_valid_examples_render_deterministically_with_zero_errors(self):
        for path in sorted(VALID.glob("*.json")):
            with self.subTest(path=path.name):
                trip = load(path)
                first = render_trip(trip)
                second = render_trip(copy.deepcopy(trip))
                self.assertEqual(first.encode("utf-8"), second.encode("utf-8"))
                self.assertEqual(hashlib.sha256(first.encode()).hexdigest(), hashlib.sha256(second.encode()).hexdigest())
                report = validate_html(first, trip)
                self.assertTrue(report.ok, [item.render() for item in report.errors])

    def test_output_name_is_safe_and_deterministic(self):
        self.assertEqual("shanghai-weekend-20261016.html", safe_output_name("shanghai-weekend-20261016"))
        self.assertEqual("unsafe-trip.html", safe_output_name("../Unsafe Trip"))

    def test_css_color_pairs_meet_normal_text_contrast(self):
        pairs = (("#1f2927", "#f7f3eb"), ("#53615d", "#fffdf8"), ("#ffffff", "#8b3022"), ("#1f5b4f", "#fffdf8"))
        for foreground, background in pairs:
            self.assertGreaterEqual(contrast(foreground, background), 4.5, (foreground, background))

    def test_cli_render_and_validate_html(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            output = Path(temporary) / "trip.html"
            trip = VALID / "weekend-live.json"
            rendered = subprocess.run([str(CTW), "render", str(trip), "--output", str(output)], text=True, capture_output=True)
            checked = subprocess.run([str(CTW), "validate-html", str(output), str(trip)], text=True, capture_output=True)
            self.assertEqual(0, rendered.returncode, rendered.stderr)
            self.assertIn("errors=0", rendered.stdout)
            self.assertEqual(0, checked.returncode, checked.stderr)
            self.assertIn("errors=0", checked.stdout)

    def test_renderer_fixture_manifest(self):
        manifest = load(FIXTURES / "manifest.json")
        self.assertEqual({"trip": 9, "html": 11}, manifest["counts"])
        for entry in manifest["files"]:
            data = (FIXTURES / entry["path"]).read_bytes()
            self.assertEqual(entry["sha256"], hashlib.sha256(data).hexdigest(), entry["path"])

    def test_network_blocked_browser_viewports_and_print(self):
        trip = load(VALID / "weekend-live.json")
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            folder = Path(temporary)
            html_path = folder / "trip-source.html"
            html_path.write_text(render_trip(trip), encoding="utf-8")
            output = folder / "qa"
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "qa_renderer_browser.py"), str(html_path), "--output", str(output)],
                text=True,
                capture_output=True,
                timeout=120,
            )
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            report = load(output / "qa-report.json")
            self.assertEqual([], report["failures"])
            self.assertEqual(4, len(report["viewports"]))
            self.assertEqual(2, len(report["screenshots"]))
            self.assertTrue((output / "renderer-print.pdf").is_file())

    def test_e104_rejects_assignment_for_every_supported_key_name(self):
        trip = load(VALID / "weekend-live.json")
        rendered = render_trip(trip)
        for name in SUPPORTED_KEY_NAMES:
            with self.subTest(name=name):
                injected = rendered.replace("</footer>", "<p>%s = ctw-render-canary</p></footer>" % name, 1)
                codes = {item.code for item in validate_html(injected, trip).errors}
                self.assertIn("E104", codes)


def _make_trip_test(path: Path):
    def test(self):
        run_trip_mutation(self, path)
    return test


def _make_html_test(path: Path):
    def test(self):
        run_html_mutation(self, path)
    return test


for _path in sorted(TRIP_MUTATIONS.glob("*.json")):
    setattr(RendererTests, "test_trip_adversarial_" + _path.stem.replace("-", "_"), _make_trip_test(_path))
for _path in sorted(HTML_MUTATIONS.glob("*.json")):
    setattr(RendererTests, "test_html_adversarial_" + _path.stem.replace("-", "_"), _make_html_test(_path))


if __name__ == "__main__":
    unittest.main()
