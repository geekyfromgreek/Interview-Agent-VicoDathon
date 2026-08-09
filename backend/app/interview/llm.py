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
            # Ensure moduleN is present
            parsed.setdefault("moduleN", focus_area["moduleN"])
            parsed.setdefault("focusReason", focus_area["reason"])
            return parsed
        # If JSON parse failed but we got text, use it as the reply
        if raw.strip():
            return {
                "reply": raw.strip(),
                "moduleN": focus_area["moduleN"],
                "focusReason": focus_area["reason"],
            }
    except Exception as exc:
        logger.error("LLM generate_question failed: %s", exc)

    # Fallback
    return {
        "reply": (
            f"Welcome, {candidate_name}. Let's talk about "
            f"{focus_area['title']}. Can you walk me through your understanding "
            f"of {focus_area['tools'][0] if focus_area['tools'] else 'this topic'} "
            f"and how you've applied it?"
        ),
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
        f"You are grading a technical interview answer for '{user_name}' and optionally generating "
        "the next question. Be fair — award 'strong' for solid understanding, "
        "'partial' for surface-level answers, 'gap' for wrong or missing knowledge.\n\n"
        "SPECIAL RULE FOR CANDIDATE QUESTIONS/GREETINGS/STALLS/UNKNOWN:\n"
        "1. If the candidate asks a generic question or greets (e.g. 'what is ai?', 'hello'): answer/greet briefly, then prompt back to the technical topic.\n"
        "2. If the candidate indicates they don't know, have no idea, or pass (e.g. 'no ide', 'no idea', 'idk', 'not sure', 'pass', 'skip'): acknowledge supportively without generic boilerplate, briefly explain or pivot to the next topic, and set verdict to 'gap'.\n"
        "3. NEVER output static repetitive filler like 'Let's continue — could you expand on that?'. Every question MUST be unique and reference specific topic details.\n\n"
        "You MUST respond with a JSON object and nothing else:\n"
        "{\n"
        '  "verdict": "strong" | "partial" | "gap",\n'
        '  "shouldEnd": true | false,\n'
        '  "nextQuestion": "<your unique response greeting/answering them directly or pivoting, then asking a specific technical question>",\n'
        '  "moduleN": <int, of the active topic>,\n'
        '  "focusReason": "<reason of the active topic>"\n'
        "}\n\n"
        "If shouldEnd is true, omit nextQuestion/moduleN/focusReason."
    )

    user_prompt = (
        f"Candidate: {candidate_name} ({candidate_role})\n"
        f"Questions asked so far: {questions_asked}\n"
        f"Distinct days covered: {len(days_covered)}\n"
        f"Current question being answered: {current_question}\n\n"
        f"GRADING CRITERIA REFERENCE for the current question:\n"
        f"- Typical Question context: {curr_scenario.get('typical_question', '')}\n"
        f"- What a STRONG answer covers: {curr_scenario.get('strong_answer', '')}\n"
        f"- What a PARTIAL answer covers: {curr_scenario.get('partial_answer', '')}\n"
        f"- What a GAP answer covers: {curr_scenario.get('gap', '')}\n\n"
        f"Full transcript:\n{transcript_text}"
        f"{next_topic_block}"
        f"\n\nGrade the candidate's latest answer strictly based on the grading criteria reference and decide whether to continue. "
        "If they asked a generic question, remember to apply the SPECIAL RULE."
    )

    try:
        resp = _client.chat.completions.create(
            model=_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.4,
            max_tokens=600,
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
        f"You are writing a final technical assessment feedback report for '{user_name}' who practiced a simulated technical interview.\n"
        "Every bullet point MUST reference something specific they actually said — no generic filler.\n\n"
        "You MUST respond with a JSON object and nothing else:\n"
        "{\n"
        '  "summary": "<2-3 sentence overall assessment>",\n'
        '  "strengths": ["<specific strength 1>", "..."],\n'
        '  "gaps": ["<specific gap 1>", "..."],\n'
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
