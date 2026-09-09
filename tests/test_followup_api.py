import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.action_executor import ActionExecutor
from backend.services.action_store import ActionStore
from backend.services.case_store import CaseStore
from backend.services.response_evaluator import EvaluationOutcome
from backend.services.response_store import ResponseStore


def _new_stores(tmp_path):
    db = tmp_path / "resolve.db"
    case_store = CaseStore(db)
    action_store = ActionStore(db)
    response_store = ResponseStore(db)
    from backend.services.followup_store import FollowupStore
    followup_store = FollowupStore(db)
    return case_store, action_store, response_store, followup_store


@pytest.fixture
def env(tmp_path, monkeypatch):
    case_store, action_store, response_store, followup_store = _new_stores(tmp_path)

    def _patch():
        monkeypatch.setattr("backend.api.case_responses.get_case_store", lambda: case_store)
        monkeypatch.setattr("backend.api.case_responses.get_response_store", lambda: response_store)
        monkeypatch.setattr("backend.api.case_responses.get_action_store", lambda: action_store)
        monkeypatch.setattr(
            "backend.api.case_responses.get_followup_store", lambda: followup_store
        )
        monkeypatch.setattr(
            "backend.api.actions.get_case_store", lambda: case_store
        )
        monkeypatch.setattr(
            "backend.api.actions.get_action_store", lambda: action_store
        )
        monkeypatch.setattr(
            "backend.api.actions.get_executor",
            lambda: ActionExecutor(action_store, case_store),
        )

    _patch()

    case_id = case_store.create_case(
        "session-followup",
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
    }
    env["client"] = TestClient(app)
    return env


def _to(env, status):
    env["case_store"].transition_status(env["case_id"], status)


def _to_response_received(env):
    _to(env, "awaiting_response")
    _to(env, "response_received")
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
    return fake_evaluate


def _patch_preparer(monkeypatch):
    from backend.services.followup_preparer import PreparedActionResult

    def fake_prepare(
        case_store, response_store, action_store, followup_store, case_id,
        model=None, agent=None,
    ):
        return PreparedActionResult(
            type="escalation",
            title="Follow-up: provide additional evidence",
            reason="Support requested evidence that the case already records.",
            content="We already provided the required evidence. Please reassess.",
            target="ASUS Support",
        )

    monkeypatch.setattr("backend.api.case_responses.prepare_followup_action", fake_prepare)


def _drive_full_followup_cycle(env, monkeypatch):
    """One full follow-up cycle: eval needs_follow_up -> prepare -> approve -> execute -> record response."""
    _patch_ai_evaluator(monkeypatch, "needs_follow_up")
    _patch_preparer(monkeypatch)
    client = env["client"]
    case_id = env["case_id"]

    eval_resp = client.post(f"/api/cases/{case_id}/evaluate-response")
    assert eval_resp.status_code == 200
    followup = eval_resp.json()["followup"]
    assert followup["followup_used"] is True

    prep_resp = client.post(f"/api/cases/{case_id}/prepare-followup")
    assert prep_resp.status_code == 200
    action = prep_resp.json()["action"]
    assert action["status"] == "pending_approval"

    approve_resp = client.post(f"/api/actions/{action['id']}/approve")
    assert approve_resp.status_code == 200

    execute_resp = client.post(f"/api/actions/{action['id']}/execute")
    assert execute_resp.status_code == 200
    assert execute_resp.json()["action"]["status"] == "executed"

    case = env["case_store"].get_case(case_id)
    assert case["status"] == "awaiting_response"

    record_resp = client.post(
        f"/api/cases/{case_id}/responses",
        json={"source": "simulated_support", "content": "Another support reply."},
    )
    assert record_resp.status_code == 200
    assert record_resp.json()["case"]["status"] == "response_received"
    return followup


# --- Core follow-up lifecycle ---

