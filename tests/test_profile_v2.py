"""Versioned profile, trusted script, visible facts, and bounded scenario tests."""

from __future__ import annotations

import base64
import copy
import hashlib
import html as html_lib
import json
import re
import unittest
from pathlib import Path
from unittest import mock

from china_trip_weaver.render import render_journey, render_trip, validate_html, validate_journey_html
from china_trip_weaver.render import RendererError
from china_trip_weaver.render import profile_html
from china_trip_weaver.render.profile_html import LABELS, _budget_summary, _duration
from china_trip_weaver.journey import journey_booking_checklist, journey_risk_items
from china_trip_weaver.render.profile_model import _scenario, build_model, clock, relative_minute
from china_trip_weaver.planning import _budget_ledger
from china_trip_weaver.validate_trip import validate_trip

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
            (self.trip, render_trip, 'demo/trip.html', '2dcd19fd0e3806fbccefafe6e615c9564a4d15c7bfda2f6f4acbdecd86b172e5'),
            (self.journey, render_journey, 'demo/journey-16d/journey.html', 'd4536f5fa634c1ee2e5ac24074c2e6bae995d83afe7cdf538e8b402e140f76d9'),
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

    def test_c03_four_locales_keep_body_navigation_footer_and_source_facts(self):
        cases = []
        for source, render, validate in ((self.trip, render_trip, validate_html),
                                         (self.journey, render_journey, validate_journey_html)):
            cases.append((source, render, validate))
            english = copy.deepcopy(source)
            if 'trips' in english:
                for segment in english['trips']:
                    segment['request']['locale'] = 'en'
            else:
                english['request']['locale'] = 'en'
            cases.append((english, render, validate))
        for source, render, validate in cases:
            with self.subTest(kind='journey' if 'trips' in source else 'trip', locale=source.get('request', {}).get('locale', 'en')):
                old = render(source, renderer_version='1')
                new = render(source, renderer_version='2')
                self.assertTrue(validate(new, source).ok)
                record = new.split('<details id="full-record">', 1)[1].split('</details></section>', 1)[0]
                self.assertNotIn('<header class="page-header"', record)
                self.assertNotIn('<aside class="truth-banner"', record)
                self.assertIn('<h2 id="truth-heading">', record)
                old_body = old.split('<main id="main-content">', 1)[1].split('</main>', 1)[0]
                new_body = new.split('<div id="full-main">', 1)[1].split('</div>\n<footer class="page-footer"', 1)[0]
                self.assertEqual(old_body, new_body)
                for tag, cls in (('nav', 'day-nav'), ('footer', 'page-footer')):
                    pattern = r'<%s class="%s".*?</%s>' % (tag, cls, tag)
                    self.assertEqual(re.search(pattern, old, re.S).group(0), re.search(pattern, new, re.S).group(0))
                summary = re.search(r'<section class="record-context".*?</section>', record, re.S).group(0)
                self.assertIn(str(source['revision']['number']), summary)
                self.assertIn(source['generated_at'][:16].replace('T', ' '), summary)
                if 'trips' in source:
                    self.assertIn(str(len(source['trips'])), summary)
                    self.assertIn(str(len(journey_booking_checklist(source))), summary)
                    self.assertIn(str(len(journey_risk_items(source))), summary)
                else:
                    self.assertIn(str(len(source['unknowns'])), summary)
                    self.assertIn(str(len(source['days'])), summary)
                    self.assertIn('飞常准' if source['request']['locale'] == 'zh-CN' else 'VariFlight', summary)
                    self.assertIn('未配置' if source['request']['locale'] == 'zh-CN' else 'Not configured', summary)

    def test_c03_mock_mixed_modes_attribution_and_grouped_party(self):
        synthetic = copy.deepcopy(self.trip)
        synthetic['mode'] = 'mock'
        synthetic['mock_notice'] = 'Synthetic <b>not live</b> inventory'
        rendered = render_trip(synthetic, renderer_version='2')
        self.assertTrue(validate_html(rendered, synthetic).ok)
        self.assertIn('data-mock-notice="true"', rendered)
        self.assertIn('Synthetic &lt;b&gt;not live&lt;/b&gt; inventory', rendered)
        self.assertNotIn('Synthetic <b>', rendered)
        self.assertFalse(validate_html(rendered.replace('Synthetic &lt;b&gt;not live&lt;/b&gt; inventory', 'live inventory', 1), synthetic).ok)

        mixed = copy.deepcopy(self.journey)
        mixed['trips'][0]['mode'] = 'mock'
        mixed['trips'][0]['mock_notice'] = 'Synthetic segment'
        mixed_html = render_journey(mixed, renderer_version='2')
        self.assertTrue(validate_journey_html(mixed_html, mixed).ok)
        summary = re.search(r'<section class="record-context".*?</section>', mixed_html, re.S).group(0)
        self.assertIn('演示数据 / 静态参考资料', summary)

        live = json.loads((ROOT / 'tests/fixtures/trips/schema/valid/weekend-live.json').read_text(encoding='utf-8'))
        live_html = render_trip(live, renderer_version='2')
        self.assertTrue(validate_html(live_html, live).ok)
        self.assertIn('data-attribution="1"', live_html)
        self.assertIn('地图与路线数据来源于高德地图', live_html)
        self.assertFalse(validate_html(live_html.replace('data-attribution="1"', 'data-attribution="0"', 1), live).ok)

        grouped = json.loads((ROOT / 'demo/grouped-departures/trip.json').read_text(encoding='utf-8'))
        self.assertNotIn('travelers', grouped['request'])
        grouped_html = render_trip(grouped, renderer_version='2')
        self.assertTrue(validate_html(grouped_html, grouped).ok)
        grouped_summary = re.search(r'<section class="record-context".*?</section>', grouped_html, re.S).group(0)
        self.assertIn('3 人', grouped_summary)

    def test_c03_forged_record_summary_or_navigation_target_is_rejected(self):
        for source, render, validate in ((self.trip, render_trip, validate_html),
                                         (self.journey, render_journey, validate_journey_html)):
            page = render(source, renderer_version='2')
            self.assertFalse(validate(page.replace('id="truth-heading"', 'id="removed-truth"', 1), source).ok)
            self.assertFalse(validate(page.replace('data-section="record-context"', 'data-section="removed"', 1), source).ok)
            anchor = re.search(r'<nav class="day-nav".*?href="#([^"]+)"', page, re.S).group(1)
            self.assertFalse(validate(page.replace('id="%s"' % anchor, 'id="removed-target"', 1), source).ok)

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
        self.assertEqual(list(range(16)), [int(value) for value in re.findall(r'data-day-support="(\d+)"', page)])
        self.assertIn('.focus-nav button,.try-action,.undo{display:none}', page)
        self.assertIn('class="noscript"', page)
        self.assertNotIn('data-day-detail="0" hidden', page)
        self.assertNotIn('data-day-support="0" hidden', page)

    def test_each_selected_day_has_a_programmatic_focus_target(self):
        for source, render in ((self.trip, render_trip), (self.journey, render_journey)):
            page = render(source, renderer_version='2')
            expected_days = len(source['days']) if 'days' in source else sum(len(trip['days']) for trip in source['trips'])
            headings = re.findall(r'<article class="day-detail"[^>]*>.*?<h3 tabindex="-1">([^<]+)</h3>', page, re.S)
            self.assertEqual(expected_days, len(headings))
            self.assertNotIn('tabindex="0"', page)
            self.assertIn('id="full-record"', page)

    def test_budget_state_distinguishes_missing_quotes_from_a_real_zero(self):
        pending = {'budget': {'status': 'incomplete', 'known': 0, 'minimum': None, 'maximum': None, 'comparable_count': 0}}
        self.assertEqual('总额待核验', _budget_summary(pending, LABELS['zh-CN'])[0])
        self.assertIn('已知部分 ¥0', _budget_summary(pending, LABELS['zh-CN'])[1])
        self.assertEqual('Total to verify', _budget_summary(pending, LABELS['en'])[0])
        partial = {'budget': {'status': 'incomplete', 'known': 4200, 'minimum': None, 'maximum': None, 'comparable_count': 2}}
        self.assertIn('¥4200', _budget_summary(partial, LABELS['zh-CN'])[1])
        empty_ledger, _ = _budget_ledger({'budget_cny': 0}, [], [], [], [], [])
        self.assertEqual('within_budget', empty_ledger['status'])
        complete_zero = {'budget': {'status': empty_ledger['status'], 'known': empty_ledger['known_cost_cny'],
                                    'minimum': empty_ledger['total_range_cny']['minimum'],
                                    'maximum': empty_ledger['total_range_cny']['maximum'], 'comparable_count': 0}}
        self.assertEqual('已知总额 ¥0', _budget_summary(complete_zero, LABELS['zh-CN'])[0])
        paid = copy.deepcopy(self.trip['pois'][0])
        paid['price'] = {'amount': 100, 'currency': 'CNY', 'price_type': 'reference', 'unit': 'total',
                         'includes_taxes': True, 'queried_at': '2026-09-04T00:00:00+08:00', 'claim_id': None}
        for limit, status in ((0, 'over_budget'), (150, 'within_budget'), (None, 'unbudgeted')):
            with self.subTest(limit=limit):
                request = dict(self.trip['request'], budget_cny=limit)
                ledger, _ = _budget_ledger(request, [{'slots': [{'ref_id': paid['poi_id']}]}], [], [], [paid], [])
                self.assertEqual(status, ledger['status'])
                shown = _budget_summary({'budget': {'status': status, 'known': ledger['known_cost_cny'],
                        'minimum': ledger['total_range_cny']['minimum'], 'maximum': ledger['total_range_cny']['maximum'],
                        'comparable_count': 1}}, LABELS['zh-CN'])
                self.assertEqual('已知总额 ¥100', shown[0])
        trip = render_trip(self.trip, renderer_version='2')
        before_record = trip.split('<section class="record">', 1)[0]
        self.assertIn('<strong>总额待核验</strong>', before_record)
        self.assertNotIn('<strong>¥0</strong>', before_record)
        journey = render_journey(self.journey, renderer_version='2')
        self.assertIn('已可比较 ¥4200', journey.split('<script id="prototype-model"', 1)[0])

    def test_legal_unbudgeted_and_zero_priced_partial_trip_do_not_invent_a_total(self):
        no_limit = copy.deepcopy(self.trip)
        no_limit['request']['budget_cny'] = None
        ledger, budget_unknowns = _budget_ledger(no_limit['request'], no_limit['days'], no_limit['transport_legs'],
                                                  no_limit['lodgings'], no_limit['pois'], no_limit['claims'])
        no_limit['budget_ledger'] = ledger
        no_limit['unknowns'] = [item for item in no_limit['unknowns'] if not item['field_path'].startswith('/budget_ledger/')] + budget_unknowns
        self.assertEqual('unbudgeted', ledger['status'])
        self.assertTrue(validate_trip(no_limit).ok)
        for locale, pending_label, false_label in (('zh-CN', '总额待核验', '已知总额 ¥0'),
                                                   ('en', 'Total to verify', 'Known total ¥0')):
            source = copy.deepcopy(no_limit)
            source['request']['locale'] = locale
            page = render_trip(source, renderer_version='2')
            self.assertTrue(validate_html(page, source).ok)
            self.assertIn('<strong>%s</strong>' % pending_label, page)
            self.assertNotIn('<strong>%s</strong>' % false_label, page)

        free = copy.deepcopy(self.trip)
        poi = free['pois'][0]
        price = {'amount': 0, 'currency': 'CNY', 'price_type': 'reference', 'unit': 'per_person',
                 'includes_taxes': True, 'queried_at': '2026-09-04T00:00:00+08:00', 'claim_id': 'claim-test-free-entry'}
        poi['price'] = price
        poi['claim_ids'].append('claim-test-free-entry')
        claim = copy.deepcopy(free['claims'][0])
        claim.update({'claim_id': 'claim-test-free-entry', 'subject_ref': poi['poi_id'], 'field_path': '/price',
                      'value': price, 'source_url': 'https://example.test/free-entry', 'provider': 'synthetic-review',
                      'queried_at': '2026-09-04T00:00:00+08:00', 'status': 'hypothesis', 'confidence': 0.5})
        free['claims'].append(claim)
        free_ledger, free_unknowns = _budget_ledger(free['request'], free['days'], free['transport_legs'],
                                                     free['lodgings'], free['pois'], free['claims'])
        free['budget_ledger'] = free_ledger
        free['unknowns'] = [item for item in free['unknowns'] if not item['field_path'].startswith('/budget_ledger/')] + free_unknowns
        self.assertTrue(validate_trip(free).ok)
        self.assertEqual(0, free_ledger['known_cost_cny'])
        self.assertEqual(1, build_model(free)['budget']['comparable_count'])
        free_page = render_trip(free, renderer_version='2')
        self.assertTrue(validate_html(free_page, free).ok)
        self.assertIn('已有 1 项零元可比报价', free_page)
        self.assertNotIn('尚无可比较报价', free_page)
        english_free = copy.deepcopy(free)
        english_free['request']['locale'] = 'en'
        english_free_page = render_trip(english_free, renderer_version='2')
        self.assertTrue(validate_html(english_free_page, english_free).ok)
        self.assertIn('1 comparable zero-priced item', english_free_page)
        self.assertNotIn('No comparable quote yet', english_free_page)

    def test_issues_are_summarized_but_every_raw_record_remains_readable(self):
        model = build_model(self.trip)
        issues = model['days'][0]['issues']
        rendered = render_trip(self.trip, renderer_version='2')
        panel = rendered.split('data-day-detail="0"', 1)[1].split('</article>', 1)[0]
        raw = rendered.split('data-day-support="0"', 1)[1].split('</article>', 1)[0]
        self.assertIn('出发前要核对', panel)
        self.assertIn('交通服务信息', panel)
        self.assertIn('href="#support-day-0"', panel)
        self.assertNotIn('no_results:leg-', panel)
        self.assertIn('<details class="issue-details">', raw)
        self.assertEqual(len(issues), raw.count('data-issue-id="'))
        for issue in issues:
            self.assertIn('data-issue-id="%s"' % issue['id'], raw)
            self.assertIn(issue['field_path'], raw)
            if issue['claim_id']:
                self.assertIn(issue['claim_id'], raw)
            self.assertIn(html_lib.escape(issue['reason'], quote=True), raw)
        self.assertIn('class="issue-source"', raw)
        self.assertTrue(validate_html(rendered, self.trip).ok)
        english = copy.deepcopy(self.trip)
        english['request']['locale'] = 'en'
        english_page = render_trip(english, renderer_version='2')
        english_panel = english_page.split('data-day-detail="0"', 1)[1].split('</article>', 1)[0]
        self.assertIn('Check before travel', english_panel)
        self.assertIn('View 11 source records', english_panel)

    def test_rail_and_ferry_service_unknowns_use_neutral_transport_language(self):
        rail = render_trip(self.trip, renderer_version='2')
        rail_panel = rail.split('data-day-detail="0"', 1)[1].split('</article>', 1)[0]
        self.assertIn('交通服务信息', rail_panel)
        ferry = json.loads((ROOT / 'tests/fixtures/trips/schema/valid/rental-ferry.json').read_text(encoding='utf-8'))
        ferry['unknowns'].append({'field_path': '/transport_legs/0/service_number',
                                  'reason': 'Synthetic ferry sailing identifier still unverified',
                                  'provider': 'gulangyu-ferry.example.invalid', 'claim_id': None})
        self.assertTrue(validate_trip(ferry).ok)
        for locale, topic in (('zh-CN', '交通服务信息'), ('en', 'Transport service details')):
            source = copy.deepcopy(ferry)
            source['request']['locale'] = locale
            page = render_trip(source, renderer_version='2')
            self.assertTrue(validate_html(page, source).ok)
            first_day = page.split('data-day-detail="0"', 1)[1].split('</article>', 1)[0]
            self.assertIn(topic, first_day)
            self.assertNotIn('车次与余票', first_day)
            self.assertNotIn('service and seats', first_day)
            support = page.split('data-day-support="0"', 1)[1].split('</article>', 1)[0]
            self.assertIn('Synthetic ferry sailing identifier still unverified', support)
            self.assertNotIn('车次', support)

    def test_static_issue_checklist_counts_match_original_record_groups(self):
        cases = (
            (self.trip, render_trip, ('交通服务信息', '住宿报价与条件', '交通费用与衔接'), (1, 1, 1), 8, 11),
            (self.journey, render_journey, ('交通服务信息', '交通费用与衔接', '预算缺价'), (1, 1, 3), 2, 7),
        )
        for source, render, labels, counts, remaining, total in cases:
            page = render(source, renderer_version='2')
            first_day = page.split('data-day-detail="0"', 1)[1].split('</article>', 1)[0]
            highlights = re.search(r'<ul class="issue-highlights">(.*?)</ul>', first_day, re.S).group(1)
            self.assertEqual(total, len(build_model(source)['days'][0]['issues']))
            self.assertEqual(3, highlights.count('<li>'))
            for label, count in zip(labels, counts):
                self.assertIn('<span>%s</span><small>%d 条</small>' % (label, count), highlights)
            self.assertEqual(total, sum(counts) + remaining)
            self.assertIn('其他主题还有 %d 条' % remaining, first_day)
            self.assertNotIn('<button', highlights)
            self.assertNotIn('<a ', highlights)
            self.assertEqual(1, first_day.count('class="issue-jump"'))

        english = copy.deepcopy(self.trip)
        english['request']['locale'] = 'en'
        page = render_trip(english, renderer_version='2')
        first_day = page.split('data-day-detail="0"', 1)[1].split('</article>', 1)[0]
        highlights = re.search(r'<ul class="issue-highlights">(.*?)</ul>', first_day, re.S).group(1)
        self.assertIn('<span>Transport service details</span><small>1 record</small>', highlights)
        self.assertIn('8 more records in other topics', first_day)
        self.assertIn('11 source records', first_day)

    def test_only_the_moving_slot_has_a_preview_replacement_clock(self):
        page = render_trip(self.trip, renderer_version='2')
        first_day = page.split('data-day-detail="0"', 1)[1].split('</article>', 1)[0]
        self.assertEqual(7, first_day.count('data-original-time="true"'))
        self.assertEqual(1, first_day.count('data-scenario-original="true"'))
        self.assertEqual(1, first_day.count('data-shifted-time="true"'))
        self.assertIn('data-scenario-original="true"', first_day.split('data-role="transport"', 1)[1].split('</li>', 1)[0])
        locked = copy.deepcopy(self.trip)
        locked['days'][0]['slots'][0]['locked'] = True
        locked['transport_legs'][0]['locked'] = True
        locked_page = render_trip(locked, renderer_version='2')
        locked_day = locked_page.split('data-day-detail="0"', 1)[1].split('</article>', 1)[0]
        self.assertNotIn('data-scenario-original="true"', locked_day)
        self.assertNotIn('data-shifted-time="true"', locked_day)

    def test_every_day_keeps_its_original_unknown_reasons_and_claim_ids(self):
        for source, render in ((self.trip, render_trip), (self.journey, render_journey)):
            model = build_model(source)
            page = render(source, renderer_version='2')
            for day in model['days']:
                support = page.split('data-day-support="%d"' % day['index'], 1)[1].split('</article>', 1)[0]
                self.assertEqual(len(day['issues']), support.count('data-issue-id="'))
                for issue in day['issues']:
                    self.assertIn('data-issue-id="%s"' % issue['id'], support)
                    self.assertIn(html_lib.escape(issue['reason'], quote=True), support)
                    if issue['claim_id']:
                        self.assertIn(issue['claim_id'], support)

    def test_duration_and_legend_use_human_units_for_every_bar_role(self):
        self.assertEqual('9小时30分钟', _duration(570, 'zh-CN'))
        self.assertEqual('9时30分', _duration(570, 'zh-CN', True))
        self.assertEqual('50分钟', _duration(50, 'zh-CN'))
        self.assertEqual('9h 30m', _duration(570, 'en'))
        page = render_journey(self.journey, renderer_version='2').split('<script id="prototype-model"', 1)[0]
        self.assertIn('9小时30分钟', page)
        self.assertIn('9时30分', page)
        self.assertNotIn('570m', page)
        for label in ('交通', '地点', '住宿', '用餐', '休息', '留白＝未安排', '斜纹＝静态/待证'):
            self.assertIn(label, page)

    def test_mobile_reading_order_places_one_decision_then_day_before_route_detail(self):
        trip = render_trip(self.trip, renderer_version='2')
        self.assertLess(trip.index('class="primary-decision"'), trip.index('id="focus-column"'))
        self.assertLess(trip.index('data-day-detail="0"'), trip.index('id="overview-title"'))
        self.assertLess(trip.index('id="overview-title"'), trip.index('id="support-day-0"'))
        self.assertIn('class="decision-details"', trip)
        self.assertIn('class="route-details"', trip)
        self.assertNotIn('<ol class="route"', trip.split('</section><noscript>', 1)[0])
        self.assertIn('data-route-size="short"', trip)
        self.assertIn('<main id="experience" data-route-size="short">', trip)
        journey = render_journey(self.journey, renderer_version='2')
        self.assertIn('data-route-size="long"', journey)
        self.assertIn('<main id="experience" data-route-size="long">', journey)

    def test_english_ui_is_not_chinese_only(self):
        trip = copy.deepcopy(self.trip)
        trip['request']['locale'] = 'en'
        page = render_trip(trip, renderer_version="2")
        self.assertTrue(validate_html(page, trip).ok)
        visible = page.split('<details id="full-record">', 1)[0]
        self.assertIn('lang="en"', page)
        self.assertIn('Whole-route time', visible)
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

    def test_skipped_and_locked_slots_keep_their_distinct_meaning(self):
        skipped = copy.deepcopy(self.trip)
        skipped['days'][0]['slots'][1]['status'] = 'skipped'
        skipped_model = build_model(skipped)
        self.assertEqual(0, skipped_model['days'][0]['scenario']['preview']['overlap_minutes'])
        skipped_page = render_trip(skipped, renderer_version='2')
        self.assertTrue(validate_html(skipped_page, skipped).ok)
        first_bar = skipped_page.split('data-select-day="0"', 1)[1].split('</a>', 1)[0]
        self.assertNotIn('title="午餐（地点待定）', first_bar)
        self.assertIn('未采用', skipped_page.split('data-day-detail="0"', 1)[1].split('</article>', 1)[0])

        locked = copy.deepcopy(self.trip)
        locked['days'][0]['slots'][0]['locked'] = True
        locked['transport_legs'][0]['locked'] = True
        locked_page = render_trip(locked, renderer_version='2')
        self.assertTrue(validate_html(locked_page, locked).ok)
        first_day = locked_page.split('data-day-detail="0"', 1)[1].split('</article>', 1)[0]
        self.assertIn('锁定', first_day)
        self.assertNotIn('data-try="true"', first_day)

    def test_conflicting_claims_are_flagged_before_raw_evidence(self):
        source = copy.deepcopy(self.trip)
        source['claims'][0]['status'] = 'conflict'
        model = build_model(source)
        urgent = sum(item['claim_status'] == 'conflict' for item in model['days'][0]['issues'])
        self.assertGreater(urgent, 0)
        page = render_trip(source, renderer_version='2')
        self.assertTrue(validate_html(page, source).ok)
        panel = page.split('data-day-detail="0"', 1)[1].split('</article>', 1)[0]
        self.assertIn('其中 %d 条来源冲突' % urgent, panel)
        self.assertNotIn(source['claims'][0]['claim_id'], panel)
        support = page.split('data-day-support="0"', 1)[1].split('</article>', 1)[0]
        self.assertIn(source['claims'][0]['claim_id'], support)

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
