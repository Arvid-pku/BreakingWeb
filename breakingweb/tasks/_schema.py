"""Task definition schema for BreakingWeb YAML tasks.

Provides the :class:`TaskDefinition` dataclass that mirrors the structure of
``breakingweb/tasks/gmail/*.yaml`` files.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from breakingweb.tasks.canonical_diff import CanonicalDiff


# ------------------------------------------------------------------
# Sub-schemas for the ``seed:`` block
# ------------------------------------------------------------------

@dataclass
class ActorSpec:
    """One entry in ``seed.actors``."""
    name: str | None = None
    domain: str = "example.com"
    is_vip: bool = False


@dataclass
class StepSpec:
    """One entry in ``seed.steps``."""
    use: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    outputs: list[str] = field(default_factory=list)


@dataclass
class TrajectoryStock:
    """Price trajectory for one stock in a live-price task."""
    keyframes: list[list[float]] = field(default_factory=list)
    noise_pct: float = 0.3


@dataclass
class PriceTrajectoryConfig:
    """The ``seed.price_trajectory`` section of a task YAML."""
    tick_interval_seconds: float = 2.0
    stocks: dict[str, TrajectoryStock] = field(default_factory=dict)


@dataclass
class SeedConfig:
    """The ``seed:`` section of a task YAML."""
    distractors: int = 20
    skip_real_hotels: bool = False
    skip_real_products: bool = False
    actors: dict[str, ActorSpec] = field(default_factory=dict)
    steps: list[StepSpec] = field(default_factory=list)
    targets: dict[str, str] = field(default_factory=dict)
    price_trajectory: PriceTrajectoryConfig | None = None


# Backward-compatible aliases expected by tasks/__init__.py
SeedActor = ActorSpec
SeedStep = StepSpec


# ------------------------------------------------------------------
# Eval schema
# ------------------------------------------------------------------

@dataclass
class Check:
    """One positive check in ``eval.checks``."""
    expr: str
    desc: str = ""


@dataclass
class NegativeCheck:
    """One negative check in ``eval.negative_checks``."""
    expr: str
    desc: str = ""
    penalty: float = 0.15


@dataclass
class EvalConfig:
    """The ``eval:`` section of a task YAML.

    Deprecated: evaluation now uses ``canonical_diff`` exclusively.
    This class is retained only so existing YAMLs with ``eval:`` blocks
    continue to load without parse errors.
    """
    source: str = "server_state"
    checks: list[Check] = field(default_factory=list)
    negative_checks: list[NegativeCheck] = field(default_factory=list)


# ------------------------------------------------------------------
# Top-level TaskDefinition
# ------------------------------------------------------------------

@dataclass
class TaskDefinition:
    """Structured representation of a BreakingWeb task YAML file."""

    task_id: str
    env_id: str = "gmail"
    title: str = ""
    instruction_template: str = ""
    instruction: str = ""
    difficulty: str = "medium"
    time_limit_seconds: int = 180
    expected_steps: int | None = None
    primary_primitives: list[str] = field(default_factory=list)
    secondary_primitives: list[str] = field(default_factory=list)
    start_path: str = "/"
    seed: SeedConfig | None = None
    eval: EvalConfig | None = None
    canonical_diff: CanonicalDiff | None = None

    # ------------------------------------------------------------------
    # Loader
    # ------------------------------------------------------------------

    @classmethod
    def from_yaml(cls, path: Path) -> "TaskDefinition":
        """Load a task definition from a YAML file."""
        with open(path) as fh:
            raw = yaml.safe_load(fh)
        return cls.from_dict(raw)

    @classmethod
    def model_validate(cls, raw: dict[str, Any]) -> "TaskDefinition":
        """Pydantic-style entry point used by the task registry."""
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "TaskDefinition":
        """Build a TaskDefinition from a plain dict (e.g. parsed YAML)."""
        raw = dict(raw)
        seed_raw = raw.pop("seed", None)
        eval_raw = raw.pop("eval", None)
        canonical_diff_raw = raw.pop("canonical_diff", None)
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in raw.items() if k in known}
        td = cls(**filtered)

        if canonical_diff_raw is not None:
            td.canonical_diff = CanonicalDiff.model_validate(canonical_diff_raw)

        if seed_raw is not None:
            actors = {
                key: ActorSpec(**spec) if isinstance(spec, dict) else ActorSpec()
                for key, spec in (seed_raw.get("actors") or {}).items()
            }
            steps = [
                StepSpec(
                    use=s.get("use", ""),
                    params=s.get("params") or {},
                    outputs=s.get("outputs") or [],
                )
                for s in (seed_raw.get("steps") or [])
            ]
            seed_cfg = SeedConfig(
                distractors=seed_raw.get("distractors", 20),
                skip_real_hotels=seed_raw.get("skip_real_hotels", False),
                skip_real_products=seed_raw.get("skip_real_products", False),
                actors=actors,
                steps=steps,
                targets=seed_raw.get("targets") or {},
            )

            pt_raw = seed_raw.get("price_trajectory")
            if pt_raw and isinstance(pt_raw, dict):
                pt_stocks = {}
                for sym, traj_data in pt_raw.get("stocks", {}).items():
                    pt_stocks[sym] = TrajectoryStock(
                        keyframes=traj_data.get("keyframes", []),
                        noise_pct=traj_data.get("noise_pct", 0.3),
                    )
                seed_cfg.price_trajectory = PriceTrajectoryConfig(
                    tick_interval_seconds=pt_raw.get("tick_interval_seconds", 2.0),
                    stocks=pt_stocks,
                )

            td.seed = seed_cfg

        if eval_raw is not None:
            checks = [
                Check(**c) if isinstance(c, dict) else Check(expr=str(c))
                for c in (eval_raw.get("checks") or [])
            ]
            negative_checks = [
                NegativeCheck(**nc) if isinstance(nc, dict) else NegativeCheck(expr=str(nc))
                for nc in (eval_raw.get("negative_checks") or [])
            ]
            td.eval = EvalConfig(
                source=eval_raw.get("source", "server_state"),
                checks=checks,
                negative_checks=negative_checks,
            )

        return td

    # dict-like access for backward compatibility with plain-dict task defs
    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def __contains__(self, key: str) -> bool:
        return hasattr(self, key)
