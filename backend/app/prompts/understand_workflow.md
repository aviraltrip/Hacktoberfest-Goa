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

