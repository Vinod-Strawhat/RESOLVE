import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.action_executor import ActionExecutor
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
    monkeypatch.setattr(
        "backend.api.actions.get_executor",
        lambda: ActionExecutor(action_store, case_store),
    )

    pending_id = action_store.create_action(
        case_id,
        type="warranty_dispute",
        target="ASUS Support",
        title="Request review",
        reason="Evidence may indicate coverage.",
        content="Please review the rejected claim.",
    )["id"]
    action_store.submit_for_approval(pending_id)

    approved = action_store.create_action(
        case_id,
        type="warranty_dispute",
        target="ASUS Support",
        title="Approve and execute",
        reason="All facts are in place.",
        content="Please reconsider the rejected claim and provide inspection evidence.",
    )
    approved_id = action_store.submit_for_approval(approved["id"])["id"]
    action_store.approve_action(approved_id)

    env = {
        "case_id": case_id,
        "action_store": action_store,
        "case_store": case_store,
        "pending_id": pending_id,
        "approved_id": approved_id,
    }
    env["client"] = TestClient(app)
    return env


# --- C. Action listing by case (via API) ---

def test_list_actions_for_case(env):
    response = env["client"].get(f"/api/cases/{env['case_id']}/actions")
    assert response.status_code == 200
    body = response.json()
    assert body["case_id"] == env["case_id"]
    assert len(body["actions"]) == 2
    titles = {action["title"] for action in body["actions"]}
    assert titles == {"Request review", "Approve and execute"}
    assert {action["status"] for action in body["actions"]} == {
        "pending_approval",
        "approved",
    }


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


# --- L. Execution endpoint ---

def test_execute_approved_action_endpoint(env):
    response = env["client"].post(f"/api/actions/{env['approved_id']}/execute")
    assert response.status_code == 200
    action = response.json()["action"]
    assert action["id"] == env["approved_id"]
    assert action["status"] == "executed"
    assert action["execution_status"] == "executed"
    assert action["execution_reference"].startswith("RESOLVE-ACTION-")
    assert action["execution_result"]
    assert action["executed_at"] is not None
    assert action["execution_error"] is None


def test_execute_updates_case_to_awaiting_response(env):
    env["client"].post(f"/api/actions/{env['approved_id']}/execute")
    case = env["case_store"].get_case(env["case_id"])
    assert case["status"] == "awaiting_response"


def test_execute_pending_approval_409(env):
    response = env["client"].post(f"/api/actions/{env['pending_id']}/execute")
    assert response.status_code == 409
    assert "only approved actions may be executed" in response.json()["detail"]


def test_execute_rejected_action_409(env):
    env["client"].post(f"/api/actions/{env['pending_id']}/reject")
    response = env["client"].post(f"/api/actions/{env['pending_id']}/execute")
    assert response.status_code == 409


def test_execute_unknown_action_404(env):
    assert env["client"].post("/api/actions/missing/execute").status_code == 404


def test_execute_already_executed_is_idempotent(env):
    first = env["client"].post(f"/api/actions/{env['approved_id']}/execute").json()["action"]
    second = env["client"].post(f"/api/actions/{env['approved_id']}/execute").json()["action"]
    assert second["status"] == "executed"
    assert second["execution_reference"] == first["execution_reference"]
    assert second["execution_result"] == first["execution_result"]
    assert second["executed_at"] == first["executed_at"]

    actions_in_case = env["client"].get(f"/api/cases/{env['case_id']}/actions").json()["actions"]
    executed = [a for a in actions_in_case if a["id"] == env["approved_id"]]
    assert len(executed) == 1
