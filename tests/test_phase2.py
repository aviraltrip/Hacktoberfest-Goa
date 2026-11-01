"""
Automated unit and API test suite for Phase 2: Browser Recording Engine.
Tests:
1. Fallback locator hierarchy generation (role, label, placeholder, text, testid, css).
2. DOM outerHTML trimming.
3. Sequential input coalescing and password value masking.
4. FastAPI health, telemetry, and recording session endpoints using TestClient.
"""

import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.locators import (
    build_locators_for_element,
    coalesce_recorded_events,
    trim_dom_context,
)
from app.main import app


class TestPhase2Locators(unittest.TestCase):
    """Verifies locator candidate extraction and ordering rules."""

    def test_button_with_role_and_name(self):
        elem = {
            "tag": "button",
            "role": "button",
            "accessible_name": "Submit Application",
            "id": "submitBtn",
            "classes": ["btn-primary"]
        }
        locators = build_locators_for_element(elem)
        self.assertGreater(len(locators), 0)

        first = locators[0]
        self.assertEqual(first.kind, "role")
        self.assertEqual(first.value, "button")
        self.assertEqual(first.name, "Submit Application")

        kinds = [l.kind for l in locators]
        self.assertIn("css", kinds)

    def test_input_with_label_and_placeholder(self):
        elem = {
            "tag": "input",
            "type": "text",
            "accessible_name": "Full Name",
            "label": "Full Name",
            "placeholder": "e.g. Maya Deshmukh",
            "id": "fullName"
        }
        locators = build_locators_for_element(elem)
        kinds = [l.kind for l in locators]

        self.assertIn("role", kinds)
        self.assertIn("placeholder", kinds)
        self.assertIn("css", kinds)

    def test_element_with_testid(self):
        elem = {
            "tag": "button",
            "testid": "submit-action-btn",
            "accessible_name": "Send"
        }
        locators = build_locators_for_element(elem)
        kinds = [l.kind for l in locators]
        self.assertIn("testid", kinds)

        testid_loc = next(l for l in locators if l.kind == "testid")
        self.assertEqual(testid_loc.value, "submit-action-btn")

    def test_trim_dom_context(self):
        long_html = "<div>" + ("<span>text</span>" * 50) + "</div>"
        trimmed = trim_dom_context(long_html, max_chars=100)
        self.assertLessEqual(len(trimmed), 100)
        self.assertTrue(trimmed.endswith("..."))


class TestPhase2Coalescing(unittest.TestCase):
    """Verifies consecutive event coalescing and privacy safeguards."""

    def test_coalesce_consecutive_keystrokes(self):
        target = {
            "tag": "input",
            "type": "text",
            "id": "fullName",
            "accessible_name": "Full Name"
        }
        raw_events = [
            {"action": "input", "value": "A", "target": target, "shot_before": "b1.jpg"},
            {"action": "input", "value": "Al", "target": target},
            {"action": "input", "value": "Ali", "target": target},
            {"action": "input", "value": "Alice", "target": target, "shot_after": "a1.jpg"}
        ]
        steps = coalesce_recorded_events(raw_events)

        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].action, "fill")
        self.assertEqual(steps[0].value, "Alice")
        self.assertEqual(steps[0].shot_before, "b1.jpg")
        self.assertEqual(steps[0].shot_after, "a1.jpg")

    def test_password_masking(self):
        target = {
            "tag": "input",
            "type": "password",
            "id": "pwdField",
            "accessible_name": "Password"
        }
        raw_events = [
            {"action": "input", "value": "SuperSecret123", "target": target}
        ]
        steps = coalesce_recorded_events(raw_events)
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].value, "***")

    def test_select_and_click_sequence(self):
        raw_events = [
            {"action": "goto", "url": "http://localhost:8080"},
            {
                "action": "input",
                "value": "Alice",
                "target": {"tag": "input", "id": "name", "accessible_name": "Name"}
            },
            {
                "action": "change",
                "value": "Computer Science",
                "target": {"tag": "select", "id": "dept", "accessible_name": "Department"}
            },
            {
                "action": "click",
                "target": {"tag": "button", "id": "submitBtn", "accessible_name": "Submit"}
            }
        ]
        steps = coalesce_recorded_events(raw_events)
        self.assertEqual(len(steps), 4)
        self.assertEqual(steps[0].action, "goto")
        self.assertEqual(steps[1].action, "fill")
        self.assertEqual(steps[1].value, "Alice")
        self.assertEqual(steps[2].action, "select")
        self.assertEqual(steps[2].value, "Computer Science")
        self.assertEqual(steps[3].action, "click")


class TestPhase2API(unittest.TestCase):
    """Verifies FastAPI endpoints via TestClient."""

    def setUp(self):
        self.client = TestClient(app)

    def test_health_endpoint(self):
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ok")

    def test_gemma_calls_endpoint(self):
        resp = self.client.get("/api/gemma/calls")
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json(), list)

    def test_stop_nonexistent_recording(self):
        resp = self.client.post("/api/record/stop", json={"recording_id": "non_existent_rec"})
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()

