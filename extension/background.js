importScripts("urls.js");

async function updateActionForTab(tabId, url) {
  if (isSupportedTrackUrl(url)) {
    await chrome.action.enable(tabId);
    await chrome.action.setTitle({ tabId, title: "ytdl — download this track" });
  } else {
    await chrome.action.disable(tabId);
    await chrome.action.setTitle({
      tabId,
      title: "ytdl — open a YouTube or SoundCloud track",
    });
  }
}

async function refreshAllTabs() {
  const tabs = await chrome.tabs.query({});
  for (const tab of tabs) {
    if (tab.id != null) {
      await chrome.action.disable(tab.id);
      await updateActionForTab(tab.id, tab.url);
    }
  }
}

chrome.runtime.onInstalled.addListener(refreshAllTabs);
chrome.runtime.onStartup.addListener(refreshAllTabs);

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === "complete" || changeInfo.url) {
    updateActionForTab(tabId, changeInfo.url || tab.url);
  }
});

chrome.tabs.onActivated.addListener(async ({ tabId }) => {
  const tab = await chrome.tabs.get(tabId);
  await updateActionForTab(tabId, tab.url);
});
