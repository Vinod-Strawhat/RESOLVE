import pytest

from backend.services.case_store import CaseStore
from backend.services.followup_preparer import (
    build_followup_context,
    prepare_followup_action,
    validate_prepared_action,
    _extract_json,
)
from backend.services.followup_store import FollowupStore
from backend.services.response_store import ResponseStore


# --- Validator / defensive parser tests ---

def test_validate_valid_action():
    result = validate_prepared_action(
        {
            "type": "escalation",
            "title": "Escalate warranty claim",
            "reason": "Support requested a photo we already provided.",
            "content": "We already provided the photo on Jan 5. Please reassess.",
            "target": "ASUS Support",
        }
    )
    assert result.type == "escalation"
    assert result.title == "Escalate warranty claim"
    assert result.target == "ASUS Support"
    assert result.reason
    assert result.content


def test_validate_invalid_type():
    with pytest.raises(ValueError, match="invalid action type"):
        validate_prepared_action(
            {
                "type": "send_email_hack",
                "title": "T",
                "reason": "R",
                "content": "C",
            }
        )


def test_validate_empty_title():
    with pytest.raises(ValueError):
        validate_prepared_action(
            {
                "type": "escalation",
                "title": "   ",
                "reason": "R",
                "content": "C",
            }
        )


def test_validate_empty_reason():
    with pytest.raises(ValueError):
        validate_prepared_action(
            {
                "type": "escalation",
                "title": "T",
                "reason": "",
                "content": "C",
            }
        )


def test_validate_empty_content():
    with pytest.raises(ValueError):
        validate_prepared_action(
            {
                "type": "escalation",
                "title": "T",
                "reason": "R",
                "content": "  ",
            }
        )


def test_validate_missing_field():
    with pytest.raises(ValueError):
        validate_prepared_action(
            {
                "type": "escalation",
                "title": "T",
                "content": "C",
            }
        )


def test_extract_json_plain():
    data = _extract_json('{"type":"escalation","title":"T","reason":"R","content":"C"}')
    assert data["type"] == "escalation"


def test_extract_json_fenced():
    text = '```json\n{"type":"refund_request","title":"T","reason":"R","content":"C"}\n```'
    assert _extract_json(text)["type"] == "refund_request"


def test_extract_json_no_object():
    with pytest.raises(ValueError, match="no JSON"):
        _extract_json("just words")


def test_extract_json_malformed():
    with pytest.raises(ValueError):
        _extract_json('{"type": "escalation", broken')


# --- Context building ---

def test_build_context_includes_case_and_history():
    case = {
        "id": "c1",
        "title": "Rejected claim",
        "status": "needs_follow_up",
        "category": "warranty",
    }
    responses = [
        {"source": "simulated_support", "content": "send photo", "received_at": "t1"}
    ]
    actions = [
        {"title": "Escalate", "type": "escalation", "status": "executed",
         "execution_result": "Simulated execution done."}
    ]
    history = [
        {"attempt_number": 1, "evaluation_reason": "Needs more evidence",
         "evaluation_confidence": 0.8}
    ]
    ctx = build_followup_context(case, responses, actions, history, 1)
    assert "CASE DETAILS" in ctx
    assert "send photo" in ctx
    assert "Escalate" in ctx
    assert "Needs more evidence" in ctx
    assert "Follow-up attempt number: 1" in ctx


def test_build_context_empty():
    case = {}
    ctx = build_followup_context(case, [], [], [], 0)
    assert "no structured case fields" in ctx
    assert "(no responses)" in ctx
    assert "(no previous actions)" in ctx
    assert "(no previous follow-up evaluations)" in ctx
    assert "CASE DETAILS" in ctx
    assert "Current case status: unknown" in ctx


# --- Preparer end-to-end (mocked agent output) ---

class FakeAgent:
    def __init__(self, raw_output):
        self._raw_output = raw_output

    def __call__(self, prompt):
        class _Result:
            def __init__(self, text):
                self.message = {"content": [{"text": text}]}
        return _Result(self._raw_output)


