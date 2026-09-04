"""Strict credential resolution, provider isolation, and redaction."""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path
from types import MappingProxyType
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .errors import CTWError


MAX_CREDENTIAL_FILE_BYTES = 64 * 1024
SECRET_NAMES = (
    "AMAP_WEBSERVICE_KEY",
    "FLYAI_API_KEY",
    "VARIFLIGHT_API_KEY",
    "X_VARIFLIGHT_KEY",
    "ANYSEARCH_API_KEY",
)
SUPPORTED_KEY_NAMES = SECRET_NAMES
NON_SECRET_NAMES = ("VARIFLIGHT_API_URL",)
FILE_ALLOWLIST = frozenset(SECRET_NAMES + NON_SECRET_NAMES)
PROVIDER_NAMES = {
    "amap": ("AMAP_WEBSERVICE_KEY",),
    "flyai": ("FLYAI_API_KEY",),
    "variflight": ("VARIFLIGHT_API_KEY", "X_VARIFLIGHT_KEY", "VARIFLIGHT_API_URL"),
    "anysearch": ("ANYSEARCH_API_KEY",),
    "rail12306": (),
    "host_web": (),
    "scheduler": (),
    "renderer": (),
}
SAFE_PROCESS_ENV = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "SYSTEMROOT")
NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
URL_SECRET_RE = re.compile(
    r"(?i)([?&](?:api[_-]?key|key|token|access[_-]?token|secret|password)=)([^&#\s]+)"
)
AUTH_HEADER_RE = re.compile(r"(?im)^(authorization\s*:\s*)([^\r\n]+)$")


def default_credential_path() -> Path:
    return Path.home() / ".config" / "china-trip-weaver" / "credentials.env"


class CredentialResolution:
    """Holds values without exposing them through repr or public summaries."""

    __slots__ = ("_values", "warnings")

    def __init__(self, values: Mapping[str, str], warnings: Sequence[str] = ()) -> None:
        self._values = MappingProxyType(dict(values))
        self.warnings = tuple(warnings)

    def __repr__(self) -> str:
        return "CredentialResolution(configured=%r, warnings=%d)" % (
            self.configured_names(),
            len(self.warnings),
        )

    def get(self, name: str) -> Optional[str]:
        return self._values.get(name)

    def configured_names(self) -> Tuple[str, ...]:
        return tuple(sorted(name for name in SECRET_NAMES if self._values.get(name)))

    def status(self) -> Mapping[str, str]:
        return MappingProxyType({name: "configured" if self._values.get(name) else "missing" for name in SECRET_NAMES})

    def secret_values(self) -> Tuple[str, ...]:
        return tuple(sorted({self._values[name] for name in SECRET_NAMES if self._values.get(name)}, key=len, reverse=True))


def _read_credential_file(path: Path) -> Tuple[Dict[str, str], Tuple[str, ...]]:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return {}, ()
    except OSError as exc:
        raise CTWError("forbidden", "CREDENTIAL_FILE_STAT", "Credential file could not be inspected.") from exc

    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise CTWError("forbidden", "CREDENTIAL_FILE_TYPE", "Credential path must be a regular, non-symlink file.")
    if os.name == "posix":
        if metadata.st_uid != os.getuid():
            raise CTWError("forbidden", "CREDENTIAL_FILE_OWNER", "Credential file must be owned by the current user.")
        if stat.S_IMODE(metadata.st_mode) != 0o600:
            raise CTWError("forbidden", "CREDENTIAL_FILE_MODE", "Credential file mode must be exactly 0600.")
    if metadata.st_size > MAX_CREDENTIAL_FILE_BYTES:
        raise CTWError("forbidden", "CREDENTIAL_FILE_SIZE", "Credential file exceeds 64 KiB.")

    try:
        raw = path.read_bytes()
        if len(raw) > MAX_CREDENTIAL_FILE_BYTES:
            raise CTWError("forbidden", "CREDENTIAL_FILE_SIZE", "Credential file exceeds 64 KiB.")
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CTWError("forbidden", "CREDENTIAL_FILE_UTF8", "Credential file must be UTF-8.") from exc
    except OSError as exc:
        raise CTWError("forbidden", "CREDENTIAL_FILE_READ", "Credential file could not be read.") from exc

    values: Dict[str, str] = {}
    warnings: List[str] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export ") or "=" not in line:
            raise CTWError("forbidden", "CREDENTIAL_FILE_SYNTAX", "Credential file has invalid syntax on line %d." % line_number)
        name, value = line.split("=", 1)
        if not NAME_RE.fullmatch(name) or not value or "\x00" in value:
            raise CTWError("forbidden", "CREDENTIAL_FILE_SYNTAX", "Credential file has invalid syntax on line %d." % line_number)
        if name not in FILE_ALLOWLIST:
            warnings.append("ignored unknown variable on line %d" % line_number)
            continue
        if name in values:
            raise CTWError("forbidden", "CREDENTIAL_FILE_DUPLICATE", "Credential file repeats a variable on line %d." % line_number)
        values[name] = value
    return values, tuple(warnings)


def resolve_credentials(
    environ: Optional[Mapping[str, str]] = None,
    credential_path: Optional[Path] = None,
) -> CredentialResolution:
    source = os.environ if environ is None else environ
    path = default_credential_path() if credential_path is None else credential_path
    file_values, warnings = _read_credential_file(path)
    values: Dict[str, str] = {}
    for name in FILE_ALLOWLIST:
        env_value = source.get(name)
        if env_value:
            values[name] = env_value
        elif file_values.get(name):
            values[name] = file_values[name]

    # The compatibility key is ignored when the canonical VariFlight key exists.
    if values.get("VARIFLIGHT_API_KEY"):
        values.pop("X_VARIFLIGHT_KEY", None)
    return CredentialResolution(values, warnings)


def provider_environment(
    provider: str,
    credentials: CredentialResolution,
    inherited: Optional[Mapping[str, str]] = None,
) -> Dict[str, str]:
    if provider not in PROVIDER_NAMES:
        raise ValueError("unknown provider: %s" % provider)
    source = os.environ if inherited is None else inherited
    result = {name: source[name] for name in SAFE_PROCESS_ENV if source.get(name)}
    for name in PROVIDER_NAMES[provider]:
        value = credentials.get(name)
        if value:
            result[name] = value
    return result


def provider_credential_status(credentials: CredentialResolution) -> Mapping[str, str]:
    """Return status-only summaries for credential-bearing providers."""

    statuses: Dict[str, str] = {}
    for provider in ("amap", "flyai", "variflight", "anysearch"):
        secret_names = tuple(name for name in PROVIDER_NAMES[provider] if name in SECRET_NAMES)
        statuses[provider] = "configured" if any(credentials.get(name) for name in secret_names) else "missing"
    return MappingProxyType(statuses)


def redact_text(text: str, credentials: CredentialResolution) -> str:
    redacted = text
    for secret in credentials.secret_values():
        redacted = redacted.replace(secret, "[REDACTED]")
    redacted = URL_SECRET_RE.sub(lambda match: match.group(1) + "[REDACTED]", redacted)
    redacted = AUTH_HEADER_RE.sub(lambda match: match.group(1) + "[REDACTED]", redacted)
    return redacted
