#!/usr/bin/env python3
"""Native messaging host for the ytdl Brave/Chrome extension."""

from __future__ import annotations

import json
import os
import shutil
import signal
import struct
import subprocess
import sys
import threading
from pathlib import Path

DEFAULT_ROOT = Path("/Volumes/SSD/Music")
OUTPUT_LOCK = threading.Lock()


def read_message() -> dict | None:
    raw_len = sys.stdin.buffer.read(4)
    if not raw_len:
        return None
    if len(raw_len) < 4:
        return None
    (length,) = struct.unpack("<I", raw_len)
    data = sys.stdin.buffer.read(length)
    if len(data) < length:
        return None
    return json.loads(data.decode("utf-8"))


def send_message(message: dict) -> None:
    encoded = json.dumps(message, ensure_ascii=False).encode("utf-8")
    with OUTPUT_LOCK:
        sys.stdout.buffer.write(struct.pack("<I", len(encoded)))
        sys.stdout.buffer.write(encoded)
        sys.stdout.buffer.flush()


def find_ytdl() -> str | None:
    path = shutil.which("ytdl")
    if path:
        return path
    candidate = Path("/usr/local/bin/ytdl")
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return str(candidate)
    return None


def download_root(value: str | None = None) -> Path:
    root = Path(value).expanduser() if value else DEFAULT_ROOT
    if not root.is_absolute():
        raise ValueError("Download folder must be an absolute path.")
    return root.resolve()


def list_folders(root: Path) -> list[str]:
    if not root.is_dir():
        return []

    folders: list[str] = []
    for current, dirnames, _filenames in os.walk(root):
        # Skip hidden directories
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        rel = Path(current).relative_to(root)
        if rel.parts:
            folders.append(rel.as_posix())

    folders.sort(key=str.lower)
    return folders


def handle_status(root: Path = DEFAULT_ROOT) -> dict:
    ytdl = find_ytdl()
    return {
        "ok": True,
        "ytdl": bool(ytdl),
        "ytdl_path": ytdl,
        "root_exists": root.is_dir(),
        "root": str(root),
    }


def handle_list_folders(root: Path = DEFAULT_ROOT) -> dict:
    if not root.is_dir():
        return {
            "ok": False,
            "error": f"Download folder does not exist: {root}",
        }
    return {"ok": True, "root": str(root), "folders": [".", *list_folders(root)]}


def handle_download(url: str, folder: str, root: Path = DEFAULT_ROOT,
                    cancel: threading.Event | None = None) -> dict:
    ytdl = find_ytdl()
    if not ytdl:
        return {"ok": False, "error": "ytdl was not found on this computer."}

    if not url or not folder:
        return {"ok": False, "error": "url and folder are required."}

    # Prevent path escape outside the selected root
    destination = (root / folder).resolve()
    try:
        destination.relative_to(root.resolve())
    except ValueError:
        return {"ok": False, "error": "Invalid folder path."}

    if not destination.is_dir():
        return {"ok": False, "error": f"Destination folder does not exist: {destination}"}

    env = os.environ.copy()
    env["YTDL_ROOT"] = str(root.resolve())
    env.setdefault("YTDL_PYTHON", sys.executable)
    # GUI-launched hosts often have a minimal PATH
    path_parts = env.get("PATH", "").split(os.pathsep)
    for extra in ("/usr/local/bin", "/opt/homebrew/bin", "/usr/bin", "/bin"):
        if extra not in path_parts:
            path_parts.insert(0, extra)
    env["PATH"] = os.pathsep.join(path_parts)

    proc = subprocess.Popen(
        [ytdl, url, folder],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
        bufsize=1,
        start_new_session=True,
    )

    finished = threading.Event()

    def watch_cancel():
        while not finished.wait(0.1):
            if cancel is not None and cancel.is_set():
                try:
                    # Stop the shell and its downloader/ffmpeg children together.
                    os.killpg(proc.pid, signal.SIGTERM)
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        pass
                    # The shell may have exited while a child still holds stdout.
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                return

    watcher = threading.Thread(target=watch_cancel, daemon=True)
    watcher.start()
    lines: list[str] = []
    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            text = line.rstrip("\n")
            lines.append(text)
            send_message({"type": "progress", "line": text})
        code = proc.wait()
    finally:
        finished.set()
        watcher.join()
        proc.stdout.close()
    output = "\n".join(lines).strip()
    if code != 0 and cancel is not None and cancel.is_set():
        return {"ok": False, "canceled": True, "output": "Download canceled.", "code": code}
    if code != 0:
        return {
            "ok": False,
            "error": output or f"ytdl exited with code {code}.",
            "output": output,
            "code": code,
        }

    return {"ok": True, "output": output or "Done.", "code": 0}


def main() -> int:
    worker = None
    cancel = threading.Event()

    def download(message, root):
        try:
            result = handle_download(str(message.get("url") or ""),
                                     str(message.get("folder") or ""), root, cancel)
            send_message(result)
        except Exception as exc:
            send_message({"ok": False, "error": str(exc)})

    while True:
        message = read_message()
        if message is None:
            cancel.set()
            if worker is not None:
                worker.join()
            return 0

        cmd = message.get("cmd")
        try:
            if cmd == "cancel":
                cancel.set()
                continue
            root = download_root(message.get("root"))
            if cmd == "status":
                send_message(handle_status(root))
            elif cmd == "list_folders":
                send_message(handle_list_folders(root))
            elif cmd == "download":
                if worker is not None and worker.is_alive():
                    send_message({"type": "progress", "line": "A download is already running."})
                    continue
                cancel.clear()
                worker = threading.Thread(target=download, args=(message, root))
                worker.start()
            else:
                send_message({"ok": False, "error": f"Unknown command: {cmd}"})
        except Exception as exc:  # noqa: BLE001 - surface to extension
            send_message({"ok": False, "error": str(exc)})


if __name__ == "__main__":
    raise SystemExit(main())
