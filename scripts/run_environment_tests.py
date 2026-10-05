from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_TESTS = [
    ROOT / "breakingweb/tests/test_gmail_feature_support.py",
    ROOT / "breakingweb/tests/test_gmail_mailbox_contract.py",
]
LOCAL_NODE_CANDIDATES = sorted(
    (ROOT / ".tools").glob("node-v*/bin/node"),
    reverse=True,
)
NODE_CANDIDATES = [
    os.environ.get("BREAKINGWEB_NODE", os.environ.get("WEBSTRESS_NODE")),
    *map(str, LOCAL_NODE_CANDIDATES),
    shutil.which("node"),
    str(Path.home() / ".lmstudio/.internal/utils/node"),
]
PYTHON_CANDIDATES = [
    sys.executable,
    str(Path.home() / "miniconda3/bin/python3.13"),
    shutil.which("python3"),
]
VITEST_BIN = ROOT / "breakingweb/environments/node_modules/.pnpm/node_modules/.bin/vitest"
VITEST_ENTRY = ROOT / "breakingweb/environments/node_modules/.pnpm/node_modules/vitest/vitest.mjs"
GMAIL_VITEST_CONFIG = ROOT / "breakingweb/environments/gmail/vitest.config.ts"


def _is_executable(path: str | None) -> bool:
    return bool(path) and Path(path).exists() and os.access(path, os.X_OK)


def _find_pytest_python() -> str | None:
    for candidate in PYTHON_CANDIDATES:
        if not _is_executable(candidate):
            continue
        probe = subprocess.run(
            [candidate, "-c", "import pytest"],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        if probe.returncode == 0:
            return candidate
    return None


def _find_frontend_runner() -> tuple[str, str] | None:
    if not VITEST_ENTRY.exists():
        return None
    for candidate in NODE_CANDIDATES:
        if _is_executable(candidate):
            return candidate, str(VITEST_ENTRY)
    return None


def _run(label: str, command: list[str], cwd: Path | None = None) -> int:
    print(f"[run] {label}")
    print("       " + " ".join(command))
    completed = subprocess.run(command, cwd=cwd or ROOT)
    return completed.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Run BreakingWeb environment tests.")
    parser.add_argument(
        "--backend-only",
        action="store_true",
        help="Run only the Python-side environment tests.",
    )
    parser.add_argument(
        "--frontend-only",
        action="store_true",
        help="Run only the Gmail frontend vitest suite.",
    )
    parser.add_argument(
        "--require-frontend",
        action="store_true",
        help="Fail if the frontend runner is unavailable instead of skipping it.",
    )
    args = parser.parse_args()

    if args.backend_only and args.frontend_only:
        parser.error("--backend-only and --frontend-only are mutually exclusive")

    run_backend = not args.frontend_only
    run_frontend = not args.backend_only

    failures = 0

    if run_backend:
        python = _find_pytest_python()
        if python is None:
            print("[skip] backend pytest runner unavailable")
            failures += 1
        else:
            command = [python, "-m", "pytest", "-q", *map(str, BACKEND_TESTS)]
            failures += _run("gmail backend contracts", command)

    if run_frontend:
        frontend_runner = _find_frontend_runner()
        if frontend_runner is None:
            print("[skip] frontend vitest runner unavailable")
            print("       expected a healthy workspace install with:")
            print(f"       {VITEST_ENTRY}")
            if args.require_frontend:
                failures += 1
        else:
            node, vitest_entry = frontend_runner
            command = [node, vitest_entry, "run", "--config", str(GMAIL_VITEST_CONFIG)]
            failures += _run(
                "gmail frontend unit tests",
                command,
                cwd=ROOT / "breakingweb/environments/gmail",
            )

    if failures == 0:
        print("[ok] environment test run completed")
        return 0

    print(f"[fail] environment test run finished with {failures} failing suite(s)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
