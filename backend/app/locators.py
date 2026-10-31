"""
Locator candidate generation and recorded event coalescing for DemoToSkill.
Follows strict Playwright fallback ordering:
1. Role + Accessible Name (get_by_role)
2. Label (get_by_label)
3. Placeholder (get_by_placeholder)
4. Visible Text (get_by_text)
5. Test ID (get_by_test_id)
6. CSS Selector (locator)
"""

import re
from typing import Optional, Any
from app.models import Locator, Step


def trim_dom_context(html: str, max_chars: int = 400) -> str:
    """Cleans up and limits outerHTML to approximately max_chars."""
    if not html:
        return ""
    # Normalize whitespaces
    compact = re.sub(r"\s+", " ", html).strip()
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3] + "..."


def sanitize_value(value: Optional[str], is_password: bool = False) -> Optional[str]:
    """Masks password input values for privacy compliance."""
    if is_password and value is not None:
        return "***"
    return value


def build_locators_for_element(element_data: dict[str, Any]) -> list[Locator]:
    """
    Builds an ordered list of locator candidates from captured DOM element metadata.
    Ordering:
    1. Role + Accessible Name
    2. Label
    3. Placeholder
    4. Visible Text
    5. Test ID
    6. CSS Selector
    """
    locators: list[Locator] = []

    role = (element_data.get("role") or "").strip()
    tag = (element_data.get("tag") or "").lower().strip()
    name = (element_data.get("accessible_name") or "").strip()
    label = (element_data.get("label") or "").strip()
    placeholder = (element_data.get("placeholder") or "").strip()
    text = (element_data.get("text") or "").strip()
    test_id = (element_data.get("testid") or "").strip()
    elem_id = (element_data.get("id") or "").strip()
    classes = element_data.get("classes") or []

    # Infer standard role if not explicitly set
    if not role:
        if tag == "button" or (tag == "input" and element_data.get("type") in ("button", "submit", "reset")):
            role = "button"
        elif tag == "a":
            role = "link"
        elif tag == "input" and element_data.get("type") in ("checkbox", "radio"):
            role = element_data.get("type")
        elif tag == "select":
            role = "combobox"
        elif tag in ("input", "textarea") and element_data.get("type") not in ("hidden", "file"):
            role = "textbox"

    # 1. Role + Accessible Name
    if role and name:
        locators.append(Locator(kind="role", value=role, name=name))

    # 2. Label
    if label and label != name:
        locators.append(Locator(kind="label", value=label))

    # 3. Placeholder
    if placeholder:
        locators.append(Locator(kind="placeholder", value=placeholder))

    # 4. Visible Text (if short and meaningful, e.g. < 50 chars)
    if text and text != name and text != label and len(text) < 50:
        locators.append(Locator(kind="text", value=text))

    # 5. Test ID
    if test_id:
        locators.append(Locator(kind="testid", value=test_id))

    # 6. CSS Selector candidates (prefer ID, then test-id, then tag + attributes)
    if elem_id and not elem_id.startswith("dyn_") and not elem_id.startswith("uid_"):
        # Avoid likely auto-generated / ephemeral dynamic IDs
        locators.append(Locator(kind="css", value=f"#{elem_id}"))

    # Tag + specific classes or attributes
    clean_classes = [c for c in classes if not re.search(r"\d{3,}", c) and len(c) < 30]
    if clean_classes and tag:
        class_sel = "." + ".".join(clean_classes[:2])
        locators.append(Locator(kind="css", value=f"{tag}{class_sel}"))
    elif elem_id:
        # Fallback CSS by id even if numeric
        locators.append(Locator(kind="css", value=f"#{elem_id}"))
    elif tag and (name or label):
        # Attribute selector fallback
        attr_val = name or label
        locators.append(Locator(kind="css", value=f'{tag}[aria-label="{attr_val}"]'))
    elif tag:
        locators.append(Locator(kind="css", value=tag))

    # Deduplicate while preserving order
    seen = set()
    unique_locators = []
    for loc in locators:
        key = (loc.kind, loc.value, loc.name)
        if key not in seen:
            seen.add(key)
            unique_locators.append(loc)

    return unique_locators


