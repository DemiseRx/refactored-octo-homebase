// background.js - Instant Data Scraper
// This script handles the extension's icon click event.

// Listen for a click on the browser action icon.
chrome.action.onClicked.addListener(handleActionClick);

/**
 * Handles the click event on the extension's icon.
 *
 * @param {chrome.tabs.Tab} tab The tab that was active when the icon was clicked.
 */
function handleActionClick(tab) {
  // When the icon is clicked, create a new popup window.
  // We pass the active tab's ID and URL to the popup so it knows which page to scrape.
  const popupUrl = chrome.runtime.getURL('popup.html');
  const targetUrl = `${popupUrl}?tabid=${encodeURIComponent(tab.id)}&url=${encodeURIComponent(tab.url)}`;

  chrome.windows.create({
    url: targetUrl,
    type: 'popup',
    width: 720,
    height: 650,
  });
}