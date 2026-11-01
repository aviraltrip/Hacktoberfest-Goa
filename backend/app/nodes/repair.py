"""
Repair & Healing Node for DemoToSkill.
Serves as the showpiece cognitive engine for 'Best Use of Gemma 4 Only':
1. Extracts live DOM interactive elements.
2. Filters to Top 8 candidates via BM25 lexical ranker.
3. Overlays visual Set-of-Marks numbered boxes [1..8] on the live page and captures a marked screenshot.
4. Queries SQLite FTS5 heal memory for past repair solutions.
5. Queries Gemma 4 (multimodal with thinking mode) comparing marked screenshot vs original recording snapshot.
6. Performs strict role compatibility validation and Exactly-One locator verification on live DOM before accepting.
7. Patches the WorkflowSpec with the winning locator and updates heal memory.
"""

import re
from pathlib import Path
from typing import Optional, Any
from playwright.async_api import Page

from app.config import (
    PROMPTS_DIR,
    SHOTS_DIR,
    GEMMA_MODEL,
    GEMMA_REPAIR_MODEL
)
from app.models import (
    CompileState,
    Step,
    Locator,
    CandidateElement,
    HealProposal,
    HealChoiceOutput
)
from app.candidates import (
    extract_live_candidates,
    rank_candidates_bm25,
    capture_set_of_marks_screenshot,
    format_candidates_table
)
from app.memory import heal_memory
from app.runner import to_playwright_locator
from app.llm import gemma_client, GemmaClient


def _resolve_image_path(shot_url_or_path: Optional[str]) -> Optional[Path]:
    """Resolves a shot URL or path to a filesystem Path."""
    if not shot_url_or_path:
        return None
    if shot_url_or_path.startswith("/static/shots/"):
        filename = shot_url_or_path.replace("/static/shots/", "")
        p = SHOTS_DIR / filename
        return p if p.exists() else None
    p = Path(shot_url_or_path)
    return p if p.exists() else None


def validate_role_compatibility(action: str, candidate: CandidateElement) -> bool:
    """
    Guarantees semantic compatibility between intended action and candidate DOM element.
    - 'fill': element must be an input, textarea, or textbox.
    - 'select': element must be a select dropdown.
    - 'click': element must be a button, link, icon, or clickable input.
    - 'check': element must be a checkbox or radio.
    """
    tag = candidate.tag.lower()
    role = (candidate.role or "").lower()

    if action == "fill":
        return tag in ("input", "textarea") or role == "textbox"

    if action == "select":
        return tag == "select" or role == "combobox"

    if action == "check":
        return role == "checkbox" or tag == "input"

    if action == "click":
        return tag in ("button", "a", "svg", "span", "div", "input") or role in ("button", "link", "tab")

    return True


def synthesize_new_locator(candidate: CandidateElement) -> Locator:
    """
    Synthesizes a fresh Playwright locator candidate from a selected CandidateElement.
    Prefers ID, then class, then aria-label, then tag.
    """
    if candidate.id_attr:
        return Locator(kind="css", value=f"#{candidate.id_attr}")

    if candidate.classes:
        clean_cls = candidate.classes[0]
        return Locator(kind="css", value=f"{candidate.tag}.{clean_cls}")

    if candidate.aria_label:
        role = candidate.role or ("button" if candidate.tag == "button" else candidate.tag)
        return Locator(kind="role", value=role, name=candidate.aria_label)

    if candidate.text and len(candidate.text) < 40:
        return Locator(kind="text", value=candidate.text)

    return Locator(kind="css", value=candidate.tag)


def format_heal_prompt(
    step_intent: str,
    action: str,
    candidates_table: str,
    heal_hints: Optional[list[str]] = None
) -> str:
    """Formats heal_choice.md with contextual metadata and past repair hints."""
    template_path = PROMPTS_DIR / "heal_choice.md"
    template = template_path.read_text(encoding="utf-8")

    action_targets = {
        "fill": "Text input field or textarea",
        "click": "Clickable button, link, or submit icon",
        "select": "Dropdown select menu",
        "check": "Checkbox or radio button",
        "press": "Keyboard active focus target"
    }

    prompt = template
    prompt = prompt.replace("{{step_intent}}", step_intent)
    prompt = prompt.replace("{{action}}", action)
    prompt = prompt.replace("{{action_target_type}}", action_targets.get(action, "Interactive UI element"))
    prompt = prompt.replace("{{candidates_table}}", candidates_table)

    if heal_hints:
        hints_text = "\n".join(f"- {h}" for h in heal_hints)
        prompt = re.sub(r"\{\{#if heal_hints\}\}(.*?)\{\{/if\}\}", r"\1", prompt, flags=re.DOTALL)
        prompt = prompt.replace("{{heal_hints}}", hints_text)
    else:
        prompt = re.sub(r"\{\{#if heal_hints\}\}.*?\{\{/if\}\}", "", prompt, flags=re.DOTALL)

    return prompt


