"""Minimal JSON-RPC-over-stdio MCP client for the pinned 12306 server."""

from __future__ import annotations

import copy
import json
import os
import queue
import re
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from ..contracts import ProviderRequest, canonical_json
from ..credentials import CredentialResolution, provider_environment
from .base import (
    ContractMismatch,
    ProviderEnvelope,
    ProviderNetworkError,
    ProviderTimeout,
)


MCP_PROTOCOL_VERSION = "2025-06-18"
DEFAULT_COMMAND = ("npx", "-y", "12306-mcp@0.3.10")
EXPECTED_12306_TOOLS = (
    "get-current-date",
    "get-stations-code-in-city",
    "get-station-code-of-citys",
    "get-station-code-by-names",
    "get-station-by-telecode",
    "get-tickets",
    "get-interline-tickets",
    "get-train-route-stations",
)
MAX_STDIO_LINE_BYTES = 8 * 1024 * 1024
_AUTHORIZATION_RE = re.compile(r"(?i)(authorization\s*:\s*(?:bearer\s+)?)[^\s]+")
_CREDENTIAL_RE = re.compile(r"(?i)(api[_-]?key|access[_-]?token|secret|password)(\s*[=:]\s*)[^\s]+")
_KNOWN_SECRET_RE = re.compile(r"(?:gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,})")


class MCPError(Exception):
    """Safe base error for the local MCP transport."""


class MCPDeadlineExceeded(MCPError):
    pass


class MCPProtocolError(MCPError):
    pass


def redact_stderr(value: str, max_length: int = 1000) -> str:
    """Return bounded diagnostics without credential-shaped values."""

    clean = "".join(character for character in value if character in "\t\n" or ord(character) >= 32)
    clean = _AUTHORIZATION_RE.sub(r"\1[REDACTED]", clean)
    clean = _CREDENTIAL_RE.sub(r"\1\2[REDACTED]", clean)
    clean = _KNOWN_SECRET_RE.sub("[REDACTED]", clean)
    return clean.strip()[:max_length]


