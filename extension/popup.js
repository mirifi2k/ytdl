const HOST = "com.razvan.ytdl";

const pageTitleEl = document.getElementById("page-title");
const statusBlock = document.getElementById("status-block");
const mainEl = document.getElementById("main");
const filterEl = document.getElementById("filter");
const foldersEl = document.getElementById("folders");
const downloadBtn = document.getElementById("download");
const logEl = document.getElementById("log");

let folders = [];
let selectedFolder = null;
let videoUrl = null;
let port = null;
let downloading = false;

function showStatus(message, kind = "") {
  statusBlock.hidden = false;
  statusBlock.className = `status ${kind}`.trim();
  statusBlock.textContent = message;
}

function showLog(text, kind = "") {
  logEl.hidden = false;
  logEl.className = `log ${kind}`.trim();
  logEl.textContent = text;
}

function appendLog(line) {
  logEl.hidden = false;
  if (!logEl.className.includes("log")) {
    logEl.className = "log";
  }
  logEl.textContent = logEl.textContent
    ? `${logEl.textContent}\n${line}`
    : line;
  logEl.scrollTop = logEl.scrollHeight;
}

function normalizeWatchUrl(url) {
  try {
    const u = new URL(url);
    if (u.hostname === "youtu.be") {
      const id = u.pathname.replace(/^\//, "");
      return id ? `https://www.youtube.com/watch?v=${id}` : url;
    }
    const id = u.searchParams.get("v");
    if (id) {
      return `https://www.youtube.com/watch?v=${id}`;
    }
    return url;
  } catch (_) {
    return url;
  }
}

function isYouTubeWatchUrl(url) {
  if (!url) return false;
  try {
    const u = new URL(url);
    if (u.hostname === "youtu.be" && u.pathname.length > 1) return true;
    if (
      /^(www\.|m\.|music\.)?youtube\.com$/i.test(u.hostname) &&
      u.pathname === "/watch" &&
      u.searchParams.get("v")
    ) {
      return true;
    }
  } catch (_) {
    return false;
  }
  return false;
}

function connectNative() {
  return new Promise((resolve, reject) => {
    let p;
    try {
      p = chrome.runtime.connectNative(HOST);
    } catch (err) {
      reject(err);
      return;
    }

    const onDisconnect = () => {
      const err =
        chrome.runtime.lastError?.message || "Native host disconnected.";
      reject(new Error(err));
    };

    const onMessage = (msg) => {
      p.onMessage.removeListener(onMessage);
      p.onDisconnect.removeListener(onDisconnect);
      resolve({ port: p, firstMessage: msg });
    };

    p.onDisconnect.addListener(onDisconnect);
    p.onMessage.addListener(onMessage);
    p.postMessage({ cmd: "status" });
  });
}

function request(cmd, payload = {}) {
  return new Promise((resolve, reject) => {
    if (!port) {
      reject(new Error("Native host is not connected."));
      return;
    }

    const onMessage = (msg) => {
      if (msg.type === "progress") {
        appendLog(msg.line);
        return;
      }
      port.onMessage.removeListener(onMessage);
      resolve(msg);
    };

    port.onMessage.addListener(onMessage);
    port.postMessage({ cmd, ...payload });
  });
}

function renderFolders() {
  const q = filterEl.value.trim().toLowerCase();
  const visible = folders.filter((f) => f.toLowerCase().includes(q));
  foldersEl.replaceChildren();

  if (!visible.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = q ? "No matching folders." : "No folders found.";
    foldersEl.appendChild(empty);
    downloadBtn.disabled = true;
    return;
  }

  for (const folder of visible) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "folder" + (folder === selectedFolder ? " selected" : "");
    btn.setAttribute("role", "option");
    btn.setAttribute("aria-selected", folder === selectedFolder ? "true" : "false");

    const path = document.createElement("span");
    path.className = "path";
    path.textContent = folder;
    btn.appendChild(path);

    btn.addEventListener("click", () => {
      selectedFolder = folder;
      renderFolders();
      downloadBtn.disabled = downloading || !selectedFolder || !videoUrl;
    });

    foldersEl.appendChild(btn);
  }

  downloadBtn.disabled = downloading || !selectedFolder || !videoUrl;
}

async function loadFolders() {
  const res = await request("list_folders");
  if (!res.ok) {
    throw new Error(res.error || "Could not list folders.");
  }
  folders = res.folders || [];
  if (folders.length && !selectedFolder) {
    selectedFolder = folders[0];
  }
  renderFolders();
}

async function startDownload() {
  if (!selectedFolder || !videoUrl || downloading) return;

  downloading = true;
  downloadBtn.disabled = true;
  downloadBtn.textContent = "Downloading…";
  showLog("Starting download…");

  try {
    const res = await request("download", {
      url: videoUrl,
      folder: selectedFolder,
    });

    if (!res.ok) {
      showLog(res.error || res.output || "Download failed.", "error");
      return;
    }

    const text = [res.output, res.error].filter(Boolean).join("\n").trim();
    showLog(text || "Done.", "success");
  } catch (err) {
    showLog(String(err.message || err), "error");
  } finally {
    downloading = false;
    downloadBtn.textContent = "Download";
    downloadBtn.disabled = !selectedFolder || !videoUrl;
  }
}

async function init() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const url = tab?.url || "";

  if (!isYouTubeWatchUrl(url)) {
    pageTitleEl.textContent = "Not a YouTube video page";
    showStatus("Open a YouTube watch page, then try again.", "error");
    return;
  }

  videoUrl = normalizeWatchUrl(url);
  pageTitleEl.textContent = tab.title || videoUrl;

  try {
    const connected = await connectNative();
    port = connected.port;
    const status = connected.firstMessage;

    if (!status.ok) {
      showStatus(status.error || "Native host error.", "error");
      return;
    }

    if (!status.ytdl) {
      showStatus("ytdl was not found on this computer (expected in PATH).", "error");
      return;
    }

    if (!status.ssd) {
      showStatus(
        "SSD is not mounted at /Volumes/SSD/Music. Mount it and reopen the popup.",
        "error"
      );
      return;
    }

    showStatus(`Ready · ${status.ytdl_path || "ytdl"}`, "ok");
    mainEl.hidden = false;
    await loadFolders();
  } catch (err) {
    showStatus(
      `${err.message || err}\n\nRun native-host/install.sh after loading the unpacked extension.`,
      "error"
    );
  }
}

filterEl.addEventListener("input", renderFolders);
downloadBtn.addEventListener("click", startDownload);

init();
