// onload.js — Instant Data Scraper (enhanced content script)
// ChatGPT — adds text search, candidate cycling, and target override.
// This script is self-contained and avoids external dependencies.

(() => {
  'use strict';

  // =========================
  // State
  // =========================
  let forcedTargetSelector = null;     // High-priority target set by search
  let candidates = [];                 // Detected tables/lists on page
  let candidateIndex = -1;             // Current position in candidates
  let highlightEl = null;              // Outline/highlight overlay
  let lastPreviewed = null;            // The last element we previewed

  // =========================
  // Utilities
  // =========================
  const raf = (cb) => (window.requestAnimationFrame ? requestAnimationFrame(cb) : setTimeout(cb, 0));

  function isElement(el) {
    return el && el.nodeType === 1;
  }

  function isVisible(el) {
    if (!isElement(el)) return false;
    const style = window.getComputedStyle(el);
    if (!style || style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity || '1') === 0) return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }

  function getText(el) {
    return (el.textContent || '').replace(/\s+/g, ' ').trim();
  }

  function scoreTextMatch(text, query) {
    const t = text.toLowerCase();
    const q = query.toLowerCase();
    if (!t || !q || !t.includes(q)) return 0;
    if (t === q) return 1000;
    if (t.startsWith(q)) return 600;
    return 400; // contains
  }

  function uniqueSelector(el) {
    if (!isElement(el)) return null;
    const parts = [];
    while (el && el.nodeType === 1 && el !== document.body) {
      const tag = el.tagName.toLowerCase();
      if (el.id) {
        parts.unshift(`${tag}#${CSS.escape(el.id)}`);
        break;
      }
      const parent = el.parentElement;
      if (!parent) {
        parts.unshift(tag);
        break;
      }
      const siblings = Array.from(parent.children).filter(c => c.tagName === el.tagName);
      const idx = siblings.indexOf(el) + 1;
      parts.unshift(`${tag}:nth-of-type(${idx})`);
      el = parent;
    }
    return parts.join(' > ');
  }

  function nearestContainer(el) {
    if (!isElement(el)) return null;
    // Prefer table/grid containers
    const tableish = el.closest('table, [role="table"], [role="grid"], .table, .data-table, .grid, .ag-center-cols-container');
    if (tableish) return tableish;

    // Heuristic: climb to a parent whose children look like repeated rows/cards
    let p = el;
    for (let i = 0; i < 6 && p && p.parentElement; i++) {
      const parent = p.parentElement;
      const kids = Array.from(parent.children);
      const sameTag = kids.filter(k => k.tagName === p.tagName);
      // if many siblings share structure or ARIA roles indicating row/listitem
      const rowish = kids.filter(k => {
        const role = (k.getAttribute('role') || '').toLowerCase();
        return role === 'row' || role === 'listitem';
      });
      if (sameTag.length >= 3 || rowish.length >= 3) return parent;
      p = parent;
    }
    return el;
  }

  function scrollIntoViewIfNeeded(el) {
    try {
      el.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'smooth' });
    } catch {
      // ignore
    }
  }

  // =========================
  // Highlight overlay
  // =========================
  function ensureHighlighter() {
    if (highlightEl) return highlightEl;
    const el = document.createElement('div');
    el.setAttribute('data-ids-highlight', 'true');
    Object.assign(el.style, {
      position: 'fixed',
      zIndex: '2147483647',
      pointerEvents: 'none',
      border: '2px solid #4C9AFF',
      boxShadow: '0 0 0 2px rgba(76,154,255,0.25)',
      borderRadius: '4px',
      transition: 'all 80ms ease',
      left: '0px',
      top: '0px',
      width: '0px',
      height: '0px',
      display: 'none'
    });
    document.documentElement.appendChild(el);
    highlightEl = el;
    return el;
  }

  function highlightTarget(el) {
    if (!isElement(el) || !isVisible(el)) {
      hideHighlight();
      return;
    }
    const rect = el.getBoundingClientRect();
    const hl = ensureHighlighter();
    hl.style.display = 'block';
    hl.style.left = `${Math.max(0, rect.left + window.scrollX)}px`;
    hl.style.top = `${Math.max(0, rect.top + window.scrollY)}px`;
    hl.style.width = `${Math.max(0, rect.width)}px`;
    hl.style.height = `${Math.max(0, rect.height)}px`;
  }

  function hideHighlight() {
    if (highlightEl) highlightEl.style.display = 'none';
  }

  // Keep highlight aligned on resize/scroll
  window.addEventListener('scroll', () => {
    if (lastPreviewed) raf(() => highlightTarget(lastPreviewed));
  }, { passive: true });
  window.addEventListener('resize', () => {
    if (lastPreviewed) raf(() => highlightTarget(lastPreviewed));
  });

  // =========================
  // Candidate detection
  // =========================
  function collectCandidates() {
    const found = new Set();

    // Native tables
    document.querySelectorAll('table').forEach(t => {
      if (isVisible(t) && t.rows && t.rows.length) found.add(t);
    });

    // ARIA tables/grids
    document.querySelectorAll('[role="table"], [role="grid"]').forEach(t => {
      if (isVisible(t)) found.add(t);
    });

    // Common data table classes and list containers
    document.querySelectorAll(`
      .table, .data-table, .dataTable, .grid, .ag-root, .ag-center-cols-container,
      [role="rowgroup"], [role="list"], ul, ol
    `).forEach(el => {
      if (!isVisible(el)) return;
      // Heuristic: must have repeated children or rows
      const kids = Array.from(el.children || []);
      if (kids.length >= 3) found.add(el);
    });

    // Deduplicate by element
    const list = Array.from(found);
    // Prefer larger/denser containers first
    const scored = list.map(el => {
      const rect = el.getBoundingClientRect();
      const area = Math.max(1, rect.width * rect.height);
      let rows = 0;
      if (el.tagName === 'TABLE' && el.rows) rows = el.rows.length;
      else rows = (el.querySelectorAll('tr,[role="row"],li,[role="listitem"]').length) || 0;

      const textLen = getText(el).length;
      const score = Math.min(1000, Math.round(area / 1000)) + Math.min(400, rows * 10) + Math.min(300, Math.round(textLen / 50));
      return { el, score };
    });

    scored.sort((a, b) => b.score - a.score);
    return scored.map(s => s.el);
  }

  // =========================
  // Search for data (text)
  // =========================
  function findBestNodeByText(query) {
    if (!query || !query.trim()) return null;

    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const scoredNodes = [];
    while (walker.nextNode()) {
      const node = walker.currentNode;
      const parent = node.parentElement;
      if (!parent || !isVisible(parent)) continue;

      const score = scoreTextMatch(getText(node), query);
      if (score > 0) {
        scoredNodes.push({ node: parent, score });
      }
    }

    if (!scoredNodes.length) return null;
    scoredNodes.sort((a, b) => b.score - a.score);
    return scoredNodes[0].node;
  }

  // =========================
  // Core logic
  // =========================
  function previewCandidate(el) {
    if (!isElement(el)) {
      hideHighlight();
      lastPreviewed = null;
      return;
    }
    scrollIntoViewIfNeeded(el);
    highlightTarget(el);
    lastPreviewed = el;
    // This is where you would typically send data to the popup for preview
  }

  function cycleNext() {
    if (!candidates.length) {
      candidates = collectCandidates();
      candidateIndex = -1;
    }
    candidateIndex = (candidateIndex + 1) % candidates.length;
    const nextEl = candidates[candidateIndex];
    previewCandidate(nextEl);
  }

  function setForcedTarget(selector) {
    forcedTargetSelector = selector;
    try {
      const el = document.querySelector(selector);
      if (el) {
        previewCandidate(el);
      } else {
        hideHighlight();
        lastPreviewed = null;
      }
    } catch (e) {
      console.warn('[IDS] Invalid selector:', selector);
      hideHighlight();
      lastPreviewed = null;
    }
  }

  // =========================
  // Message listeners
  // =========================
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    switch (message.type) {
      case 'ids:cycle-next-table':
        cycleNext();
        sendResponse({ status: 'ok' });
        break;

      case 'ids:find-node-by-text':
        const foundNode = findBestNodeByText(message.query);
        if (foundNode) {
          const container = nearestContainer(foundNode);
          const selector = uniqueSelector(container);
          sendResponse({ selector });
        } else {
          sendResponse({ selector: null });
        }
        break;

      case 'ids:set-target-selector':
        setForcedTarget(message.selector);
        sendResponse({ status: 'ok' });
        break;

      case 'ids:refresh-preview':
        const target = forcedTargetSelector ? document.querySelector(forcedTargetSelector) : (candidates[candidateIndex] || null);
        if (target) {
          previewCandidate(target);
        }
        sendResponse({ status: 'ok' });
        break;
    }
    // Keep message channel open for async responses
    return true;
  });

  // Initial state
  candidates = collectCandidates();
  if (candidates.length > 0) {
    candidateIndex = 0;
    previewCandidate(candidates[0]);
  }

  // Signal to the background script that the content script is ready.
  chrome.runtime.sendMessage({ type: 'ids:content-script-ready' });
})();