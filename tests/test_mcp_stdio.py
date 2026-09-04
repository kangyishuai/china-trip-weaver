from __future__ import annotations

import os
import signal
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "plugins" / "china-trip-weaver" / "src"
sys.path.insert(0, str(SRC))

from china_trip_weaver.clock import FixedClock
from china_trip_weaver.contracts import ProviderRequest
from china_trip_weaver.credentials import provider_environment, resolve_credentials
from china_trip_weaver.providers.base import ProviderContext
from china_trip_weaver.providers.mcp_stdio import (
    MCPDeadlineExceeded,
    MCPProtocolError,
    MCPStdioClient,
    RailMCPStdioTransport,
)
from china_trip_weaver.providers.rail12306 import EXPECTED_TOOLS, Rail12306Adapter


SERVER = ROOT / "tests" / "fixtures" / "mcp_stdio_server.py"


class MCPStdioClientTests(unittest.TestCase):
    def command(self, mode="normal"):
        return (sys.executable, str(SERVER), mode)

    def environment(self):
        credentials = resolve_credentials({}, ROOT / ".tmp" / "mcp-no-credentials")
        return provider_environment("rail12306", credentials)

    def test_jsonrpc_lifecycle_stderr_redaction_and_process_cleanup(self):
        client = MCPStdioClient(self.command(), environment=self.environment(), deadline_seconds=2)
        with client:
            process = client.process
            initialized = client.initialize()
            tools = client.list_tools()
            result = client.call_tool("get-station-code-of-citys", {"citys": "北京|上海"})
            self.assertEqual("12306-mcp", initialized["serverInfo"]["name"])
            self.assertEqual(EXPECTED_TOOLS, tuple(tool["name"] for tool in tools))
            self.assertIn("content", result)
        self.assertIsNotNone(process)
        self.assertIsNotNone(process.poll())
        diagnostics = "\n".join(client.stderr_lines)
        self.assertIn("[REDACTED]", diagnostics)
        self.assertNotIn("ctw-stdio-canary", diagnostics)

    def test_absolute_deadline_terminates_the_process(self):
        client = MCPStdioClient(self.command("slow"), environment=self.environment(), deadline_seconds=0.05)
        client.start()
        process = client.process
        try:
            with self.assertRaises(MCPDeadlineExceeded):
                client.initialize()
        finally:
            client.close()
        self.assertIsNotNone(process)
        self.assertIsNotNone(process.poll())

    def test_close_escalates_from_sigterm_to_sigkill_after_stdin_eof(self):
        client = MCPStdioClient(self.command("hang-after-eof"), environment=self.environment(), deadline_seconds=2)
        client.start()
        process = client.process
        self.assertIsNotNone(process)

        def reap_after_failed_assertion():
            if process.poll() is None:
                process.kill()
                process.wait(timeout=2)
            client.close()

        self.addCleanup(reap_after_failed_assertion)
        client.close()

        self.assertIsNone(client.process)
        self.assertEqual(-signal.SIGKILL, process.poll())
        diagnostics = "\n".join(client.stderr_lines)
        self.assertIn("fixture-received-stdin-eof", diagnostics)
        self.assertIn("fixture-received-sigterm", diagnostics)

    def test_non_json_stdout_is_protocol_error_and_process_is_reaped(self):
        client = MCPStdioClient(self.command("invalid-json"), environment=self.environment(), deadline_seconds=2)
        client.start()
        process = client.process
        try:
            with self.assertRaises(MCPProtocolError):
                client.initialize()
        finally:
            client.close()
        self.assertIsNotNone(process)
        self.assertIsNotNone(process.poll())

    def test_transport_runs_station_then_ticket_and_adapter_emits_live_leg(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            credentials = resolve_credentials({}, ROOT / ".tmp" / "mcp-no-credentials")
            transport = RailMCPStdioTransport(
                cache_dir=Path(temporary) / "npm-cache",
                credentials=credentials,
                command=self.command("assert-time-bounds"),
                cwd=ROOT,
            )
            request = ProviderRequest(
                request_id="mcp-integration",
                capability="rail",
                parameters={
                    "date": "2026-09-10",
                    "from_name": "北京",
                    "to_name": "上海",
                    "from_ref": "city-beijing",
                    "to_ref": "city-shanghai",
                    "train_filter_flags": "GD",
                    "limited_num": 1,
                    "earliest_start_time": 15,
                    "latest_start_time": 21,
                },
                deadline_ms=2000,
                as_of="2026-09-10",
                cache_policy="bypass",
                trace={"stage": "test"},
            )
            context = ProviderContext(
                clock=FixedClock.from_iso("2026-09-03T20:46:00+08:00"),
                credentials=resolve_credentials({}, ROOT / ".tmp" / "mcp-no-credentials"),
                transport=transport,
            )
            result = Rail12306Adapter().query(request, context)
        self.assertIsNone(result.error_class)
        self.assertEqual(1, transport.calls)
        self.assertEqual("G1001", result.normalized_items[0]["service_number"])
        self.assertEqual(300, result.normalized_items[0]["price"]["amount"])
        self.assertEqual("live", result.normalized_items[0]["price"]["price_type"])

    def test_rail_subprocess_receives_only_provider_environment(self):
        inherited = {
            "AMAP_WEBSERVICE_KEY": "ctw-canary-amap-not-a-real-secret",
            "FLYAI_API_KEY": "ctw-canary-flyai-not-a-real-secret",
            "VARIFLIGHT_API_KEY": "ctw-canary-variflight-not-a-real-secret",
            "UNRELATED_TOKEN": "ctw-canary-unrelated-not-a-real-secret",
        }
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            credentials = resolve_credentials(inherited, Path(temporary) / "missing")
            transport = RailMCPStdioTransport(
                cache_dir=Path(temporary) / "npm-cache",
                credentials=credentials,
                command=self.command("assert-minimal-env"),
                cwd=ROOT,
            )
            request = ProviderRequest(
                request_id="mcp-minimal-env",
                capability="station",
                parameters={"city": "北京"},
                deadline_ms=2000,
                as_of="2026-09-10",
                cache_policy="bypass",
                trace={"stage": "test"},
            )
            context = ProviderContext(
                clock=FixedClock.from_iso("2026-09-03T20:46:00+08:00"),
                credentials=credentials,
                transport=transport,
            )
            with mock.patch.dict(os.environ, inherited, clear=False):
                result = Rail12306Adapter().query(request, context)
        self.assertIsNone(result.error_class)


if __name__ == "__main__":
    unittest.main()
