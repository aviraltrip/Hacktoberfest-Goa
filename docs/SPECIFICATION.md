# DemoToSkill: Data Models & API Specification

## 1. Core Data Models (`backend/app/models.py`)

All core data structures are strictly typed using Pydantic v2.

```python
from typing import Literal, Optional, Any
from pydantic import BaseModel, Field

class Locator(BaseModel):
    kind: Literal['role', 'label', 'placeholder', 'text', 'testid', 'css']
    value: str
    name: Optional[str] = None  # Accessible name for 'role' locators (e.g. name='Submit')

class Step(BaseModel):
    idx: int
    action: Literal['goto', 'click', 'fill', 'select', 'check', 'press']
    locators: list[Locator] = []    # Evaluated sequentially; first with count == 1 wins
    value: Optional[str] = None     # Literal string or '{{var_name}}' template
    intent: str = ''                # Human/Gemma-inferred semantic intention
    shot_before: str = ''           # Filepath or base64 thumbnail before action
    shot_after: str = ''            # Filepath or base64 thumbnail after settle
    dom_context: str = ''           # Outer HTML of target + immediate parent (~400 chars)

class Variable(BaseModel):
    name: str                       # e.g. "applicant_name"
    type: Literal['text', 'select', 'date', 'number']
    example: str                    # Value observed during the recording
    options: list[str] = []         # For select dropdowns (scraped from DOM)

class SuccessCondition(BaseModel):
    text_visible: Optional[str] = None   # Deterministic: string visible on target page
    url_contains: Optional[str] = None   # Deterministic: substring inside current URL
    visual: str                          # Evaluated by Gemma 4 vision on final screenshot

class WorkflowSpec(BaseModel):
    id: Optional[str] = None
    name: str
    start_url: str
    variables: list[Variable] = []
    steps: list[Step] = []
    success: SuccessCondition

class StepResult(BaseModel):
    idx: int
    ok: bool
    error: Optional[str] = None
    shot: Optional[str] = None
    resolved_locator: Optional[Locator] = None
    duration_ms: Optional[float] = None

class RowResult(BaseModel):
    row_idx: int
    row_data: dict[str, Any]
    steps: list[StepResult] = []
    success: Optional[bool] = None
    evidence: Optional[str] = None
    final_shot: Optional[str] = None

# Candidate Extraction & Healing
class CandidateElement(BaseModel):
    id: int                         # Numeric marker [1..8]
    tag: str                        # 'button', 'input', etc.
    role: Optional[str] = None
    text: Optional[str] = None
    aria_label: Optional[str] = None
    placeholder: Optional[str] = None
    id_attr: Optional[str] = None
    classes: list[str] = []
    bbox: dict[str, float]          # {x, y, width, height}
    bm25_score: float = 0.0

class HealProposal(BaseModel):
    step_idx: int
    choice: Optional[int]           # Index matching CandidateElement.id
    confidence: float
    reason: str
    marked_shot: str                # Filepath to screenshot with numbered badges
    original_shot: str              # Original shot_before
    candidate: Optional[CandidateElement] = None
    proposed_locator: Optional[Locator] = None

# Gemma Call Inspector
class GemmaCallLog(BaseModel):
    id: str
    timestamp: str
    endpoint: Literal['understand_step', 'understand_workflow', 'heal_choice', 'verify_visual']
    model: str
    prompt_summary: str
    image_paths: list[str] = []
    response_raw: str
    parsed_json: Optional[dict[str, Any]] = None
    latency_ms: float
    status: Literal['success', 'retry', 'error']
    error: Optional[str] = None
```

---

## 2. LangGraph State Schemas

```python
from typing import TypedDict, Optional, Any

class CompileState(TypedDict):
    recording_id: str
    raw_steps: list[Step]
    intents_approved: bool
    spec: Optional[WorkflowSpec]
    trial_rows: list[dict[str, Any]]
    results: list[RowResult]
    repairs_count: int
    status: Literal['idle', 'understanding', 'review_pending', 'compiling', 'testing', 'verifying', 'repairing', 'saved', 'failed']
    error: Optional[str]

class RunState(TypedDict):
    run_id: str
    spec_id: str
    spec: WorkflowSpec
    rows: list[dict[str, Any]]
    current_row_idx: int
    results: list[RowResult]
    failed_step: Optional[Step]
    heal_proposal: Optional[HealProposal]
    heal_approved: bool
    status: Literal['running', 'heal_pending', 'patched', 'completed', 'failed']
```

