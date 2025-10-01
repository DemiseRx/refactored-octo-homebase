// background.js - Instant Data Scraper
// This script handles the extension's icon click event.

// Listen for a click on the browser action icon.
chrome.action.onClicked.addListener(handleActionClick);

/**
 * Handles the click event on the extension's icon. This function now uses
 * programmatic injection to ensure content scripts are loaded before the popup opens.
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
    // First, inject the necessary CSS into the active tab.
    await chrome.scripting.insertCSS({
      target: { tabId: tab.id },
      files: ['onload.css'],
    });

    // Then, inject the JavaScript files in the correct order.
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: [
        'js/jquery-3.1.1.min.js',
        'js/sha256.min.js',
        'onload.js'
      ],
    });

    // Only after the scripts have been successfully injected, create the popup window.
    const popupUrl = chrome.runtime.getURL('popup.html');
    const targetUrl = `${popupUrl}?tabid=${encodeURIComponent(tab.id)}&url=${encodeURIComponent(tab.url)}`;

    await chrome.windows.create({
      url: targetUrl,
      type: 'popup',
      width: 720,
      height: 650,
    });
  } catch (err) {
    console.error(`[IDS] An error occurred during injection or popup creation: ${err}`);
  }
}