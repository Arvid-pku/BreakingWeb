"""Solvability proof for the hardened pp_resolve_schedule_conflicts task (v2).

The task seeds several groups of double/triple-booked appointments that share
an exact date+time. In each group exactly one appointment was booked first
(earliest ``booked_at``, tie-break lexicographic id) and must be KEPT; every
other (later-booked) member of the group must be CANCELLED. Non-conflicting
upcoming appointments must be left untouched.

The v2 upgrade adds two discrimination traps on top of the multi-cluster core:

* A ``keeper_trap`` cluster where the earliest-booked keeper deliberately sits
  on a *specialist* provider with a ``telehealth`` visit type while the
  later-booked duplicates sit on the PCP with ``in-person`` — so a naive
  "keep the PCP / in-person one" heuristic cancels the keeper.
* ``pseudo_conflict`` decoy groups where a scheduled appointment shares its
  exact datetime with an already-``completed`` appointment. These are NOT real
  conflicts (only one member is scheduled), so the scheduled survivor must be
  LEFT scheduled. An agent that groups by datetime without first filtering to
  ``status == 'scheduled'`` will cancel it (a critical over-cancellation).

The CORRECT solution is driven through the REAL backend cancel endpoint
(POST /api/env/patient_portal/appointments/{id}/cancel) using the seed's
precomputed ``cluster_cancel_apt_ids`` as the intended answer. WRONG
trajectories (cancelling the keeper, a pseudo-conflict survivor, a
non-conflicting appointment, or missing one duplicate) are asserted to fail.
"""

from collections import defaultdict

from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task


_TASK_ID = "pp_resolve_schedule_conflicts"
_CANCEL_URL = "/api/env/patient_portal/appointments/{aid}/cancel"


def _seed_session():
    """Create a seeded session on the app's SessionManager.

    Returns ``(client, sid, targets, state)``. The state is the live object the
    routes mutate, so post-cancel it reflects the real backend mutations.
    """
    client = TestClient(app)
    sm = app.state.session_manager
    sid, targets, _ = sm.create_session(
        env_id="patient_portal", task_id=_TASK_ID, seed=42
    )
    state = sm.get_state(sid)
    return client, sid, dict(targets), state


def test_seed_partition_is_a_valid_earliest_booked_grouping():
    """The precomputed keep/cancel sets match the group-by-datetime +
    earliest-booked tie-break the agent must re-derive over the SCHEDULED
    cluster members, and the only same-datetime scheduled groups are the
    conflict clusters."""
    _client, _sid, targets, state = _seed_session()

    cancel = set(targets["cluster_cancel_apt_ids"])
    keep = set(targets["cluster_keep_apt_ids"])
    cluster_all = set(targets["cluster_all_apt_ids"])
    pseudo = set(targets["pseudo_conflict_apt_ids"])

    assert cancel, "expected a non-empty cancel set"
    assert keep, "expected a non-empty keep set"
    assert cancel.isdisjoint(keep)
    assert cancel | keep == cluster_all
    # Multi-group, multi-cancel scenario (v2: clusters [3,3,2] => keep 3 /
    # cancel 5), genuinely harder than the v1 [3,2,2].
    assert len(keep) >= 3
    assert len(cancel) >= 5
    # Pseudo-conflict survivors exist and are disjoint from the cluster ids.
    assert len(pseudo) >= 2
    assert pseudo.isdisjoint(cluster_all)

    # Re-derive the partition from raw state (only scheduled cluster members)
    # and confirm it matches.
    by_dt: dict[str, list] = defaultdict(list)
    for a in state.appointments:
        if a.id in cluster_all and a.status == "scheduled":
            by_dt[a.datetime.isoformat()].append(a)
    derived_keep, derived_cancel = set(), set()
    for _dt, apts in by_dt.items():
        assert len(apts) >= 2, "every cluster group must be a real conflict"
        apts_sorted = sorted(apts, key=lambda a: (a.booked_at, a.id))
        derived_keep.add(apts_sorted[0].id)
        derived_cancel.update(a.id for a in apts_sorted[1:])
    assert derived_keep == keep
    assert derived_cancel == cancel

    # Keeper-trap: at least one cluster's keeper is on a different provider AND
    # visit type than its later-booked duplicates (so heuristics misfire).
    trap_seen = False
    for _dt, apts in by_dt.items():
        apts_sorted = sorted(apts, key=lambda a: (a.booked_at, a.id))
        keeper = apts_sorted[0]
        dups = apts_sorted[1:]
        if keeper.type not in {d.type for d in dups} and keeper.provider_id not in {
            d.provider_id for d in dups
        }:
            trap_seen = True
    assert trap_seen, "expected a keeper-off-provider/type trap cluster"

    # Pseudo-conflict survivors share a datetime with a COMPLETED appointment
    # (so they LOOK double-booked) but are the only scheduled member there.
    for pid in pseudo:
        a = state.get_appointment(pid)
        assert a is not None and a.status == "scheduled"
        sharers = [
            o for o in state.appointments if o.datetime == a.datetime and o.id != pid
        ]
        assert sharers, "pseudo survivor must share a slot with a decoy"
        assert all(o.status != "scheduled" for o in sharers), (
            "pseudo decoys must be non-scheduled so the survivor is not a real conflict"
        )

    # No NON-cluster scheduled appointment may share a datetime with another
    # scheduled appointment (otherwise the instruction would imply cancelling
    # outside the precomputed set).
    all_sched: dict[str, list] = defaultdict(list)
    for a in state.appointments:
        if a.status == "scheduled":
            all_sched[a.datetime.isoformat()].append(a.id)
    for _dt, ids in all_sched.items():
        if len(ids) > 1:
            assert all(i in cluster_all for i in ids), (
                f"stray non-cluster conflict at {_dt}: {ids}"
            )


