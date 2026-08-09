# Prompts

## Prompt 1: Initial Build Request
```
PROJECT: ABTalks AI Interview Agent — FastAPI Backend Only
(paste technical-spec.md, curriculum.json, candidates.json into Antigravity along with this prompt)

═══════════════════════════════════
FOLDER STRUCTURE
═══════════════════════════════════

interview-agent/backend/
 ├── app/
 │    ├── main.py                    (FastAPI app, CORS, router mount)
 │    ├── interview/
 │    │    ├── focus_plan.py         (builds priority plan from candidate missions)
 │    │    ├── llm.py                (isolated LLM call functions, swappable provider)
 │    │    └── session_store.py      (in-memory dict, session lifecycle)
 │    ├── data/
 │    │    ├── technical-spec.md
 │    │    ├── curriculum.json
 │    │    └── candidates.json
 │    └── models/                    (Pydantic request/response schemas)
 ├── requirements.txt
 └── .env.example                    (LLM_API_KEY=, LLM_PROVIDER=)

═══════════════════════════════════
GOAL
═══════════════════════════════════

Build a FastAPI backend exposing exactly one endpoint, POST /api/interview, that conducts
a personalized multi-turn technical interview grounded in real curriculum and candidate
data, matching technical-spec.md exactly. Must run cleanly on localhost before deployment.

═══════════════════════════════════
DATA SHAPES
═══════════════════════════════════

curriculum.json → modules[]: {n, title, days:[start,end]} | days[]: {day, title, type, tools[], objectives[]}
candidates.json → candidates[]: { member:{id,name,jobRole,yearsExperience,education,status},
                                   missions[]:{day,title,passed?,attempts?,skipped?},
                                   signals:{commitDays,missionsCompleted,missionsFirstTry} }

On app startup: load curriculum.json and candidates.json into memory ONCE (module-level,
not per-request). Build a day → {title, type, tools, objectives} lookup dict for fast access.

═══════════════════════════════════
ENDPOINT CONTRACT (must match exactly)
═══════════════════════════════════

POST /api/interview — no auth, state keyed by sessionId, in-memory dict.
Determine request type by payload shape: has "candidate" key → START, has "message" only → TURN.

Start:
  Request:  { "sessionId": "abc-123", "candidate": {...} }
  Response: { "reply": "...", "done": false, "focusReason": "...", "moduleN": <int> }

Turn:
  Request:  { "sessionId": "abc-123", "message": "..." }
  Response: { "reply": "...", "done": false, "focusReason": "...", "moduleN": <int>, "verdict": "strong"|"partial"|"gap" }

End:
  Response: {
    "reply": "Interview completed.", "done": true,
    "feedback": { "summary": "string", "strengths": [], "gaps": [], "next": [] }
  }

focusReason/moduleN/verdict are additive extras — reply/done/feedback must never break,
since the evaluator depends on that base contract from technical-spec.md.

═══════════════════════════════════
START FLOW — STEP BY STEP
═══════════════════════════════════

1. Read sessionId + candidate from body
2. Build the focus plan from candidate.missions:
   - Tier 1 (ask first): skipped == true OR passed == false
   - Tier 2 (ask next): passed == true AND attempts >= 3 (struggled but passed)
   - Tier 3 (ask if room remains): attempts == 1 (fast pass — ask a harder stretch question)
   - Order Tier 1 → 2 → 3, but interleave slightly so it doesn't read as an obvious
     "weak points first" script
3. Confirm the plan spans at least 4 distinct curriculum days — if the candidate's mission
   list is too short, pull additional days from curriculum.json they haven't attempted at
   all, framed as "let's see what you know here"
4. Initialize session_store[sessionId] = { candidate, focusPlan, transcript: [],
   questionsAsked: 0, daysCovered: set() }
5. Call llm.generate_question() with candidate name/role + first focus area's day title,
   objectives, and tools from curriculum.json. Request structured JSON:
   { "reply": "...", "moduleN": <int>, "focusReason": "<short string>" }
6. Append the question to transcript, return the response (no "verdict" key — nothing graded yet)

═══════════════════════════════════
TURN FLOW — STEP BY STEP
═══════════════════════════════════

1. Read sessionId + message
2. If sessionId missing/expired: return { "reply": "This session has expired — please
   restart the interview.", "done": true, "feedback": null } — graceful, not a raw 404
3. Append the candidate's answer to the transcript for the current question
4. Call llm.grade_and_continue() in ONE combined call (avoid two LLM round trips):
   Input: full transcript, question just answered, focus plan, daysCovered, questionsAsked
   Output JSON: { "verdict": "strong"|"partial"|"gap", "shouldEnd": bool,
   "nextQuestion": "..." (omit if ending), "moduleN": <int> (omit if ending),
   "focusReason": "..." (omit if ending) }
5. Backend enforces the real ending rule regardless of the LLM's shouldEnd suggestion:
   end only when questionsAsked >= 8 AND len(daysCovered) >= 4 — never end early, and hard
   cap at ~12 questions even if conditions aren't fully met, so a demo can't run forever
6. If continuing: increment questionsAsked, add day to daysCovered, append new question,
   return { reply, done:false, focusReason, moduleN, verdict } (verdict grades the answer
   just given)
7. If ending: call llm.generate_feedback() with full transcript + verdicts, requesting
   { summary, strengths[], gaps[], next[] } — each point must reference something specific
   the candidate actually said, not generic filler. Return { reply: "Interview completed.",
   done: true, feedback }

═══════════════════════════════════
ERROR HANDLING
═══════════════════════════════════

- Wrap every LLM call in try/except — on failure, return a graceful fallback reply
  ("Let's continue — could you expand on that?") instead of crashing, so a flaky LLM
  call doesn't kill a live demo
- Validate incoming payloads with Pydantic — reject malformed requests with a clear 422,
  don't let bad input reach the LLM call

═══════════════════════════════════
TECH DECISIONS
═══════════════════════════════════

- FastAPI, single router, Pydantic models matching the contract exactly
- LLM: fastest to wire up (Groq/OpenAI-compatible key via .env), isolated in one swappable
  function in llm.py — don't scatter LLM calls across files
- Session store: plain in-memory dict, no database, no auth (matches Out of Scope)
- Enable CORS for http://localhost:5173 (and your eventual deployed frontend origin)

═══════════════════════════════════
LOCALHOST SETUP — RUN BEFORE ANYTHING ELSE
═══════════════════════════════════

1. cd backend
2. python -m venv venv && source venv/bin/activate   (Windows: venv\Scripts\activate)
3. pip install -r requirements.txt
4. Copy .env.example to .env, fill in LLM_API_KEY
5. Run: uvicorn app.main:app --reload --port 8000
6. Confirm it's up: open http://localhost:8000/docs — FastAPI's auto docs should load
   and show POST /api/interview

═══════════════════════════════════
LOCAL TEST CHECKLIST
═══════════════════════════════════

- [ ] POST start (via /docs or curl/Postman) → confirm { reply, done:false, focusReason, moduleN }
- [ ] Send 8+ sequential turns manually → confirm final response has done:true with a full
      feedback object (summary, strengths, gaps, next all populated)
- [ ] Confirm daysCovered actually reaches 4+ distinct days across the run
- [ ] Kill LLM key temporarily (bad env var) → confirm fallback reply returns instead of a 500
- [ ] Confirm field names match technical-spec.md exactly — no renamed keys

Only move to frontend wiring or deployment once every box above is checked.

═══════════════════════════════════
FILE INSTRUCTIONS
═══════════════════════════════════

Create progress.md, activeContext.md, prompts.md at project root if they don't exist.
Append this exact prompt to prompts.md before starting the build, with a one-line summary
once done.
Update progress.md once the local test checklist is fully passing. This zip contains all UI files, technical-spec.md, curriculum.json, and candidates.json for the ABTalks AI Interview Agent — use these as the source of truth and build the FastAPI backend to match the contract exactly.
```

