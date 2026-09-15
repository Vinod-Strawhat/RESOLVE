"""Phase 8B security tests: ownership isolation, CSRF, session guessing, migration."""

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.api.dependencies import _allowed_cors_origins
from backend.services.action_executor import ActionExecutor
from backend.services.action_store import ActionStore
from backend.services.auth import COOKIE_NAME
from backend.services.case_store import CaseStore
from backend.services.document_store import DocumentStore
from backend.services.legacy_ownership import (
    LEGACY_EMAIL,
    migrate_legacy_ownership,
)
from backend.services.memory_store import MemoryStore
from backend.services.session_store import SessionStore
from backend.services.user_store import UserStore
from conftest import create_test_user, issue_auth_token


class _FakeAgent:
    def __call__(self, prompt, **kwargs):
        message = SimpleNamespace(content=[{"text": "ok"}])
        return SimpleNamespace(message=message, stop_reason="end_turn")


def _setup(monkeypatch, tmp_path):
    db = tmp_path / "resolve.db"
    user_store = UserStore(db)
    owner = create_test_user(
        user_store, email="owner@example.com", display_name="Owner"
    )
    other = create_test_user(
        user_store, email="other@example.com", display_name="Other"
    )
    session_store = SessionStore(db)
    case_store = CaseStore(db)
    action_store = ActionStore(db)
    memory = MemoryStore(db)
    documents = DocumentStore(db, tmp_path / "uploads")

    monkeypatch.setattr("backend.api.dependencies.get_user_store", lambda: user_store)
    monkeypatch.setattr(
        "backend.api.dependencies.get_session_store", lambda: session_store
    )
    monkeypatch.setattr(
        "backend.api.dependencies.get_case_store", lambda: case_store
    )
    monkeypatch.setattr(
        "backend.api.dependencies.get_action_store", lambda: action_store
    )
    monkeypatch.setattr("backend.api.agent.get_memory_store", lambda: memory)
    monkeypatch.setattr("backend.api.agent.get_case_store", lambda: case_store)
    monkeypatch.setattr("backend.api.actions.get_action_store", lambda: action_store)
    monkeypatch.setattr(
        "backend.api.actions.get_executor",
        lambda: ActionExecutor(action_store, case_store),
    )
    monkeypatch.setattr("backend.api.cases.get_case_store", lambda: case_store)
    monkeypatch.setattr("backend.api.cases.get_document_store", lambda: documents)
    monkeypatch.setattr("backend.api.cases.get_memory_store", lambda: memory)
    monkeypatch.setattr(
        "backend.api.agent.build_resolve_agent", lambda tool_activity=None: _FakeAgent()
    )
    monkeypatch.setattr(
        "backend.api.cases.build_resolve_agent", lambda tool_activity=None: _FakeAgent()
    )

    def client_for(user_id):
        client = TestClient(app)
        client.cookies.set(COOKIE_NAME, issue_auth_token(session_store, user_id))
        return client

    return {
        "case_store": case_store,
        "action_store": action_store,
        "memory": memory,
        "owner": owner,
        "other": other,
        "owner_client": client_for(owner["id"]),
        "other_client": client_for(other["id"]),
    }


@pytest.fixture
def env(monkeypatch, tmp_path):
    return _setup(monkeypatch, tmp_path)


# --- Ownership isolation: every case-scoped endpoint returns 404 for a foreign user ---


def test_foreign_user_gets_404_on_all_case_endpoints(env):
    case_id = env["case_store"].create_case(
        "session-owner",
        user_id=env["owner"]["id"],
        title="Owner claim",
        category="warranty",
        description="Private.",
    )["id"]

    foreign = env["other_client"]
    for method, url in [
        ("get", f"/api/cases/{case_id}"),
        ("get", f"/api/cases/{case_id}/evaluations"),
        ("get", f"/api/cases/{case_id}/responses"),
        ("get", f"/api/cases/{case_id}/history"),
        ("get", f"/api/cases/{case_id}/followup-status"),
        ("get", f"/api/cases/{case_id}/actions"),
    ]:
        response = getattr(foreign, method)(url)
        assert response.status_code == 404, f"{method.upper()} {url} -> {response.status_code}"
        assert response.json()["detail"] == "case not found"
    bodies = {
        f"/api/cases/{case_id}/responses": {"source": "simulated_support", "content": "hi"},
        f"/api/cases/{case_id}/evaluate": {"outcome": "resolved", "confidence": 0.5},
        f"/api/cases/{case_id}/evaluate-response": {},
        f"/api/cases/{case_id}/prepare-followup": {},
    }
    for url, body in bodies.items():
        response = foreign.post(url, json=body)
        assert response.status_code == 404, f"POST {url} -> {response.status_code}"
        assert response.json()["detail"] == "case not found"

    upload = foreign.post(
        f"/api/cases/{case_id}/documents",
        files={"file": ("invoice.txt", b"laptop", "text/plain")},
    )
    assert upload.status_code == 404
    assert upload.json()["detail"] == "case not found"


