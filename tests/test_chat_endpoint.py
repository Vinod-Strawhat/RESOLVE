from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.agent.resolve_agent import _make_tool_recorder
from backend.api.agent import ToolActivity
from backend.main import app

client = TestClient(app)


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