One-line summary: Build the FastAPI backend for the ABTalks AI Interview Agent exposing `POST /api/interview` for personalized multi-turn interviews using in-memory sessions and LLM grading.

---

## Prompt 2: Continue Request
```
continue
```

One-line summary: Instruction to continue the work after fixing the OpenAI client initialization key issue.

---

## Prompt 3: Save Prompts Request
```
make sure u are saving myeac hprompt as it is
```

One-line summary: Explicit request to ensure every single prompt from the user is saved exactly as it is.

---

## Prompt 4: How to Test Request
```
how to test
```

One-line summary: User asking for instructions on how to test the backend locally.

---

## Prompt 5: PowerShell Command Error Request
```
nv\Scripts\python.exe : The module 'venv' could not be loaded. For 
more information, run 'Import-Module venv'.
At line:1 char:1
+ venv\Scripts\python.exe 
"C:\Users\karpe\.gemini\antigravity-ide\brain ...
+ ~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : ObjectNotFound: (venv\Scripts\python.exe 
   :String) [], CommandNotFoundException
    + FullyQualifiedErrorId : CouldNotAutoLoadModule
```

One-line summary: User reporting command execution error due to running the venv command in the wrong directory.

---

## Prompt 6: Connection Refused Error Request
```
  File "C:\Users\karpe\.gemini\antigravity-ide\brain\09df06b9-3f6e-43c4-9652-eb6c7ef16fd6\scratch\test_backend.py", line 112, in <module>       
    test_flow()
    ~~~~~~~~~^^
  File "C:\Users\karpe\.gemini\antigravity-ide\brain\09df06b9-3f6e-43c4-9652-eb6c7ef16fd6\scratch\test_backend.py", line 41, in test_flow       
    assert status == 200, f"Expected 200, got {status}"
           ^^^^^^^^^^^^^
AssertionError: Expected 200, got 500
PS C:\Users\karpe\Desktop\Interview agent\interview-
```

