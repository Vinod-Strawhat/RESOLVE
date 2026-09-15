import pytest

from backend.services.case_store import CaseStore
from backend.services.response_evaluator import (
    EVALUATOR_SYSTEM_PROMPT,
    build_evaluation_context,
    evaluate_response,
    validate_evaluation_result,
    _extract_json,
)
from backend.services.response_store import ResponseStore
from backend.services.user_store import UserStore
from conftest import create_test_user


# --- Validator / defensive parser tests ---

def test_validate_valid_resolved():
    result = validate_evaluation_result(
        {
            "outcome": "resolved",
            "confidence": 0.9,
            "reason": "The response confirms the refund was processed.",
            "next_step": "Wait for the refund to arrive within 3 business days.",
        }
    )
    assert result.outcome == "resolved"
    assert result.confidence == 0.9
    assert result.reason
    assert result.next_step


@pytest.mark.parametrize(
    "outcome",
    ["resolved", "needs_follow_up", "human_intervention"],
)
def test_validate_valid_outcomes(outcome):
    result = validate_evaluation_result(
        {
            "outcome": outcome,
            "confidence": 0.5,
            "reason": "A reason.",
            "next_step": "A next step.",
        }
    )
    assert result.outcome == outcome


def test_validate_invalid_outcome():
    with pytest.raises(ValueError, match="invalid outcome"):
        validate_evaluation_result(
            {
                "outcome": "escalate_now",
                "confidence": 0.5,
                "reason": "A reason.",
                "next_step": "A next step.",
            }
        )


def test_validate_confidence_below_zero():
    with pytest.raises(ValueError):
        validate_evaluation_result(
            {
                "outcome": "resolved",
                "confidence": -0.1,
                "reason": "A reason.",
                "next_step": "A next step.",
            }
        )


def test_validate_confidence_above_one():
    with pytest.raises(ValueError):
        validate_evaluation_result(
            {
                "outcome": "resolved",
                "confidence": 1.5,
                "reason": "A reason.",
                "next_step": "A next step.",
            }
        )


def test_validate_confidence_non_numeric():
    with pytest.raises(ValueError):
        validate_evaluation_result(
            {
                "outcome": "resolved",
                "confidence": "high",
                "reason": "A reason.",
                "next_step": "A next step.",
            }
        )


def test_validate_missing_reason():
    with pytest.raises(ValueError):
        validate_evaluation_result(
            {
                "outcome": "resolved",
                "confidence": 0.5,
                "reason": "   ",
                "next_step": "A next step.",
            }
        )


def test_validate_missing_next_step():
    with pytest.raises(ValueError):
        validate_evaluation_result(
            {
                "outcome": "resolved",
                "confidence": 0.5,
                "reason": "A reason.",
                "next_step": "",
            }
        )


def test_validate_missing_field():
    with pytest.raises(ValueError):
        validate_evaluation_result(
            {
                "outcome": "resolved",
                "confidence": 0.5,
            }
        )


def test_validate_rounds_confidence():
    result = validate_evaluation_result(
        {
            "outcome": "needs_follow_up",
            "confidence": 0.876543,
            "reason": "A reason.",
            "next_step": "A next step.",
        }
    )
    assert result.confidence == 0.877


# --- Defensive JSON extraction ---

def test_extract_json_plain():
    data = _extract_json('{"outcome":"resolved","confidence":0.5}')
    assert data["outcome"] == "resolved"


def test_extract_json_fenced():
    text = 'Here is the result:\n```json\n{"outcome":"resolved","confidence":0.5}\n```\n'
    assert _extract_json(text)["outcome"] == "resolved"


def test_extract_json_wrapped_in_text():
    text = 'Consider this:\n{"outcome":"human_intervention","confidence":0.3} and that was it.'
    assert _extract_json(text)["outcome"] == "human_intervention"


def test_extract_json_no_object():
    with pytest.raises(ValueError, match="no JSON"):
        _extract_json("I think the case is resolved, no JSON here.")


def test_extract_json_malformed():
    with pytest.raises(ValueError):
        _extract_json('{"outcome": "resolved", broken')


