# Active Context

## Current Focus
Finished frontend SPA integration and connected the API endpoints.

## Architecture
- **Single Backend Server**: Serving both static HTML/JS pages and API endpoints.
- **Static files mount**: Serves `index.html` at `/` using FastAPI's `StaticFiles`.
- **API endpoints**:
  - `POST /api/interview` (START/TURN/END flows)
  - `GET /api/candidates` (returns list of candidates from `candidates.json`)
  - `GET /api/curriculum` (returns cohort modules and objectives)
- **Session store**: In-memory dict keyed by `sessionId`.
- **LLM provider**: Groq/OpenAI compatible, wrapped in fallback logic.

## Key Files
| File | Purpose |
|------|---------|
| `app/main.py` | FastAPI app, endpoints, static serving |
| `app/static/index.html` | SPA frontend handling landing, candidate selection, chat console, and feedback report |
| `app/interview/focus_plan.py` | Priority plans from candidate missions |
| `app/interview/llm.py` | Swappable LLM integration with graceful fallbacks |
| `app/interview/session_store.py` | In-memory session store |
| `app/models/__init__.py` | Pydantic validation schemas |

## Decisions Made
- Serve frontend directly from FastAPI (`StaticFiles`) for simplified single-port localhost operation.
- Added candidate/curriculum data endpoints to decouple candidate details from frontend code.
- State-driven SPA layout referencing the user-provided CSS classes and styles.
