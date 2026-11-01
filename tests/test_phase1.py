"""
Automated unit and integration test suite for Phase 1.
Tests:
1. Pydantic schema validation & serialization.
2. Image downscaling, mode conversion, and hashing.
3. Resilient JSON extraction across diverse LLM output variations.
4. SHA-256 caching and FIFO eviction.
5. In-memory and SQLite Gemma call logging.
"""

import sys
import unittest
from pathlib import Path

from PIL import Image

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.cache import ResponseCache
from app.call_logger import GemmaCallLogger
from app.imaging import (
    compute_image_hash,
    decode_image_from_base64,
    encode_image_to_base64,
    resize_and_compress_image,
)
from app.llm import extract_json_payload
from app.models import (
    CandidateElement,
    HealProposal,
    Locator,
    Step,
    SuccessCondition,
    Variable,
    WorkflowSpec,
)


class TestPhase1Models(unittest.TestCase):
    """Verifies Pydantic v2 schemas."""

    def test_locator_model(self):
        loc = Locator(kind="role", value="button", name="Submit")
        self.assertEqual(loc.kind, "role")
        self.assertEqual(loc.name, "Submit")

    def test_step_and_workflow_spec(self):
        step = Step(
            idx=1,
            action="click",
            locators=[Locator(kind="role", value="button", name="Submit")],
            intent="Submit application form"
        )
        spec = WorkflowSpec(
            name="Scholarship Application",
            start_url="http://localhost:8080",
            variables=[
                Variable(name="applicant_name", type="text", example="Alice"),
                Variable(name="dept", type="select", example="CS", options=["CS", "IT"])
            ],
            steps=[step],
            success=SuccessCondition(
                text_visible="Application received",
                visual="Green confirmation banner visible"
            )
        )
        dumped = spec.model_dump()
        self.assertEqual(dumped["name"], "Scholarship Application")
        self.assertEqual(len(dumped["steps"]), 1)
        self.assertEqual(dumped["steps"][0]["intent"], "Submit application form")
        self.assertEqual(len(dumped["variables"]), 2)

    def test_candidate_element_and_heal_proposal(self):
        cand = CandidateElement(
            id=3,
            tag="button",
            role="button",
            text="",
            aria_label=None,
            classes=["btn-action-xyz"],
            bbox={"x": 500, "y": 800, "width": 48, "height": 48},
            bm25_score=0.85
        )
        proposal = HealProposal(
            step_idx=4,
            choice=3,
            confidence=0.96,
            reason="Icon button in footer",
            marked_shot="shot_marked.jpg",
            original_shot="shot_before.jpg",
            candidate=cand,
            proposed_locator=Locator(kind="css", value="button.btn-action-xyz")
        )
        self.assertEqual(proposal.choice, 3)
        self.assertEqual(proposal.candidate.id, 3)


class TestPhase1Imaging(unittest.TestCase):
    """Verifies image downscaling and base64 transformations."""

    def test_downscale_large_image(self):
        img = Image.new("RGB", (2400, 1600), color=(100, 150, 200))
        compressed_bytes = resize_and_compress_image(img, max_width=1024, quality=70)

        import io
        result_img = Image.open(io.BytesIO(compressed_bytes))
        self.assertEqual(result_img.width, 1024)
        self.assertEqual(result_img.height, int((1024 / 2400) * 1600))
        self.assertLess(len(compressed_bytes), 150_000)

    def test_rgba_to_rgb_conversion(self):
        img = Image.new("RGBA", (500, 500), color=(255, 0, 0, 128))
        compressed_bytes = resize_and_compress_image(img)
        self.assertTrue(len(compressed_bytes) > 0)

    def test_base64_roundtrip(self):
        img = Image.new("RGB", (100, 100), color=(50, 50, 50))
        raw = resize_and_compress_image(img)
        b64 = encode_image_to_base64(raw)
        decoded = decode_image_from_base64(b64)
        self.assertEqual(compute_image_hash(raw), compute_image_hash(decoded))


class TestPhase1JSONExtraction(unittest.TestCase):
    """Verifies robust JSON extraction under various LLM output formats."""

    def test_clean_json(self):
        raw = '{"intent": "enter email", "role": "variable", "confidence": 0.95}'
        parsed = extract_json_payload(raw)
        self.assertEqual(parsed["intent"], "enter email")
        self.assertEqual(parsed["confidence"], 0.95)

    def test_fenced_json(self):
        raw = '```json\n{\n  "intent": "select department",\n  "role": "variable",\n  "confidence": 0.9\n}\n```'
        parsed = extract_json_payload(raw)
        self.assertEqual(parsed["intent"], "select department")

    def test_json_surrounded_by_commentary(self):
        raw = """
        Based on the provided screenshot, here is the deduced intention:
        {
          "intent": "Click submit button",
          "role": "constant",
          "variable_name": null,
          "confidence": 0.98
        }
        I hope this helps!
        """
        parsed = extract_json_payload(raw)
        self.assertEqual(parsed["intent"], "Click submit button")
        self.assertEqual(parsed["role"], "constant")

    def test_invalid_json_raises(self):
        raw = "Sorry, I cannot parse this image into an automation step."
        with self.assertRaises(ValueError):
            extract_json_payload(raw)


class TestPhase1CacheAndLogger(unittest.TestCase):
    """Verifies caching and call logging."""

    def test_cache_operations(self):
        cache = ResponseCache(max_size=3)
        k1 = cache.compute_key("p1", ["h1"], "m1")
        k2 = cache.compute_key("p2", ["h2"], "m1")
        k3 = cache.compute_key("p3", ["h3"], "m1")
        k4 = cache.compute_key("p4", ["h4"], "m1")

        cache.set(k1, {"v": 1})
        cache.set(k2, {"v": 2})
        cache.set(k3, {"v": 3})
        self.assertEqual(cache.size(), 3)
        self.assertTrue(cache.has(k1))

        cache.set(k4, {"v": 4})
        self.assertEqual(cache.size(), 3)
        self.assertFalse(cache.has(k1))
        self.assertTrue(cache.has(k4))

    def test_call_logger(self):
        test_db = BACKEND_DIR.parent / "data" / "test_logger.db"
        logger = GemmaCallLogger(db_path=test_db)
        logger.clear()

        log = logger.log(
            endpoint="understand_step",
            model="gemma-4-26b-a4b-it",
            prompt_summary="Analyze step 1",
            response_raw='{"intent": "fill name"}',
            latency_ms=210.5,
            status="success",
            image_paths=["hash_abc"],
            parsed_json={"intent": "fill name"}
        )
        self.assertIsNotNone(log.id)
        self.assertEqual(log.endpoint, "understand_step")

        recent = logger.get_recent_calls(10)
        self.assertGreaterEqual(len(recent), 1)
        self.assertEqual(recent[0].endpoint, "understand_step")
        self.assertEqual(recent[0].latency_ms, 210.5)

        logger.clear()
        if test_db.exists():
            test_db.unlink()


if __name__ == "__main__":
    unittest.main()

