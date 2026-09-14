"""Execution configuration endpoints (Phase 7A-1).

Exposes only non-secret runtime configuration to the frontend (which channel
is active and whether it performs real external sends).  SMTP hosts, ports,
recipients, and credentials are never returned.
"""

import logging

from fastapi import APIRouter, HTTPException

from backend.channels.factory import build_channel, is_real_channel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("/execution")
def execution_config() -> dict:
    try:
        channel = build_channel()
    except Exception as exc:
        logger.warning("unable to build execution channel for config lookup: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="execution channel configuration is invalid",
        ) from exc
    name = channel.name
    return {
        "channel": name,
        "real_sending_enabled": is_real_channel(name),
    }