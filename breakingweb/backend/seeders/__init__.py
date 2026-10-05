"""Composable seed runners for BreakingWeb environments.

Each environment registers a :class:`SeedRunner`-compatible callable in
:data:`SEEDER_REGISTRY`.  ``SessionManager`` dispatches to the correct
runner by ``env_id`` — adding a new environment only requires a new entry.
"""

from __future__ import annotations

import random
from typing import Any, Protocol

from breakingweb.tasks._schema import TaskDefinition

from .amazon import AmazonSeedRunner
from .booking import BookingSeedRunner
from .gmail import GmailSeedRunner
from .lms import LMSSeedRunner
from .patient_portal import PatientPortalSeedRunner
from .reddit import RedditSeedRunner
from .robinhood import RobinhoodSeedRunner


class SeedRunner(Protocol):
    """Protocol that every environment seed runner must satisfy."""

    def run(
        self,
        task: TaskDefinition,
        seed: int,
        fake: Any,
        rng: random.Random,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return ``(base_state, resolved_targets)``."""
        ...


SEEDER_REGISTRY: dict[str, SeedRunner] = {
    "amazon": AmazonSeedRunner(),
    "booking": BookingSeedRunner(),
    "gmail": GmailSeedRunner(),
    "lms": LMSSeedRunner(),
    "patient_portal": PatientPortalSeedRunner(),
    "reddit": RedditSeedRunner(),
    "robinhood": RobinhoodSeedRunner(),
}


__all__ = ["AmazonSeedRunner", "BookingSeedRunner", "GmailSeedRunner", "LMSSeedRunner", "PatientPortalSeedRunner", "RedditSeedRunner", "RobinhoodSeedRunner", "SeedRunner", "SEEDER_REGISTRY"]
