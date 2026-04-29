"""Request logging module for PizzaStack API. Writes crash-safe JSONL."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

LOG_DIR = os.path.join(os.environ.get("PIZZASTACK_DATA_DIR", "data"), "logs")


def _ensure_log_dir():
    os.makedirs(LOG_DIR, exist_ok=True)


def _write_line(filename: str, entry: dict):
    """Open, write one line, flush, close. Crash loses at most one in-flight request."""
    _ensure_log_dir()
    with open(os.path.join(LOG_DIR, filename), "a") as f:
        f.write(json.dumps(entry) + "\n")
        f.flush()
        os.fsync(f.fileno())


def log_api_request(
    session_id: str,
    endpoint: str,
    method: str,
    request_body: dict,
    response_body: dict,
    response_status: int,
    latency_ms: int,
):
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "endpoint": endpoint,
        "method": method,
        "request_body": request_body,
        "response_body": response_body,
        "response_status": response_status,
        "latency_ms": latency_ms,
    }
    _write_line("requests.jsonl", entry)


def log_docs_fetch(
    session_id: str,
    url: str,
    format: str,
    status: int,
    bytes_count: int,
):
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "url": url,
        "format": format,
        "status": status,
        "bytes": bytes_count,
    }
    _write_line("fetches.jsonl", entry)
