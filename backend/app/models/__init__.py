"""
Pydantic request/response schemas for POST /api/interview.

Response uses exclude_none=True so START responses omit verdict,
TURN responses omit feedback, and END responses include feedback.
"""

from __future__ import annotations

from typing import Optional, List

from pydantic import BaseModel, ConfigDict


# ─── Request ─────────────────────────────────────────────────────────

class InterviewRequest(BaseModel):
    """Incoming payload for POST /api/interview.

    Discriminated by payload shape:
      - has "candidate" key  → START
      - has "message" only   → TURN
    """

    sessionId: str
    candidate: Optional[dict] = None
    message: Optional[str] = None
    persona: Optional[str] = None


# ─── Response components ─────────────────────────────────────────────

class Feedback(BaseModel):
    """End-of-interview feedback object."""

    summary: str
    strengths: List[str]
    gaps: List[str]
    next: List[str]


class InterviewResponse(BaseModel):
    """Outgoing payload for POST /api/interview.

    Fields that are None are excluded from the serialized JSON via
    response_model_exclude_none=True on the route.
    """

    model_config = ConfigDict(populate_by_name=True)

    reply: str
    done: bool
    focusReason: Optional[str] = None
    moduleN: Optional[int] = None
    verdict: Optional[str] = None
    feedback: Optional[Feedback] = None
