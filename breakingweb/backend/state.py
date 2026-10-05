from __future__ import annotations

import random
import threading
import uuid
from collections.abc import Callable
from typing import Any

from .models.base import AuditEntry, BaseEnvState
from .models.amazon import AmazonState
from .models.booking import BookingState
from .models.gmail import GmailState
from .models.lms import LMSState
from .models.patient_portal import PatientPortalState
from .models.reddit import RedditState
from .models.robinhood import RobinhoodState
from .seeder import FakeDataGenerator, derive_seed
from .seeders import SEEDER_REGISTRY


STATE_TYPES: dict[str, type[BaseEnvState]] = {
    "amazon": AmazonState,
    "booking": BookingState,
    "gmail": GmailState,
    "lms": LMSState,
    "patient_portal": PatientPortalState,
    "reddit": RedditState,
    "robinhood": RobinhoodState,
}


class SessionManager:
    """In-memory session state for advanced BreakingWeb environments."""

    def __init__(self):
        self._sessions: dict[str, BaseEnvState] = {}
        self._initial_snapshots: dict[str, BaseEnvState] = {}
        self._lock = threading.RLock()

    def create_session(self, env_id: str, task_id: str, seed: int | None = None) -> tuple[str, dict[str, Any], int]:
        runner = SEEDER_REGISTRY.get(env_id)
        state_cls = STATE_TYPES.get(env_id)
        if runner is None or state_cls is None:
            raise KeyError(f"Unknown environment: {env_id}")
        actual_seed = seed if seed is not None else derive_seed(f"{env_id}:{task_id}")
        from breakingweb.tasks._registry import get_task
        task = get_task(task_id)
        rng = random.Random(actual_seed)
        fake = FakeDataGenerator(actual_seed)
        seeded_data, resolved_targets = runner.run(task, actual_seed, fake, rng)
        # Every session carries a session_start timestamp so diff checks can
        # window over "changes since session creation". Use the seed-derived
        # anchor time so (task_id, seed) remains fully deterministic — tests
        # like test_deterministic_seeds compare target dicts for equality.
        from breakingweb.backend.seeder import derive_anchor_time
        resolved_targets["session_start"] = derive_anchor_time(actual_seed).isoformat()
        state = state_cls.model_validate(seeded_data)
        state._resolved_targets = dict(resolved_targets)
        state._seed = actual_seed

        # Initialize price engine for robinhood tasks with trajectories
        if env_id == "robinhood":
            from breakingweb.tasks._schema import PriceTrajectoryConfig
            pt = getattr(task.seed, 'price_trajectory', None) if task.seed else None
            if pt is not None and isinstance(pt, PriceTrajectoryConfig) and pt.stocks:
                from breakingweb.backend.price_engine import PriceEngine, TrajectoryConfig, StockTrajectory
                tconfig = TrajectoryConfig(
                    tick_interval_seconds=pt.tick_interval_seconds,
                    stocks={
                        sym: StockTrajectory(keyframes=ts.keyframes, noise_pct=ts.noise_pct)
                        for sym, ts in pt.stocks.items()
                    },
                )
                state._price_engine = PriceEngine(config=tconfig, seed=actual_seed)

                # Sync seeded stock quotes to trajectory tick-0 prices so the
                # initial prices visible to the agent match the task description
                # and trajectory start, rather than the randomly seeded values.
                from decimal import Decimal as _Dec
                for stock in state.stocks:
                    if stock.symbol in tconfig.stocks:
                        tick0_price = state._price_engine.price_at_tick(stock.symbol, 0)
                        stock.price = tick0_price
                        stock.bid = tick0_price - _Dec("0.01")
                        stock.ask = tick0_price + _Dec("0.01")
                        stock.day_change = tick0_price - stock.previous_close
                        stock.day_change_pct = (
                            _Dec(str(round(float(stock.day_change) / float(stock.previous_close) * 100, 2)))
                            if stock.previous_close != 0 else _Dec("0")
                        )
                # Also sync positions that hold trajectory stocks
                for pos in state.positions:
                    if pos.symbol in tconfig.stocks:
                        tick0_price = state._price_engine.price_at_tick(pos.symbol, 0)
                        pos.current_price = tick0_price
                        cost_total = pos.avg_cost_basis * pos.quantity
                        market_total = tick0_price * pos.quantity
                        pos.total_return = market_total - cost_total
                        pos.total_return_pct = (
                            _Dec(str(round(float(pos.total_return) / float(cost_total) * 100, 2)))
                            if cost_total != 0 else _Dec("0")
                        )

        # Capture baseline snapshot for evaluator filters (e.g. ``o.id not in
        # state._initial_snapshot.get('orders', {})``). REST session routes may
        # re-capture this after applying degradation; this default makes the
        # snapshot available to tests and callers that skip degradation.
        if hasattr(state, "state_snapshot"):
            state._initial_snapshot = state.state_snapshot()

        session_id = f"{env_id}_{task_id}_{uuid.uuid4().hex[:10]}"
        # Take a post-seed snapshot of the state so the canonical_diff
        # evaluator can compute a net diff later. Deep-copy isolates the
        # snapshot from subsequent agent mutations (spec §7.5).
        initial_snapshot = state.model_copy(deep=True)
        state._initial_state_copy = initial_snapshot
        with self._lock:
            self._sessions[session_id] = state
            self._initial_snapshots[session_id] = initial_snapshot
        return session_id, resolved_targets, actual_seed

    def get(self, session_id: str) -> BaseEnvState:
        with self._lock:
            try:
                return self._sessions[session_id]
            except KeyError as exc:
                raise KeyError(f"Unknown session_id: {session_id}") from exc

    def destroy(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)
            self._initial_snapshots.pop(session_id, None)

    def get_initial_snapshot(self, session_id: str) -> BaseEnvState | None:
        """Return the post-seed snapshot of session state (taken at creation time).

        This is the reference point for compute_diff during evaluation.
        Returns None if the session is unknown or has no snapshot.
        """
        with self._lock:
            return self._initial_snapshots.get(session_id)

    def get_targets(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            return self.get(session_id).resolved_targets

    def set_benchmark_state(self, session_id: str, benchmark_state: dict[str, Any]) -> None:
        with self._lock:
            state = self._sessions.get(session_id)
            if state is None:
                raise KeyError(f"Unknown session_id: {session_id}")
            state.set_benchmark_state(benchmark_state)
            state.audit_log.append(
                AuditEntry(
                    action="benchmark_state.capture",
                    payload={"keys": sorted(benchmark_state.keys())},
                    summary="Captured client benchmark state",
                    snapshot={"completed": bool(benchmark_state.get("completed"))},
                )
            )

    def mutate(
        self,
        session_id: str,
        action: str,
        payload: dict[str, Any],
        mutator: Callable[[BaseEnvState], Any],
    ) -> Any:
        with self._lock:
            state = self.get(session_id)
            result = mutator(state)
            state.touch()
            state.audit_log.append(
                AuditEntry(
                    action=action,
                    payload=payload,
                    summary=self._summarize_result(result),
                    snapshot=self._snapshot(state),
                )
            )
            return result

    def session_summary(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            state = self.get(session_id)
            summary = {
                "session_id": session_id,
                "env_id": state.env_id,
                "task_id": state.task_id,
                "seed": state.seed,
                "created_at": state.created_at,
                "updated_at": state.updated_at,
                "audit_entries": len(state.audit_log),
            }
            if state.degradation:
                summary["degradation"] = state.degradation
            if hasattr(state, "session_summary"):
                summary["state"] = state.session_summary()
            return summary

    def _summarize_result(self, result: Any) -> str:
        if isinstance(result, BaseEnvState):
            return f"{result.env_id}:{result.task_id}"
        if hasattr(result, "id"):
            return f"{type(result).__name__}:{getattr(result, 'id', '')}"
        if isinstance(result, dict):
            return f"dict[{', '.join(sorted(result.keys())[:4])}]"
        if isinstance(result, list):
            return f"list[{len(result)}]"
        return str(result)

    def _snapshot(self, state: BaseEnvState) -> dict[str, Any]:
        snapshot = {"task_id": state.task_id, "audit_entries": len(state.audit_log) + 1}
        if hasattr(state, "session_summary"):
            summary = state.session_summary()
            if "counts" in summary:
                snapshot["counts"] = summary["counts"]
        return snapshot

    def get_state(self, session_id: str) -> BaseEnvState | None:
        """Return the session state or None if the session is unknown.

        A non-raising accessor intended for read-only inspection (tests, chat
        forwarding). Callers that require a 404 should use :meth:`get`.
        """
        with self._lock:
            return self._sessions.get(session_id)

    def append_chat_message(self, session_id: str, *, role: str, content: str) -> None:
        """Append an agent-produced chat message to the session's state.chat.

        No-op if the session doesn't exist (graceful degradation).
        """
        from .models.base import ChatMessage
        with self._lock:
            state = self._sessions.get(session_id)
            if state is None:
                return
            state.chat.append(ChatMessage(role=role, content=content))


def materialize_task_state(
    env_id: str, task_id: str, seed: int | None = None
) -> tuple:
    """Create a seeded task state without persisting it in a session.

    Returns ``(task, state, resolved_targets, actual_seed)``.
    """
    from breakingweb.tasks._registry import get_task

    runner = SEEDER_REGISTRY.get(env_id)
    state_cls = STATE_TYPES.get(env_id)
    if runner is None or state_cls is None:
        raise KeyError(f"Unknown environment: {env_id}")

    task = get_task(task_id)
    actual_seed = seed if seed is not None else derive_seed(f"{env_id}:{task_id}")
    rng = random.Random(actual_seed)
    fake = FakeDataGenerator(actual_seed)
    seeded_data, resolved_targets = runner.run(task, actual_seed, fake, rng)
    state = state_cls.model_validate(seeded_data)
    state._resolved_targets = dict(resolved_targets)
    state._seed = actual_seed
    if hasattr(state, "state_snapshot"):
        state._initial_snapshot = state.state_snapshot()
    # Mirror SessionManager.create_session: canonical_diff evaluation
    # expects a pydantic deep-copy of the post-seed state so that
    # filter/expression predicates can access fields via attribute
    # lookup uniformly.
    state._initial_state_copy = state.model_copy(deep=True)
    return task, state, resolved_targets, actual_seed