---

## 3. REST API Contract

### Recording Endpoints
- **`POST /api/record/start`**
  - **Body**: `{"start_url": "http://localhost:8000/demo_app"}`
  - **Returns**: `{"recording_id": "rec_123", "status": "recording"}`
- **`POST /api/record/stop`**
  - **Body**: `{"recording_id": "rec_123"}`
  - **Returns**: `{"recording_id": "rec_123", "step_count": 5, "raw_steps": [...]}`
- **`GET /api/record/events?id=rec_123`**
  - **Type**: `text/event-stream` (SSE)
  - **Stream Data**: Live steps captured with action, target tag, and thumbnail URL.

### Compilation Endpoints
- **`POST /api/compile`**
  - **Body**: `{"recording_id": "rec_123"}`
  - **Returns**: `{"compile_id": "cmp_456", "status": "understanding"}`
- **`GET /api/compile/{id}/events`**
  - **Type**: `text/event-stream` (SSE)
  - **Stream Data**: Emits node lifecycle events (`node_start`, `node_end`, `interrupt_review_intents`, `trial_run_step`, `verify_result`).
- **`POST /api/compile/{id}/approve`**
  - **Body**: `{"approved_spec": WorkflowSpec}` (User modifications to variables or intents)
  - **Returns**: `{"status": "resumed"}`

### Execution Endpoints
- **`POST /api/run`**
  - **Body**: `{"spec_id": "spec_789", "rows": [{"name": "Alice", "dept": "CS"}]}`
  - **Returns**: `{"run_id": "run_001", "status": "running"}`
- **`GET /api/run/{id}/events`**
  - **Type**: `text/event-stream` (SSE)
  - **Stream Data**: Emits step execution progress, cell status (green/red), and heal interrupts.
- **`POST /api/run/{id}/approve_heal`**
  - **Body**: `{"approved": true, "override_choice": null}`
  - **Returns**: `{"status": "resumed"}`

### Specs & Inspection
- **`GET /api/specs`**
  - **Returns**: `list[WorkflowSpec]`
- **`GET /api/specs/{id}/export`**
  - **Returns**: `{"spec": WorkflowSpec, "playwright_script": "async def run(): ..."}`
- **`GET /api/gemma/calls`**
  - **Returns**: `list[GemmaCallLog]` (Powers the live Gemma Call Inspector drawer)

---

## 4. Server-Sent Events (SSE) Protocol

SSE messages are JSON formatted with event identifiers:

```json
event: step_recorded
data: {
  "idx": 2,
  "action": "fill",
  "value": "Alice Smith",
  "shot_before": "/static/shots/rec_123_step_2_before.jpg",
  "selector_summary": "input#fullName"
}

event: compile_progress
data: {
  "node": "understand",
  "step_idx": 2,
  "intent": "Enter the applicant's full legal name",
  "is_variable": true,
  "variable_name": "applicant_name"
}

event: heal_required
data: {
  "step_idx": 4,
  "action": "click",
  "intent": "Submit the scholarship application",
  "choice": 3,
  "confidence": 0.94,
  "reason": "Candidate 3 has an upload/send paper plane icon within a submit-style button container in the newly introduced footer bar",
  "marked_shot": "/static/shots/heal_run_001_marked.jpg"
}
```

---

## 5. Database Schema (`backend/app/memory.py`)

Using SQLite3 with native JSON1 and FTS5 extensions:

```sql
-- Workflow Specifications
CREATE TABLE IF NOT EXISTS specs (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    start_url TEXT NOT NULL,
    spec_json TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Execution Runs
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    spec_id TEXT NOT NULL,
    status TEXT NOT NULL,
    results_json TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(spec_id) REFERENCES specs(id)
);

-- Gemma Call Logs
CREATE TABLE IF NOT EXISTS gemma_calls (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_summary TEXT NOT NULL,
    image_paths TEXT NOT NULL,
    response_raw TEXT NOT NULL,
    latency_ms REAL NOT NULL,
    status TEXT NOT NULL
);

-- Vectorless Heal Memory with SQLite FTS5
CREATE TABLE IF NOT EXISTS heals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site TEXT NOT NULL,
    intent TEXT NOT NULL,
    old_locator TEXT NOT NULL,
    new_locator TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE VIRTUAL TABLE IF NOT EXISTS heals_fts USING fts5(
    intent,
    content='heals',
    content_rowid='id'
);
```
