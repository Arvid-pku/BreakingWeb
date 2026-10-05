"""Migration status dashboard — per-env progress tracker.

Scans all task YAMLs and test files to report which tasks have been migrated
to canonical_diff and which are still on the legacy eval path.

Usage:
    python -m breakingweb.tasks.migration_status
    python -m breakingweb.tasks.migration_status --env patient_portal
    python -m breakingweb.tasks.migration_status --json

A task is "fully migrated" when all of these are true:
  1. Its YAML declares a canonical_diff: block.
  2. breakingweb/tests/test_<task>_canonical_diff.py exists.
  3. breakingweb/tests/test_<task>_adversarial.py exists.

"Partial" tasks have a canonical_diff but are missing one or both test files.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml


_REPO_ROOT = Path(__file__).resolve().parents[2]
_TASKS_DIR = _REPO_ROOT / "breakingweb" / "tasks"
_TESTS_DIR = _REPO_ROOT / "breakingweb" / "tests"


@dataclass
class TaskStatus:
    task_id: str
    env_id: str
    has_canonical_diff: bool
    has_canonical_diff_test: bool
    has_adversarial_test: bool
    has_legacy_eval: bool

    @property
    def state(self) -> str:
        # The parametrized battery in test_adversarial_battery.py covers every
        # task with a canonical_diff block; per-task adversarial files are only
        # required for oneof-branch logic the generic synthesizer can't express
        # (see docs/guides/canonical-diff-authoring-protocol.md). So the
        # canonical_diff test is the only per-task test we require.
        if self.has_canonical_diff and self.has_canonical_diff_test:
            return "migrated"
        if self.has_canonical_diff:
            return "partial"
        return "legacy"


def _task_tests_index() -> dict[str, dict[str, bool]]:
    """Pre-index all test files. For each, record which task_ids it
    references (by string search) and whether its filename suggests
    canonical_diff vs adversarial coverage.

    Returns: {task_id: {"canonical_diff_test": bool, "adversarial_test": bool}}
    """
    out: dict[str, dict[str, bool]] = {}
    for path in sorted(_TESTS_DIR.glob("test_*.py")):
        try:
            body = path.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        name = path.name.lower()
        is_cd_file = "canonical_diff" in name or "end_to_end" in name
        is_adv_file = "adversarial" in name
        if not (is_cd_file or is_adv_file):
            continue
        # Find any "pp_..." / "gmail_..." / etc. task-id-like strings in the body
        # This avoids brittle filename-task_id matching.
        for match in _iter_task_ids_in(body):
            bucket = out.setdefault(match, {"canonical_diff_test": False, "adversarial_test": False})
            if is_cd_file:
                bucket["canonical_diff_test"] = True
            if is_adv_file:
                bucket["adversarial_test"] = True
    return out


_TASK_ID_RE = re.compile(r"[\"'](pp_\w+|gmail_\w+|rh_\w+|lms_\w+|booking_\w+|amazon_\w+|reddit_\w+)[\"']")


def _iter_task_ids_in(text: str) -> set[str]:
    return set(_TASK_ID_RE.findall(text))


def scan_tasks() -> list[TaskStatus]:
    tests_index = _task_tests_index()
    results: list[TaskStatus] = []
    for yaml_path in sorted(_TASKS_DIR.rglob("*.yaml")):
        if yaml_path.name.startswith("_"):
            continue
        try:
            raw = yaml.safe_load(yaml_path.read_text()) or {}
        except Exception:
            continue
        if not isinstance(raw, dict) or "task_id" not in raw:
            continue
        task_id = raw["task_id"]
        env_id = raw.get("env_id", "unknown")
        has_cd = "canonical_diff" in raw and raw["canonical_diff"] is not None
        has_legacy = "eval" in raw and raw["eval"] is not None
        test_info = tests_index.get(task_id, {"canonical_diff_test": False, "adversarial_test": False})
        results.append(
            TaskStatus(
                task_id=task_id,
                env_id=env_id,
                has_canonical_diff=has_cd,
                has_canonical_diff_test=test_info["canonical_diff_test"],
                has_adversarial_test=test_info["adversarial_test"],
                has_legacy_eval=has_legacy,
            ),
        )
    return results


def summarize_by_env(statuses: list[TaskStatus]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for s in statuses:
        env_bucket = out.setdefault(
            s.env_id,
            {"migrated": 0, "partial": 0, "legacy": 0, "total": 0},
        )
        env_bucket[s.state] += 1
        env_bucket["total"] += 1
    return out


def print_report(statuses: list[TaskStatus], env_filter: str | None = None) -> None:
    filtered = [s for s in statuses if env_filter is None or s.env_id == env_filter]

    print("=" * 72)
    print("  CANONICAL-DIFF MIGRATION STATUS")
    print("=" * 72)

    summary = summarize_by_env(filtered)
    envs = sorted(summary)

    # Table header
    print(f"\n  {'ENV':<16}  {'MIGRATED':>10}  {'PARTIAL':>10}  {'LEGACY':>10}  {'TOTAL':>8}  PROGRESS")
    print(f"  {'-'*16}  {'-'*10}  {'-'*10}  {'-'*10}  {'-'*8}  {'-'*20}")

    grand_migrated = grand_partial = grand_legacy = grand_total = 0
    for env in envs:
        b = summary[env]
        m, p, l, t = b["migrated"], b["partial"], b["legacy"], b["total"]
        grand_migrated += m
        grand_partial += p
        grand_legacy += l
        grand_total += t
        pct = (m / t * 100) if t else 0.0
        bar_width = 20
        filled = int(pct / 100 * bar_width)
        bar = "█" * filled + "░" * (bar_width - filled)
        print(f"  {env:<16}  {m:>10}  {p:>10}  {l:>10}  {t:>8}  {bar} {pct:5.1f}%")

    print(f"  {'-'*16}  {'-'*10}  {'-'*10}  {'-'*10}  {'-'*8}")
    overall_pct = (grand_migrated / grand_total * 100) if grand_total else 0.0
    print(
        f"  {'TOTAL':<16}  {grand_migrated:>10}  {grand_partial:>10}  "
        f"{grand_legacy:>10}  {grand_total:>8}  "
        f"overall: {overall_pct:.1f}%",
    )

    # Partial-state detail — users often want to know what's blocking
    partials = [s for s in filtered if s.state == "partial"]
    if partials:
        print(f"\n  {len(partials)} partial task(s) (canonical_diff present but canonical_diff_test missing):")
        for s in partials:
            missing = []
            if not s.has_canonical_diff_test:
                missing.append("canonical_diff_test")
            print(f"    {s.env_id:<16} {s.task_id:<40} missing: {', '.join(missing)}")

    # Migrated without legacy removed — Phase C sweep candidates
    phase_c_ready = [s for s in filtered if s.state == "migrated" and s.has_legacy_eval]
    if phase_c_ready:
        print(f"\n  {len(phase_c_ready)} task(s) ready for Phase C sweep (still have legacy eval: block):")
        for s in phase_c_ready[:10]:
            print(f"    {s.env_id:<16} {s.task_id}")
        if len(phase_c_ready) > 10:
            print(f"    ... and {len(phase_c_ready) - 10} more")

    print("\n" + "=" * 72)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--env", default=None, help="Filter to a single env_id")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    args = parser.parse_args()

    statuses = scan_tasks()
    if args.json:
        out = {
            "per_env": summarize_by_env(statuses),
            "tasks": [asdict(s) for s in statuses],
        }
        print(json.dumps(out, indent=2))
    else:
        print_report(statuses, env_filter=args.env)
    return 0


if __name__ == "__main__":
    sys.exit(main())
