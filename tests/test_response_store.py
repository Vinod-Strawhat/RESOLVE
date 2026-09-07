import pytest

from backend.services.case_store import CaseStore
from backend.services.response_store import (
    ResponseStore,
    default_response_store_path,
)


@pytest.fixture
def env(tmp_path):
    case_store = CaseStore(tmp_path / "resolve.db")
    response_store = ResponseStore(tmp_path / "resolve.db")
    case_id = case_store.create_case(
        "session-resp",
        title="Rejected warranty claim",
        category="warranty",
        description="ASUS refused coverage.",
    )["id"]
    return {
        "case_id": case_id,
        "response_store": response_store,
    }


def test_create_response(env):
    response = env["response_store"].create_response(
        env["case_id"], source="simulated_support", content="We reviewed your claim."
    )
    assert response["id"]
    assert response["case_id"] == env["case_id"]
    assert response["source"] == "simulated_support"
    assert response["content"] == "We reviewed your claim."
    assert response["received_at"]
    assert response["created_at"]
    assert response["received_at"] == response["created_at"]


def test_create_response_trims_and_rejects_empty(env):
    with pytest.raises(ValueError, match="empty"):
        env["response_store"].create_response(env["case_id"], source="x", content="   ")
    with pytest.raises(ValueError, match="empty"):
        env["response_store"].create_response(env["case_id"], source="   ", content="x")


def test_list_responses_oldest_first(env):
    env["response_store"].create_response(
        env["case_id"], source="simulated_support", content="first"
    )
    env["response_store"].create_response(
        env["case_id"], source="simulated_support", content="second"
    )
    responses = env["response_store"].list_responses_for_case(env["case_id"])
    assert len(responses) == 2
    assert [r["content"] for r in responses] == ["first", "second"]
    assert responses[0]["received_at"] <= responses[1]["received_at"]


def test_list_responses_empty_for_unknown_case(env):
    assert env["response_store"].list_responses_for_case("nope") == []


def test_get_response(env):
    response = env["response_store"].create_response(
        env["case_id"], source="simulated_support", content="hi"
    )
    assert env["response_store"].get_response(response["id"])["content"] == "hi"
    assert env["response_store"].get_response("missing") is None


def test_restart_persistence(tmp_path):
    path = tmp_path / "resolve.db"
    case_store = CaseStore(path)
    case_id = case_store.create_case(
        "s1", title="A", category="warranty", description="D"
    )["id"]
    ResponseStore(path).create_response(
        case_id, source="simulated_support", content="persisted"
    )

    reloaded = ResponseStore(path)
    responses = reloaded.list_responses_for_case(case_id)
    assert len(responses) == 1
    assert responses[0]["content"] == "persisted"


def test_default_path_uses_memory_db(monkeypatch):
    monkeypatch.setenv("MEMORY_DB_PATH", "C:\\tmp\\custom\\resolve.db")
    assert str(default_response_store_path()) == "C:\\tmp\\custom\\resolve.db"