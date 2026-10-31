"""
Live DOM Candidate Extraction, BM25 Ranking, and Set-of-Marks Overlay for DemoToSkill.
Extracts visible interactive elements from the live page without external models,
ranks them via BM25, and injects dynamic visual numbered bounding badges (Set-of-Marks)
so Gemma 4 can select target elements visually without fragile pixel guessing.
"""

import re
import json
from typing import Optional, Any
from rank_bm25 import BM25Okapi
from playwright.async_api import Page

from app.config import SHOTS_DIR
from app.imaging import resize_and_compress_image, save_screenshot_bytes
from app.models import CandidateElement


# JavaScript function injected into live page to extract visible interactive elements
EXTRACT_CANDIDATES_JS = """
(() => {
  const elements = [];
  const query = 'button, a, input, select, textarea, [role="button"], [role="link"], [role="combobox"], [role="checkbox"], [tabindex]';
  const nodes = document.querySelectorAll(query);

  let counter = 0;
  for (const el of nodes) {
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
      continue;
    }
    const rect = el.getBoundingClientRect();
    if (rect.width <= 4 || rect.height <= 4) {
      continue;
    }

    let label = '';
    if (el.labels && el.labels.length > 0) {
      label = el.labels[0].innerText.trim();
    } else if (el.id) {
      const lblNode = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (lblNode) label = lblNode.innerText.trim();
    }

    counter++;
    elements.push({
      id: counter,
      tag: el.tagName.toLowerCase(),
      role: el.getAttribute('role') || '',
      type: el.getAttribute('type') || '',
      text: (el.innerText || '').trim().substring(0, 80),
      aria_label: el.getAttribute('aria-label') || label || '',
      placeholder: el.getAttribute('placeholder') || '',
      id_attr: el.id || '',
      classes: Array.from(el.classList || []),
      bbox: {
        x: Math.round(rect.x),
        y: Math.round(rect.y),
        width: Math.round(rect.width),
        height: Math.round(rect.height)
      }
    });
  }

  return elements;
})();
"""


# JavaScript injected to overlay numbered Set-of-Marks badges over candidate bounding boxes
INJECT_SOM_JS = """
(candidates) => {
  // Remove any preexisting overlay
  const existing = document.getElementById('__demotoskill_som_container');
  if (existing) existing.remove();

  const container = document.createElement('div');
  container.id = '__demotoskill_som_container';
  container.style.position = 'fixed';
  container.style.top = '0';
  container.style.left = '0';
  container.style.width = '100vw';
  container.style.height = '100vh';
  container.style.pointerEvents = 'none';
  container.style.zIndex = '2147483647';

  // Distinct high-contrast palette
  const colors = [
    '#dc2626', // Red
    '#2563eb', // Blue
    '#16a34a', // Green
    '#d97706', // Amber
    '#9333ea', // Purple
    '#0891b2', // Cyan
    '#ea580c', // Orange
    '#db2777'  // Pink
  ];

  candidates.forEach((cand, idx) => {
    const bbox = cand.bbox;
    if (!bbox || bbox.width <= 0 || bbox.height <= 0) return;

    const color = colors[idx % colors.length];

    // Bounding box border
    const box = document.createElement('div');
    box.style.position = 'absolute';
    box.style.left = `${bbox.x}px`;
    box.style.top = `${bbox.y}px`;
    box.style.width = `${bbox.width}px`;
    box.style.height = `${bbox.height}px`;
    box.style.border = `3px solid ${color}`;
    box.style.boxSizing = 'border-box';
    box.style.borderRadius = '4px';

    // Numbered Badge
    const badge = document.createElement('div');
    badge.innerText = `${cand.id}`;
    badge.style.position = 'absolute';
    badge.style.top = '-14px';
    badge.style.left = '-14px';
    badge.style.backgroundColor = color;
    badge.style.color = '#ffffff';
    badge.style.fontSize = '14px';
    badge.style.fontWeight = 'bold';
    badge.style.fontFamily = 'monospace, sans-serif';
    badge.style.width = '26px';
    badge.style.height = '26px';
    badge.style.lineHeight = '26px';
    badge.style.textAlign = 'center';
    badge.style.borderRadius = '50%';
    badge.style.boxShadow = '0 2px 4px rgba(0,0,0,0.4)';
    badge.style.border = '2px solid #ffffff';

    box.appendChild(badge);
    container.appendChild(box);
  });

  document.body.appendChild(container);
};
"""

CLEAR_SOM_JS = """
(() => {
  const container = document.getElementById('__demotoskill_som_container');
  if (container) container.remove();
})();
"""


