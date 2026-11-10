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

// The service worker owns native ports, so closing the popup cannot end a job.
// A connected native messaging port keeps the MV3 worker alive during downloads.
let downloadState = { running: false, url: null, folder: null, log: "", ok: null };

function nativeRequest(message, onProgress = () => {}) {
  return new Promise((resolve, reject) => {
    const port = chrome.runtime.connectNative("com.ytdl");
    port.onDisconnect.addListener(() => {
      reject(new Error(chrome.runtime.lastError?.message || "Native host disconnected."));
    });
    port.onMessage.addListener((response) => {
      if (response.type === "progress") {
        onProgress(response.line);
      } else {
        resolve(response);
        port.disconnect();
      }
    });
    port.postMessage(message);
  });
}

function setDownloadBadge(text, color) {
  chrome.action.setBadgeBackgroundColor({ color });
  chrome.action.setBadgeText({ text });
}

async function runDownload(message) {
  try {
    const result = await nativeRequest(message, (line) => {
      downloadState.log = `${downloadState.log}\n${line}`.slice(-32000);
    });
    downloadState.ok = Boolean(result.ok);
    downloadState.log = (result.output || result.error || "Done.").slice(-32000);
  } catch (err) {
    downloadState.ok = false;
    downloadState.log = String(err.message || err);
  } finally {
    downloadState.running = false;
    setDownloadBadge(downloadState.ok ? "✓" : "!", downloadState.ok ? "#29834a" : "#b83c3c");
  }
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (sender.id !== chrome.runtime.id) return;
  if (message.cmd === "download_state") {
    sendResponse(downloadState);
  } else if (message.cmd === "download") {
    if (downloadState.running) {
      sendResponse({ ok: false, error: "A download is already running." });
    } else if (!isSupportedTrackUrl(message.url) || typeof message.folder !== "string" || !message.folder) {
      sendResponse({ ok: false, error: "A supported track URL and folder are required." });
    } else {
      downloadState = {
        running: true, url: message.url, folder: message.folder,
        log: "Starting download…", ok: null,
      };
      setDownloadBadge("↓", "#267e90");
      void runDownload({ cmd: "download", url: message.url, folder: message.folder });
      sendResponse({ ok: true, state: downloadState });
    }
  } else if (message.cmd === "status" || message.cmd === "list_folders") {
    nativeRequest({ cmd: message.cmd }).then(sendResponse, (err) => {
      sendResponse({ ok: false, error: String(err.message || err) });
    });
    return true;
  }
});
