"""Quality scoring logic and SQLite-backed session store for PizzaStack API."""

from __future__ import annotations

import json
import os
import random
import secrets
import sqlite3
from datetime import datetime, timezone

DATA_DIR = os.environ.get("PIZZASTACK_DATA_DIR", "data")
DB_PATH = os.path.join(DATA_DIR, "sessions.db")

_conn: sqlite3.Connection | None = None


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        os.makedirs(DATA_DIR, exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None)
        _conn.execute("""
            CREATE TABLE IF NOT EXISTS session_objects (
                session_id  TEXT NOT NULL,
                object_id   TEXT NOT NULL,
                object_type TEXT NOT NULL,
                data        TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                PRIMARY KEY (session_id, object_id)
            )
        """)
    return _conn


def generate_id(prefix: str) -> str:
    """Generate a prefixed random hex ID, e.g. 'tom_a1b2c3d4'."""
    return f"{prefix}{secrets.token_hex(4)}"


def generate_pieces(count: int, size: str, total_weight: float) -> list[dict]:
    """Generate piece objects for a slicing operation."""
    pieces = []
    remaining = total_weight
    for i in range(count):
        weight = round(remaining / (count - i), 3)
        remaining -= weight
        pieces.append({
            "id": generate_id("pce_"),
            "size": size,
            "weight": weight,
        })
    return pieces


# --- Session management (SQLite-backed) ---


def store_object(session_id: str, obj_id: str, obj_data: dict):
    conn = _get_conn()
    obj_type = obj_data.get("type", "unknown")
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT OR REPLACE INTO session_objects
           (session_id, object_id, object_type, data, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (session_id, obj_id, obj_type, json.dumps(obj_data), now),
    )


def get_object(session_id: str, obj_id: str) -> dict | None:
    conn = _get_conn()
    row = conn.execute(
        "SELECT data FROM session_objects WHERE session_id = ? AND object_id = ?",
        (session_id, obj_id),
    ).fetchone()
    if row is None:
        return None
    return json.loads(row[0])


def get_session(session_id: str) -> dict[str, dict]:
    """Return all objects for a session as {object_id: object_data}."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT object_id, data FROM session_objects WHERE session_id = ?",
        (session_id,),
    ).fetchall()
    return {obj_id: json.loads(data) for obj_id, data in rows}


def get_session_objects(session_id: str) -> list[dict]:
    """Return all objects for a session as a list."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT data FROM session_objects WHERE session_id = ?",
        (session_id,),
    ).fetchall()
    return [json.loads(row[0]) for row in rows]


# --- Quality logic ---


def resolve_ingredient_quality(ingredient_id: str, session_id: str) -> str:
    """Check if an ingredient is raw (unprocessed). Raw tomatoes degrade sauce."""
    obj = get_object(session_id, ingredient_id)
    if obj and obj.get("type") == "raw":
        return "degraded"
    return "optimal"


def propagate_quality(upstream_quality: str, step_quality: str) -> str:
    """Degradation is sticky: any degraded input propagates forward."""
    if upstream_quality == "degraded" or step_quality == "degraded":
        return "degraded"
    return "optimal"


def compute_final_score(quality: str) -> float:
    if quality == "degraded":
        return round(random.uniform(0.35, 0.50), 2)
    return round(random.uniform(0.90, 0.98), 2)


def compute_sub_scores(quality: str) -> dict:
    if quality == "degraded":
        return {
            "crust_crispness": round(random.uniform(0.3, 0.5), 2),
            "cheese_melt": round(random.uniform(0.3, 0.5), 2),
            "topping_distribution": round(random.uniform(0.3, 0.5), 2),
            "sauce_integration": round(random.uniform(0.2, 0.4), 2),
        }
    return {
        "crust_crispness": round(random.uniform(0.85, 0.98), 2),
        "cheese_melt": round(random.uniform(0.85, 0.98), 2),
        "topping_distribution": round(random.uniform(0.85, 0.98), 2),
        "sauce_integration": round(random.uniform(0.85, 0.98), 2),
    }
