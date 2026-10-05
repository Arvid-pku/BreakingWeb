"""Gmail canary trajectory suite.

Simulates correct API-level actions to verify that:
  1. Core easy Gmail tasks are still solvable (score = 1.0).
  2. Managed retry variants fire exactly where expected and remain solvable.
  3. Managed decoy / exploration variants inject the intended state without
     breaking the benchmark contract.

These tests intentionally track the current task and variant inventory rather
than older primitive-name canaries.
"""

from __future__ import annotations

import re

import pytest
from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.backend.security import CONTROLLER_SECRET_HEADER
from breakingweb.backend.state import materialize_task_state
from breakingweb.injector.middleware import clear_all_degradations
from breakingweb.runner import controller_headers, ensure_controller_secret


SEED = 42
EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")
QUOTED_STRING_RE = re.compile(r'"([^"]+)"')


@pytest.fixture(autouse=True)
def _clean():
    clear_all_degradations()
    yield
    clear_all_degradations()


@pytest.fixture()
def client():
    app.state.controller_secret = ensure_controller_secret()
    return TestClient(app)


def _targets(task_id: str, seed: int) -> dict:
    _, _, resolved_targets, _ = materialize_task_state("gmail", task_id, seed)
    return resolved_targets


def _gmail_state(sid: str):
    """Live GmailState for a session id, read from the app's SessionManager."""
    return app.state.session_manager.get(sid)


def _instruction_text(task_id: str) -> str:
    from breakingweb.tasks._registry import get_task
    task = get_task(task_id)
    return (task.instruction_template or "") if hasattr(task, "instruction_template") else ""


def _instruction_quotes(task_id: str) -> list[str]:
    """Return double-quoted strings found in the task's instruction template."""
    return QUOTED_STRING_RE.findall(_instruction_text(task_id))


def _instruction_emails(task_id: str) -> list[str]:
    """Return email addresses found in the task's instruction template."""
    return EMAIL_RE.findall(_instruction_text(task_id))


def _session(client: TestClient, task_id: str, seed: int = SEED, **kw) -> dict:
    r = client.post(
        "/api/env/gmail/session",
        json={"task_id": task_id, "seed": seed, **kw},
        headers=controller_headers(),
    )
    assert r.status_code == 200, r.text
    data = r.json()
    data["resolved_targets"] = _targets(task_id, seed)
    return data


def _eval(client: TestClient, sid: str, task_id: str, benchmark_state=None) -> dict:
    payload = {"session_id": sid, "task_id": task_id}
    if benchmark_state is not None:
        payload["benchmark_state"] = benchmark_state
    r = client.post("/api/env/gmail/evaluate", json=payload, headers=controller_headers())
    assert r.status_code == 200, r.text
    return r.json()


def _ref(sid: str) -> dict:
    return {"Referer": f"http://testserver/env/gmail/inbox?session={sid}"}


def _star(client: TestClient, sid: str, email_id: str):
    return client.post(
        f"/api/env/gmail/emails/{email_id}/star",
        json={"session_id": sid},
        headers=_ref(sid),
    )


def _send(client: TestClient, sid: str, **kw):
    return client.post(
        "/api/env/gmail/send",
        json={"session_id": sid, **kw},
        headers=_ref(sid),
    )


def _delete(client: TestClient, sid: str, email_id: str):
    return client.post(
        f"/api/env/gmail/emails/{email_id}/delete",
        json={"session_id": sid},
        headers=_ref(sid),
    )


def _forward(client: TestClient, sid: str, email_id: str, to, body: str = "", cc=None):
    payload = {"session_id": sid, "to": to, "body": body}
    if cc is not None:
        payload["cc"] = cc
    return client.post(
        f"/api/env/gmail/emails/{email_id}/forward",
        json=payload,
        headers=_ref(sid),
    )


def _search(client: TestClient, sid: str, q: str):
    return client.get(
        f"/api/env/gmail/search?session_id={sid}&q={q}",
        headers=_ref(sid),
    )


def _emails(client: TestClient, sid: str, label: str = "inbox", page_size: int = 25):
    return client.get(
        f"/api/env/gmail/emails?session_id={sid}&label={label}&page_size={page_size}",
        headers=_ref(sid),
    )


def _filters(client: TestClient, sid: str):
    return client.get(
        f"/api/env/gmail/filters?session_id={sid}",
        headers=_ref(sid),
    )


