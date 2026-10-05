"""Integrity checks for task YAML files and seed builders.

These tests catch common authoring mistakes across all task definitions:
- Using nonexistent model attributes in eval expressions
- Leftover .test TLD domains in actor definitions or seed builder code
- Unsafe bare indexing that can raise IndexError at eval time
"""

import re
from pathlib import Path

import yaml

WAB_DIR = Path(__file__).resolve().parents[2] / "breakingweb"
TASKS_DIR = WAB_DIR / "tasks"


def _load_all_task_yamls():
    """Yield (path, parsed_dict) for every task YAML."""
    for yaml_path in sorted(TASKS_DIR.rglob("*.yaml")):
        with open(yaml_path) as f:
            data = yaml.safe_load(f)
        if data:
            yield yaml_path, data


def _collect_check_exprs(data):
    """Extract all eval `expr` strings from a task YAML dict."""
    exprs = []
    for phase in ("checks", "negative_checks"):
        for section_key in ("eval", "evaluation"):
            section = data.get(section_key)
            if not isinstance(section, dict):
                continue
            for item in section.get(phase, []) or []:
                if isinstance(item, dict) and "expr" in item:
                    exprs.append(item["expr"])
    return exprs


# ------------------------------------------------------------------
# T1: No eval expression should reference f.sender (use f.from_addresses)
# ------------------------------------------------------------------
def test_no_f_sender_in_eval_exprs():
    violations = []
    for path, data in _load_all_task_yamls():
        for expr in _collect_check_exprs(data):
            if re.search(r"\bf\.sender\b", expr):
                violations.append(f"{path.name}: {expr!r}")
    assert not violations, (
        "Eval expressions reference f.sender (FilterRule has no such attribute; "
        f"use f.from_addresses):\n" + "\n".join(violations)
    )


# ------------------------------------------------------------------
# T3: No .test TLD in actor domain fields
# ------------------------------------------------------------------
def test_no_test_tld_in_actor_domains():
    violations = []
    for path, data in _load_all_task_yamls():
        actors = (data.get("seed") or {}).get("actors") or {}
        for actor_name, actor_cfg in actors.items():
            if not isinstance(actor_cfg, dict):
                continue
            domain = actor_cfg.get("domain", "")
            if domain.endswith(".test"):
                violations.append(f"{path.name}: actors.{actor_name}.domain = {domain}")
    assert not violations, (
        "Actor domains must not use .test TLD:\n" + "\n".join(violations)
    )


# ------------------------------------------------------------------
# T6: No bare [expr][0] indexing in eval expressions (IndexError risk)
# ------------------------------------------------------------------
def test_no_bare_index_zero_in_eval_exprs():
    # Matches patterns like `[...][0]` which crash when the list is empty.
    bare_index_re = re.compile(r"\[[^\]]+\]\[0\]")
    violations = []
    for path, data in _load_all_task_yamls():
        for expr in _collect_check_exprs(data):
            if bare_index_re.search(expr):
                violations.append(f"{path.name}: {expr!r}")
    assert not violations, (
        "Eval expressions use bare [list][0] indexing which raises IndexError "
        "when the list is empty. Use any() or next(..., None) instead:\n"
        + "\n".join(violations)
    )


# ------------------------------------------------------------------
# T7: No .test TLD in seed builder files or injector source
# ------------------------------------------------------------------
_DOT_TEST_DOMAIN_RE = re.compile(
    r"""['"]        # opening quote
    [^'"]*          # any chars before the domain
    \.test          # the .test TLD
    ['"]            # closing quote
    """,
    re.VERBOSE,
)


def test_no_test_tld_in_seed_builders_or_injector():
    """Seed builders and injector source must not contain .test TLD domains.

    The project migrated from .test to realistic TLDs (.com, .io, .co, .net).
    This test prevents regressions.
    """
    source_globs = [
        TASKS_DIR.glob("_seed_builders*.py"),
        (WAB_DIR / "injector").rglob("*.py"),
        (WAB_DIR / "injector").rglob("*.yaml"),
        (WAB_DIR / "backend" / "seeders").glob("*.py"),
        [WAB_DIR / "backend" / "seeder.py"],
        [WAB_DIR / "tasks" / "_schema.py"],
    ]
    violations = []
    for glob_iter in source_globs:
        for fpath in sorted(glob_iter):
            for lineno, line in enumerate(fpath.read_text().splitlines(), 1):
                # Skip comments that are not domain-bearing
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith("//"):
                    continue
                if _DOT_TEST_DOMAIN_RE.search(line):
                    violations.append(f"{fpath.relative_to(WAB_DIR)}:{lineno}: {stripped}")
    assert not violations, (
        "Source files still contain .test TLD domains. "
        "Replace with realistic TLDs (.com, .io, .co, .net):\n"
        + "\n".join(violations)
    )