One-line summary: User reporting a connection refused (500/WinError 10061) error when running tests without starting the server first.

---

## Prompt 7: Connection Refused Retry Request
```
same issue
```

One-line summary: User indicating they got the same connection refused error again because the server was not running.

---

## Prompt 8: Build Frontend Request
```
test passed, now focus on building frontend and connect our api to it
```

One-line summary: User requesting to focus on building the frontend and connecting the API to it.

---

## Prompt 9: Groq API Key and gitignore Configuration Request
```
now wanna setup an llm api for the perosnalized answers, i wanna use grpq but dont wanna expose key during submission create .enc adn gitignore heres my key :gsk_REDACTED_SECRET_KEY
```

One-line summary: User requesting to set up Groq API key in .env and gitignore to prevent key exposure.

---

## Prompt 10: In-Context Scenarios Request
```
llm isnt asnweing based on my question, can u create various functions aroud each expected input , like 30 diffrent scanrios and  llama will read it and aasnwer based on that
```

One-line summary: User requesting to create 30 different in-context scenarios so that the LLM can reference them to generate accurate questions and grade answers.

---

## Prompt 11: Handle Generic Questions Request
```
 still not answering well, user could be asking some generic question als ofix it
```

One-line summary: User requesting to fix the response when the candidate asks a generic question (e.g. "what is ai") rather than answering the technical question.

---

## Prompt 12: Group Candidates and Elect Interviewer Request
```
thus looks so complex . the ui looks sluggish and filled, maek section for wach type of engineer, and within that user will be able t oelect interviewer
```

One-line summary: User requesting to categorize candidates into sections by engineering discipline and allow selecting the interviewer/persona.

---

## Prompt 13: Live Conversational Greet and Answer Generic Query Request
```
 this was reply to hi hello, it should respond real time to users query, and if its generic answer generic while keeping intevieww context
```

One-line summary: User requesting the LLM to greet back or answer generic queries dynamically before prompting to return to the technical question.

---

## Prompt 14: 3D Model on Landing Page Request
```
now landing pagee looks s o mepty, i wanna    add a 3d model that is free adn looks relvant there
```

One-line summary: User requesting to add a free and relevant 3D model/animation to the landing page to fill the empty visual space.

---

## Prompt 15: Interview Workspace Illustration Request
```
find something related to interview,, like a person sitting on desk or working in office
```

One-line summary: User requesting to replace the 3D grid with an interview-related asset like a person working at an office desk.

---

## Prompt 16: Fix Image Path Request
```
not visbile and interative, find me online if u cant fix it
```

One-line summary: User pointing out that the landing page illustration is broken (showing alt text), requesting a fix or finding an online alternative.

---

## Prompt 17: Embed 3D Model with Locked Rotations Request
```
theresss a office worker model i added in our folder, add it to mainscreen, lock all axis for rotations
```

One-line summary: User requesting to render their custom GLB 3D model (office-worker) on the landing page, locking all rotation axes.

---

## Prompt 18: Autoplay 3D Model Animation Request
```
model is not playing, [lay in a loop
```

One-line summary: User requesting to play the GLB model's animation in a continuous loop.

---

## Prompt 19: Rename Application Request
```
now since this is for interview after the program,adn help u build confidence and practice for real interviews, name it acccordingly
```

One-line summary: User requesting to rename the app and titles to highlight post-program confidence building and real interview practice.

---

## Prompt 20: Rename App to interviewIQ Request
```
  name it interviewIQ
```

One-line summary: User requesting to rename the application to interviewIQ.

---

## Prompt 21: Restore Model with Increased Size and Shift Right Request
```
okay retore model, dont keep the box boundary to it increase its size and move slightly to the right, remote prompts  realted to pan tool
```

One-line summary: User requesting to restore the locked model (no camera-controls), increase its size, shift it slightly to the right, and remove previous prompts about the pan tool.

---

## Prompt 22: Resize by 50% and Shift Right by 10% Request
```
 increase size by 50% and move to the right 10%
```

