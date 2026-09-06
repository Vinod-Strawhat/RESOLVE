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