"""Combined resolution history assembly for a case (Phase 7C).

Builds a single chronological event list from the persisted lifecycle
records (responses, evaluations, actions, follow-up attempts) plus grounded
case markers (creation, resolution). Every event is derived from persisted
rows; nothing is fabricated.

The same stores used by the case endpoints provide the records, so there is
no duplicated data-access logic. Ordering is by ``occurred_at`` (UTC ISO-8601,
lexicographically comparable) with a deterministic secondary key (event-type
rank, then position within each store's own chronologically ordered list) so
equal timestamps still produce stable output across runs.
"""

_SOURCE_RANK = {
    "case_created": 0,
    "case_resolved": 1,
    "response": 2,
    "evaluation": 3,
    "action": 4,
    "followup": 5,
}

ACTIVITY_TYPES = ("response", "evaluation", "action", "followup")


def _event(
    event_type: str,
    occurred_at: str,
    title: str,
    event_id: str,
    *,
    source=None,
    status=None,
    detail=None,
) -> dict:
    return {
        "event_type": event_type,
        "occurred_at": occurred_at,
        "title": title,
        "id": event_id,
        "source": source,
        "status": status,
        "detail": detail or {},
    }


def build_case_history(
    case: dict,
    *,
    response_store,
    evaluation_store,
    action_store,
    followup_store,
) -> list[dict]:
    """Return the chronological history events for a case."""
    case_id = case["id"]
    ranked = []

    ranked.append(
        (
            case["created_at"],
            _SOURCE_RANK["case_created"],
            0,
            _event("case_created", case["created_at"], "Case created", case_id),
        )
    )
    if case.get("status") == "resolved" and case.get("resolved_at"):
        ranked.append(
            (
                case["resolved_at"],
                _SOURCE_RANK["case_resolved"],
                0,
                _event(
                    "case_resolved",
                    case["resolved_at"],
                    "Case resolved",
                    case_id,
                    status="resolved",
                ),
            )
        )

    for seq, record in enumerate(response_store.list_responses_for_case(case_id)):
        ranked.append(
            (
                record["received_at"],
                _SOURCE_RANK["response"],
                seq,
                _event(
                    "response",
                    record["received_at"],
                    "Company response recorded",
                    record["id"],
                    source=record["source"],
                    detail={
                        "content": record["content"],
                        "received_at": record["received_at"],
                    },
                ),
            )
        )

    for seq, record in enumerate(evaluation_store.list_evaluations_for_case(case_id)):
        ranked.append(
            (
                record["created_at"],
                _SOURCE_RANK["evaluation"],
                seq,
                _event(
                    "evaluation",
                    record["created_at"],
                    "Response evaluated",
                    record["id"],
                    source=record["source"],
                    status=record["outcome"],
                    detail={
                        "outcome": record["outcome"],
                        "confidence": record["confidence"],
                        "reason": record["reason"],
                        "next_step": record["next_step"],
                    },
                ),
            )
        )

    for seq, record in enumerate(action_store.list_actions_for_case(case_id)):
        ranked.append(
            (
                record["created_at"],
                _SOURCE_RANK["action"],
                seq,
                _event(
                    "action",
                    record["created_at"],
                    f"Action prepared: {record['title']}",
                    record["id"],
                    status=record["status"],
                    detail={
                        "type": record["type"],
                        "title": record["title"],
                        "target": record["target"],
                        "reason": record["reason"],
                        "content": record["content"],
                        "status": record["status"],
                        "execution_channel": record["execution_channel"],
                        "execution_reference": record["execution_reference"],
                        "execution_result": record["execution_result"],
                        "execution_error": record["execution_error"],
                        "executed_at": record["executed_at"],
                    },
                ),
            )
        )

    for seq, record in enumerate(followup_store.get_followup_history(case_id)):
        ranked.append(
            (
                record["created_at"],
                _SOURCE_RANK["followup"],
                seq,
                _event(
                    "followup",
                    record["created_at"],
                    f"Follow-up attempt {record['attempt_number']} recorded",
                    record["id"],
                    detail={
                        "attempt_number": record["attempt_number"],
                        "reason": record["evaluation_reason"],
                        "confidence": record["evaluation_confidence"],
                    },
                ),
            )
        )

    ranked.sort(key=lambda item: (item[0], item[1], item[2]))
    return [item[3] for item in ranked]