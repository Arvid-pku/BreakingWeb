"""Deterministic seed-stability tests for the Amazon environment.

Verifies that:
- Same (task_id, seed) pair always produces identical state
- Comparison task targets are genuinely the best/cheapest/highest across all seeds 0-19
- Pre-seeded account state does not contaminate task checks
- Decoy count is sufficient for comparison tasks
"""
import pytest
from breakingweb.backend.state import SessionManager
from breakingweb.tasks._registry import load_all_tasks, get_task

@pytest.fixture(scope="module")
def all_tasks():
    load_all_tasks.cache_clear()
    return load_all_tasks()

class TestAmazonSeedStability:
    def test_deterministic_seeds(self):
        """Same (task_id, seed) pair produces identical product count and order."""
        sm1 = SessionManager()
        sm2 = SessionManager()
        sid1, t1, _ = sm1.create_session("amazon", "amazon_search_and_buy", seed=42)
        sid2, t2, _ = sm2.create_session("amazon", "amazon_search_and_buy", seed=42)
        s1 = sm1.get(sid1)
        s2 = sm2.get(sid2)
        assert len(s1.products) == len(s2.products)
        assert t1 == t2
        assert [p.name for p in s1.products] == [p.name for p in s2.products]

    @pytest.mark.parametrize("seed", range(20))
    def test_buy_highest_rated_target_valid(self, seed):
        """Target product must actually have the highest rating across all seeds."""
        sm = SessionManager()
        sid, targets, _ = sm.create_session("amazon", "amazon_buy_highest_rated", seed=seed)
        state = sm.get(sid)
        target = state.get_product(targets["best_product_id"])
        assert target is not None
        max_rating = max(p.rating for p in state.products)
        assert target.rating >= max_rating, f"Seed {seed}: target={target.rating}, max={max_rating}"

    @pytest.mark.parametrize("seed", range(20))
    def test_compare_cheapest_target_valid(self, seed):
        """Target product must be cheapest eligible speaker across all seeds."""
        sm = SessionManager()
        sid, targets, _ = sm.create_session("amazon", "amazon_compare_and_buy_cheapest", seed=seed)
        state = sm.get(sid)
        target = state.get_product(targets["cheapest_product_id"])
        assert target is not None
        speakers = [p for p in state.products if "speaker" in p.name.lower() and p.rating >= 4.0 and p.in_stock]
        if speakers:
            min_price = min(p.price for p in speakers)
            assert target.price <= min_price, f"Seed {seed}: target=${target.price}, min=${min_price}"

    @pytest.mark.parametrize("seed", range(20))
    def test_deal_hunter_target_valid(self, seed):
        """Target product must have the biggest discount percentage across all seeds."""
        sm = SessionManager()
        sid, targets, _ = sm.create_session("amazon", "amazon_deal_hunter", seed=seed)
        state = sm.get(sid)
        target = state.get_product(targets["deal_product_id"])
        assert target is not None
        assert target.list_price is not None and target.list_price > target.price
        target_disc = (target.list_price - target.price) / target.list_price
        for p in state.products:
            if p.list_price and p.list_price > p.price and p.id != target.id:
                disc = (p.list_price - p.price) / p.list_price
                assert target_disc >= disc - 0.001, f"Seed {seed}: target={target_disc:.1%}, {p.name}={disc:.1%}"

    @pytest.mark.parametrize("seed", range(20))
    def test_price_comparison_has_enough_candidates(self, seed):
        """Price comparison must have at least 3 products in the $50-$100 range within the target category."""
        sm = SessionManager()
        sid, targets, _ = sm.create_session("amazon", "amazon_price_comparison", seed=seed)
        state = sm.get(sid)
        category = targets.get("category", "Home & Kitchen")
        in_range = [p for p in state.products if 50 <= p.price <= 100 and p.category == category and p.in_stock]
        assert len(in_range) >= 3, f"Seed {seed}: only {len(in_range)} {category} products in $50-$100"

    def test_no_trivial_pass_on_empty_trajectory(self, all_tasks):
        """No Amazon task should fully pass with zero agent actions."""
        from breakingweb.tasks._evaluator import evaluate as unified_evaluate
        sm = SessionManager()
        trivial_passes = []
        for task_id, task in all_tasks.items():
            if task.env_id != "amazon":
                continue
            sid, _, _ = sm.create_session("amazon", task_id)
            state = sm.get(sid)
            result = unified_evaluate(task, server_state=state, targets=state.resolved_targets, trajectory=[])
            if result["success"]:
                trivial_passes.append(task_id)
        assert not trivial_passes, f"Tasks trivially pass with no actions: {trivial_passes}"