class MCPStdioClient:
    """Line-delimited JSON-RPC client with one absolute deadline."""

    def __init__(
        self,
        command: Sequence[str] = DEFAULT_COMMAND,
        *,
        environment: Mapping[str, str],
        stderr_redactor: Optional[Callable[[str], str]] = None,
        deadline_seconds: float = 30.0,
        cwd: Optional[Path] = None,
    ) -> None:
        if not command or deadline_seconds <= 0:
            raise ValueError("MCP command and positive deadline are required")
        self.command = tuple(str(part) for part in command)
        self.deadline_seconds = float(deadline_seconds)
        self.cwd = Path(cwd) if cwd is not None else None
        self.environment = dict(environment)
        self.stderr_redactor = stderr_redactor or (lambda value: value)
        self._deadline = 0.0
        self._next_id = 1
        self._process: Optional[subprocess.Popen[str]] = None
        self._stdout_queue: "queue.Queue[object]" = queue.Queue()
        self._stderr_lines: List[str] = []
        self._stderr_lock = threading.Lock()
        self._threads: List[threading.Thread] = []

    @property
    def process(self) -> Optional[subprocess.Popen[str]]:
        return self._process

    @property
    def stderr_lines(self) -> Tuple[str, ...]:
        with self._stderr_lock:
            return tuple(self._stderr_lines)

    def __enter__(self) -> "MCPStdioClient":
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        del exc_type, exc, traceback
        self.close()

    def start(self) -> None:
        if self._process is not None:
            raise RuntimeError("MCP client already started")
        try:
            self._process = subprocess.Popen(
                self.command,
                cwd=str(self.cwd) if self.cwd is not None else None,
                env=self.environment,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                start_new_session=True,
            )
        except OSError as exc:
            raise MCPError("could not start the pinned MCP process") from exc
        self._deadline = time.monotonic() + self.deadline_seconds
        stdout_thread = threading.Thread(target=self._read_stdout, name="ctw-mcp-stdout", daemon=True)
        stderr_thread = threading.Thread(target=self._read_stderr, name="ctw-mcp-stderr", daemon=True)
        self._threads = [stdout_thread, stderr_thread]
        for thread in self._threads:
            thread.start()

    def initialize(self) -> Mapping[str, Any]:
        response = self._request(
            "initialize",
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "china-trip-weaver", "version": "0.5.0"},
            },
        )
        result = _result_object(response, "initialize")
        if result.get("protocolVersion") != MCP_PROTOCOL_VERSION:
            raise MCPProtocolError("MCP protocol version mismatch")
        self._notify("notifications/initialized", {})
        return result

    def list_tools(self) -> Tuple[Mapping[str, Any], ...]:
        result = _result_object(self._request("tools/list", {}), "tools/list")
        tools = result.get("tools")
        if not isinstance(tools, list) or not all(isinstance(tool, dict) for tool in tools):
            raise MCPProtocolError("MCP tools/list returned the wrong shape")
        return tuple(tools)

    def call_tool(self, name: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        if not name or not isinstance(arguments, Mapping):
            raise ValueError("tool name and arguments are required")
        return _result_object(
            self._request("tools/call", {"name": name, "arguments": dict(arguments)}),
            "tools/call",
        )

    def close(self) -> None:
        process = self._process
        if process is None:
            return
        if process.stdin is not None and not process.stdin.closed:
            try:
                process.stdin.close()
            except OSError:
                pass
        try:
            process.wait(timeout=1.5)
        except subprocess.TimeoutExpired:
            self._terminate_process_group(process, signal.SIGTERM)
            try:
                process.wait(timeout=1.5)
            except subprocess.TimeoutExpired:
                self._terminate_process_group(process, signal.SIGKILL)
                try:
                    process.wait(timeout=1.5)
                except subprocess.TimeoutExpired:
                    pass
        for stream in (process.stdout, process.stderr):
            if stream is not None and not stream.closed:
                try:
                    stream.close()
                except OSError:
                    pass
        for thread in self._threads:
            thread.join(timeout=0.2)
        self._process = None

    @staticmethod
    def _terminate_process_group(process: subprocess.Popen[str], signum: signal.Signals) -> None:
        if process.poll() is not None:
            return
        try:
            os.killpg(process.pid, signum)
        except (OSError, ProcessLookupError):
            try:
                process.terminate() if signum == signal.SIGTERM else process.kill()
            except OSError:
                pass

    def _request(self, method: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": dict(params)})
        while True:
            remaining = self._deadline - time.monotonic()
            if remaining <= 0:
                raise MCPDeadlineExceeded("MCP session deadline exceeded")
            try:
                message = self._stdout_queue.get(timeout=remaining)
            except queue.Empty as exc:
                raise MCPDeadlineExceeded("MCP session deadline exceeded") from exc
            if isinstance(message, Exception):
                raise message
            if message is None:
                return_code = self._process.poll() if self._process is not None else None
                raise MCPError("MCP process closed stdout (exit=%s)" % return_code)
            if not isinstance(message, dict):
                raise MCPProtocolError("MCP response is not an object")
            if message.get("id") != request_id:
                continue
            if message.get("jsonrpc") != "2.0":
                raise MCPProtocolError("MCP response is not JSON-RPC 2.0")
            if "error" in message:
                raise MCPError("MCP request failed")
            return message

    def _notify(self, method: str, params: Mapping[str, Any]) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": dict(params)})

    def _send(self, value: Mapping[str, Any]) -> None:
        process = self._process
        if process is None or process.stdin is None or process.poll() is not None:
            raise MCPError("MCP process is not running")
        encoded = canonical_json(value)
        if len(encoded.encode("utf-8")) > MAX_STDIO_LINE_BYTES:
            raise MCPProtocolError("MCP request line is too large")
        try:
            process.stdin.write(encoded + "\n")
            process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise MCPError("MCP stdin closed unexpectedly") from exc

    def _read_stdout(self) -> None:
        process = self._process
        assert process is not None and process.stdout is not None
        try:
            for line in process.stdout:
                if len(line.encode("utf-8")) > MAX_STDIO_LINE_BYTES:
                    self._stdout_queue.put(MCPProtocolError("MCP response line is too large"))
                    return
                try:
                    self._stdout_queue.put(json.loads(line))
                except json.JSONDecodeError:
                    self._stdout_queue.put(MCPProtocolError("MCP stdout contained non-JSON data"))
                    return
        finally:
            self._stdout_queue.put(None)

    def _read_stderr(self) -> None:
        process = self._process
        assert process is not None and process.stderr is not None
        for line in process.stderr:
            sanitized = redact_stderr(self.stderr_redactor(line))
            if sanitized:
                with self._stderr_lock:
                    if len(self._stderr_lines) < 50:
                        self._stderr_lines.append(sanitized)


def _result_object(response: Mapping[str, Any], method: str) -> Mapping[str, Any]:
    result = response.get("result")
    if not isinstance(result, dict):
        raise MCPProtocolError("%s result is not an object" % method)
    return result


class RailMCPStdioTransport:
    """Execute the station-resolution then ticket-query MCP sequence."""

    def __init__(
        self,
        *,
        cache_dir: Path,
        credentials: CredentialResolution,
        temp_root: Optional[Path] = None,
        command: Sequence[str] = DEFAULT_COMMAND,
        cwd: Optional[Path] = None,
        station_distance_enricher: Optional[Any] = None,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.credentials = credentials
        self.temp_root = Path(temp_root) if temp_root is not None else self.cache_dir.parent / ".tmp" / "rail-runtime"
        self.command = tuple(command)
        self.cwd = Path(cwd) if cwd is not None else None
        self.station_distance_enricher = station_distance_enricher
        self.calls = 0
        self.last_stderr: Tuple[str, ...] = ()

    def execute(self, provider: str, request: ProviderRequest) -> ProviderEnvelope:
        if provider != "12306-mcp":
            raise ContractMismatch("MCP stdio transport is restricted to 12306-mcp")
        self.calls += 1
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        temp = self.temp_root / "tmp"
        config = self.temp_root / "config"
        cache = self.temp_root / "cache"
        home = self.temp_root / "home"
        for path in (temp, config, cache, home):
            path.mkdir(parents=True, exist_ok=True)
        shim = Path(__file__).with_name("rail_home_shim.cjs")
        if not shim.is_file():
            raise ContractMismatch("rail isolated-home shim is missing")
        environment = provider_environment("rail12306", self.credentials)
        environment["CTW_RAIL_HOME"] = str(home.resolve())
        environment["NODE_OPTIONS"] = "--require=" + str(shim.resolve())
        environment["TMPDIR"] = str(temp.resolve())
        environment["XDG_CONFIG_HOME"] = str(config.resolve())
        environment["XDG_CACHE_HOME"] = str(cache.resolve())
        environment["npm_config_cache"] = str(self.cache_dir.resolve())
        environment["npm_config_userconfig"] = str((self.temp_root / "npmrc").resolve())
        environment["npm_config_update_notifier"] = "false"
        deadline_seconds = request.deadline_ms / 1000.0
        client = MCPStdioClient(
            self.command,
            deadline_seconds=deadline_seconds,
            cwd=self.cwd,
            environment=environment,
        )
        try:
            with client:
                initialized = client.initialize()
                tools = client.list_tools()
                tool_names = tuple(tool.get("name") for tool in tools)
                if tool_names != EXPECTED_12306_TOOLS:
                    raise MCPProtocolError("12306 tools/list fingerprint mismatch")
                body: Dict[str, Any] = {
                    "protocol_version": initialized.get("protocolVersion"),
                    "server_info": initialized.get("serverInfo"),
                    "tools": list(tool_names),
                    "calls": [],
                }
                if request.capability == "station":
                    city = _required_text(request.parameters, "city")
                    arguments = {"city": city}
                    result = client.call_tool("get-stations-code-in-city", arguments)
                    body["calls"].append({"name": "get-stations-code-in-city", "arguments": arguments, "result": result})
                elif request.capability == "rail":
                    from_name = _required_text(request.parameters, "from_name")
                    to_name = _required_text(request.parameters, "to_name")
                    resolution = _resolve_rail_stations(client, body, from_name, to_name)
                    body["station_resolution"] = resolution
                    if resolution["status"] == "resolved":
                        from_code = resolution["endpoints"]["from"]["candidates"][0]["station_code"]
                        to_code = resolution["endpoints"]["to"]["candidates"][0]["station_code"]
                        ticket_arguments: Dict[str, Any] = {
                            "date": _required_text(request.parameters, "date"),
                            "fromStation": from_code,
                            "toStation": to_code,
                            "trainFilterFlags": str(request.parameters.get("train_filter_flags", "")),
                            "format": "json",
                        }
                        for parameter_name, argument_name in (
                            ("earliest_start_time", "earliestStartTime"),
                            ("latest_start_time", "latestStartTime"),
                        ):
                            time_bound = request.parameters.get(parameter_name)
                            if time_bound is not None:
                                if isinstance(time_bound, bool) or not isinstance(time_bound, (int, float)) or not 0 <= time_bound <= 24:
                                    raise ContractMismatch("rail time bound must be between 0 and 24")
                                ticket_arguments[argument_name] = time_bound
                        limited_num = request.parameters.get("limited_num")
                        if limited_num is not None:
                            if not isinstance(limited_num, int) or isinstance(limited_num, bool) or limited_num <= 0:
                                raise ContractMismatch("rail limited_num must be a positive integer")
                            ticket_arguments["limitedNum"] = limited_num
                        result = client.call_tool("get-tickets", ticket_arguments)
                        body["calls"].append({"name": "get-tickets", "arguments": ticket_arguments, "result": result})
                else:
                    raise ContractMismatch("unsupported 12306 capability")
            # Do not keep the rail subprocess open while optional AMap work runs.
            if request.capability == "rail" and body["station_resolution"]["status"] == "ambiguous":
                body["station_resolution"] = self._best_effort_station_distances(
                    body["station_resolution"],
                    request,
                )
            return ProviderEnvelope(status_code=200, body=body, headers={})
        except MCPDeadlineExceeded as exc:
            raise ProviderTimeout("pinned 12306 MCP deadline exceeded") from exc
        except MCPProtocolError as exc:
            raise ContractMismatch(str(exc)) from exc
        except MCPError as exc:
            raise ProviderNetworkError("pinned 12306 MCP process failed") from exc
        finally:
            self.last_stderr = client.stderr_lines
            client.close()

    def _best_effort_station_distances(
        self,
        resolution: Mapping[str, Any],
        request: ProviderRequest,
    ) -> Mapping[str, Any]:
        original = copy.deepcopy(dict(resolution))
        if not _station_resolution_needs_distance(original):
            return original
        try:
            enricher = self.station_distance_enricher
            if enricher is None:
                from ..credentials import resolve_credentials
                from ..station_distance import AMapStationDistanceEnricher

                # AMap is resolved separately and never enters the rail process
                # environment, even when the caller supplied a shared resolution.
                amap_credentials = self.credentials
                if not amap_credentials.get("AMAP_WEBSERVICE_KEY"):
                    amap_credentials = resolve_credentials()
                enricher = AMapStationDistanceEnricher(amap_credentials)
            return enricher.enrich(copy.deepcopy(original), request)
        except Exception:
            # Station distance is an optional signal. Its provider must never turn a
            # successful 12306 resolution into a rail transport or health failure.
            return original


def _station_resolution_needs_distance(resolution: Mapping[str, Any]) -> bool:
    if resolution.get("status") != "ambiguous":
        return False
    endpoints = resolution.get("endpoints")
    if not isinstance(endpoints, dict):
        return False
    for endpoint in ("from", "to"):
        value = endpoints.get(endpoint)
        candidates = value.get("candidates") if isinstance(value, dict) else None
        if isinstance(candidates, list) and len(candidates) > 1:
            if any(isinstance(candidate, dict) and "distance_meters" not in candidate for candidate in candidates):
                return True
    return False


def _required_text(parameters: Mapping[str, Any], name: str) -> str:
    value = parameters.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ContractMismatch("rail request is missing %s" % name)
    return value.strip()


def _station_tool_json(result: Mapping[str, Any]) -> Any:
    if not isinstance(result, dict):
        raise ContractMismatch("MCP station tool result is not an object")
    is_error = result.get("isError", False)
    if not isinstance(is_error, bool):
        raise ContractMismatch("MCP station tool isError flag has the wrong shape")
    content = result.get("content")
    if not isinstance(content, list) or len(content) != 1 or not isinstance(content[0], dict):
        raise ContractMismatch("MCP tool content has the wrong shape")
    if content[0].get("type") != "text" or not isinstance(content[0].get("text"), str):
        raise ContractMismatch("MCP tool content is not text JSON")
    text = content[0]["text"].strip()
    if is_error or _is_station_not_found_text(text):
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ContractMismatch("MCP tool text is not JSON") from exc
    if _is_station_error(payload):
        return None
    return payload


def _is_station_not_found_text(value: str) -> bool:
    return value.rstrip(". ") == "Error: City not found"


def _is_station_error(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"error"}
        and isinstance(value.get("error"), str)
        and bool(value["error"].strip())
    )


def _station_candidate(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ContractMismatch("12306 station candidate is not an object")
    code = value.get("station_code")
    name = value.get("station_name")
    if not isinstance(code, str) or not re.fullmatch(r"[A-Z]{3}", code):
        raise ContractMismatch("12306 station code is invalid")
    if not isinstance(name, str) or not name.strip():
        raise ContractMismatch("12306 station name is invalid")
    candidate: Dict[str, Any] = {"station_code": code, "station_name": name.strip()}
    distance = value.get("distance_meters")
    if isinstance(distance, (int, float)) and not isinstance(distance, bool) and distance >= 0:
        candidate["distance_meters"] = distance
    return candidate


def _candidate_sort_key(candidate: Mapping[str, Any]) -> Tuple[Any, ...]:
    distance = candidate.get("distance_meters")
    has_distance = isinstance(distance, (int, float)) and not isinstance(distance, bool)
    return (
        0 if has_distance else 1,
        float(distance) if has_distance else 0.0,
        str(candidate["station_name"]),
        str(candidate["station_code"]),
    )


def _deduplicated_candidates(values: Sequence[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    by_code: Dict[str, Mapping[str, Any]] = {}
    for value in values:
        candidate = _station_candidate(value)
        code = str(candidate["station_code"])
        previous = by_code.get(code)
        if previous is not None and previous != candidate:
            raise ContractMismatch("12306 returned conflicting station candidates")
        by_code[code] = candidate
    return sorted(by_code.values(), key=_candidate_sort_key)


def _mapped_station_candidates(
    payload: Any,
    names: Sequence[str],
    *,
    strip_station_suffix: bool,
) -> Mapping[str, Sequence[Mapping[str, Any]]]:
    if payload is None or payload == {}:
        return {name: () for name in names}
    if not isinstance(payload, dict):
        raise ContractMismatch("12306 station-name response is not an object")
    resolved: Dict[str, Sequence[Mapping[str, Any]]] = {}
    for name in names:
        lookup_name = name[:-1] if strip_station_suffix and name.endswith("站") else name
        value = payload.get(lookup_name)
        if value is None or _is_station_error(value):
            resolved[name] = ()
        else:
            resolved[name] = (_station_candidate(value),)
    return resolved


def _city_station_candidates(payload: Any) -> Sequence[Mapping[str, Any]]:
    if payload is None or payload == []:
        return ()
    if not isinstance(payload, list):
        raise ContractMismatch("12306 stations-in-city response is not an array")
    return tuple(_deduplicated_candidates(payload))


def _call_station_tool(
    client: MCPStdioClient,
    body: Dict[str, Any],
    name: str,
    arguments: Mapping[str, Any],
) -> Any:
    result = client.call_tool(name, arguments)
    body["calls"].append({"name": name, "arguments": dict(arguments), "result": result})
    return _station_tool_json(result)


def _unique_names(values: Sequence[str]) -> List[str]:
    return list(dict.fromkeys(values))


def _resolve_rail_stations(
    client: MCPStdioClient,
    body: Dict[str, Any],
    from_name: str,
    to_name: str,
) -> Mapping[str, Any]:
    endpoint_names = {"from": from_name, "to": to_name}
    endpoint_candidates: Dict[str, Sequence[Mapping[str, Any]]] = {"from": (), "to": ()}

    names = _unique_names((from_name, to_name))
    exact_arguments = {"stationNames": "|".join(names)}
    exact_payload = _call_station_tool(client, body, "get-station-code-by-names", exact_arguments)
    exact = _mapped_station_candidates(exact_payload, names, strip_station_suffix=True)
    for endpoint, name in endpoint_names.items():
        endpoint_candidates[endpoint] = exact[name]

    unresolved = [endpoint for endpoint in ("from", "to") if not endpoint_candidates[endpoint]]
    if unresolved:
        city_names = _unique_names(tuple(endpoint_names[endpoint] for endpoint in unresolved))
        city_arguments = {"citys": "|".join(city_names)}
        city_payload = _call_station_tool(client, body, "get-station-code-of-citys", city_arguments)
        representatives = _mapped_station_candidates(city_payload, city_names, strip_station_suffix=False)
        for endpoint in unresolved:
            endpoint_candidates[endpoint] = representatives[endpoint_names[endpoint]]

    unresolved = [endpoint for endpoint in ("from", "to") if not endpoint_candidates[endpoint]]
    city_results: Dict[str, Sequence[Mapping[str, Any]]] = {}
    for endpoint in unresolved:
        city = endpoint_names[endpoint]
        if city not in city_results:
            payload = _call_station_tool(client, body, "get-stations-code-in-city", {"city": city})
            city_results[city] = _city_station_candidates(payload)
        endpoint_candidates[endpoint] = city_results[city]

    counts = [len(endpoint_candidates[endpoint]) for endpoint in ("from", "to")]
    if any(count == 0 for count in counts):
        status = "no_results"
    elif any(count > 1 for count in counts):
        status = "ambiguous"
    else:
        status = "resolved"
    return {
        "status": status,
        "endpoints": {
            endpoint: {
                "query": endpoint_names[endpoint],
                "candidates": list(endpoint_candidates[endpoint]),
            }
            for endpoint in ("from", "to")
        },
    }
