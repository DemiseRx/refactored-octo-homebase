// popup.js — Instant Data Scraper (enhanced)

(function () {
  'use strict';

  const urlParams = new URLSearchParams(window.location.search);
  const tabId = parseInt(urlParams.get('tabid'), 10);
  let hot; // This will hold the Handsontable instance.
  let isCrawling = false;

  // =========================
  // Helpers
  // =========================

  function withActiveTab(cb) {
    if (!tabId || isNaN(tabId)) {
      console.warn('[IDS] No valid tab ID was found in the URL.');
      return;
    }
    cb({ id: tabId });
  }

  function cycleNextTable() {
    withActiveTab((tab) => {
      chrome.tabs.sendMessage(tab.id, { type: 'ids:cycle-next-table' }, () => {
        if (chrome.runtime.lastError) {
          // console.warn('[IDS] cycle-next-table error:', chrome.runtime.lastError.message);
        }
      });
    });
  }

  const STORAGE_KEY = 'ids.searchQuery';
  function saveQuery(q) {
    try {
      chrome.storage.local.set({ [STORAGE_KEY]: q });
    } catch (e) { /* non-fatal */ }
  }

  function loadQuery(cb) {
    try {
      chrome.storage.local.get([STORAGE_KEY], (res) => cb(res && res[STORAGE_KEY] ? String(res[STORAGE_KEY]) : ''));
    } catch (e) { cb(''); }
  }

  // =========================
  // Main Wiring
  // =========================
  document.addEventListener('DOMContentLoaded', () => {
    const searchInput = document.getElementById('ids-search');
    const tryAnotherBtn = document.getElementById('try-another-table-btn');
    const nextButton = document.getElementById('nextButton');
    const startScrapingBtn = document.getElementById('startScraping');
    const stopScrapingBtn = document.getElementById('stopScraping');
    const infiniteScrollCheckbox = document.getElementById('infiniteScroll');
    const hotElement = document.getElementById('hot');

    // Initialize Handsontable
    if (hotElement) {
      hot = new Handsontable(hotElement, {
        data: [],
        rowHeaders: true,
        colHeaders: true,
        contextMenu: true,
        manualColumnResize: true,
        manualRowResize: true,
        colWidths: 150,
        licenseKey: 'non-commercial-and-evaluation'
      });
    }

    loadQuery((val) => {
      if (searchInput && typeof val === 'string' && val.trim()) {
        searchInput.value = val;
      }
    });

    if (searchInput) {
      let t;
      const handler = () => {
        clearTimeout(t);
        t = setTimeout(() => saveQuery(searchInput.value || ''), 200);
      };
      searchInput.addEventListener('input', handler);
      searchInput.addEventListener('change', handler);
      searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          if (tryAnotherBtn) tryAnotherBtn.click();
        }
      });
    }

    if (tryAnotherBtn) {
      tryAnotherBtn.addEventListener('click', (e) => {
        const query = (searchInput.value || '').trim();
        if (!query) {
          cycleNextTable();
          return;
        }
        saveQuery(query);
        withActiveTab((tab) => {
          chrome.tabs.sendMessage(tab.id, { type: 'ids:find-node-by-text', query }, (res) => {
            if (chrome.runtime.lastError) {
              cycleNextTable();
              return;
            }
            if (res && res.selector) {
              chrome.tabs.sendMessage(tab.id, { type: 'ids:set-target-selector', selector: res.selector }, () => {
                chrome.tabs.sendMessage(tab.id, { type: 'ids:refresh-preview' });
              });
            } else {
              cycleNextTable();
            }
          });
        });
      });
    }

    if (nextButton) {
      nextButton.addEventListener('click', () => {
        withActiveTab((tab) => {
          chrome.tabs.sendMessage(tab.id, { type: 'ids:locate-next-button' });
        });
      });
    }

    function setCrawlingState(crawling) {
      isCrawling = crawling;
      startScrapingBtn.disabled = crawling;
      stopScrapingBtn.disabled = !crawling;
      nextButton.disabled = crawling;
      tryAnotherBtn.disabled = crawling;
      infiniteScrollCheckbox.disabled = crawling;
    }

    if (startScrapingBtn) {
      startScrapingBtn.addEventListener('click', () => {
        setCrawlingState(true);
        withActiveTab((tab) => {
          chrome.tabs.sendMessage(tab.id, {
            type: 'ids:start-crawling',
            infiniteScroll: infiniteScrollCheckbox.checked,
          });
        });
      });
    }

    if (stopScrapingBtn) {
      stopScrapingBtn.addEventListener('click', () => {
        setCrawlingState(false);
        withActiveTab((tab) => {
          chrome.tabs.sendMessage(tab.id, { type: 'ids:stop-crawling' });
        });
      });
    }

    // Set initial button states
    setCrawlingState(false);

    chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
      if (message.type === 'ids:data-scraped') {
        const currentData = hot.getData();
        hot.loadData(currentData.concat(message.data));
      } else if (message.type === 'ids:crawling-finished') {
        setCrawlingState(false);
      }
    });

    // Handshake with content script
    function initiateHandshakeWithRetry(attempts = 0) {
      const MAX_ATTEMPTS = 5;
      const RETRY_DELAY_MS = 250;

      withActiveTab(tab => {
        chrome.tabs.sendMessage(tab.id, { type: 'ids:initialize' }, (response) => {
          const waitScreen = document.getElementById('wait');
          const contentScreen = document.getElementById('content');
          const errorDiv = document.getElementById('noResponseErr');

          if (chrome.runtime.lastError) {
            if (attempts < MAX_ATTEMPTS) {
              setTimeout(() => initiateHandshakeWithRetry(attempts + 1), RETRY_DELAY_MS);
            } else {
              console.error('[IDS] Handshake failed after multiple retries:', chrome.runtime.lastError.message);
              if (errorDiv) {
                errorDiv.textContent = "Could not connect to the page. Please reload the page and try again.";
                errorDiv.style.display = 'block';
              }
            }
            return;
          }

          if (waitScreen) waitScreen.style.display = 'none';
          if (contentScreen) contentScreen.style.display = 'block';

          if (hot && response && response.data) {
            hot.loadData(response.data);
          } else if (hot) {
            hot.loadData([[]]);
          }
        });
      });
    }

    initiateHandshakeWithRetry();
  });
})();