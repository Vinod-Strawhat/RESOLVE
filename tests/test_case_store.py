import pytest

from backend.services.case_store import CaseStore


@pytest.fixture
def store(tmp_path):
    return CaseStore(tmp_path / "resolve.db")


def test_create_and_get_case(store):
    case_id = store.create_case(
        "session-abc",
        title="Rejected warranty claim",
        category="warranty",
        description="Company refused to cover the damage.",
    )["id"]
    case = store.get_case(case_id)
    assert case["id"] == case_id
    assert case["session_id"] == "session-abc"
    assert case["title"] == "Rejected warranty claim"
    assert case["category"] == "warranty"
    assert case["description"].startswith("Company refused")
    assert case["status"] is None
    assert case["created_at"]
    assert case["updated_at"]


def test_get_case_unknown_returns_none(store):
    assert store.get_case("missing") is None


def test_get_case_by_session(store):
    store.create_case(
        "session-abc",
        title="Title",
        category="refund",
        description="Description",
    )
    case = store.get_case_by_session("session-abc")
    assert case is not None
    assert case["category"] == "refund"


def test_get_case_by_session_unknown_returns_none(store):
    assert store.get_case_by_session("nope") is None


def test_one_active_case_per_session(store):
    store.create_case("session-abc", title="A", category="warranty", description="D")
    with pytest.raises(ValueError, match="already exists"):
        store.create_case("session-abc", title="B", category="warranty", description="D")


def test_different_sessions_get_separate_cases(store):
    first = store.create_case("s1", title="A", category="warranty", description="D")
    second = store.create_case("s2", title="B", category="refund", description="D")
    assert first["id"] != second["id"]
    assert store.get_case_by_session("s1")["id"] == first["id"]


def test_update_case_fields(store):
    case_id = store.create_case("s1", title="A", category="warranty", description="D")["id"]
    updated = store.update_case(
        case_id,
        {"product": "ASUS Vivobook", "purchase_date": "March 2026", "status": "in_progress"},
    )
    assert updated["product"] == "ASUS Vivobook"
    assert updated["purchase_date"] == "March 2026"
    assert updated["status"] == "in_progress"
    assert updated["updated_at"] >= updated["created_at"]


def test_update_case_amount_coerced_to_float(store):
    case_id = store.create_case("s1", title="A", category="refund", description="D")["id"]
    updated = store.update_case(case_id, {"amount": "35000"})
    assert updated["amount"] == 35000.0


def test_update_case_amount_must_be_numeric(store):
    case_id = store.create_case("s1", title="A", category="warranty", description="D")["id"]
    with pytest.raises(ValueError, match="numeric"):
        store.update_case(case_id, {"amount": "not-a-number"})


def test_update_case_rejects_unknown_field(store):
    case_id = store.create_case("s1", title="A", category="warranty", description="D")["id"]
    with pytest.raises(ValueError, match="invalid case fields"):
        store.update_case(case_id, {"purchase_date": "x", "DROP TABLE cases": "x"})


def test_update_case_rejects_empty_value(store):
    case_id = store.create_case("s1", title="A", category="warranty", description="D")["id"]
    with pytest.raises(ValueError, match="must not be empty"):
        store.update_case(case_id, {"product": "   "})


def test_update_case_unknown_id(store):
    with pytest.raises(ValueError, match="not found"):
        store.update_case("missing", {"product": "x"})


def test_restart_persistence(tmp_path):
    path = tmp_path / "resolve.db"
    store_one = CaseStore(path)
    case_id = store_one.create_case("s1", title="A", category="warranty", description="D")["id"]
    store_one.update_case(case_id, {"product": "ASUS Vivobook"})
    del store_one

    store_two = CaseStore(path)
    case = store_two.get_case(case_id)
    assert case["product"] == "ASUS Vivobook"
    assert case["session_id"] == "s1"


def test_list_cases(store):
    store.create_case("s1", title="A", category="warranty", description="D")
    store.create_case("s2", title="B", category="refund", description="D")
    assert len(store.list_cases()) == 2


# --- Phase 6B: resolution state machine ---

def test_entry_into_awaiting_response_from_free_status(store):
    case_id = store.create_case("s1", title="A", category="warranty", description="D")["id"]
    updated = store.transition_status(case_id, "awaiting_response")
    assert updated["status"] == "awaiting_response"


def test_transition_awaiting_response_to_response_received(store):
    case_id = store.create_case("s1", title="A", category="warranty", description="D")["id"]
    store.transition_status(case_id, "awaiting_response")
    updated = store.transition_status(case_id, "response_received")
    assert updated["status"] == "response_received"
    assert updated["resolved_at"] is None


