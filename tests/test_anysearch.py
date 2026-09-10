"""Contract tests for the AnySearch MCP transport and adapter."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.parse
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "plugins" / "china-trip-weaver" / "src"
CTW = ROOT / "plugins" / "china-trip-weaver" / "scripts" / "ctw"
sys.path.insert(0, str(SRC))

from china_trip_weaver.clock import FixedClock
from china_trip_weaver.contracts import ProviderRequest
from china_trip_weaver.credentials import resolve_credentials
from china_trip_weaver.providers.anysearch import AnySearchAdapter
from china_trip_weaver.providers.anysearch_http import ANYSEARCH_ENDPOINT, AnySearchHTTPTransport
from china_trip_weaver.providers.base import (
    ContractMismatch,
    ProviderContext,
    ProviderNetworkError,
    ProviderTimeout,
    ReplayTransport,
)


FIXTURES = ROOT / "tests" / "fixtures" / "providers" / "anysearch"


def load(path: Path) -> Mapping[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_fixture(case: str) -> Mapping[str, Any]:
    return load(FIXTURES / (case + ".json"))


def credentials(configured: bool = True):
    environment = {"ANYSEARCH_API_KEY": "ctw-canary-anysearch-not-real"} if configured else {}
    return resolve_credentials(environment, ROOT / ".tmp" / "anysearch-test-no-file")


def request(parameters: Mapping[str, Any], deadline_ms: int = 10000) -> ProviderRequest:
    return ProviderRequest(
        request_id="anysearch-test",
        capability="research",
        parameters=parameters,
        deadline_ms=deadline_ms,
        as_of="2026-10-16",
        cache_policy="bypass",
        trace={"stage": "test"},
    )


def run_fixture_result(case: str):
    fixture = load_fixture(case)
    environment = {"ANYSEARCH_API_KEY": "ctw-canary-anysearch-not-real"} if fixture["credential_state"] == "configured" else {}
    transport = ReplayTransport(fixture["transport"])
    result = AnySearchAdapter().query(
        ProviderRequest(**fixture["request"]),
        ProviderContext(
            clock=FixedClock.from_iso(fixture["captured_at"]),
            credentials=resolve_credentials(environment, ROOT / ".tmp" / "anysearch-test-no-file"),
            transport=transport,
        ),
    )
    return result, transport


class FakeResponse:
    def __init__(self, body: bytes, url: str, status: int = 200, headers: Mapping[str, str] = None) -> None:
        self._body = body
        self._url = url
        self.status = status
        self.headers = dict(headers or {"Content-Type": "application/json"})

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        del exc_type, exc, traceback

    def read(self, amount: int) -> bytes:
        return self._body[:amount]

    def geturl(self) -> str:
        return self._url

    def getcode(self) -> int:
        return self.status


def json_response(body: Any, url: str = ANYSEARCH_ENDPOINT, status: int = 200) -> FakeResponse:
    return FakeResponse(json.dumps(body).encode("utf-8"), url, status)


class RecordingOpener:
    def __init__(self, response: FakeResponse = None) -> None:
        self.requests = []
        self._response = response

    def __call__(self, http_request, timeout):
        self.requests.append((http_request, timeout))
        if self._response is not None:
            return self._response
        return json_response(_success_body())


def _success_body() -> Mapping[str, Any]:
    text = "## Search Results (1 results, 12ms)\n\n### 1. 上海博物馆开放信息\n- **URL**: https://www.shanghai.gov.cn/museum\n- official result\n"
    return {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": text}]}}


class AnySearchHTTPTransportTests(unittest.TestCase):
    def test_execute_posts_json_rpc_body_with_bearer_header(self):
        opener = RecordingOpener()
        transport = AnySearchHTTPTransport(credentials(), opener=opener)
        envelope = transport.execute("anysearch", request({"city": "上海", "query": "博物馆 开放", "max_results": 5}))

        http_request, timeout = opener.requests[-1]
        self.assertEqual(ANYSEARCH_ENDPOINT, http_request.full_url)
        self.assertEqual("POST", http_request.get_method())
        self.assertEqual(10.0, timeout)
        self.assertEqual("Bearer ctw-canary-anysearch-not-real", http_request.get_header("Authorization"))
        self.assertEqual("application/json", http_request.get_header("Content-type"))
        payload = json.loads(http_request.data.decode("utf-8"))
        self.assertEqual(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "search", "arguments": {"query": "博物馆 开放", "max_results": 5}},
            },
            payload,
        )
        self.assertEqual(200, envelope.status_code)
        self.assertEqual("text", envelope.body["result"]["content"][0]["type"])

    def test_key_never_appears_in_url_or_raw_ref(self):
        opener = RecordingOpener()
        transport = AnySearchHTTPTransport(credentials(), opener=opener)
        envelope = transport.execute("anysearch", request({"city": "上海", "query": "博物馆"}))

        http_request, _ = opener.requests[-1]
        parsed = urllib.parse.urlsplit(http_request.full_url)
        self.assertEqual("", parsed.query)
        self.assertNotIn("ctw-canary-anysearch-not-real", http_request.full_url)
        self.assertNotIn("ctw-canary-anysearch-not-real", envelope.raw_ref or "")

    def test_missing_credentials_raises_contract_mismatch_without_network_call(self):
        opener = RecordingOpener()
        transport = AnySearchHTTPTransport(credentials(configured=False), opener=opener)
        with self.assertRaisesRegex(ContractMismatch, "configured credentials"):
            transport.execute("anysearch", request({"city": "上海", "query": "博物馆"}))
        self.assertEqual([], opener.requests)

    def test_missing_query_parameter_raises_contract_mismatch_without_network_call(self):
        opener = RecordingOpener()
        transport = AnySearchHTTPTransport(credentials(), opener=opener)
        with self.assertRaisesRegex(ContractMismatch, "missing query"):
            transport.execute("anysearch", request({"city": "上海"}))
        self.assertEqual([], opener.requests)

    def test_max_results_defaults_and_is_bounded(self):
        opener = RecordingOpener()
        transport = AnySearchHTTPTransport(credentials(), opener=opener)
        transport.execute("anysearch", request({"city": "上海", "query": "博物馆"}))
        payload = json.loads(opener.requests[-1][0].data.decode("utf-8"))
        self.assertEqual(10, payload["params"]["arguments"]["max_results"])

        with self.assertRaisesRegex(ContractMismatch, "max_results"):
            transport.execute("anysearch", request({"city": "上海", "query": "博物馆", "max_results": 51}))
        self.assertEqual(1, len(opener.requests))

    def test_timeout_maps_to_provider_timeout(self):
        def timeout_opener(http_request, timeout):
            raise TimeoutError("synthetic timeout")

        transport = AnySearchHTTPTransport(credentials(), opener=timeout_opener)
        with self.assertRaisesRegex(ProviderTimeout, "deadline exceeded"):
            transport.execute("anysearch", request({"city": "上海", "query": "博物馆"}))

    def test_network_error_maps_to_provider_network_error(self):
        def failing_opener(http_request, timeout):
            raise urllib.error.URLError(socket.gaierror("synthetic DNS failure"))

        transport = AnySearchHTTPTransport(credentials(), opener=failing_opener)
        with self.assertRaisesRegex(ProviderNetworkError, "network request failed"):
            transport.execute("anysearch", request({"city": "上海", "query": "博物馆"}))

    def test_redirect_outside_pinned_origin_is_rejected(self):
        opener = RecordingOpener(json_response(_success_body(), url="https://evil.example/mcp"))
        transport = AnySearchHTTPTransport(credentials(), opener=opener)
        with self.assertRaisesRegex(ProviderNetworkError, "pinned origin"):
            transport.execute("anysearch", request({"city": "上海", "query": "博物馆"}))

    def test_http_error_status_is_captured_in_envelope(self):
        def forbidden_opener(http_request, timeout):
            raise urllib.error.HTTPError(
                http_request.full_url, 403, "Forbidden",
                {"Content-Type": "application/json"},
                _bytes_io(json.dumps({"jsonrpc": "2.0", "id": 1, "error": {"code": -32001, "message": "bad key"}})),
            )

        transport = AnySearchHTTPTransport(credentials(), opener=forbidden_opener)
        envelope = transport.execute("anysearch", request({"city": "上海", "query": "博物馆"}))
        self.assertEqual(403, envelope.status_code)
        self.assertEqual("bad key", envelope.body["error"]["message"])

    def test_non_dict_response_on_success_status_raises_contract_mismatch(self):
        opener = RecordingOpener(FakeResponse(b"[1, 2, 3]", ANYSEARCH_ENDPOINT))
        transport = AnySearchHTTPTransport(credentials(), opener=opener)
        with self.assertRaisesRegex(ContractMismatch, "not an object"):
            transport.execute("anysearch", request({"city": "上海", "query": "博物馆"}))


def _bytes_io(text: str):
    import io
    return io.BytesIO(text.encode("utf-8"))


class AnySearchNormalizeTests(unittest.TestCase):
    def _query(self, body: Any, *, configured: bool = True):
        return AnySearchAdapter().query(
            request({"city": "上海", "query": "博物馆"}),
            ProviderContext(
                clock=FixedClock.from_iso("2026-09-10T00:00:00+08:00"),
                credentials=credentials(configured=configured),
                transport=ReplayTransport({"kind": "response", "status_code": 200, "headers": {}, "body": body}),
            ),
        )

    def test_declared_result_count_mismatch_is_contract_mismatch(self):
        text = "## Search Results (2 results, 10ms)\n\n### 1. 上海博物馆开放信息\n- **URL**: https://www.shanghai.gov.cn/museum\n- official result\n"
        result = self._query({"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": text}]}})
        self.assertEqual("contract_mismatch", result.error_class)
        self.assertEqual((), result.normalized_items)

    def test_missing_jsonrpc_envelope_is_contract_mismatch(self):
        result = self._query({"result": {"content": [{"type": "text", "text": "no envelope"}]}})
        self.assertEqual("contract_mismatch", result.error_class)


class AnySearchFixtureTests(unittest.TestCase):
    def test_fixture_success_maps_title_url_summary_into_item_and_claim(self):
        result, transport = run_fixture_result("success")
        self.assertIsNone(result.error_class)
        self.assertEqual(1, transport.calls)
        item = result.normalized_items[0]
        self.assertEqual("上海博物馆开放信息", item["name"])
        self.assertEqual(["https://www.shanghai.gov.cn/museum"], item["deep_links"])
        claim = result.claims[0]
        self.assertEqual("/name", claim["field_path"])
        self.assertEqual("partial", claim["status"])
        self.assertEqual("上海博物馆开放信息", claim["value"]["name"])
        self.assertEqual("official result", claim["value"]["summary"])

    def test_fixture_empty_reports_no_results(self):
        result, _ = run_fixture_result("empty")
        self.assertEqual("no_results", result.error_class)
        self.assertEqual((), result.normalized_items)
        self.assertEqual("ready", result.health["status"])

    def test_fixture_auth_missing_key_makes_zero_transport_calls(self):
        result, transport = run_fixture_result("auth")
        self.assertEqual("credential_missing", result.error_class)
        self.assertEqual(0, transport.calls)

    def test_fixture_rate_limit_reports_rate_limited(self):
        result, transport = run_fixture_result("rate_limit")
        self.assertEqual("rate_limited", result.error_class)
        self.assertEqual(1, transport.calls)

    def test_fixture_timeout_reports_timeout(self):
        result, transport = run_fixture_result("timeout")
        self.assertEqual("timeout", result.error_class)
        self.assertEqual(2, transport.calls)

    def test_fixture_wrong_shape_top_level_error_is_contract_mismatch(self):
        fixture = load_fixture("wrong_shape")
        self.assertIn("error", fixture["transport"]["body"])
        self.assertNotIn("result", fixture["transport"]["body"])
        result, _ = run_fixture_result("wrong_shape")
        self.assertEqual("contract_mismatch", result.error_class)

    def test_fixture_malicious_strips_script_tag_and_javascript_link(self):
        result, _ = run_fixture_result("malicious")
        self.assertEqual(1, len(result.normalized_items))
        name = result.normalized_items[0]["name"]
        self.assertNotIn("<script", name.lower())
        self.assertNotIn("javascript:", name.lower())
        self.assertNotIn("\x1b", name)
        self.assertIn("[REDACTED]", name)
        self.assertIn("详情", name)


class AnySearchResearchCLITests(unittest.TestCase):
    def test_cli_research_with_fixture_writes_items_and_succeeds(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            output = Path(temporary) / "r.json"
            command = subprocess.run(
                [
                    str(CTW), "research",
                    "--fixture", str(FIXTURES / "success.json"),
                    "--city", "上海", "--query", "博物馆",
                    "--fixed-clock", "2026-09-04T00:00:00+08:00",
                    "--output-json", str(output),
                ],
                text=True, capture_output=True,
            )
            self.assertEqual(0, command.returncode, command.stdout + command.stderr)
            self.assertIn("RESEARCH_COMPLETE", command.stdout)
            payload = load(output)
            self.assertGreaterEqual(len(payload["items"]), 1)
            self.assertEqual("ready", payload["health"]["status"])
            self.assertIsNone(payload["error_class"])

    def test_cli_research_without_key_reports_missing_and_exits_two_with_no_network_events(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            home = Path(temporary) / "home"
            home.mkdir()
            output = Path(temporary) / "r2.json"
            command = subprocess.run(
                [
                    str(CTW), "research",
                    "--city", "上海", "--query", "博物馆",
                    "--progress", "ndjson",
                    "--output-json", str(output),
                ],
                env={"PATH": "/usr/bin:/bin", "HOME": str(home)},
                text=True, capture_output=True,
            )
            self.assertEqual(2, command.returncode, command.stdout + command.stderr)
            self.assertIn("RESEARCH_COMPLETE", command.stdout)
            payload = load(output)
            self.assertEqual("missing", payload["health"]["status"])
            self.assertEqual("credential_missing", payload["error_class"])
            self.assertEqual([], payload["items"])
            self.assertTrue(command.stderr.strip(), "expected at least a completion progress line")
            for line in command.stderr.splitlines():
                if not line.strip():
                    continue
                event = json.loads(line)
                self.assertNotIn(event.get("event"), ("query", "degrade", "retry"))

    def test_cli_research_fixed_clock_without_fixture_fails(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            output = Path(temporary) / "r.json"
            command = subprocess.run(
                [
                    str(CTW), "research",
                    "--city", "上海", "--query", "博物馆",
                    "--fixed-clock", "2026-09-04T00:00:00+08:00",
                    "--output-json", str(output),
                ],
                text=True, capture_output=True,
            )
            self.assertEqual(1, command.returncode, command.stdout + command.stderr)
            self.assertIn("RESEARCH_FAILED", command.stderr)
            self.assertIn("--fixed-clock is allowed only with --fixture", command.stderr)
            self.assertFalse(output.exists())

    def test_cli_research_rejects_non_anysearch_fixture(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            output = Path(temporary) / "r.json"
            command = subprocess.run(
                [
                    str(CTW), "research",
                    "--fixture", str(ROOT / "tests" / "fixtures" / "providers" / "rail12306" / "success.json"),
                    "--city", "上海", "--query", "博物馆",
                    "--output-json", str(output),
                ],
                text=True, capture_output=True,
            )
            self.assertEqual(1, command.returncode, command.stdout + command.stderr)
            self.assertIn("must be an anysearch provider fixture", command.stderr)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
