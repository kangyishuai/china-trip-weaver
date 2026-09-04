"""Pinned VariFlight MCP stdio transport with probe-only keyless behavior."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from ..contracts import ProviderRequest
from ..credentials import CredentialResolution, provider_environment, redact_text
from .base import ContractMismatch, ProviderEnvelope, ProviderNetworkError, ProviderTimeout
from .mcp_stdio import (
    MCPDeadlineExceeded,
    MCPError,
    MCPProtocolError,
    MCPStdioClient,
)
from .variflight import EXPECTED_TOOLS


DEFAULT_COMMAND = ("npx", "-y", "@variflight-ai/variflight-mcp@1.0.3")


class VariFlightMCPTransport:
    def __init__(
        self,
        credentials: CredentialResolution,
        *,
        cache_dir: Path,
        temp_root: Path,
        command: Sequence[str] = DEFAULT_COMMAND,
        cwd: Optional[Path] = None,
    ) -> None:
        self.credentials = credentials
        self.cache_dir = Path(cache_dir)
        self.temp_root = Path(temp_root)
        self.command = tuple(str(item) for item in command)
        self.cwd = Path(cwd) if cwd is not None else None
        self.probe_calls = 0
        self.business_calls = 0
        self.last_stderr: Tuple[str, ...] = ()
        self.last_tools: Tuple[Mapping[str, Any], ...] = ()

    @property
    def calls(self) -> int:
        return self.business_calls

    def probe(self, deadline_seconds: float = 15.0) -> Tuple[Mapping[str, Any], ...]:
        initialized, tools, result = self._session(None, {}, deadline_seconds)
        del initialized, result
        self.probe_calls += 1
        self.last_tools = tools
        return tools

    def execute(self, provider: str, request: ProviderRequest) -> ProviderEnvelope:
        if provider != "variflight":
            raise ContractMismatch("VariFlight MCP transport is restricted to variflight")
        if not self.credentials.get("VARIFLIGHT_API_KEY") and not self.credentials.get("X_VARIFLIGHT_KEY"):
            raise ContractMismatch("VariFlight business call requires a configured credential")
        tool_name, arguments = _tool_call(request)
        initialized, tools, result = self._session(
            tool_name, arguments, request.deadline_ms / 1000.0,
        )
        del initialized
        self.probe_calls += 1
        self.business_calls += 1
        self.last_tools = tools
        status = _result_status(result)
        return ProviderEnvelope(
            status_code=status,
            body={
                "tools": [item["name"] for item in tools],
                "tool": tool_name,
                "content": result.get("content", []),
                "isError": bool(result.get("isError", False)),
            },
            headers={},
            raw_ref="variflight-mcp:" + tool_name,
        )

    def _session(
        self,
        tool_name: Optional[str],
        arguments: Mapping[str, Any],
        deadline_seconds: float,
    ) -> Tuple[Mapping[str, Any], Tuple[Mapping[str, Any], ...], Mapping[str, Any]]:
        if deadline_seconds <= 0:
            raise ContractMismatch("VariFlight deadline must be positive")
        environment = self._environment()
        client = MCPStdioClient(
            self.command,
            environment=environment,
            stderr_redactor=lambda value: redact_text(value, self.credentials),
            deadline_seconds=deadline_seconds,
            cwd=self.cwd,
        )
        try:
            with client:
                initialized = client.initialize()
                tools = tuple(client.list_tools())
                names = tuple(item.get("name") for item in tools)
                if names != EXPECTED_TOOLS:
                    raise MCPProtocolError("VariFlight tools/list fingerprint mismatch")
                result: Mapping[str, Any] = {}
                if tool_name is not None:
                    result = client.call_tool(tool_name, arguments)
                return initialized, tools, result
        except MCPDeadlineExceeded as exc:
            raise ProviderTimeout("VariFlight MCP deadline exceeded") from exc
        except MCPProtocolError as exc:
            raise ContractMismatch(str(exc)) from exc
        except MCPError as exc:
            raise ProviderNetworkError("VariFlight MCP process failed") from exc
        finally:
            self.last_stderr = client.stderr_lines
            client.close()

    def _environment(self) -> Dict[str, str]:
        temp = self.temp_root / "tmp"
        config = self.temp_root / "config"
        cache = self.temp_root / "cache"
        home = self.temp_root / "home"
        for path in (self.cache_dir, temp, config, cache, home):
            path.mkdir(parents=True, exist_ok=True)
        shim = Path(__file__).with_name("variflight_home_shim.cjs")
        if not shim.is_file():
            raise ValueError("VariFlight isolated-home shim is missing")
        environment = provider_environment("variflight", self.credentials)
        environment.update({
            "CTW_VARIFLIGHT_HOME": str(home.resolve()),
            "NODE_OPTIONS": "--require=" + str(shim.resolve()),
            "TMPDIR": str(temp.resolve()),
            "XDG_CONFIG_HOME": str(config.resolve()),
            "XDG_CACHE_HOME": str(cache.resolve()),
            "npm_config_cache": str(self.cache_dir.resolve()),
            "npm_config_userconfig": str((self.temp_root / "npmrc").resolve()),
            "npm_config_update_notifier": "false",
        })
        return environment


def _tool_call(request: ProviderRequest) -> Tuple[str, Mapping[str, Any]]:
    action = request.parameters.get("action", "search")
    if action == "search":
        return "searchFlightsByDepArr", {
            "depcity": _iata(request.parameters, "dep_city"),
            "arrcity": _iata(request.parameters, "arr_city"),
            "date": _date(request.parameters, "date"),
        }
    if action == "comfort":
        return "flightHappinessIndex", {
            "fnum": _flight_number(request.parameters, "flight_no"),
            "date": _date(request.parameters, "date"),
        }
    raise ContractMismatch("unsupported VariFlight action")


def _result_status(result: Mapping[str, Any]) -> int:
    if not result.get("isError"):
        return 200
    content = result.get("content")
    text = ""
    if isinstance(content, list):
        text = " ".join(
            str(item.get("text", "")) for item in content if isinstance(item, dict)
        ).lower()
    if "429" in text or "rate" in text or "quota" in text:
        return 429
    if "401" in text:
        return 401
    if "403" in text or "forbidden" in text or "key" in text or "balance" in text:
        return 403
    return 502


def _iata(values: Mapping[str, Any], name: str) -> str:
    value = values.get(name)
    if not isinstance(value, str) or len(value) != 3 or not value.isascii() or not value.isalpha():
        raise ContractMismatch("VariFlight %s must be a 3-letter IATA code" % name)
    return value.upper()


def _date(values: Mapping[str, Any], name: str) -> str:
    value = values.get(name)
    if not isinstance(value, str) or len(value) != 10 or value[4] != "-" or value[7] != "-":
        raise ContractMismatch("VariFlight date must be YYYY-MM-DD")
    return value


def _flight_number(values: Mapping[str, Any], name: str) -> str:
    value = values.get(name)
    if not isinstance(value, str) or not value.isascii() or not 3 <= len(value) <= 7 or not value.isalnum():
        raise ContractMismatch("VariFlight flight number is invalid")
    return value.upper()
