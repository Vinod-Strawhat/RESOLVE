from fastapi.testclient import TestClient

import pytest

from backend.main import app
from backend.services.auth import COOKIE_NAME
from backend.services.case_store import CaseStore
from backend.services.evaluation_store import EvaluationStore
from backend.services.session_store import SessionStore
from backend.services.user_store import UserStore
from conftest import create_test_user, issue_auth_token


def _new_stores(tmp_path):
    db = tmp_path / "resolve.db"
    user = create_test_user(UserStore(db))
    session_store = SessionStore(db)
    case_store = CaseStore(db)
    evaluation_store = EvaluationStore(db)
    return case_store, evaluation_store, user, session_store


def _set_up(monkeypatch, tmp_path):
    case_store, evaluation_store, user, session_store = _new_stores(tmp_path)
    monkeypatch.setattr(
        "backend.api.case_responses.get_case_store", lambda: case_store
    )
    monkeypatch.setattr(
        "backend.api.dependencies.get_case_store", lambda: case_store
    )
    monkeypatch.setattr(
        "backend.api.case_responses.get_evaluation_store", lambda: evaluation_store
    )
    monkeypatch.setattr(
        "backend.api.dependencies.get_user_store", lambda: UserStore(tmp_path / "resolve.db")
    )
    monkeypatch.setattr(
        "backend.api.dependencies.get_session_store", lambda: session_store
    )
    case_id = case_store.create_case(
        "session-evals-api",
        user_id=user["id"],
        title="Rejected warranty claim",
        category="warranty",
        description="ASUS refused coverage.",
    )["id"]
    client = TestClient(app)
    client.cookies.set(COOKIE_NAME, issue_auth_token(session_store, user["id"]))
    return {
        "case_store": case_store,
        "evaluation_store": evaluation_store,
        "case_id": case_id,
        "client": client,
    }


def test_list_evaluations_empty(monkeypatch, tmp_path):
    env = _set_up(monkeypatch, tmp_path)
    response = env["client"].get(f"/api/cases/{env['case_id']}/evaluations")
    assert response.status_code == 200
    assert response.json() == {"case_id": env["case_id"], "evaluations": []}


def test_list_evaluations_round_trip_in_order(monkeypatch, tmp_path):
    env = _set_up(monkeypatch, tmp_path)
    env["evaluation_store"].record_evaluation(
        env["case_id"],
        outcome="needs_follow_up",
        source="ai",
        confidence=0.8,
        reason="first",
        next_step="ask again",
    )
    env["evaluation_store"].record_evaluation(
        env["case_id"],
        outcome="resolved",
        source="manual",
        confidence=0.0,
    )
    response = env["client"].get(f"/api/cases/{env['case_id']}/evaluations")
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"case_id", "evaluations"}
    records = body["evaluations"]
    assert [r["outcome"] for r in records] == ["needs_follow_up", "resolved"]
    assert [r["source"] for r in records] == ["ai", "manual"]
    assert records[0]["confidence"] == 0.8
    assert records[1]["confidence"] == 0.0
    assert records[0]["reason"] == "first"
    assert records[0]["next_step"] == "ask again"


def test_list_evaluations_unknown_case_404(monkeypatch, tmp_path):
    env = _set_up(monkeypatch, tmp_path)
    response = env["client"].get("/api/cases/no-such-case/evaluations")
    assert response.status_code == 404
    assert response.json()["detail"] == "case not found"


def test_evaluations_do_not_leak_between_cases(monkeypatch, tmp_path):
    env = _set_up(monkeypatch, tmp_path)
    other_id = env["case_store"].create_case(
        "session-evals-other",
        user_id=env["case_store"].get_case(env["case_id"])["user_id"],
        title="Another claim",
        category="refund",
        description="Other case.",
    )["id"]
    env["evaluation_store"].record_evaluation(
        env["case_id"],
        outcome="resolved",
        source="manual",
    )
    env["evaluation_store"].record_evaluation(
        other_id,
        outcome="human_intervention",
        source="ai",
    )
    body = env["client"].get(f"/api/cases/{env['case_id']}/evaluations").json()
    assert [r["case_id"] for r in body["evaluations"]] == [env["case_id"]]
    assert body["evaluations"][0]["outcome"] == "resolved"


def test_evaluations_listed_after_manual_endpoint(monkeypatch, tmp_path):
    env = _set_up(monkeypatch, tmp_path)
    env["case_store"].transition_status(env["case_id"], "awaiting_response")
    env["case_store"].transition_status(env["case_id"], "response_received")
    post = env["client"].post(
        f"/api/cases/{env['case_id']}/evaluate",
        json={"outcome": "needs_follow_up", "confidence": 0.6, "reason": "r"},
    )
    assert post.status_code == 200
    body = env["client"].get(f"/api/cases/{env['case_id']}/evaluations").json()
    records = body["evaluations"]
    assert len(records) == 1
    assert records[0]["outcome"] == "needs_follow_up"
    assert records[0]["confidence"] == 0.6
    assert records[0]["reason"] == "r"
    assert records[0]["source"] == "manual"


def test_manual_evaluations_have_no_followup_marker(monkeypatch, tmp_path):
    """The follow-up marker is AI-evaluation only; manual rows stay None."""
    env = _set_up(monkeypatch, tmp_path)
    env["case_store"].transition_status(env["case_id"], "awaiting_response")
    env["case_store"].transition_status(env["case_id"], "response_received")
    post = env["client"].post(
        f"/api/cases/{env['case_id']}/evaluate",
        json={"outcome": "resolved", "confidence": 0.9, "reason": "manual close"},
    )
    assert post.status_code == 200
    records = env["client"].get(
        f"/api/cases/{env['case_id']}/evaluations"
    ).json()["evaluations"]
    assert "followup_marker" in records[0]
    assert records[0]["followup_marker"] is None


def test_followup_marker_rejected_for_manual_source(tmp_path):
    _case_store, evaluation_store, _user, _session = _new_stores(tmp_path)
    with pytest.raises(ValueError, match="only recorded for AI evaluations"):
        evaluation_store.record_evaluation(
            "case-x",
            outcome="resolved",
            source="manual",
            followup_marker="resolved",
        )


def test_followup_marker_round_trip(monkeypatch, tmp_path):
    env = _set_up(monkeypatch, tmp_path)
    env["evaluation_store"].record_evaluation(
        env["case_id"], outcome="needs_follow_up", source="ai",
        confidence=0.7, reason="pending", next_step="ask again",
        followup_marker="awaiting",
    )
    records = env["client"].get(
        f"/api/cases/{env['case_id']}/evaluations"
    ).json()["evaluations"]
    assert records[0]["followup_marker"] == "awaiting"