# --- Context building ---

def test_build_context_no_responses():
    case = {
        "id": "abc",
        "category": "warranty",
        "title": "Rejected claim",
        "description": "ASUS refused.",
        "status": "response_received",
    }
    context = build_evaluation_context(case, [])
    assert "CASE DETAILS" in context
    assert "RESPONSE HISTORY" in context
    assert "LATEST RESPONSE" in context
    assert "(none)" in context
    assert "first" in context


def test_build_context_with_responses():
    case = {"id": "abc", "title": "Case", "status": "response_received"}
    responses = [
        {"id": "r1", "source": "simulated_support", "content": "first", "received_at": "t1"},
        {"id": "r2", "source": "simulated_support", "content": "second", "received_at": "t2"},
    ]
    context = build_evaluation_context(case, responses)
    assert "first" in context
    assert "second" in context
    assert "follow-up" in context


# --- Stale workflow fields must not become evaluation evidence ---

def test_build_context_omits_stale_workflow_fields():
    """status/next_action are internal bookkeeping and must not reach the model
    as case facts, even when they still hold stale pre-resolution values."""
    case = {
        "id": "abc",
        "category": "warranty",
        "title": "ASUS Vivobook 15 dispute",
        "description": "Defective laptop; warranty claim rejected.",
        "status": "response_received",
        "next_action": "awaiting further details from user",
    }
    responses = [
        {
            "id": "r1",
            "source": "simulated_support",
            "content": (
                "The replacement laptop has been delivered and the case is "
                "closed. No further action is required."
            ),
            "received_at": "t1",
        }
    ]
    context = build_evaluation_context(case, responses)
    assert "- status: response_received" not in context
    assert "- next_action:" not in context
    assert "awaiting further details from user" not in context
    assert "delivered and the case is" in context


def test_build_context_labels_workflow_status_as_bookkeeping():
    case = {"id": "abc", "status": "response_received", "next_action": "x"}
    context = build_evaluation_context(case, [])
    assert "Workflow status" in context
    assert "NOT evidence" in context


@pytest.mark.parametrize(
    "stale_next_action",
    [
        "awaiting further details from user",
        "please confirm delivery of the replacement",
        "provide photos of the charging port",
    ],
)
def test_build_context_never_echoes_stale_next_action(stale_next_action):
    case = {"id": "abc", "next_action": stale_next_action}
    responses = [
        {
            "id": "r1",
            "source": "simulated_support",
            "content": "The replacement was delivered.",
            "received_at": "t1",
        }
    ]
    context = build_evaluation_context(case, responses)
    assert stale_next_action not in context
    assert "The replacement was delivered." in context
    assert "- next_action:" not in context


# --- Prompt rules: resolution recognition ---

def test_system_prompt_latest_response_is_primary_evidence():
    assert "LATEST response is the primary evidence" in EVALUATOR_SYSTEM_PROMPT


def test_system_prompt_workflow_fields_not_facts():
    assert "Structured case fields are internal bookkeeping" in EVALUATOR_SYSTEM_PROMPT
    assert "must never override the latest response" in EVALUATOR_SYSTEM_PROMPT


def test_system_prompt_resolved_requires_completion():
    assert "genuinely completed or closed" in EVALUATOR_SYSTEM_PROMPT
    for phrase in ("a replacement was", "a refund was issued",
                   "a repair was completed",
                   "no further action is required"):
        assert phrase in EVALUATOR_SYSTEM_PROMPT


def test_system_prompt_approval_without_completion_not_resolved():
    assert "Do NOT use 'resolved' for: an approval" in EVALUATOR_SYSTEM_PROMPT
    for phrase in ("we will ship", "please confirm delivery", "will issue"):
        assert phrase in EVALUATOR_SYSTEM_PROMPT


