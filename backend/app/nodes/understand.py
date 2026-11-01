"""
Understand Node for DemoToSkill Compile Graph.
Executes two Gemma 4 cognitive passes:
Pass 1: Per-step multimodal deduction (intent, variable vs constant, variable name, field type).
Pass 2: Global workflow synthesis (title, variable schema with select options, dual success criteria).
"""

import json
import asyncio
from pathlib import Path
from typing import Optional, Any

from app.config import PROMPTS_DIR, SHOTS_DIR
from app.models import (
    Step,
    Variable,
    SuccessCondition,
    WorkflowSpec,
    CompileState,
    UnderstandStepOutput,
    UnderstandWorkflowOutput
)
from app.llm import gemma_client, GemmaClient


def _resolve_image_path(shot_url_or_path: str) -> Optional[Path]:
    """Resolves a static shot URL (e.g. /static/shots/xyz.jpg) or local path to a filesystem Path."""
    if not shot_url_or_path:
        return None

    if shot_url_or_path.startswith("/static/shots/"):
        filename = shot_url_or_path.replace("/static/shots/", "")
        p = SHOTS_DIR / filename
        return p if p.exists() else None

    p = Path(shot_url_or_path)
    if p.exists():
        return p

    p_shots = SHOTS_DIR / shot_url_or_path
    if p_shots.exists():
        return p_shots

    return None


def load_prompt_template(filename: str) -> str:
    """Loads a prompt template markdown file from prompts directory."""
    path = PROMPTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Prompt template {filename} not found at {path}")
    return path.read_text(encoding="utf-8")


def format_step_prompt(
    action: str,
    observed_value: str,
    dom_context: str,
    previous_intent: str = ""
) -> str:
    """Formats the understand_step.md prompt with step context."""
    template = load_prompt_template("understand_step.md")
    replacements = {
        "{{previous_intent}}": previous_intent or "None (initial step)",
        "{{action}}": action,
        "{{observed_value}}": observed_value or "",
        "{{dom_context}}": dom_context or "No DOM snippet captured"
    }
    prompt = template
    for placeholder, val in replacements.items():
        prompt = prompt.replace(placeholder, str(val))
    return prompt


def format_workflow_prompt(
    steps: list[Step],
    select_options: Optional[dict[str, list[str]]] = None
) -> str:
    """Formats the understand_workflow.md prompt with summarized steps and select options."""
    template = load_prompt_template("understand_workflow.md")

    steps_summary = [
        {
            "step": s.idx,
            "action": s.action,
            "intent": s.intent,
            "value_template": s.value,
            "context": s.dom_context[:120] if s.dom_context else ""
        }
        for s in steps
    ]

    replacements = {
        "{{steps_summary_json}}": json.dumps(steps_summary, indent=2),
        "{{dom_select_options_json}}": json.dumps(select_options or {}, indent=2)
    }
    prompt = template
    for placeholder, val in replacements.items():
        prompt = prompt.replace(placeholder, str(val))
    return prompt


async def understand_single_step(
    step: Step,
    previous_intent: str = "",
    client: Optional[GemmaClient] = None
) -> tuple[Step, Optional[Variable]]:
    """
    Pass 1: Analyzes a single recorded step multimodally.
    Deduces intent and determines if observed value should be parameterized.
    """
    llm = client or gemma_client

    if step.action == "goto":
        step.intent = f"Navigate to {step.value or 'target URL'}"
        return step, None

    prompt = format_step_prompt(
        action=step.action,
        observed_value=step.value or "",
        dom_context=step.dom_context,
        previous_intent=previous_intent
    )

    images: list[Path] = []
    after_path = _resolve_image_path(step.shot_after)
    if after_path:
        images.append(after_path)
    elif step.shot_before:
        before_path = _resolve_image_path(step.shot_before)
        if before_path:
            images.append(before_path)

    try:
        output: UnderstandStepOutput = await llm.generate_structured(
            prompt=prompt,
            schema_class=UnderstandStepOutput,
            images=images,
            temperature=0.2,
            endpoint="understand_step"
        )

        step.intent = output.intent
        var_obj = None

        if output.role == "variable" and output.variable_name:
            var_name = output.variable_name.strip()
            example_val = step.value or ""
            step.value = f"{{{{{var_name}}}}}"
            var_obj = Variable(
                name=var_name,
                type=output.field_type or "text",
                example=example_val
            )

        return step, var_obj

    except Exception as e:
        print(f"[UnderstandNode] Step {step.idx} understanding warning: {e}")
        if not step.intent:
            step.intent = f"Perform {step.action} on {step.dom_context[:40]}"
        return step, None


