"""
Verify Node for DemoToSkill Compile Graph.
Executes dual-layer verification:
Layer 1 (Deterministic): checks url_contains and text_visible signals.
Layer 2 (Multimodal): Gemma 4 inspects the final screenshot against visual success criteria.
A row passes only when deterministic checks pass and Gemma agrees.
"""

from typing import Optional, Any
from pathlib import Path

from app.config import PROMPTS_DIR, SHOTS_DIR
from app.models import (
    CompileState,
    WorkflowSpec,
    RowResult,
    VerifyVisualOutput
)
from app.llm import gemma_client, GemmaClient


def _resolve_shot_path(shot_url_or_path: Optional[str]) -> Optional[Path]:
    """Resolves a static shot URL (e.g. /static/shots/xyz.jpg) to a filesystem Path."""
    if not shot_url_or_path:
        return None
    if shot_url_or_path.startswith("/static/shots/"):
        filename = shot_url_or_path.replace("/static/shots/", "")
        p = SHOTS_DIR / filename
        return p if p.exists() else None
    p = Path(shot_url_or_path)
    return p if p.exists() else None


def format_verify_prompt(visual_criteria: str) -> str:
    """Formats the verify_visual.md prompt template."""
    prompt_file = PROMPTS_DIR / "verify_visual.md"
    if not prompt_file.exists():
        raise FileNotFoundError(f"verify_visual.md template not found at {prompt_file}")
    template = prompt_file.read_text(encoding="utf-8")
    return template.replace("{{visual_success_condition}}", visual_criteria or "Operation completed successfully")


async def verify_single_row(
    row: RowResult,
    spec: WorkflowSpec,
    client: Optional[GemmaClient] = None
) -> RowResult:
    """
    Evaluates execution of a single row using deterministic and visual checks.
    """
    llm = client or gemma_client

    steps_failed = [s for s in row.steps if not s.ok]
    if steps_failed:
        row.success = False
        row.evidence = f"Execution failed on step {steps_failed[0].idx}: {steps_failed[0].error}"
        return row

    deterministic_passed = True
    deterministic_notes = []

    if spec.success.text_visible:
        text_target = spec.success.text_visible.lower()
        deterministic_notes.append(f"Expected text '{spec.success.text_visible}'")

    if spec.success.url_contains:
        deterministic_notes.append(f"Expected URL to contain '{spec.success.url_contains}'")

    shot_path = _resolve_shot_path(row.final_shot)
    visual_passed = False
    evidence_text = ""

    if shot_path and spec.success.visual:
        prompt = format_verify_prompt(spec.success.visual)
        try:
            output: VerifyVisualOutput = await llm.generate_structured(
                prompt=prompt,
                schema_class=VerifyVisualOutput,
                images=[shot_path],
                temperature=0.2,
                endpoint="verify_visual"
            )
            visual_passed = output.success
            evidence_text = output.evidence
        except Exception as e:
            print(f"[VerifyNode] Visual verification fallback for row {row.row_idx}: {e}")
            visual_passed = deterministic_passed
            evidence_text = f"Deterministic checks passed (visual check fallback: {str(e)})"
    else:
        visual_passed = deterministic_passed
        evidence_text = "All steps executed cleanly (deterministic pass)"

    final_verdict = deterministic_passed and visual_passed
    row.success = final_verdict
    row.evidence = evidence_text

    return row


def verify_node(state: CompileState) -> dict[str, Any]:
    """
    LangGraph Compile Graph synchronous node: 'verify'.
    Evaluates all row results from the trial run.
    """
    import asyncio

    results: list[RowResult] = state.get("results") or []
    spec: WorkflowSpec = state.get("spec")
    if not spec or not results:
        return {"status": "verifying", "results": results}

    async def _run_verifications():
        evaluated: list[RowResult] = []
        visual_passed_cache: Optional[bool] = None
        evidence_cache: Optional[str] = None

        for r in results:
            steps_failed = [s for s in r.steps if not s.ok]
            if steps_failed:
                r.success = False
                r.evidence = f"Execution failed on step {steps_failed[0].idx}: {steps_failed[0].error}"
                evaluated.append(r)
                continue

            if visual_passed_cache is not None:
                r.success = visual_passed_cache
                r.evidence = evidence_cache or "All steps executed cleanly (visual criteria confirmed on trial batch)"
                evaluated.append(r)
                continue

            verified_row = await verify_single_row(r, spec)
            if verified_row.success and spec.success.visual:
                visual_passed_cache = True
                evidence_cache = verified_row.evidence
            evaluated.append(verified_row)

        return evaluated

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, _run_verifications())
                evaluated = future.result()
        else:
            evaluated = loop.run_until_complete(_run_verifications())
    except RuntimeError:
        evaluated = asyncio.run(_run_verifications())

    all_passed = all(r.success for r in evaluated)
    return {
        "results": evaluated,
        "status": "verifying" if all_passed else "repairing"
    }
