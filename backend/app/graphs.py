"""
LangGraph workflow graphs for DemoToSkill.
Defines:
1. Compile Graph: processes recording -> understand -> review_intents (interrupt) -> compile_spec -> trial_run -> verify -> repair -> save.
2. Run Graph: executes saved spec -> batch run_rows -> heal -> review_heal -> patch_spec -> report.
Both graphs share MemorySaver checkpointers and state models.
"""

from typing import Optional, Any
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from app.models import CompileState, RunState
from app.nodes.understand import understand_node
from app.nodes.review import review_intents_node
from app.nodes.compile_spec import compile_spec_node

MAX_REPAIRS = 2


# ---------------------------------------------------------------------------
# Phase 3 / Phase 4 Bridge Placeholders
# (trial_run, verify, repair, save will be fully populated in Phase 4 & 5)
# ---------------------------------------------------------------------------

def trial_run_node(state: CompileState) -> dict[str, Any]:
    """Trial run execution node across test rows (Bridge to Phase 4)."""
    results = state.get("results") or []
    return {
        "results": results,
        "status": "testing"
    }


def verify_node(state: CompileState) -> dict[str, Any]:
    """Verification node evaluating deterministic + visual success criteria (Bridge to Phase 4)."""
    return {
        "status": "verifying"
    }


def repair_node(state: CompileState) -> dict[str, Any]:
    """Repair node utilizing Set-of-Marks visual prompt (Bridge to Phase 5)."""
    repairs = state.get("repairs_count", 0) + 1
    return {
        "repairs_count": repairs,
        "status": "repairing"
    }


def save_node(state: CompileState) -> dict[str, Any]:
    """Save finalized workflow to SQLite and export (Bridge to Phase 4/5)."""
    return {
        "status": "saved"
    }


def route_after_verify(state: CompileState) -> str:
    """Conditional edge routing: retries repair if failures occurred and retries < MAX_REPAIRS."""
    results = state.get("results") or []
    repairs = state.get("repairs_count", 0)
    failed = [r for r in results if not r.success]
    if failed and repairs < MAX_REPAIRS:
        return "repair"
    return "save"


# ---------------------------------------------------------------------------
# Compile Graph Construction
# ---------------------------------------------------------------------------

def build_compile_graph(checkpointer: Optional[Any] = None):
    """
    Constructs and compiles the LangGraph Compile Graph.
    Uses MemorySaver checkpointer for state persistence and human-in-the-loop review interrupts.
    """
    chk = checkpointer if checkpointer is not None else MemorySaver()
    builder = StateGraph(CompileState)

    # Register nodes (all synchronous for full cross-version & Windows compatibility)
    builder.add_node("understand", understand_node)
    builder.add_node("review_intents", review_intents_node)  # Interrupts for human confirmation
    builder.add_node("compile_spec", compile_spec_node)
    builder.add_node("trial_run", trial_run_node)
    builder.add_node("verify", verify_node)
    builder.add_node("repair", repair_node)
    builder.add_node("save", save_node)

    # Register edges
    builder.add_edge(START, "understand")
    builder.add_edge("understand", "review_intents")
    builder.add_edge("review_intents", "compile_spec")
    builder.add_edge("compile_spec", "trial_run")
    builder.add_edge("trial_run", "verify")
    builder.add_conditional_edges("verify", route_after_verify, {"repair": "repair", "save": "save"})
    builder.add_edge("repair", "trial_run")
    builder.add_edge("save", END)

    return builder.compile(checkpointer=chk)


# Global default compile graph instance
compile_graph = build_compile_graph()
