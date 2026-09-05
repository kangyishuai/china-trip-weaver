from __future__ import annotations

import json
import re
import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "plugins" / "china-trip-weaver" / "skills"
CODEX_HOME = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
VALIDATOR = CODEX_HOME / "skills/.system/skill-creator/scripts/quick_validate.py"
PLUGIN = ROOT / "plugins" / "china-trip-weaver"
INSTALLER = ROOT / "scripts" / "install_local_plugin.sh"

DESCRIPTIONS = {
    "plan-china-trip": "Plan, compare, or locally replan a read-only trip or multi-Trip Journey within mainland China. Use when the user asks for a China itinerary of any length, a city weekend, cross-city transport and lodging choices, an executable day schedule, a disruption-aware revision, or a sourced mobile Trip or Journey overview. Orchestrate the plugin's explicit-only research, provider, scheduling, replanning, and rendering Skills; never book, log in, submit identity, pay, cancel, or change an order.",
    "research-china-destination": "Build date-bound destination and POI claims for a mainland-China city from authoritative web sources and user-pasted notes. Invoke explicitly from plan-china-trip when candidate places, current events, opening information, seasonal constraints, food, or local cautions are missing; do not create or render a full itinerary.",
    "search-china-rail": "Normalize read-only China Railway station, schedule, seat, fare, direct, transfer, and route-stop results from the pinned 12306 MCP. Invoke explicitly from plan-china-trip for a dated rail leg or rail alternative; never log in, hold, purchase, pay, cancel, or change a ticket.",
    "search-china-air": "Normalize dated mainland-China flight candidates and booking deep links from the pinned FlyAI CLI, with optional VariFlight status, comfort, weather, and price enrichment. Invoke explicitly from plan-china-trip for a flight leg or flight-versus-rail comparison; do not transact or present an untyped price.",
    "search-china-lodging": "Produce dated mainland-China lodging areas, candidate properties, verifiable conditions, and deep links from the pinned FlyAI CLI or explicit degradation. Invoke explicitly from plan-china-trip when overnight stays are required; never claim room-level inventory, tax, cancellation, or total price unless the corresponding claim is verified.",
    "resolve-china-mobility": "Resolve mainland-China POIs, geocodes, coordinate provenance, and walking, transit, driving, or cycling route-time matrix cells through the AMap adapter. Invoke explicitly from plan-china-trip after candidates exist or when affected hops need revalidation; do not schedule a trip or treat straight lines as routes.",
    "schedule-china-trip": "Create or validate deterministic day slots from a schema-valid Trip, a route-time matrix, opening windows, dwell times, buffers, and locks. Invoke explicitly from plan-china-trip after evidence collection; return a feasible schedule or a structured no-solution result, never silently drop a hard constraint.",
    "replan-china-trip": "Apply a versioned local patch to a schema-valid Trip after a disruption or user edit. Invoke explicitly from plan-china-trip with the current revision, event, locks, and affected scope; preserve unrelated days and accepted or booked items byte-for-byte and list every claim that must be reverified.",
    "render-china-trip": "Render a schema-valid Trip as the single deterministic, phone-first HTML artifact and validate its structure, security, accessibility, and offline core. Invoke explicitly from plan-china-trip only after Trip validation; never research, reschedule, alter facts, or embed credentials.",
}


def frontmatter(path: Path):
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        raise AssertionError("missing frontmatter")
    end = lines.index("---", 1)
    result = {}
    for line in lines[1:end]:
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip().strip('"')
    return result


