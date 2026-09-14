from fastapi.testclient import TestClient

from backend.main import app
from backend.services.case_store import CaseStore
from backend.services.evaluation_store import EvaluationStore


def _new_stores(tmp_path):
    db = tmp_path / "resolve.db"
    case_store = CaseStore(db)
    evaluation_store = EvaluationStore(db)
    return case_store, evaluation_store


def _set_up(monkeypatch, tmp_path):
    case_store, evaluation_store = _new_stores(tmp_path)
    monkeypatch.setattr(
        "backend.api.case_responses.get_case_store", lambda: case_store
    )
    monkeypatch.setattr(
        "backend.api.case_responses.get_evaluation_store", lambda: evaluation_store
    )
    case_id = case_store.create_case(
        "session-evals-api",
        title="Rejected warranty claim",
        category="warranty",
        description="ASUS refused coverage.",
    )["id"]
    return {
        "case_store": case_store,
        "evaluation_store": evaluation_store,
        "case_id": case_id,
        "client": TestClient(app),
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
    _set_up(monkeypatch, tmp_path)
    response = TestClient(app).get("/api/cases/no-such-case/evaluations")
    assert response.status_code == 404
    assert response.json()["detail"] == "case not found"


def test_evaluations_do_not_leak_between_cases(monkeypatch, tmp_path):
    env = _set_up(monkeypatch, tmp_path)
    other_id = env["case_store"].create_case(
        "session-evals-other",
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