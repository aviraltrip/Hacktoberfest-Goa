"""
Review Node for DemoToSkill Compile Graph.
Implements human-in-the-loop review of inferred intents and parameter schema
using LangGraph interrupt mechanisms.
"""

from typing import Any
from langgraph.types import interrupt

from app.models import CompileState, WorkflowSpec, Variable, Step


def review_intents_node(state: CompileState) -> dict[str, Any]:
    """
    LangGraph node: 'review_intents'.
    Interrupts execution and waits for human confirmation or modification of variables and intents.
    When resumed with Command(resume=payload), payload updates the draft spec.
    """
    # If already approved (e.g. auto-approve mode or resumed), bypass interrupt
    if state.get("intents_approved"):
        return {"status": "compiling", "intents_approved": True}

    current_spec: WorkflowSpec = state.get("spec")

    # Present payload for the human review UI
    review_payload = {
        "recording_id": state.get("recording_id"),
        "spec_name": current_spec.name if current_spec else "",
        "variables": [v.model_dump() for v in (current_spec.variables if current_spec else [])],
        "steps": [s.model_dump() for s in (current_spec.steps if current_spec else [])],
        "success": current_spec.success.model_dump() if current_spec else {}
    }

    # LangGraph interrupt: pauses graph execution until Command(resume=...) is provided
    human_input = interrupt(review_payload)

    # When resumed, human_input contains any user overrides
    if isinstance(human_input, dict) and current_spec:
        # Update spec name if modified
        if human_input.get("name"):
            current_spec.name = human_input["name"]

        # Update variables if modified
        if "variables" in human_input:
            current_spec.variables = [
                Variable.model_validate(v) if isinstance(v, dict) else v
                for v in human_input["variables"]
            ]

        # Update steps if modified
        if "steps" in human_input:
            current_spec.steps = [
                Step.model_validate(s) if isinstance(s, dict) else s
                for s in human_input["steps"]
            ]

    return {
        "spec": current_spec,
        "intents_approved": True,
        "status": "compiling"
    }