class SkillPackagingTests(unittest.TestCase):
    def test_exact_nine_skill_names_and_descriptions(self):
        actual = {path.name for path in SKILLS.iterdir() if path.is_dir()}
        self.assertEqual(set(DESCRIPTIONS), actual)
        for name, description in DESCRIPTIONS.items():
            values = frontmatter(SKILLS / name / "SKILL.md")
            self.assertEqual(name, values["name"])
            self.assertEqual(description, values["description"])

    def test_only_main_skill_is_implicit(self):
        policies = {}
        for name in DESCRIPTIONS:
            text = (SKILLS / name / "agents" / "openai.yaml").read_text(encoding="utf-8")
            match = re.search(r"allow_implicit_invocation:\s*(true|false)", text)
            self.assertIsNotNone(match, name)
            policies[name] = match.group(1) == "true"
        self.assertEqual(["plan-china-trip"], [name for name, implicit in policies.items() if implicit])

    def test_ui_metadata_has_scannable_description_and_explicit_default_prompt(self):
        for name in DESCRIPTIONS:
            text = (SKILLS / name / "agents" / "openai.yaml").read_text(encoding="utf-8")
            short = re.search(r'short_description:\s*"([^"]+)"', text)
            prompt = re.search(r'default_prompt:\s*"([^"]+)"', text)
            self.assertIsNotNone(short, name)
            self.assertGreaterEqual(len(short.group(1)), 25)
            self.assertLessEqual(len(short.group(1)), 64)
            self.assertIsNotNone(prompt, name)
            self.assertIn("$" + name, prompt.group(1))

    def test_main_routes_only_to_renamed_explicit_children(self):
        body = (SKILLS / "plan-china-trip" / "SKILL.md").read_text(encoding="utf-8")
        for name in set(DESCRIPTIONS) - {"plan-china-trip"}:
            self.assertIn("$" + name, body)
        self.assertNotIn("search-china-trains", body)
        self.assertNotIn("search-china-flights", body)

    def test_every_explicit_child_references_a_real_ctw_command(self):
        for name in set(DESCRIPTIONS) - {"plan-china-trip"}:
            body = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("scripts/ctw ", body, name)
        main = (SKILLS / "plan-china-trip" / "SKILL.md").read_text(encoding="utf-8")
        for command in ("validate-candidates", "plan", "validate", "validate-html", "replan"):
            self.assertIn("scripts/ctw " + command, main)

    def test_no_scaffold_placeholders_or_chat_key_request(self):
        combined = "\n".join(path.read_text(encoding="utf-8") for path in SKILLS.rglob("*.*") if path.is_file())
        self.assertNotIn("[TODO:", combined)
        self.assertNotRegex(combined.lower(), r"paste (?:your )?(?:api )?key")

    def test_destination_research_contract_uses_host_first_then_anysearch_fallback(self):
        body = (SKILLS / "research-china-destination" / "SKILL.md").read_text(encoding="utf-8")
        host = "Use the host's built-in network search first."
        fallback = "fall back to AnySearch with an already configured key"
        degraded = "use only material the user already pasted, mark destination research `degraded`"
        self.assertIn(host, body)
        self.assertIn(fallback, body)
        self.assertIn(degraded, body)
        self.assertLess(body.index(host), body.index(fallback))
        self.assertLess(body.index(fallback), body.index(degraded))
        for rung in ("host-web", "anysearch", "user-pasted-only"):
            self.assertIn(rung, body)

    def test_downstream_skills_preserve_or_do_not_substitute_search_rung(self):
        expectations = {
            "render-china-trip": "destination-search rung",
            "replan-china-trip": "destination-search rung",
            "resolve-china-mobility": "destination-search rung",
            "schedule-china-trip": "destination-search rung",
            "search-china-rail": "destination-search rung",
        }
        for name, phrase in expectations.items():
            with self.subTest(name=name):
                body = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
                self.assertIn(phrase, body)

    def test_manifest_uses_repository_website_without_invented_legal_urls(self):
        manifest = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        interface = manifest["interface"]
        self.assertEqual("0.6.0", manifest["version"])
        self.assertEqual("https://github.com/kangyishuai/china-trip-weaver", interface["websiteURL"])
        self.assertNotIn("privacyPolicyURL", interface)
        self.assertNotIn("termsOfServiceURL", interface)

    def test_codex_skill_parser_smoke_runs_standalone(self):
        result = subprocess.run([str(INSTALLER), "--skill-smoke"], text=True, capture_output=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("SKILL parser smoke: OK (9 SKILL.md via codex debug prompt-input)", result.stdout)

    def test_all_skills_pass_bundled_validator(self):
        if not VALIDATOR.is_file():
            self.skipTest("Codex bundled skill validator is not installed on this machine")
        for name in DESCRIPTIONS:
            result = subprocess.run([sys.executable, str(VALIDATOR), str(SKILLS / name)], text=True, capture_output=True)
            self.assertEqual(0, result.returncode, name + "\n" + result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
