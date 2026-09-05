from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "china-trip-weaver"
SRC = PLUGIN / "src"
sys.path.insert(0, str(SRC))

from china_trip_weaver import __version__


CODEX_HOME = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
PLUGIN_VALIDATOR = CODEX_HOME / "skills/.system/plugin-creator/scripts/validate_plugin.py"

EXPECTED_MANIFEST = {
    "name": "china-trip-weaver",
    "version": "0.5.0",
    "description": "Evidence-backed, read-only planning for 1-7 day trips within mainland China, with provider degradation, local replanning, and deterministic mobile HTML.",
    "author": {"name": "kangyishuai"},
    "license": "MIT",
    "homepage": "https://github.com/kangyishuai/china-trip-weaver",
    "repository": "https://github.com/kangyishuai/china-trip-weaver",
    "keywords": ["china-travel", "itinerary", "12306", "amap", "evidence", "replanning"],
    "skills": "./skills/",
    "mcpServers": "./.mcp.json",
    "interface": {
        "displayName": "China Trip Weaver",
        "shortDescription": "Evidence-backed China trip planning",
        "longDescription": "Plan and locally replan short mainland-China trips with explicit sources, provider health, price types, and a deterministic mobile itinerary.",
        "developerName": "kangyishuai",
        "category": "Productivity",
        "capabilities": ["trip planning", "provider comparison", "local replanning", "mobile HTML"],
        "defaultPrompt": [
            "Plan a three-day China trip with sources and explicit unknowns.",
            "Replan only the affected part of this itinerary.",
            "Render this validated Trip as a mobile HTML file.",
        ],
        "brandColor": "#C94F36",
        "websiteURL": "https://github.com/kangyishuai/china-trip-weaver",
    },
}


class PackagingTests(unittest.TestCase):
    def test_plugin_manifest_is_exact_and_version_matches_package(self):
        manifest = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(EXPECTED_MANIFEST, manifest)
        self.assertEqual(__version__, manifest["version"])
        self.assertEqual(["plugin.json"], sorted(path.name for path in (PLUGIN / ".codex-plugin").iterdir()))

    def test_mcp_config_has_exact_pins_and_names_not_values(self):
        config = json.loads((PLUGIN / ".mcp.json").read_text(encoding="utf-8"))
        self.assertEqual({"china-rail", "variflight"}, set(config["mcpServers"]))
        self.assertEqual(["-y", "12306-mcp@0.3.10"], config["mcpServers"]["china-rail"]["args"])
        self.assertEqual(["-y", "@variflight-ai/variflight-mcp@1.0.3"], config["mcpServers"]["variflight"]["args"])
        self.assertEqual(["VARIFLIGHT_API_KEY", "X_VARIFLIGHT_KEY", "VARIFLIGHT_API_URL"], config["mcpServers"]["variflight"]["env_vars"])
        self.assertNotIn("env", config["mcpServers"]["variflight"])

    def test_marketplace_entry_is_exact_and_resolves_from_root(self):
        marketplace = json.loads((ROOT / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8"))
        expected = {
            "name": "china-trip-weaver-local",
            "interface": {"displayName": "China Trip Weaver Local"},
            "plugins": [{
                "name": "china-trip-weaver",
                "source": {"source": "local", "path": "./plugins/china-trip-weaver"},
                "policy": {"installation": "AVAILABLE", "authentication": "ON_USE"},
                "category": "Productivity",
            }],
        }
        self.assertEqual(expected, marketplace)
        self.assertEqual(PLUGIN.resolve(), (ROOT / marketplace["plugins"][0]["source"]["path"]).resolve())

    def test_runtime_entry_is_executable_and_cwd_independent(self):
        entry = PLUGIN / "scripts" / "ctw"
        self.assertTrue(os.access(entry, os.X_OK))
        result = subprocess.run([str(entry), "doctor"], cwd="/", text=True, capture_output=True)
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("0.5.0", payload["plugin_version"])
        self.assertTrue(payload["schema_exists"])

    def test_package_contains_required_contracts_and_notices(self):
        required = (
            PLUGIN / "schema" / "trip.schema.json",
            PLUGIN / "schema" / "candidates.schema.json",
            PLUGIN / "assets" / "renderer.css",
            PLUGIN / "references" / "credentials.md",
            PLUGIN / "references" / "provider-contracts.md",
            PLUGIN / "references" / "candidates.example.json",
            ROOT / "THIRD_PARTY_NOTICES.md",
            ROOT / "BLOCKED.md",
        )
        for path in required:
            self.assertTrue(path.is_file(), path)
        self.assertEqual((ROOT / "docs/design/schema/trip.schema.json").read_bytes(), (PLUGIN / "schema/trip.schema.json").read_bytes())

    def test_no_forbidden_plugin_components_or_build_residue(self):
        self.assertFalse((PLUGIN / ".app.json").exists())
        self.assertFalse((PLUGIN / "hooks.json").exists())
        def git_ls_files(*arguments: str) -> list[Path]:
            output = subprocess.run(
                ["git", "ls-files", *arguments, "-z"],
                cwd=ROOT,
                check=True,
                capture_output=True,
            ).stdout
            return [Path(os.fsdecode(raw_path)) for raw_path in output.split(b"\0") if raw_path]

        repository_paths = git_ls_files("--cached", "--others", "--exclude-standard")
        # Collapse wholly ignored trees at their first boundary, while still surfacing
        # a forbidden name that is itself the ignored boundary.
        ignored_boundaries = git_ls_files("--others", "--ignored", "--exclude-standard", "--directory")
        forbidden = [
            path
            for path in repository_paths + ignored_boundaries
            if any(name in ("node_modules", "credentials.env") or Path(name).suffix == ".env" for name in path.parts)
        ]
        self.assertEqual([], forbidden)
        placeholders = [path for path in PLUGIN.rglob("*") if path.is_file() and "[TODO:" in path.read_text(encoding="utf-8", errors="ignore")]
        self.assertEqual([], placeholders)

    def test_plugin_passes_bundled_validator(self):
        if not PLUGIN_VALIDATOR.is_file():
            self.skipTest("Codex bundled plugin validator is not installed on this machine")
        result = subprocess.run([sys.executable, str(PLUGIN_VALIDATOR), str(PLUGIN)], text=True, capture_output=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
