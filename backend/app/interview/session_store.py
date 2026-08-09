"""
In-memory session store — plain dict, no database, no auth.

Each session tracks:
    - candidate data
    - focus plan (ordered list of topics)
    - transcript (list of {role, content})
    - questions asked count
    - days covered set
    - verdicts list (one per graded answer)
    - current focus index (pointer into focus plan)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Session:
    candidate: dict[str, Any]
    focus_plan: list[dict[str, Any]]
    persona: str = "Pragmatic Architect"
    user_name: str = "Candidate"
    transcript: list[dict[str, str]] = field(default_factory=list)
    questions_asked: int = 0
    days_covered: set[int] = field(default_factory=set)
    verdicts: list[str] = field(default_factory=list)
    current_focus_index: int = 0


# ─── Store ───────────────────────────────────────────────────────────

_sessions: dict[str, Session] = {}


def create_session(
    session_id: str,
    candidate: dict[str, Any],
    focus_plan: list[dict[str, Any]],
    persona: str = "Pragmatic Architect",
    user_name: str = "Candidate",
) -> Session:
    """Initialize and store a new interview session."""
    session = Session(candidate=candidate, focus_plan=focus_plan, persona=persona, user_name=user_name)
    _sessions[session_id] = session
    return session


def get_session(session_id: str) -> Session | None:
    """Retrieve an existing session, or None if expired/missing."""
    return _sessions.get(session_id)


def delete_session(session_id: str) -> None:
    """Remove a session (optional cleanup)."""
    _sessions.pop(session_id, None)
