// background.js - Instant Data Scraper
// This script handles the extension's icon click event.

// Listen for a click on the browser action icon.
chrome.action.onClicked.addListener(handleActionClick);

/**
 * Handles the click event on the extension's icon. This function now uses
 * programmatic injection and waits for the content script to be ready before opening the popup.
 *
 * @param {chrome.tabs.Tab} tab The tab that was active when the icon was clicked.
 */
async function handleActionClick(tab) {
  // Check if the URL is accessible by the extension.
  if (tab.url.startsWith('chrome://') || tab.url.startsWith('https://chrome.google.com')) {
    console.error(`[IDS] Cannot inject scripts into restricted URL: ${tab.url}.`);
    return;
  }

  try {
    console.log(`[IDS] Action clicked for tab ${tab.id}. Injecting scripts and waiting for readiness signal.`);

    // A promise that resolves when the content script is ready.
    const readyPromise = new Promise((resolve, reject) => {
      const listener = (message, sender) => {
        // Ensure the message is from the correct tab.
        if (message.type === 'ids:content-script-ready' && sender.tab?.id === tab.id) {
          console.log(`[IDS] Readiness signal received from tab ${tab.id}.`);
          chrome.runtime.onMessage.removeListener(listener);
          clearTimeout(timeout); // Clear the timeout
          resolve();
        }
      };
      chrome.runtime.onMessage.addListener(listener);

      // Timeout to prevent the promise from hanging indefinitely.
      const timeout = setTimeout(() => {
        chrome.runtime.onMessage.removeListener(listener);
        reject(new Error(`Timeout: Content script on tab ${tab.id} did not signal readiness.`));
      }, 5000); // 5-second timeout
    });

    // First, inject the necessary CSS into the active tab.
    await chrome.scripting.insertCSS({
      target: { tabId: tab.id },
      files: ['onload.css'],
    });

    // Then, inject the JavaScript files. The execution of this will trigger the 'ids:content-script-ready' message.
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: [
        'js/jquery-3.1.1.min.js',
        'js/sha256.min.js',
        'onload.js'
      ],
    });

    // Wait for the content script to be ready.
    await readyPromise;

    console.log(`[IDS] Content script is ready. Creating popup for tab ${tab.id}.`);
    // After the scripts are ready, create the popup window.
    const popupUrl = chrome.runtime.getURL('popup.html');
    const targetUrl = `${popupUrl}?tabid=${encodeURIComponent(tab.id)}&url=${encodeURIComponent(tab.url)}`;

    await chrome.windows.create({
      url: targetUrl,
      type: 'popup',
      width: 720,
      height: 650,
    });
  } catch (err) {
    console.error(`[IDS] An error occurred during injection or popup creation: ${err.message}`);
  }
}