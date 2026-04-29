"""Session utility routes."""

import json
import os

from fastapi import APIRouter, Depends

from api.logic import get_session
from api.logger import LOG_DIR
from api.routes.deps import get_session_id, verify_api_key

router = APIRouter(prefix="/session", tags=["session"])


@router.get("/{session_id}/log")
async def get_session_log(
    session_id: str,
    api_key: str = Depends(verify_api_key),
):
    return get_session(session_id)


@router.get("/{session_id}/requests")
async def get_session_requests(
    session_id: str,
    api_key: str = Depends(verify_api_key),
):
    """Return all request log entries for a session, ordered by timestamp."""
    log_path = os.path.join(LOG_DIR, "requests.jsonl")
    entries = []
    if os.path.exists(log_path):
        with open(log_path) as f:
            for line in f:
                entry = json.loads(line)
                if entry.get("session_id") == session_id:
                    entries.append(entry)
    return {"session_id": session_id, "requests": entries}
