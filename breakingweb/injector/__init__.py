"""Four-layer instrumentation system for standard/degraded benchmark variants.

Layers:
    seed    — Data-level: what the agent reads (email content, contacts, info distribution)
    server  — State-level: structural mutations (hidden prereqs, shuffled entities)
    client  — UI-level: DOM/JS mutations (swapped labels, decoy elements, hidden affordances)
    network — Transport-level: HTTP interception (delays, stale data, silent failures)
"""

from .apply import apply_degradation, apply_seed_degradations
from .config import DegradationConfig, Injection

__all__ = [
    "DegradationConfig",
    "Injection",
    "apply_degradation",
    "apply_seed_degradations",
]
