"""
Client-side JavaScript injected into the recording browser page.
Monitors user clicks, inputs, selections, and keystrokes,
extracts rich DOM accessibility and structural metadata,
and relays events back to Python via window.__record.
"""

INJECTED_RECORDER_JS = """
(() => {
  if (window.__demotoskill_recorder_active) return;
  window.__demotoskill_recorder_active = true;

  function getElementLabel(elem) {
    if (!elem) return '';
    if (elem.labels && elem.labels.length > 0) {
      return elem.labels[0].innerText.trim();
    }
    if (elem.id) {
      const labelElem = document.querySelector(`label[for="${CSS.escape(elem.id)}"]`);
      if (labelElem) return labelElem.innerText.trim();
    }
    const parentLabel = elem.closest('label');
    if (parentLabel) return parentLabel.innerText.trim();
    return '';
  }

  function getAccessibleName(elem) {
    if (!elem) return '';
    const ariaLabel = elem.getAttribute('aria-label');
    if (ariaLabel) return ariaLabel.trim();

    const ariaLabelledBy = elem.getAttribute('aria-labelledby');
    if (ariaLabelledBy) {
      const target = document.getElementById(ariaLabelledBy);
      if (target) return target.innerText.trim();
    }

    const label = getElementLabel(elem);
    if (label) return label;

    const img = elem.querySelector('img[alt]');
    if (img && img.alt) return img.alt.trim();

    const title = elem.getAttribute('title');
    if (title) return title.trim();

    const placeholder = elem.getAttribute('placeholder');
    if (placeholder) return placeholder.trim();

    const tag = elem.tagName.toLowerCase();
    if (['button', 'a'].includes(tag) || elem.getAttribute('role') === 'button') {
      const text = (elem.innerText || '').trim();
      if (text && text.length < 60) return text;
    }

    return '';
  }

  function extractElementData(elem) {
    if (!elem || !(elem instanceof Element)) return {};
    const rect = elem.getBoundingClientRect();
    const tag = elem.tagName.toLowerCase();

    let outer = elem.outerHTML || '';
    if (outer.length > 300) {
      outer = outer.substring(0, 300) + '...';
    }
    let parentOuter = elem.parentElement ? (elem.parentElement.outerHTML || '') : '';
    if (parentOuter.length > 300) {
      parentOuter = parentOuter.substring(0, 300) + '...';
    }

    return {
      tag: tag,
      role: elem.getAttribute('role') || '',
      type: elem.getAttribute('type') || '',
      id: elem.id || '',
      testid: elem.getAttribute('data-testid') || elem.getAttribute('data-test') || elem.getAttribute('data-cy') || '',
      accessible_name: getAccessibleName(elem),
      label: getElementLabel(elem),
      placeholder: elem.getAttribute('placeholder') || '',
      text: (elem.innerText || '').trim().substring(0, 80),
      classes: Array.from(elem.classList || []),
      outerHTML: `${outer} (Parent: ${parentOuter})`,
      bbox: {
        x: Math.round(rect.x),
        y: Math.round(rect.y),
        width: Math.round(rect.width),
        height: Math.round(rect.height)
      }
    };
  }

  function dispatchRecord(payload) {
    if (typeof window.__record === 'function') {
      try {
        window.__record(payload);
      } catch (err) {
        console.warn('[DemoToSkill Recorder] Dispatch error:', err);
      }
    }
  }

  document.addEventListener('click', (e) => {
    if (e.button !== 0) return;
    const target = e.target.closest('button, a, input, select, textarea, [role="button"], [tabindex], label') || e.target;
    if (!target) return;

    if (target.type === 'password') {
      return;
    }

    dispatchRecord({
      action: 'click',
      target: extractElementData(target),
      timestamp: Date.now()
    });
  }, true);

  let inputTimer = null;
  document.addEventListener('input', (e) => {
    const target = e.target;
    if (!target || !['input', 'textarea'].includes(target.tagName.toLowerCase())) return;

    const val = target.type === 'password' ? '***' : target.value;

    clearTimeout(inputTimer);
    inputTimer = setTimeout(() => {
      dispatchRecord({
        action: 'input',
        value: val,
        target: extractElementData(target),
        timestamp: Date.now()
      });
    }, 250);
  }, true);

  document.addEventListener('change', (e) => {
    const target = e.target;
    if (!target) return;
    const tag = target.tagName.toLowerCase();

    if (tag === 'select') {
      dispatchRecord({
        action: 'change',
        value: target.value,
        target: extractElementData(target),
        timestamp: Date.now()
      });
    } else if (tag === 'input' && ['checkbox', 'radio'].includes(target.type)) {
      dispatchRecord({
        action: 'click',
        value: target.checked ? 'true' : 'false',
        target: extractElementData(target),
        timestamp: Date.now()
      });
    }
  }, true);

  document.addEventListener('keydown', (e) => {
    if (['Enter', 'Tab'].includes(e.key)) {
      const target = e.target;
      dispatchRecord({
        action: 'press',
        key: e.key,
        target: extractElementData(target),
        timestamp: Date.now()
      });
    }
  }, true);

  console.log('[DemoToSkill Recorder] Injected and listening for interactions.');
})();
"""

