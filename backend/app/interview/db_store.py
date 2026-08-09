"""
Persistent Interview History Store using Python built-in SQLite & JSON.

Stores completed interview sessions persistently across server restarts
without requiring any external database dependencies or hurting Render deployments.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from typing import Any

logger = logging.getLogger(__name__)

DB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data"))
DB_PATH = os.path.join(DB_DIR, "interview_history.db")


def init_db() -> None:
    """Ensure data directory and SQLite tables exist."""
    try:
        os.makedirs(DB_DIR, exist_ok=True)
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS interview_history (
                    id TEXT PRIMARY KEY,
                    user_name TEXT,
                    candidate_role TEXT,
                    persona TEXT,
                    date TEXT,
                    feedback_json TEXT,
                    transcript_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
    except Exception as exc:
        logger.error("Failed to initialize SQLite DB: %s", exc)


def save_interview_history(record: dict[str, Any]) -> None:
    """Save or update an interview session record in SQLite."""
    init_db()
    session_id = str(record.get("id") or os.urandom(8).hex())
    user_name = str(record.get("userName") or "Candidate")
    role = str(record.get("candidateRole") or "AI Engineer")
    persona = str(record.get("persona") or "Pragmatic Architect")
    date_str = str(record.get("date") or "")
    feedback_json = json.dumps(record.get("feedback") or {})
    transcript_json = json.dumps(record.get("transcript") or [])

    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO interview_history 
                (id, user_name, candidate_role, persona, date, feedback_json, transcript_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (session_id, user_name, role, persona, date_str, feedback_json, transcript_json))
            conn.commit()
            logger.info("Saved interview history record %s to SQLite DB", session_id)
    except Exception as exc:
        logger.error("Failed to save history record %s: %s", session_id, exc)


def get_all_history() -> list[dict[str, Any]]:
    """Retrieve all saved interview sessions from SQLite."""
    init_db()
    results: list[dict[str, Any]] = []
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM interview_history ORDER BY created_at DESC")
            rows = cursor.fetchall()
            for row in rows:
                results.append({
                    "id": row["id"],
                    "userName": row["user_name"],
                    "candidateRole": row["candidate_role"],
                    "persona": row["persona"],
                    "date": row["date"],
                    "feedback": json.loads(row["feedback_json"] or "{}"),
                    "transcript": json.loads(row["transcript_json"] or "[]"),
                    "createdAt": row["created_at"],
                })
    except Exception as exc:
        logger.error("Failed to fetch interview history: %s", exc)

    return results
