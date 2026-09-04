#!/usr/bin/env python3
"""Fail closed when repository files contain credential-shaped material."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple


PREFIX_PATTERNS = (
    "gh" + r"[pousr]_[A-Za-z0-9]{20,}",
    "sk" + r"-[A-Za-z0-9]{20,}",
    "AK" + r"IA[0-9A-Z]{16}",
    "-----BEGIN " + r"(?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
)
PATTERNS = tuple(re.compile(pattern) for pattern in PREFIX_PATTERNS)
ASSIGNMENT = re.compile(
    r"(?i)(?:AMAP_WEBSERVICE_KEY|FLYAI_API_KEY|VARIFLIGHT_API_KEY|X_VARIFLIGHT_KEY|ANYSEARCH_API_KEY)\s*[=:]\s*[\"']?([^\s\"',}\]]{8,})"
)
PLACEHOLDERS = frozenset(("example", "placeholder", "replace-me", "redacted", "[redacted]", "changeme"))


def repository_files(root: Path) -> List[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
    return [root / item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def findings(paths: Sequence[Path]) -> List[Tuple[Path, int, str]]:
    found: List[Tuple[Path, int, str]] = []
    for path in paths:
        if not path.is_file():
            continue
        try:
            raw = path.read_bytes()
        except OSError as exc:
            found.append((path, 0, "unreadable: %s" % exc.__class__.__name__))
            continue
        if b"\x00" in raw:
            continue
        text = raw.decode("utf-8", errors="replace")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if any(pattern.search(line) for pattern in PATTERNS):
                found.append((path, line_number, "credential prefix"))
            assignment = ASSIGNMENT.search(line)
            if assignment and assignment.group(1).lower() not in PLACEHOLDERS:
                found.append((path, line_number, "secret variable assignment"))
    return found


def credential_value_hits_in_paths(paths: Sequence[Path], values: Sequence[str]) -> int:
    encoded_values = tuple(value.encode("utf-8") for value in values if value)
    hits = 0
    for path in paths:
        if not path.is_file():
            continue
        raw = path.read_bytes()
        hits += sum(raw.count(value) for value in encoded_values)
    return hits


def credential_value_hits_in_history(root: Path, values: Sequence[str]) -> int:
    encoded_values = tuple(value.encode("utf-8") for value in values if value)
    listed = subprocess.run(
        ["git", "rev-list", "--objects", "--all"],
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if listed.returncode != 0:
        raise RuntimeError(listed.stderr.decode("utf-8", errors="replace"))
    object_ids = sorted({line.split(None, 1)[0] for line in listed.stdout.splitlines() if line})
    batch = subprocess.run(
        ["git", "cat-file", "--batch"],
        cwd=str(root),
        input=b"\n".join(object_ids) + (b"\n" if object_ids else b""),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if batch.returncode != 0:
        raise RuntimeError(batch.stderr.decode("utf-8", errors="replace"))
    hits = 0
    output = batch.stdout
    offset = 0
    while offset < len(output):
        line_end = output.find(b"\n", offset)
        if line_end < 0:
            raise RuntimeError("git cat-file returned a truncated header")
        header = output[offset:line_end].split()
        if len(header) != 3:
            raise RuntimeError("git cat-file returned an invalid header")
        object_type = header[1]
        size = int(header[2])
        start = line_end + 1
        end = start + size
        if end > len(output):
            raise RuntimeError("git cat-file returned a truncated object")
        if object_type == b"blob":
            raw = output[start:end]
            hits += sum(raw.count(value) for value in encoded_values)
        offset = end + 1
    return hits


def credential_values(path: Path) -> Tuple[str, ...]:
    root = Path(__file__).resolve().parents[1]
    source = root / "plugins" / "china-trip-weaver" / "src"
    sys.path.insert(0, str(source))
    from china_trip_weaver.credentials import resolve_credentials

    return resolve_credentials({}, path).secret_values()


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser(description="Scan tracked and untracked repository files for secrets")
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--credential-values", action="store_true", help="scan exact local credential values without printing them")
    parser.add_argument("--credential-file", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--git-history", action="store_true", help="scan every Git object; requires --credential-values")
    args = parser.parse_args(list(argv) if argv else None)
    root = Path(__file__).resolve().parents[1]
    if args.git_history and not args.credential_values:
        parser.error("--git-history requires --credential-values")
    if args.credential_values:
        credential_path = args.credential_file or (Path.home() / ".config" / "china-trip-weaver" / "credentials.env")
        values = credential_values(credential_path)
        if args.git_history:
            count = credential_value_hits_in_history(root, values)
        else:
            paths = [path.resolve() for path in args.paths] if args.paths else repository_files(root)
            count = credential_value_hits_in_paths(paths, values)
        print("credential-value scan: %d finding(s)" % count)
        return 1 if count else 0
    paths = [path.resolve() for path in args.paths] if args.paths else repository_files(root)
    matches = findings(paths)
    for path, line, reason in matches:
        try:
            display = path.relative_to(root)
        except ValueError:
            display = path
        print("SECRET %s:%d %s" % (display, line, reason), file=sys.stderr)
    print("secret scan: %d finding(s) across %d file(s)" % (len(matches), len(paths)))
    return 1 if matches else 0


if __name__ == "__main__":
    raise SystemExit(main())
