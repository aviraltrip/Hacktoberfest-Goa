# DemoToSkill: Agent Coding Guidelines & Context

This file defines the project instructions, architectural boundaries, and implementation rules for building **DemoToSkill** at the Hacktoberfest Hack Day (31 Oct 2026).
**Target Prize:** Best Use of Gemma 4 Only.

---

## 1. Project Mission & North Star
DemoToSkill enables users to record a browser workflow once and convert it into a resilient, parameterized automation ("skill") that generalizes across diverse inputs and **repairs itself** when the target website's UI mutates.

### The Gemma 4 Advantage
Traditional recorders rely on brittle CSS/XPath selectors and break on UI changes. In DemoToSkill, **Gemma 4** is the cognitive backbone:
1. **Understand:** Multimodal analysis of before/after screenshots + DOM context to deduce semantic intent.
2. **Generalize:** Discerns dynamic user inputs from static navigation constants to create parameter schemas.
3. **Verify:** Dual-layer verification (deterministic + Gemma 4 visual inspection of the final state).
4. **Heal (Showpiece):** Uses **Set-of-Marks (SoM)** visual prompting over live DOM candidates to locate elements even when IDs, classes, labels, and text have completely disappeared (e.g. icon-only buttons).

---

## 2. Tech Stack & Environment Standards

| Component | Library / Tool | Requirements & Notes |
| :--- | :--- | :--- |
| **Language** | Python 3.11+ | Use async everywhere for I/O and Playwright. |
| **LLM SDK** | `google-genai` | Gemma 4 via Google GenAI (`GEMINI_API_KEY`). Models: `gemma-4-26b-a4b-it` (default) & `gemma-4-31b-it` (repair). |
| **Orchestrator** | `langgraph` >= 0.2 | Use `StateGraph`, `MemorySaver`, `interrupt()`, and `Command(resume=...)`. |
| **API Framework** | `FastAPI`, `uvicorn` | Pydantic v2 schemas, Server-Sent Events (`sse-starlette`) for real-time frontend streaming. |
| **Browser Engine** | `playwright` (async) | Chromium, headed recording, headless/headed replay. Reset context between runs. |
| **Candidate Retrieval** | `rank_bm25`, `sqlite3` | Vectorless retrieval over live interactive DOM elements + SQLite FTS5 for heal memory. |
| **Database** | SQLite3 (built-in) | Local persistence for specs, runs, call logs, and heal memory. |
| **Frontend** | React 18, Vite, Tailwind CSS | Single-page console: Record, Step Editor, Run Grid, Heal Review, Gemma Inspector. |

---

## 3. Strict Coding Conventions

### A. Gemma 4 Calls (`backend/app/llm.py`)
- **JSON Only:** Always instruct Gemma to respond with pure JSON. Do not rely on code fences. Strip ```json ... ``` fences if returned.
- **Pydantic Validation:** Always validate model output against Pydantic models. Retry once upon validation or JSON decoding failure.
- **Image Handling:** Always downscale input screenshots to a maximum width of 1024px, JPEG quality 70.
- **Rate-Limit & Concurrency:** Wrap all Gemma invocations in an `asyncio.Semaphore(3)` and cache results by SHA-256 hash of `(image_bytes + prompt_text)`.
- **Latency & Call Logging:** Every LLM call must be logged into an in-memory/SQLite call inspector table with: timestamp, prompt summary, thumbnail hashes, raw JSON output, latency (ms), and token/status stats.

### B. Playwright & Runner Safety (`backend/app/runner.py`)
- **Do NOT generate raw Playwright code strings with the LLM.** The runner interprets structured `WorkflowSpec` JSON.
- **Exactly-One Resolution Rule:** A locator candidate only wins if `await target.count() == 1`. If `count() > 1` or `count() == 0`, move to the next locator candidate.
- **Locator Fallback Chain:**
  1. Role + Accessible Name (`page.get_by_role(role, name=...)`)
  2. Label (`page.get_by_label(...)`)
  3. Placeholder (`page.get_by_placeholder(...)`)
  4. Visible Text (`page.get_by_text(...)`)
  5. Test ID (`page.get_by_test_id(...)`)
  6. CSS selector (last resort)
- **Settling:** After every interaction, await DOM stability (network idle cap 1.5s + 300ms pause) before taking screenshots or proceeding.
- **Context Isolation:** Fresh browser context per row to prevent cookie/session leakage.

### C. Privacy & Security
- Never record values of `input[type="password"]`.
- Mask sensitive field values in logs, state, and screenshots.
- Never commit `.env` or API keys.

---

## 4. Key Directory Structure
```text
Hacktoberfest-Goa/
├── AGENTS.md                  # This file
├── README.md                  # Public pitch, setup, and submission documentation
├── docs/                      # Full project specifications and architecture
│   ├── ARCHITECTURE.md        # Graph definitions, node contracts, data flow
│   ├── SPECIFICATION.md       # Pydantic schemas, API contracts, SSE protocols
│   ├── PROMPTS.md             # Gemma 4 prompt engineering templates
│   ├── DEMO_AND_ABLATION.md   # ScholarshipPortal demo app & mutation test suite
│   └── ROADMAP_AND_TASKS.md   # Hour-by-hour timeline, milestones, fallback cuts
├── .agent/
│   └── skills/
│       └── demotoskill-dev/   # Antigravity developer workflow skill
│           └── SKILL.md
├── backend/                   # Python FastAPI backend
│   ├── app/
│   │   ├── main.py            # API routes and SSE handlers
│   │   ├── models.py          # Pydantic data schemas
│   │   ├── llm.py             # Gemma 4 wrapper, cache, semaphore, call logger
│   │   ├── recorder.py        # Playwright headed recording session
│   │   ├── runner.py          # Spec interpreter and locator resolver
│   │   ├── candidates.py      # DOM extraction, BM25 ranking, Set-of-Marks overlay
│   │   ├── memory.py          # SQLite FTS5 heal memory
│   │   ├── graphs.py          # LangGraph Compile and Run graphs
│   │   ├── nodes/             # Individual graph nodes
│   │   │   ├── understand.py
│   │   │   ├── review.py
│   │   │   ├── compile_spec.py
│   │   │   ├── trial_run.py
│   │   │   ├── verify.py
│   │   │   ├── repair.py
│   │   │   └── save.py
│   │   └── prompts/           # Markdown prompt templates
│   └── requirements.txt
├── frontend/                  # Vite + React + Tailwind dashboard
├── demo_app/                  # ScholarshipPortal demo target app (v1 and ?v=2)
└── specs/                     # Saved workflow specifications
```

