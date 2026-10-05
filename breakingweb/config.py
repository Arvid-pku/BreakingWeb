"""Read benchmark settings, accepting the previous environment-variable prefix."""

from __future__ import annotations

import os
from typing import overload


@overload
def getenv(name: str, default: str) -> str: ...


@overload
def getenv(name: str, default: None = None) -> str | None: ...


def getenv(name: str, default: str | None = None) -> str | None:
    """Prefer BREAKINGWEB settings, including explicit empty values.

    Read at call time so settings loaded from .env files and test overrides
    follow the same precedence as process environment variables.
    """
    if name in os.environ:
        return os.environ[name]
    if name.startswith("BREAKINGWEB_"):
        legacy_name = "WEBSTRESS_" + name.removeprefix("BREAKINGWEB_")
        return os.environ.get(legacy_name, default)
    return default
