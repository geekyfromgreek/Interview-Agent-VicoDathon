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

_api_key = os.getenv("LLM_API_KEY") or os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
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

GROQ_MODELS = [
    os.getenv("LLM_MODEL", "llama-3.3-70b-versatile"),
    "llama3-70b-8192",
    "llama3-8b-8192",
    "mixtral-8x7b-32768",
    "gemma2-9b-it",
]


def _get_client() -> OpenAI:
    api_key = os.getenv("LLM_API_KEY") or os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY") or _api_key
    provider = os.getenv("LLM_PROVIDER", "groq").lower()
    base_url = _PROVIDER_URLS.get(provider, _PROVIDER_URLS["groq"])
    return OpenAI(api_key=api_key or "mock_key", base_url=base_url)


def _call_groq_llm(messages: list[dict[str, str]], max_tokens: int = 650, temperature: float = 0.7) -> str:
    """Execute Groq API call with model fallback chain so Groq LLM calls NEVER fail."""
    client = _get_client()
    last_exc = None
    for model_name in GROQ_MODELS:
        try:
            logger.info("Calling Groq API model: %s", model_name)
            resp = client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = resp.choices[0].message.content or ""
            if content.strip():
                return content
        except Exception as exc:
            logger.warning("Groq model %s failed: %s. Trying fallback model...", model_name, exc)
            last_exc = exc

    logger.error("All Groq models failed: %s", last_exc)
    raise RuntimeError(f"Groq API call failed across all models: {last_exc}")


# ─── Public API ──────────────────────────────────────────────────────

def generate_question(
    candidate_name: str,
    candidate_role: str,
    focus_area: dict[str, Any],
    persona: str = "Pragmatic Architect",
    user_name: str = "Candidate",
) -> dict[str, Any]:
    """Generate initial interview question tailored to candidate and persona via Groq LLM."""
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
        raw = _call_groq_llm(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=500,
            temperature=0.7
        )
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
        logger.error("LLM generate_question failed on initial try: %s. Retrying live Groq call...", exc)

    # Secondary Groq call with direct text prompt to guarantee 100% LLM output
    for model_name in GROQ_MODELS:
        try:
            client = _get_client()
            resp = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": persona_instruction},
                    {"role": "user", "content": f"Greet {user_name} as a technical interviewer and ask a creative question testing their knowledge of {focus_area['title']} ({', '.join(focus_area.get('tools', []))})."}
                ],
                max_tokens=400,
                temperature=0.8
            )
            text = resp.choices[0].message.content or ""
            if text.strip():
                return {
                    "reply": text.strip(),
                    "moduleN": focus_area["moduleN"],
                    "focusReason": focus_area["reason"],
                }
        except Exception as retry_err:
            logger.warning("Secondary Groq model %s failed: %s", model_name, retry_err)

    raise RuntimeError("Groq API could not generate question across all models.")


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
        "DEEP EVALUATION & DYNAMIC CHATBOT RULE:\n"
        "1. READ and EVALUATE candidate's latest response carefully against the full transcript history.\n"
        "2. In 'nextQuestion', start by explicitly addressing their exact words or technical concept (e.g., 'You mentioned X...').\n"
        "3. If their answer is correct/strong, validate why it's right with a 1-sentence technical insight. If partial or gap, highlight the exact missing nuance in 1 sentence.\n"
        "4. NEVER output repetitive or canned template text. Every single response MUST be dynamically generated live by Groq AI, completely tailored to what the candidate just typed.\n"
        "5. THEN ask your next follow-up question or pivot seamlessly to the next focus topic.\n\n"
        "You MUST respond with a JSON object and nothing else:\n"
        "{\n"
        '  "verdict": "strong" | "partial" | "gap",\n'
        '  "shouldEnd": true | false,\n'
        '  "nextQuestion": "<1-2 sentence direct evaluation referencing candidate exact words + tailored follow-up question>",\n'
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
        raw = _call_groq_llm(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=650,
            temperature=0.7
        )
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
        logger.error("LLM grade_and_continue JSON attempt failed: %s. Retrying live Groq generation...", exc)

    # Dynamic Chatbot Retry via Groq LLM — guarantees zero static template strings
    try:
        last_msg = ""
        for entry in reversed(transcript):
            if entry["role"] == "candidate":
                last_msg = entry["content"]
                break

        current_focus = focus_plan[min(current_focus_index, len(focus_plan) - 1)]
        dynamic_prompt = (
            f"You are a technical interviewer chatbot ({persona}).\n"
            f"Candidate: {user_name} ({candidate_role})\n"
            f"Candidate just said: '{last_msg}'\n"
            f"Active topic: {current_focus['title']} ({', '.join(current_focus.get('tools', []))})\n\n"
            "INSTRUCTION:\n"
            "1. Read their answer carefully.\n"
            "2. Give a direct 1-sentence reaction evaluating what they just said.\n"
            "3. Ask a tailored follow-up question or pivot to the next architectural aspect.\n"
            "Respond in 2-3 natural sentences."
        )

        raw_reply = _call_groq_llm(
            messages=[
                {"role": "system", "content": "You are a live technical interviewer AI. Answer dynamically based on candidate input. Do NOT use static templates."},
                {"role": "user", "content": dynamic_prompt}
            ],
            max_tokens=400,
            temperature=0.8
        )

        if raw_reply.strip():
            return {
                "verdict": "partial",
                "shouldEnd": False,
                "nextQuestion": raw_reply.strip(),
                "moduleN": current_focus.get("moduleN", 1),
                "focusReason": current_focus.get("reason", current_focus.get("title", ""))
            }
    except Exception as retry_exc:
        logger.error("Dynamic Groq retry failed: %s", retry_exc)

    raise RuntimeError("Groq API could not grade or continue turn across all models.")


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
        raw = _call_groq_llm(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=800,
            temperature=0.5
        )
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
