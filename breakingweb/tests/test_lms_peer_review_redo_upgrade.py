"""Solvability proof for the v2-hardened lms_peer_review_redo task.

The upgraded task requires the agent to:
  * redo EVERY returned-for-revision peer review (a saturating bijection over
    target['returned_review_ids']), not just one;
  * apply a deterministic published scoring rule PER REVIEW (previous score + 2
    capped at 5; criteria with no previous score -> 3). Crucially each returned
    review now carries a DISTINCT previous_rubric_scores profile, so the
    rule-derived target triple differs per review (review_1 -> 5/3/3,
    review_2 -> 4/3/5, review_3 -> 3/5/3 for SEED 42) — the v1 "re-derive once,
    replay three times" shortcut no longer works. Every review exercises both
    rule branches (a +2->5 cap and an unscored->3 criterion);
  * write a fresh comment of at least 80 characters that addresses the reviewee
    by their first name (a per-review grounding discriminator);
  * leave every non-returned peer review (and all sibling collections) frozen,
    and send no messages.

The correct solution is driven through the REAL backend endpoint
``POST /api/env/lms/peer-reviews/{id}/submit`` via the Starlette TestClient
against the app's shared SessionManager, confirming the answer is achievable
past the real route (key sanitization + status guard). Near-miss trajectories
(constant triple replayed across reviews, wrong scores, partial redo, short
comment, name-omitting comment) must fail.
"""

from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task

TASK_ID = "lms_peer_review_redo"
SEED = 42


def _create_session():
    """Create a session on the app's shared SessionManager and return ids+targets."""
    sm = app.state.session_manager
    sid, targets, _ = sm.create_session(env_id="lms", task_id=TASK_ID, seed=SEED)
    return sm, sid, dict(targets)


def _returned_ids(targets: dict) -> list[str]:
    raw = targets["returned_review_ids"]
    return [r.strip() for r in raw.split(",") if r.strip()]


def _req_scores_by_rid(targets: dict) -> dict[str, dict[str, int]]:
    """Parse per-review required rubric triples from returned_req_scores.

    Format: "<rid>=<clarity>~<depth>~<originality>|...".
    """
    out: dict[str, dict[str, int]] = {}
    for entry in targets["returned_req_scores"].split("|"):
        if not entry.strip():
            continue
        rid, raw = entry.split("=", 1)
        clarity, depth, originality = (int(p) for p in raw.split("~"))
        out[rid.strip()] = {
            "clarity": clarity,
            "depth": depth,
            "originality": originality,
        }
    return out


