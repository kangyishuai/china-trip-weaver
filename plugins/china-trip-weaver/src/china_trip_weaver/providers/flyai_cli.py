"""Pinned, isolated subprocess transport for FlyAI CLI 1.0.16."""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from ..contracts import ProviderRequest
from ..credentials import CredentialResolution, provider_environment, redact_text
from .base import ContractMismatch, ProviderEnvelope, ProviderNetworkError, ProviderTimeout


DEFAULT_COMMAND = ("npx", "-y", "@fly-ai/flyai-cli@1.0.16")
CLI_VERSION = "1.0.16"
MAX_OUTPUT_BYTES = 16 * 1024 * 1024
ROOT_FINGERPRINTS = (
    "Usage: flyai [options] [command]",
    "search-hotel|search-hotels",
    "search-flight",
)
COMMAND_FLAGS = {
    "search-hotel": ("--dest-name", "--check-in-date", "--check-out-date"),
    "search-flight": ("--origin", "--destination", "--dep-date", "--journey-type"),
}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class FlyAISubprocessTransport:
    """Run constant argv with provider-only credentials and bounded diagnostics."""

    _provider_gate = threading.BoundedSemaphore(1)
    retry_rate_limits = True

    def __init__(
        self,
        credentials: CredentialResolution,
        *,
        cache_dir: Path,
        temp_root: Path,
        command: Sequence[str] = DEFAULT_COMMAND,
        cwd: Optional[Path] = None,
        progress: Optional[Callable[[Mapping[str, Any]], None]] = None,
    ) -> None:
        if not command:
            raise ValueError("FlyAI command is required")
        self.credentials = credentials
        self.cache_dir = Path(cache_dir)
        self.temp_root = Path(temp_root)
        self.command = tuple(str(item) for item in command)
        self.cwd = Path(cwd) if cwd is not None else None
        self.progress = progress
        self.calls = 0
        self.probe_calls = 0
        self.last_stderr: Tuple[str, ...] = ()
        self.argv_history: List[Tuple[str, ...]] = []
        self._root_probed = False
        self._command_probes: Dict[str, Tuple[str, ...]] = {}

    def execute(self, provider: str, request: ProviderRequest) -> ProviderEnvelope:
        if provider != "flyai":
            raise ContractMismatch("FlyAI subprocess transport is restricted to flyai")
        if request.deadline_ms <= 0:
            raise ContractMismatch("FlyAI deadline must be positive")
        command_name, arguments = _business_arguments(request)
        deadline = time.monotonic() + request.deadline_ms / 1000.0
        environment = self._environment()
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not self._provider_gate.acquire(timeout=remaining):
            raise ProviderTimeout("FlyAI concurrency gate deadline exceeded")
        try:
            return self._execute_serial(command_name, arguments, deadline, environment)
        finally:
            self._provider_gate.release()

    def _execute_serial(
        self,
        command_name: str,
        arguments: Tuple[str, ...],
        deadline: float,
        environment: Mapping[str, str],
    ) -> ProviderEnvelope:
        if not self._root_probed:
            self._emit_progress(event="probe", provider="flyai", scope="root", status="started")
            root_help, root_stderr = self._run(self.command + ("--help",), environment, deadline)
            self.probe_calls += 1
            self._remember_stderr(root_stderr)
            if any(fragment not in root_help for fragment in ROOT_FINGERPRINTS):
                raise ContractMismatch("FlyAI root help fingerprint mismatch")
            self._root_probed = True
        if command_name not in self._command_probes:
            self._emit_progress(
                event="probe", provider="flyai", scope="command",
                capability=command_name, status="started",
            )
            command_help, command_stderr = self._run(
                self.command + (command_name, "--help"), environment, deadline,
            )
            self.probe_calls += 1
            self._remember_stderr(command_stderr)
            required_flags = COMMAND_FLAGS[command_name]
            if any(flag not in command_help for flag in required_flags):
                raise ContractMismatch("FlyAI %s help fingerprint mismatch" % command_name)
            self._command_probes[command_name] = required_flags

        stdout, stderr = self._run(self.command + (command_name,) + arguments, environment, deadline)
        self.calls += 1
        self._remember_stderr(stderr)
        try:
            body = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise ContractMismatch("FlyAI stdout is not one JSON document") from exc
        if not isinstance(body, dict):
            raise ContractMismatch("FlyAI stdout root is not an object")
        body = dict(body)
        body["cliVersion"] = CLI_VERSION
        body["commands"] = ["search-hotel", "search-flight"]
        body["probe"] = {
            "command": command_name,
            "flags": list(self._command_probes[command_name]),
        }
        return ProviderEnvelope(
            status_code=429 if body.get("status") == 429 else 200,
            body=body,
            headers={},
            raw_ref="flyai-cli:" + command_name,
        )

    def _emit_progress(self, **event: Any) -> None:
        if not callable(self.progress):
            return
        try:
            self.progress(dict(event))
        except Exception:
            return

    def _environment(self) -> Dict[str, str]:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        temp = self.temp_root / "tmp"
        config = self.temp_root / "config"
        cache = self.temp_root / "cache"
        home = self.temp_root / "home"
        for path in (temp, config, cache, home):
            path.mkdir(parents=True, exist_ok=True)
        home_shim = Path(__file__).with_name("flyai_home_shim.cjs")
        if not home_shim.is_file():
            raise ValueError("FlyAI isolated-home shim is missing")
        environment = provider_environment("flyai", self.credentials)
        environment.update({
            "CTW_FLYAI_HOME": str(home.resolve()),
            "NODE_OPTIONS": "--require=" + str(home_shim.resolve()),
            "TMPDIR": str(temp.resolve()),
            "XDG_CONFIG_HOME": str(config.resolve()),
            "XDG_CACHE_HOME": str(cache.resolve()),
            "npm_config_cache": str(self.cache_dir.resolve()),
            "npm_config_userconfig": str((self.temp_root / "npmrc").resolve()),
            "npm_config_update_notifier": "false",
        })
        return environment

    def _run(
        self,
        argv: Tuple[str, ...],
        environment: Mapping[str, str],
        deadline: float,
    ) -> Tuple[str, str]:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ProviderTimeout("FlyAI absolute deadline exceeded")
        self.argv_history.append(argv)
        try:
            process = subprocess.Popen(
                argv,
                cwd=str(self.cwd) if self.cwd is not None else None,
                env=dict(environment),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                start_new_session=True,
            )
        except OSError as exc:
            raise ProviderNetworkError("could not start pinned FlyAI CLI") from exc
        try:
            stdout, stderr = process.communicate(timeout=remaining)
        except subprocess.TimeoutExpired as exc:
            _terminate_process(process)
            process.communicate()
            raise ProviderTimeout("FlyAI absolute deadline exceeded") from exc
        if len(stdout.encode("utf-8")) > MAX_OUTPUT_BYTES or len(stderr.encode("utf-8")) > MAX_OUTPUT_BYTES:
            raise ContractMismatch("FlyAI subprocess output exceeds 16 MiB")
        safe_stderr = redact_text(stderr, self.credentials)[:2000]
        if process.returncode != 0:
            diagnostic = (safe_stderr + "\n" + stdout[:1000]).lower()
            if any(token in diagnostic for token in ("429", "quota", "rate limit", "trial limit")):
                return json.dumps({"status": 429, "message": "rate limited", "data": {}}), safe_stderr
            if any(token in diagnostic for token in ("401", "403", "unauthorized", "forbidden", "invalid api key")):
                return json.dumps({"status": 403, "message": "forbidden", "data": {}}), safe_stderr
            raise ProviderNetworkError("FlyAI CLI exited nonzero")
        return stdout.strip(), safe_stderr

    def _remember_stderr(self, value: str) -> None:
        if value:
            self.last_stderr = tuple((list(self.last_stderr) + [value])[-10:])


