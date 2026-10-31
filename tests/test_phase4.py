"""
Automated unit and integration test suite for Phase 4: Execution Runner & Verification.
Tests:
1. Dynamic template variable interpolation ({{var_name}}).
2. Exactly-One locator resolution rule (count == 1).
3. Dual-layer verification (deterministic checks + Gemma 4 visual inspection).
4. FastAPI batch execution endpoints and run telemetry.
"""

import sys
import unittest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
for p in (str(BACKEND_DIR), str(ROOT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from app.models import (
        Locator,
        Step,
        Variable,
        SuccessCondition,
        WorkflowSpec,
        StepResult,
        RowResult,
        VerifyVisualOutput
    )
    from app.runner import (
        interpolate_template,
        resolve_locator,
        to_playwright_locator
    )
    from app.nodes.verify import verify_single_row, format_verify_prompt
    from app.nodes.compile_spec import save_spec_to_file
    from app.main import app, active_runs
except ImportError:
    from backend.app.models import (
        Locator,
        Step,
        Variable,
        SuccessCondition,
        WorkflowSpec,
        StepResult,
        RowResult,
        VerifyVisualOutput
    )
    from backend.app.runner import (
        interpolate_template,
        resolve_locator,
        to_playwright_locator
    )
    from backend.app.nodes.verify import verify_single_row, format_verify_prompt
    from backend.app.nodes.compile_spec import save_spec_to_file
    from backend.app.main import app, active_runs


class TestPhase4Runner(unittest.TestCase):
    """Verifies template interpolation and locator resolution logic."""

    def test_interpolate_template(self):
        template = "Hello {{applicant_name}}, welcome to {{dept}} for {{year}}!"
        row_data = {
            "applicant_name": "Maya Deshmukh",
            "dept": "Computer Science",
            "year": 2026
        }
        res = interpolate_template(template, row_data)
        self.assertEqual(res, "Hello Maya Deshmukh, welcome to Computer Science for 2026!")

    def test_interpolate_template_no_vars(self):
        literal = "Submit Application"
        self.assertEqual(interpolate_template(literal, {}), "Submit Application")
        self.assertIsNone(interpolate_template(None, {}))

    def test_resolve_locator_exactly_one_rule(self):
        """
        Candidate 1 has count 0 (not found)
        Candidate 2 has count 2 (duplicate/ambiguous)
        Candidate 3 has count 1 (exactly-one match -> WINS!)
        """
        loc1 = Locator(kind="role", value="button", name="Old Submit")
        loc2 = Locator(kind="css", value=".btn")
        loc3 = Locator(kind="css", value="#submitBtn")

        mock_page = MagicMock()

        # Mock targets
        target1 = MagicMock()
        target1.count = AsyncMock(return_value=0)

        target2 = MagicMock()
        target2.count = AsyncMock(return_value=2)

        target3 = MagicMock()
        target3.count = AsyncMock(return_value=1)

        def side_effect(val, **kwargs):
            if val == "Old Submit":
                return target1
            elif val == ".btn":
                return target2
            elif val == "#submitBtn":
                return target3
            return target1

        mock_page.get_by_role = MagicMock(side_effect=lambda r, **kw: side_effect(kw.get("name", "")))
        mock_page.locator = MagicMock(side_effect=side_effect)

        loop = asyncio.new_event_loop()
        winning_target, winning_loc = loop.run_until_complete(
            resolve_locator(mock_page, [loc1, loc2, loc3])
        )
        loop.close()

        self.assertIsNotNone(winning_target)
        self.assertEqual(winning_target, target3)
        self.assertEqual(winning_loc.value, "#submitBtn")


class TestPhase4Verification(unittest.TestCase):
    """Verifies deterministic and multimodal visual verification."""

    def test_format_verify_prompt(self):
        prompt = format_verify_prompt("Green banner with ref #")
        self.assertIn("Green banner with ref #", prompt)
        self.assertNotIn("{{visual_success_condition}}", prompt)

    def test_verify_single_row_success(self):
        spec = WorkflowSpec(
            name="Scholarship Submission",
            start_url="http://localhost:8080",
            success=SuccessCondition(
                text_visible="Application received",
                visual="Green confirmation banner visible"
            )
        )
        row = RowResult(
            row_idx=1,
            row_data={"name": "Alice"},
            steps=[StepResult(idx=1, ok=True), StepResult(idx=2, ok=True)],
            final_shot=""
        )

        loop = asyncio.new_event_loop()
        evaluated_row = loop.run_until_complete(verify_single_row(row, spec))
        loop.close()

        self.assertTrue(evaluated_row.success)

    def test_verify_single_row_step_failure(self):
        spec = WorkflowSpec(
            name="Scholarship Submission",
            start_url="http://localhost:8080",
            success=SuccessCondition(visual="Green alert")
        )
        row = RowResult(
            row_idx=1,
            row_data={"name": "Bob"},
            steps=[
                StepResult(idx=1, ok=True),
                StepResult(idx=2, ok=False, error="Button not found")
            ]
        )

        loop = asyncio.new_event_loop()
        evaluated_row = loop.run_until_complete(verify_single_row(row, spec))
        loop.close()

        self.assertFalse(evaluated_row.success)
        self.assertIn("Execution failed on step 2", evaluated_row.evidence)


class TestPhase4API(unittest.TestCase):
    """Verifies batch execution REST endpoints."""

    def setUp(self):
        self.client = TestClient(app)

    def test_run_nonexistent_spec(self):
        resp = self.client.post("/api/run", json={"spec_id": "non_existent_spec", "rows": [{}]})
        self.assertEqual(resp.status_code, 404)

    @patch("app.main._run_batch_worker", new_callable=AsyncMock)
    def test_run_lifecycle_and_history(self, mock_worker):
        # Save a test spec
        spec = WorkflowSpec(
            id="spec_test_phase4",
            name="Phase 4 Test Portal",
            start_url="http://localhost:8080",
            variables=[Variable(name="applicant", type="text", example="Test")],
            steps=[
                Step(idx=1, action="goto", value="http://localhost:8080", intent="Go to portal")
            ],
            success=SuccessCondition(visual="Success message")
        )
        save_spec_to_file(spec)

        # Trigger run
        resp = self.client.post("/api/run", json={
            "spec_id": "spec_test_phase4",
            "rows": [{"applicant": "Student A"}, {"applicant": "Student B"}],
            "headed": False
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("run_id", data)
        self.assertEqual(data["status"], "running")
        self.assertEqual(data["row_count"], 2)

        run_id = data["run_id"]
        self.assertIn(run_id, active_runs)

        # Query runs list
        resp_list = self.client.get("/api/runs")
        self.assertEqual(resp_list.status_code, 200)
        self.assertIsInstance(resp_list.json(), list)


if __name__ == "__main__":
    unittest.main()
