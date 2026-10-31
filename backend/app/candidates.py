"""
Live DOM Candidate Extraction and BM25 Ranking for DemoToSkill.
Extracts visible interactive elements from the live page without external models,
and applies BM25 lexical ranking against the failed step's intent and old locators
to select the Top 8 candidate elements for Set-of-Marks visual prompting.
"""

import re
from typing import Optional, Any
from rank_bm25 import BM25Okapi
from playwright.async_api import Page

from app.models import CandidateElement


# JavaScript function injected into live page to extract visible interactive elements
EXTRACT_CANDIDATES_JS = """
(() => {
  const elements = [];
  const query = 'button, a, input, select, textarea, [role="button"], [role="link"], [role="combobox"], [role="checkbox"], [tabindex]';
  const nodes = document.querySelectorAll(query);

  let counter = 0;
  for (const el of nodes) {
    // Check visibility
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
      continue;
    }
    const rect = el.getBoundingClientRect();
    if (rect.width <= 4 || rect.height <= 4) {
      continue;
    }

    // Accessible label deduction
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

    # If query is empty or no valid tokens, select top candidates by visual area
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

    # Rank with BM25
    bm25 = BM25Okapi(corpus_tokens)
    scores = bm25.get_scores(query_tokens)

    for i, c in enumerate(candidates):
        c.bm25_score = float(scores[i])

    # Sort descending by BM25 score
    ranked = sorted(candidates, key=lambda c: c.bm25_score, reverse=True)

    # If Top BM25 scores are all 0, blend with visible elements
    top_candidates = ranked[:top_k]

    # Assign sequential numeric marker badges [1..N]
    for idx, item in enumerate(top_candidates, 1):
        item.id = idx

    return top_candidates
