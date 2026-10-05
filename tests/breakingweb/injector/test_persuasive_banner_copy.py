"""Persuasive `false_banner` copy must pass the adversarial obviousness rubric.

The TSX-side `PERSUASIVE_BANNER_COPY` array is the source of truth for
banner strings injected with `style: persuasive`. The rubric we use to
gate seed-layer adversarial content must also accept these banner strings
— if a string would be flagged by the rubric, it shouldn't be in the
banner pool either.

This test extracts the array from BenchmarkToolbar.tsx with a regex (no JS
runtime needed for CI) and runs each entry through the Python rubric
(`breakingweb.injector.seed._adv_passes_obviousness_rubric`). The two
implementations of "obvious" are kept in lock-step.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from breakingweb.injector.seed import _adv_passes_obviousness_rubric

TSX_PATH = (
    Path(__file__).resolve().parents[3]
    / "breakingweb/environments/shared/src/components/BenchmarkToolbar.tsx"
)


def _extract_banner_copy() -> list[str]:
    text = TSX_PATH.read_text()
    # Find the PERSUASIVE_BANNER_COPY = readonly string[] = [ ... ];
    match = re.search(
        r"const\s+PERSUASIVE_BANNER_COPY[^=]*=\s*\[(?P<body>.*?)\]\s*;",
        text,
        re.DOTALL,
    )
    if not match:
        raise AssertionError("PERSUASIVE_BANNER_COPY not found in BenchmarkToolbar.tsx")
    body = match.group("body")
    # Pull out double-quoted strings, accounting for embedded escapes.
    return re.findall(r'"((?:[^"\\]|\\.)+)"', body)


@pytest.mark.parametrize("copy", _extract_banner_copy())
def test_persuasive_banner_copy_passes_rubric(copy: str) -> None:
    passed, reason = _adv_passes_obviousness_rubric(copy)
    assert passed, f"Persuasive banner copy failed rubric ({reason}): {copy!r}"


def test_persuasive_pool_is_nonempty() -> None:
    pool = _extract_banner_copy()
    assert len(pool) >= 3, "Need at least 3 lures in the persuasive pool"