One-line summary: User requesting to increase the 3D model scale by 50% and translate its container to the right by 10%.

---

## Prompt 23: Multi-feature Request (Hamburger Menu, Overall Progress Tracker, Competency Profiler, Custom Name personalization, and Report Downloads)
```
now i wanna add some unique 3 4 features, first a 3 line menu, and features are  firstly progress of overall interviews, where user excels, downnloadble report generated specifically  for user,ask for user name each time before he  starts interview and perosnlaize everthing around him, interivew report and progress
```

One-line summary: User requesting a slide-out hamburger navigation menu, overall session progress analytics, a competency profiler, a name input dialog to personalize assessment sessions, and downloadable feedback reports.

---

## Prompt 24: Problem Statement Gap Analysis & Deployment Suggestions Request
```
ill give u wh hele problem statement tell me what feels lackyThe Situation
The AI Cohort is a 31-day enterprise AI engineering program covering modern AI topics including:

Retrieval-Augmented Generation (RAG)
Vector Databases
Prompt Engineering
Agentic AI
Model Context Protocol (MCP)
AI Deployment
Production AI Systems
After completing the cohort, learners should be able to confidently explain the systems they built and the engineering decisions behind them.

However, preparing for technical interviews and effectively communicating this knowledge remains one of the biggest challenges.

Your task is to build an AI Interview Agent that conducts personalized technical interviews based on a candidate's learning journey throughout the cohort.

Your Challenge
Design and build an AI agent capable of conducting a realistic, multi-turn technical interview.

The interview should:

Assess the candidate's understanding of the concepts they have completed.
Adapt naturally throughout the conversation.
Ask intelligent follow-up questions.
Maintain context across the interview.
Provide actionable feedback at the end.
The overall experience should resemble a real technical interview rather than a scripted questionnaire.

What You're Given
Every team will receive the following resources:

1. Curriculum
A structured JSON containing the complete 31-day AI Cohort curriculum, including:

Modules
Daily topics
Learning objectives
Tools used throughout the program
2. Candidate Profiles
A collection of candidate profiles describing each participant's progress through the cohort, including:

Completed missions
Attempts
Skipped topics
Learning signals
3. Technical Specification
A separate document defining:

Required API contract
Submission requirements
Request/response formats
Minimum Requirements
Your solution must:

Conduct a conversational technical interview.
Ask a minimum of 8 questions covering at least 4 different curriculum days.
Generate follow-up questions based on previous responses.
Maintain conversation context throughout the interview.
Produce structured feedback at the end of the interview.
Expose the required HTTP endpoint defined in the Technical Specification.
You are free to choose any:

AI models
Frameworks
Agent orchestration strategy
Retrieval pipeline
System architecture
Out of Scope
The following are not required:

Voice interaction
User authentication
Persistent user accounts
Long-term conversation history
Mobile applications
Notes
All curriculum and candidate data provided for this challenge are synthetic and intended solely for the hackathon.
Teams may use any AI models, agent frameworks, vector databases, or supporting technologies.
Creativity in interview flow, reasoning, interaction design, and overall user experience is highly encouraged.
Attached Resources
Curriculum JSON
Candidate Profiles
Technical Specification ,also suggest me where i can deploy this full stack agent easily
```

One-line summary: User sharing the complete hackathon problem statement to identify missing requirements/gaps and asking for deployment platform recommendations.

---

## Prompt 25: Eliminate Repetitive Fallback Text Request
```
 THIS LINE  is repetetive and not needed, i need a new answeer to each user query or answer
```

One-line summary: User requesting to remove repetitive fallback strings like "Let's continue — could you expand on that?" and generate unique, contextual questions dynamically for every response.

---

## Prompt 26: Railway Full-Stack Deployment Query
```
can railwahy handle full stack deployment
```

One-line summary: User asking if Railway can handle deploying the complete full-stack application (FastAPI backend + Vanilla frontend).

---

## Prompt 27: Step-by-Step Railway Deployment Guide Request
```
guide
```

One-line summary: User providing a screenshot of Railway Project Settings and requesting step-by-step guidance to connect GitHub, set environment variables, and generate a public deployment domain.

---

## Prompt 28: Railway Target Port Prompt Query
```
[Screenshot showing Railway Generate Service Domain modal: "Enter the port your app is listening on"]
```

One-line summary: User providing a screenshot of Railway's target port prompt and asking which port to enter for the service domain generation.

---

## Prompt 29: Railway Free Limit Query & 100% Free Alternatives Request
```
it has 5 dolar limit
```

One-line summary: User noting Railway's $5 trial limit and requesting a 100% free alternative platform (Render.com) with no credit card requirement.





