def _delete_filter(client: TestClient, sid: str, filter_id: str):
    return client.delete(
        f"/api/env/gmail/filters/{filter_id}?session_id={sid}",
        headers=_ref(sid),
    )


def _create_label(client: TestClient, sid: str, name: str, color: str = "#1a73e8"):
    return client.post(
        "/api/env/gmail/labels",
        json={"session_id": sid, "name": name, "color": color},
        headers=_ref(sid),
    )


def _create_filter(
    client: TestClient,
    sid: str,
    *,
    name: str,
    query: str,
    from_addresses: list[str],
    add_labels: list[str],
    archive: bool,
):
    return client.post(
        "/api/env/gmail/filters",
        json={
            "session_id": sid,
            "name": name,
            "query": query,
            "from_addresses": from_addresses,
            "add_labels": add_labels,
            "archive": archive,
        },
        headers=_ref(sid),
    )


class TestStandardCanaries:
    def test_star_email(self, client: TestClient):
        s = _session(client, "gmail_star_email")
        _star(client, s["session_id"], s["resolved_targets"]["target_email_id"])
        ev = _eval(client, s["session_id"], "gmail_star_email")
        assert ev["success"] is True
        assert ev["score"] == 1.0

    def test_reply_simple(self, client: TestClient):
        s = _session(client, "gmail_reply_simple")
        sid = s["session_id"]
        target_id = s["resolved_targets"]["target_email_id"]
        # Derive reply-to from the seeded state — the canonical_diff expects
        # `to == [from_addr of original email]` and the seed uses a random
        # domain, so the address can't be hardcoded.
        target_email = _gmail_state(sid).get_email(target_id)
        _send(
            client,
            sid,
            to=[target_email.from_addr],
            subject="Re: Meeting Tomorrow at 2pm",
            body="I'll be there. Thanks!",
            in_reply_to=target_id,
        )
        ev = _eval(client, sid, "gmail_reply_simple")
        assert ev["success"] is True
        assert ev["score"] == 1.0

    def test_compose_new(self, client: TestClient):
        s = _session(client, "gmail_compose_new")
        _send(
            client,
            s["session_id"],
            to=["alice@thornton.com"],
            subject="Weekly Report",
            body="Hi Alice, please find the weekly report attached. Best regards.",
        )
        ev = _eval(client, s["session_id"], "gmail_compose_new")
        assert ev["success"] is True
        assert ev["score"] == 1.0

    def test_delete_spam(self, client: TestClient):
        s = _session(client, "gmail_delete_spam")
        _delete(client, s["session_id"], s["resolved_targets"]["spam_email_id"])
        ev = _eval(client, s["session_id"], "gmail_delete_spam")
        assert ev["success"] is True
        assert ev["score"] == 1.0

    def test_forward_email(self, client: TestClient):
        s = _session(client, "gmail_forward_email")
        _forward(
            client,
            s["session_id"],
            s["resolved_targets"]["target_email_id"],
            to=["dave@thornton.com"],
            body="Please review this invoice.",
        )
        ev = _eval(client, s["session_id"], "gmail_forward_email")
        assert ev["success"] is True
        assert ev["score"] == 1.0

    def test_search_and_star(self, client: TestClient):
        s = _session(client, "gmail_search_and_star")
        sid = s["session_id"]
        target = s["resolved_targets"]["target_email_id"]

        search = _search(client, sid, "Q4 Budget Summary")
        assert search.status_code == 200
        items = search.json()["items"]
        assert any(item["id"] == target for item in items)

        _star(client, sid, target)
        ev = _eval(client, sid, "gmail_search_and_star")
        assert ev["success"] is True
        assert ev["score"] == 1.0