def test_first_needs_followup_records_attempt(env, monkeypatch):
    _to_response_received(env)
    _patch_ai_evaluator(monkeypatch, "needs_follow_up")
    response = env["client"].post(
        f"/api/cases/{env['case_id']}/evaluate-response"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["case"]["status"] == "needs_follow_up"
    assert body["followup"]["count"] == 1
    assert body["followup"]["max_followups"] == 3
    assert body["followup"]["overflowed_to_human_intervention"] is False
    assert body["followup"]["followup_used"] is True


def test_followup_count_increments_across_cycles(env, monkeypatch):
    _to_response_received(env)
    cyc1 = _drive_full_followup_cycle(env, monkeypatch)
    assert cyc1["count"] == 1
    cyc2 = _drive_full_followup_cycle(env, monkeypatch)
    assert cyc2["count"] == 2


def test_followup_action_created_pending_approval(env, monkeypatch):
    _to_response_received(env)
    _patch_ai_evaluator(monkeypatch, "needs_follow_up")
    _patch_preparer(monkeypatch)
    env["client"].post(f"/api/cases/{env['case_id']}/evaluate-response")
    response = env["client"].post(
        f"/api/cases/{env['case_id']}/prepare-followup"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["action"]["status"] == "pending_approval"
    assert body["action"]["case_id"] == env["case_id"]
    assert body["action"]["title"] == "Follow-up: provide additional evidence"
    assert body["followup"]["count"] == 1


def test_followup_action_cannot_execute_before_approval(env, monkeypatch):
    _to_response_received(env)
    _patch_ai_evaluator(monkeypatch, "needs_follow_up")
    _patch_preparer(monkeypatch)
    env["client"].post(f"/api/cases/{env['case_id']}/evaluate-response")
    prep = env["client"].post(
        f"/api/cases/{env['case_id']}/prepare-followup"
    ).json()["action"]
    response = env["client"].post(f"/api/actions/{prep['id']}/execute")
    assert response.status_code == 409
    assert "only approved actions may be executed" in response.json()["detail"]


def test_approved_followup_executes_through_simulated_executor(env, monkeypatch):
    _to_response_received(env)
    _patch_ai_evaluator(monkeypatch, "needs_follow_up")
    _patch_preparer(monkeypatch)
    client = env["client"]
    case_id = env["case_id"]

    client.post(f"/api/cases/{case_id}/evaluate-response")
    action = client.post(f"/api/cases/{case_id}/prepare-followup").json()["action"]
    client.post(f"/api/actions/{action['id']}/approve")
    execute_resp = client.post(f"/api/actions/{action['id']}/execute")
    assert execute_resp.status_code == 200
    executed = execute_resp.json()["action"]
    assert executed["status"] == "executed"
    assert executed["execution_reference"].startswith("RESOLVE-ACTION-")
    assert executed["execution_result"]

    case = env["case_store"].get_case(case_id)
    assert case["status"] == "awaiting_response"


def test_second_response_can_be_evaluated(env, monkeypatch):
    _to_response_received(env)
    _drive_full_followup_cycle(env, monkeypatch)
    _patch_ai_evaluator(monkeypatch, "needs_follow_up")
    response = env["client"].post(
        f"/api/cases/{env['case_id']}/evaluate-response"
    )
    assert response.status_code == 200
    assert response.json()["case"]["status"] == "needs_follow_up"
    assert response.json()["followup"]["count"] == 2


def test_followup_status_reports_can_prepare(env, monkeypatch):
    _to_response_received(env)
    _patch_ai_evaluator(monkeypatch, "needs_follow_up")
    env["client"].post(f"/api/cases/{env['case_id']}/evaluate-response")
    status = env["client"].get(
        f"/api/cases/{env['case_id']}/followup-status"
    )
    assert status.status_code == 200
    body = status.json()
    assert body["case_status"] == "needs_follow_up"
    assert body["followup_count"] == 1
    assert body["max_followups"] == 3
    assert body["can_prepare_action"] is True
    assert len(body["attempts"]) == 1


# --- Maximum enforcement ---

def test_maximum_followup_count_enforced(env, monkeypatch):
    _to_response_received(env)
    for _ in range(3):
        _drive_full_followup_cycle(env, monkeypatch)
    assert env["followup_store"].get_followup_count(env["case_id"]) == 3

    _patch_ai_evaluator(monkeypatch, "needs_follow_up")
    response = env["client"].post(
        f"/api/cases/{env['case_id']}/evaluate-response"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["case"]["status"] == "human_intervention"
    assert body["followup"]["overflowed_to_human_intervention"] is True
    assert body["followup"]["count"] == 3
    assert body["evaluation"]["outcome"] == "needs_follow_up"


def test_after_max_attempts_no_more_preparation(env, monkeypatch):
    _to_response_received(env)
    for _ in range(3):
        _drive_full_followup_cycle(env, monkeypatch)
    _patch_ai_evaluator(monkeypatch, "needs_follow_up")
    _patch_preparer(monkeypatch)
    env["client"].post(f"/api/cases/{env['case_id']}/evaluate-response")
    assert env["case_store"].get_case(env["case_id"])["status"] == "human_intervention"
    prep = env["client"].post(
        f"/api/cases/{env['case_id']}/prepare-followup"
    )
    assert prep.status_code == 409


# --- Early termination ---

def test_ai_human_intervention_stops_loop(env, monkeypatch):
    _to_response_received(env)
    _patch_ai_evaluator(monkeypatch, "human_intervention")
    response = env["client"].post(
        f"/api/cases/{env['case_id']}/evaluate-response"
    )
    assert response.status_code == 200
    assert response.json()["case"]["status"] == "human_intervention"
    assert response.json()["followup"]["count"] == 0


def test_ai_resolved_stops_loop(env, monkeypatch):
    _to_response_received(env)
    _patch_ai_evaluator(monkeypatch, "resolved")
    response = env["client"].post(
        f"/api/cases/{env['case_id']}/evaluate-response"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["case"]["status"] == "resolved"
    assert body["case"]["resolved_at"] is not None


def test_resolved_cannot_receive_followup(env, monkeypatch):
    _to_response_received(env)
    _patch_ai_evaluator(monkeypatch, "resolved")
    env["client"].post(f"/api/cases/{env['case_id']}/evaluate-response")
    prep = env["client"].post(
        f"/api/cases/{env['case_id']}/prepare-followup"
    )
    assert prep.status_code == 409
    assert "cannot prepare a follow-up" in prep.json()["detail"]


def test_human_intervention_cannot_receive_followup(env, monkeypatch):
    _to_response_received(env)
    _patch_ai_evaluator(monkeypatch, "human_intervention")
    env["client"].post(f"/api/cases/{env['case_id']}/evaluate-response")
    prep = env["client"].post(
        f"/api/cases/{env['case_id']}/prepare-followup"
    )
    assert prep.status_code == 409


# --- Error handling ---

def test_evaluate_response_wrong_state_409(env, monkeypatch):
    _patch_ai_evaluator(monkeypatch, "resolved")
    response = env["client"].post(
        f"/api/cases/{env['case_id']}/evaluate-response"
    )
    assert response.status_code == 409


def test_evaluate_response_unknown_case_404(env, monkeypatch):
    _patch_ai_evaluator(monkeypatch, "resolved")
    response = env["client"].post("/api/cases/missing/evaluate-response")
    assert response.status_code == 404


def test_failed_ai_evaluation_no_mutation(env, monkeypatch):
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
    assert env["case_store"].get_case(env["case_id"])["status"] == "response_received"
    assert env["followup_store"].get_followup_count(env["case_id"]) == 0


def test_failed_preparation_no_action_no_mutation(env, monkeypatch):
    _to_response_received(env)
    _patch_ai_evaluator(monkeypatch, "needs_follow_up")
    env["client"].post(f"/api/cases/{env['case_id']}/evaluate-response")

    def failing_prepare(case_store, response_store, action_store, followup_store,
                        case_id, model=None, agent=None):
        raise ValueError("model unavailable")

    monkeypatch.setattr(
        "backend.api.case_responses.prepare_followup_action", failing_prepare
    )
    response = env["client"].post(
        f"/api/cases/{env['case_id']}/prepare-followup"
    )
    assert response.status_code == 422
    assert env["action_store"].list_actions_for_case(env["case_id"]) == []
    assert env["case_store"].get_case(env["case_id"])["status"] == "needs_follow_up"


def test_prepare_followup_wrong_state_409(env, monkeypatch):
    _patch_preparer(monkeypatch)
    response = env["client"].post(
        f"/api/cases/{env['case_id']}/prepare-followup"
    )
    assert response.status_code == 409


def test_prepare_followup_unknown_case_404(env, monkeypatch):
    _patch_preparer(monkeypatch)
    assert env["client"].post("/api/cases/missing/prepare-followup").status_code == 404


def test_failed_execution_does_not_advance_case(env, monkeypatch):
    env["case_store"].transition_status(env["case_id"], "awaiting_response")
    env["case_store"].transition_status(env["case_id"], "response_received")
    env["case_store"].transition_status(env["case_id"], "needs_follow_up")

    action = env["action_store"].create_action(
        env["case_id"],
        type="escalation",
        title="Follow-up action",
        reason="Follow-up required",
        content="Please reassess.",
    )["id"]
    env["action_store"].submit_for_approval(action)
    env["action_store"].approve_action(action)

    class FailingChannel:
        def submit(self, action):
            raise RuntimeError("simulated channel failure")

    failing_executor = ActionExecutor(
        env["action_store"], env["case_store"], channel=FailingChannel()
    )
    monkeypatch.setattr(
        "backend.api.actions.get_executor", lambda: failing_executor
    )
    response = env["client"].post(f"/api/actions/{action}/execute")
    assert response.status_code == 200
    failed = response.json()["action"]
    assert failed["status"] == "failed"
    assert failed["execution_error"]
    assert env["case_store"].get_case(env["case_id"])["status"] == "needs_follow_up"


def test_followup_status_unknown_case_404(env):
    assert env["client"].get("/api/cases/missing/followup-status").status_code == 404