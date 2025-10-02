// onload.js — Instant Data Scraper (enhanced content script)
// This script is self-contained and avoids external dependencies.

(() => {
  'use strict';

  // =========================
  // State
  // =========================
  let forcedTargetSelector = null;
  let candidates = [];
  let candidateIndex = -1;
  let highlightEl = null;
  let lastPreviewed = null;
  let nextButtonEl = null;
  let isCrawling = false;

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
    const tableish = el.closest('table, [role="table"], [role="grid"], .table, .data-table, .grid, .ag-center-cols-container');
    if (tableish) return tableish;

    let p = el;
    for (let i = 0; i < 6 && p && p.parentElement; i++) {
      const parent = p.parentElement;
      const kids = Array.from(parent.children);
      const sameTag = kids.filter(k => k.tagName === p.tagName);
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
    document.querySelectorAll('table').forEach(t => {
      if (isVisible(t) && t.rows && t.rows.length) found.add(t);
    });
    document.querySelectorAll('[role="table"], [role="grid"]').forEach(t => {
      if (isVisible(t)) found.add(t);
    });
    document.querySelectorAll('.table, .data-table, .dataTable, .grid, .ag-root, .ag-center-cols-container, [role="rowgroup"], [role="list"], ul, ol').forEach(el => {
      if (!isVisible(el)) return;
      const kids = Array.from(el.children || []);
      if (kids.length >= 3) found.add(el);
    });
    const list = Array.from(found);
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
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
    let bestNode = null;
    let maxScore = 0;
    while (walker.nextNode()) {
      const node = walker.currentNode;
      const parent = node.parentElement;
      if (!parent || !isVisible(parent)) continue;
      const text = node.nodeValue || '';
      const score = scoreTextMatch(text, query);
      if (score > maxScore) {
        maxScore = score;
        bestNode = parent;
      }
    }
    return bestNode;
  }

  function findNextButton() {
    const linkSelectors = 'a, button';
    const nextText = ['next', 'more', '›', '»'];

    const elements = document.querySelectorAll(linkSelectors);
    for (const el of elements) {
        if (isVisible(el)) {
            const text = getText(el).toLowerCase();
            for (const t of nextText) {
                if (text.includes(t)) {
                    return el;
                }
            }
        }
    }
    return null;
  }

  // =========================
  // Data Scraping
  // =========================
  function scrapeDataFromElement(el) {
    if (!el) return [];
    const data = [];
    const rows = el.querySelectorAll('tr, [role="row"], li');
    if (rows.length > 0) {
      rows.forEach(row => {
        const rowData = [];
        const cells = row.querySelectorAll('td, th, [role="cell"], [role="gridcell"]');
        if (cells.length > 0) {
          cells.forEach(cell => {
            rowData.push(getText(cell));
          });
          data.push(rowData);
        } else {
          const cellText = getText(row);
          if (cellText) data.push([cellText]);
        }
      });
    } else {
      Array.from(el.children).forEach(child => {
        const childText = getText(child);
        if (childText) data.push([childText]);
      });
    }
    return data;
  }

  async function crawl(infiniteScroll) {
    if (!isCrawling) return;

    const currentTarget = forcedTargetSelector ? document.querySelector(forcedTargetSelector) : (candidates[candidateIndex] || null);
    if (currentTarget) {
      const data = scrapeDataFromElement(currentTarget);
      if (typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.sendMessage) {
        chrome.runtime.sendMessage({ type: 'ids:data-scraped', data });
      }
    }

    if (infiniteScroll) {
      window.scrollTo(0, document.body.scrollHeight);
    } else if (nextButtonEl) {
      nextButtonEl.click();
    } else {
      isCrawling = false;
      if (typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.sendMessage) {
        chrome.runtime.sendMessage({ type: 'ids:crawling-finished' });
      }
      return;
    }

    await new Promise(resolve => setTimeout(resolve, 2000 + Math.random() * 1000));
    crawl(infiniteScroll);
  }

  // =========================
  // Message Handling
  // =========================
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    switch (message.type) {
      case 'ids:initialize': {
        candidates = collectCandidates();
        candidateIndex = candidates.length > 0 ? 0 : -1;
        const target = candidates[candidateIndex];
        if (target) {
          lastPreviewed = target;
          raf(() => {
            highlightTarget(target);
            scrollIntoViewIfNeeded(target);
          });
          const data = scrapeDataFromElement(target);
          sendResponse({ data, selector: uniqueSelector(target), candidatesFound: candidates.length });
        } else {
          sendResponse({ data: [], selector: null, candidatesFound: 0 });
        }
        break;
      }
      case 'ids:cycle-next-table': {
        if (candidates.length > 0) {
          candidateIndex = (candidateIndex + 1) % candidates.length;
          const target = candidates[candidateIndex];
          lastPreviewed = target;
          raf(() => {
            highlightTarget(target);
            scrollIntoViewIfNeeded(target);
          });
          const data = scrapeDataFromElement(target);
          sendResponse({ data, selector: uniqueSelector(target) });
        } else {
          sendResponse({ data: [], selector: null });
        }
        break;
      }
      case 'ids:find-node-by-text': {
        const { query } = message;
        const foundNode = findBestNodeByText(query);
        if (foundNode) {
          const container = nearestContainer(foundNode);
          lastPreviewed = container;
          if (!candidates.includes(container)) {
            candidates.unshift(container);
          }
          candidateIndex = candidates.indexOf(container);
          raf(() => {
            highlightTarget(container);
            scrollIntoViewIfNeeded(container);
          });
          sendResponse({ selector: uniqueSelector(container) });
        } else {
          sendResponse({ selector: null });
        }
        break;
      }
      case 'ids:set-target-selector': {
        forcedTargetSelector = message.selector;
        break;
      }
      case 'ids:refresh-preview': {
        const currentTarget = forcedTargetSelector ? document.querySelector(forcedTargetSelector) : (candidates[candidateIndex] || null);
        if (currentTarget) {
          const data = scrapeDataFromElement(currentTarget);
          sendResponse({ data, selector: uniqueSelector(currentTarget) });
        } else {
          sendResponse({ data: [], selector: null });
        }
        break;
      }
      case 'ids:locate-next-button': {
        nextButtonEl = findNextButton();
        if (nextButtonEl) {
          raf(() => {
            highlightTarget(nextButtonEl);
            scrollIntoViewIfNeeded(nextButtonEl);
          });
        }
        break;
      }
      case 'ids:start-crawling': {
        isCrawling = true;
        crawl(message.infiniteScroll);
        break;
      }
      case 'ids:stop-crawling': {
        isCrawling = false;
        break;
      }
    }
    return true; // Keep message channel open for async response
  });

  // Signal to the background script that the content script is ready.
  if (typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.sendMessage) {
    chrome.runtime.sendMessage({ type: 'ids:content-script-ready' });
  }
})();