async def extract_live_candidates(page: Page) -> list[CandidateElement]:
    """
    Extracts all visible, interactive DOM elements from the live page.
    """
    try:
        raw_list = await page.evaluate(EXTRACT_CANDIDATES_JS)
        candidates = []
        for item in raw_list:
            cand = CandidateElement(
                id=item.get("id", 0),
                tag=item.get("tag", "div"),
                role=item.get("role") or None,
                text=item.get("text") or None,
                aria_label=item.get("aria_label") or None,
                placeholder=item.get("placeholder") or None,
                id_attr=item.get("id_attr") or None,
                classes=item.get("classes") or [],
                bbox=item.get("bbox") or {}
            )
            candidates.append(cand)
        return candidates
    except Exception as e:
        print(f"[Candidates] Error evaluating live candidates: {e}")
        return []


def rank_candidates_bm25(
    candidates: list[CandidateElement],
    query_text: str,
    top_k: int = 8
) -> list[CandidateElement]:
    """
    Applies vectorless lexical BM25 ranking over live candidates.
    Corpus: tag, role, text, aria-label, classes, and ID.
    Query: step intent + old locator values.
    Returns the top_k elements re-indexed with IDs [1..top_k].
    """
    if not candidates:
        return []

    # Tokenize query
    query_tokens = [t.lower() for t in re.findall(r"\w+", query_text) if len(t) > 1]

    # Tokenize corpus documents
    corpus_tokens = []
    for c in candidates:
        doc = f"{c.tag} {c.role or ''} {c.text or ''} {c.aria_label or ''} {' '.join(c.classes)} {c.id_attr or ''} {c.placeholder or ''}"
        tokens = [t.lower() for t in re.findall(r"\w+", doc)]
        corpus_tokens.append(tokens if tokens else ["element"])

    if not query_tokens:
        sorted_by_area = sorted(
            candidates,
            key=lambda c: (c.bbox.get("width", 0) * c.bbox.get("height", 0)),
            reverse=True
        )[:top_k]
        for idx, item in enumerate(sorted_by_area, 1):
            item.id = idx
            item.bm25_score = 0.0
        return sorted_by_area

    bm25 = BM25Okapi(corpus_tokens)
    scores = bm25.get_scores(query_tokens)

    for i, c in enumerate(candidates):
        c.bm25_score = float(scores[i])

    ranked = sorted(candidates, key=lambda c: c.bm25_score, reverse=True)
    top_candidates = ranked[:top_k]

    for idx, item in enumerate(top_candidates, 1):
        item.id = idx

    return top_candidates


async def capture_set_of_marks_screenshot(
    page: Page,
    candidates: list[CandidateElement],
    run_id: str,
    step_idx: int
) -> str:
    """
    Injects numbered Set-of-Marks overlay [1..8], takes a snapshot,
    clears overlay, and returns the saved JPEG filepath.
    """
    cand_dicts = [c.model_dump() for c in candidates]
    try:
        # 1. Inject overlay
        await page.evaluate(INJECT_SOM_JS, cand_dicts)

        # 2. Capture screenshot with overlay
        raw_png = await page.screenshot(type="png", full_page=False)
        compressed_jpeg = resize_and_compress_image(raw_png)

        filename = f"heal_{run_id}_step_{step_idx}_marked.jpg"
        save_screenshot_bytes(compressed_jpeg, filename)

        # 3. Clean up overlay
        await page.evaluate(CLEAR_SOM_JS)

        return f"/static/shots/{filename}"

    except Exception as e:
        print(f"[SetOfMarks] Overlay error: {e}")
        try:
            await page.evaluate(CLEAR_SOM_JS)
        except Exception:
            pass
        return ""


def format_candidates_table(candidates: list[CandidateElement]) -> str:
    """
    Formats the candidates list into a clean Markdown table for the Gemma 4 prompt.
    """
    lines = [
        "| Box # | Tag | Role | Visible Text | Aria-Label / Label | Classes / ID |",
        "| :---: | :--- | :--- | :--- | :--- | :--- |"
    ]
    for c in candidates:
        text_disp = f"'{c.text}'" if c.text else "(none)"
        aria_disp = f"'{c.aria_label}'" if c.aria_label else "(none)"
        cls_id = f"#{c.id_attr}" if c.id_attr else (f".{c.classes[0]}" if c.classes else "")
        role_disp = c.role or "(implicit)"
        lines.append(f"| **{c.id}** | `<{c.tag}>` | {role_disp} | {text_disp} | {aria_disp} | {cls_id} |")

    return "\n".join(lines)
