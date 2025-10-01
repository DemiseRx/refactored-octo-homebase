// popup.js — Instant Data Scraper (enhanced)
// ChatGPT — adds "Search for data" support on "Try another table" click,
// persists query, and falls back to normal cycling when no match is found.

(function () {
  'use strict';

  // Get the target tab's ID from the URL. This is more reliable than
  // querying for the "active" tab, which can be inconsistent.
  const urlParams = new URLSearchParams(window.location.search);
  const tabId = parseInt(urlParams.get('tabid'), 10);

  // -----------------------------
  // Helpers
  // -----------------------------

  // Send a message to the target tab's content script
  function withActiveTab(cb) {
    if (!tabId || isNaN(tabId)) {
      console.warn('[IDS][popup] No valid tab ID was found in the URL.');
      return;
    }
    // The callback expects a 'tab' object, but only really needs the 'id' property for messaging.
    cb({ id: tabId });
  }

  // Ask content script to cycle to the next detected table/list
  function cycleNextTable() {
    withActiveTab((tab) => {
      chrome.tabs.sendMessage(tab.id, { type: 'ids:cycle-next-table' }, () => {
        // Best-effort; content script may or may not acknowledge
        if (chrome.runtime.lastError) {
          // Silent fallback; not critical to surface to user
          // console.warn('[IDS][popup] cycle-next-table error:', chrome.runtime.lastError.message);
        }
      });
    });
  }

  // Persist and load query
  const STORAGE_KEY = 'ids.searchQuery';

  function saveQuery(q) {
    try {
      chrome.storage && chrome.storage.local && chrome.storage.local.set({ [STORAGE_KEY]: q });
    } catch (e) {
      // Non-fatal
    }
  }

  function loadQuery(cb) {
    try {
      if (!chrome.storage || !chrome.storage.local) return cb('');
      chrome.storage.local.get([STORAGE_KEY], (res) => cb(res && res[STORAGE_KEY] ? String(res[STORAGE_KEY]) : ''));
    } catch (e) {
      cb('');
    }
  }

  // -----------------------------
  // Main wiring
  // -----------------------------
  document.addEventListener('DOMContentLoaded', () => {
    const searchInput = document.getElementById('ids-search');
    const tryAnotherBtn = document.getElementById('try-another-table-btn');

    // Restore previous query (if any)
    loadQuery((val) => {
      if (searchInput && typeof val === 'string' && val.trim()) {
        searchInput.value = val;
      }
    });

    // Save on change/typing (debounced via simple timer)
    if (searchInput) {
      let t;
      const handler = () => {
        clearTimeout(t);
        t = setTimeout(() => saveQuery(searchInput.value || ''), 200);
      };
      searchInput.addEventListener('input', handler);
      searchInput.addEventListener('change', handler);

      // Pressing Enter in the search field triggers "Try another table"
      searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          if (tryAnotherBtn) tryAnotherBtn.click();
        }
      });
    }

    // Core: Intercept the "Try another table" button
    if (tryAnotherBtn) {
      tryAnotherBtn.addEventListener('click', (e) => {
        // If there is no search field, behave as before
        if (!searchInput) {
          cycleNextTable();
          return;
        }

        const query = (searchInput.value || '').trim();
        // No query -> keep original cycling behavior
        if (!query) {
          cycleNextTable();
          return;
        }

        // Persist immediately (so quick open/close keeps the value)
        saveQuery(query);

        // Ask the content script to find a node by text
        withActiveTab((tab) => {
          chrome.tabs.sendMessage(
            tab.id,
            { type: 'ids:find-node-by-text', query },
            (res) => {
              // If content script not available or other error -> fallback
              if (chrome.runtime.lastError) {
                // console.warn('[IDS][popup] find-node error:', chrome.runtime.lastError.message);
                cycleNextTable();
                return;
              }

              // If we got a selector, set it and refresh preview
              if (res && res.selector) {
                chrome.tabs.sendMessage(
                  tab.id,
                  { type: 'ids:set-target-selector', selector: res.selector },
                  () => {
                    // Even if this errors, still attempt to refresh the preview.
                    chrome.tabs.sendMessage(tab.id, { type: 'ids:refresh-preview' }, () => {
                      // Done; ignore errors — content script may not implement refresh.
                    });
                  }
                );
              } else {
                // No match found -> fallback to normal cycling
                cycleNextTable();
              }
            }
          );
        });
      });
    }

    // Optional: expose a tiny status line (if your popup.html includes an element with this id)
    const statusEl = document.getElementById('ids-status');
    if (statusEl && searchInput) {
      const updateStatus = () => {
        const q = (searchInput.value || '').trim();
        statusEl.textContent = q ? `Search active: "${q}"` : 'Search inactive';
      };
      searchInput.addEventListener('input', updateStatus);
      searchInput.addEventListener('change', updateStatus);
      updateStatus();
    }
  });
})();
