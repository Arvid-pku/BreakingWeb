"""Seeding utilities — deterministic seed derivation and fake data generation.

Provides :func:`derive_seed` / :func:`derive_anchor_time` for deterministic
seed arithmetic, and :class:`FakeDataGenerator` for reproducible fake data
(names, companies, emails, etc.).  Environment-specific seed runners live
in ``breakingweb.backend.seeders``.
"""

from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta, timezone


def derive_seed(*parts: str | int) -> int:
    joined = "::".join(str(part) for part in parts)
    digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


def derive_anchor_time(seed: int) -> datetime:
    """Return a fixed UTC reference time for a given seed, always in the past."""
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    minutes = derive_seed("anchor", seed) % (365 * 24 * 60)
    anchor = base + timedelta(minutes=minutes)
    # Ensure anchor is never in the future so seeded timestamps look realistic
    now = datetime.now(timezone.utc)
    if anchor > now - timedelta(hours=2):
        anchor = now - timedelta(hours=2)
    return anchor


class FakeDataGenerator:
    """Small deterministic fake-data generator used for seeded benchmarks."""

    _FIRST_NAMES = [
        "Avery", "Jordan", "Maya", "Nina", "Miles",
        "Priya", "Elena", "Marcus", "Sofia", "Theo",
    ]
    _LAST_NAMES = [
        "Chen", "Patel", "Garcia", "Nguyen", "Brooks",
        "Rivera", "Singh", "Kim", "Morris", "Wright",
    ]
    _COMPANIES = [
        "Northwind Labs", "Blue Cedar", "Atlas Harbor",
        "Summit Metrics", "Pioneer Supply", "Lattice Works",
    ]
    _DOMAINS = ["ops", "signal", "harbor", "northwind", "atlas", "lattice"]
    _BUSINESS_SPEAK = [
        "optimize cross-functional alignment",
        "streamline operational reporting",
        "coordinate board readiness",
        "improve vendor responsiveness",
        "stabilize the review cadence",
    ]
    _CATCH_PHRASES = [
        "Reliable systems for fast-moving teams",
        "Clear workflows, fewer surprises",
        "Signal over noise for every launch",
        "Move with confidence and precision",
    ]
    _PARAGRAPH_SENTENCES = [
        "Please review the latest draft before the afternoon check-in.",
        "I flagged the items that still need an owner.",
        "We can close the loop once the dependencies are clear.",
        "Let me know if you need the supporting spreadsheet.",
        "The timeline still works if we keep the original scope.",
    ]

    def __init__(self, seed: int):
        self.rng = random.Random(seed)

    def name(self) -> str:
        return f"{self.rng.choice(self._FIRST_NAMES)} {self.rng.choice(self._LAST_NAMES)}"

    def company(self) -> str:
        return self.rng.choice(self._COMPANIES)

    def domain_word(self) -> str:
        return self.rng.choice(self._DOMAINS)

    def bs(self) -> str:
        return self.rng.choice(self._BUSINESS_SPEAK)

    def catch_phrase(self) -> str:
        return self.rng.choice(self._CATCH_PHRASES)

    def paragraph(self, nb_sentences: int = 3) -> str:
        return " ".join(self.rng.choice(self._PARAGRAPH_SENTENCES) for _ in range(nb_sentences))

    def email(self, domain: str | None = None) -> str:
        local = f"{self.rng.choice(self._FIRST_NAMES)}.{self.rng.choice(self._LAST_NAMES)}".lower()
        return f"{local}@{domain or f'{self.domain_word()}.com'}"


# Backwards-compatible alias for existing imports.
_FallbackFaker = FakeDataGenerator
