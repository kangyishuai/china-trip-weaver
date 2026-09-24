"""Pure QA contract checks. These tests never call run_qa or start ChromePipe."""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import unittest
from pathlib import Path

from china_trip_weaver.render import render_journey, render_trip


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("qa_renderer_report", ROOT / "scripts/qa_renderer_browser.py")
QA = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(QA)


class QaRendererReportTests(unittest.TestCase):
    def test_exact_section_contract_tracks_actual_root_version_and_kind(self):
        trip = json.loads((ROOT / "demo/trip.json").read_text(encoding="utf-8"))
        journey = json.loads((ROOT / "demo/journey-16d/journey.json").read_text(encoding="utf-8"))
        for source, render, expected in ((trip, render_trip, (12, 11)),
                                         (journey, render_journey, (16, 15))):
            for version, count in zip(("1", "2"), expected):
                with self.subTest(version=version, count=count):
                    page = render(source, renderer_version=version)
                    self.assertEqual(count, QA.expected_section_count(page))
                    self.assertEqual(count, page.count('data-section="'))

        quoted = copy.deepcopy(trip)
        quoted["request"]["assumptions"].append('The literal data-renderer-version="2" is source text.')
        self.assertEqual(12, QA.expected_section_count(render_trip(quoted, renderer_version="1")))
        with self.assertRaises(ValueError):
            QA.expected_section_count('<html data-renderer-version="3"><nav data-section="day-nav"></nav></html>')

    def test_report_keeps_exact_sections_and_fails_a_small_visible_target(self):
        report = {
            "viewportWidth": 375, "horizontalOverflow": 0, "bodyFontPx": 16,
            "bodyLineHeightPx": 24, "visibleTargetCount": 4, "minTargetHeight": 24,
            "sectionCount": 11, "nonEmptySections": 11, "headingJumps": 0,
            "resourceRequests": [], "svgSemantics": True, "timeSemantics": True,
            "mainCount": 1, "h1Count": 1, "coreTextLength": 400,
        }
        self.assertEqual(["touch targets"], QA.validate_report(report, 375, [], 11))
        report["minTargetHeight"] = 44
        self.assertEqual([], QA.validate_report(report, 375, [], 11))
        self.assertIn("12 sections", QA.validate_report(report, 375, [], 12))
        report["visibleTargetCount"] = 0
        self.assertIn("touch targets", QA.validate_report(report, 375, [], 11))

    def test_operable_target_probe_excludes_hidden_links_and_includes_summary_button(self):
        script = r'''
const expression = __EXPRESSION__;
function target(height, options = {}) {
  return {
    disabled: !!options.disabled, hiddenAncestor: !!options.hidden,
    detail: options.detail || null, visibility: options.visibility || 'visible',
    getAttribute: () => null,
    closest(selector) {
      if (selector === '[hidden],[inert]') return this.hiddenAncestor ? {} : null;
      if (selector === 'details:not([open])') return this.detail;
      return null;
    },
    getClientRects() { return height ? [{width: 80, height}] : []; },
    getBoundingClientRect() { return {width: 80, height}; },
    parentElement: null,
  };
}
const summary = target(44);
summary.contains = element => element === summary;
const closed = {querySelector: () => summary, parentElement: null};
summary.detail = closed;
const visible = target(44);
const button = target(44);
const small = target(24);
const hiddenDay = target(44, {hidden: true});
const closedLink = target(44, {detail: closed});
const disabled = target(24, {disabled: true});
let targets = [visible, button, summary, small, hiddenDay, closedLink, disabled];
global.scrollTo = () => {};
global.innerWidth = 375;
global.innerHeight = 812;
global.performance = {getEntriesByType: () => []};
global.getComputedStyle = element => ({
  fontSize: '16px', lineHeight: '24px', overflowX: 'visible',
  visibility: element.visibility || 'visible',
});
global.document = {
  documentElement: {scrollWidth: 375, clientWidth: 375},
  body: {innerText: 'x'.repeat(400)},
  querySelectorAll(selector) {
    if (selector === 'a[href],button,summary') return targets;
    if (selector === '[data-section]') return [{textContent: 'content'}];
    if (selector === 'main' || selector === 'h1') return [{}];
    return [];
  },
};
const first = eval(expression);
targets = targets.filter(element => element !== small);
const second = eval(expression);
process.stdout.write(JSON.stringify([first, second]));
'''.replace("__EXPRESSION__", json.dumps(QA.AUDIT_EXPRESSION))
        result = subprocess.run(["node", "-e", script], text=True, capture_output=True, check=True)
        small_present, small_removed = json.loads(result.stdout)
        self.assertEqual((4, 24), (small_present["visibleTargetCount"], small_present["minTargetHeight"]))
        self.assertEqual((3, 44), (small_removed["visibleTargetCount"], small_removed["minTargetHeight"]))


if __name__ == "__main__":
    unittest.main()
