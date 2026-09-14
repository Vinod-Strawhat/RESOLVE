import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.action_store import ActionStore
from backend.services.case_store import CaseStore
from backend.services.evaluation_store import EvaluationStore
from backend.services.followup_store import FollowupStore
from backend.services.response_evaluator import EvaluationOutcome
from backend.services.response_store import ResponseStore


@pytest.fixture
def env(tmp_path, monkeypatch):
    db = tmp_path / "resolve.db"
    case_store = CaseStore(db)
    action_store = ActionStore(db)
    response_store = ResponseStore(db)
    followup_store = FollowupStore(db)
    evaluation_store = EvaluationStore(db)

    monkeypatch.setattr("backend.api.case_responses.get_case_store", lambda: case_store)
    monkeypatch.setattr(
        "backend.api.case_responses.get_response_store", lambda: response_store
    )
    monkeypatch.setattr("backend.api.case_responses.get_action_store", lambda: action_store)
    monkeypatch.setattr(
        "backend.api.case_responses.get_followup_store", lambda: followup_store
    )
    monkeypatch.setattr(
        "backend.api.case_responses.get_evaluation_store", lambda: evaluation_store
    )

    case_id = case_store.create_case(
        "session-eval-persist",
        title="Rejected warranty claim",
        category="warranty",
        description="ASUS refused coverage.",
    )["id"]
    env = {
        "case_id": case_id,
        "case_store": case_store,
        "action_store": action_store,
        "response_store": response_store,
        "followup_store": followup_store,
        "evaluation_store": evaluation_store,
    }
    env["client"] = TestClient(app)
    return env


def _to_response_received(env):
    env["case_store"].transition_status(env["case_id"], "awaiting_response")
    env["case_store"].transition_status(env["case_id"], "response_received")
    env["response_store"].create_response(
        env["case_id"],
        source="simulated_support",
        content="We need more information before we can help.",
    )


def _patch_ai_evaluator(monkeypatch, outcome, confidence=0.87):
    def fake_evaluate(case_store, response_store, case_id, model=None):
        return EvaluationOutcome(
            outcome=outcome,
            confidence=confidence,
            reason="A concise, grounded reason.",
            next_step="A concrete next step.",
        )

    monkeypatch.setattr("backend.api.case_responses.evaluate_response", fake_evaluate)


def _evaluations(env):
    return env["evaluation_store"].list_evaluations_for_case(env["case_id"])


# --- Manual evaluation ---


def test_manual_evaluation_persists_record(env):
    _to_response_received(env)
    response = env["client"].post(
        f"/api/cases/{env['case_id']}/evaluate",
        json={"outcome": "resolved"},
    )
    assert response.status_code == 200
    assert response.json()["case"]["status"] == "resolved"

    records = _evaluations(env)
    assert len(records) == 1
    record = records[0]
    assert record["case_id"] == env["case_id"]
    assert record["outcome"] == "resolved"
    assert record["source"] == "manual"
    assert record["created_at"]


def test_manual_evaluation_persists_optional_fields(env):
    _to_response_received(env)
    response = env["client"].post(
        f"/api/cases/{env['case_id']}/evaluate",
        json={
            "outcome": "needs_follow_up",
            "confidence": 0.6,
            "reason": "Response was incomplete.",
            "next_step": "Request the missing document.",
        },
    )
    assert response.status_code == 200

    record = _evaluations(env)[0]
    assert record["outcome"] == "needs_follow_up"
    assert record["confidence"] == 0.6
    assert record["reason"] == "Response was incomplete."
    assert record["next_step"] == "Request the missing document."
    assert record["source"] == "manual"


def test_manual_evaluation_response_shape_unchanged(env):
    _to_response_received(env)
    response = env["client"].post(
        f"/api/cases/{env['case_id']}/evaluate",
        json={"outcome": "human_intervention"},
    )
    assert response.status_code == 200
    assert set(response.json().keys()) == {"case"}
    assert response.json()["case"]["status"] == "human_intervention"