async def understand_workflow_synthesis(
    steps: list[Step],
    final_shot: Optional[str] = None,
    select_options: Optional[dict[str, list[str]]] = None,
    client: Optional[GemmaClient] = None
) -> UnderstandWorkflowOutput:
    """
    Pass 2: Synthesizes overall workflow title, variables, and dual success conditions.
    """
    llm = client or gemma_client
    prompt = format_workflow_prompt(steps, select_options)

    images: list[Path] = []
    final_path = _resolve_image_path(final_shot or (steps[-1].shot_after if steps else ""))
    if final_path:
        images.append(final_path)

    try:
        output: UnderstandWorkflowOutput = await llm.generate_structured(
            prompt=prompt,
            schema_class=UnderstandWorkflowOutput,
            images=images,
            temperature=0.2,
            endpoint="understand_workflow"
        )
        return output
    except Exception as e:
        print(f"[UnderstandNode] Workflow synthesis fallback: {e}")
        return UnderstandWorkflowOutput(
            name="Automated Portal Workflow",
            variables=[],
            success=SuccessCondition(
                text_visible="Application received",
                visual="Confirmation message visible on screen"
            )
        )


async def _async_understand_pipeline(state: CompileState) -> dict[str, Any]:
    """Underlying async execution pipeline for step & workflow understanding."""
    raw_steps = list(state.get("raw_steps") or [])
    if not raw_steps:
        return {"status": "failed", "error": "No raw steps available for understanding"}

    processed_steps: list[Step] = []
    detected_variables: dict[str, Variable] = {}

    steps_needing_analysis: list[Step] = []
    for s in raw_steps:
        if s.action == "goto":
            s.intent = f"Navigate to {s.value or 'target URL'}"
            processed_steps.append(s)
        elif s.action == "click":
            if not s.intent:
                target_desc = s.dom_context[:40] if s.dom_context else "element"
                s.intent = f"Click {target_desc}"
            processed_steps.append(s)
        else:
            steps_needing_analysis.append(s)
            processed_steps.append(s)

    if steps_needing_analysis:
        tasks = [understand_single_step(step=s) for s in steps_needing_analysis]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for res in results:
            if isinstance(res, tuple) and len(res) == 2:
                updated_s, var_obj = res
                if var_obj and var_obj.name not in detected_variables:
                    detected_variables[var_obj.name] = var_obj

    final_shot = processed_steps[-1].shot_after if processed_steps else None
    wf_output = await understand_workflow_synthesis(
        steps=processed_steps,
        final_shot=final_shot
    )

    merged_variables: list[Variable] = list(detected_variables.values())
    for v in wf_output.variables:
        if v.name not in detected_variables:
            merged_variables.append(v)
        else:
            if v.options and not detected_variables[v.name].options:
                detected_variables[v.name].options = v.options

    start_url = processed_steps[0].value if processed_steps and processed_steps[0].action == "goto" else "http://localhost:8080"
    spec = WorkflowSpec(
        id=f"spec_{state.get('recording_id', 'draft')}",
        name=wf_output.name or "Web Automation Workflow",
        start_url=start_url or "http://localhost:8080",
        variables=merged_variables,
        steps=processed_steps,
        success=wf_output.success
    )

    return {
        "raw_steps": processed_steps,
        "spec": spec,
        "status": "review_pending",
        "intents_approved": False
    }


def understand_node(state: CompileState) -> dict[str, Any]:
    """
    LangGraph Compile Graph synchronous node: 'understand'.
    Runs the multimodal understanding pipeline synchronously to ensure full
    compatibility with LangGraph checkpointer and interrupt mechanisms across Python versions.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, _async_understand_pipeline(state))
                return future.result()
        else:
            return loop.run_until_complete(_async_understand_pipeline(state))
    except RuntimeError:
        return asyncio.run(_async_understand_pipeline(state))