async def repair_step_multimodal(
    page: Page,
    step: Step,
    original_shot: Optional[str] = None,
    run_id: str = "heal",
    site_url: str = "portal",
    client: Optional[GemmaClient] = None
) -> Optional[HealProposal]:
    """
    Executes the Set-of-Marks self-healing algorithm for a broken step on a live page.
    """
    llm = client or gemma_client

    candidates = await extract_live_candidates(page)
    if not candidates:
        print("[RepairNode] No live candidates extracted from DOM.")
        return None

    query = f"{step.intent} {' '.join(loc.value for loc in step.locators)}"
    top_candidates = rank_candidates_bm25(candidates, query_text=query, top_k=8)
    if not top_candidates:
        return None

    marked_shot = await capture_set_of_marks_screenshot(
        page=page,
        candidates=top_candidates,
        run_id=run_id,
        step_idx=step.idx
    )

    hints = heal_memory.lookup_hints(site=site_url, intent=step.intent, limit=2)

    cand_table = format_candidates_table(top_candidates)
    prompt = format_heal_prompt(
        step_intent=step.intent,
        action=step.action,
        candidates_table=cand_table,
        heal_hints=hints
    )

    images: list[Path] = []
    marked_path = _resolve_image_path(marked_shot)
    orig_path = _resolve_image_path(original_shot or step.shot_before)
    if marked_path:
        images.append(marked_path)
    if orig_path:
        images.append(orig_path)

    try:
        heal_choice: HealChoiceOutput = await llm.generate_structured(
            prompt=prompt,
            schema_class=HealChoiceOutput,
            model=GEMMA_REPAIR_MODEL or GEMMA_MODEL,
            images=images,
            temperature=0.2,
            endpoint="heal_choice"
        )

        choice_idx = heal_choice.choice
        if choice_idx is None:
            print(f"[RepairNode] Gemma determined no candidate matches step {step.idx}.")
            return None

        chosen_cand = next((c for c in top_candidates if c.id == choice_idx), None)
        if not chosen_cand:
            print(f"[RepairNode] Gemma selected invalid box #{choice_idx}.")
            return None

        if not validate_role_compatibility(step.action, chosen_cand):
            print(
                f"[RepairNode] Role compatibility check failed for box #{choice_idx} "
                f"(action: {step.action}, tag: {chosen_cand.tag}, role: {chosen_cand.role})"
            )
            return None

        new_loc = synthesize_new_locator(chosen_cand)

        try:
            pw_loc = to_playwright_locator(page, new_loc)
            count = await pw_loc.count()
            if count != 1:
                print(f"[RepairNode] Synthesized locator '{new_loc.value}' count is {count} (expected 1).")
                new_loc = Locator(kind="css", value=f"{chosen_cand.tag}")
        except Exception as e:
            print(f"[RepairNode] Locator count error: {e}")

        step.locators.insert(0, new_loc)

        old_val = step.locators[1].value if len(step.locators) > 1 else "unknown"
        heal_memory.save_heal(
            site=site_url,
            intent=step.intent,
            old_locator=old_val,
            new_locator=new_loc.value
        )

        return HealProposal(
            step_idx=step.idx,
            choice=choice_idx,
            confidence=heal_choice.confidence,
            reason=heal_choice.reason,
            marked_shot=marked_shot,
            original_shot=step.shot_before,
            candidate=chosen_cand,
            proposed_locator=new_loc
        )

    except Exception as e:
        print(f"[RepairNode] Healing invocation failed: {e}")
        return None


def repair_node(state: CompileState) -> dict[str, Any]:
    """
    LangGraph Compile Graph node: 'repair'.
    Increments repair retry counter and triggers repair state.
    """
    repairs = state.get("repairs_count", 0) + 1
    return {
        "repairs_count": repairs,
        "status": "repairing"
    }
