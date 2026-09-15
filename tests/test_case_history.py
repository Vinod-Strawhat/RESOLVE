import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.action_store import ActionStore
from backend.services.auth import COOKIE_NAME
from backend.services.case_history import build_case_history
from backend.services.case_store import CaseStore
from backend.services.evaluation_store import EvaluationStore
from backend.services.followup_store import FollowupStore
from backend.services.response_store import ResponseStore
from backend.services.session_store import SessionStore
from backend.services.user_store import UserStore
from conftest import create_test_user, issue_auth_token


@pytest.fixture
def env(tmp_path, monkeypatch):
    db = tmp_path / "resolve.db"
    user = create_test_user(UserStore(db))
    session_store = SessionStore(db)
    case_store = CaseStore(db)
    response_store = ResponseStore(db)
    evaluation_store = EvaluationStore(db)
    action_store = ActionStore(db)
    followup_store = FollowupStore(db)

    monkeypatch.setattr("backend.api.history.get_case_store", lambda: case_store)
    monkeypatch.setattr(
        "backend.api.dependencies.get_case_store", lambda: case_store
    )
    monkeypatch.setattr("backend.api.history.get_response_store", lambda: response_store)
    monkeypatch.setattr(
        "backend.api.history.get_evaluation_store", lambda: evaluation_store
    )
    monkeypatch.setattr("backend.api.history.get_action_store", lambda: action_store)
    monkeypatch.setattr(
        "backend.api.history.get_followup_store", lambda: followup_store
    )
    monkeypatch.setattr(
        "backend.api.dependencies.get_user_store", lambda: UserStore(db)
    )
    monkeypatch.setattr(
        "backend.api.dependencies.get_session_store", lambda: session_store
    )

    def _new_case(session_id):
        return case_store.create_case(
            session_id,
            user_id=user["id"],
            title="Rejected warranty claim",
            category="warranty",
            description="ASUS refused coverage.",
        )

    case_id = _new_case("session-history")["id"]
    env = {
        "case_id": case_id,
        "case_store": case_store,
        "response_store": response_store,
        "evaluation_store": evaluation_store,
        "action_store": action_store,
        "followup_store": followup_store,
        "_new_case": _new_case,
    }
    env["client"] = TestClient(app)
    env["client"].cookies.set(
        COOKIE_NAME, issue_auth_token(session_store, user["id"])
    )
    return env


def _seed_full_activity(env):
    env["response_store"].create_response(
        env["case_id"], source="simulated_support", content="Please provide evidence."
    )
    env["evaluation_store"].record_evaluation(
        env["case_id"],
        outcome="needs_follow_up",
        source="ai",
        confidence=0.85,
        reason="Evidence missing.",
        next_step="Ask for proof of purchase.",
    )
    env["followup_store"].record_followup(
        env["case_id"], reason="Evidence missing.", confidence=0.85
    )
    action = env["action_store"].create_action(
        env["case_id"],
        type="escalation",
        title="Follow-up: request evidence",
        reason="Evidence is missing.",
        content="Please provide proof of purchase.",
        target="ASUS Support",
    )
    env["action_store"].submit_for_approval(action["id"])
    env["action_store"].approve_action(action["id"])
    env["action_store"].begin_execution(action["id"], channel_name="simulated")
    env["action_store"].complete_execution(
        action["id"], reference="RESOLVE-ACTION-1234", result="simulated done"
    )


def test_history_returns_all_event_types(env):
    _seed_full_activity(env)
    response = env["client"].get(f"/api/cases/{env['case_id']}/history")
    assert response.status_code == 200
    body = response.json()
    assert body["case_id"] == env["case_id"]
    assert body["case"]["id"] == env["case_id"]

    types = [e["event_type"] for e in body["events"]]
    assert types.count("case_created") == 1
    assert types.count("response") == 1
    assert types.count("evaluation") == 1
    assert types.count("action") == 1
    assert types.count("followup") == 1


def test_history_event_shapes(env):
    _seed_full_activity(env)
    events = env["client"].get(f"/api/cases/{env['case_id']}/history").json()["events"]
    by_type = {e["event_type"]: e for e in events}

    response_event = by_type["response"]
    assert response_event["source"] == "simulated_support"
    assert response_event["detail"]["content"] == "Please provide evidence."

    evaluation_event = by_type["evaluation"]
    assert evaluation_event["status"] == "needs_follow_up"
    assert evaluation_event["source"] == "ai"
    assert evaluation_event["detail"]["confidence"] == 0.85
    assert evaluation_event["detail"]["reason"] == "Evidence missing."
    assert evaluation_event["detail"]["next_step"] == "Ask for proof of purchase."

    followup_event = by_type["followup"]
    assert followup_event["detail"]["attempt_number"] == 1
    assert followup_event["detail"]["reason"] == "Evidence missing."
    assert followup_event["detail"]["confidence"] == 0.85

    action_event = by_type["action"]
    assert action_event["status"] == "executed"
    assert action_event["detail"]["type"] == "escalation"
    assert action_event["detail"]["execution_channel"] == "simulated"
    assert action_event["detail"]["execution_reference"] == "RESOLVE-ACTION-1234"
    assert action_event["detail"]["execution_result"] == "simulated done"
    assert "Evidence is missing." in action_event["detail"]["reason"]


