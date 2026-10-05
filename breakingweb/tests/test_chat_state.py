"""Chat messages appear in state.chat after send_msg_to_user."""

from breakingweb.backend.state import SessionManager


def test_chat_starts_empty():
    sm = SessionManager()
    sid, _, _ = sm.create_session(env_id="patient_portal",
                                  task_id="pp_check_immunizations", seed=42)
    state = sm.get_state(sid)
    assert state.chat == []


def test_chat_append_on_agent_message():
    sm = SessionManager()
    sid, _, _ = sm.create_session(env_id="patient_portal",
                                  task_id="pp_check_immunizations", seed=42)
    sm.append_chat_message(sid, role="assistant", content="hello")
    state = sm.get_state(sid)
    assert len(state.chat) == 1
    assert state.chat[0].role == "assistant"
    assert state.chat[0].content == "hello"


def test_chat_append_preserves_order():
    sm = SessionManager()
    sid, _, _ = sm.create_session(env_id="patient_portal",
                                  task_id="pp_check_immunizations", seed=42)
    sm.append_chat_message(sid, role="assistant", content="first")
    sm.append_chat_message(sid, role="assistant", content="second")
    state = sm.get_state(sid)
    contents = [m.content for m in state.chat]
    assert contents == ["first", "second"]


def test_chat_append_noop_for_missing_session():
    sm = SessionManager()
    # Should not raise — graceful no-op
    sm.append_chat_message("does-not-exist", role="assistant", content="hi")
