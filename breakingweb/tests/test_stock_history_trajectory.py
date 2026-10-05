"""Unit tests for `_history_to_trajectory` defensive per-step error handling.

Regression: in the sonnet_4_6_full_openrouter3 sweep two booking intervention
runs had `agent.steps=38` but `agent.trajectory=[]` — `_history_to_trajectory`
raised mid-loop after writing 22 / 35 screenshots, and the partial work was
discarded by the outer `try/except` in `run_episode`.
"""
from __future__ import annotations

from breakingweb.stock_browseruse_eval import _history_to_trajectory


class _FakeAction:
    """Minimal stand-in for browser-use ActionModel."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def model_dump(self, **_):
        return self._payload


class _FakeModelOutput:
    def __init__(self, action_payloads: list[dict]) -> None:
        self.thinking = "thinking"
        self.memory = ""
        self.action = [_FakeAction(p) for p in action_payloads]


class _FakeState:
    def __init__(self, url: str = "https://example.com") -> None:
        self.url = url
        self.interacted_element = []


class _GoodItem:
    def __init__(self) -> None:
        self.model_output = _FakeModelOutput([{"click": {"index": 0}}])
        self.state = _FakeState()
        self.result = []
        self.metadata = None


class _BoomItem:
    """An item whose `model_output` access raises — exercises the defensive
    per-step try/except. Non-AttributeError so getattr's default kwarg can't
    swallow it (Python: `getattr(x, name, default)` catches AttributeError
    only)."""

    @property
    def model_output(self):
        raise RuntimeError("simulated browser-use schema error")

    state = _FakeState()
    result = []
    metadata = None


class _FakeHistory:
    def __init__(self, items: list) -> None:
        self.history = items

    def screenshots(self):
        return []


def test_partial_progress_preserved_when_one_step_raises():
    """A single bad step must not zero out the whole trajectory."""
    history = _FakeHistory([_GoodItem(), _GoodItem(), _BoomItem(), _GoodItem()])

    traj = _history_to_trajectory(history, include_screenshots=False)

    assert len(traj) == 4, f"expected 4 entries (3 good + 1 error), got {len(traj)}"
    # Steps 1, 2, 4 should be normal; step 3 should be an error placeholder.
    assert "ERROR" not in traj[0]["status"]
    assert "ERROR" not in traj[1]["status"]
    assert "ERROR" in traj[2]["status"]
    assert "RuntimeError" in traj[2]["status"]
    assert "simulated browser-use schema error" in traj[2]["status"]
    assert "ERROR" not in traj[3]["status"]
    # Step numbers stay 1-indexed and aligned with original positions.
    assert traj[0]["step"] == 1
    assert traj[2]["step"] == 3
    assert traj[3]["step"] == 4


def test_all_good_steps_no_regression():
    history = _FakeHistory([_GoodItem(), _GoodItem()])
    traj = _history_to_trajectory(history, include_screenshots=False)
    assert len(traj) == 2
    assert all("ERROR" not in s["status"] for s in traj)
