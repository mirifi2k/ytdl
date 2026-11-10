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

function request(cmd, payload = {}) {
  return chrome.runtime.sendMessage({ cmd, ...payload });
}

function renderDownload(state) {
  downloading = state.running;
  downloadBtn.textContent = downloading ? "Downloading…" : "Download";
  downloadBtn.disabled = downloading || !selectedFolder || !videoUrl;
  if (state.url) {
    const context = `${state.url} → ${state.folder}`;
    showLog(`${context}\n\n${state.log}`, downloading ? "" : state.ok ? "success" : "error");
  }
}

async function refreshDownload() {
  renderDownload(await request("download_state"));
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
  try {
    const res = await request("download", {
      url: videoUrl,
      folder: selectedFolder,
    });
    if (!res.ok) throw new Error(res.error || "Could not start download.");
    renderDownload(res.state);
  } catch (err) {
    downloading = false;
    downloadBtn.disabled = !selectedFolder || !videoUrl;
    showLog(String(err.message || err), "error");
  }
}

async function init() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const url = tab?.url || "";

  if (!isSupportedTrackUrl(url)) {
    pageTitleEl.textContent = "Not a supported track page";
    showStatus("Open a YouTube video or SoundCloud track, then try again.", "error");
    return;
  }

  videoUrl = normalizeTrackUrl(url);
  pageTitleEl.textContent = tab.title || videoUrl;

  try {
    await refreshDownload();
    const status = await request("status");

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
    setInterval(() => refreshDownload().catch(() => {}), 500);
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
