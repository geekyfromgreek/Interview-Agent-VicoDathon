"""
ABTalks AI Interview Agent — FastAPI Backend

Single endpoint:  POST /api/interview
No auth, state keyed by sessionId, in-memory dict.

Request type determined by payload shape:
    - has "candidate" key  → START flow
    - has "message" key    → TURN flow
"""

from __future__ import annotations

import os
import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.models import InterviewRequest, InterviewResponse, Feedback
from app.interview.focus_plan import build_focus_plan, CANDIDATES, CURRICULUM
from app.interview.session_store import create_session, get_session
from app.interview import llm
from app.interview import db_store

# ─── Logging ─────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)

# ─── App ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="interviewIQ",
    description="Post-cohort technical interview practice and confidence builder.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://.*",
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Constants ───────────────────────────────────────────────────────

MIN_QUESTIONS = 8
MIN_DAYS = 4
HARD_CAP_QUESTIONS = 12


# ─── Endpoint ────────────────────────────────────────────────────────

@app.post(
    "/api/interview",
    response_model=InterviewResponse,
    response_model_exclude_none=True,
)
async def interview(req: InterviewRequest) -> InterviewResponse:
    """Single interview endpoint handling START, TURN, and END flows."""

    # ── Validate: must have either candidate (START) or message (TURN)
    if req.candidate is not None:
        return _handle_start(req)
    elif req.message is not None:
        return _handle_turn(req)
    else:
        raise HTTPException(
            status_code=422,
            detail="Request must contain either 'candidate' (start) or 'message' (turn).",
        )


# ─── Data Endpoints ──────────────────────────────────────────────────

@app.get("/health")
@app.get("/api/health")
async def health_check():
    """Keep-alive ping endpoint for UptimeRobot / Cron pinger services."""
    return {"status": "ok", "service": "interviewIQ Engine"}


@app.get("/api/candidates")
async def get_candidates():
    """Retrieve all candidate profiles."""
    return CANDIDATES


@app.get("/api/curriculum")
async def get_curriculum():
    """Retrieve full curriculum data."""
    return CURRICULUM


@app.get("/api/history")
async def get_history():
    """Retrieve all persistent candidate interview session records."""
    return db_store.get_all_history()


@app.post("/api/history")
async def save_history(record: dict):
    """Save or update a candidate interview session record in persistent SQLite DB."""
    db_store.save_interview_history(record)
    return {"status": "success", "message": "Interview session saved persistently"}


# ─── START Flow ──────────────────────────────────────────────────────

def _handle_start(req: InterviewRequest) -> InterviewResponse:
    """Initialize session and return the first interview question."""
    session_id = req.sessionId
    candidate = req.candidate  # type: ignore[assignment]
    persona = req.persona or "Pragmatic Architect"

    logger.info("START interview  session=%s  candidate=%s  persona=%s", session_id, candidate.get("member", {}).get("name", "unknown"), persona)

    # 1. Build focus plan from candidate missions
    focus_plan = build_focus_plan(candidate)
    logger.info("Focus plan built: %d entries covering days %s",
                len(focus_plan), [e["day"] for e in focus_plan])

    # 2. Initialize session
    user_name = req.userName or "Candidate"
    session = create_session(session_id, candidate, focus_plan, persona, user_name)

    # 3. Get the first focus area
    if not focus_plan:
        return InterviewResponse(
            reply=f"Welcome {user_name}! Let's have a conversation about your learning journey.",
            done=False,
            focusReason="General assessment",
            moduleN=1,
        )

    first_focus = focus_plan[0]

    # 4. Generate the first question via LLM
    candidate_role = candidate.get("member", {}).get("jobRole", "candidate")

    result = llm.generate_question(
        candidate_name=candidate.get("member", {}).get("name", "there"),
        candidate_role=candidate_role,
        focus_area=first_focus,
        persona=session.persona,
        user_name=user_name
    )

    # 5. Update session state
    session.transcript.append({"role": "interviewer", "content": result["reply"]})
    session.questions_asked = 1
    session.days_covered.add(first_focus["day"])
    session.current_focus_index = 0

    # 6. Return response (no verdict on START)
    return InterviewResponse(
        reply=result["reply"],
        done=False,
        focusReason=result.get("focusReason", first_focus["reason"]),
        moduleN=result.get("moduleN", first_focus["moduleN"]),
    )


# ─── TURN Flow ───────────────────────────────────────────────────────

