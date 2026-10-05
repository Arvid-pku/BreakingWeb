"""Solvability + near-miss proof for the hardened (v2) lms_peer_review_cycle task.

Drives the CORRECT solution through the REAL backend endpoint handler
(``submit_peer_review``) using a real ``SessionManager`` instance, then evaluates
via the canonical_diff evaluator. Also asserts several near-miss trajectories fail.

The v2 base partitions the pending set into a RETURNED subset (which must receive
the EXACT rule-derived corrected scores: previous + 2 capped at 5, else 3) and a
FRESH subset (any valid 1-5). Each comment must be >= 60 chars, address the
reviewee by first name, AND name the criterion that received that review's LOWEST
corrected score. These are precomputed per-review and exposed as seed targets:
``pending_review_req_scores`` (rid=clarity~depth~originality), ``pending_review_low_crit``
(rid:criterion) and ``pending_review_name_tokens`` (rid:first_name).

Method note: the correct path calls the route handler ``submit_peer_review`` directly
(passing the same SessionManager the session was created on). This is the real
backend mutation — identical to the HTTP path — and avoids the dual session-manager
problem of TestClient (which owns a separate manager via FastAPI dependency
injection). All backend gates (status guard, score sanitisation) are exercised.
"""

from __future__ import annotations

from breakingweb.backend.state import SessionManager
from breakingweb.backend.routes.lms import SubmitPeerReviewRequest, submit_peer_review
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task


TASK_ID = "lms_peer_review_cycle"
RUBRIC = ["clarity", "depth", "originality"]


def _make_session():
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="lms", task_id=TASK_ID, seed=42)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), state


def _pending_ids(targets: dict) -> list[str]:
    return [r.strip() for r in targets["pending_review_ids"].split(",") if r.strip()]


def _req_scores(targets: dict) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for entry in targets["pending_review_req_scores"].split("|"):
        rid, vec = entry.split("=")
        out[rid] = [int(s) for s in vec.split("~")]
    return out


