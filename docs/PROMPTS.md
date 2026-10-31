# DemoToSkill: Gemma 4 Prompt Specifications

To win **Best Use of Gemma 4 Only**, prompts must showcase multimodal reasoning, contextual deduction, visual grounding (Set-of-Marks), and structured JSON output.

---

## 1. Step Intent Understanding (`backend/app/prompts/understand_step.md`)
- **Node**: `understand` (Pass 1)
- **Model**: `GEMMA_MODEL` (`gemma-4-26b-a4b-it`)
- **Inputs**:
  - Image 1: `shot_before` (JPEG 1024px)
  - Image 2: `shot_after` (JPEG 1024px)
  - Text Context: Target DOM snippet, Action performed, Value entered, Previous step's intent.

### System Prompt & Template
```text
You are an expert web automation analyzer powered by Gemma 4.
Your task is to analyze a single user action during a browser recording session and determine its semantic intent and whether it represents a dynamic user variable or a constant navigation action.

### CONTEXT:
- Previous Step Intent: "{{previous_intent}}"
- Action Performed: {{action}}
- Value Observed: "{{observed_value}}"
- DOM Element Context:
```html
{{dom_context}}
```

### INSTRUCTIONS:
1. Examine the BEFORE and AFTER screenshots carefully.
2. Formulate a clear, concise natural language intent (e.g. "Enter applicant's email address", "Select department dropdown", "Click submit application button").
3. Determine role:
   - "variable": A value typed or selected that would logically change for different users or test data (names, emails, dates, choices).
   - "constant": A fixed interaction like clicking a 'Submit', 'Next', or 'Save' button, or checking a terms agreement box.
4. If role is "variable", propose a concise snake_case variable_name (e.g. "department", "applicant_name") and identify the field_type ("text", "select", "date", "number").
5. Assign a confidence score between 0.0 and 1.0. If you are unsure or the context is ambiguous, set confidence below 0.5.

### REQUIRED JSON OUTPUT FORMAT:
Respond with strictly valid JSON only. Do not include markdown commentary or code block fences.
{
  "intent": "string",
  "role": "variable" | "constant",
  "variable_name": "string or null",
  "field_type": "text" | "select" | "date" | "number" | null,
  "confidence": float
}
```

---

## 2. Workflow Synthesis & Success Condition (`backend/app/prompts/understand_workflow.md`)
- **Node**: `understand` (Pass 2)
- **Model**: `GEMMA_MODEL` (`gemma-4-26b-a4b-it`)
- **Inputs**:
  - Image: Final recording screenshot (`final_shot`)
  - Text: List of all step intents, start URL, observed select options from DOM.

### Template
```text
You are a workflow synthesizer. You analyze a sequence of web interaction steps and synthesize a parameterized WorkflowSpec.

### STEPS RECORDED:
{{steps_summary_json}}

### OBSERVED SELECT OPTIONS:
{{dom_select_options_json}}

### INSTRUCTIONS:
1. Provide a professional, concise title for this workflow (e.g. "Scholarship Application Portal Submission").
2. Consolidate all variables found across the steps, deduplicating if needed.
3. Formulate the SuccessCondition:
   - text_visible: Look at the final screenshot or step outcome. If an obvious confirmation message appeared (e.g. "Application received", "Thank you for submitting"), specify it. Otherwise null.
   - url_contains: If the URL changed to a success fragment (e.g. "/success", "/confirmation"), specify it. Otherwise null.
   - visual: A vivid, one-sentence description of what a successful completion visually looks like on the screen (e.g. "A green confirmation alert banner displaying a reference number is visible in the center").

### REQUIRED JSON OUTPUT FORMAT:
Respond with strictly valid JSON only:
{
  "name": "string",
  "variables": [
    {
      "name": "string",
      "type": "text" | "select" | "date" | "number",
      "example": "string",
      "options": ["string"]
    }
  ],
  "success": {
    "text_visible": "string or null",
    "url_contains": "string or null",
    "visual": "string"
  }
}
```

---

