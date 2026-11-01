"""
Automated unit and integration test suite for Phase 5: Set-of-Marks Self-Healing.
Tests:
1. Vectorless BM25 candidate ranking over live DOM candidates.
2. Set-of-Marks candidates metadata table formatting.
3. SQLite FTS5 heal memory persistence and full-text search retrieval.
4. Action-to-role compatibility validation.
5. Locator synthesis from chosen candidate elements.
6. LangGraph Run Graph self-healing loop: execution failure -> heal -> review interrupt -> patch_spec.
7. FastAPI heal approval API endpoint.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock
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
        CandidateElement,
        HealProposal,
        RowResult,
        StepResult
    )
    from app.candidates import (
        rank_candidates_bm25,
        format_candidates_table
    )
    from app.memory import HealMemory
    from app.nodes.repair import (
        validate_role_compatibility,
        synthesize_new_locator,
        format_heal_prompt
    )
    from app.graphs import build_run_graph
    from app.main import app, active_runs
except ImportError:
    from backend.app.models import (
        Locator,
        Step,
        Variable,
        SuccessCondition,
        WorkflowSpec,
        CandidateElement,
        HealProposal,
        RowResult,
        StepResult
    )
    from backend.app.candidates import (
        rank_candidates_bm25,
        format_candidates_table
    )
    from backend.app.memory import HealMemory
    from backend.app.nodes.repair import (
        validate_role_compatibility,
        synthesize_new_locator,
        format_heal_prompt
    )
    from backend.app.graphs import build_run_graph
    from backend.app.main import app, active_runs
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command


class TestPhase5CandidatesAndBM25(unittest.TestCase):
    """Verifies BM25 ranking and candidate table generation."""

    def test_bm25_candidate_ranking(self):
        cands = [
            CandidateElement(id=1, tag="input", role="textbox", placeholder="Enter Name", bbox={"x": 0, "y": 0, "width": 200, "height": 30}),
            CandidateElement(id=2, tag="select", role="combobox", text="Computer Science IT", bbox={"x": 0, "y": 40, "width": 200, "height": 30}),
            CandidateElement(id=3, tag="button", role="button", text="Submit Application", classes=["btn-primary"], bbox={"x": 0, "y": 80, "width": 120, "height": 40})
        ]

        query = "Click submit application button"
        ranked = rank_candidates_bm25(cands, query, top_k=3)

        self.assertEqual(len(ranked), 3)
        self.assertEqual(ranked[0].tag, "button")
        self.assertEqual(ranked[0].id, 1)
        self.assertGreater(ranked[0].bm25_score, ranked[1].bm25_score)

    def test_candidates_table_formatting(self):
        cands = [
            CandidateElement(id=1, tag="button", text="Send", aria_label="Submit", id_attr="btn1"),
            CandidateElement(id=2, tag="input", placeholder="Email", classes=["form-control"])
        ]
        table = format_candidates_table(cands)
        self.assertIn("| Box # | Tag |", table)
        self.assertIn("| **1** | `<button>`", table)
        self.assertIn("#btn1", table)
        self.assertIn(".form-control", table)


class TestPhase5HealMemory(unittest.TestCase):
    """Verifies SQLite FTS5 heal memory persistence and hint queries."""

    def test_heal_memory_save_and_lookup(self):
        test_db = BACKEND_DIR.parent / "data" / "test_heal_memory.db"
        mem = HealMemory(db_path=test_db)
        mem.clear()

        mem.save_heal(
            site="scholarship_portal",
            intent="Submit the scholarship application form",
            old_locator="button#submitBtn",
            new_locator="button.ui-footer-act-pill"
        )

        hints = mem.lookup_hints(site="scholarship_portal", intent="Submit scholarship", limit=2)
        self.assertGreaterEqual(len(hints), 1)
        self.assertIn("button.ui-footer-act-pill", hints[0])

        mem.clear()
        if test_db.exists():
            test_db.unlink()


class TestPhase5RoleAndLocatorValidation(unittest.TestCase):
    """Verifies semantic role compatibility and locator synthesis."""

    def test_role_compatibility(self):
        btn_cand = CandidateElement(id=1, tag="button", role="button")
        input_cand = CandidateElement(id=2, tag="input", role="textbox")
        select_cand = CandidateElement(id=3, tag="select", role="combobox")

        self.assertTrue(validate_role_compatibility("fill", input_cand))
        self.assertFalse(validate_role_compatibility("fill", btn_cand))

        self.assertTrue(validate_role_compatibility("select", select_cand))
        self.assertFalse(validate_role_compatibility("select", input_cand))

        self.assertTrue(validate_role_compatibility("click", btn_cand))

    def test_synthesize_new_locator(self):
        cand_id = CandidateElement(id=1, tag="button", id_attr="btn_action_882")
        loc_id = synthesize_new_locator(cand_id)
        self.assertEqual(loc_id.kind, "css")
        self.assertEqual(loc_id.value, "#btn_action_882")

        cand_cls = CandidateElement(id=2, tag="button", classes=["ui-footer-act-pill", "btn"])
        loc_cls = synthesize_new_locator(cand_cls)
        self.assertEqual(loc_cls.kind, "css")
        self.assertEqual(loc_cls.value, "button.ui-footer-act-pill")

        cand_aria = CandidateElement(id=3, tag="button", aria_label="Submit application")
        loc_aria = synthesize_new_locator(cand_aria)
        self.assertEqual(loc_aria.kind, "role")
        self.assertEqual(loc_aria.name, "Submit application")


class TestPhase5RunGraph(unittest.TestCase):
    """Verifies the Run Graph self-healing feedback loop with LangGraph."""

    def test_run_graph_heal_loop_and_spec_patching(self):
        graph = build_run_graph()
        thread_config = {"configurable": {"thread_id": "test_run_graph_thread"}}

        step2 = Step(
            idx=2,
            action="click",
            intent="Submit application",
            locators=[Locator(kind="css", value="#broken_old_btn")]
        )
        spec = WorkflowSpec(
            id="spec_heal_test",
            name="Mutated Portal Test",
            start_url="http://localhost:8080/?v=2",
            steps=[
                Step(idx=1, action="goto", value="http://localhost:8080/?v=2", intent="Open site"),
                step2
            ],
            success=SuccessCondition(visual="Done")
        )

        initial_state = {
            "run_id": "run_test_heal",
            "spec_id": spec.id,
            "spec": spec,
            "rows": [{"name": "Aarav"}],
            "results": [
                RowResult(
                    row_idx=1,
                    row_data={"name": "Aarav"},
                    steps=[
                        StepResult(idx=1, ok=True),
                        StepResult(idx=2, ok=False, error="Element #broken_old_btn not found")
                    ],
                    success=False
                )
            ],
            "heal_approved": False,
            "status": "running"
        }

        for chunk in graph.stream(initial_state, config=thread_config):
            pass

        state_after_interrupt = graph.get_state(thread_config)
        self.assertEqual(state_after_interrupt.next, ("review_heal",))

        proposal: HealProposal = state_after_interrupt.values.get("heal_proposal")
        self.assertIsNotNone(proposal)
        self.assertEqual(proposal.step_idx, 2)

        mock_success_results = [
            RowResult(
                row_idx=1,
                row_data={"name": "Aarav"},
                steps=[StepResult(idx=1, ok=True), StepResult(idx=2, ok=True)],
                success=True
            )
        ]

        resume_payload = {"approved": True, "results": mock_success_results}
        for chunk in graph.stream(Command(resume=resume_payload), config=thread_config):
            pass

        final_state = graph.get_state(thread_config)
        patched_spec: WorkflowSpec = final_state.values.get("spec")
        self.assertGreater(len(patched_spec.steps[1].locators), 1)
        self.assertEqual(patched_spec.steps[1].locators[0].value, "button.ui-footer-act-pill")


class TestPhase5API(unittest.TestCase):
    """Verifies heal approval endpoint."""

    def setUp(self):
        self.client = TestClient(app)

    def test_approve_heal_endpoint(self):
        run_id = "run_test_approve_heal"
        import asyncio
        active_runs[run_id] = {
            "run_id": run_id,
            "spec_id": "spec_123",
            "status": "heal_pending",
            "rows": [],
            "results": [],
            "event_queue": asyncio.Queue()
        }

        resp = self.client.post(f"/api/run/{run_id}/approve_heal", json={
            "approved": True,
            "override_choice": 1
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "heal_approved")

    def test_get_heal_memory_endpoint(self):
        resp = self.client.get("/api/heal/memory")
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json(), list)

    def test_get_ablation_endpoint(self):
        resp = self.client.get("/api/ablation")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("benchmark_results", data)
        self.assertIn("summary", data)
        self.assertIn("gemma_average", data["summary"])
        self.assertEqual(data["summary"]["gemma_average"], 100.0)



if __name__ == "__main__":
    unittest.main()
