import sqlite3

import pytest

from backend.services.case_store import CaseStore
from backend.services.evaluation_store import (
    EVALUATION_SOURCES,
    EvaluationStore,
)
from backend.services.user_store import UserStore
from conftest import create_test_user


@pytest.fixture
def env(tmp_path, user):
    path = tmp_path / "resolve.db"
    user_id = user["id"]
    case_store = CaseStore(path)
    evaluation_store = EvaluationStore(path)
    case1 = case_store.create_case(
        "session-eval-1",
        user_id=user_id,
        title="Case one",
        category="warranty",
        description="d1",
    )["id"]
    case2 = case_store.create_case(
        "session-eval-2",
        user_id=user_id,
        title="Case two",
        category="warranty",
        description="d2",
    )["id"]
    return {
        "path": path,
        "case1": case1,
        "case2": case2,
        "evaluation_store": evaluation_store,
    }


def test_record_evaluation_persists_all_fields(env):
    evaluation = env["evaluation_store"].record_evaluation(
        env["case1"],
        outcome="needs_follow_up",
        source="ai",
        confidence=0.87,
        reason="Support promised a future action without resolving the issue.",
        next_step="Send a follow-up requesting the promised update.",
    )
    assert evaluation["id"]
    assert evaluation["case_id"] == env["case1"]
    assert evaluation["outcome"] == "needs_follow_up"
    assert evaluation["confidence"] == 0.87
    assert evaluation["reason"] == (
        "Support promised a future action without resolving the issue."
    )
    assert evaluation["next_step"] == (
        "Send a follow-up requesting the promised update."
    )
    assert evaluation["source"] == "ai"
    assert evaluation["created_at"]

    stored = env["evaluation_store"].get_evaluation(evaluation["id"])
    assert stored == evaluation


def test_get_unknown_evaluation_returns_none(env):
    assert env["evaluation_store"].get_evaluation("missing") is None


def test_cases_are_scoped(env):
    env["evaluation_store"].record_evaluation(
        env["case1"], outcome="resolved", source="manual"
    )
    env["evaluation_store"].record_evaluation(
        env["case2"], outcome="human_intervention", source="manual"
    )
    only_a = env["evaluation_store"].list_evaluations_for_case(env["case1"])
    only_b = env["evaluation_store"].list_evaluations_for_case(env["case2"])
    assert [e["case_id"] for e in only_a] == [env["case1"]]
    assert [e["case_id"] for e in only_b] == [env["case2"]]


def test_list_empty_for_unknown_case(env):
    assert env["evaluation_store"].list_evaluations_for_case("nope") == []


def test_retrieval_order_is_chronological(env):
    store = env["evaluation_store"]
    store.record_evaluation(
        env["case1"], outcome="needs_follow_up", source="ai", reason="first"
    )
    store.record_evaluation(
        env["case1"], outcome="needs_follow_up", source="ai", reason="second"
    )
    store.record_evaluation(
        env["case1"], outcome="resolved", source="manual", reason="third"
    )
    evaluations = store.list_evaluations_for_case(env["case1"])
    assert len(evaluations) == 3
    assert [e["reason"] for e in evaluations] == ["first", "second", "third"]
    assert evaluations[0]["created_at"] <= evaluations[1]["created_at"]
    assert evaluations[1]["created_at"] <= evaluations[2]["created_at"]


def test_sources_are_preserved(env):
    manual = env["evaluation_store"].record_evaluation(
        env["case1"], outcome="resolved", source="manual", reason="covered"
    )
    ai = env["evaluation_store"].record_evaluation(
        env["case1"],
        outcome="needs_follow_up",
        source="ai",
        confidence=0.9,
        reason="incomplete",
        next_step="follow up",
    )
    by_source = {
        e["source"]: e
        for e in env["evaluation_store"].list_evaluations_for_case(env["case1"])
    }
    assert by_source["manual"]["id"] == manual["id"]
    assert by_source["ai"]["id"] == ai["id"]
    assert set(e["source"] for e in env["evaluation_store"].list_evaluations_for_case(
        env["case1"]
    )) == set(EVALUATION_SOURCES)


def test_restart_persistence(tmp_path, user):
    path = tmp_path / "resolve.db"
    case_store = CaseStore(path)
    case_id = case_store.create_case(
        "session-eval-persist",
        user_id=user["id"],
        title="Persisted case",
        category="warranty",
        description="d",
    )["id"]
    EvaluationStore(path).record_evaluation(
        case_id,
        outcome="needs_follow_up",
        source="ai",
        confidence=0.8,
        reason="r1",
        next_step="n1",
    )

    reloaded = EvaluationStore(path)
    evaluations = reloaded.list_evaluations_for_case(case_id)
    assert len(evaluations) == 1
    assert evaluations[0]["reason"] == "r1"
    assert evaluations[0]["next_step"] == "n1"
    assert evaluations[0]["outcome"] == "needs_follow_up"
    assert evaluations[0]["source"] == "ai"