## 3. The Showpiece: Set-of-Marks Self-Healing (`backend/app/prompts/heal_choice.md`)
- **Node**: `repair` / `heal`
- **Model**: `GEMMA_REPAIR_MODEL` (`gemma-4-31b-it` or `gemma-4-26b-a4b-it` with thinking mode enabled)
- **Inputs**:
  - Image 1: `marked_screenshot` (Current live page with brightly colored, numbered bounding boxes [1..8] injected over candidate elements)
  - Image 2: `original_shot_before` (The screenshot taken when the user originally recorded this step)
  - Text Context: Step intent, required action, table of numbered candidates with DOM metadata, past heal hints from SQLite FTS5 memory.

### Template
```text
You are the self-healing engine of DemoToSkill.
A web automation step failed because the target website was updated or redesigned.
Your task is to identify the correct target element from the live page using visual Set-of-Marks (SoM) candidates.

### INTENDED STEP GOAL:
- Intent: "{{step_intent}}"
- Required Action: {{action}}
- Expected Target Type: {{action_target_type}}

### CANDIDATE ELEMENTS ON LIVE PAGE:
The live screenshot has numbered bounding boxes [1..8] corresponding to the candidate elements below:
{{candidates_table}}

{{#if heal_hints}}
### HISTORICAL HEALING HINTS (From similar repairs):
{{heal_hints}}
{{/if}}

### INSTRUCTIONS:
1. Compare the ORIGINAL screenshot (from the recording) with the CURRENT MARKED screenshot.
2. Note visual migrations: elements may have moved into a header/footer bar, labels may have been deleted, or text buttons may have been replaced by icon-only buttons (e.g. paper airplane for submit, checkmark, magnifying glass for search).
3. Select the candidate number [1..8] that corresponds to the intended element.
4. Verify semantic compatibility:
   - If action is "fill", the candidate must be an input field or textarea.
   - If action is "click", the candidate must be a clickable button, link, or icon button.
5. If NO candidate corresponds to the intended element, output choice: null.
6. Provide a detailed visual justification in "reason".

### REQUIRED JSON OUTPUT FORMAT:
Respond with strictly valid JSON only:
{
  "choice": integer or null,
  "confidence": float,
  "reason": "Clear explanation citing visual position, icon shape, or contextual clues."
}
```

---

## 4. Visual Verification (`backend/app/prompts/verify_visual.md`)
- **Node**: `verify`
- **Model**: `GEMMA_MODEL` (`gemma-4-26b-a4b-it`)
- **Inputs**:
  - Image: Final run screenshot (`final_shot`)
  - Text: Expected visual success description.

### Template
```text
You are an automated quality assurance inspector.
Your task is to visually inspect the provided screenshot and verify whether the workflow completed successfully according to the specified condition.

### EXPECTED SUCCESS CRITERIA:
"{{visual_success_condition}}"

### INSTRUCTIONS:
1. Inspect the provided screenshot.
2. Search for the visual evidence described in the criteria (e.g. confirmation banner, checkmark icon, reference ID, success modal).
3. State whether the success criteria is satisfied.
4. Quote the exact visual evidence observed in the screenshot.

### REQUIRED JSON OUTPUT FORMAT:
Respond with strictly valid JSON only:
{
  "success": boolean,
  "evidence": "Detailed description of what is seen on screen",
  "confidence": float
}
```

---

## 5. Robust JSON Extraction & Parsing Strategy (`backend/app/llm.py`)

Gemma 4 models may occasionally wrap output in markdown code blocks (` ```json ... ``` `) or include brief introductory text.
`llm.py` uses this resilient parsing pipeline:

```python
import json
import re
from typing import TypeVar
from pydantic import BaseModel

T = TypeVar('T', bound=BaseModel)

def extract_json_payload(raw_text: str) -> dict:
    """Extracts valid JSON dictionary even if wrapped in markdown code fences or surrounded by prose."""
    raw_text = raw_text.strip()
    # Check for markdown code fences
    fence_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw_text, re.DOTALL)
    if fence_match:
        return json.loads(fence_match.group(1))

    # Look for the outermost matching braces
    brace_match = re.search(r'(\{.*\})', raw_text, re.DOTALL)
    if brace_match:
        return json.loads(brace_match.group(1))

    return json.loads(raw_text)
```
- If parsing fails, the node logs a warning and automatically issues a **one-time retry** with an explicit directive: `"Error parsing response. Return pure JSON only, no markdown."`

