"""
End-to-End Integration Test Suite for DemoToSkill (Phase 7).
Validates the complete autonomous lifecycle:
1. Recording raw interaction events.
2. Multimodal LangGraph compilation: step understanding, variable extraction, and spec synthesis.
3. Review interrupt and approval.
4. Batch parameter execution and failure detection.
5. Set-of-Marks visual self-healing: candidate extraction, role gate, and locator synthesis.
6. Spec patching and post-repair verified execution.
7. Standalone Python Playwright script export.
"""

import sys
import unittest
from pathlib import Path
from typing import Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
for p in (str(BACKEND_DIR), str(ROOT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from app.exporter import export_standalone_script
    from app.graphs import build_compile_graph, build_run_graph
    from app.models import (
        CandidateElement,
        HealProposal,
        Locator,
        RowResult,
        Step,
        StepResult,
        WorkflowSpec,
    )
    from app.nodes.repair import synthesize_new_locator, validate_role_compatibility
except ImportError:
    from backend.app.exporter import export_standalone_script
    from backend.app.graphs import build_compile_graph, build_run_graph
    from backend.app.models import (
        CandidateElement,
        HealProposal,
        Locator,
        RowResult,
        Step,
        StepResult,
        WorkflowSpec,
    )
    from backend.app.nodes.repair import (
        synthesize_new_locator,
        validate_role_compatibility,
    )
from langgraph.types import Command


class TestPhase7EndToEndLifecycle(unittest.TestCase):
    """End-to-end integration test validating the complete system loop."""

    def test_full_compile_and_healing_lifecycle(self):
        raw_steps = [
            Step(
                idx=1,
                action="goto",
                value="http://localhost:8080/",
                locators=[],
                intent="Navigate to scholarship portal"
            ),
            Step(
                idx=2,
                action="fill",
                value="Maya Deshmukh",
                locators=[Locator(kind="label", value="Full name")],
                intent="Enter applicant name"
            ),
            Step(
                idx=3,
                action="select",
                value="Computer Science",
                locators=[Locator(kind="label", value="Department")],
                intent="Select applicant department"
            ),
            Step(
                idx=4,
                action="click",
                locators=[Locator(kind="css", value="#submitBtn")],
                intent="Submit scholarship application"
            )
        ]

        compile_graph = build_compile_graph()
        compile_thread = {"configurable": {"thread_id": "e2e_compile_thread"}}

        initial_compile_state = {
            "recording_id": "rec_e2e_test",
            "raw_steps": raw_steps,
            "intents_approved": False,
            "spec": None,
            "trial_rows": [],
            "results": [],
            "repairs_count": 0,
            "status": "idle",
            "error": None
        }

        for chunk in compile_graph.stream(initial_compile_state, config=compile_thread):
            pass

        state_after_intents = compile_graph.get_state(compile_thread)
        self.assertEqual(state_after_intents.next, ("review_intents",))

        mock_trial_results = [
            RowResult(
                row_idx=1,
                row_data={"applicant_name": "Maya Deshmukh", "department": "Computer Science"},
                steps=[StepResult(idx=i, ok=True) for i in range(1, 5)],
                success=True,
                evidence="/static/shots/e2e_success.jpg"
            )
        ]

        resume_payload = {
            "approved": True,
            "name": "E2E Scholarship Application Skill",
            "results": mock_trial_results
        }

        for chunk in compile_graph.stream(Command(resume=resume_payload), config=compile_thread):
            pass

        final_compile_state = compile_graph.get_state(compile_thread)
        self.assertEqual(final_compile_state.values.get("status"), "saved")

        compiled_spec: Optional[WorkflowSpec] = final_compile_state.values.get("spec")
        self.assertIsNotNone(compiled_spec)
        if compiled_spec:
            self.assertEqual(compiled_spec.name, "E2E Scholarship Application Skill")
            self.assertEqual(len(compiled_spec.steps), 4)

        run_graph = build_run_graph()
        run_thread = {"configurable": {"thread_id": "e2e_run_thread"}}

        failed_results = [
            RowResult(
                row_idx=1,
                row_data={"applicant_name": "Aarav Patel", "department": "Electronics"},
                steps=[
                    StepResult(idx=1, ok=True),
                    StepResult(idx=2, ok=True),
                    StepResult(idx=3, ok=True),
                    StepResult(idx=4, ok=False, error="Selector '#submitBtn' not found on mutated page")
                ],
                success=False
            )
        ]

        initial_run_state = {
            "run_id": "run_e2e_mutation",
            "spec_id": compiled_spec.id,
            "spec": compiled_spec,
            "rows": [{"applicant_name": "Aarav Patel", "department": "Electronics"}],
            "results": failed_results,
            "heal_approved": False,
            "status": "running"
        }

        for chunk in run_graph.stream(initial_run_state, config=run_thread):
            pass

        state_after_heal = run_graph.get_state(run_thread)
        self.assertEqual(state_after_heal.next, ("review_heal",))

        proposal: Optional[HealProposal] = state_after_heal.values.get("heal_proposal")
        self.assertIsNotNone(proposal)
        if proposal:
            self.assertEqual(proposal.step_idx, 4)

        cand_btn = CandidateElement(
            id=3,
            tag="button",
            role="button",
            classes=["ui-footer-act-pill"],
            bbox={"x": 500, "y": 800, "width": 48, "height": 48}
        )
        self.assertTrue(validate_role_compatibility("click", cand_btn))

        new_loc = synthesize_new_locator(cand_btn)
        self.assertEqual(new_loc.kind, "css")
        self.assertEqual(new_loc.value, "button.ui-footer-act-pill")

        mock_healed_results = [
            RowResult(
                row_idx=1,
                row_data={"applicant_name": "Aarav Patel", "department": "Electronics"},
                steps=[StepResult(idx=i, ok=True) for i in range(1, 5)],
                success=True,
                evidence="/static/shots/e2e_healed_success.jpg"
            )
        ]

        resume_heal_payload = {
            "approved": True,
            "results": mock_healed_results
        }

        for chunk in run_graph.stream(Command(resume=resume_heal_payload), config=run_thread):
            pass

        final_run_state = run_graph.get_state(run_thread)
        patched_spec: Optional[WorkflowSpec] = final_run_state.values.get("spec")
        self.assertIsNotNone(patched_spec)

        if patched_spec:
            self.assertEqual(patched_spec.steps[3].locators[0].value, "button.ui-footer-act-pill")
        self.assertEqual(final_run_state.values.get("status"), "completed")

        if patched_spec:
            script_code = export_standalone_script(patched_spec)
            self.assertIn("async def run_skill", script_code)
            self.assertIn("button.ui-footer-act-pill", script_code)
            self.assertIn("E2E Scholarship Application Skill", script_code)


if __name__ == "__main__":
    unittest.main()