def test_invalid_outcome_rejected(env):
    with pytest.raises(ValueError, match="invalid evaluation outcome"):
        env["evaluation_store"].record_evaluation(
            env["case1"], outcome="partially_resolved", source="manual"
        )


def test_invalid_source_rejected(env):
    with pytest.raises(ValueError, match="invalid evaluation source"):
        env["evaluation_store"].record_evaluation(
            env["case1"], outcome="resolved", source="agent"
        )


def test_non_numeric_confidence_rejected(env):
    with pytest.raises(ValueError, match="confidence must be numeric"):
        env["evaluation_store"].record_evaluation(
            env["case1"], outcome="resolved", source="manual", confidence="high"
        )


def test_followup_marker_persists_round_trip(env):
    evaluation = env["evaluation_store"].record_evaluation(
        env["case1"],
        outcome="needs_follow_up",
        source="ai",
        confidence=0.7,
        reason="r",
        next_step="s",
        followup_marker="awaiting",
    )
    assert evaluation["followup_marker"] == "awaiting"
    stored = env["evaluation_store"].get_evaluation(evaluation["id"])
    assert stored["followup_marker"] == "awaiting"
    listed = env["evaluation_store"].list_evaluations_for_case(env["case1"])
    assert listed[0]["followup_marker"] == "awaiting"


def test_followup_marker_defaults_to_none(env):
    evaluation = env["evaluation_store"].record_evaluation(
        env["case1"], outcome="resolved", source="ai"
    )
    assert evaluation["followup_marker"] is None


@pytest.mark.parametrize(
    "marker",
    ["awaiting", "exhausted/overflowed", "permanently_blocked", "resolved"],
)
def test_followup_marker_valid_vocabulary(env, marker):
    evaluation = env["evaluation_store"].record_evaluation(
        env["case1"],
        outcome="needs_follow_up",
        source="ai",
        followup_marker=marker,
    )
    assert evaluation["followup_marker"] == marker


def test_followup_marker_invalid_rejected(env):
    with pytest.raises(ValueError, match="invalid followup marker"):
        env["evaluation_store"].record_evaluation(
            env["case1"],
            outcome="needs_follow_up",
            source="ai",
            followup_marker="maybe",
        )


def test_followup_marker_rejected_for_manual_source(env):
    with pytest.raises(ValueError, match="only recorded for AI evaluations"):
        env["evaluation_store"].record_evaluation(
            env["case1"],
            outcome="resolved",
            source="manual",
            followup_marker="resolved",
        )


def test_legacy_database_is_migrated_with_marker_column(tmp_path, user):
    """A DB created before the marker column must be upgraded in place, with
    existing rows reading back followup_marker=None."""
    path = tmp_path / "legacy.db"
    user_id = create_test_user(UserStore(path))["id"]
    case_store = CaseStore(path)
    case_id = case_store.create_case(
        "session-legacy", user_id=user_id, title="T", category="warranty",
        description="d",
    )["id"]
    legacy_ddl = (
        "CREATE TABLE evaluations ("
        "id TEXT PRIMARY KEY, case_id TEXT NOT NULL, outcome TEXT NOT NULL, "
        "confidence REAL, reason TEXT, next_step TEXT, source TEXT NOT NULL, "
        "created_at TEXT NOT NULL, "
        "FOREIGN KEY (case_id) REFERENCES cases (id))"
    )
    with sqlite3.connect(path) as conn:
        conn.execute(legacy_ddl)
        conn.execute(
            "INSERT INTO evaluations "
            "(id, case_id, outcome, confidence, source, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("legacy-1", case_id, "resolved", 0.9, "manual", "2026-01-01T00:00:00"),
        )

    store = EvaluationStore(path)
    columns = {
        row[1] for row in sqlite3.connect(path).execute("PRAGMA table_info(evaluations)")
    }
    assert "followup_marker" in columns
    legacy = store.get_evaluation("legacy-1")
    assert legacy["outcome"] == "resolved"
    assert legacy["followup_marker"] is None

    store.record_evaluation(
        case_id,
        outcome="needs_follow_up",
        source="ai",
        followup_marker="awaiting",
    )
    records = store.list_evaluations_for_case(case_id)
    markers = {r["followup_marker"] for r in records}
    assert markers == {None, "awaiting"}