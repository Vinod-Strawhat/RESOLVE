import pytest

from backend.services.action_store import ActionStore
from backend.services.case_store import CaseStore


@pytest.fixture
def stores(tmp_path):
    case_store = CaseStore(tmp_path / "resolve.db")
    action_store = ActionStore(tmp_path / "resolve.db")
    case_id = case_store.create_case(
        "session-abc",
        title="Rejected warranty claim",
        category="warranty",
        description="Company refused coverage.",
    )["id"]
    return {"action_store": action_store, "case_store": case_store, "case_id": case_id}


def _draft(store, case_id, **overrides):
    kwargs = {
        "type": "warranty_dispute",
        "title": "Request review of rejected warranty claim",
        "reason": "Evidence may indicate coverage.",
        "content": "Please review the attached case evidence.",
        "target": "ASUS Support",
    }
    kwargs.update(overrides)
    return store.create_action(case_id, **kwargs)


# --- A. Action creation ---

def test_create_action(stores):
    action = _draft(stores["action_store"], stores["case_id"])
    assert action["id"]
    assert action["case_id"] == stores["case_id"]
    assert action["type"] == "warranty_dispute"
    assert action["target"] == "ASUS Support"
    assert action["title"] == "Request review of rejected warranty claim"
    assert action["reason"].startswith("Evidence")
    assert "case evidence" in action["content"]
    assert action["status"] == "draft"
    assert action["created_at"]
    assert action["approved_at"] is None
    assert action["rejected_at"] is None


def test_create_action_rejects_unknown_type(stores):
    with pytest.raises(ValueError, match="invalid action type"):
        _draft(stores["action_store"], stores["case_id"], type="not_a_type")


def test_create_action_rejects_empty_title(stores):
    with pytest.raises(ValueError, match="title must not be empty"):
        _draft(stores["action_store"], stores["case_id"], title="   ")


def test_create_action_rejects_empty_content(stores):
    with pytest.raises(ValueError, match="content must not be empty"):
        _draft(stores["action_store"], stores["case_id"], content="  ")


def test_create_action_rejects_empty_reason(stores):
    with pytest.raises(ValueError, match="reason must not be empty"):
        _draft(stores["action_store"], stores["case_id"], reason="")


def test_create_action_defaults_target_to_empty(stores):
    action = _draft(stores["action_store"], stores["case_id"], target="  ")
    assert action["target"] == ""


# --- B. Action retrieval ---

def test_get_action(stores):
    action = _draft(stores["action_store"], stores["case_id"])
    fetched = stores["action_store"].get_action(action["id"])
    assert fetched["id"] == action["id"]
    assert fetched["title"] == action["title"]


def test_get_unknown_action_returns_none(stores):
    assert stores["action_store"].get_action("missing") is None


# --- C. Action listing by case ---

def test_list_actions_for_case(stores):
    _draft(stores["action_store"], stores["case_id"], title="First")
    _draft(stores["action_store"], stores["case_id"], title="Second")
    actions = stores["action_store"].list_actions_for_case(stores["case_id"])
    assert len(actions) == 2
    assert {a["title"] for a in actions} == {"First", "Second"}


def test_list_actions_unknown_case_empty(stores):
    assert stores["action_store"].list_actions_for_case("no-case") == []


# --- D. Pending approval state ---

def test_submit_for_approval(stores):
    action = _draft(stores["action_store"], stores["case_id"])
    pending = stores["action_store"].submit_for_approval(action["id"])
    assert pending["status"] == "pending_approval"


def test_submit_non_draft_rejected(stores):
    action = _draft(stores["action_store"], stores["case_id"])
    stores["action_store"].submit_for_approval(action["id"])
    with pytest.raises(ValueError, match="must be draft"):
        stores["action_store"].submit_for_approval(action["id"])


def test_submit_unknown_action_raises(stores):
    with pytest.raises(ValueError, match="action not found"):
        stores["action_store"].submit_for_approval("missing")


# --- E. Approval transition ---

def test_approve_pending_action(stores):
    action = _draft(stores["action_store"], stores["case_id"])
    stores["action_store"].submit_for_approval(action["id"])
    approved = stores["action_store"].approve_action(action["id"])
    assert approved["status"] == "approved"
    assert approved["approved_at"] is not None
    assert approved["rejected_at"] is None


def test_approve_draft_rejected(stores):
    action = _draft(stores["action_store"], stores["case_id"])
    with pytest.raises(ValueError, match="must be pending_approval"):
        stores["action_store"].approve_action(action["id"])


def test_approve_unknown_raises(stores):
    with pytest.raises(ValueError, match="action not found"):
        stores["action_store"].approve_action("missing")


# --- F. Rejection transition ---

def test_reject_pending_action(stores):
    action = _draft(stores["action_store"], stores["case_id"])
    stores["action_store"].submit_for_approval(action["id"])
    rejected = stores["action_store"].reject_action(action["id"])
    assert rejected["status"] == "rejected"
    assert rejected["rejected_at"] is not None
    assert rejected["approved_at"] is None


def test_reject_draft_rejected(stores):
    action = _draft(stores["action_store"], stores["case_id"])
    with pytest.raises(ValueError, match="must be pending_approval"):
        stores["action_store"].reject_action(action["id"])


# --- G. Invalid state transitions ---

def test_rejected_cannot_be_approved(stores):
    action = _draft(stores["action_store"], stores["case_id"])
    stores["action_store"].submit_for_approval(action["id"])
    stores["action_store"].reject_action(action["id"])
    with pytest.raises(ValueError, match="must be pending_approval"):
        stores["action_store"].approve_action(action["id"])


def test_approved_cannot_be_rejected(stores):
    action = _draft(stores["action_store"], stores["case_id"])
    stores["action_store"].submit_for_approval(action["id"])
    stores["action_store"].approve_action(action["id"])
    with pytest.raises(ValueError, match="must be pending_approval"):
        stores["action_store"].reject_action(action["id"])


def test_approved_cannot_be_reapproved(stores):
    action = _draft(stores["action_store"], stores["case_id"])
    stores["action_store"].submit_for_approval(action["id"])
    stores["action_store"].approve_action(action["id"])
    with pytest.raises(ValueError, match="must be pending_approval"):
        stores["action_store"].approve_action(action["id"])


def test_rejected_cannot_be_rerejected(stores):
    action = _draft(stores["action_store"], stores["case_id"])
    stores["action_store"].submit_for_approval(action["id"])
    stores["action_store"].reject_action(action["id"])
    with pytest.raises(ValueError, match="must be pending_approval"):
        stores["action_store"].reject_action(action["id"])


# --- Persistence ---

def test_restart_persistence(tmp_path):
    path = tmp_path / "resolve.db"
    case_store = CaseStore(path)
    case_id = case_store.create_case(
        "s1", title="A", category="warranty", description="D"
    )["id"]
    store_one = ActionStore(path)
    store_one.create_action(
        case_id,
        type="warranty_dispute",
        title="T",
        reason="R",
        content="C",
        target="Target",
    )
    del store_one

    store_two = ActionStore(path)
    actions = store_two.list_actions_for_case(case_id)
    assert len(actions) == 1
    assert actions[0]["title"] == "T"
    assert actions[0]["target"] == "Target"