def _env(tmp_path):
    case_store = CaseStore(tmp_path / "resolve.db")
    response_store = ResponseStore(tmp_path / "resolve.db")
    followup_store = FollowupStore(tmp_path / "resolve.db")
    from backend.services.action_store import ActionStore
    action_store = ActionStore(tmp_path / "resolve.db")
    case_id = case_store.create_case(
        "session-fu",
        title="Claim DELL-2026-4821",
        category="warranty",
        description="Laptop charging port failed.",
    )["id"]
    case_store.transition_status(case_id, "awaiting_response")
    case_store.transition_status(case_id, "response_received")
    response_store.create_response(
        case_id,
        source="simulated_support",
        content="Provide a clear photograph of the charging port.",
    )
    case_store.transition_status(case_id, "needs_follow_up")
    followup_store.record_followup(case_id, reason="Needs photo", confidence=0.8)
    return case_store, response_store, action_store, followup_store, case_id


def test_prepare_followup_success(tmp_path):
    case_store, response_store, action_store, followup_store, case_id = _env(tmp_path)
    agent = FakeAgent(
        '{"type":"warranty_dispute","title":"Provide photo to ASUS",'
        '"reason":"Support requested the charging port photo.","content":'
        '"Attached is the photograph of the charging port. Please reassess.",'
        '"target":"ASUS Support"}'
    )
    result = prepare_followup_action(
        case_store, response_store, action_store, followup_store, case_id, agent=agent
    )
    assert result.type == "warranty_dispute"
    assert result.title == "Provide photo to ASUS"
    assert result.reason
    assert result.content
    assert result.target == "ASUS Support"


def test_prepare_unknown_case(tmp_path):
    case_store, response_store, action_store, followup_store, _ = _env(tmp_path)
    with pytest.raises(ValueError, match="case not found"):
        prepare_followup_action(
            case_store, response_store, action_store, followup_store,
            "missing", agent=FakeAgent("{}"),
        )


def test_prepare_wrong_state(tmp_path):
    case_store, response_store, action_store, followup_store, case_id = _env(tmp_path)
    case_store.transition_status(case_id, "awaiting_response")
    with pytest.raises(ValueError, match="cannot prepare follow-up"):
        prepare_followup_action(
            case_store, response_store, action_store, followup_store,
            case_id, agent=FakeAgent("{}"),
        )


def test_prepare_empty_model_output(tmp_path):
    case_store, response_store, action_store, followup_store, case_id = _env(tmp_path)
    with pytest.raises(ValueError, match="empty response"):
        prepare_followup_action(
            case_store, response_store, action_store, followup_store,
            case_id, agent=FakeAgent("   "),
        )


def test_prepare_malformed_json(tmp_path):
    case_store, response_store, action_store, followup_store, case_id = _env(tmp_path)
    with pytest.raises(ValueError, match="failed to parse"):
        prepare_followup_action(
            case_store, response_store, action_store, followup_store,
            case_id, agent=FakeAgent("not json at all"),
        )


def test_prepare_invalid_action_validated(tmp_path):
    case_store, response_store, action_store, followup_store, case_id = _env(tmp_path)
    agent = FakeAgent(
        '{"type":"bogus_type","title":"T","reason":"R","content":"C"}'
    )
    with pytest.raises(ValueError, match="invalid action type"):
        prepare_followup_action(
            case_store, response_store, action_store, followup_store,
            case_id, agent=agent,
        )


def test_prepare_never_creates_action(tmp_path):
    case_store, response_store, action_store, followup_store, case_id = _env(tmp_path)
    agent = FakeAgent(
        '{"type":"escalation","title":"T","reason":"R","content":"C"}'
    )
    prepare_followup_action(
        case_store, response_store, action_store, followup_store, case_id, agent=agent
    )
    assert action_store.list_actions_for_case(case_id) == []