def _first_names_by_rid(targets: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for entry in targets["returned_review_name_tokens"].split("|"):
        if not entry.strip():
            continue
        rid, name = entry.split(":", 1)
        out[rid.strip()] = name.strip()
    return out


def _good_comment(first_name: str) -> str:
    return (
        f"{first_name}, this reworked review now states a clear thesis, develops the "
        f"supporting evidence in real depth, and closes with an original reflection."
    )


def test_seed_shape_is_as_designed():
    """Three returned reviews, each with a DISTINCT rule-derived target triple."""
    sm, sid, targets = _create_session()
    state = sm.get_state(sid)

    returned = _returned_ids(targets)
    assert len(returned) == 3, f"expected 3 returned reviews, got {returned}"

    req = _req_scores_by_rid(targets)
    # Every returned review must have a per-rid required triple.
    assert set(req) == set(returned), (req, returned)
    # The triples must NOT all be identical — that is the whole point of the v2
    # per-review variation (defeats re-derive-once-and-replay).
    triples = {tuple(req[r][c] for c in ("clarity", "depth", "originality")) for r in returned}
    assert len(triples) == 3, f"per-review triples collapsed to {triples}"
    # Every triple must respect the rule range and hit the 5 cap on >=1 criterion
    # while leaving exactly one criterion at the unscored default of 3.
    for rid in returned:
        vals = req[rid]
        assert all(1 <= vals[c] <= 5 for c in vals), vals
        assert 5 in vals.values(), f"{rid} never hits the cap: {vals}"

    returned_set = set(returned)
    seen_returned = {r.id for r in state.peer_reviews if r.returned_for_revision}
    assert seen_returned == returned_set
    # There must be non-returned reviews to freeze (the standing wall).
    non_returned = [r for r in state.peer_reviews if not r.returned_for_revision]
    assert len(non_returned) >= 2

    # Each returned review carries its own previous_rubric_scores, and applying
    # the published rule to it must reproduce the exposed target triple.
    by_id = {r.id: r for r in state.peer_reviews}
    for rid in returned:
        prev = dict(by_id[rid].previous_rubric_scores)
        for crit in ("clarity", "depth", "originality"):
            expected = req[rid][crit]
            if crit in prev:
                assert expected == min(prev[crit] + 2, 5), (rid, crit, prev, expected)
            else:
                assert expected == 3, (rid, crit, expected)


def test_correct_trajectory_via_backend_passes():
    """Submitting every returned review with its OWN rule-derived triple passes."""
    sm, sid, targets = _create_session()
    client = TestClient(app)
    req = _req_scores_by_rid(targets)
    names = _first_names_by_rid(targets)

    for review_id in _returned_ids(targets):
        scores = req[review_id]
        resp = client.post(
            f"/api/env/lms/peer-reviews/{review_id}/submit",
            json={
                "session_id": sid,
                "rubric_scores": scores,
                "comments": _good_comment(names[review_id]),
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()["peer_review"]
        assert body["status"] == "submitted"
        assert body["rubric_scores"] == scores

    state = sm.get_state(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99, f"score too low: {result}"
    # Richer than the legacy 2-check eval (bijection + standing-wall invariants).
    assert len(result.get("checks", [])) + len(result.get("negative_checks", [])) > 2


def test_constant_triple_replay_fails():
    """Applying ONE review's correct triple to ALL three must fail.

    This is the v1 shortcut the hardening targets: re-derive once and replay.
    Because the per-review previous scores differ, a single triple is wrong on
    at least one of the other two reviews.
    """
    sm, sid, targets = _create_session()
    client = TestClient(app)
    req = _req_scores_by_rid(targets)
    names = _first_names_by_rid(targets)
    returned = _returned_ids(targets)
    # The triple that is correct only for the FIRST review.
    constant = req[returned[0]]

    for review_id in returned:
        resp = client.post(
            f"/api/env/lms/peer-reviews/{review_id}/submit",
            json={
                "session_id": sid,
                "rubric_scores": constant,
                "comments": _good_comment(names[review_id]),
            },
        )
        assert resp.status_code == 200, resp.text

    state = sm.get_state(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"constant-triple replay should fail: {result}"


def test_wrong_scores_fail():
    """Ignoring the scoring rule (all 5s) must fail the exact-value predicate."""
    sm, sid, targets = _create_session()
    client = TestClient(app)
    names = _first_names_by_rid(targets)
    wrong_scores = {"clarity": 5, "depth": 5, "originality": 5}

    for review_id in _returned_ids(targets):
        resp = client.post(
            f"/api/env/lms/peer-reviews/{review_id}/submit",
            json={
                "session_id": sid,
                "rubric_scores": wrong_scores,
                "comments": _good_comment(names[review_id]),
            },
        )
        assert resp.status_code == 200, resp.text

    state = sm.get_state(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"wrong scores should fail: {result}"


def test_incomplete_only_one_review_fails():
    """Redoing only one of three returned reviews must fail the bijection."""
    sm, sid, targets = _create_session()
    client = TestClient(app)
    req = _req_scores_by_rid(targets)
    names = _first_names_by_rid(targets)

    only = _returned_ids(targets)[0]
    resp = client.post(
        f"/api/env/lms/peer-reviews/{only}/submit",
        json={
            "session_id": sid,
            "rubric_scores": req[only],
            "comments": _good_comment(names[only]),
        },
    )
    assert resp.status_code == 200, resp.text

    state = sm.get_state(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"partial redo should fail: {result}"


def test_short_comment_fails():
    """Correct scores but a too-short comment (<80 chars) must fail."""
    sm, sid, targets = _create_session()
    client = TestClient(app)
    req = _req_scores_by_rid(targets)
    short = "Looks fine now."

    for review_id in _returned_ids(targets):
        resp = client.post(
            f"/api/env/lms/peer-reviews/{review_id}/submit",
            json={
                "session_id": sid,
                "rubric_scores": req[review_id],
                "comments": short,
            },
        )
        assert resp.status_code == 200, resp.text

    state = sm.get_state(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"short comment should fail: {result}"


def test_comment_missing_reviewee_name_fails():
    """Correct scores + long comment, but the comment omits the reviewee first
    name -> the per-review grounding discriminator must fail."""
    sm, sid, targets = _create_session()
    client = TestClient(app)
    req = _req_scores_by_rid(targets)
    # A long, generic comment that mentions no name at all.
    nameless = (
        "This reworked review now states a clear thesis, develops the supporting "
        "evidence in real depth, and closes with an original, well-grounded reflection."
    )

    for review_id in _returned_ids(targets):
        resp = client.post(
            f"/api/env/lms/peer-reviews/{review_id}/submit",
            json={
                "session_id": sid,
                "rubric_scores": req[review_id],
                "comments": nameless,
            },
        )
        assert resp.status_code == 200, resp.text

    state = sm.get_state(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"name-omitting comment should fail: {result}"