def test_owner_can_access_own_case(env):
    case_id = env["case_store"].create_case(
        "session-owner",
        user_id=env["owner"]["id"],
        title="Owner claim",
        category="warranty",
        description="Private.",
    )["id"]
    response = env["owner_client"].get(f"/api/cases/{case_id}")
    assert response.status_code == 200
    assert response.json()["case"]["id"] == case_id


def test_list_cases_is_user_scoped(env):
    owner_case = env["case_store"].create_case(
        "session-owner",
        user_id=env["owner"]["id"],
        title="Owner claim",
        category="warranty",
        description="Private.",
    )["id"]
    other_case = env["case_store"].create_case(
        "session-other",
        user_id=env["other"]["id"],
        title="Other claim",
        category="refund",
        description="Other user's private case.",
    )["id"]

    owner_ids = [c["id"] for c in env["owner_client"].get("/api/cases").json()["cases"]]
    other_ids = [c["id"] for c in env["other_client"].get("/api/cases").json()["cases"]]

    assert owner_ids == [owner_case]
    assert other_ids == [other_case]
    assert owner_case not in other_ids
    assert other_case not in owner_ids


def test_list_cases_requires_auth_401(monkeypatch, tmp_path):
    env = _setup(monkeypatch, tmp_path)
    client = TestClient(app)
    response = client.get("/api/cases")
    assert response.status_code == 401


def test_list_cases_empty_state_for_new_user(monkeypatch, tmp_path):
    db = tmp_path / "resolve.db"
    user_store = UserStore(db)
    session_store = SessionStore(db)
    case_store = CaseStore(db)
    new_user = create_test_user(
        user_store, email="new@example.com", display_name="New"
    )
    monkeypatch.setattr("backend.api.dependencies.get_user_store", lambda: user_store)
    monkeypatch.setattr(
        "backend.api.dependencies.get_session_store", lambda: session_store
    )
    monkeypatch.setattr(
        "backend.api.dependencies.get_case_store", lambda: case_store
    )
    monkeypatch.setattr("backend.api.cases.get_case_store", lambda: case_store)
    client = TestClient(app)
    client.cookies.set(COOKIE_NAME, issue_auth_token(session_store, new_user["id"]))
    response = client.get("/api/cases")
    assert response.status_code == 200
    assert response.json()["cases"] == []


# --- Ownership isolation: actions ---


def test_foreign_user_gets_404_on_action_endpoints(env):
    case_id = env["case_store"].create_case(
        "session-owner",
        user_id=env["owner"]["id"],
        title="Owner claim",
        category="warranty",
        description="Private.",
    )["id"]
    action = env["action_store"].create_action(
        case_id,
        type="warranty_dispute",
        target="ASUS",
        title="T",
        reason="R",
        content="C",
    )
    env["action_store"].submit_for_approval(action["id"])

    foreign = env["other_client"]
    for method, url in [
        ("get", f"/api/actions/{action['id']}"),
        ("post", f"/api/actions/{action['id']}/approve"),
        ("post", f"/api/actions/{action['id']}/reject"),
        ("post", f"/api/actions/{action['id']}/execute"),
    ]:
        response = getattr(foreign, method)(url)
        assert response.status_code == 404, f"{method.upper()} {url}"
        assert response.json()["detail"] == "action not found"


def test_owner_can_approve_own_action(env):
    case_id = env["case_store"].create_case(
        "session-owner",
        user_id=env["owner"]["id"],
        title="Owner claim",
        category="warranty",
        description="Private.",
    )["id"]
    action = env["action_store"].create_action(
        case_id,
        type="warranty_dispute",
        target="ASUS",
        title="T",
        reason="R",
        content="C",
    )
    action = env["action_store"].submit_for_approval(action["id"])
    response = env["owner_client"].post(f"/api/actions/{action['id']}/approve")
    assert response.status_code == 200


# --- Session ownership ---


def test_foreign_session_returns_404(env):
    first = env["owner_client"].post(
        "/api/agent/chat", json={"message": "Turn one"}
    )
    assert first.status_code == 200
    session_id = first.json()["session_id"]

    own_resume = env["owner_client"].post(
        "/api/agent/chat",
        json={"session_id": session_id, "message": "More"},
    )
    assert own_resume.status_code == 200
    assert own_resume.json()["session_id"] == session_id

    foreign_resume = env["other_client"].post(
        "/api/agent/chat",
        json={"session_id": session_id, "message": "More"},
    )
    assert foreign_resume.status_code == 404
    assert foreign_resume.json()["detail"] == "session not found"

    random_resume = env["other_client"].post(
        "/api/agent/chat",
        json={"session_id": "does-not-exist", "message": "More"},
    )
    assert random_resume.status_code == 404


