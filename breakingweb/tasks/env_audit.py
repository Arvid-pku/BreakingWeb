"""Env pre-flight audit — scans an env for the hazard classes from the
canonical-diff migration playbook and produces a structured report.

Classes audited:
  - Class 3: UI gates (backend HTTPException raises that reject agent actions)
  - Class 5: Date-derivation drift sites in the SPA
  - Class 6: Side-effect mutations on entity-level list fields

Usage:
    python -m breakingweb.tasks.env_audit patient_portal
    python -m breakingweb.tasks.env_audit patient_portal --json

See docs/guides/canonical-diff-authoring-protocol.md for the hazard catalogue
and docs/guides/canonical-diff-authoring-protocol.md for how findings
translate into pre-migration fixes.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterator  # noqa: F401 — used in type hints


_REPO_ROOT = Path(__file__).resolve().parents[2]


# ──────────────────────────────────────────────────────────────
# Data types
# ──────────────────────────────────────────────────────────────


@dataclass
class Finding:
    hazard_class: int
    severity: str  # "info" | "warn" | "block"
    location: str  # file:line
    summary: str
    detail: str
    remediation: str
    extra: dict = field(default_factory=dict)


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────


def _read(path: Path) -> str:
    try:
        return path.read_text()
    except (OSError, UnicodeDecodeError):
        return ""


def _iter_lines(path: Path) -> Iterator[tuple[int, str]]:
    for i, line in enumerate(_read(path).splitlines(), start=1):
        yield i, line


def _route_file(env_id: str) -> Path:
    return _REPO_ROOT / "breakingweb" / "backend" / "routes" / f"{env_id}.py"


def _model_file(env_id: str) -> Path:
    return _REPO_ROOT / "breakingweb" / "backend" / "models" / f"{env_id}.py"


def _spa_dir(env_id: str) -> Path:
    return _REPO_ROOT / "breakingweb" / "environments" / env_id / "src"


# ──────────────────────────────────────────────────────────────
# Class 3 — UI gates (backend rejection raises)
# ──────────────────────────────────────────────────────────────

_HTTP_RAISE_RE = re.compile(
    r"raise\s+HTTPException\s*\(\s*(?:[^)]*?status_code\s*=\s*(\d{3}))[^)]*?detail\s*=\s*(?:f?[\"'])(.*?)[\"']",
    re.DOTALL,
)


def audit_class3(env_id: str) -> list[Finding]:
    """Scan backend routes for HTTP 4xx raises that reject agent actions."""
    path = _route_file(env_id)
    if not path.is_file():
        return []
    src = _read(path)

    findings: list[Finding] = []
    for match in _HTTP_RAISE_RE.finditer(src):
        status = match.group(1)
        detail = match.group(2).replace("\n", " ").strip()
        # Only 4xx — backend validation errors; 5xx are server errors not gates.
        if not status.startswith("4"):
            continue
        # Line number: count newlines before match.start()
        line_no = src.count("\n", 0, match.start()) + 1
        findings.append(
            Finding(
                hazard_class=3,
                severity="info" if status == "404" else "warn",
                location=f"{path.relative_to(_REPO_ROOT)}:{line_no}",
                summary=f"HTTP {status}: {detail[:70]}",
                detail=(
                    f"Route raises HTTPException({status}, detail={detail!r}). "
                    "Any agent trajectory that trips this condition will fail the "
                    "UI booking/submission flow."
                ),
                remediation=(
                    "If tasks in this env depend on this action succeeding, the seed "
                    "must avoid setting up state that trips this gate. "
                    "Walk the agent's intended path manually before migrating such tasks."
                ),
                extra={"status": status, "message": detail},
            ),
        )
    return findings


# ──────────────────────────────────────────────────────────────
# Class 5 — Date-derived status in the SPA
# ──────────────────────────────────────────────────────────────

_DATE_DERIVATION_PATTERNS = [
    # is<Something>Overdue / isExpired / isExpiringSoon → derived status
    (re.compile(r"(?:is|has)(?:Overdue|Expired|Expiring\w*|PastDue|Stale)\s*[:=]"), "named predicate"),
    # new Date(field) < new Date() → inline comparison
    (re.compile(r"new\s+Date\s*\([^)]+\)\s*[<>]=?\s*new\s+Date\s*\(\s*\)"), "inline date comparison"),
    # Date.now() - field or vice versa
    (re.compile(r"Date\.now\s*\(\s*\)\s*[-+]"), "Date.now arithmetic"),
]


def audit_class5(env_id: str) -> list[Finding]:
    """Scan env SPA for date-derivation patterns that can drift from seed
    targets."""
    root = _spa_dir(env_id)
    if not root.is_dir():
        return []

    findings: list[Finding] = []
    for path in sorted(root.rglob("*.tsx")):
        for line_no, line in _iter_lines(path):
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("/*"):
                continue
            for pat, kind in _DATE_DERIVATION_PATTERNS:
                if pat.search(line):
                    # Try to extract the field name for a more informative summary
                    field_match = re.search(r"new\s+Date\s*\(\s*([\w\.\[\]\"']+)", line)
                    field_name = field_match.group(1) if field_match else "<unknown>"
                    findings.append(
                        Finding(
                            hazard_class=5,
                            severity="warn",
                            location=f"{path.relative_to(_REPO_ROOT)}:{line_no}",
                            summary=f"{kind} on {field_name}",
                            detail=(
                                f"Line: {stripped[:120]}\n"
                                "UI derives an 'overdue / expired' status from a date "
                                "field compared against current time. Seeds must place "
                                "date fields on the intended side of `now` for each "
                                "entity's task role — otherwise UI and task targets drift."
                            ),
                            remediation=(
                                f"Tasks that include {field_name}-bearing entities must "
                                "verify seed consistency: completed/healthy entities get "
                                "future dates; overdue/expired entities get past dates. "
                                "Add a per-task `test_<task>_seed_ui_consistency` guard."
                            ),
                            extra={"field": field_name, "pattern_kind": kind},
                        ),
                    )
                    break  # one finding per line
    return findings


# ──────────────────────────────────────────────────────────────
# Class 6 — Side-effect mutations on entity-level list fields
# ──────────────────────────────────────────────────────────────

_MUTATION_RE = re.compile(r"(\w+)\.(\w+)\.(remove|pop|append|extend)\s*\(")


def audit_class6(env_id: str) -> list[Finding]:
    """Scan backend routes for mutations on entity-level list fields that
    aren't the agent's primary target (i.e. not `state.<collection>.append`).
    Cross-reference against `DIFF_IGNORE_FIELDS` on the owning entity class.
    """
    route_path = _route_file(env_id)
    model_path = _model_file(env_id)
    if not route_path.is_file():
        return []

    # Map each pydantic entity class in the env to (a) its list fields and
    # (b) its DIFF_IGNORE_FIELDS declaration.
    entity_lists = _discover_entity_list_fields(model_path)
    ignored = _discover_diff_ignore_fields(model_path)

    # State-level collection names (to distinguish from entity-level fields)
    state_collections = _discover_state_collections(model_path)

    findings: list[Finding] = []
    src = _read(route_path)
    lines = src.splitlines()
    for i, line in enumerate(lines, start=1):
        for match in _MUTATION_RE.finditer(line):
            obj, fname, method = match.group(1), match.group(2), match.group(3)
            # Skip `state.<collection>.<method>(` — those are top-level.
            if obj == "state" and fname in state_collections:
                continue
            # Skip if `fname` isn't a known entity-level list field
            owning_classes = [cls for cls, fields in entity_lists.items() if fname in fields]
            if not owning_classes:
                continue
            cls = owning_classes[0]
            is_already_ignored = fname in ignored.get(cls, set())
            severity = "info" if is_already_ignored else "warn"
            findings.append(
                Finding(
                    hazard_class=6,
                    severity=severity,
                    location=f"{route_path.relative_to(_REPO_ROOT)}:{i}",
                    summary=f"{cls}.{fname}.{method}() — {'already in DIFF_IGNORE_FIELDS' if is_already_ignored else 'side-effect candidate'}",
                    detail=(
                        f"Line: {line.strip()[:120]}\n"
                        f"Route mutates {obj}.{fname} (entity class {cls!r}) via "
                        f"{method}(). This is a side-effect on a non-target collection."
                    ),
                    remediation=(
                        f"Already handled: {fname!r} is in {cls}.DIFF_IGNORE_FIELDS."
                        if is_already_ignored
                        else (
                            f"If this mutation is a legitimate side-effect of an agent "
                            f"action (e.g. slot consumption on booking), add "
                            f"{fname!r} to {cls}.DIFF_IGNORE_FIELDS in "
                            f"breakingweb/backend/models/{env_id}.py. "
                            f"If it's accidental collateral, leave it and let the "
                            f"unaccounted-sweep flag it during per-task verification."
                        )
                    ),
                    extra={
                        "object": obj,
                        "field": fname,
                        "method": method,
                        "owning_class": cls,
                        "already_ignored": is_already_ignored,
                    },
                ),
            )
    return findings


def _discover_entity_list_fields(model_path: Path) -> dict[str, set[str]]:
    """Return {entity_class_name: {list_field_name, ...}} for pydantic classes
    in the env's model module that derive from BaseEntity."""
    if not model_path.is_file():
        return {}
    src = _read(model_path)
    out: dict[str, set[str]] = {}
    # Find class declarations
    for class_match in re.finditer(
        r"^class\s+(\w+)\s*\(\s*BaseEntity\s*\)\s*:\s*\n((?:\s{4}.*\n)*)",
        src,
        re.MULTILINE,
    ):
        name = class_match.group(1)
        body = class_match.group(2)
        fields = set(re.findall(r"^\s+(\w+)\s*:\s*list\[", body, re.MULTILINE))
        if fields:
            out[name] = fields
    return out