def test_history_chronologically_ordered(env):
    _seed_full_activity(env)
    events = env["client"].get(f"/api/cases/{env['case_id']}/history").json()["events"]
    assert events[0]["event_type"] == "case_created"
    assert events[1]["event_type"] == "response"
    assert events[2]["event_type"] == "evaluation"
    assert events[3]["event_type"] == "followup"
    assert events[4]["event_type"] == "action"

    stamps = [e["occurred_at"] for e in events]
    assert stamps == sorted(stamps)


def test_history_excludes_other_cases(env):
    other = env["_new_case"]("session-history-other")
    env["response_store"].create_response(
        other["id"], source="simulated_support", content="Other response."
    )
    env["evaluation_store"].record_evaluation(
        other["id"], outcome="resolved", source="manual"
    )
    env["action_store"].create_action(
        other["id"],
        type="refund_request",
        title="Other action",
        reason="Other",
        content="Other",
    )
    _seed_full_activity(env)

    events = env["client"].get(f"/api/cases/{env['case_id']}/history").json()["events"]
    for event in events:
        if event["event_type"] == "response":
            assert event["detail"]["content"] != "Other response."
        if event["event_type"] == "evaluation":
            assert event["status"] != "resolved"
        if event["event_type"] == "action":
            assert event["detail"]["title"] != "Other action"
    assert len(events) == 5


def test_history_empty_has_only_creation_marker(env):
    body = env["client"].get(f"/api/cases/{env['case_id']}/history").json()
    assert len(body["events"]) == 1
    event = body["events"][0]
    assert event["event_type"] == "case_created"
    assert event["title"] == "Case created"
    assert event["id"] == env["case_id"]
    assert event["occurred_at"] == env["case_store"].get_case(env["case_id"])[
        "created_at"
    ]


def test_history_resolved_marker(env):
    env["case_store"].transition_status(env["case_id"], "awaiting_response")
    env["case_store"].transition_status(env["case_id"], "response_received")
    env["case_store"].transition_status(env["case_id"], "resolved")
    events = env["client"].get(f"/api/cases/{env['case_id']}/history").json()["events"]
    by_type = {e["event_type"]: e for e in events}
    assert by_type["case_resolved"]["status"] == "resolved"
    assert (
        by_type["case_resolved"]["occurred_at"]
        == env["case_store"].get_case(env["case_id"])["resolved_at"]
    )


def test_history_unknown_case_404(env):
    response = env["client"].get("/api/cases/does-not-exist/history")
    assert response.status_code == 404
    assert response.json()["detail"] == "case not found"


# --- Unit-level determinism (equal timestamps) ---


class _FakeStore:
    def __init__(self, records):
        self._records = records

    def list_responses_for_case(self, case_id):
        return [r for r in self._records if r.get("_kind") == "response"]

    def list_evaluations_for_case(self, case_id):
        return [r for r in self._records if r.get("_kind") == "evaluation"]

    def list_actions_for_case(self, case_id):
        return [r for r in self._records if r.get("_kind") == "action"]

    def get_followup_history(self, case_id):
        return [r for r in self._records if r.get("_kind") == "followup"]


def _row(kind, **fields):
    row = {"_kind": kind}
    row.update(fields)
    return row


def test_builder_equal_timestamps_uses_rank_then_source_order():
    stamp = "2026-01-01T00:00:00+00:00"
    case = {"id": "case-1", "created_at": stamp}
    store = _FakeStore(
        [
            _row("evaluation", id="eval-2", created_at=stamp, outcome="resolved",
                 source="manual", confidence=0.0, reason="", next_step=""),
            _row("action", id="act-1", created_at=stamp, type="escalation",
                 title="A", reason="r", content="c", target="", status="approved",
                 execution_channel=None, execution_reference=None,
                 execution_result=None, execution_error=None, executed_at=None),
            _row("response", id="resp-1", created_at=stamp, received_at=stamp,
                 source="simulated_support", content="hi"),
            _row("followup", id="fu-1", created_at=stamp, attempt_number=1,
                 evaluation_reason="r", evaluation_confidence=0.5),
        ]
    )
    events = build_case_history(
        case,
        response_store=store,
        evaluation_store=store,
        action_store=store,
        followup_store=store,
    )
    assert [e["event_type"] for e in events] == [
        "case_created",
        "response",
        "evaluation",
        "action",
        "followup",
    ]


def test_builder_equal_timestamps_stable_within_source():
    stamp = "2026-01-01T00:00:00+00:00"
    case = {"id": "case-1", "created_at": stamp}
    store = _FakeStore(
        [
            _row("evaluation", id="eval-first", created_at=stamp, outcome="needs_follow_up",
                 source="ai", confidence=0.5, reason="r", next_step="n"),
            _row("evaluation", id="eval-second", created_at=stamp, outcome="resolved",
                 source="manual", confidence=0.0, reason="", next_step=""),
        ]
    )
    events = build_case_history(
        case,
        response_store=store,
        evaluation_store=store,
        action_store=store,
        followup_store=store,
    )
    evaluation_ids = [e["id"] for e in events if e["event_type"] == "evaluation"]
    assert evaluation_ids == ["eval-first", "eval-second"]