# --- CSRF: cross-origin state changes are rejected ---


def test_cross_origin_state_change_rejected_403(env):
    response = env["owner_client"].post(
        "/api/agent/chat",
        json={"message": "hello"},
        headers={"Origin": "http://evil.example"},
    )
    assert response.status_code == 403


def test_cross_origin_upload_rejected_403(env):
    case_id = env["case_store"].create_case(
        "session-owner",
        user_id=env["owner"]["id"],
        title="Owner claim",
        category="warranty",
        description="Private.",
    )["id"]
    response = env["owner_client"].post(
        f"/api/cases/{case_id}/documents",
        files={"file": ("invoice.txt", b"laptop", "text/plain")},
        headers={"Origin": "http://evil.example"},
    )
    assert response.status_code == 403


def test_same_origin_state_change_allowed(env):
    response = env["owner_client"].post(
        "/api/agent/chat",
        json={"message": "hello"},
        headers={"Origin": str(sorted(_allowed_cors_origins())[0])},
    )
    assert response.status_code == 200


def test_read_endpoints_are_not_csrf_guarded(env):
    case_id = env["case_store"].create_case(
        "session-owner",
        user_id=env["owner"]["id"],
        title="Owner claim",
        category="warranty",
        description="Private.",
    )["id"]
    response = env["owner_client"].get(
        f"/api/cases/{case_id}",
        headers={"Origin": "http://evil.example"},
    )
    assert response.status_code == 200


# --- Session guessing ---


def test_garbage_cookie_is_rejected_401(monkeypatch, tmp_path):
    env = _setup(monkeypatch, tmp_path)
    client = TestClient(app)
    client.cookies.set(COOKIE_NAME, "G" * 64)
    response = client.get(f"/api/cases/{uuid.uuid4().hex}")
    assert response.status_code == 401


def test_missing_cookie_is_rejected_401(monkeypatch, tmp_path):
    env = _setup(monkeypatch, tmp_path)
    client = TestClient(app)
    response = client.get(f"/api/cases/{uuid.uuid4().hex}")
    assert response.status_code == 401


# --- Legacy migration backfill ---


def _legacy_now():
    return datetime.now(timezone.utc).isoformat()


def test_legacy_migration_claims_unowned_rows_and_is_idempotent(tmp_path):
    db = tmp_path / "resolve.db"
    case_store = CaseStore(db)
    memory = MemoryStore(db)
    user_store = UserStore(db)

    legacy_session = memory.create_session()
    now = _legacy_now()
    with case_store._connect() as conn:
        conn.execute(
            "INSERT INTO cases (id, session_id, user_id, category, title, description, created_at, updated_at) "
            "VALUES (?, ?, NULL, 'warranty', 'Legacy case', 'Pre-8B', ?, ?)",
            ("legacy-case-1", legacy_session, now, now),
        )

    first = migrate_legacy_ownership(
        case_store=case_store,
        memory_store=memory,
        user_store=user_store,
    )
    assert first["cases_claimed"] == 1
    assert first["sessions_claimed"] == 1
    assert first["owner_email"] == LEGACY_EMAIL

    owner = user_store.get_user_by_email(LEGACY_EMAIL)
    assert owner is not None

    claimed_case = case_store.get_case("legacy-case-1")
    assert claimed_case["user_id"] == owner["id"]
    assert memory.get_session(legacy_session)["user_id"] == owner["id"]

    second = migrate_legacy_ownership(
        case_store=case_store,
        memory_store=memory,
        user_store=user_store,
    )
    assert second["cases_claimed"] == 0
    assert second["sessions_claimed"] == 0
    assert second["owner_user_id"] == first["owner_user_id"]


def test_legacy_migration_leaves_owned_rows_untouched(tmp_path):
    db = tmp_path / "resolve.db"
    case_store = CaseStore(db)
    memory = MemoryStore(db)
    user_store = UserStore(db)
    user = create_test_user(user_store)

    case_id = case_store.create_case(
        "session-owned",
        user_id=user["id"],
        title="Owned",
        category="refund",
        description="Already attributed.",
    )["id"]
    with memory._connect() as conn:
        conn.execute(
            "UPDATE sessions SET user_id = ? WHERE id = ?",
            (user["id"], "session-owned"),
        )

    summary = migrate_legacy_ownership(
        case_store=case_store,
        memory_store=memory,
        user_store=user_store,
    )
    assert summary["cases_claimed"] == 0
    assert summary["sessions_claimed"] == 0

    after = case_store.get_case(case_id)
    assert after["user_id"] == user["id"]