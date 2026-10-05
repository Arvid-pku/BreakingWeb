"""Advanced environment backend package for BreakingWeb."""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = ["SessionManager"]

if TYPE_CHECKING:
    from .state import SessionManager


def __getattr__(name: str):
    if name == "SessionManager":
        from .state import SessionManager

        return SessionManager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
