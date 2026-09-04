"""Detect Skill-name collisions between this plugin and other enabled plugins.

Codex does not merge Skills that share a name, so two enabled plugins exposing
`plan-china-trip` both reach the selector and the user cannot tell them apart.
`codex plugin list --json` reports every installed plugin with its enabled flag
and its on-disk source path, which is enough to find the collision before any
provider is called.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple


PLUGIN_NAME = "china-trip-weaver"

DESKTOP_CLI = Path("/Applications/ChatGPT.app/Contents/Resources/codex")

NOTICE = (
    "检测到另一个同名 Skill。Codex 不会合并同名 Skill，两个入口会同时出现在选择器里。"
    "请先在 Plugins Directory 中禁用或卸载其中一个，然后新建会话再试；当前未运行任何行程查询。"
)


def codex_executable() -> Optional[Path]:
    """Locate a Codex CLI: explicit override, then PATH, then the desktop app."""
    override = os.environ.get("CODEX_BIN")
    if override:
        candidate = Path(override)
        return candidate if candidate.is_file() else None
    found = shutil.which("codex")
    if found:
        return Path(found)
    return DESKTOP_CLI if DESKTOP_CLI.is_file() else None


def plugin_listing(executable: Path, timeout_seconds: float = 30.0) -> Mapping[str, Any]:
    """Return the parsed `codex plugin list --json` document."""
    result = subprocess.run(
        [str(executable), "plugin", "list", "--json"],
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    if result.returncode != 0:
        raise RuntimeError("codex plugin list --json exited %d" % result.returncode)
    return json.loads(result.stdout)


def skill_names(plugin_root: Path) -> Tuple[str, ...]:
    """Names of the Skills a plugin directory exposes."""
    skills = plugin_root / "skills"
    if not skills.is_dir():
        return ()
    return tuple(sorted(
        entry.name for entry in skills.iterdir()
        if entry.is_dir() and (entry / "SKILL.md").is_file()
    ))


def find_conflicts(listing: Mapping[str, Any], plugin_name: str = PLUGIN_NAME) -> Dict[str, Sequence[str]]:
    """Map each Skill name this plugin shares with another enabled plugin.

    Only enabled, installed plugins can reach the selector, so a disabled
    conflicting plugin is correctly not reported.
    """
    owners: Dict[str, list] = {}
    for entry in listing.get("installed", ()):
        if not entry.get("enabled") or not entry.get("installed"):
            continue
        source = entry.get("source") or {}
        path = source.get("path")
        if not path:
            continue
        for name in skill_names(Path(path)):
            owners.setdefault(name, []).append(entry.get("pluginId") or entry.get("name") or path)
    conflicts = {}
    for skill, plugin_ids in owners.items():
        mine = [item for item in plugin_ids if item.split("@")[0] == plugin_name]
        others = [item for item in plugin_ids if item.split("@")[0] != plugin_name]
        if mine and others:
            conflicts[skill] = tuple(sorted(others))
    return conflicts


def conflict_report(timeout_seconds: float = 30.0) -> Dict[str, Any]:
    """Machine-readable conflict status for `ctw doctor`.

    `status` is `clear` when no enabled plugin shares a Skill name, `conflict`
    when one does, and `unknown` when no Codex CLI could be consulted. `unknown`
    must be treated as fail-closed by the caller, not as clear.
    """
    executable = codex_executable()
    if executable is None:
        return {"status": "unknown", "reason": "no Codex CLI found; set CODEX_BIN", "conflicts": {}}
    try:
        listing = plugin_listing(executable, timeout_seconds)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        return {"status": "unknown", "reason": exc.__class__.__name__, "conflicts": {}}
    conflicts = find_conflicts(listing)
    if conflicts:
        return {
            "status": "conflict",
            "conflicts": {name: list(owners) for name, owners in sorted(conflicts.items())},
            "notice": NOTICE,
        }
    return {"status": "clear", "conflicts": {}}