def test_evaluate_prompt_contains_context_and_schema(tmp_path):
    """The prompt handed to the model must contain the context plus output schema."""
    case_store, response_store, case_id = _env(tmp_path)

    captured = {}

    class CapturingAgent:
        def __init__(self, raw_output):
            self._raw_output = raw_output

        def __call__(self, prompt):
            class _Result:
                def __init__(self, text):
                    self.message = {"content": [{"text": text}]}

            captured["prompt"] = prompt
            return _Result(self._raw_output)

    result = evaluate_response(
        case_store,
        response_store,
        case_id,
        agent=CapturingAgent(
            '{"outcome":"needs_follow_up","confidence":0.5,"reason":"r","next_step":"s"}'
        ),
    )
    assert result.outcome == "needs_follow_up"
    assert "=== CASE DETAILS ===" in captured["prompt"]
    assert "=== LATEST RESPONSE (" in captured["prompt"]
    assert "outcome" in captured["prompt"]
    assert "confidence" in captured["prompt"]


# --- Evaluator end-to-end (mocked model output) ---

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
    user_id = create_test_user(UserStore(tmp_path / "resolve.db"))["id"]
    response_store = ResponseStore(tmp_path / "resolve.db")
    case_id = case_store.create_case(
        "session-eval",
        user_id=user_id,
        title="Claim DELL-2026-4821",
        category="warranty",
        description="Laptop charging port failed; warranty claim rejected.",
    )["id"]
    case_store.transition_status(case_id, "awaiting_response")
    case_store.transition_status(case_id, "response_received")
    response_store.create_response(
        case_id,
        source="simulated_support",
        content="We need a photo of the charging port before we can reassess.",
    )
    return case_store, response_store, case_id


def test_evaluate_response_success(tmp_path):
    case_store, response_store, case_id = _env(tmp_path)
    agent = FakeAgent(
        '{"outcome":"needs_follow_up","confidence":0.87,"reason":"Support needs more evidence.","next_step":"Provide the photo of the charging port."}'
    )
    result = evaluate_response(case_store, response_store, case_id, agent=agent)
    assert result.outcome == "needs_follow_up"
    assert result.confidence == 0.87
    assert result.reason
    assert result.next_step


def test_evaluate_response_unknown_case(tmp_path):
    case_store, response_store, _ = _env(tmp_path)
    with pytest.raises(ValueError, match="case not found"):
        evaluate_response(case_store, response_store, "missing", agent=FakeAgent("{}"))


def test_evaluate_response_wrong_state(tmp_path):
    case_store, response_store, case_id = _env(tmp_path)
    case_store.transition_status(case_id, "resolved")
    with pytest.raises(ValueError, match="cannot be evaluated"):
        evaluate_response(case_store, response_store, case_id, agent=FakeAgent("{}"))


def test_evaluate_response_no_responses(tmp_path):
    case_store = CaseStore(tmp_path / "resolve.db")
    user_id = create_test_user(UserStore(tmp_path / "resolve.db"))["id"]
    response_store = ResponseStore(tmp_path / "resolve.db")
    case_id = case_store.create_case(
        "s1", user_id=user_id, title="A", category="warranty", description="D"
    )["id"]
    case_store.transition_status(case_id, "awaiting_response")
    case_store.transition_status(case_id, "response_received")
    with pytest.raises(ValueError, match="no responses"):
        evaluate_response(case_store, response_store, case_id, agent=FakeAgent("{}"))


def test_evaluate_response_empty_model_output(tmp_path):
    case_store, response_store, case_id = _env(tmp_path)
    with pytest.raises(ValueError, match="empty response"):
        evaluate_response(case_store, response_store, case_id, agent=FakeAgent("   "))


def test_evaluate_response_malformed_json(tmp_path):
    case_store, response_store, case_id = _env(tmp_path)
    with pytest.raises(ValueError, match="failed to parse"):
        evaluate_response(case_store, response_store, case_id, agent=FakeAgent("not json"))


def test_evaluate_response_validates_model_output(tmp_path):
    case_store, response_store, case_id = _env(tmp_path)
    agent = FakeAgent(
        '{"outcome":"resolved","confidence":1.2,"reason":"x","next_step":"y"}'
    )
    with pytest.raises(ValueError, match="invalid evaluation output"):
        evaluate_response(case_store, response_store, case_id, agent=agent)