def _handle_turn(req: InterviewRequest) -> InterviewResponse:
    """Process candidate answer, grade, decide to continue or end."""
    session_id = req.sessionId
    message = req.message  # type: ignore[assignment]

    # 1. Check session exists or restore seamlessly
    session = get_session(session_id)
    if session is None:
        logger.info("Session %s not found in memory, restoring dynamically...", session_id)
        default_candidate = CANDIDATES[0]
        focus_plan = build_focus_plan(default_candidate)
        session = create_session(session_id, default_candidate, focus_plan, persona="Pragmatic Architect", user_name="Candidate")

    logger.info("TURN  session=%s  question#=%d  message_len=%d",
                session_id, session.questions_asked, len(message))

    # 2. Append candidate's answer to transcript
    session.transcript.append({"role": "candidate", "content": message})

    # 3. Figure out the current question text (last interviewer message)
    current_question = ""
    for entry in reversed(session.transcript):
        if entry["role"] == "interviewer":
            current_question = entry["content"]
            break

    # 4. Get candidate info
    candidate_name = session.candidate.get("member", {}).get("name", "there")
    candidate_role = session.candidate.get("member", {}).get("jobRole", "candidate")

    # 5. Call LLM to grade + generate next question (single round trip)
    grading = llm.grade_and_continue(
        transcript=session.transcript,
        current_question=current_question,
        focus_plan=session.focus_plan,
        current_focus_index=session.current_focus_index,
        days_covered=session.days_covered,
        questions_asked=session.questions_asked,
        candidate_name=candidate_name,
        candidate_role=candidate_role,
        persona=session.persona,
        user_name=session.user_name,
    )

    verdict = grading.get("verdict", "partial")
    session.verdicts.append(verdict)

    # 6. Backend enforces the real ending rule
    should_end = _should_end_interview(
        questions_asked=session.questions_asked,
        days_covered=session.days_covered,
        llm_says_end=grading.get("shouldEnd", False),
        focus_plan_exhausted=session.current_focus_index + 1 >= len(session.focus_plan),
    )

    if should_end:
        return _end_interview(session, verdict, candidate_name, candidate_role)

    next_question = grading.get("nextQuestion")
    if not next_question:
        curr_topic = session.focus_plan[min(session.current_focus_index, len(session.focus_plan) - 1)]
        res_q = llm.generate_question(
            candidate_name=candidate_name,
            candidate_role=candidate_role,
            focus_area=curr_topic,
            persona=session.persona,
            user_name=session.user_name
        )
        next_question = res_q["reply"]

    next_moduleN = grading.get("moduleN", 0)
    next_focusReason = grading.get("focusReason", "")

    # Advance focus topic index for the next turn
    session.current_focus_index = min(session.current_focus_index + 1, len(session.focus_plan) - 1)
    if session.current_focus_index < len(session.focus_plan):
        new_day = session.focus_plan[session.current_focus_index]["day"]
        session.days_covered.add(new_day)

    session.transcript.append({"role": "interviewer", "content": next_question})
    session.questions_asked += 1

    return InterviewResponse(
        reply=next_question,
        done=False,
        focusReason=next_focusReason,
        moduleN=next_moduleN,
        verdict=verdict,
    )


# ─── END Flow ────────────────────────────────────────────────────────

def _end_interview(
    session,
    last_verdict: str,
    candidate_name: str,
    candidate_role: str,
) -> InterviewResponse:
    """Generate feedback and return the final interview response."""
    logger.info("ENDING interview  questions=%d  days=%d  verdicts=%s",
                session.questions_asked, len(session.days_covered), session.verdicts)

    feedback_data = llm.generate_feedback(
        transcript=session.transcript,
        verdicts=session.verdicts,
        candidate_name=candidate_name,
        candidate_role=candidate_role,
        user_name=session.user_name,
    )

    feedback = Feedback(
        summary=feedback_data.get("summary", "Interview completed."),
        strengths=feedback_data.get("strengths", []),
        gaps=feedback_data.get("gaps", []),
        next=feedback_data.get("next", []),
    )

    # Persist completed interview session to SQLite DB
    try:
        import datetime
        db_store.save_interview_history({
            "id": getattr(session, "session_id", "session_" + str(os.urandom(4).hex())),
            "userName": session.user_name,
            "candidateRole": candidate_role,
            "persona": session.persona,
            "date": datetime.date.today().isoformat(),
            "feedback": feedback_data,
            "transcript": session.transcript,
        })
    except Exception as exc:
        logger.error("Failed to auto-persist completed session: %s", exc)

    return InterviewResponse(
        reply="Interview completed.",
        done=True,
        feedback=feedback,
    )


# ─── Ending logic ───────────────────────────────────────────────────

def _should_end_interview(
    questions_asked: int,
    days_covered: set[int],
    llm_says_end: bool,
    focus_plan_exhausted: bool,
) -> bool:
    """Backend-enforced ending rule.

    End when:  questionsAsked >= 8  AND  daysCovered >= 4
    Hard cap:  questionsAsked >= 12  (never run forever)

    The LLM's shouldEnd is only honoured if both minimums are met.
    """
    met_minimums = questions_asked >= MIN_QUESTIONS and len(days_covered) >= MIN_DAYS

    # Hard cap — always end
    if questions_asked >= HARD_CAP_QUESTIONS:
        return True

    # Focus plan exhausted AND minimums met
    if focus_plan_exhausted and met_minimums:
        return True

    # LLM says end AND minimums met
    if llm_says_end and met_minimums:
        return True

    # Minimums met and we've covered enough ground
    if met_minimums and focus_plan_exhausted:
        return True

    return False


# ─── Static Mount (conditional — only if frontend dir exists locally) ────

frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../frontend"))
if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="static")
else:
    logger.warning("Frontend dir not found at %s — static mount skipped (normal on Render)", frontend_dir)
