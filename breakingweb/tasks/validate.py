"""Per-task validation runner — runs the 6-stage migration pipeline for
any task and reports pass/fail per stage with actionable remediation.

Usage:
    python -m breakingweb.tasks.validate <task_id>
    python -m breakingweb.tasks.validate <task_id> --stages 1,2,3
    python -m breakingweb.tasks.validate <task_id> --json

Stages:
  1. YAML has a canonical_diff block
  2. Schema validation — task loads via _registry without errors
  3. Preview render — apply_canonical_diff produces a concrete final state
  4. Round-trip smoke — pytest test_<task>_canonical_diff.py (correct path)
  5. Adversarial battery — pytest test_<task>_adversarial.py
  6. Equivalence vs history — scripts/canonical_diff_equivalence.py

Exit code: 0 if all selected stages pass; non-zero with the earliest
failed stage number.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml


_REPO_ROOT = Path(__file__).resolve().parents[2]
_TASKS_DIR = _REPO_ROOT / "breakingweb" / "tasks"
_TESTS_DIR = _REPO_ROOT / "breakingweb" / "tests"


@dataclass
class StageResult:
    stage: int
    name: str
    passed: bool
    skipped: bool
    summary: str
    detail: str = ""


def _find_task_yaml(task_id: str) -> Path | None:
    for path in _TASKS_DIR.rglob("*.yaml"):
        if path.name.startswith("_"):
            continue
        try:
            raw = yaml.safe_load(path.read_text()) or {}
        except Exception:
            continue
        if isinstance(raw, dict) and raw.get("task_id") == task_id:
            return path
    return None


# ── Stage 1 — YAML has canonical_diff ────────────────────────────

def stage1_yaml(task_id: str) -> StageResult:
    path = _find_task_yaml(task_id)
    if path is None:
        return StageResult(1, "yaml", passed=False, skipped=False,
                           summary=f"task {task_id!r} not found in any YAML")
    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except Exception as exc:
        return StageResult(1, "yaml", passed=False, skipped=False,
                           summary=f"YAML parse failed: {exc}")
    if "canonical_diff" not in raw or raw["canonical_diff"] is None:
        return StageResult(1, "yaml", passed=False, skipped=False,
                           summary=f"no canonical_diff block in {path.name}",
                           detail="Run the migration scaffolder and author a canonical_diff block.")
    return StageResult(1, "yaml", passed=True, skipped=False,
                       summary=f"canonical_diff block present in {path.name}")


# ── Stage 2 — Schema validation ──────────────────────────────────

def stage2_schema(task_id: str) -> StageResult:
    try:
        from breakingweb.tasks._registry import get_task
        task = get_task(task_id)
    except Exception as exc:
        return StageResult(2, "schema", passed=False, skipped=False,
                           summary=f"task load failed: {type(exc).__name__}",
                           detail=str(exc))
    if task.canonical_diff is None:
        return StageResult(2, "schema", passed=False, skipped=False,
                           summary="task.canonical_diff is None after load")
    return StageResult(2, "schema", passed=True, skipped=False,
                       summary=f"schema valid; {len(task.canonical_diff.invariant)} invariants, "
                               f"{len(task.canonical_diff.create)} creates, "
                               f"{len(task.canonical_diff.named_invariants)} named")


# ── Stage 3 — Preview render ─────────────────────────────────────

def stage3_preview(task_id: str, seed: int = 42) -> StageResult:
    try:
        from breakingweb.backend.state import SessionManager
        from breakingweb.tasks.preview import apply_canonical_diff
        from breakingweb.tasks._registry import get_task
    except Exception as exc:
        return StageResult(3, "preview", passed=False, skipped=False,
                           summary=f"import failed: {exc}")

    task = get_task(task_id)
    try:
        sm = SessionManager()
        sid, targets, _ = sm.create_session(env_id=task.env_id, task_id=task_id, seed=seed)
        initial = sm.get_state(sid)
        final = apply_canonical_diff(initial_state=initial, task_id=task_id,
                                      targets=dict(targets))
        if final is None:
            return StageResult(3, "preview", passed=False, skipped=False,
                               summary="apply_canonical_diff returned None")
        return StageResult(3, "preview", passed=True, skipped=False,
                           summary="canonical final state rendered")
    except Exception as exc:
        return StageResult(3, "preview", passed=False, skipped=False,
                           summary=f"preview failed: {type(exc).__name__}",
                           detail=f"{exc}\n"
                                  "Common causes: missing target key (Class 3), "
                                  "invalid predicate, entity class resolution failure.")


# ── Stage 4 — Round-trip smoke (correct trajectory test) ─────────

def _find_test_file(task_id: str, suffix: str) -> Path | None:
    # Search any test file that references the task_id AND has the suffix in its name
    for path in _TESTS_DIR.glob(f"test_*{suffix}*.py"):
        try:
            body = path.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        if f"'{task_id}'" in body or f'"{task_id}"' in body:
            return path
    return None


def _run_pytest(path: Path, node_expr: str | None = None) -> tuple[bool, str]:
    cmd = [sys.executable, "-m", "pytest", str(path)]
    if node_expr:
        cmd += ["-k", node_expr]
    cmd += ["-q", "--no-header", "--tb=short"]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=_REPO_ROOT, timeout=180)
    return r.returncode == 0, (r.stdout + r.stderr).strip()


def stage4_roundtrip(task_id: str) -> StageResult:
    path = _find_test_file(task_id, "canonical_diff") or _find_test_file(task_id, "end_to_end")
    if path is None:
        return StageResult(4, "roundtrip", passed=False, skipped=True,
                           summary="no canonical_diff / end_to_end test file found",
                           detail=f"Expected breakingweb/tests/test_{task_id}_canonical_diff.py "
                                  "or similar. Create it using the per-task test template.")
    ok, output = _run_pytest(path, node_expr="correct")
    if ok:
        return StageResult(4, "roundtrip", passed=True, skipped=False,
                           summary=f"correct-trajectory test passed ({path.name})")
    return StageResult(4, "roundtrip", passed=False, skipped=False,
                       summary=f"correct-trajectory test failed in {path.name}",
                       detail=output[-1500:])


# ── Stage 5 — Adversarial battery ────────────────────────────────

def stage5_adversarial(task_id: str) -> StageResult:
    path = _find_test_file(task_id, "adversarial")
    if path is None:
        return StageResult(5, "adversarial", passed=False, skipped=True,
                           summary="no adversarial test file found",
                           detail=f"Expected breakingweb/tests/test_{task_id}_adversarial.py")
    ok, output = _run_pytest(path)
    if ok:
        return StageResult(5, "adversarial", passed=True, skipped=False,
                           summary=f"adversarial battery passed ({path.name})")
    return StageResult(5, "adversarial", passed=False, skipped=False,
                       summary=f"adversarial battery failed in {path.name}",
                       detail=output[-1500:])


# ── Stage 6 — Equivalence vs history ─────────────────────────────

def stage6_equivalence(task_id: str) -> StageResult:
    script = _REPO_ROOT / "scripts" / "canonical_diff_equivalence.py"
    if not script.is_file():
        return StageResult(6, "equivalence", passed=False, skipped=True,
                           summary="equivalence script missing")
    try:
        r = subprocess.run(
            [sys.executable, str(script), task_id],
            capture_output=True, text=True, cwd=_REPO_ROOT, timeout=120,
        )
    except subprocess.TimeoutExpired:
        return StageResult(6, "equivalence", passed=False, skipped=False,
                           summary="equivalence script timed out after 120s")
    out = (r.stdout + r.stderr).strip()
    # Script exits 1 when fail_pass > 0; 0 otherwise (including when no trajectories)
    passed = r.returncode == 0
    return StageResult(6, "equivalence", passed=passed, skipped=False,
                       summary=("equivalence OK" if passed
                                else "new matcher more lenient than legacy on ≥ 1 trajectory"),
                       detail=out[-1500:])


# ── Orchestration ────────────────────────────────────────────────

_STAGES = {
    1: stage1_yaml,
    2: stage2_schema,
    3: stage3_preview,
    4: stage4_roundtrip,
    5: stage5_adversarial,
    6: stage6_equivalence,
}


def run_pipeline(task_id: str, stages: list[int] | None = None) -> list[StageResult]:
    selected = stages if stages else sorted(_STAGES)
    results: list[StageResult] = []
    for s in selected:
        fn = _STAGES.get(s)
        if fn is None:
            continue
        result = fn(task_id)
        results.append(result)
        # Fail-fast on earlier stages — later stages depend on earlier ones
        if not result.passed and not result.skipped and s <= 3:
            break
    return results


def print_report(task_id: str, results: list[StageResult]) -> None:
    print("=" * 72)
    print(f"  VALIDATION PIPELINE — {task_id}")
    print("=" * 72)
    for r in results:
        if r.skipped:
            sym = "—"
            status = "SKIP"
        elif r.passed:
            sym = "✓"
            status = "PASS"
        else:
            sym = "✗"
            status = "FAIL"
        print(f"  [{status}] {sym} Stage {r.stage} ({r.name}): {r.summary}")
        if r.detail and not r.passed:
            for line in r.detail.splitlines():
                if line.strip():
                    print(f"         │ {line[:100]}")
    print("=" * 72)

    failed = [r for r in results if not r.passed and not r.skipped]
    if failed:
        first = failed[0]
        print(f"  First failing stage: {first.stage} ({first.name})")
        print(f"  See docs/guides/canonical-diff-authoring-protocol.md for the ")
        print(f"  triage decision tree — hazard class likely to match this failure.")
    else:
        skipped = [r for r in results if r.skipped]
        if skipped:
            print(f"  All ran stages passed; {len(skipped)} skipped (missing test files).")
        else:
            print(f"  All {len(results)} stages passed. Task is migration-complete.")
    print("=" * 72)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("task_id")
    parser.add_argument("--stages", default=None,
                        help="Comma-separated stage numbers to run (default: all 6)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    stages = None
    if args.stages:
        stages = [int(s.strip()) for s in args.stages.split(",") if s.strip()]

    results = run_pipeline(args.task_id, stages)

    if args.json:
        print(json.dumps([asdict(r) for r in results], indent=2))
    else:
        print_report(args.task_id, results)

    first_failed = next((r.stage for r in results if not r.passed and not r.skipped), 0)
    return first_failed


if __name__ == "__main__":
    sys.exit(main())