def _discover_diff_ignore_fields(model_path: Path) -> dict[str, set[str]]:
    """Return {entity_class_name: set_of_fields_in_DIFF_IGNORE_FIELDS}."""
    if not model_path.is_file():
        return {}
    src = _read(model_path)
    out: dict[str, set[str]] = {}
    for class_match in re.finditer(
        r"^class\s+(\w+)\s*\([^)]+\)\s*:\s*\n((?:\s{4}.*\n)*)",
        src,
        re.MULTILINE,
    ):
        name = class_match.group(1)
        body = class_match.group(2)
        ignore_match = re.search(
            r"DIFF_IGNORE_FIELDS\s*:\s*[^\n]+=\s*\(([^)]*)\)",
            body,
        )
        if ignore_match:
            fields = set(re.findall(r'["\']([\w_]+)["\']', ignore_match.group(1)))
            out[name] = fields
    return out


def _discover_state_collections(model_path: Path) -> set[str]:
    """Return the names of list fields on <Env>State — these are the top-level
    collections (NOT side-effect candidates)."""
    if not model_path.is_file():
        return set()
    src = _read(model_path)
    state_match = re.search(
        r"^class\s+\w+State\s*\(\s*BaseEnvState\s*\)\s*:\s*\n((?:\s{4}.*\n)*)",
        src,
        re.MULTILINE,
    )
    if not state_match:
        return set()
    body = state_match.group(1)
    return set(re.findall(r"^\s+(\w+)\s*:\s*list\[", body, re.MULTILINE))