def test_failed_manual_evaluation_does_not_create_record(env):
    _to_response_received(env)
    bad = env["client"].post(
        f"/api/cases/{env['case_id']}/evaluate",
        json={"outcome": "banana"},
    )
    assert bad.status_code == 400
    assert _evaluations(env) == []

    env["case_store"].transition_status(env["case_id"], "resolved")
    wrong_state = env["client"].post(
        f"/api/cases/{env['case_id']}/evaluate",
        json={"outcome": "resolved"},
    )
    assert wrong_state.status_code == 409
    assert _evaluations(env) == []


# --- AI evaluation ---


def test_ai_evaluation_persists_record(env, monkeypatch):
    _to_response_received(env)
    _patch_ai_evaluator(
        monkeypatch,
        "needs_follow_up",
        confidence=0.92,
    )
    response = env["client"].post(
        f"/api/cases/{env['case_id']}/evaluate-response"
    )
    assert response.status_code == 200

    records = _evaluations(env)
    assert len(records) == 1
    record = records[0]
    assert record["case_id"] == env["case_id"]
    assert record["outcome"] == "needs_follow_up"
    assert record["confidence"] == 0.92
    assert record["reason"] == "A concise, grounded reason."
    assert record["next_step"] == "A concrete next step."
    assert record["source"] == "ai"
    assert record["created_at"]


def test_ai_evaluation_response_shape_unchanged(env, monkeypatch):
    _to_response_received(env)
    _patch_ai_evaluator(monkeypatch, "resolved")
    response = env["client"].post(
        f"/api/cases/{env['case_id']}/evaluate-response"
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"evaluation", "followup", "case"}
    assert set(body["evaluation"].keys()) == {
        "outcome",
        "confidence",
        "reason",
        "next_step",
    }


def test_failed_ai_evaluation_does_not_create_record(env, monkeypatch):
    _to_response_received(env)

    def failing_evaluate(case_store, response_store, case_id, model=None):
        raise ValueError("model unavailable: 429")

    monkeypatch.setattr(
        "backend.api.case_responses.evaluate_response", failing_evaluate
    )
    response = env["client"].post(
        f"/api/cases/{env['case_id']}/evaluate-response"
    )
    assert response.status_code == 422
    assert _evaluations(env) == []
    assert env["case_store"].get_case(env["case_id"])["status"] == "response_received"


def test_ai_overflow_persists_raw_outcome(env, monkeypatch):
    _to_response_received(env)
    for _ in range(3):
        _patch_ai_evaluator(monkeypatch, "needs_follow_up")
        env["followup_store"].record_followup(
            env["case_id"], reason="r", confidence=0.8
        )
    _patch_ai_evaluator(monkeypatch, "needs_follow_up")
    response = env["client"].post(
        f"/api/cases/{env['case_id']}/evaluate-response"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["followup"]["overflowed_to_human_intervention"] is True
    assert body["case"]["status"] == "human_intervention"

    records = _evaluations(env)
    assert len(records) == 1
    assert records[0]["outcome"] == "needs_follow_up"
    assert records[0]["source"] == "ai"


# --- Error handling / atomicity ---


def test_ai_persistence_failure_returns_500_and_no_mutation(env, monkeypatch):
    _to_response_received(env)
    _patch_ai_evaluator(monkeypatch, "needs_follow_up")

    def boom(*args, **kwargs):
        raise RuntimeError("db locked")

    monkeypatch.setattr(env["evaluation_store"], "record_evaluation", boom)
    response = env["client"].post(
        f"/api/cases/{env['case_id']}/evaluate-response"
    )
    assert response.status_code == 500
    assert response.json()["detail"] == "failed to persist evaluation record"
    assert env["case_store"].get_case(env["case_id"])["status"] == "response_received"
    assert env["followup_store"].get_followup_count(env["case_id"]) == 0
    assert _evaluations(env) == []


def test_manual_persistence_failure_returns_500_and_no_mutation(env, monkeypatch):
    _to_response_received(env)

    def boom(*args, **kwargs):
        raise RuntimeError("db locked")

    monkeypatch.setattr(env["evaluation_store"], "record_evaluation", boom)
    response = env["client"].post(
        f"/api/cases/{env['case_id']}/evaluate",
        json={"outcome": "resolved"},
    )
    assert response.status_code == 500
    assert response.json()["detail"] == "failed to persist evaluation record"
    assert env["case_store"].get_case(env["case_id"])["status"] == "response_received"
    assert _evaluations(env) == []