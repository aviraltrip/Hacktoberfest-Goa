"""
Standalone Playwright Python script exporter for DemoToSkill.
Converts a WorkflowSpec JSON into an independent, runnable Python script
using Jinja2 templating.
"""

from jinja2 import Template
from app.models import WorkflowSpec

SCRIPT_TEMPLATE = """# Standalone Playwright script for {{ spec.name }}
# Generated automatically by DemoToSkill (Hacktoberfest Hack Day 2026)

import asyncio
from playwright.async_api import async_playwright

SPEC = {{ spec_json }}

async def resolve_element(page, locators):
    \"\"\"Resolves the first locator that matches exactly one element on the page.\"\"\"
    for loc in locators:
        kind = loc['kind']
        val = loc['value']
        name = loc.get('name')

        target = None
        if kind == 'role':
            target = page.get_by_role(val, name=name) if name else page.get_by_role(val)
        elif kind == 'label':
            target = page.get_by_label(val)
        elif kind == 'placeholder':
            target = page.get_by_placeholder(val)
        elif kind == 'text':
            target = page.get_by_text(val)
        elif kind == 'testid':
            target = page.get_by_test_id(val)
        elif kind == 'css':
            target = page.locator(val)

        if target is not None:
            try:
                count = await target.count()
                if count == 1:
                    return target
            except Exception:
                continue
    return None

async def run_skill(row_data: dict, headed: bool = True):
    \"\"\"Executes {{ spec.name }} with the provided input parameters.\"\"\"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not headed)
        context = await browser.new_context()
        page = await context.new_page()

        print(f"Starting workflow on {{ spec.start_url }}...")
        await page.goto("{{ spec.start_url }}")
        await page.wait_for_load_state("networkidle", timeout=2000)

        for step in SPEC['steps']:
            action = step['action']
            val = step.get('value') or ''
            intent = step.get('intent', '')

            # Interpolate variables: {{var_name}} -> row_data['var_name']
            for var_key, var_val in row_data.items():
                val = val.replace(f"{{{{{var_key}}}}}", str(var_val))

            print(f"Step {step['idx']}: {intent} ({action})")

            if action == 'goto':
                await page.goto(val)
            else:
                target = await resolve_element(page, step['locators'])
                if not target:
                    raise RuntimeError(f"Step {step['idx']} failed: Could not resolve target element.")

                if action == 'fill':
                    await target.fill(val)
                elif action == 'click':
                    await target.click()
                elif action == 'select':
                    await target.select_option(val)
                elif action == 'check':
                    await target.check()
                elif action == 'press':
                    await target.press(val)

            await page.wait_for_timeout(300)

        # Verification
        {% if spec.success.text_visible %}
        assert await page.get_by_text("{{ spec.success.text_visible }}").is_visible(), "Success text not found!"
        {% endif %}
        print("Workflow executed successfully!")
        await browser.close()

if __name__ == '__main__':
    # Sample run with observed recording examples
    sample_data = {
    {% for var in spec.variables %}
        "{{ var.name }}": "{{ var.example }}",
    {% endfor %}
    }
    asyncio.run(run_skill(sample_data))
"""

def export_standalone_script(spec: WorkflowSpec) -> str:
    """Renders a standalone Playwright Python automation script from WorkflowSpec."""
    import json
    template = Template(SCRIPT_TEMPLATE)
    return template.render(
        spec=spec,
        spec_json=json.dumps(spec.model_dump(), indent=2)
    )