def coalesce_recorded_events(raw_events: list[dict[str, Any]]) -> list[Step]:
    """
    Coalesces raw recorded DOM events into standardized workflow Steps.
    - Merges consecutive typing events on the same element into a single 'fill'.
    - Maps checkbox toggles to 'check' or 'click'.
    - Formats dropdown selections as 'select'.
    - Sanitizes password fields.
    - Assigns monotonic step indices (1, 2, 3...).
    """
    coalesced: list[Step] = []
    pending_fill: Optional[dict[str, Any]] = None

    def flush_pending_fill():
        nonlocal pending_fill
        if pending_fill:
            elem_data = pending_fill.get("target", {})
            is_pwd = elem_data.get("type") == "password"
            val = sanitize_value(pending_fill.get("value", ""), is_pwd)

            coalesced.append(
                Step(
                    idx=len(coalesced) + 1,
                    action="fill",
                    locators=build_locators_for_element(elem_data),
                    value=val,
                    intent=f"Enter value into {elem_data.get('label') or elem_data.get('placeholder') or elem_data.get('name') or 'field'}",
                    shot_before=pending_fill.get("shot_before", ""),
                    shot_after=pending_fill.get("shot_after", ""),
                    dom_context=trim_dom_context(elem_data.get("outerHTML", ""))
                )
            )
            pending_fill = None

    for event in raw_events:
        action = event.get("action")
        target = event.get("target", {})
        target_id = target.get("id") or target.get("name") or target.get("selector") or str(id(target))

        # Check for consecutive input / fill events on the same target
        if action in ("input", "change"):
            tag = (target.get("tag") or "").lower()
            if tag == "select":
                # Select dropdown change is immediate, flush any text fill
                flush_pending_fill()
                coalesced.append(
                    Step(
                        idx=len(coalesced) + 1,
                        action="select",
                        locators=build_locators_for_element(target),
                        value=event.get("value"),
                        intent=f"Select {event.get('value')} in {target.get('label') or 'dropdown'}",
                        shot_before=event.get("shot_before", ""),
                        shot_after=event.get("shot_after", ""),
                        dom_context=trim_dom_context(target.get("outerHTML", ""))
                    )
                )
                continue

            # Text input or textarea
            if pending_fill and pending_fill.get("target_id") == target_id:
                # Update with latest value and after-shot
                pending_fill["value"] = event.get("value", "")
                if event.get("shot_after"):
                    pending_fill["shot_after"] = event.get("shot_after")
            else:
                flush_pending_fill()
                pending_fill = {
                    "target_id": target_id,
                    "target": target,
                    "value": event.get("value", ""),
                    "shot_before": event.get("shot_before", ""),
                    "shot_after": event.get("shot_after", "")
                }
            continue

        # If any other action arrives (e.g. click, press, goto), flush active typing
        flush_pending_fill()

        if action == "goto":
            coalesced.append(
                Step(
                    idx=len(coalesced) + 1,
                    action="goto",
                    value=event.get("url"),
                    intent=f"Navigate to {event.get('url')}",
                    shot_after=event.get("shot_after", "")
                )
            )
        elif action == "click":
            coalesced.append(
                Step(
                    idx=len(coalesced) + 1,
                    action="click",
                    locators=build_locators_for_element(target),
                    intent=f"Click {target.get('accessible_name') or target.get('text') or target.get('tag') or 'element'}",
                    shot_before=event.get("shot_before", ""),
                    shot_after=event.get("shot_after", ""),
                    dom_context=trim_dom_context(target.get("outerHTML", ""))
                )
            )
        elif action == "press":
            key = event.get("key", "Enter")
            coalesced.append(
                Step(
                    idx=len(coalesced) + 1,
                    action="press",
                    value=key,
                    locators=build_locators_for_element(target) if target else [],
                    intent=f"Press {key}",
                    shot_before=event.get("shot_before", ""),
                    shot_after=event.get("shot_after", "")
                )
            )

    # Final flush if input was last recorded event
    flush_pending_fill()

    return coalesced

