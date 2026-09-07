import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.case_store import CaseStore
from backend.services.response_evaluator import EvaluationOutcome
from backend.services.response_store import ResponseStore


@pytest.fixture
def env(tmp_path, monkeypatch):
    case_store = CaseStore(tmp_path / "resolve.db")
    response_store = ResponseStore(tmp_path / "resolve.db")
    monkeypatch.setattr("backend.api.case_responses.get_case_store", lambda: case_store)
    monkeypatch.setattr(
        "backend.api.case_responses.get_response_store", lambda: response_store
    )

    case_id = case_store.create_case(
        "session-resp-api",
        title="Rejected warranty claim",
        category="warranty",
        description="ASUS refused coverage.",
    )["id"]
    env = {
        "case_id": case_id,
        "case_store": case_store,
        "response_store": response_store,
    }
    env["client"] = TestClient(app)
    return env


def _to_status(env, status: str) -> None:
    env["case_store"].transition_status(env["case_id"], status)


# --- Response API ---

def test_record_response(env):
    _to_status(env, "awaiting_response")
    response = env["client"].post(
        f"/api/cases/{env['case_id']}/responses",
        json={"source": "simulated_support", "content": "We reviewed your claim."},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["response"]["case_id"] == env["case_id"]
    assert body["response"]["source"] == "simulated_support"
    assert body["response"]["content"] == "We reviewed your claim."
    assert body["response"]["received_at"]
    assert body["case"]["status"] == "response_received"


def test_response_persisted_and_listed(env):
    _to_status(env, "awaiting_response")
    env["client"].post(
        f"/api/cases/{env['case_id']}/responses",
        json={"source": "simulated_support", "content": "first"},
    )
    env["client"].post(
        f"/api/cases/{env['case_id']}/evaluate", json={"outcome": "needs_follow_up"}
    )
    env["client"].post(
        f"/api/cases/{env['case_id']}/responses",
        json={"source": "simulated_support", "content": "second"},
    )
    listing = env["client"].get(f"/api/cases/{env['case_id']}/responses")
    assert listing.status_code == 200
    body = listing.json()
    assert body["case_id"] == env["case_id"]
    assert [r["content"] for r in body["responses"]] == ["first", "second"]
    assert all(r.get("storage_path") is None for r in body["responses"])
    assert len(env["response_store"].list_responses_for_case(env["case_id"])) == 2


def test_record_response_unknown_case_404(env):
    response = env["client"].post(
        "/api/cases/missing/responses",
        json={"source": "simulated_support", "content": "hi"},
    )
    assert response.status_code == 404


def test_record_response_empty_content_400(env):
    _to_status(env, "awaiting_response")
    response = env["client"].post(
        f"/api/cases/{env['case_id']}/responses",
        json={"source": "simulated_support", "content": "   "},
    )
    assert response.status_code == 400
    assert "empty" in response.json()["detail"]


def test_record_response_empty_source_400(env):
    _to_status(env, "awaiting_response")
    response = env["client"].post(
        f"/api/cases/{env['case_id']}/responses",
        json={"source": "  ", "content": "hi"},
    )
    assert response.status_code == 400


def test_record_response_invalid_case_state_409(env):
    response = env["client"].post(
        f"/api/cases/{env['case_id']}/responses",
        json={"source": "simulated_support", "content": "too early"},
    )
    assert response.status_code == 409
    assert "cannot receive a response" in response.json()["detail"]


def test_record_response_after_resolved_409(env):
    _to_status(env, "awaiting_response")
    _to_status(env, "response_received")
    _to_status(env, "resolved")
    response = env["client"].post(
        f"/api/cases/{env['case_id']}/responses",
        json={"source": "simulated_support", "content": "late"},
    )
    assert response.status_code == 409


def test_record_response_when_follow_up_needed(env):
    _to_status(env, "awaiting_response")
    _to_status(env, "response_received")
    _to_status(env, "needs_follow_up")
    response = env["client"].post(
        f"/api/cases/{env['case_id']}/responses",
        json={"source": "simulated_support", "content": "follow-up reply"},
    )
    assert response.status_code == 200
    assert response.json()["case"]["status"] == "response_received"


def test_list_responses_unknown_case_404(env):
    assert env["client"].get("/api/cases/missing/responses").status_code == 404


def test_list_responses_empty(env):
    listing = env["client"].get(f"/api/cases/{env['case_id']}/responses")
    assert listing.status_code == 200
    assert listing.json()["responses"] == []


# --- Evaluation API ---

@pytest.mark.parametrize("outcome", ["resolved", "needs_follow_up", "human_intervention"])
def test_evaluate_outcomes(env, outcome):
    _to_status(env, "awaiting_response")
    _to_status(env, "response_received")
    response = env["client"].post(
        f"/api/cases/{env['case_id']}/evaluate", json={"outcome": outcome}
    )
    assert response.status_code == 200
    case = response.json()["case"]
    assert case["status"] == outcome
    if outcome == "resolved":
        assert case["resolved_at"] is not None


def test_evaluate_resolved_sets_resolved_at(env):
    _to_status(env, "awaiting_response")
    _to_status(env, "response_received")
    response = env["client"].post(
        f"/api/cases/{env['case_id']}/evaluate", json={"outcome": "resolved"}
    )
    assert response.json()["case"]["resolved_at"] is not None


def test_evaluate_invalid_outcome_400(env):
    _to_status(env, "awaiting_response")
    _to_status(env, "response_received")
    response = env["client"].post(
        f"/api/cases/{env['case_id']}/evaluate", json={"outcome": "escalate"}
    )
    assert response.status_code == 400
    assert "invalid outcome" in response.json()["detail"]


def test_evaluate_wrong_case_state_409(env):
    _to_status(env, "awaiting_response")
    response = env["client"].post(
        f"/api/cases/{env['case_id']}/evaluate", json={"outcome": "resolved"}
    )
    assert response.status_code == 409
    assert "cannot be evaluated" in response.json()["detail"]


def test_evaluate_free_status_409(env):
    response = env["client"].post(
        f"/api/cases/{env['case_id']}/evaluate", json={"outcome": "resolved"}
    )
    assert response.status_code == 409


def test_evaluate_unknown_case_404(env):
    response = env["client"].post(
        "/api/cases/missing/evaluate", json={"outcome": "resolved"}
    )
    assert response.status_code == 404


def test_evaluate_resolved_cannot_be_evaluated_again(env):
    _to_status(env, "awaiting_response")
    _to_status(env, "response_received")
    env["client"].post(
        f"/api/cases/{env['case_id']}/evaluate", json={"outcome": "resolved"}
    )
    second = env["client"].post(
        f"/api/cases/{env['case_id']}/evaluate", json={"outcome": "resolved"}
    )
    assert second.status_code == 409


def test_evaluate_human_intervention_is_terminal(env):
    _to_status(env, "awaiting_response")
    _to_status(env, "response_received")
    env["client"].post(
        f"/api/cases/{env['case_id']}/evaluate", json={"outcome": "human_intervention"}
    )
    second = env["client"].post(
        f"/api/cases/{env['case_id']}/evaluate", json={"outcome": "resolved"}
    )
    assert second.status_code == 409


# --- AI evaluate-response endpoint ---

def _patch_ai_evaluator(monkeypatch, outcome, confidence=0.87):
    def fake_evaluate(case_store, response_store, case_id, model=None):
        return EvaluationOutcome(
            outcome=outcome,
            confidence=confidence,
            reason="A concise, grounded reason.",
            next_step="A concrete next step.",
        )

    monkeypatch.setattr(
        "backend.api.case_responses.evaluate_response", fake_evaluate
    )
    return fake_evaluate


@pytest.mark.parametrize("outcome", ["resolved", "needs_follow_up", "human_intervention"])
def test_ai_evaluate_success(env, monkeypatch, outcome):
    _to_status(env, "awaiting_response")
    _to_status(env, "response_received")
    _patch_ai_evaluator(monkeypatch, outcome)
    response = env["client"].post(
        f"/api/cases/{env['case_id']}/evaluate-response"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["evaluation"]["outcome"] == outcome
    assert body["evaluation"]["confidence"] == 0.87
    assert body["evaluation"]["reason"]
    assert body["evaluation"]["next_step"]
    assert body["case"]["status"] == outcome


def test_ai_evaluate_unknown_case_404(env, monkeypatch):
    _patch_ai_evaluator(monkeypatch, "resolved", confidence=0.9)
    response = env["client"].post("/api/cases/missing/evaluate-response")
    assert response.status_code == 404


def test_ai_evaluate_wrong_state_409(env, monkeypatch):
    _patch_ai_evaluator(monkeypatch, "resolved", confidence=0.9)
    response = env["client"].post(
        f"/api/cases/{env['case_id']}/evaluate-response"
    )
    assert response.status_code == 409
    assert "cannot be evaluated" in response.json()["detail"]


def test_ai_evaluate_failure_leaves_state_unchanged(env, monkeypatch):
    _to_status(env, "awaiting_response")
    _to_status(env, "response_received")

    def failing_evaluate(case_store, response_store, case_id, model=None):
        raise ValueError("model unavailable: 429")

    monkeypatch.setattr(
        "backend.api.case_responses.evaluate_response", failing_evaluate
    )
    response = env["client"].post(
        f"/api/cases/{env['case_id']}/evaluate-response"
    )
    assert response.status_code == 422
    assert env["case_store"].get_case(env["case_id"])["status"] == "response_received"


def test_ai_evaluate_invalid_model_result_leaves_state_unchanged(env, monkeypatch):
    _to_status(env, "awaiting_response")
    _to_status(env, "response_received")

    def invalid_evaluate(case_store, response_store, case_id, model=None):
        raise ValueError("invalid evaluation output: outcome 'escalate'")

    monkeypatch.setattr(
        "backend.api.case_responses.evaluate_response", invalid_evaluate
    )
    response = env["client"].post(
        f"/api/cases/{env['case_id']}/evaluate-response"
    )
    assert response.status_code == 422
    assert env["case_store"].get_case(env["case_id"])["status"] == "response_received"


def test_ai_evaluate_unexpected_error_500(env, monkeypatch):
    _to_status(env, "awaiting_response")
    _to_status(env, "response_received")

    def exploding_evaluate(case_store, response_store, case_id, model=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "backend.api.case_responses.evaluate_response", exploding_evaluate
    )
    response = env["client"].post(
        f"/api/cases/{env['case_id']}/evaluate-response"
    )
    assert response.status_code == 500
    assert env["case_store"].get_case(env["case_id"])["status"] == "response_received"


def test_ai_evaluate_sets_resolved_at_for_resolved(env, monkeypatch):
    _to_status(env, "awaiting_response")
    _to_status(env, "response_received")
    _patch_ai_evaluator(monkeypatch, "resolved")
    response = env["client"].post(
        f"/api/cases/{env['case_id']}/evaluate-response"
    )
    assert response.json()["case"]["resolved_at"] is not None