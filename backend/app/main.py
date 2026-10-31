"""
FastAPI application for DemoToSkill.
Provides HTTP REST endpoints and Server-Sent Events (SSE) streaming for:
1. Recording sessions (/api/record/*)
2. Workflow compilation and review (/api/compile/*)
3. Workflow execution and healing (/api/run/*)
4. Gemma 4 Call Inspector telemetry (/api/gemma/calls)
5. Static screenshots serving (/static/shots/*)
"""

import json
import asyncio
from typing import Optional, Any
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import SHOTS_DIR, BACKEND_PORT
from app.models import Step, GemmaCallLog
from app.recorder import PlaywrightRecorder
from app.call_logger import call_logger


# In-memory session registries
active_recorders: dict[str, PlaywrightRecorder] = {}
completed_recordings: dict[str, list[Step]] = {}


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

    # Start browser session asynchronously
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
            # Yield initial connection confirmation
            yield f"event: connected\ndata: {json.dumps({'recording_id': id})}\n\n"

            while True:
                # Check for client disconnect
                if await request.is_disconnected():
                    break

                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=1.0)
                    yield f"event: {event.get('type', 'step_recorded')}\ndata: {json.dumps(event)}\n\n"
                    if event.get("type") == "recording_stopped":
                        break
                except asyncio.TimeoutError:
                    # Keep-alive heartbeat comment
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
