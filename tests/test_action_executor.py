import pytest

from backend.services.action_executor import (
    ActionExecutor,
    ExecutionOutcome,
    SimulatedExecutionChannel,
)
from backend.services.action_store import ActionStore
from backend.services.case_store import CaseStore


class BoomChannel:
    def submit(self, action):
        raise RuntimeError("simulated channel outage")


class CountingChannel:
    def __init__(self):
        self.calls = 0

    def submit(self, action):
        self.calls += 1
        return f"RESOLVE-ACTION-{action['id'][:8].upper()}", "counting-channel done"


@pytest.fixture
def env(tmp_path):
    case_store = CaseStore(tmp_path / "resolve.db")
    action_store = ActionStore(tmp_path / "resolve.db")
    case_id = case_store.create_case(
        "session-exec",
        title="Rejected warranty claim",
        category="warranty",
        description="ASUS refused coverage.",
    )["id"]
    return {
        "case_id": case_id,
        "action_store": action_store,
        "case_store": case_store,
    }


def _approved(store, case_id):
    action = store.create_action(
        case_id,
        type="warranty_dispute",
        target="ASUS Support",
        title="Request review",
        reason="Evidence may indicate coverage.",
        content="Please review the rejected claim.",
    )
    store.submit_for_approval(action["id"])
    return store.approve_action(action["id"])


def _executor(env, channel=None):
    return ActionExecutor(env["action_store"], env["case_store"], channel=channel)


def test_approved_action_executes(env):
    action = _approved(env["action_store"], env["case_id"])
    outcome = _executor(env).execute(action["id"])
    assert outcome.status == "executed"
    assert outcome.reference.startswith("RESOLVE-ACTION-")
    assert len(outcome.reference) == len("RESOLVE-ACTION-") + 8
    assert "simulated" in outcome.result
    assert outcome.executed_at is not None

    saved = env["action_store"].get_action(action["id"])
    assert saved["status"] == "executed"
    assert saved["execution_status"] == "executed"
    assert saved["execution_reference"] == outcome.reference
    assert saved["execution_result"] == outcome.result


def test_successful_execution_updates_case_to_awaiting_response(env):
    action = _approved(env["action_store"], env["case_id"])
    _executor(env).execute(action["id"])
    case = env["case_store"].get_case(env["case_id"])
    assert case["status"] == "awaiting_response"


def test_pending_approval_cannot_execute(env):
    action = env["action_store"].create_action(
        env["case_id"],
        type="warranty_dispute",
        title="Request review",
        reason="Reason",
        content="Content",
    )
    env["action_store"].submit_for_approval(action["id"])
    with pytest.raises(ValueError, match="only approved actions may be executed"):
        _executor(env).execute(action["id"])


def test_rejected_action_cannot_execute(env):
    action = env["action_store"].create_action(
        env["case_id"],
        type="warranty_dispute",
        title="Request review",
        reason="Reason",
        content="Content",
    )
    env["action_store"].submit_for_approval(action["id"])
    env["action_store"].reject_action(action["id"])
    with pytest.raises(ValueError, match="only approved actions may be executed"):
        _executor(env).execute(action["id"])


def test_failed_action_cannot_execute(env):
    action = _approved(env["action_store"], env["case_id"])
    executor = _executor(env, channel=BoomChannel())
    assert executor.execute(action["id"]).status == "failed"
    with pytest.raises(ValueError, match="only approved actions may be executed"):
        executor.execute(action["id"])


def test_draft_action_cannot_execute(env):
    action = env["action_store"].create_action(
        env["case_id"],
        type="warranty_dispute",
        title="Request review",
        reason="Reason",
        content="Content",
    )
    with pytest.raises(ValueError, match="only approved actions may be executed"):
        _executor(env).execute(action["id"])


def test_unknown_action_raises(env):
    with pytest.raises(ValueError, match="action not found"):
        _executor(env).execute("missing")


def test_already_executed_action_is_idempotent(env):
    action = _approved(env["action_store"], env["case_id"])
    channel = CountingChannel()
    executor = _executor(env, channel=channel)

    first = executor.execute(action["id"])
    second = executor.execute(action["id"])

    assert channel.calls == 1
    assert second.status == "executed"
    assert second.reference == first.reference
    assert second.result == first.result
    assert second.executed_at == first.executed_at

    saved = env["action_store"].get_action(action["id"])
    assert saved["status"] == "executed"
    assert saved["execution_reference"] == first.reference


def test_execution_failure_is_persisted(env):
    action = _approved(env["action_store"], env["case_id"])
    outcome = _executor(env, channel=BoomChannel()).execute(action["id"])
    assert outcome.status == "failed"
    assert outcome.error == "simulated channel outage"

    saved = env["action_store"].get_action(action["id"])
    assert saved["status"] == "failed"
    assert saved["execution_status"] == "failed"
    assert saved["execution_error"] == "simulated channel outage"
    assert saved["executed_at"] is None
    assert saved["execution_reference"] is None


def test_outcome_dataclass_shape():
    outcome = ExecutionOutcome(status="executed", reference="r", result="s")
    assert outcome.status == "executed"
    assert outcome.reference == "r"
    assert outcome.result == "s"
    assert outcome.error == ""
    assert outcome.executed_at is None


def test_simulated_channel_result_is_clearly_labeled(env):
    action = _approved(env["action_store"], env["case_id"])
    reference, result = SimulatedExecutionChannel().submit(action)
    assert reference == f"RESOLVE-ACTION-{action['id'][:8].upper()}"
    assert "simulated" in result
    assert "nothing was actually sent" in result