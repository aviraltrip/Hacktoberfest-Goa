"""
WorkflowSpec Interpreter and Playwright Execution Engine for DemoToSkill.
Interprets structured JSON specs directly without generating raw LLM code.
Enforces:
1. Fallback locator resolution with the Exactly-One Rule (count == 1).
2. Clean browser context isolation per row.
3. Post-action settling (network idle cap 1.5s + 300ms pause).
4. Runtime variable template interpolation ({{var_name}} -> row_data[var_name]).
"""

import time
import re
import asyncio
from typing import Optional, Any, Callable
from pathlib import Path
from playwright.async_api import async_playwright, Page, Browser, BrowserContext

from app.config import (
    SHOTS_DIR,
    NETWORK_IDLE_TIMEOUT_MS,
    POST_ACTION_SETTLE_MS
)
from app.imaging import resize_and_compress_image, save_screenshot_bytes
from app.models import (
    Locator,
    Step,
    WorkflowSpec,
    StepResult,
    RowResult
)


def interpolate_template(template_str: Optional[str], row_data: dict[str, Any]) -> Optional[str]:
    """
    Interpolates dynamic variables in a step value.
    Replaces '{{var_name}}' with the corresponding value from row_data.
    """
    if template_str is None:
        return None

    result = str(template_str)
    # Find all {{var_name}} matches
    matches = re.findall(r"\{\{([a-zA-Z0-9_\-\.]+)\}\}", result)
    for var_name in matches:
        if var_name in row_data:
            val = str(row_data[var_name])
            result = result.replace(f"{{{{{var_name}}}}}", val)

    return result


def to_playwright_locator(page: Page, loc: Locator):
    """
    Maps a declarative Locator schema object to its matching Playwright Locator object.
    """
    kind = loc.kind
    val = loc.value
    name = loc.name

    if kind == "role":
        return page.get_by_role(val, name=name) if name else page.get_by_role(val)
    elif kind == "label":
        return page.get_by_label(val)
    elif kind == "placeholder":
        return page.get_by_placeholder(val)
    elif kind == "text":
        return page.get_by_text(val)
    elif kind == "testid":
        return page.get_by_test_id(val)
    elif kind == "css":
        return page.locator(val)
    else:
        return page.locator(val)


async def resolve_locator(page: Page, locators: list[Locator]) -> tuple[Any, Optional[Locator]]:
    """
    Evaluates candidate locators in priority order.
    EXACTLY-ONE RULE: A candidate only wins if await target.count() == 1.
    If count() > 1 or count() == 0, advances to the next candidate.
    Returns (playwright_locator_instance, winning_locator_schema) or (None, None).
    """
    for loc in locators:
        try:
            target = to_playwright_locator(page, loc)
            count = await target.count()
            if count == 1:
                return target, loc
        except Exception:
            continue

    return None, None