def test_transition_response_received_to_resolved(store):
    case_id = _response_received_case(store)
    updated = store.transition_status(case_id, "resolved")
    assert updated["status"] == "resolved"
    assert updated["resolved_at"] is not None


def test_transition_response_received_to_needs_follow_up(store):
    case_id = _response_received_case(store)
    updated = store.transition_status(case_id, "needs_follow_up")
    assert updated["status"] == "needs_follow_up"


def test_transition_response_received_to_human_intervention(store):
    case_id = _response_received_case(store)
    updated = store.transition_status(case_id, "human_intervention")
    assert updated["status"] == "human_intervention"


def test_transition_needs_follow_up_back_to_response_received(store):
    case_id = _response_received_case(store)
    store.transition_status(case_id, "needs_follow_up")
    updated = store.transition_status(case_id, "response_received")
    assert updated["status"] == "response_received"


def test_transition_needs_follow_up_to_awaiting_response(store):
    case_id = _response_received_case(store)
    store.transition_status(case_id, "needs_follow_up")
    updated = store.transition_status(case_id, "awaiting_response")
    assert updated["status"] == "awaiting_response"


def test_awaiting_response_cannot_transition_to_awaiting_response_after_resolution(store):
    case_id = _response_received_case(store)
    store.transition_status(case_id, "needs_follow_up")
    store.transition_status(case_id, "awaiting_response")
    with pytest.raises(ValueError, match="cannot transition"):
        store.transition_status(case_id, "needs_follow_up")


def test_transition_keeps_unrelated_case_fields(store):
    case_id = store.create_case(
        "s1", title="A", category="warranty", description="D"
    )["id"]
    store.update_case(
        case_id,
        {"product": "ASUS Vivobook", "seller": "Shop", "next_action": "send email"},
    )
    store.transition_status(case_id, "awaiting_response")
    store.transition_status(case_id, "response_received")
    updated = store.transition_status(case_id, "resolved")
    assert updated["product"] == "ASUS Vivobook"
    assert updated["seller"] == "Shop"
    assert updated["next_action"] == "send email"
    assert updated["title"] == "A"
    assert updated["category"] == "warranty"


def test_resolved_cannot_transition(store):
    case_id = _response_received_case(store)
    store.transition_status(case_id, "resolved")
    with pytest.raises(ValueError, match="cannot transition"):
        store.transition_status(case_id, "response_received")
    with pytest.raises(ValueError, match="cannot transition"):
        store.transition_status(case_id, "needs_follow_up")


def test_human_intervention_cannot_transition_automatically(store):
    case_id = _response_received_case(store)
    store.transition_status(case_id, "human_intervention")
    with pytest.raises(ValueError, match="cannot transition"):
        store.transition_status(case_id, "response_received")
    with pytest.raises(ValueError, match="cannot transition"):
        store.transition_status(case_id, "resolved")


def test_awaiting_response_to_resolved_rejected(store):
    case_id = store.create_case("s1", title="A", category="warranty", description="D")["id"]
    store.transition_status(case_id, "awaiting_response")
    with pytest.raises(ValueError, match="cannot transition"):
        store.transition_status(case_id, "resolved")


def test_free_status_cannot_jump_into_machine(store):
    case_id = store.create_case("s1", title="A", category="warranty", description="D")["id"]
    with pytest.raises(ValueError, match="cannot transition"):
        store.transition_status(case_id, "resolved")
    with pytest.raises(ValueError, match="cannot transition"):
        store.transition_status(case_id, "response_received")


def test_transition_unknown_status(store):
    case_id = store.create_case("s1", title="A", category="warranty", description="D")["id"]
    with pytest.raises(ValueError, match="unknown case status"):
        store.transition_status(case_id, "banana")


def test_transition_unknown_case(store):
    with pytest.raises(ValueError, match="not found"):
        store.transition_status("missing", "awaiting_response")


def test_update_case_rejects_resolution_statuses(store):
    case_id = store.create_case("s1", title="A", category="warranty", description="D")["id"]
    for status in ("awaiting_response", "response_received", "resolved", "needs_follow_up", "human_intervention"):
        with pytest.raises(ValueError, match="resolution status changes"):
            store.update_case(case_id, {"status": status})


def test_update_case_still_allows_free_status(store):
    case_id = store.create_case("s1", title="A", category="warranty", description="D")["id"]
    updated = store.update_case(case_id, {"status": "in_progress"})
    assert updated["status"] == "in_progress"


def _response_received_case(store) -> str:
    case_id = store.create_case("s1", title="A", category="warranty", description="D")["id"]
    store.transition_status(case_id, "awaiting_response")
    store.transition_status(case_id, "response_received")
    return case_id