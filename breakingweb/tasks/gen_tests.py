"""Per-task test generator — auto-creates the canonical_diff test file
from an already-authored canonical_diff block.

Usage:
    python -m breakingweb.tasks.gen_tests <task_id>
    python -m breakingweb.tasks.gen_tests <task_id> --force   # overwrite

Emits:
  breakingweb/tests/test_<task_id>_canonical_diff.py

Adversarial coverage is automatic: tests/test_adversarial_battery.py
parametrizes ``synthesize_adversarial_cases`` over every task whose YAML
contains a ``canonical_diff`` block — no per-task file needed. If a task
needs hand-written adversarial cases (oneof-branch logic, bespoke
mutations), add a ``test_<task_id>_adversarial.py`` file manually; the
battery runs alongside it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml


_REPO_ROOT = Path(__file__).resolve().parents[2]
_TASKS_DIR = _REPO_ROOT / "breakingweb" / "tasks"
_TESTS_DIR = _REPO_ROOT / "breakingweb" / "tests"


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


def _render_predicate_hint(pred: dict) -> str:
    """Short human-readable rendering of a predicate for inline comments."""
    if not isinstance(pred, dict) or len(pred) != 1:
        return str(pred)
    k = next(iter(pred))
    v = pred[k]
    if k == "eq":
        return f"== {v!r}"
    if k == "in":
        return f"in {v!r}"
    if k == "between":
        return f"between {v!r}"
    if k == "expr":
        return f"<expr: {v}>"
    if k == "any":
        return "any value"
    if k == "set_eq":
        return f"set == {v!r}"
    if k == "superset":
        return f"superset of {v!r}"
    if k == "subset":
        return f"subset of {v!r}"
    if k == "contains":
        return f"contains {v!r}"
    if k == "substring":
        return f"substring {v!r}"
    if k == "substring_all":
        return f"all substrings {v!r}"
    if k == "regex":
        return f"regex {v!r}"
    if k == "matches_semantic":
        return f"semantic ~ {v!r}"
    return str(pred)


def _canonical_diff_test_source(task_id: str, env_id: str, cd: dict) -> str:
    """Render the canonical_diff test file body."""
    create_entries = cd.get("create") or []
    first_create = create_entries[0] if create_entries else None

    # Hint block: list predicate constraints for the first create entry
    hint_lines: list[str] = []
    if first_create:
        entity = first_create.get("entity", "?")
        bijection = first_create.get("bijection")
        if bijection:
            hint_lines.append(f"    # Bijection over: {bijection.get('over')}, variable: {bijection.get('variable')}")
            hint_lines.append(f"    # Create one {entity} per element of the bijection target.")
        else:
            hint_lines.append(f"    # Create a single {entity}.")
        props = first_create.get("properties") or {}
        if props:
            hint_lines.append(f"    # Required field constraints on {entity}:")
            for fname, pred in props.items():
                hint_lines.append(f"    #   - {fname}: {_render_predicate_hint(pred)}")

    hint_block = "\n".join(hint_lines) if hint_lines else "    # (canonical_diff has no create entries — may be an update/delete or read-only task)"

    bijection_iter = ""
    if first_create and first_create.get("bijection"):
        over_expr = first_create["bijection"]["over"]
        var_name = first_create["bijection"]["variable"]
        # Heuristic: parse target['X'] or target.X to get the key
        key_name = None
        if "target[" in over_expr:
            import re
            m = re.search(r"target\[['\"]([^'\"]+)['\"]\]", over_expr)
            if m:
                key_name = m.group(1)
        elif "target." in over_expr:
            key_name = over_expr.split("target.")[1].split(".")[0].strip()

        if key_name:
            bijection_iter = f"""\
    # TODO(author): for each element in the bijection target set, build
    # an entity that satisfies every predicate above and append it to
    # state.<collection>. Example pattern:
    #
    #     for {var_name} in targets[{key_name!r}]:
    #         state.<collection>.append(_make_correct_entity({var_name}, targets))
    #
    # The collection name is the lowercase pluralization of
    # '{first_create.get('entity', '?')}' (e.g. 'appointments', 'emails')."""
        else:
            bijection_iter = "    # TODO(author): iterate over the bijection target set and append correct entities."
    elif first_create:
        bijection_iter = f"    # TODO(author): build a single {first_create.get('entity', '?')} that satisfies the predicates above and append to state.<collection>."
    else:
        bijection_iter = "    # TODO(author): mutate state per the task's canonical_diff (update / delete / ChatMessage.content / etc)."

    body = f'''"""End-to-end tests for {task_id} canonical_diff.

Auto-generated scaffolding — fill in the TODO blocks before running.

After filling: `python -m breakingweb.tasks.validate {task_id}`
"""

from datetime import datetime, timezone, timedelta

from breakingweb.backend.state import SessionManager
from breakingweb.eval_core import compute_diff, match_diff
from breakingweb.tasks._registry import get_task


# TODO(author): import the entity class(es) this task's canonical_diff targets:
# from breakingweb.backend.models.{env_id} import ...


def _setup_session(seed: int = 42):
    """Fresh session + initial snapshot + live state."""
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id={env_id!r},
        task_id={task_id!r},
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _make_correct_entity(*args, **kwargs):
    """Construct an entity that satisfies every predicate on create[0].

    TODO(author): replace the NotImplementedError with real construction.
    Common pattern for patient_portal bookings:
        return Appointment(
            id=f"appt_correct_{{args[0]}}",
            provider_id=targets["admin_providers"][args[0]][0],
            datetime=(datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
            status="scheduled",
            type="in-person",
            reason="...",
        )
    """
    raise NotImplementedError("fill in _make_correct_entity")


def test_correct_trajectory_passes():
    """Agent produces entities satisfying every authored predicate.
    Expected: score=1.0, passed=True, no failures."""
    sm, sid, targets, initial, state = _setup_session()

{hint_block}

{bijection_iter}

    task = get_task({task_id!r})
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {{report.failures}}"
    assert report.score == 1.0, f"expected 1.0, got {{report.score}}"


def test_wrong_field_fails():
    """Agent produces entities with at least one violating property.
    Expected: score < 1.0, passed=False, at least one check fails."""
    sm, sid, targets, initial, state = _setup_session()

    # TODO(author): same structure as test_correct_trajectory_passes but
    # mutate one field to an invalid value (e.g. wrong provider_id, past date,
    # wrong status). See hazard Class 4 (identity test) in
    # docs/guides/canonical-diff-authoring-protocol.md for guidance.

    task = get_task({task_id!r})
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        f"wrong-field trajectory unexpectedly passed. Verify that the matched "
        f"predicate actually rejects the wrong value, not just the missing one."
    )


def test_excess_fails():
    """Agent produces correct entities PLUS one extra.
    Expected: score may be 1.0 but passed=False (unaccounted excess)
    OR score<1.0 with 'did not schedule more than X' invariant penalty."""
    sm, sid, targets, initial, state = _setup_session()

    # TODO(author): produce the correct entities AND one additional entity
    # of the same type. If the task has no bijection, this test may not
    # apply — delete it.

    task = get_task({task_id!r})
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "excess-entity trajectory unexpectedly passed. Check that the "
        "unaccounted sweep is surfacing the extra entity as a failure."
    )
'''
    return body


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("task_id")
    parser.add_argument("--force", action="store_true", help="Overwrite existing file")
    args = parser.parse_args()

    yaml_path = _find_task_yaml(args.task_id)
    if yaml_path is None:
        print(f"Task {args.task_id!r} not found.", file=sys.stderr)
        return 1
    raw = yaml.safe_load(yaml_path.read_text()) or {}
    env_id = raw.get("env_id") or "unknown"
    cd = raw.get("canonical_diff")
    if cd is None:
        print(f"Task {args.task_id!r} has no canonical_diff. Author it first "
              "(run Tool B to scaffold).", file=sys.stderr)
        return 1

    cd_file = _TESTS_DIR / f"test_{args.task_id}_canonical_diff.py"

    if cd_file.exists() and not args.force:
        print(f"[skip] {cd_file.relative_to(_REPO_ROOT)} already exists (use --force to overwrite)")
        return 0

    cd_file.write_text(_canonical_diff_test_source(args.task_id, env_id, cd))
    print(f"[write] {cd_file.relative_to(_REPO_ROOT)}")
    print()
    print("Next steps:")
    print("  1. Open the canonical_diff test file and fill in the TODO blocks.")
    print(f"  2. Run: python -m breakingweb.tasks.validate {args.task_id}")
    print("  3. Adversarial coverage is automatic via test_adversarial_battery.py;")
    print("     only write a bespoke test_<task_id>_adversarial.py if the task needs")
    print("     oneof-branch logic the generic synthesizer can't express.")
    print("  4. When all stages pass, commit the YAML + canonical_diff test.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
