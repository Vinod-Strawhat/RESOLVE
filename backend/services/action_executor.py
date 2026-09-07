"""Phase 6A execution service: approved -> executing -> executed | failed.

Execution is triggered exclusively through the execution API. The Strands
agent cannot execute an action; the human approval gate stays mandatory.

The current channel is a SAFE SIMULATED execution. Nothing is sent to any
real company. The channel object is the single integration point, so a real
support channel (email, Gmail, support API) can replace the simulator later
without redesigning the action lifecycle.
"""

import threading
from dataclasses import dataclass

from backend.services.action_store import get_action_store
from backend.services.case_store import get_case_store


class SimulatedExecutionChannel:
    """Safe, clearly-labeled simulated execution channel.

    Produces a stable execution reference and a human-readable result without
    making any external request. A real channel should implement the same
    ``submit`` contract: given an approved action, return ``(reference, result)``
    or raise an exception (the failure is then persisted).
    """

    def submit(self, action: dict) -> tuple[str, str]:
        reference = f"RESOLVE-ACTION-{action['id'][:8].upper()}"
        result = (
            "Action submitted through the configured simulated support channel. "
            f"Reference {reference}. This is a simulated execution; nothing was "
            "actually sent to any external party."
        )
        return reference, result


@dataclass(frozen=True)
class ExecutionOutcome:
    status: str
    reference: str = ""
    result: str = ""
    error: str = ""
    executed_at: str | None = None


class ActionExecutor:
    """Orchestrates action execution and keeps action + case state consistent.

    Only ``approved`` actions may be executed. Executing an already executed
    action is idempotent: the existing execution state/result is returned and
    the action is never executed twice. Failures are persisted on the action.
    """

    def __init__(self, action_store, case_store, channel=None):
        self._store = action_store
        self._cases = case_store
        self._channel = channel or SimulatedExecutionChannel()

    def execute(self, action_id: str) -> ExecutionOutcome:
        action = self._store.get_action(action_id)
        if action is None:
            raise ValueError(f"action not found: {action_id}")

        if action["status"] == "executed":
            return self._existing_outcome(action)

        if action["status"] == "executing":
            raise ValueError("action is currently being executed")

        if action["status"] != "approved":
            raise ValueError(
                f"cannot execute action in status {action['status']!r}; "
                "only approved actions may be executed"
            )

        self._store.begin_execution(action_id)
        try:
            reference, result = self._channel.submit(action)
            completed = self._store.complete_execution(
                action_id, reference=reference, result=result
            )
            self._cases.transition_status(action["case_id"], "awaiting_response")
        except Exception as exc:
            error = str(exc) or exc.__class__.__name__
            try:
                self._store.fail_execution(action_id, error=error)
            except ValueError:
                pass
            return ExecutionOutcome(status="failed", error=error)

        return ExecutionOutcome(
            status="executed",
            reference=reference,
            result=result,
            executed_at=completed["executed_at"],
        )

    def _existing_outcome(self, action: dict) -> ExecutionOutcome:
        return ExecutionOutcome(
            status="executed",
            reference=action.get("execution_reference") or "",
            result=action.get("execution_result") or "",
            executed_at=action.get("executed_at"),
        )


_executor: ActionExecutor | None = None
_executor_lock = threading.Lock()


def get_executor() -> ActionExecutor:
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ActionExecutor(get_action_store(), get_case_store())
        return _executor


def set_executor(executor: ActionExecutor | None) -> None:
    global _executor
    with _executor_lock:
        _executor = executor