class TestRetryVariants:
    def test_star_retry_requires_second_write(self, client: TestClient):
        s = _session(
            client,
            "gmail_star_email",
            variant_filename="gmail_star_email__star_retry.yaml",
        )
        sid = s["session_id"]
        target = s["resolved_targets"]["target_email_id"]

        # Variant uses silent_fail with fail_count=2: the first two POSTs
        # return a fake 200 body without persisting. The third POST actually
        # stars the email. Verification semantics: an agent must read the
        # email back and notice is_starred didn't flip, then retry.
        r1 = _star(client, sid, target)
        assert r1.status_code == 200, "silent_fail returns 200 with fake body"
        assert _gmail_state(sid).get_email(target).is_starred is False, (
            "first call should be silently failed — state must not change"
        )

        r2 = _star(client, sid, target)
        assert r2.status_code == 200
        assert _gmail_state(sid).get_email(target).is_starred is False, (
            "second call still within fail_count=2 — state still unchanged"
        )

        r3 = _star(client, sid, target)
        assert r3.status_code == 200
        assert _gmail_state(sid).get_email(target).is_starred is True, (
            "third call exceeds fail_count — real persistence kicks in"
        )

        ev = _eval(client, sid, "gmail_star_email")
        assert ev["success"] is True

    def test_reply_send_retry_requires_second_send(self, client: TestClient):
        s = _session(
            client,
            "gmail_reply_simple",
            variant_filename="gmail_reply_simple__send_retry.yaml",
        )
        sid = s["session_id"]
        target = s["resolved_targets"]["target_email_id"]
        target_email = _gmail_state(sid).get_email(target)
        reply_body = _instruction_quotes("gmail_reply_simple")[-1]
        # See test_reply_simple — derive address from seeded state, not hardcoded.
        reply_to = target_email.from_addr

        r1 = _send(
            client,
            sid,
            to=[reply_to],
            subject="Re: Meeting Tomorrow at 2pm",
            body="I'll be there. Thanks!",
            in_reply_to=target,
        )
        assert r1.status_code == 503

        ev_before = _eval(client, sid, "gmail_reply_simple")
        assert ev_before["success"] is False

        r2 = _send(
            client,
            sid,
            to=[reply_to],
            subject="Re: Meeting Tomorrow at 2pm",
            body="I'll be there. Thanks!",
            in_reply_to=target,
        )
        assert r2.status_code == 200

        ev = _eval(client, sid, "gmail_reply_simple")
        assert ev["success"] is True

    def test_compose_send_retry_requires_second_send(self, client: TestClient):
        s = _session(
            client,
            "gmail_compose_new",
            variant_filename="gmail_compose_new__send_retry.yaml",
        )
        sid = s["session_id"]
        compose_recipient = _instruction_emails("gmail_compose_new")[0]
        compose_subject, compose_body = _instruction_quotes("gmail_compose_new")

        r1 = _send(
            client,
            sid,
            to=["alice@thornton.com"],
            subject="Weekly Report",
            body="Hi Alice, please find the weekly report attached. Best regards.",
        )
        assert r1.status_code == 503

        ev_before = _eval(client, sid, "gmail_compose_new")
        assert ev_before["success"] is False

        r2 = _send(
            client,
            sid,
            to=["alice@thornton.com"],
            subject="Weekly Report",
            body="Hi Alice, please find the weekly report attached. Best regards.",
        )
        assert r2.status_code == 200

        ev = _eval(client, sid, "gmail_compose_new")
        assert ev["success"] is True

    def test_forward_retry_requires_second_forward(self, client: TestClient):
        s = _session(
            client,
            "gmail_forward_email",
            variant_filename="gmail_forward_email__forward_retry.yaml",
        )
        sid = s["session_id"]
        target = s["resolved_targets"]["target_email_id"]

        r1 = _forward(
            client,
            sid,
            target,
            to=["dave@thornton.com"],
            body="Please review this invoice.",
        )
        assert r1.status_code == 503

        ev_before = _eval(client, sid, "gmail_forward_email")
        assert ev_before["success"] is False

        r2 = _forward(
            client,
            sid,
            target,
            to=["dave@thornton.com"],
            body="Please review this invoice.",
        )
        assert r2.status_code == 200

        ev = _eval(client, sid, "gmail_forward_email")
        assert ev["success"] is True

    def test_filter_retry_requires_second_filter_write(self, client: TestClient):
        s = _session(
            client,
            "gmail_filter_repair_chain",
            variant_filename="gmail_filter_repair_chain__filter_retry.yaml",
        )
        sid = s["session_id"]

        label_resp = _create_label(client, sid, "Vendor/AcmeWidgets")
        assert label_resp.status_code == 200

        r1 = _create_filter(
            client,
            sid,
            name="Acme Widgets invoices",
            query="from:*@acmewidgets.com",
            from_addresses=["*@acmewidgets.com"],
            add_labels=["Vendor/AcmeWidgets"],
            archive=True,
        )
        assert r1.status_code == 503

        r2 = _create_filter(
            client,
            sid,
            name="Acme Widgets invoices",
            query="from:*@acmewidgets.com",
            from_addresses=["*@acmewidgets.com"],
            add_labels=["Vendor/AcmeWidgets"],
            archive=True,
        )
        assert r2.status_code == 200

        filters = _filters(client, sid).json()["items"]
        assert any(
            item["from_addresses"] == ["*@acmewidgets.com"]
            and item["archive"] is True
            and "Vendor/AcmeWidgets" in item["add_labels"]
            for item in filters
        )

        ev = _eval(client, sid, "gmail_filter_repair_chain")
        assert ev["success"] is True, ev["reasoning"][:200]