class WorkflowRunner:
    """Interprets and executes a WorkflowSpec across data rows."""

    def __init__(self, run_id: Optional[str] = None):
        self.run_id = run_id or f"run_{int(time.time())}"

    async def _settle_page(self, page: Page):
        """Awaits DOM stability after an action."""
        if page.is_closed():
            return
        try:
            await page.wait_for_load_state("networkidle", timeout=NETWORK_IDLE_TIMEOUT_MS)
        except Exception:
            pass
        await asyncio.sleep(POST_ACTION_SETTLE_MS / 1000.0)

    async def _capture_final_shot(self, page: Page, row_idx: int) -> str:
        """Captures and saves a compressed JPEG screenshot of the final page state."""
        if page.is_closed():
            return ""
        try:
            raw_png = await page.screenshot(type="png", full_page=False)
            jpeg_bytes = resize_and_compress_image(raw_png)
            filename = f"{self.run_id}_row_{row_idx}_final.jpg"
            save_screenshot_bytes(jpeg_bytes, filename)
            return f"/static/shots/{filename}"
        except Exception as e:
            print(f"[Runner] Screenshot capture error: {e}")
            return ""

    async def execute_step(
        self,
        page: Page,
        step: Step,
        row_data: dict[str, Any]
    ) -> StepResult:
        """
        Executes a single step on the page with a 5-second timeout and locator resolution.
        """
        t0 = time.time()
        action = step.action
        interpolated_val = interpolate_template(step.value, row_data)

        # 1. Action: Navigation
        if action == "goto":
            url = interpolated_val or step.value
            try:
                await page.goto(url, timeout=10000)
                await self._settle_page(page)
                duration = (time.time() - t0) * 1000
                return StepResult(idx=step.idx, ok=True, duration_ms=duration)
            except Exception as e:
                return StepResult(idx=step.idx, ok=False, error=f"Navigation failed: {str(e)}")

        # 2. Resolve target element using Exactly-One Rule
        target, winning_loc = await resolve_locator(page, step.locators)
        if not target:
            return StepResult(
                idx=step.idx,
                ok=False,
                error=f"Step {step.idx} ({step.intent}): Could not resolve any locator to exactly one element"
            )

        # 3. Apply action
        try:
            if action == "fill":
                await target.fill(interpolated_val or "", timeout=5000)
            elif action == "click":
                await target.click(timeout=5000)
            elif action == "select":
                await target.select_option(interpolated_val or "", timeout=5000)
            elif action == "check":
                await target.check(timeout=5000)
            elif action == "press":
                await target.press(interpolated_val or "Enter", timeout=5000)
            else:
                return StepResult(idx=step.idx, ok=False, error=f"Unsupported action: {action}")

            # Settle after interaction
            await self._settle_page(page)
            duration = (time.time() - t0) * 1000
            return StepResult(
                idx=step.idx,
                ok=True,
                resolved_locator=winning_loc,
                duration_ms=duration
            )

        except Exception as e:
            duration = (time.time() - t0) * 1000
            return StepResult(
                idx=step.idx,
                ok=False,
                error=f"Action '{action}' failed on resolved element: {str(e)}",
                duration_ms=duration
            )

    async def execute_row(
        self,
        spec: WorkflowSpec,
        row_data: dict[str, Any],
        row_idx: int,
        browser: Browser,
        on_step_progress: Optional[Callable] = None
    ) -> RowResult:
        """
        Executes the entire workflow for a single input data row.
        Context isolation: creates a clean BrowserContext and Page.
        Halts the row if any step fails.
        """
        # Fresh isolated context per row
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            ignore_https_errors=True
        )
        page = await context.new_page()

        step_results: list[StepResult] = []
        final_shot = ""
        row_success = True

        try:
            # Navigate to workflow start URL if 1st step isn't goto
            if not spec.steps or spec.steps[0].action != "goto":
                await page.goto(spec.start_url)
                await self._settle_page(page)

            for step in spec.steps:
                res = await self.execute_step(page, step, row_data)
                step_results.append(res)

                if on_step_progress:
                    await on_step_progress(row_idx, step.idx, res)

                # Stop row immediately upon step failure
                if not res.ok:
                    row_success = False
                    break

            # Capture final screenshot
            final_shot = await self._capture_final_shot(page, row_idx)

        except Exception as e:
            row_success = False
            print(f"[Runner] Row {row_idx} unexpected failure: {e}")

        finally:
            await context.close()

        return RowResult(
            row_idx=row_idx,
            row_data=row_data,
            steps=step_results,
            success=row_success,
            final_shot=final_shot
        )

    async def execute_batch(
        self,
        spec: WorkflowSpec,
        rows: list[dict[str, Any]],
        headed: bool = False,
        on_step_progress: Optional[Callable] = None
    ) -> list[RowResult]:
        """
        Runs the workflow sequentially across all input data rows.
        """
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=not headed)
            results: list[RowResult] = []

            for i, row in enumerate(rows):
                res = await self.execute_row(
                    spec=spec,
                    row_data=row,
                    row_idx=i + 1,
                    browser=browser,
                    on_step_progress=on_step_progress
                )
                results.append(res)

            await browser.close()
            return results
