// background.js - Web Scraper 2.0

// A set to track tabs where injection is in progress or complete.
const processingTabs = new Set();

chrome.action.onClicked.addListener((tab) => {
  // If we are already processing this tab, do nothing to prevent re-injection.
  if (processingTabs.has(tab.id)) {
    console.log(`[IDS][background] Already processing tab ${tab.id}.`);
    // Attempt to open the popup directly in case the user closed it.
    openPopup(tab);
    return;
  }

  processingTabs.add(tab.id);

  // Inject the content scripts in order.
  chrome.scripting.executeScript({
    target: { tabId: tab.id },
    files: ['js/jquery-3.1.1.min.js', 'js/sha256.min.js', 'onload.js'],
  })
  .catch(err => {
    console.error(`[IDS][background] Script injection failed on tab ${tab.id}:`, err);
    // If injection fails, remove from processing set so the user can retry.
    processingTabs.delete(tab.id);
  });
});

// Listen for the ready signal from the content script.
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'ids:content-script-ready') {
    console.log('[IDS][background] Content script is ready. Opening popup.');
    if (sender.tab) {
      openPopup(sender.tab);
    }
    sendResponse({ status: 'ok' });
    return true; // Keep channel open for async response.
  }
});

function openPopup(tab) {
  const popupUrl = chrome.runtime.getURL('popup.html');
  const targetUrl = `${popupUrl}?tabid=${encodeURIComponent(tab.id)}&url=${encodeURIComponent(tab.url)}`;

  chrome.windows.create({
    url: targetUrl,
    type: 'popup',
    width: 720,
    height: 650,
  });
}

// Clean up the set when a tab is closed or reloaded.
chrome.tabs.onRemoved.addListener((tabId) => {
  if (processingTabs.has(tabId)) {
    processingTabs.delete(tabId);
  }
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
  // If the page has reloaded, the content script will be gone.
  if (changeInfo.status === 'complete') {
    if (processingTabs.has(tabId)) {
      processingTabs.delete(tabId);
    }
  }
});