def _low_crit(targets: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for entry in targets["pending_review_low_crit"].split("|"):
        rid, crit = entry.split(":", 1)
        out[rid] = crit
    return out


def _name_tokens(targets: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for entry in targets["pending_review_name_tokens"].split("|"):
        rid, name = entry.split(":", 1)
        out[rid] = name
    return out


def _correct_scores_for(rid: str, targets: dict) -> dict[str, int]:
    """The EXACT rule-derived corrected scores for the given review id."""
    c, d, o = _req_scores(targets)[rid]
    return {"clarity": c, "depth": d, "originality": o}


def _correct_comment_for(rid: str, targets: dict) -> str:
    first_name = _name_tokens(targets)[rid]
    crit = _low_crit(targets)[rid]
    return (
        f"{first_name}, the {crit} dimension is the weakest part of this submission "
        f"and needs the most improvement to lift the overall quality of the argument."
    )


def _submit(sm, sid, review_id, scores, comments):
    body = SubmitPeerReviewRequest(session_id=sid, rubric_scores=scores, comments=comments)
    return submit_peer_review(review_id=review_id, body=body, session_manager=sm)


def _evaluate(state, targets):
    return evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )


# ---------------------------------------------------------------------------
# Positive: correct trajectory passes
# ---------------------------------------------------------------------------

def test_correct_trajectory_passes():
    sm, sid, targets, state = _make_session()
    pending = _pending_ids(targets)
    assert len(pending) >= 4, f"expected a non-trivial pending set, got {pending}"

    # Sanity: there are >=2 returned-for-revision reviews carrying DISTINCT prior
    # scores (so they demand DIFFERENT exact corrected vectors — no uniform vector
    # passes both). This is the v2 discriminator.
    returned = sorted(r.strip() for r in targets["returned_review_ids"].split(",") if r.strip())
    assert len(returned) >= 2, f"expected >=2 returned reviews, got {returned}"
    req = _req_scores(targets)
    assert req[returned[0]] != req[returned[1]], (
        f"returned reviews should demand distinct exact vectors, got {req[returned[0]]} "
        f"and {req[returned[1]]}"
    )

    for rid in pending:
        _submit(sm, sid, rid, _correct_scores_for(rid, targets), _correct_comment_for(rid, targets))

    result = _evaluate(state, targets)
    assert result.get("success") is True, f"reasoning:\n{result.get('reasoning')}"
    assert result.get("score", 0.0) >= 0.99, result.get("score")
    # canonical_diff is richer than a 2-check legacy eval.
    assert len(result.get("checks", [])) + len(result.get("negative_checks", [])) > 2


# ---------------------------------------------------------------------------
# Near-miss A: the old "all 5s" shortcut (was the v1 exploit) now fails
# ---------------------------------------------------------------------------

def test_wrong_all_fives_shortcut_fails():
    sm, sid, targets, state = _make_session()
    pending = _pending_ids(targets)
    for rid in pending:
        # Uniform max vector. Strictly-higher than any previous score, but NOT the
        # exact rule-derived value for the returned reviews -> must fail update[0].
        _submit(sm, sid, rid, {"clarity": 5, "depth": 5, "originality": 5}, _correct_comment_for(rid, targets))

    result = _evaluate(state, targets)
    assert result.get("success") is False, f"reasoning:\n{result.get('reasoning')}"


# ---------------------------------------------------------------------------
# Near-miss B: off-by-one exact scores (applied +1 instead of +2) fails
# ---------------------------------------------------------------------------

def test_wrong_off_by_one_exact_scores_fails():
    sm, sid, targets, state = _make_session()
    pending = _pending_ids(targets)
    for rid in pending:
        scores = _correct_scores_for(rid, targets)
        scores["clarity"] = max(1, scores["clarity"] - 1)  # one point too low
        _submit(sm, sid, rid, scores, _correct_comment_for(rid, targets))

    result = _evaluate(state, targets)
    assert result.get("success") is False, f"reasoning:\n{result.get('reasoning')}"


# ---------------------------------------------------------------------------
# Near-miss C: comment names the WRONG (non-lowest) criterion -> fails
# ---------------------------------------------------------------------------

def test_wrong_comment_names_wrong_criterion_fails():
    sm, sid, targets, state = _make_session()
    pending = _pending_ids(targets)
    low = _low_crit(targets)
    name = _name_tokens(targets)
    for rid in pending:
        # Always blame "clarity"; for reviews whose true lowest criterion is NOT
        # clarity (the returned ones), this names the wrong criterion.
        wrong = "originality" if low[rid] == "clarity" else "clarity"
        comment = (
            f"{name[rid]}, the {wrong} dimension is the weakest part of this work "
            f"and needs the most improvement to lift the overall quality here."
        )
        _submit(sm, sid, rid, _correct_scores_for(rid, targets), comment)

    result = _evaluate(state, targets)
    assert result.get("success") is False, f"reasoning:\n{result.get('reasoning')}"


# ---------------------------------------------------------------------------
# Near-miss D: generic comment not addressed to the reviewee
# ---------------------------------------------------------------------------

def test_wrong_generic_comment_fails():
    sm, sid, targets, state = _make_session()
    pending = _pending_ids(targets)
    generic = (
        "Good clarity overall; please expand the depth of the analysis and add more "
        "originality in the conclusion section to strengthen the overall argument here."
    )
    for rid in pending:
        _submit(sm, sid, rid, _correct_scores_for(rid, targets), generic)

    result = _evaluate(state, targets)
    assert result.get("success") is False, f"reasoning:\n{result.get('reasoning')}"


# ---------------------------------------------------------------------------
# Near-miss E: comment too short (< 60 chars)
# ---------------------------------------------------------------------------

def test_wrong_short_comment_fails():
    sm, sid, targets, state = _make_session()
    pending = _pending_ids(targets)
    low = _low_crit(targets)
    name = _name_tokens(targets)
    for rid in pending:
        _submit(sm, sid, rid, _correct_scores_for(rid, targets), f"{name[rid]} {low[rid]} weak.")

    result = _evaluate(state, targets)
    assert result.get("success") is False, f"reasoning:\n{result.get('reasoning')}"


# ---------------------------------------------------------------------------
# Near-miss F: missing a criterion (only two rubric scores)
# ---------------------------------------------------------------------------

def test_wrong_missing_criterion_fails():
    sm, sid, targets, state = _make_session()
    pending = _pending_ids(targets)
    for rid in pending:
        scores = _correct_scores_for(rid, targets)
        scores.pop("originality", None)  # drop a criterion
        _submit(sm, sid, rid, scores, _correct_comment_for(rid, targets))

    result = _evaluate(state, targets)
    assert result.get("success") is False, f"reasoning:\n{result.get('reasoning')}"


# ---------------------------------------------------------------------------
# Near-miss G: leaves one pending review unsubmitted
# ---------------------------------------------------------------------------

def test_wrong_incomplete_fails():
    sm, sid, targets, state = _make_session()
    pending = _pending_ids(targets)
    for rid in pending[:-1]:  # skip the last pending review
        _submit(sm, sid, rid, _correct_scores_for(rid, targets), _correct_comment_for(rid, targets))

    result = _evaluate(state, targets)
    assert result.get("success") is False, f"reasoning:\n{result.get('reasoning')}"


# ---------------------------------------------------------------------------
# Freedom path (regression for the low_crit bug): fresh reviews "take any valid
# 1-5 score", so the comment must name the criterion lowest among the agent's
# OWN submitted scores — NOT a seed-fixed 'clarity'. The previous canonical_diff
# hard-required pending_review_low_crit (always 'clarity' for fresh reviews,
# being argmin of the unused 3~3~3 default), failing a correct agent that scored
# a different criterion lowest and named it.
# ---------------------------------------------------------------------------

_ORDER = ["clarity", "depth", "originality"]


def _lowest_crit(scores: dict) -> str:
    return min(_ORDER, key=lambda c: (int(scores[c]), _ORDER.index(c)))


def _comment_naming(first_name: str, crit: str) -> str:
    return (
        f"{first_name}, the {crit} dimension is the weakest part of this submission "
        f"and needs the most improvement to lift the overall quality of the work."
    )


def _fresh_ids(targets: dict) -> list[str]:
    returned = {r.strip() for r in targets["returned_review_ids"].split(",") if r.strip()}
    return [r for r in _pending_ids(targets) if r not in returned]


def test_fresh_review_nonuniform_scores_names_true_lowest_passes():
    sm, sid, targets, state = _make_session()
    fresh = _fresh_ids(targets)
    assert fresh, "expected at least one fresh (never-returned) pending review"
    names = _name_tokens(targets)
    returned = {r.strip() for r in targets["returned_review_ids"].split(",") if r.strip()}
    for rid in returned:  # returned reviews still need the exact rule-derived scores
        _submit(sm, sid, rid, _correct_scores_for(rid, targets), _correct_comment_for(rid, targets))
    fresh_scores = {"clarity": 5, "depth": 4, "originality": 2}  # lowest = originality, NOT clarity
    assert _lowest_crit(fresh_scores) == "originality"
    for rid in fresh:
        _submit(sm, sid, rid, dict(fresh_scores), _comment_naming(names[rid], "originality"))

    result = _evaluate(state, targets)
    assert result.get("success") is True, f"reasoning:\n{result.get('reasoning')}"
    assert result.get("score", 0.0) >= 0.99, result.get("score")


def test_fresh_review_names_nonlowest_criterion_fails():
    sm, sid, targets, state = _make_session()
    fresh = _fresh_ids(targets)
    names = _name_tokens(targets)
    returned = {r.strip() for r in targets["returned_review_ids"].split(",") if r.strip()}
    for rid in returned:
        _submit(sm, sid, rid, _correct_scores_for(rid, targets), _correct_comment_for(rid, targets))
    fresh_scores = {"clarity": 5, "depth": 4, "originality": 2}  # lowest = originality
    for rid in fresh:
        # Names 'clarity' (the agent's HIGHEST score), not the true lowest -> must fail.
        _submit(sm, sid, rid, dict(fresh_scores), _comment_naming(names[rid], "clarity"))

    result = _evaluate(state, targets)
    assert result.get("success") is False, f"reasoning:\n{result.get('reasoning')}"