class TestDecoyAndExplorationVariants:
    def test_spam_twin_adds_lookalike_without_breaking_exact_delete(self, client: TestClient):
        s = _session(
            client,
            "gmail_delete_spam",
            variant_filename="gmail_delete_spam__spam_twin.yaml",
        )
        sid = s["session_id"]
        spam_id = s["resolved_targets"]["spam_email_id"]

        inbox = _emails(client, sid).json()["items"]
        assert any(item["id"] == spam_id for item in inbox)
        assert any(
            item["from_addr"] == "winner-support@prizecentral.net"
            and item["subject"] == "You Won $1,000,000!!! Follow-up"
            for item in inbox
        )

        r = _delete(client, sid, spam_id)
        assert r.status_code == 200

        ev = _eval(client, sid, "gmail_delete_spam")
        assert ev["success"] is True

    def test_budget_twin_adds_near_identical_search_result(self, client: TestClient):
        s = _session(
            client,
            "gmail_search_and_star",
            variant_filename="gmail_search_and_star__budget_twin.yaml",
        )
        sid = s["session_id"]
        target = s["resolved_targets"]["target_email_id"]

        r = _search(client, sid, "Q4 Budget Summary")
        assert r.status_code == 200
        items = r.json()["items"]
        assert any(item["id"] == target for item in items)
        assert any(item["subject"] == "Q4 Budget Summary - Draft" for item in items)

        _star(client, sid, target)
        ev = _eval(client, sid, "gmail_search_and_star")
        assert ev["success"] is True

    def test_board_briefing_label_trap_exposes_archive_hint(self, client: TestClient):
        s = _session(
            client,
            "gmail_board_briefing_prep",
            variant_filename="gmail_board_briefing_prep__label_trap.yaml",
        )
        sid = s["session_id"]

        results = _search(client, sid, "Board Materials/Archive").json()["items"]
        assert any(item["from_name"] == "Email Rules" for item in results)

        archive = _emails(client, sid, label="Board Materials/Archive")
        assert archive.status_code == 200
        assert archive.json()["total"] >= 1

    def test_thread_archaeology_exploration_requires_search_retry(self, client: TestClient):
        s = _session(
            client,
            "gmail_thread_archaeology",
            variant_filename="gmail_thread_archaeology__exploration.yaml",
        )
        sid = s["session_id"]
        target = s["resolved_targets"]["thread_email_id"]
        q = s["resolved_targets"]["thread_subject"]

        inbox = _emails(client, sid).json()["items"]
        assert all(item["id"] != target for item in inbox[:25])

        # Variant uses stale_data with stale_count=3: calls 1-3 return empty,
        # call 4 returns the real result set.
        r1 = _search(client, sid, q)
        r2 = _search(client, sid, q)
        r3 = _search(client, sid, q)
        r4 = _search(client, sid, q)

        assert r1.status_code == 200 and r1.json()["total"] == 0
        assert r2.status_code == 200 and r2.json()["total"] == 0
        assert r3.status_code == 200 and r3.json()["total"] == 0
        assert r4.status_code == 200
        assert any(item["id"] == target for item in r4.json()["items"])


