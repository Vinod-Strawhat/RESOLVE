import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.action_store import ActionStore
from backend.services.case_store import CaseStore


@pytest.fixture
def env(tmp_path, monkeypatch):
    case_store = CaseStore(tmp_path / "resolve.db")
    action_store = ActionStore(tmp_path / "resolve.db")
    case_id = case_store.create_case(
        "session-1",
        title="Rejected warranty claim",
        category="warranty",
        description="ASUS refused coverage.",
    )["id"]
    monkeypatch.setattr("backend.api.actions.get_case_store", lambda: case_store)
    monkeypatch.setattr("backend.api.actions.get_action_store", lambda: action_store)

    pending_id = action_store.create_action(
        case_id,
        type="warranty_dispute",
        target="ASUS Support",
        title="Request review",
        reason="Evidence may indicate coverage.",
        content="Please review the rejected claim.",
    )["id"]
    action_store.submit_for_approval(pending_id)
    env = {
        "case_id": case_id,
        "action_store": action_store,
        "pending_id": pending_id,
    }
    env["client"] = TestClient(app)
    return env


# --- C. Action listing by case (via API) ---

def test_list_actions_for_case(env):
    response = env["client"].get(f"/api/cases/{env['case_id']}/actions")
    assert response.status_code == 200
    body = response.json()
    assert body["case_id"] == env["case_id"]
    assert len(body["actions"]) == 1
    assert body["actions"][0]["title"] == "Request review"
    assert body["actions"][0]["status"] == "pending_approval"


def test_list_actions_unknown_case_404(env):
    assert env["client"].get("/api/cases/missing/actions").status_code == 404


# --- B. Action retrieval (via API) ---

def test_get_action(env):
    response = env["client"].get(f"/api/actions/{env['pending_id']}")
    assert response.status_code == 200
    assert response.json()["action"]["id"] == env["pending_id"]


def test_get_unknown_action_404(env):
    assert env["client"].get("/api/actions/missing").status_code == 404


# --- I. Approval endpoint ---

def test_approve_endpoint(env):
    response = env["client"].post(f"/api/actions/{env['pending_id']}/approve")
    assert response.status_code == 200
    action = response.json()["action"]
    assert action["status"] == "approved"
    assert action["approved_at"] is not None
    assert action["rejected_at"] is None


def test_approve_endpoint_unknown_404(env):
    response = env["client"].post("/api/actions/missing/approve")
    assert response.status_code == 404


def test_approve_invalid_transition_409(env):
    env["client"].post(f"/api/actions/{env['pending_id']}/approve")
    response = env["client"].post(f"/api/actions/{env['pending_id']}/approve")
    assert response.status_code == 409
    assert "must be pending_approval" in response.json()["detail"]


# --- J. Rejection endpoint ---

def test_reject_endpoint(env):
    response = env["client"].post(f"/api/actions/{env['pending_id']}/reject")
    assert response.status_code == 200
    action = response.json()["action"]
    assert action["status"] == "rejected"
    assert action["rejected_at"] is not None
    assert action["approved_at"] is None


def test_reject_endpoint_unknown_404(env):
    assert env["client"].post("/api/actions/missing/reject").status_code == 404


def test_reject_invalid_transition_409(env):
    env["client"].post(f"/api/actions/{env['pending_id']}/reject")
    response = env["client"].post(f"/api/actions/{env['pending_id']}/reject")
    assert response.status_code == 409
    assert "must be pending_approval" in response.json()["detail"]


def test_approve_after_reject_409(env):
    env["client"].post(f"/api/actions/{env['pending_id']}/reject")
    response = env["client"].post(f"/api/actions/{env['pending_id']}/approve")
    assert response.status_code == 409


def test_reject_after_approve_409(env):
    env["client"].post(f"/api/actions/{env['pending_id']}/approve")
    response = env["client"].post(f"/api/actions/{env['pending_id']}/reject")
    assert response.status_code == 409
