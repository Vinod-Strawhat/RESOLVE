from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.agent.resolve_agent import _make_tool_recorder
from backend.api.agent import ToolActivity
from backend.main import app
from backend.services.case_store import CaseStore
from backend.services.memory_store import MemoryStore

import backend.api.agent as agent_module

client = TestClient(app)


@pytest.fixture
def store(tmp_path, monkeypatch):
    store = MemoryStore(tmp_path / "resolve.db")
    monkeypatch.setattr("backend.api.agent.get_memory_store", lambda: store)
    return store


class FakeAgent:
    def __init__(self):
        self.prompts = []

    def __call__(self, prompt, **kwargs):
        self.prompts.append(prompt)
        message = SimpleNamespace(content=[{"text": "ok"}])
        return SimpleNamespace(message=message, stop_reason="end_turn")


@pytest.fixture
def fake_agent(monkeypatch):
    agent = FakeAgent()
    monkeypatch.setattr("backend.api.agent.build_resolve_agent", lambda tool_activity=None: agent)
    return agent


def test_chat_requires_message():
    response = client.post("/api/agent/chat", json={})
    assert response.status_code == 422


def test_chat_rejects_blank_message():
    response = client.post("/api/agent/chat", json={"message": "   "})
    assert response.status_code == 400


def test_chat_returns_config_error_without_credentials(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    response = client.post("/api/agent/chat", json={"message": "hello"})
    assert response.status_code == 503
    assert "OPENROUTER_API_KEY" in response.json()["detail"]


def test_chat_creates_session_and_persists_turn(fake_agent, store):
    response = client.post(
        "/api/agent/chat", json={"message": "My laptop warranty claim was rejected."}
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["session_id"]) == 32
    assert body["response"] == "ok"
    assert body["tool_activity"] == []

    messages = store.list_messages(body["session_id"])
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "My laptop warranty claim was rejected."
    assert messages[1]["content"] == "ok"


def test_chat_reuses_session_and_forwards_history(fake_agent, store):
    first = client.post("/api/agent/chat", json={"message": "Turn one message"})
    session_id = first.json()["session_id"]

    second = client.post(
        "/api/agent/chat",
        json={"session_id": session_id, "message": "It's an ASUS Vivobook."},
    )
    assert second.status_code == 200
    assert second.json()["session_id"] == session_id

    transcript_roles = [m["role"] for m in fake_agent.prompts[1]]
    transcript_texts = [
        m["content"][0]["text"] for m in fake_agent.prompts[1]
    ]
    assert transcript_roles == ["user", "assistant", "user"]
    assert transcript_texts == ["Turn one message", "ok", "It's an ASUS Vivobook."]


def test_chat_unknown_session_returns_404(fake_agent, store):
    response = client.post(
        "/api/agent/chat",
        json={"session_id": "does-not-exist", "message": "hello"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "session not found"


def test_chat_blank_session_id_rejected(fake_agent, store):
    response = client.post(
        "/api/agent/chat",
        json={"session_id": "   ", "message": "hello"},
    )
    assert response.status_code == 400


def test_tool_recorder_success_event():
    target: list[dict] = []
    recorder = _make_tool_recorder(target)
    event = SimpleNamespace(
        tool_use={"name": "create_case_note"},
        result={"status": "success"},
    )
    recorder(event)
    assert target == [{"tool": "create_case_note", "status": "executed"}]


def test_tool_recorder_failure_event():
    target: list[dict] = []
    recorder = _make_tool_recorder(target)
    event = SimpleNamespace(
        tool_use={"name": "create_case_note"},
        result={"status": "error"},
    )
    recorder(event)
    assert target == [{"tool": "create_case_note", "status": "failed"}]


def test_tool_activity_response_shape():
    activity = ToolActivity(tool="create_case_note", status="executed")
    assert activity.model_dump() == {"tool": "create_case_note", "status": "executed"}


class CaseCreatingFakeAgent(FakeAgent):
    def __call__(self, prompt, **kwargs):
        session_id = kwargs.get("invocation_state", {}).get("session_id")
        agent_module.get_case_store().create_case(
            session_id,
            title="Rejected warranty claim",
            category="warranty",
            description="Company refused coverage.",
        )
        return super().__call__(prompt, **kwargs)


def test_chat_returns_null_case_id_when_no_case(fake_agent, store):
    response = client.post("/api/agent/chat", json={"message": "hello"})
    assert response.status_code == 200
    assert response.json()["case_id"] is None


def test_chat_returns_case_id_when_agent_creates_case(tmp_path, monkeypatch):
    cases = CaseStore(tmp_path / "resolve.db")
    store = MemoryStore(tmp_path / "resolve.db")
    monkeypatch.setattr("backend.api.agent.get_memory_store", lambda: store)
    monkeypatch.setattr("backend.api.agent.get_case_store", lambda: cases)
    monkeypatch.setattr(
        "backend.api.agent.build_resolve_agent",
        lambda tool_activity=None: CaseCreatingFakeAgent(),
    )
    response = client.post(
        "/api/agent/chat",
        json={"message": "My laptop warranty claim was rejected."},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["case_id"]) == 32
    case = cases.get_case(body["case_id"])
    assert case is not None
    assert case["session_id"] == body["session_id"]


def test_chat_returns_case_id_for_existing_case(tmp_path, monkeypatch):
    cases = CaseStore(tmp_path / "resolve.db")
    store = MemoryStore(tmp_path / "resolve.db")
    monkeypatch.setattr("backend.api.agent.get_memory_store", lambda: store)
    monkeypatch.setattr("backend.api.agent.get_case_store", lambda: cases)
    monkeypatch.setattr(
        "backend.api.agent.build_resolve_agent",
        lambda tool_activity=None: FakeAgent(),
    )
    first = client.post("/api/agent/chat", json={"message": "hello"})
    session_id = first.json()["session_id"]
    case_id = cases.create_case(
        session_id,
        title="Existing case",
        category="refund",
        description="Description",
    )["id"]
    second = client.post(
        "/api/agent/chat",
        json={"session_id": session_id, "message": "More details"},
    )
    assert second.status_code == 200
    assert second.json()["case_id"] == case_id