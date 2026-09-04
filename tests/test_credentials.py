from __future__ import annotations

import contextlib
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "plugins" / "china-trip-weaver" / "src"
sys.path.insert(0, str(SRC))

from china_trip_weaver.credentials import (
    SECRET_NAMES,
    provider_credential_status,
    provider_environment,
    redact_text,
    resolve_credentials,
)
from china_trip_weaver.cli import main as cli_main
from china_trip_weaver.errors import CTWError


def canary(label: str) -> str:
    return "ctw-canary-" + label + "-not-a-real-secret"


def assignment(name: str, value: str) -> str:
    return name + "=" + value + "\n"


class CredentialTests(unittest.TestCase):
    def make_file(self, directory: Path, text: str, mode: int = 0o600) -> Path:
        path = directory / "secrets.input"
        path.write_text(text, encoding="utf-8")
        path.chmod(mode)
        return path

    def test_environment_overrides_file_per_name(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            text = assignment("AMAP_WEBSERVICE_KEY", canary("file-amap")) + assignment("FLYAI_API_KEY", canary("file-fly"))
            path = self.make_file(Path(temporary), text)
            result = resolve_credentials({"AMAP_WEBSERVICE_KEY": canary("env-amap")}, path)
            self.assertEqual(canary("env-amap"), result.get("AMAP_WEBSERVICE_KEY"))
            self.assertEqual(canary("file-fly"), result.get("FLYAI_API_KEY"))
            self.assertNotIn(canary("env-amap"), repr(result))

    def test_missing_file_is_keyless_not_error(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            result = resolve_credentials({}, Path(temporary) / "missing")
            self.assertEqual(set(SECRET_NAMES), {name for name, state in result.status().items() if state == "missing"})

    def test_unknown_names_warn_and_are_not_forwarded(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            path = self.make_file(Path(temporary), "UNRELATED_TOKEN=%s\n" % canary("other"))
            result = resolve_credentials({}, path)
            self.assertEqual(1, len(result.warnings))
            self.assertNotIn("UNRELATED_TOKEN", provider_environment("amap", result, {}))

    def test_unsafe_mode_is_rejected(self):
        if os.name != "posix":
            return
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            path = self.make_file(Path(temporary), assignment("AMAP_WEBSERVICE_KEY", canary("amap")), 0o644)
            with self.assertRaises(CTWError) as raised:
                resolve_credentials({}, path)
            self.assertEqual("CREDENTIAL_FILE_MODE", raised.exception.code)

    def test_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            folder = Path(temporary)
            target = self.make_file(folder, assignment("AMAP_WEBSERVICE_KEY", canary("amap")))
            link = folder / "link.input"
            link.symlink_to(target)
            with self.assertRaises(CTWError) as raised:
                resolve_credentials({}, link)
            self.assertEqual("CREDENTIAL_FILE_TYPE", raised.exception.code)

    def test_non_owner_is_rejected(self):
        if os.name != "posix":
            return
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            path = self.make_file(Path(temporary), assignment("AMAP_WEBSERVICE_KEY", canary("amap")))
            fake_stat = SimpleNamespace(
                st_mode=stat.S_IFREG | 0o600,
                st_uid=os.getuid() + 1,
                st_size=path.stat().st_size,
            )
            with mock.patch.object(Path, "lstat", return_value=fake_stat):
                with self.assertRaises(CTWError) as raised:
                    resolve_credentials({}, path)
            self.assertEqual("CREDENTIAL_FILE_OWNER", raised.exception.code)

    def test_shell_syntax_and_duplicate_names_are_rejected(self):
        cases = (
            "export " + assignment("AMAP_WEBSERVICE_KEY", "value"),
            assignment("AMAP_WEBSERVICE_KEY", "firstvalue") + assignment("AMAP_WEBSERVICE_KEY", "secondvalue"),
            "not an assignment\n",
        )
        for text in cases:
            with self.subTest(text=text), tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
                path = self.make_file(Path(temporary), text)
                with self.assertRaises(CTWError):
                    resolve_credentials({}, path)

    def test_each_provider_receives_only_its_credential(self):
        values = {name: canary(name.lower()) for name in SECRET_NAMES}
        values["VARIFLIGHT_API_URL"] = "https://example.invalid/api"
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            result = resolve_credentials(values, Path(temporary) / "missing")
            amap = provider_environment("amap", result, {"PATH": "/bin", "FLYAI_API_KEY": canary("leak")})
            flyai = provider_environment("flyai", result, {"PATH": "/bin"})
            vari = provider_environment("variflight", result, {"PATH": "/bin"})
            self.assertEqual({"PATH", "AMAP_WEBSERVICE_KEY"}, set(amap))
            self.assertEqual({"PATH", "FLYAI_API_KEY"}, set(flyai))
            self.assertEqual({"PATH", "VARIFLIGHT_API_KEY", "VARIFLIGHT_API_URL"}, set(vari))
            for provider in ("rail12306", "host_web", "scheduler", "renderer"):
                self.assertEqual({"PATH": "/bin"}, provider_environment(provider, result, {"PATH": "/bin"}))

    def test_provider_statuses_are_names_only(self):
        values = {
            "AMAP_WEBSERVICE_KEY": canary("amap"),
            "VARIFLIGHT_API_KEY": canary("variflight"),
        }
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            result = resolve_credentials(values, Path(temporary) / "missing")
        self.assertEqual({
            "amap": "configured",
            "flyai": "missing",
            "variflight": "configured",
            "anysearch": "missing",
        }, dict(provider_credential_status(result)))

    def test_doctor_reports_statuses_and_rejects_unsafe_file_without_values(self):
        if os.name != "posix":
            return
        amap = canary("doctor-amap")
        flyai = canary("doctor-flyai")
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            path = self.make_file(
                Path(temporary),
                assignment("AMAP_WEBSERVICE_KEY", amap) + assignment("FLYAI_API_KEY", flyai),
            )
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(0, cli_main(["doctor"], credential_path=path))
            payload = json.loads(stdout.getvalue())
            self.assertEqual("configured", payload["providers"]["amap"])
            self.assertEqual("configured", payload["providers"]["flyai"])
            self.assertEqual("missing", payload["providers"]["variflight"])
            self.assertNotIn(amap, stdout.getvalue())
            self.assertNotIn(flyai, stdout.getvalue())

            path.chmod(0o644)
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(1, cli_main(["doctor"], credential_path=path))
            error = json.loads(stderr.getvalue())
            self.assertEqual("forbidden", error["credential_error"]["status"])
            self.assertEqual("CREDENTIAL_FILE_MODE", error["credential_error"]["code"])
            self.assertNotIn(amap, stderr.getvalue())
            self.assertNotIn(flyai, stderr.getvalue())

            path.chmod(0o600)
            restored = io.StringIO()
            with contextlib.redirect_stdout(restored):
                self.assertEqual(0, cli_main(["doctor"], credential_path=path))
            self.assertEqual("configured", json.loads(restored.getvalue())["providers"]["amap"])

    def test_compatibility_variflight_key_only_used_without_canonical(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            path = Path(temporary) / "missing"
            canonical = resolve_credentials({"VARIFLIGHT_API_KEY": canary("canonical"), "X_VARIFLIGHT_KEY": canary("compat")}, path)
            compat = resolve_credentials({"X_VARIFLIGHT_KEY": canary("compat")}, path)
            self.assertIsNone(canonical.get("X_VARIFLIGHT_KEY"))
            self.assertEqual(canary("compat"), compat.get("X_VARIFLIGHT_KEY"))

    def test_redaction_covers_values_urls_and_authorization(self):
        value = canary("amap")
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            result = resolve_credentials({"AMAP_WEBSERVICE_KEY": value}, Path(temporary) / "missing")
            raw = "value=%s https://example.invalid/?key=%s\nAuthorization: Bearer %s" % (value, value, value)
            cleaned = redact_text(raw, result)
            self.assertNotIn(value, cleaned)
            self.assertEqual(3, cleaned.count("[REDACTED]"))

    def test_secret_scanner_detects_canary_without_echoing_it(self):
        scanner = ROOT / "scripts" / "scan_secrets.py"
        value = "gh" + "p_" + "0" * 30
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            log = Path(temporary) / "provider.log"
            log.write_text("provider stderr " + value + "\n", encoding="utf-8")
            result = subprocess.run([sys.executable, str(scanner), str(log)], text=True, capture_output=True)
            self.assertEqual(1, result.returncode)
            self.assertIn("credential prefix", result.stderr)
            self.assertNotIn(value, result.stdout + result.stderr)

    def test_exact_credential_value_mode_prints_only_hit_count(self):
        scanner = ROOT / "scripts" / "scan_secrets.py"
        value = canary("exact-value-scan")
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            folder = Path(temporary)
            credential_file = self.make_file(folder, assignment("AMAP_WEBSERVICE_KEY", value))
            target = folder / "artifact.txt"
            target.write_text("opaque=" + value + "\n", encoding="utf-8")
            hit = subprocess.run(
                [
                    sys.executable,
                    str(scanner),
                    "--credential-values",
                    "--credential-file",
                    str(credential_file),
                    str(target),
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(1, hit.returncode)
            self.assertEqual("credential-value scan: 1 finding(s)\n", hit.stdout)
            self.assertEqual("", hit.stderr)
            self.assertNotIn(value, hit.stdout + hit.stderr)
            self.assertNotIn("AMAP_WEBSERVICE_KEY", hit.stdout + hit.stderr)

            target.write_text("clean\n", encoding="utf-8")
            clean = subprocess.run(
                [
                    sys.executable,
                    str(scanner),
                    "--credential-values",
                    "--credential-file",
                    str(credential_file),
                    str(target),
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(0, clean.returncode)
            self.assertEqual("credential-value scan: 0 finding(s)\n", clean.stdout)


if __name__ == "__main__":
    unittest.main()