def _business_arguments(request: ProviderRequest) -> Tuple[str, Tuple[str, ...]]:
    values = request.parameters
    if request.capability == "lodging":
        return "search-hotel", (
            "--dest-name", _safe_text(values, "city"),
            "--check-in-date", _date(values, "check_in"),
            "--check-out-date", _date(values, "check_out"),
        )
    if request.capability == "flight":
        return "search-flight", (
            "--origin", _safe_text(values, "origin"),
            "--destination", _safe_text(values, "destination"),
            "--dep-date", _date(values, "date"),
            "--journey-type", "1",
        )
    raise ContractMismatch("unsupported FlyAI capability")


def _safe_text(values: Mapping[str, Any], name: str) -> str:
    value = values.get(name)
    if not isinstance(value, str) or not value.strip() or value.strip().startswith("-") or len(value) > 120:
        raise ContractMismatch("FlyAI request has invalid %s" % name)
    return value.strip()


def _date(values: Mapping[str, Any], name: str) -> str:
    value = _safe_text(values, name)
    if not DATE_RE.fullmatch(value):
        raise ContractMismatch("FlyAI %s must be YYYY-MM-DD" % name)
    return value


def _terminate_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (OSError, ProcessLookupError):
        process.terminate()
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            process.kill()
        process.wait(timeout=1)
