"""
Trial Run Node for DemoToSkill Compile Graph.
Executes the compiled WorkflowSpec across synthetic trial rows
using WorkflowRunner to prove generalization before final persistence.
"""

import asyncio
from typing import Any

from app.models import CompileState, WorkflowSpec, RowResult
from app.runner import WorkflowRunner


async def _async_trial_run(spec: WorkflowSpec, rows: list[dict[str, Any]], recording_id: str) -> list[RowResult]:
    """Runs WorkflowRunner across trial rows in headless mode."""
    runner = WorkflowRunner(run_id=f"trial_{recording_id}")
    results = await runner.execute_batch(
        spec=spec,
        rows=rows,
        headed=False
    )
    return results


def trial_run_node(state: CompileState) -> dict[str, Any]:
    """
    LangGraph Compile Graph node: 'trial_run'.
    Executes the spec across trial_rows.
    """
    # If trial results are already supplied (e.g. mock or pre-evaluated), pass through
    if state.get("results"):
        return {"results": state["results"], "status": "testing"}

    spec: WorkflowSpec = state.get("spec")
    trial_rows: list[dict[str, Any]] = state.get("trial_rows") or []
    rec_id = state.get("recording_id", "draft")

    if not spec:
        return {"status": "failed", "error": "No compiled spec found for trial run"}

    # If no trial rows, use empty row
    if not trial_rows:
        trial_rows = [{}]

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, _async_trial_run(spec, trial_rows, rec_id))
                results = future.result()
        else:
            results = loop.run_until_complete(_async_trial_run(spec, trial_rows, rec_id))
    except RuntimeError:
        results = asyncio.run(_async_trial_run(spec, trial_rows, rec_id))

    return {
        "results": results,
        "status": "testing"
    }
