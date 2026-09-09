import pytest

from backend.services.case_store import CaseStore
from backend.services.followup_store import FollowupStore, DEFAULT_MAX_FOLLOWUPS


@pytest.fixture
def store(tmp_path):
    path = tmp_path / "followups.db"
    case_store = CaseStore(path)
    followups = FollowupStore(path)
    followups.case1 = case_store.create_case(
        "session-fu-store",
        title="Case one",
        category="warranty",
        description="d1",
    )["id"]
    followups.case2 = case_store.create_case(
        "session-fu-store-2",
        title="Case two",
        category="warranty",
        description="d2",
    )["id"]
    return followups


def test_count_zero_for_empty_case(store):
    assert store.get_followup_count("missing") == 0


def test_record_and_count(store):
    store.record_followup(store.case1, reason="Need more info", confidence=0.8)
    assert store.get_followup_count(store.case1) == 1


def test_record_multiple(store):
    store.record_followup(store.case1, reason="r1", confidence=0.8)
    store.record_followup(store.case1, reason="r2", confidence=0.7)
    store.record_followup(store.case1, reason="r3", confidence=0.6)
    assert store.get_followup_count(store.case1) == 3


def test_cases_are_scoped(store):
    store.record_followup(store.case1, reason="r1")
    store.record_followup(store.case2, reason="r2")
    assert store.get_followup_count(store.case1) == 1
    assert store.get_followup_count(store.case2) == 1


def test_attempt_number_increments(store):
    r1 = store.record_followup(store.case1, reason="r1")
    r2 = store.record_followup(store.case1, reason="r2")
    r3 = store.record_followup(store.case1, reason="r3")
    assert r1["attempt_number"] == 1
    assert r2["attempt_number"] == 2
    assert r3["attempt_number"] == 3


def test_history_order(store):
    store.record_followup(store.case1, reason="second", confidence=0.7)
    store.record_followup(store.case1, reason="first", confidence=0.9)
    history = store.get_followup_history(store.case1)
    assert len(history) == 2
    assert history[0]["attempt_number"] == 1
    assert history[1]["attempt_number"] == 2
    assert history[0]["evaluation_reason"] == "second"
    assert history[1]["evaluation_reason"] == "first"


def test_history_empty(store):
    assert store.get_followup_history("missing") == []


def test_recorded_fields(store):
    record = store.record_followup(
        store.case1, reason="because", confidence=0.55
    )
    assert record["case_id"] == store.case1
    assert record["attempt_number"] == 1
    assert record["evaluation_reason"] == "because"
    assert record["evaluation_confidence"] == 0.55
    assert record["created_at"]
    assert record["id"]


def test_restart_persistence(tmp_path):
    path = tmp_path / "followups.db"
    case_store = CaseStore(path)
    case_id = case_store.create_case(
        "session-fu-store",
        title="Case one",
        category="warranty",
        description="d",
    )["id"]
    s1 = FollowupStore(path)
    s1.record_followup(case_id, reason="r1")
    s1.record_followup(case_id, reason="r2")
    del s1

    s2 = FollowupStore(path)
    assert s2.get_followup_count(case_id) == 2
    history = s2.get_followup_history(case_id)
    assert len(history) == 2
    assert history[0]["evaluation_reason"] == "r1"
    assert history[1]["evaluation_reason"] == "r2"


def test_default_max_followups():
    assert DEFAULT_MAX_FOLLOWUPS == 3