"""
FastAPI application for DemoToSkill.
Provides HTTP REST endpoints and Server-Sent Events (SSE) streaming for:
1. Recording sessions (/api/record/*)
2. Workflow compilation and review (/api/compile/*)
3. Workflow execution and healing (/api/run/*)
4. Historical specs and run traces (/api/specs/*, /api/runs/*)
5. Gemma 4 Call Inspector telemetry (/api/gemma/calls)
6. Static screenshots serving (/static/shots/*)
"""

import json
import uuid
import sqlite3
import asyncio
from typing import Optional, Any
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from langgraph.types import Command

from app.config import SHOTS_DIR, SPECS_DIR, DB_PATH, BACKEND_PORT
from app.models import Step, Variable, WorkflowSpec, RowResult, StepResult, GemmaCallLog, CompileState
from app.recorder import PlaywrightRecorder
from app.runner import WorkflowRunner
from app.call_logger import call_logger
from app.graphs import build_compile_graph
from app.exporter import export_standalone_script
from app.nodes.save import persist_run_results_to_sqlite


# In-memory session registries
active_recorders: dict[str, PlaywrightRecorder] = {}
completed_recordings: dict[str, list[Step]] = {}
active_compilations: dict[str, dict[str, Any]] = {}
active_runs: dict[str, dict[str, Any]] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management."""
    print(f"🚀 DemoToSkill Backend running on port {BACKEND_PORT}")
    yield
    # Cleanup any active recorders on shutdown
    for rec in list(active_recorders.values()):
        try:
            await rec.stop()
        except Exception:
            pass
    active_recorders.clear()


app = FastAPI(
    title="DemoToSkill API",
    description="Autonomous web skill synthesizer and self-healing executor powered by Gemma 4",
    version="0.1.0",
    lifespan=lifespan
)

# Enable CORS for frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve generated screenshot images statically
app.mount("/static/shots", StaticFiles(directory=str(SHOTS_DIR)), name="shots")


# ---------------------------------------------------------------------------
# Request / Response Schemas
# ---------------------------------------------------------------------------

class RecordStartRequest(BaseModel):
    start_url: str
    headed: bool = True

class RecordStopRequest(BaseModel):
    recording_id: str

class CompileStartRequest(BaseModel):
    recording_id: str

class CompileApproveRequest(BaseModel):
    name: Optional[str] = None
    variables: Optional[list[Variable]] = None
    steps: Optional[list[Step]] = None

class RunStartRequest(BaseModel):
    spec_id: str
    rows: list[dict[str, Any]]
    headed: bool = False


# ---------------------------------------------------------------------------
# Health & Telemetry Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "version": "0.1.0"}


@app.get("/api/gemma/calls", response_model=list[GemmaCallLog])
async def get_gemma_calls(limit: int = 50):
    """Returns recent Gemma 4 calls for the UI Call Inspector."""
    return call_logger.get_recent_calls(limit=limit)


# ---------------------------------------------------------------------------
# Recording Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/record/start")
async def start_recording(req: RecordStartRequest):
    """Starts a new browser recording session."""
    recorder = PlaywrightRecorder()
    rec_id = recorder.recording_id
    active_recorders[rec_id] = recorder

    try:
        await recorder.start(start_url=req.start_url, headed=req.headed)
    except Exception as e:
        active_recorders.pop(rec_id, None)
        raise HTTPException(status_code=500, detail=f"Failed to start recording: {str(e)}")

    return {
        "recording_id": rec_id,
        "status": "recording",
        "start_url": req.start_url
    }


@app.post("/api/record/stop")
async def stop_recording(req: RecordStopRequest):
    """Stops an active recording session and returns coalesced steps."""
    recorder = active_recorders.pop(req.recording_id, None)
    if not recorder:
        raise HTTPException(status_code=404, detail="Recording session not found or already stopped")

    try:
        final_steps = await recorder.stop()
        completed_recordings[req.recording_id] = final_steps
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to cleanly stop recorder: {str(e)}")

    return {
        "recording_id": req.recording_id,
        "step_count": len(final_steps),
        "steps": [s.model_dump() for s in final_steps]
    }


@app.get("/api/record/events")
async def stream_record_events(request: Request, id: str = Query(..., description="Recording session ID")):
    """Server-Sent Events (SSE) stream broadcasting live recorded steps."""
    recorder = active_recorders.get(id)
    if not recorder:
        raise HTTPException(status_code=404, detail="Recording session not found")

    event_queue = recorder.subscribe()

    async def sse_generator():
        try:
            yield f"event: connected\ndata: {json.dumps({'recording_id': id})}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=1.0)
                    yield f"event: {event.get('type', 'step_recorded')}\ndata: {json.dumps(event)}\n\n"
                    if event.get("type") == "recording_stopped":
                        break
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            recorder.unsubscribe(event_queue)

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


# ---------------------------------------------------------------------------
# Compilation Endpoints & Thread Worker
# ---------------------------------------------------------------------------

def _run_compile_thread_worker(compile_id: str, graph: Any, config: dict, initial_state: dict, event_queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
    """Executes the compile graph synchronously inside a worker thread to ensure complete interrupt compatibility."""
    session = active_compilations[compile_id]
    try:
        loop.call_soon_threadsafe(event_queue.put_nowait, {"type": "compile_started", "compile_id": compile_id})

        for chunk in graph.stream(initial_state, config=config):
            for node_name, update in chunk.items():
                if node_name == "__interrupt__":
                    continue
                spec_dump = None
                if isinstance(update, dict) and update.get("spec"):
                    spec_dump = update["spec"].model_dump() if hasattr(update["spec"], "model_dump") else update["spec"]
                status_str = update.get("status", "running") if isinstance(update, dict) else "running"

                loop.call_soon_threadsafe(
                    event_queue.put_nowait,
                    {
                        "type": "node_update",
                        "node": node_name,
                        "status": status_str,
                        "spec": spec_dump
                    }
                )

        state_snapshot = graph.get_state(config)
        session["state"] = state_snapshot.values

        if state_snapshot.next:
            next_node = state_snapshot.next[0]
            session["status"] = "review_pending"
            interrupt_val = state_snapshot.tasks[0].interrupts[0].value if state_snapshot.tasks and state_snapshot.tasks[0].interrupts else {}
            loop.call_soon_threadsafe(
                event_queue.put_nowait,
                {
                    "type": "interrupt",
                    "node": next_node,
                    "payload": interrupt_val
                }
            )
        else:
            session["status"] = "completed"
            spec_obj = session["state"].get("spec")
            loop.call_soon_threadsafe(
                event_queue.put_nowait,
                {
                    "type": "compile_completed",
                    "spec": spec_obj.model_dump() if hasattr(spec_obj, "model_dump") else spec_obj
                }
            )
    except Exception as e:
        session["status"] = "failed"
        session["error"] = str(e)
        loop.call_soon_threadsafe(event_queue.put_nowait, {"type": "compile_error", "error": str(e)})


@app.post("/api/compile")
async def start_compilation(req: CompileStartRequest):
    """Starts the LangGraph Compile Graph for a completed recording session."""
    raw_steps = completed_recordings.get(req.recording_id)
    if not raw_steps:
        rec = active_recorders.get(req.recording_id)
        if rec and not rec.is_active:
            raw_steps = await rec.stop()
            completed_recordings[req.recording_id] = raw_steps
        else:
            raise HTTPException(status_code=400, detail="Recording ID has no completed steps to compile")

    compile_id = f"cmp_{uuid.uuid4().hex[:8]}"
    thread_id = f"thread_{compile_id}"
    event_queue = asyncio.Queue()

    graph = build_compile_graph()
    config = {"configurable": {"thread_id": thread_id}}

    initial_state = {
        "recording_id": req.recording_id,
        "raw_steps": raw_steps,
        "intents_approved": False,
        "repairs_count": 0,
        "status": "understanding"
    }

    active_compilations[compile_id] = {
        "compile_id": compile_id,
        "graph": graph,
        "config": config,
        "event_queue": event_queue,
        "status": "understanding",
        "state": initial_state
    }

    loop = asyncio.get_running_loop()
    asyncio.create_task(
        asyncio.to_thread(
            _run_compile_thread_worker,
            compile_id,
            graph,
            config,
            initial_state,
            event_queue,
            loop
        )
    )

    return {
        "compile_id": compile_id,
        "status": "understanding",
        "recording_id": req.recording_id
    }


@app.get("/api/compile/{id}/events")
async def stream_compile_events(request: Request, id: str):
    """Server-Sent Events (SSE) stream for compilation progress and interrupt events."""
    session = active_compilations.get(id)
    if not session:
        raise HTTPException(status_code=404, detail="Compilation session not found")

    event_queue: asyncio.Queue = session["event_queue"]

    async def sse_generator():
        try:
            yield f"event: connected\ndata: {json.dumps({'compile_id': id, 'status': session['status']})}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=1.0)
                    event_type = event.get("type", "compile_progress")
                    yield f"event: {event_type}\ndata: {json.dumps(event)}\n\n"
                    if event_type in ("compile_completed", "compile_error"):
                        break
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            pass

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.post("/api/compile/{id}/approve")
async def approve_compilation(id: str, req: CompileApproveRequest):
    """Resumes compilation graph execution past the review_intents interrupt."""
    session = active_compilations.get(id)
    if not session:
        raise HTTPException(status_code=404, detail="Compilation session not found")

    graph = session["graph"]
    config = session["config"]
    event_queue: asyncio.Queue = session["event_queue"]

    resume_payload = {}
    if req.name:
        resume_payload["name"] = req.name
    if req.variables is not None:
        resume_payload["variables"] = [v.model_dump() for v in req.variables]
    if req.steps is not None:
        resume_payload["steps"] = [s.model_dump() for s in req.steps]

    def _resume_sync_worker(loop):
        try:
            loop.call_soon_threadsafe(event_queue.put_nowait, {"type": "review_approved", "compile_id": id})
            for chunk in graph.stream(Command(resume=resume_payload), config=config):
                for node_name, update in chunk.items():
                    if node_name == "__interrupt__":
                        continue
                    spec_dump = None
                    if isinstance(update, dict) and update.get("spec"):
                        spec_dump = update["spec"].model_dump() if hasattr(update["spec"], "model_dump") else update["spec"]
                    status_str = update.get("status", "running") if isinstance(update, dict) else "running"

                    loop.call_soon_threadsafe(
                        event_queue.put_nowait,
                        {
                            "type": "node_update",
                            "node": node_name,
                            "status": status_str,
                            "spec": spec_dump
                        }
                    )

            state_snapshot = graph.get_state(config)
            session["state"] = state_snapshot.values
            session["status"] = "completed"
            spec_obj = session["state"].get("spec")
            loop.call_soon_threadsafe(
                event_queue.put_nowait,
                {
                    "type": "compile_completed",
                    "spec": spec_obj.model_dump() if hasattr(spec_obj, "model_dump") else spec_obj
                }
            )
        except Exception as e:
            session["status"] = "failed"
            loop.call_soon_threadsafe(event_queue.put_nowait, {"type": "compile_error", "error": str(e)})

    loop = asyncio.get_running_loop()
    asyncio.create_task(asyncio.to_thread(_resume_sync_worker, loop))

    return {
        "compile_id": id,
        "status": "resumed"
    }


# ---------------------------------------------------------------------------
# Execution (Run) Endpoints
# ---------------------------------------------------------------------------

async def _run_batch_worker(run_id: str, spec: WorkflowSpec, rows: list[dict[str, Any]], headed: bool, event_queue: asyncio.Queue):
    """Executes batch workflow runs asynchronously while broadcasting row/step progress to SSE."""
    session = active_runs[run_id]
    runner = WorkflowRunner(run_id=run_id)

    async def on_step(row_idx: int, step_idx: int, res: StepResult):
        await event_queue.put({
            "type": "step_progress",
            "run_id": run_id,
            "row_idx": row_idx,
            "step_idx": step_idx,
            "ok": res.ok,
            "error": res.error,
            "duration_ms": res.duration_ms
        })

    try:
        await event_queue.put({"type": "run_started", "run_id": run_id, "total_rows": len(rows)})

        results = await runner.execute_batch(
            spec=spec,
            rows=rows,
            headed=headed,
            on_step_progress=on_step
        )

        session["results"] = results
        all_ok = all(r.success for r in results)
        session["status"] = "completed" if all_ok else "failed"

        # Persist run results to SQLite
        persist_run_results_to_sqlite(
            run_id=run_id,
            spec_id=spec.id or "custom",
            status=session["status"],
            results=results
        )

        await event_queue.put({
            "type": "run_completed",
            "run_id": run_id,
            "status": session["status"],
            "total_rows": len(rows),
            "passed_rows": sum(1 for r in results if r.success),
            "results": [r.model_dump() for r in results]
        })

    except Exception as e:
        session["status"] = "failed"
        session["error"] = str(e)
        await event_queue.put({"type": "run_error", "run_id": run_id, "error": str(e)})


@app.post("/api/run")
async def start_run(req: RunStartRequest):
    """Starts batch execution of a compiled WorkflowSpec over multiple rows."""
    spec_data = await get_spec(req.spec_id)
    spec_obj = WorkflowSpec.model_validate(spec_data)

    run_id = f"run_{uuid.uuid4().hex[:8]}"
    event_queue = asyncio.Queue()

    active_runs[run_id] = {
        "run_id": run_id,
        "spec_id": req.spec_id,
        "status": "running",
        "rows": req.rows,
        "results": [],
        "event_queue": event_queue
    }

    asyncio.create_task(
        _run_batch_worker(
            run_id=run_id,
            spec=spec_obj,
            rows=req.rows,
            headed=req.headed,
            event_queue=event_queue
        )
    )

    return {
        "run_id": run_id,
        "spec_id": req.spec_id,
        "status": "running",
        "row_count": len(req.rows)
    }


@app.get("/api/run/{id}/events")
async def stream_run_events(request: Request, id: str):
    """Server-Sent Events (SSE) stream for batch execution progress."""
    session = active_runs.get(id)
    if not session:
        raise HTTPException(status_code=404, detail="Run session not found")

    event_queue: asyncio.Queue = session["event_queue"]

    async def sse_generator():
        try:
            yield f"event: connected\ndata: {json.dumps({'run_id': id, 'status': session['status']})}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=1.0)
                    event_type = event.get("type", "run_progress")
                    yield f"event: {event_type}\ndata: {json.dumps(event)}\n\n"
                    if event_type in ("run_completed", "run_error"):
                        break
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            pass

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.get("/api/runs")
async def list_runs():
    """Returns historical execution runs from SQLite."""
    runs_list = []
    if DB_PATH.exists():
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS runs (
                        id TEXT PRIMARY KEY,
                        spec_id TEXT NOT NULL,
                        status TEXT NOT NULL,
                        results_json TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("SELECT id, spec_id, status, results_json, created_at FROM runs ORDER BY created_at DESC")
                for row in cursor.fetchall():
                    runs_list.append({
                        "id": row["id"],
                        "spec_id": row["spec_id"],
                        "status": row["status"],
                        "results": json.loads(row["results_json"]),
                        "created_at": row["created_at"]
                    })
        except Exception as e:
            print(f"[Main] Error reading runs: {e}")
    return runs_list


@app.get("/api/runs/{id}")
async def get_run(id: str):
    """Retrieves execution details for a specific run ID."""
    session = active_runs.get(id)
    if session:
        return {
            "id": id,
            "spec_id": session["spec_id"],
            "status": session["status"],
            "results": [r.model_dump() if hasattr(r, "model_dump") else r for r in session["results"]]
        }

    if DB_PATH.exists():
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT id, spec_id, status, results_json, created_at FROM runs WHERE id = ?", (id,))
            row = cursor.fetchone()
            if row:
                return {
                    "id": row["id"],
                    "spec_id": row["spec_id"],
                    "status": row["status"],
                    "results": json.loads(row["results_json"]),
                    "created_at": row["created_at"]
                }

    raise HTTPException(status_code=404, detail=f"Run record {id} not found")


# ---------------------------------------------------------------------------
# Workflow Spec Inspection & Export Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/specs")
async def list_specs():
    """Returns all compiled WorkflowSpec records from SQLite."""
    specs_list = []
    if DB_PATH.exists():
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("SELECT id, name, start_url, spec_json, created_at FROM specs ORDER BY created_at DESC")
                for row in cursor.fetchall():
                    specs_list.append(json.loads(row["spec_json"]))
        except Exception as e:
            print(f"[Main] Error reading specs from DB: {e}")
    return specs_list


@app.get("/api/specs/{id}")
async def get_spec(id: str):
    """Retrieves a single WorkflowSpec by ID."""
    spec_file = SPECS_DIR / f"{id}.json"
    if spec_file.exists():
        try:
            with open(spec_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    if DB_PATH.exists():
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT spec_json FROM specs WHERE id = ?", (id,))
            row = cursor.fetchone()
            if row:
                return json.loads(row["spec_json"])

    raise HTTPException(status_code=404, detail=f"Specification {id} not found")


@app.get("/api/specs/{id}/export")
async def export_spec_script(id: str):
    """Exports WorkflowSpec alongside an executable standalone Playwright Python script."""
    spec_data = await get_spec(id)
    spec_obj = WorkflowSpec.model_validate(spec_data)
    script_str = export_standalone_script(spec_obj)

    return {
        "spec_id": id,
        "spec": spec_data,
        "playwright_script": script_str
    }