# ──────────────────────────────────────────────────────────────
# Orchestration
# ──────────────────────────────────────────────────────────────


def audit_env(env_id: str) -> list[Finding]:
    return [
        *audit_class3(env_id),
        *audit_class5(env_id),
        *audit_class6(env_id),
    ]


def _group_by_class(findings: list[Finding]) -> dict[int, list[Finding]]:
    out: dict[int, list[Finding]] = {}
    for f in findings:
        out.setdefault(f.hazard_class, []).append(f)
    return out


def print_report(env_id: str, findings: list[Finding]) -> None:
    grouped = _group_by_class(findings)
    total = len(findings)
    print("=" * 72)
    print(f"  ENV PRE-FLIGHT AUDIT — {env_id}")
    print("=" * 72)
    print(f"  {total} finding(s) across 3 audited hazard classes\n")

    if not findings:
        print("  No findings — env is clear for migration.\n")
        return

    sev_symbol = {"info": "·", "warn": "⚠", "block": "✗"}
    class_labels = {
        3: "Class 3 — UI gates (backend rejection raises)",
        5: "Class 5 — Date-derivation drift sites",
        6: "Class 6 — Side-effect mutations on entity lists",
    }
    for cls in sorted(grouped):
        hits = grouped[cls]
        n_block = sum(1 for f in hits if f.severity == "block")
        n_warn = sum(1 for f in hits if f.severity == "warn")
        n_info = sum(1 for f in hits if f.severity == "info")
        print(f"──── {class_labels.get(cls, f'Class {cls}')}")
        print(f"     {len(hits)} finding(s)  |  block={n_block}  warn={n_warn}  info={n_info}\n")
        for f in hits:
            sym = sev_symbol.get(f.severity, "·")
            print(f"  {sym}  {f.location}")
            print(f"     {f.summary}")
            for line in f.detail.splitlines():
                if line.strip():
                    print(f"     │ {line}")
            print(f"     → {f.remediation}")
            print()

    print("=" * 72)
    print("  Next steps:")
    print("  - Resolve all `block` findings before migrating any task in this env.")
    print("  - Review `warn` findings alongside each task that touches the ")
    print("    relevant collection / field.")
    print("  - `info` findings are already handled; listed for cross-reference.")
    print("  See docs/guides/canonical-diff-authoring-protocol.md for how")
    print("  findings translate into pre-migration fixes.")
    print("=" * 72)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("env_id", help="Env to audit (patient_portal, gmail, robinhood, etc.)")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of a human-readable report.")
    parser.add_argument("--severity", default="info", choices=["info", "warn", "block"],
                        help="Minimum severity to report (default: info — shows all).")
    args = parser.parse_args()

    findings = audit_env(args.env_id)
    severity_rank = {"info": 0, "warn": 1, "block": 2}
    filtered = [f for f in findings if severity_rank[f.severity] >= severity_rank[args.severity]]

    if args.json:
        print(json.dumps([asdict(f) for f in filtered], indent=2))
    else:
        print_report(args.env_id, filtered)

    # Exit 1 if any block findings; 0 otherwise.
    return 1 if any(f.severity == "block" for f in filtered) else 0


if __name__ == "__main__":
    sys.exit(main())
