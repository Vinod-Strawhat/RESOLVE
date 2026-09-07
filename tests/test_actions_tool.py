import json
from types import SimpleNamespace

import pytest

from backend.agent.resolve_agent import RESOLVE_TOOLS
from backend.services.action_store import ActionStore
from backend.services.case_store import CaseStore


def _tool_context(session_id):
    return SimpleNamespace(invocation_state={"session_id": session_id})


@pytest.fixture
def env(tmp_path, monkeypatch):
    case_store = CaseStore(tmp_path / "resolve.db")
    action_store = ActionStore(tmp_path / "resolve.db")
    session_id = "session-xyz"
    case_id = case_store.create_case(
        session_id,
        title="Rejected warranty claim",
        category="warranty",
        description="ASUS refused coverage of a laptop.",
        product="ASUS Vivobook",
        rejection_reason="Not covered by warranty terms",
    )["id"]
    monkeypatch.setattr("backend.tools.actions.get_case_store", lambda: case_store)
    monkeypatch.setattr("backend.tools.actions.get_action_store", lambda: action_store)
    return {
        "session_id": session_id,
        "case_id": case_id,
        "action_store": action_store,
        "case_store": case_store,
    }


def _call_prepare(env, **overrides):
    from backend.tools.actions import prepare_action

    args = {
        "type": "warranty_dispute",
        "title": "Request review of rejected warranty claim",
        "reason": "The purchase and warranty evidence may indicate the issue is covered.",
        "content": "We request a review of the rejected claim based on the purchase date and warranty terms.",
        "target": "ASUS Support",
    }
    args.update(overrides)
    result = prepare_action(_tool_context(env["session_id"]), **args)
    return result, json.loads(result)


def test_prepare_action_with_active_case(env):
    result, body = _call_prepare(env)
    assert body["status"] == "prepared"
    assert body["case_id"] == env["case_id"]
    assert body["type"] == "warranty_dispute"
    assert body["target"] == "ASUS Support"
    assert body["title"].startswith("Request review")
    assert body["approval_status"] == "pending_approval"
    assert "awaiting" in body["note"] or "not be" in body["note"]

    saved = env["action_store"].get_action(body["action_id"])
    assert saved is not None
    assert saved["status"] == "pending_approval"
    assert saved["case_id"] == env["case_id"]


def test_prepare_action_no_session_returns_error(env, monkeypatch):
    from backend.tools.actions import prepare_action

    result = prepare_action(_tool_context(None), type="warranty_dispute", title="T", reason="R", content="C")
    body = json.loads(result)
    assert body["status"] == "error"


def test_prepare_action_no_case_returns_error(env, monkeypatch):
    from backend.tools.actions import prepare_action

    ctx = SimpleNamespace(invocation_state={"session_id": "no-case-session"})
    result = prepare_action(ctx, type="warranty_dispute", title="T", reason="R", content="C")
    body = json.loads(result)
    assert body["status"] == "error"
    assert "case" in body["message"]


def test_prepare_action_invalid_type_returns_error(env):
    _, body = _call_prepare(env, type="garbage")
    assert body["status"] == "error"
    assert "type must be one of" in body["message"]


def test_prepare_action_empty_title_returns_error(env):
    _, body = _call_prepare(env, title="  ")
    assert body["status"] == "error" or body["message"]


def test_prepare_action_does_not_execute(env):
    _, body = _call_prepare(env)
    assert body["status"] == "prepared"
    saved = env["action_store"].get_action(body["action_id"])
    assert saved["status"] == "pending_approval"
    assert saved["approved_at"] is None


# --- K. Agent tool registration ---

def test_prepare_action_registered_with_agent():
    names = [tool.tool_name for tool in RESOLVE_TOOLS]
    assert "prepare_action" in names


def test_agent_tools_include_all_phase_tools():
    names = {tool.tool_name for tool in RESOLVE_TOOLS}
    assert {"create_case_note", "create_case", "update_case", "prepare_action"} <= names