def test_correct_trajectory_via_real_endpoint_passes():
    """Cancelling exactly the later-booked duplicate of every group via the
    real cancel endpoint evaluates to success."""
    client, sid, targets, state = _seed_session()

    for aid in targets["cluster_cancel_apt_ids"]:
        resp = client.post(
            _CANCEL_URL.format(aid=aid),
            json={"session_id": sid, "reason": "Duplicate booking for the same slot"},
        )
        assert resp.status_code == 200, (aid, resp.status_code, resp.text)
        assert resp.json()["status"] == "cancelled"

    # Keepers and non-conflicting appointments must remain scheduled.
    for aid in targets["cluster_keep_apt_ids"]:
        assert state.get_appointment(aid).status == "scheduled"
    # Pseudo-conflict survivors must remain scheduled.
    for aid in targets["pseudo_conflict_apt_ids"]:
        assert state.get_appointment(aid).status == "scheduled"

    result = evaluate(
        task=get_task(_TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99, f"result: {result}"
    # Richer than the legacy single-update eval.
    assert len(result.get("checks", [])) + len(result.get("negative_checks", [])) > 2


def test_cancelling_earliest_keeper_fails():
    """Near-miss: cancelling a group's earliest-booked keeper (instead of the
    later-booked duplicate) must fail — it both leaves a cancel slot unmet and
    trips the critical 'keeper remains scheduled' constraint. Uses the
    keeper-trap cluster whose keeper sits on a specialist/telehealth."""
    client, sid, targets, state = _seed_session()

    cancel = list(targets["cluster_cancel_apt_ids"])
    keep = list(targets["cluster_keep_apt_ids"])

    # Cancel all-but-one of the correct duplicates, then cancel a KEEPER
    # instead of the remaining duplicate.
    for aid in cancel[:-1]:
        resp = client.post(
            _CANCEL_URL.format(aid=aid),
            json={"session_id": sid},
        )
        assert resp.status_code == 200
    # Pick the keeper that is on a different provider/type than its duplicates
    # (the trap keeper) if discoverable; otherwise the first keeper.
    by_dt: dict[str, list] = defaultdict(list)
    cluster_all = set(targets["cluster_all_apt_ids"])
    for a in state.appointments:
        if a.id in cluster_all and a.status in ("scheduled",):
            by_dt[a.datetime.isoformat()].append(a)
    trap_keeper = None
    for _dt, apts in by_dt.items():
        apts_sorted = sorted(apts, key=lambda a: (a.booked_at, a.id))
        k = apts_sorted[0]
        dups = apts_sorted[1:]
        if dups and k.type not in {d.type for d in dups}:
            trap_keeper = k.id
            break
    wrong = trap_keeper or keep[0]
    resp = client.post(_CANCEL_URL.format(aid=wrong), json={"session_id": sid})
    assert resp.status_code == 200
    assert state.get_appointment(wrong).status == "cancelled"

    result = evaluate(
        task=get_task(_TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"expected failure, got: {result}"


def test_cancelling_pseudo_conflict_survivor_fails():
    """Near-miss: cancelling a scheduled appointment that only shares a slot
    with a COMPLETED appointment (a pseudo-conflict, not a real conflict) must
    fail the critical status-filter constraint, even when the real cancel set
    is otherwise correct."""
    client, sid, targets, state = _seed_session()

    # Do the correct cancels first.
    for aid in targets["cluster_cancel_apt_ids"]:
        resp = client.post(_CANCEL_URL.format(aid=aid), json={"session_id": sid})
        assert resp.status_code == 200

    # Then cancel a pseudo-conflict survivor (the tempting status-filter trap).
    survivor = targets["pseudo_conflict_apt_ids"][0]
    resp = client.post(_CANCEL_URL.format(aid=survivor), json={"session_id": sid})
    assert resp.status_code == 200
    assert state.get_appointment(survivor).status == "cancelled"

    result = evaluate(
        task=get_task(_TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"expected failure, got: {result}"


def test_cancelling_a_non_conflicting_appointment_fails():
    """Near-miss: cancelling a non-conflicting upcoming appointment in addition
    to the correct set must fail the invariant freezing all non-cancel rows."""
    client, sid, targets, state = _seed_session()

    cluster_all = set(targets["cluster_all_apt_ids"])
    pseudo = set(targets["pseudo_conflict_apt_ids"])

    # Do the correct cancels first.
    for aid in targets["cluster_cancel_apt_ids"]:
        resp = client.post(_CANCEL_URL.format(aid=aid), json={"session_id": sid})
        assert resp.status_code == 200

    # Then cancel one extra scheduled appointment that is NOT a conflict member
    # and NOT a pseudo survivor.
    extra = next(
        a for a in state.appointments
        if a.status == "scheduled"
        and a.id not in cluster_all
        and a.id not in pseudo
    )
    resp = client.post(_CANCEL_URL.format(aid=extra.id), json={"session_id": sid})
    assert resp.status_code == 200

    result = evaluate(
        task=get_task(_TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"expected failure, got: {result}"


def test_under_cancelling_one_duplicate_fails():
    """Near-miss: missing a single later-booked duplicate (cancel 4 of 5) must
    fail the saturating cancel bijection and the 'every duplicate cancelled'
    critical constraint."""
    client, sid, targets, state = _seed_session()

    for aid in targets["cluster_cancel_apt_ids"][:-1]:
        resp = client.post(_CANCEL_URL.format(aid=aid), json={"session_id": sid})
        assert resp.status_code == 200

    result = evaluate(
        task=get_task(_TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"expected failure, got: {result}"