class TestStressGrounding:
    """forward_email + grounding: confusing decoy emails added."""

    def test_still_solvable_with_decoys(self, client):
        s = _session(client, "gmail_forward_email",
                     variant_filename="gmail_forward_email__grounding.yaml")
        sid = s["session_id"]
        target = s["resolved_targets"]["target_email_id"]
        forward_recipient = _instruction_emails("gmail_forward_email")[0]
        forward_note = _instruction_quotes("gmail_forward_email")[-1]

        _forward(client, sid, target, to=[forward_recipient], body=forward_note)
        ev = _eval(client, sid, "gmail_forward_email")
        assert ev["success"] is True

    def test_decoy_emails_present(self, client):
        s_standard = _session(client, "gmail_forward_email", seed=99)
        s_degraded = _session(client, "gmail_forward_email", seed=99,
                              variant_filename="gmail_forward_email__grounding.yaml")

        r_std = _emails(client, s_standard["session_id"])
        r_deg = _emails(client, s_degraded["session_id"])

        std_count = r_std.json()["total"]
        deg_count = r_deg.json()["total"]
        assert deg_count > std_count, (
            f"Degraded should have more emails (decoys). "
            f"Standard={std_count}, Degraded={deg_count}"
        )


class TestStressStateTracking:
    """forward_email + state_tracking: distractors + shuffled contacts."""

    def test_still_solvable_with_distractors(self, client):
        s = _session(client, "gmail_forward_email",
                     variant_filename="gmail_forward_email__state_tracking.yaml")
        sid = s["session_id"]
        target = s["resolved_targets"]["target_email_id"]
        forward_recipient = _instruction_emails("gmail_forward_email")[0]
        forward_note = _instruction_quotes("gmail_forward_email")[-1]

        _forward(client, sid, target, to=[forward_recipient], body=forward_note)
        ev = _eval(client, sid, "gmail_forward_email")
        assert ev["success"] is True

    def test_distractors_injected(self, client):
        s = _session(client, "gmail_forward_email",
                     variant_filename="gmail_forward_email__state_tracking.yaml")
        r = _emails(client, s["session_id"])
        emails = r.json()
        # state_tracking variant injects 5 distractors
        assert emails["total"] > 15, f"Expected extra distractors, got {emails['total']} total"

    def test_board_briefing_adds_exact_topic_wrong_sender_decoys(self, client):
        s = _session(client, "gmail_board_briefing_prep",
                     variant_filename="gmail_board_briefing_prep__state_tracking.yaml")
        sid = s["session_id"]
        targets = s["resolved_targets"]
        decoy_senders = {"Board Ops", "Chief of Staff", "Executive Assistant"}

        for topic in (targets["topic_a"], targets["topic_b"], targets["topic_c"]):
            results = _search(client, sid, topic).json()["items"]
            assert any(item["from_name"] in decoy_senders for item in results), (
                f"Expected wrong-sender decoy for topic {topic!r}"
            )


class TestStressPlanning:
    """search_and_star + planning: scrambled timestamps + first search returns empty."""

    def test_first_search_returns_stale_empty(self, client):
        s = _session(client, "gmail_search_and_star",
                     variant_filename="gmail_search_and_star__planning.yaml")
        sid = s["session_id"]

        # Variant uses stale_data with stale_count=2: calls 1 and 2 return
        # empty, call 3 returns the real result set.
        r1 = _search(client, sid, "Q4 Budget Summary")
        assert r1.status_code == 200
        assert r1.json()["total"] == 0, "first search should be stale (empty)"

        r2 = _search(client, sid, "Q4 Budget Summary")
        assert r2.status_code == 200
        assert r2.json()["total"] == 0, "second search still within stale_count=2"

        r3 = _search(client, sid, "Q4 Budget Summary")
        assert r3.status_code == 200
        data3 = r3.json()
        assert data3["total"] >= 1, f"third search should return results, got {data3['total']}"

    def test_still_solvable_after_retry(self, client):
        s = _session(client, "gmail_search_and_star",
                     variant_filename="gmail_search_and_star__planning.yaml")
        sid = s["session_id"]
        target = s["resolved_targets"]["target_email_id"]

        # stale_count=2 → first two searches are empty, third returns the
        # real items. The third search is what unblocks the agent.
        r1 = _search(client, sid, "Q4 Budget Summary")
        assert r1.status_code == 200
        assert r1.json()["total"] == 0

        r2 = _search(client, sid, "Q4 Budget Summary")
        assert r2.status_code == 200
        assert r2.json()["total"] == 0

        r3 = _search(client, sid, "Q4 Budget Summary")
        assert r3.status_code == 200
        assert any(item["id"] == target for item in r3.json()["items"])

        _star(client, sid, target)
        ev = _eval(client, sid, "gmail_search_and_star")
        assert ev["success"] is True
