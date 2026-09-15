#!/usr/bin/env python3
"""One-shot coverage measurement for the full test suite, in a throwaway venv.

Why this exists: the only interpreter on a contributor's machine that may
already have `coverage` installed is often a general-purpose environment
shared across unrelated projects. If a third-party package in that shared
environment's site-packages happens to ship its own top-level `tests`
package, it silently shadows this repository's `tests/` (a PEP 420
namespace package) for every interpreter that has it on sys.path.
`unittest discover -s tests` then finds and runs only whichever test modules
survive that shadowing -- with no error, no non-zero exit, and no visible
sign that anything is wrong. A coverage percentage measured that way is not
just imprecise, it is measuring the wrong test run entirely.

This script never installs anything into, or otherwise touches, a
pre-existing interpreter. It builds a fresh, disposable virtualenv from a
fixed system interpreter, wires up the documented coverage.py recipe for
measuring subprocesses (the suite has ~80 `subprocess.run([ctw, ...])`
calls that shell out to the real CLI, each a fresh process that plain
`coverage run` never sees), runs the full suite inside that venv, and
refuses to print a single coverage number unless it can first prove that
every test module on disk actually ran.

Usage:
    /usr/bin/python3 scripts/measure_coverage.py

Everything this script writes (the venv, coverage data files, the report)
lives under .tmp/coverage-measurement/, which is gitignored.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple


ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = ROOT / "tests"
SRC_DIR = ROOT / "plugins" / "china-trip-weaver" / "src"
SCRATCH_DIR = ROOT / ".tmp" / "coverage-measurement"
VENV_DIR = SCRATCH_DIR / "venv"
DATA_DIR = SCRATCH_DIR / "data"
COVERAGERC = SCRATCH_DIR / "coveragerc.ini"

SYSTEM_PYTHON = "/usr/bin/python3"
MIN_EXPECTED_TESTS = 685


def log(message: str) -> None:
    print("[measure_coverage] %s" % message, file=sys.stderr)


def discovered_test_modules() -> List[str]:
    return sorted("tests." + path.stem for path in TESTS_DIR.glob("test_*.py"))


def run(cmd: List[str], **kwargs) -> subprocess.CompletedProcess:
    log("+ " + " ".join(str(part) for part in cmd))
    return subprocess.run(cmd, check=True, **kwargs)


def build_isolated_venv() -> Path:
    if VENV_DIR.exists():
        shutil.rmtree(VENV_DIR)
    log("building an isolated venv from %s (never a pre-existing interpreter)" % SYSTEM_PYTHON)
    run([SYSTEM_PYTHON, "-m", "venv", str(VENV_DIR)])
    python_bin = VENV_DIR / "bin" / "python3"
    run([str(python_bin), "-m", "pip", "install", "--quiet", "coverage", "pyyaml"])
    return python_bin


def site_packages_of(python_bin: Path) -> Path:
    result = subprocess.run(
        [str(python_bin), "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
        check=True, capture_output=True, text=True,
    )
    return Path(result.stdout.strip())


def write_subprocess_hook(python_bin: Path) -> None:
    """Install coverage.py's documented subprocess-measurement recipe.

    A sitecustomize.py in the venv's own site-packages starts coverage for
    any process that imports site at startup (i.e. every plain `python3`
    invocation) whenever COVERAGE_PROCESS_START is set in its environment.
    This is what lets the ~80 `subprocess.run([str(CTW), ...])` calls in the
    test suite -- each a brand-new process, invoked via the `ctw` launcher's
    `#!/usr/bin/env python3` shebang -- be measured at all.
    """
    site_packages = site_packages_of(python_bin)
    (site_packages / "sitecustomize.py").write_text(
        "import coverage\ncoverage.process_startup()\n", encoding="utf-8",
    )


def write_coveragerc() -> None:
    COVERAGERC.write_text(
        "\n".join([
            "[run]",
            "parallel = True",
            "relative_files = True",
            "source = %s" % SRC_DIR,
            "data_file = %s" % (DATA_DIR / ".coverage"),
            "",
        ]),
        encoding="utf-8",
    )


def run_suite(python_bin: Path, *, with_subprocess_hook: bool) -> subprocess.CompletedProcess:
    if DATA_DIR.exists():
        shutil.rmtree(DATA_DIR)
    DATA_DIR.mkdir(parents=True)
    write_coveragerc()
    if with_subprocess_hook:
        write_subprocess_hook(python_bin)
    env = dict(os.environ)
    env["COVERAGE_PROCESS_START"] = str(COVERAGERC)
    # Puts this interpreter first on PATH so `env python3` (the `ctw`
    # launcher's shebang) resolves to it instead of whatever `python3` the
    # caller's shell already had -- required for the sitecustomize.py hook
    # above to ever run inside those subprocesses.
    env["PATH"] = str(python_bin.parent) + os.pathsep + env.get("PATH", "")
    log("running the full suite under coverage (several minutes) ...")
    return subprocess.run(
        [
            str(python_bin), "-m", "coverage", "run", "--rcfile", str(COVERAGERC),
            "-m", "unittest", "discover", "-s", "tests", "-v",
        ],
        cwd=ROOT, env=env, capture_output=True, text=True,
    )


def parse_unittest_output(output: str) -> Tuple[int, bool, int, List[str]]:
    total_match = re.search(r"^Ran (\d+) tests? in [\d.]+s", output, re.MULTILINE)
    total = int(total_match.group(1)) if total_match else 0
    ok = bool(re.search(r"^OK\s*$", output, re.MULTILINE))
    skipped_match = re.search(r"skipped=(\d+)", output)
    skipped = int(skipped_match.group(1)) if skipped_match else 0
    # `unittest discover -s tests` has no tests/__init__.py to anchor a
    # package, so `-t` (top_level_dir) defaults to `-s` itself and every
    # verbose result line names its module as bare `test_x`, never the
    # qualified `tests.test_x` -- confirmed by running discover -v directly
    # and comparing against `-m unittest tests.test_x`, which does qualify.
    modules_seen = {
        "tests." + name if not name.startswith("tests.") else name
        for name in re.findall(r"\(((?:tests\.)?test_[A-Za-z0-9_]+)\.", output)
    }
    missing = sorted(set(discovered_test_modules()) - modules_seen)
    return total, ok, skipped, missing


def assert_full_run(result: subprocess.CompletedProcess) -> None:
    """The one job this script cannot get wrong: refuse to lie.

    A silent-shadowing failure looks exactly like a healthy run from the
    outside (exit code aside, which callers of `unittest discover` rarely
    check against a specific number). The only reliable signal is checking,
    by name, that every test module this repository ships actually reported
    at least one test result -- not just that *some* run finished.
    """
    output = result.stdout + result.stderr
    log_path = SCRATCH_DIR / "last_run.log"
    log_path.write_text(output, encoding="utf-8")
    log("full captured test output written to %s" % log_path)
    total, ok, skipped, missing = parse_unittest_output(output)
    expected = discovered_test_modules()
    problems = []
    if total < MIN_EXPECTED_TESTS:
        problems.append("only %d tests ran (need >= %d)" % (total, MIN_EXPECTED_TESTS))
    if not ok:
        problems.append("the test run did not report OK")
    if skipped:
        problems.append("%d test(s) were skipped (must be 0)" % skipped)
    if missing:
        problems.append(
            "%d test module(s) on disk never reported a single result "
            "(import/discovery failure -- likely a site-packages 'tests' "
            "package shadowing this repo's tests/ namespace package): %s"
            % (len(missing), ", ".join(missing))
        )
    if problems:
        log("REFUSING TO REPORT COVERAGE -- this run did not exercise the real suite:")
        for problem in problems:
            log("  - %s" % problem)
        log("---- tail of captured test output ----")
        log(output[-4000:])
        raise SystemExit(1)
    log("confirmed: all %d test modules ran, %d tests total, 0 skipped, OK" % (len(expected), total))


def combine_and_report(python_bin: Path) -> str:
    run(
        [str(python_bin), "-m", "coverage", "combine", "--rcfile", str(COVERAGERC)],
        cwd=ROOT, capture_output=True, text=True,
    )
    report = run(
        [
            str(python_bin), "-m", "coverage", "report", "--rcfile", str(COVERAGERC),
            "--include", "plugins/china-trip-weaver/src/*",
        ],
        cwd=ROOT, capture_output=True, text=True,
    )
    print(report.stdout)
    for line in report.stdout.splitlines():
        if line.startswith("TOTAL") or "cli.py" in line:
            log("HEADLINE: %s" % line)
    return report.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--force-interpreter", default=None, metavar="PYTHON",
        help=(
            "DEBUG / REVERSE-VERIFICATION ONLY. Skip venv isolation entirely and "
            "run the suite directly with this interpreter (it must already have "
            "coverage installed; nothing is installed into it and its "
            "site-packages is never written to). Exists only to demonstrate that "
            "assert_full_run() actually fires against a known-bad interpreter -- "
            "never use this flag to produce a real measurement."
        ),
    )
    args = parser.parse_args()

    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)

    if args.force_interpreter:
        log("!!! --force-interpreter is set: using %s directly, no isolation, no install !!!" % args.force_interpreter)
        python_bin = Path(args.force_interpreter)
        result = run_suite(python_bin, with_subprocess_hook=False)
        assert_full_run(result)
        combine_and_report(python_bin)
        return 0

    python_bin = build_isolated_venv()
    result = run_suite(python_bin, with_subprocess_hook=True)
    assert_full_run(result)
    combine_and_report(python_bin)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
