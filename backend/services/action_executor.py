"""Phase 6A/7A-1 execution service: approved -> executing -> executed | failed.

Execution is triggered exclusively through the execution API. The Strands
agent cannot execute an action; the human approval gate stays mandatory.

The channel object is the single integration point. The default is the safe
SIMULATED channel (nothing is sent to any real company). A local SMTP relay
channel can be selected with ``EXECUTION_CHANNEL=smtp``; a real support channel
(email, Gmail, support API) can later replace it without redesigning the action
lifecycle.

``SimulatedExecutionChannel`` is re-exported from this module for backward
compatibility (it now lives in :mod:`backend.channels.simulated`).
"""

import logging
import threading
from dataclasses import dataclass

from backend.channels.base import ChannelResult
from backend.channels.factory import build_channel
from backend.channels.simulated import SimulatedExecutionChannel as _Simulated
from backend.services.action_store import get_action_store
from backend.services.case_store import get_case_store

# Backward-compatible alias: previously defined in this module.
SimulatedExecutionChannel = _Simulated

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExecutionOutcome:
    status: str
    reference: str = ""
    result: str = ""
    error: str = ""
    executed_at: str | None = None
    channel: str = ""


class ActionExecutor:
    """Orchestrates action execution and keeps action + case state consistent.

    Only ``approved`` actions may be executed. Executing an already executed
    action is idempotent: the existing execution state/result is returned and
    the action is never executed twice. Failures are persisted on the action.

    A channel is only ever invoked AFTER ``begin_execution`` succeeds, so the
    approval gate cannot be bypassed by any channel implementation.
    """

    def __init__(self, action_store, case_store, channel=None):
        self._store = action_store
        self._cases = case_store
        self._channel = channel if channel is not None else build_channel()

    @property
    def channel_name(self) -> str:
        return getattr(self._channel, "name", "simulated")

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

        channel_name = self.channel_name
        self._store.begin_execution(action_id, channel_name=channel_name)

        try:
            submission = self._channel.submit(action)
        except Exception as exc:
            # Delivery never happened; recording the action as failed is safe
            # because a retry cannot double-send.
            error = str(exc) or exc.__class__.__name__
            try:
                self._store.fail_execution(action_id, error=error)
            except ValueError:
                pass
            return ExecutionOutcome(status="failed", error=error, channel=channel_name)

        if isinstance(submission, ChannelResult):
            reference, result = submission.reference, submission.result
        else:
            reference, result = submission

        try:
            completed = self._store.complete_execution(
                action_id, reference=reference, result=result
            )
        except Exception as exc:
            # The action was already delivered by the channel. Marking it
            # failed would invite a duplicate send on retry, so the persistence
            # problem is surfaced distinctly instead of as a delivery failure.
            error = str(exc) or exc.__class__.__name__
            logger.exception(
                "action %s was delivered (%s) but its execution record could "
                "not be persisted: %s",
                action_id,
                channel_name,
                error,
            )
            return ExecutionOutcome(
                status="delivered",
                reference=reference,
                result=result,
                error=f"execution record not persisted: {error}",
                channel=channel_name,
            )

        try:
            self._cases.transition_status(action["case_id"], "awaiting_response")
        except Exception as exc:
            # The action executed and is recorded; only the case update failed.
            # The action must not be reported as failed (it was delivered).
            error = str(exc) or exc.__class__.__name__
            logger.exception(
                "action %s executed but its case transition to awaiting_response "
                "failed: %s",
                action_id,
                error,
            )
            return ExecutionOutcome(
                status="executed",
                reference=reference,
                result=result,
                executed_at=completed["executed_at"],
                channel=channel_name,
                error=f"case status not updated: {error}",
            )

        return ExecutionOutcome(
            status="executed",
            reference=reference,
            result=result,
            executed_at=completed["executed_at"],
            channel=channel_name,
        )

    def _existing_outcome(self, action: dict) -> ExecutionOutcome:
        return ExecutionOutcome(
            status="executed",
            reference=action.get("execution_reference") or "",
            result=action.get("execution_result") or "",
            executed_at=action.get("executed_at"),
            channel=action.get("execution_channel") or "",
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