"""Versioned profile, trusted script, visible facts, and bounded scenario tests."""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import re
import unittest
from pathlib import Path
from unittest import mock

from china_trip_weaver.render import render_journey, render_trip, validate_html, validate_journey_html
from china_trip_weaver.render import RendererError
from china_trip_weaver.render import profile_html
from china_trip_weaver.render.profile_model import _scenario, build_model, clock, relative_minute

ROOT = Path(__file__).resolve().parents[1]


class ProfileV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trip = json.loads((ROOT / "demo/trip.json").read_text(encoding="utf-8"))
        cls.journey = json.loads((ROOT / "demo/journey-16d/journey.json").read_text(encoding="utf-8"))

    def test_v1_contract_remains_readable_and_v2_is_the_new_version(self):
        for source, render, validate in ((self.trip, render_trip, validate_html),
                                         (self.journey, render_journey, validate_journey_html)):
            legacy = render(source, renderer_version="1")
            self.assertEqual(legacy, render(source))
            self.assertTrue(validate(legacy, source).ok)
            page = render(source, renderer_version="2")
            self.assertTrue(validate(page, source).ok)
            self.assertEqual(page, render(copy.deepcopy(source), renderer_version="2"))
            self.assertIn('data-renderer-version="2"', page)
            self.assertIn('<details id="full-record">', page)
            self.assertEqual(page.count('data-select-day="'), len(build_model(source)["days"]))
            self.assertEqual(page.count('data-day-detail="'), len(build_model(source)["days"]))
            self.assertEqual(page.count('<main'), 1)
            self.assertEqual(page.count('<h1'), 1)

    def test_v1_visible_text_can_quote_v2_marker_without_changing_dispatch(self):
        source = copy.deepcopy(self.trip)
        source['request']['assumptions'].append('The literal data-renderer-version="2" is a note, not an HTML version.')
        legacy = render_trip(source, renderer_version='1')
        self.assertIn('data-renderer-version="2"', legacy)
        self.assertTrue(validate_html(legacy, source).ok)

    def test_visible_header_counts_come_from_raw_trip_and_journey_facts(self):
        trip_page = render_trip(self.trip, renderer_version='2')
        trip_expected = '%s — %s · %d 人 · %d 天' % (
            self.trip['request']['start_date'], self.trip['request']['end_date'],
            self.trip['request']['travelers'], len(self.trip['days']))
        self.assertEqual(trip_expected, re.search(r'<p class="hero-sub">([^<]+)</p>', trip_page).group(1))
        self.assertIn('V206', {item.code for item in validate_html(
            trip_page.replace(trip_expected, trip_expected.replace('3 天', '2 天'), 1), self.trip).errors})

        journey_page = render_journey(self.journey, renderer_version='2')
        journey_expected = '%s — %s · %d 人 · %d 天' % (
            self.journey['start_date'], self.journey['end_date'], self.journey['travelers'],
            sum(len(segment['days']) for segment in self.journey['trips']))
        self.assertEqual(journey_expected, re.search(r'<p class="hero-sub">([^<]+)</p>', journey_page).group(1))
        self.assertIn('V206', {item.code for item in validate_journey_html(
            journey_page.replace(journey_expected, journey_expected.replace('16 天', '2 天'), 1), self.journey).errors})

        one_day = json.loads((ROOT / 'demo/guangzhou-shenzhen/trip.json').read_text(encoding='utf-8'))
        one_day['request']['locale'] = 'en'
        english_page = render_trip(one_day, renderer_version='2')
        self.assertEqual('%s — %s · %d travelers · 1 day' % (
            one_day['request']['start_date'], one_day['request']['end_date'], one_day['request']['travelers']),
            re.search(r'<p class="hero-sub">([^<]+)</p>', english_page).group(1))
        self.assertTrue(validate_html(english_page, one_day).ok)

    def test_v2_asset_revision_is_frozen_and_drift_is_explicit(self):
        page = render_trip(self.trip, renderer_version='2')
        self.assertIn('name="ctw-profile-assets" content="%s"' % profile_html.PROFILE_ASSET_SHA256, page)
        css, script = profile_html.assets()
        with mock.patch.object(profile_html, 'assets', return_value=(css + '\n', script)):
            report = validate_html(page, self.trip)
            self.assertIn('V207', {item.code for item in report.errors})
            with self.assertRaisesRegex(RendererError, 'format upgrade'):
                render_trip(self.trip, renderer_version='2')
        self.assertIn('V207', {item.code for item in validate_html(
            page.replace('<meta name="ctw-profile-assets" content="%s">' % profile_html.PROFILE_ASSET_SHA256, '', 1), self.trip).errors})

    def test_v2_fixture_bytes_guard_template_and_legacy_record_changes(self):
        expected = (
            (self.trip, render_trip, 'demo/trip.html', 'ed65925717d4c52960207d0dae68e7decea90d09f10f95d975bfa444333c34d1'),
            (self.journey, render_journey, 'demo/journey-16d/journey.html', '58254a9f20e6db78217d273e1f68e4af6188a0731f2355b126291383ec467e5a'),
        )
        for source, render, path, digest in expected:
            with self.subTest(path=path):
                actual = render(source, renderer_version='2').encode('utf-8')
                self.assertEqual(digest, hashlib.sha256(actual).hexdigest())
                self.assertEqual(actual, (ROOT / path).read_bytes())

    def test_hidden_controls_have_state_specific_and_print_rules(self):
        css = (ROOT / 'plugins/china-trip-weaver/assets/profile.css').read_text(encoding='utf-8')
        self.assertIn('.focus-nav button,.try-action,.undo{display:none}', css)
        self.assertIn('.js-ready .try-action:not([hidden])', css)
        self.assertIn('.js-ready .try-action[hidden]', css)
        self.assertIn('.js-ready .try-action[hidden],.js-ready .undo[hidden]{display:none}', css)
        self.assertIn('.try-result[hidden]{display:none}', css)
        self.assertIn('@media print{html,body{background:white}', css)
        self.assertIn('.try,.try-action,.undo,.focus-nav{display:none!important}', css)

    def test_complete_record_keeps_existing_visible_capabilities(self):
        page = render_journey(self.journey, renderer_version="2")
        record = page.split('<details id="full-record">', 1)[1].split('</details></section>', 1)[0]
        for term in ('data-section="location-overview"', 'data-section="day-timeline"',
                     'data-section="budget-summary"', 'data-section="booking-checklist"',
                     'data-section="risk-register"', 'data-section="provider-health"'):
            self.assertIn(term, record)
        trip_page = render_trip(self.trip, renderer_version="2")
        trip_record = trip_page.split('<details id="full-record">', 1)[1].split('</details></section>', 1)[0]
        for term in ('data-section="transport-summary"', 'data-section="lodging-summary"',
                     'data-section="days"', 'data-section="location-overview"',
                     'data-section="evidence"', 'data-section="provider-health"'):
            self.assertIn(term, trip_record)

    def test_script_and_csp_cannot_be_replaced_together(self):
        page = render_trip(self.trip, renderer_version="2")
        start = page.index('<script>', page.index('id="source-document"')) + len('<script>')
        end = page.index('</script>', start)
        original = page[start:end]
        malicious = original + '\nwindow.injected = true;'
        old_hash = base64.b64encode(hashlib.sha256(original.encode()).digest()).decode()
        new_hash = base64.b64encode(hashlib.sha256(malicious.encode()).digest()).decode()
        changed = page[:start] + malicious + page[end:]
        changed = changed.replace(old_hash, new_hash)
        report = validate_html(changed, self.trip)
        self.assertFalse(report.ok)
        self.assertIn('V203', {issue.code for issue in report.errors})

    def test_visible_price_unknown_and_external_resources_are_bound(self):
        page = render_journey(self.journey, renderer_version="2")
        visible = page.split('<script id="prototype-model"', 1)[0]
        self.assertIn('参考价 ¥300 · 每晚', visible)
        self.assertNotIn('为reference', visible)
        self.assertFalse(validate_journey_html(page.replace('参考价 ¥300 · 每晚', '参考价 ¥3 · 每晚', 1), self.journey).ok)
        self.assertFalse(validate_journey_html(page.replace('</head>', '<script src="https://example.test/x.js"></script></head>', 1), self.journey).ok)
        self.assertFalse(validate_journey_html(page.replace('data-section="provider-health"', 'data-section="gone"', 1), self.journey).ok)
        self.assertFalse(validate_journey_html(page.replace('id="source-document"', 'id="changed-source"', 1), self.journey).ok)

    def test_no_script_has_all_days_and_no_dead_controls(self):
        page = render_journey(self.journey, renderer_version="2")
        self.assertEqual(16, page.count('data-day-detail="'))
        self.assertIn('.focus-nav button,.try-action,.undo{display:none}', page)
        self.assertIn('class="noscript"', page)
        self.assertNotIn('data-day-detail="0" hidden', page)

    def test_english_ui_is_not_chinese_only(self):
        trip = copy.deepcopy(self.trip)
        trip['request']['locale'] = 'en'
        page = render_trip(trip, renderer_version="2")
        self.assertTrue(validate_html(page, trip).ok)
        visible = page.split('<details id="full-record">', 1)[0]
        self.assertIn('lang="en"', page)
        self.assertIn('Time across the route', visible)
        self.assertIn('Show consequence', visible)
        self.assertIn('Complete itinerary and source record', page)
        self.assertNotIn('参考价', visible)
        journey = copy.deepcopy(self.journey)
        for segment in journey['trips']:
            segment['request']['locale'] = 'en'
        translated = render_journey(journey, renderer_version='2')
        self.assertTrue(validate_journey_html(translated, journey).ok)
        self.assertIn('lang="en"', translated)

    def test_weather_dining_and_optional_origin_remain_visible(self):
        weather = json.loads((ROOT / 'tests/fixtures/trips/schema/valid/weekend-live.json').read_text(encoding='utf-8'))
        page = render_trip(weather, renderer_version='2')
        self.assertTrue(validate_html(page, weather).ok)
        self.assertIn('data-weather-date="2026-10-16"', page)
        self.assertIn('出发地未提供', page)
        self.assertNotIn('¥None', page)
        dining = json.loads((ROOT / 'tests/fixtures/trips/schema/valid/dining-references.json').read_text(encoding='utf-8'))
        dining_page = render_trip(dining, renderer_version='2')
        self.assertTrue(validate_html(dining_page, dining).ok)
        self.assertIn('data-dining-slot=', dining_page)

    def test_scenario_status_intersection_and_baseline(self):
        source = copy.deepcopy(self.trip)
        day = source['days'][0]
        legs = {leg['leg_id']: leg for leg in source['transport_legs']}
        self.assertEqual(30, _scenario(day, legs)['preview']['overlap_minutes'])
        for status in ('skipped', 'tentative', 'unknown'):
            changed = copy.deepcopy(day)
            changed['slots'][1]['status'] = status
            self.assertEqual(0, _scenario(changed, legs)['preview']['overlap_minutes'])
        short = copy.deepcopy(day)
        short['slots'][1]['end_at'] = '2026-10-16T13:10:00+08:00'
        self.assertEqual(10, _scenario(short, legs)['preview']['overlap_minutes'])
        existing = copy.deepcopy(day)
        existing['slots'][1]['start_at'] = '2026-10-16T12:50:00+08:00'
        self.assertEqual(10, _scenario(existing, legs)['baseline']['overlap_minutes'])

    def test_scenario_excludes_disjoint_group_and_cross_date(self):
        day = {'slots': [
            {'slot_id': 'a', 'ref_id': 'a', 'kind': 'transport', 'status': 'scheduled', 'locked': False,
             'start_at': '2026-10-16T08:00:00+08:00', 'end_at': '2026-10-16T09:00:00+08:00', 'title': 'A'},
            {'slot_id': 'b', 'ref_id': 'b', 'kind': 'transport', 'status': 'scheduled', 'locked': False,
             'start_at': '2026-10-16T08:30:00+08:00', 'end_at': '2026-10-16T09:30:00+08:00', 'title': 'B'},
        ]}
        legs = {'a': {'group_refs': ['a'], 'locked': False, 'data_mode': 'static', 'service_number': None, 'price': {'amount': None}},
                'b': {'group_refs': ['b'], 'locked': False, 'data_mode': 'static', 'service_number': None, 'price': {'amount': None}}}
        self.assertEqual(0, _scenario(day, legs)['preview']['overlap_minutes'])
        crossing = copy.deepcopy(day)
        crossing['slots'][0]['end_at'] = '2026-10-17T00:20:00+08:00'
        self.assertFalse(_scenario(crossing, legs)['available'])
        self.assertEqual(1460, relative_minute(crossing['slots'][0]['end_at'], '2026-10-16'))
        self.assertEqual('+1d 00:20', clock(1460))
        live = copy.deepcopy(legs)
        live['a']['data_mode'] = 'live'
        self.assertFalse(_scenario({'slots': [day['slots'][0]]}, live)['available'])


if __name__ == '__main__':
    unittest.main()
