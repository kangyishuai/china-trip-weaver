#!/usr/bin/env python3
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator


def json_files(target):
    path = Path(target)
    return sorted(path.rglob("*.json")) if path.is_dir() else [path]


def main():
    if len(sys.argv) < 3:
        print("usage: check_schema.py SCHEMA JSON_OR_DIR [...]", file=sys.stderr)
        return 2
    schema_path = Path(sys.argv[1])
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        print(f"FAIL {schema_path}: {exc}")
        return 2
    validator = Draft202012Validator(
        schema, format_checker=Draft202012Validator.FORMAT_CHECKER
    )
    failed = False
    for target in sys.argv[2:]:
        for path in json_files(target):
            try:
                instance = json.loads(path.read_text(encoding="utf-8"))
                errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
            except Exception as exc:
                errors = [exc]
            if errors:
                failed = True
                detail = getattr(errors[0], "message", str(errors[0]))
                print(f"FAIL {path}: {detail}")
            else:
                print(f"PASS {path}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
