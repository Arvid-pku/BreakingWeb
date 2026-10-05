"""Canonical cognitive primitive taxonomy for BreakingWeb.

Seven orthogonal primitives derived from empirical failure analysis of
WebArena, OSWorld, and AgentBench traces. See Claude.html for the full
design rationale.
"""

PRIMITIVES = [
    "grounding",
    "planning",
    "state_tracking",
    "backtracking",
    "patience",
    "exploration",
    "verification",
]

# Migration from old 12-primitive taxonomy
_MIGRATION_MAP: dict[str, str] = {
    "memory": "state_tracking",
    "attention": "grounding",
    "adversarial_robustness": "grounding",
    "spatial_reasoning": "grounding",
    "reflection": "verification",
    "constraint_satisfaction": "planning",
    "error_recovery": "backtracking",
    "planning": "planning",
    "patience": "patience",
    "exploration": "exploration",
    "verification": "verification",
    "backtracking": "backtracking",
}


def migrate_primitives(old_list: list[str]) -> list[str]:
    """Convert old primitives to new taxonomy, deduplicating."""
    new: list[str] = []
    seen: set[str] = set()
    for p in old_list:
        mapped = _MIGRATION_MAP.get(p, p)
        if mapped not in seen:
            seen.add(mapped)
            new.append(mapped)
    return new


def validate_primitives(primitives: list[str]) -> list[str]:
    """Return any primitives not in the canonical set."""
    return [p for p in primitives if p not in PRIMITIVES]
