"""Integrity checks for injection variant YAML configs.

These tests catch structural bugs in variant definitions that would
silently cause injections to be no-ops at runtime.
"""

import pathlib

import pytest
import yaml

VARIANTS_DIR = pathlib.Path(__file__).resolve().parents[2] / "breakingweb" / "injector" / "variants"

GMAIL_VARIANTS = sorted(VARIANTS_DIR.glob("gmail_*.yaml"))


def _load_variant(path: pathlib.Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


# ── I1: alias_entities must have a non-empty aliases list ──────────────


def _collect_alias_entity_variants():
    """Find all variant files that use action: alias_entities."""
    results = []
    for path in GMAIL_VARIANTS:
        data = _load_variant(path)
        for inj in data.get("injections", []):
            params = inj.get("params", {})
            if params.get("action") == "alias_entities":
                results.append((path.name, params))
    return results


_ALIAS_VARIANTS = _collect_alias_entity_variants()


@pytest.mark.parametrize(
    "variant_name,params",
    _ALIAS_VARIANTS,
    ids=[v[0] for v in _ALIAS_VARIANTS],
)
def test_alias_entities_has_aliases(variant_name, params):
    """Every alias_entities injection must supply a non-empty aliases list."""
    aliases = params.get("aliases")
    assert aliases is not None, (
        f"{variant_name}: alias_entities injection is missing 'aliases' param"
    )
    assert isinstance(aliases, list) and len(aliases) > 0, (
        f"{variant_name}: alias_entities 'aliases' must be a non-empty list"
    )


# ── I3: progressive delay stages must all have after_call ──────────────


def _collect_progressive_delay_variants():
    """Find all variant files with progressive delay stages."""
    results = []
    for path in GMAIL_VARIANTS:
        data = _load_variant(path)
        for inj in data.get("injections", []):
            params = inj.get("params", {})
            behavior = params.get("behavior", {})
            if isinstance(behavior, dict) and behavior.get("mode") == "progressive":
                stages = behavior.get("stages", [])
                results.append((path.name, stages))
    return results


_PROGRESSIVE_VARIANTS = _collect_progressive_delay_variants()


@pytest.mark.parametrize(
    "variant_name,stages",
    _PROGRESSIVE_VARIANTS,
    ids=[v[0] for v in _PROGRESSIVE_VARIANTS],
)
def test_progressive_delay_stages_have_after_call(variant_name, stages):
    """Every stage in a progressive delay block must have an after_call key."""
    for i, stage in enumerate(stages):
        assert "after_call" in stage, (
            f"{variant_name}: progressive delay stage {i} is missing 'after_call'"
        )
