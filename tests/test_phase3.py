"""
Automated unit and integration test suite for Phase 3: Semantic Understanding & Compilation.
Tests:
1. Prompt formatting for understand_step and understand_workflow.
2. Multimodal step understanding and parameterization logic.
3. LangGraph Compile Graph execution, interrupt at review_intents, and Command resume.
4. Standalone Playwright Python script exporter.
5. FastAPI compilation, spec inspection, and export endpoints.
"""

import sys
import unittest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

# Ensure backend directory is in sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.models import (
    Step,
    Locator,
    Variable,
    SuccessCondition,
    WorkflowSpec,
    RowResult,
    UnderstandStepOutput,
    UnderstandWorkflowOutput
)
from app.nodes.understand import (
    format_step_prompt,
    format_workflow_prompt,
    understand_single_step,
    understand_workflow_synthesis
)
from app.nodes.compile_spec import (
    generate_trial_rows,
    compile_spec_node,
    save_spec_to_file
)
from app.exporter import export_standalone_script
from app.graphs import build_compile_graph
from app.main import app, completed_recordings, active_compilations
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command


class TestPhase3Understanding(unittest.TestCase):
    """Verifies prompt templating and step parameterization."""

    def test_format_step_prompt(self):
        prompt = format_step_prompt(
            action="fill",
            observed_value="Maya Deshmukh",
            dom_context="<input id='fullName'>",
            previous_intent="Navigate to portal"
        )
        self.assertIn("Navigate to portal", prompt)
        self.assertIn("Maya Deshmukh", prompt)
        self.assertIn("<input id='fullName'>", prompt)
        self.assertNotIn("{{action}}", prompt)

    def test_format_workflow_prompt(self):
        step = Step(idx=1, action="click", intent="Click submit", locators=[])
        prompt = format_workflow_prompt([step], {"dept": ["CS", "IT"]})
        self.assertIn("Click submit", prompt)
        self.assertIn("CS", prompt)
        self.assertNotIn("{{steps_summary_json}}", prompt)

    def test_understand_single_step_variable_detection(self):
        step = Step(
            idx=2,
            action="fill",
            value="Aarav Patel",
            dom_context="<input id='fullName'>",
            locators=[Locator(kind="css", value="#fullName")]
        )

        mock_client = MagicMock()
        mock_client.generate_structured = AsyncMock(
            return_value=UnderstandStepOutput(
                intent="Enter applicant's full legal name",
                role="variable",
                variable_name="applicant_name",
                field_type="text",
                confidence=0.98
            )
        )

        loop = asyncio.new_event_loop()
        updated_step, var_obj = loop.run_until_complete(
            understand_single_step(step, "previous step", client=mock_client)
        )
        loop.close()

        self.assertEqual(updated_step.intent, "Enter applicant's full legal name")
        self.assertEqual(updated_step.value, "{{applicant_name}}")
        self.assertIsNotNone(var_obj)
        self.assertEqual(var_obj.name, "applicant_name")
        self.assertEqual(var_obj.example, "Aarav Patel")


class TestPhase3Compilation(unittest.TestCase):
    """Verifies spec compilation, row generation, and script export."""

    def test_generate_trial_rows(self):
        vars_list = [
            Variable(name="name", type="text", example="Alice"),
            Variable(name="dept", type="select", example="CS", options=["CS", "IT", "Mech"]),
            Variable(name="year", type="number", example="2026")
        ]
        rows = generate_trial_rows(vars_list)
        self.assertEqual(len(rows), 2)
        # Verify select variation
        self.assertEqual(rows[0]["dept"], "CS")
        self.assertEqual(rows[1]["dept"], "IT")
        # Verify number variation
        self.assertEqual(rows[0]["year"], 2026)
        self.assertEqual(rows[1]["year"], 2027)

    def test_export_standalone_script(self):
        spec = WorkflowSpec(
            id="spec_test_001",
            name="Test Scholarship Workflow",
            start_url="http://localhost:8080",
            variables=[Variable(name="applicant_name", type="text", example="Maya")],
            steps=[
                Step(idx=1, action="goto", value="http://localhost:8080", intent="Go to portal"),
                Step(idx=2, action="fill", value="{{applicant_name}}", intent="Fill name", locators=[Locator(kind="label", value="Full name")])
            ],
            success=SuccessCondition(text_visible="Application received", visual="Alert shown")
        )
        script = export_standalone_script(spec)
        self.assertIn("async def run_skill", script)
        self.assertIn("Test Scholarship Workflow", script)
        self.assertIn("Application received", script)
        self.assertIn("page.get_by_label", script)


class TestPhase3LangGraph(unittest.TestCase):
    """Verifies LangGraph Compile Graph execution, interrupt, and resume."""

    def test_compile_graph_interrupt_and_resume(self):
        checkpointer = MemorySaver()
        graph = build_compile_graph(checkpointer=checkpointer)
        thread_config = {"configurable": {"thread_id": "test_thread_p3_stream"}}

        sample_steps = [
            Step(idx=1, action="goto", value="http://localhost:8080", intent="Open site"),
            Step(
                idx=2,
                action="fill",
                value="Alice",
                intent="Enter name",
                dom_context="<input id='name'>",
                locators=[Locator(kind="css", value="#name")]
            )
        ]

        initial_state = {
            "recording_id": "rec_test_graph",
            "raw_steps": sample_steps,
            "intents_approved": False,
            "repairs_count": 0,
            "results": [RowResult(row_idx=1, row_data={}, steps=[], success=True)],
            "status": "understanding"
        }

        # Step 1: Run graph until interrupt using stream
        for chunk in graph.stream(initial_state, config=thread_config):
            pass

        state_after_interrupt = graph.get_state(thread_config)

        # Verify graph paused at review_intents
        self.assertEqual(state_after_interrupt.next, ("review_intents",))

        # Step 2: Resume graph with human approval Command
        resume_payload = {
            "name": "Approved Scholarship Workflow",
            "variables": [
                {"name": "student_name", "type": "text", "example": "Alice", "options": []}
            ]
        }

        for chunk in graph.stream(Command(resume=resume_payload), config=thread_config):
            pass

        final_state = graph.get_state(thread_config)

        # Verify completion
        self.assertEqual(final_state.values.get("status"), "saved")
        final_spec: WorkflowSpec = final_state.values.get("spec")
        self.assertEqual(final_spec.name, "Approved Scholarship Workflow")
        self.assertEqual(final_spec.variables[0].name, "student_name")


class TestPhase3API(unittest.TestCase):
    """Verifies compilation API endpoints."""

    def setUp(self):
        self.client = TestClient(app)

    def test_compile_missing_recording(self):
        resp = self.client.post("/api/compile", json={"recording_id": "non_existent_rec"})
        self.assertEqual(resp.status_code, 400)

    def test_compile_and_export_lifecycle(self):
        rec_id = "rec_test_api_p3"
        completed_recordings[rec_id] = [
            Step(idx=1, action="goto", value="http://localhost:8080", intent="Go to portal"),
            Step(idx=2, action="click", intent="Submit", locators=[Locator(kind="role", value="button", name="Submit")])
        ]

        # Trigger compilation
        resp = self.client.post("/api/compile", json={"recording_id": rec_id})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("compile_id", data)
        self.assertEqual(data["status"], "understanding")

        compile_id = data["compile_id"]
        self.assertIn(compile_id, active_compilations)


if __name__ == "__main__":
    unittest.main()
