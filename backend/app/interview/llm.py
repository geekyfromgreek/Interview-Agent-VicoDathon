"""
Isolated LLM call functions — swappable provider.

All three public functions are wrapped in try/except so a flaky LLM
call never crashes a live demo.  On failure a graceful fallback is
returned instead.

Provider is configured via .env:
    LLM_API_KEY      – API key
    LLM_PROVIDER     – "groq" | "openai"  (maps to base_url)
    LLM_MODEL        – model identifier
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI
from app.interview.scenarios import SCENARIOS

load_dotenv()

logger = logging.getLogger(__name__)

# ─── Provider config ─────────────────────────────────────────────────

_PROVIDER_URLS: dict[str, str] = {
    "groq": "https://api.groq.com/openai/v1",
    "openai": "https://api.openai.com/v1",
}

_api_key = os.getenv("LLM_API_KEY", "")
_provider = os.getenv("LLM_PROVIDER", "groq").lower()
_model = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
_base_url = _PROVIDER_URLS.get(_provider, _PROVIDER_URLS["groq"])

_client = OpenAI(api_key=_api_key or "mock_key", base_url=_base_url)


# ─── JSON Extraction Helper ─────────────────────────────────────────

def _extract_json(text: str) -> dict | None:
    """Try to extract a JSON object from LLM text that may contain markdown fences."""
    # Try direct parse first
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass

    # Try extracting from ```json ... ``` fences
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try finding first { ... } block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return None


# ─── Public API ──────────────────────────────────────────────────────

def generate_question(
    candidate_name: str,
    candidate_role: str,
    focus_area: dict[str, Any],
    persona: str = "Pragmatic Architect",
    user_name: str = "Candidate",
) -> dict[str, Any]:
    """Generate the first (or next) interview question for a focus area.

    Returns: {"reply": str, "moduleN": int, "focusReason": str}
    """
    day_num = focus_area.get("day", 1)
    scenario = SCENARIOS.get(day_num, {})
    typical_question = scenario.get("typical_question", "")

    persona_prompts = {
        "Pragmatic Architect": (
            "You are a pragmatic software architect technical interviewer. "
            "Focus heavily on structural trade-offs, architecture decisions, database choices, and system design."
        ),
        "Rigorous Lead": (
            "You are a tough, rigorous lead developer technical interviewer. "
            "Keep questions direct and demanding, and grade answers strictly against exact technical terms."
        ),
        "Encouraging Mentor": (
            "You are a friendly, encouraging technical mentor interviewer. "
            "Frame questions supportively and provide helpful framing context."
        )
    }
    persona_instruction = persona_prompts.get(persona, persona_prompts["Pragmatic Architect"])

    system_prompt = (
        f"{persona_instruction}\n"
        f"Greet the candidate as '{user_name}' (e.g. 'Hello {user_name}, let's talk about...').\n"
        "Ask ONE clear, specific question that tests whether the candidate truly understands "
        "the topic — not a yes/no question. Personalise the question to their role.\n\n"
        "You MUST respond with a JSON object and nothing else:\n"
        '{"reply": "<your question>", "moduleN": <int>, "focusReason": "<short reason>"}'
    )

    user_prompt = (
        f"Candidate: {candidate_name} ({candidate_role})\n"
        f"Topic: Day {focus_area['day']} — {focus_area['title']}\n"
        f"Module: {focus_area['moduleN']}\n"
        f"Focus reason: {focus_area['reason']}\n"
        f"Day type: {focus_area['type']}\n"
        f"Tools covered: {', '.join(focus_area['tools'])}\n"
        f"Learning objectives:\n"
        + "\n".join(f"  - {obj}" for obj in focus_area["objectives"])
        + f"\n\nHere is a reference/sample question for this topic to guide you:\n"
        f"Reference Question: {typical_question}\n\n"
        "Generate a personalised technical question based on this topic and reference."
    )

    try:
        resp = _client.chat.completions.create(
            model=_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=500,
        )
        raw = resp.choices[0].message.content or ""
        parsed = _extract_json(raw)
        if parsed and "reply" in parsed:
            parsed.setdefault("moduleN", focus_area["moduleN"])
            parsed.setdefault("focusReason", focus_area["reason"])
            return parsed
        if raw.strip():
            return {
                "reply": raw.strip(),
                "moduleN": focus_area["moduleN"],
                "focusReason": focus_area["reason"],
            }
    except Exception as exc:
        logger.error("LLM generate_question primary call failed: %s", exc)

    # Retry with Groq LLM using alternative model or temperature to guarantee 100% LLM generation
    for attempt in range(2):
        try:
            resp = _client.chat.completions.create(
                model=_model,
                messages=[
                    {"role": "system", "content": f"{persona_instruction}\nGreet {user_name} and ask a unique technical question about {focus_area['title']}. Do NOT use static templates."},
                    {"role": "user", "content": f"Candidate: {candidate_name} ({candidate_role}). Focus: {focus_area['title']} with tools {', '.join(focus_area['tools'])}. Ask a creative initial question."},
                ],
                temperature=0.7 + (attempt * 0.1),
                max_tokens=400,
            )
            reply_text = resp.choices[0].message.content or ""
            if reply_text.strip():
                return {
                    "reply": reply_text.strip(),
                    "moduleN": focus_area["moduleN"],
                    "focusReason": focus_area["reason"],
                }
        except Exception as retry_exc:
            logger.error("LLM generate_question retry %d failed: %s", attempt + 1, retry_exc)

    return {
        "reply": f"Welcome {user_name}! I'm {candidate_name} ({candidate_role}). Let's dive right into {focus_area['title']} — how have you practically designed and implemented solutions using {focus_area['tools'][0] if focus_area['tools'] else 'this stack'}?",
        "moduleN": focus_area["moduleN"],
        "focusReason": focus_area["reason"],
    }


def grade_and_continue(
    transcript: list[dict[str, str]],
    current_question: str,
    focus_plan: list[dict[str, Any]],
    current_focus_index: int,
    days_covered: set[int],
    questions_asked: int,
    candidate_name: str,
    candidate_role: str,
    persona: str = "Pragmatic Architect",
    user_name: str = "Candidate",
) -> dict[str, Any]:
    """Grade the candidate's latest answer AND generate the next question in ONE call.

    Returns:
        {
            "verdict": "strong"|"partial"|"gap",
            "shouldEnd": bool,
            "nextQuestion": str,       # omitted if ending
            "moduleN": int,            # omitted if ending
            "focusReason": str         # omitted if ending
        }
    """
    # Determine next focus area (if any remain)
    next_index = current_focus_index + 1
    next_focus = None
    if next_index < len(focus_plan):
        next_focus = focus_plan[next_index]

    # Get scenarios safely
    if current_focus_index < len(focus_plan):
        current_focus = focus_plan[current_focus_index]
    else:
        current_focus = focus_plan[-1] if focus_plan else {
            "day": 1, "title": "General Assessment", "moduleN": 1, "reason": "General follow-up", "type": "Core", "tools": [], "objectives": []
        }
    curr_day = current_focus.get("day", 1)
    curr_scenario = SCENARIOS.get(curr_day, {})

    next_scenario = {}
    if next_focus:
        next_scenario = SCENARIOS.get(next_focus.get("day", 1), {})

    # Build transcript text
    transcript_text = "\n".join(
        f"{'Interviewer' if t['role'] == 'interviewer' else 'Candidate'}: {t['content']}"
        for t in transcript
    )

    next_topic_block = ""
    if next_focus:
        next_topic_block = (
            f"\n\nNEXT TOPIC to ask about (if not ending):\n"
            f"Day {next_focus['day']} — {next_focus['title']}\n"
            f"Module: {next_focus['moduleN']}\n"
            f"Focus reason: {next_focus['reason']}\n"
            f"Tools: {', '.join(next_focus['tools'])}\n"
            f"Reference Question: {next_scenario.get('typical_question', '')}\n"
            f"Objectives:\n"
            + "\n".join(f"  - {obj}" for obj in next_focus["objectives"])
        )

    persona_prompts = {
        "Pragmatic Architect": (
            "You are a pragmatic software architect technical interviewer. "
            "Focus heavily on structural trade-offs, architecture decisions, database choices, and system design."
        ),
        "Rigorous Lead": (
            "You are a tough, rigorous lead developer technical interviewer. "
            "Keep questions direct and demanding, and grade answers strictly against exact technical terms."
        ),
        "Encouraging Mentor": (
            "You are a friendly, encouraging technical mentor interviewer. "
            "Frame questions supportively and provide helpful framing context."
        )
    }
    persona_instruction = persona_prompts.get(persona, persona_prompts["Pragmatic Architect"])

    system_prompt = (
        f"{persona_instruction}\n"
        f"You are grading a technical interview answer for '{user_name}' and generating the next response.\n"
        "Be fair and analytical — award 'strong' for accurate/solid understanding, "
        "'partial' for surface-level answers, and 'gap' for wrong, incorrect, or missing knowledge.\n\n"
        "LIVE INTERVIEW CONTEXT RETENTION RULE:\n"
        "1. You MUST maintain active live memory of the ENTIRE transcript history provided below.\n"
        "2. Frequently tie your reactions back to specific statements, tools, or architectural decisions the candidate mentioned in earlier turns (e.g. 'Earlier you mentioned vector chunking with FAISS—how does that connect to...').\n"
        "3. NEVER treat questions in isolation. Build a continuous, evolving technical conversation.\n\n"
        "INTERACTION RULE:\n"
        "1. In 'nextQuestion', start with a 1-2 sentence direct reaction to what the candidate just said.\n"
        "   - DO NOT dump the full correct answer immediately if they are wrong.\n"
        "   - If their answer is wrong for the 1st time: do NOT give the answer away. Ask them to re-think their assumption (e.g. 'Not quite—think about how memory complexity grows here. How would you adjust that?').\n"
        "   - If their answer is wrong for the 2nd time on the same topic: offer a subtle hint/nudge, brief 1-sentence insight, and pivot to the next focus area.\n"
        "   - If their answer is strong: validate their specific technical insight enthusiastically.\n"
        "   - If they said 'idk', 'no idea', or pass: acknowledge supportively, give a 1-sentence nudge, and pivot.\n"
        "2. EVERY response MUST be 100% unique, dynamic, and tailored to their exact words—NEVER use repetitive static filler.\n"
        "3. THEN ask your next follow-up question or pivot to the next focus topic.\n\n"
        "You MUST respond with a JSON object and nothing else:\n"
        "{\n"
        '  "verdict": "strong" | "partial" | "gap",\n'
        '  "shouldEnd": true | false,\n'
        '  "nextQuestion": "<1-2 sentence direct reaction/hint + unique follow-up question>",\n'
        '  "moduleN": <int, active topic module>,\n'
        '  "focusReason": "<active topic title>"\n'
        "}\n\n"
        "If shouldEnd is true, omit nextQuestion/moduleN/focusReason."
    )

    user_prompt = (
        f"Candidate: {candidate_name} ({candidate_role})\n"
        f"Questions asked so far: {questions_asked}\n"
        f"Distinct days covered: {len(days_covered)}\n"
        f"Current question being answered: {current_question}\n\n"
        f"PREDEFINED EXPECTED ANSWER REFERENCE for this question:\n"
        f"- Target Question: {curr_scenario.get('typical_question', '')}\n"
        f"- Predefined Expected Model Answer: {curr_scenario.get('strong_answer', '')}\n"
        f"- Partial Answer Reference: {curr_scenario.get('partial_answer', '')}\n"
        f"- Missing/Incorrect Reference: {curr_scenario.get('gap', '')}\n\n"
        f"Full transcript:\n{transcript_text}"
        f"{next_topic_block}"
        f"\n\nEVALUATION TASK:\n"
        "1. Compare candidate's latest response against the Predefined Expected Model Answer above.\n"
        "2. Check if their answer is close to the expected concept. If close, assign 'strong'. If surface level, assign 'partial'. If wrong/missing, assign 'gap'.\n"
        "3. Generate a tailored response based on their exact input, applying the INTERACTION RULE."
    )

    try:
        resp = _client.chat.completions.create(
            model=_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=650,
        )
        raw = resp.choices[0].message.content or ""
        parsed = _extract_json(raw)
        if parsed and "verdict" in parsed:
            # Normalise verdict
            v = parsed["verdict"].lower().strip()
            if v not in ("strong", "partial", "gap"):
                v = "partial"
            parsed["verdict"] = v
            # Ensure next question details if not ending
            if not parsed.get("shouldEnd") and next_focus:
                # Clean up / convert moduleN to valid int
                m_val = parsed.get("moduleN")
                try:
                    if m_val is None or m_val == "":
                        parsed["moduleN"] = next_focus["moduleN"]
                    else:
                        parsed["moduleN"] = int(m_val)
                except (ValueError, TypeError):
                    parsed["moduleN"] = next_focus["moduleN"]

                parsed.setdefault("focusReason", next_focus["reason"])
                if "nextQuestion" not in parsed or not parsed["nextQuestion"]:
                    parsed["nextQuestion"] = (
                        f"Let's move on. Regarding {next_focus['title']} — "
                        f"can you explain how you'd approach this topic?"
                    )
            else:
                # If ending or next_focus is None, ensure moduleN is an int
                m_val = parsed.get("moduleN")
                try:
                    parsed["moduleN"] = int(m_val) if (m_val is not None and m_val != "") else 0
                except (ValueError, TypeError):
                    parsed["moduleN"] = 0
            return parsed
    except Exception as exc:
        logger.error("LLM grade_and_continue failed: %s", exc)

    # Heuristic check for greetings, generic questions, or unknown/pass answers in fallback mode
    last_candidate_msg = ""
    for entry in reversed(transcript):
        if entry["role"] == "candidate":
            last_candidate_msg = entry["content"].lower().strip()
            break

    is_greeting = any(last_candidate_msg.startswith(g) for g in ["hello", "hi", "hey", "greetings", "good morning", "good afternoon"])
    is_question = "?" in last_candidate_msg or any(q in last_candidate_msg for q in ["what is", "how do", "can you", "why do", "explain", "who is", "what are"])
    is_unknown = any(u in last_candidate_msg for u in ["no ide", "no idea", "don't know", "dont know", "not sure", "idk", "pass", "skip", "no clue"])

    current_focus = focus_plan[current_focus_index]

    fallback_reply = ""
    if is_greeting:
        fallback_reply = f"Hello {user_name}! Let me know how you'd approach our evaluation topic on {current_focus['title']}."
    elif is_question:
        if "what is ai" in last_candidate_msg:
            fallback_reply = f"AI refers to algorithms that perform tasks requiring cognitive capabilities. Returning to {current_focus['title']} — how have you applied {current_focus['tools'][0] if current_focus['tools'] else 'these tools'}?"
        else:
            fallback_reply = f"Good question! To keep our assessment on track regarding {current_focus['title']} — could you describe your practical experience here?"
    elif is_unknown:
        if next_focus:
            fallback_reply = f"No problem at all, {user_name}! Let's move on to our next area: {next_focus['title']}. How have you worked with {next_focus['tools'][0] if next_focus['tools'] else 'these tools'}?"
        else:
            fallback_reply = f"No worries! Regarding {current_focus['title']}, which concepts or tools are you most familiar with?"

    fallback: dict[str, Any] = {
        "verdict": "gap" if (is_question or is_unknown) else "partial",
        "shouldEnd": False,
    }

    if fallback_reply:
        fallback["nextQuestion"] = fallback_reply
        fallback["moduleN"] = (next_focus["moduleN"] if (is_unknown and next_focus) else current_focus["moduleN"])
        fallback["focusReason"] = (next_focus["reason"] if (is_unknown and next_focus) else current_focus["reason"])
    elif next_focus:
        fallback["nextQuestion"] = (
            f"Let's explore {next_focus['title']}. "
            f"What's your experience with {next_focus['tools'][0] if next_focus['tools'] else 'this area'}?"
        )
        fallback["moduleN"] = next_focus["moduleN"]
        fallback["focusReason"] = next_focus["reason"]
    else:
        fallback["nextQuestion"] = f"Regarding {current_focus['title']} — what was your main takeaway from implementing this?"
        fallback["moduleN"] = current_focus["moduleN"]
        fallback["focusReason"] = current_focus["reason"]

    return fallback


def generate_feedback(
    transcript: list[dict[str, str]],
    verdicts: list[str],
    candidate_name: str,
    candidate_role: str,
    user_name: str = "Candidate",
) -> dict[str, Any]:
    """Generate final feedback from the full interview.

    Returns: {"summary": str, "strengths": [], "gaps": [], "next": []}

    Each point must reference something specific the candidate said.
    """
    transcript_text = "\n".join(
        f"{'Interviewer' if t['role'] == 'interviewer' else 'Candidate'}: {t['content']}"
        for t in transcript
    )

    verdict_summary = ", ".join(
        f"Q{i+1}: {v}" for i, v in enumerate(verdicts)
    )

    system_prompt = (
        f"You are writing a comprehensive technical assessment feedback report for '{user_name}'.\n"
        "CRITICAL RULES:\n"
        "1. If the candidate answered any questions wrong or received a 'gap' / 'partial' verdict, you MUST explicitly identify those wrong answers and missing technical concepts under 'gaps'.\n"
        "2. Detail exactly why those answers were incorrect based on the transcript.\n"
        "3. Under 'strengths', highlight specific technical topics they answered correctly.\n"
        "4. Under 'next', list concrete actionable study recommendations.\n\n"
        "You MUST respond with a JSON object and nothing else:\n"
        "{\n"
        '  "summary": "<2-3 sentence overall performance evaluation>",\n'
        '  "strengths": ["<specific accurate answer / strength 1>", "..."],\n'
        '  "gaps": ["<specific wrong answer / gap 1 with explanation>", "..."],\n'
        '  "next": ["<specific recommendation 1>", "..."]\n'
        "}"
    )

    user_prompt = (
        f"Candidate: {candidate_name} ({candidate_role})\n"
        f"Verdict per question: {verdict_summary}\n\n"
        f"Full interview transcript:\n{transcript_text}\n\n"
        f"Generate the feedback report."
    )

    try:
        resp = _client.chat.completions.create(
            model=_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.5,
            max_tokens=800,
        )
        raw = resp.choices[0].message.content or ""
        parsed = _extract_json(raw)
        if parsed and "summary" in parsed:
            # Ensure all fields are present
            parsed.setdefault("strengths", [])
            parsed.setdefault("gaps", [])
            parsed.setdefault("next", [])
            return parsed
    except Exception as exc:
        logger.error("LLM generate_feedback failed: %s", exc)

    # Fallback — build from verdicts
    strong_count = verdicts.count("strong")
    gap_count = verdicts.count("gap")
    total = len(verdicts)

    return {
        "summary": (
            f"{candidate_name} answered {total} questions. "
            f"{strong_count} were rated strong and {gap_count} showed gaps. "
            f"Overall performance was {'solid' if strong_count > gap_count else 'mixed'}."
        ),
        "strengths": [
            f"Demonstrated understanding in {strong_count} out of {total} areas assessed."
        ] if strong_count > 0 else [],
        "gaps": [
            f"Showed gaps in {gap_count} out of {total} areas assessed."
        ] if gap_count > 0 else [],
        "next": [
            "Review the topics where gaps were identified and practice with hands-on exercises."
        ],
    }
