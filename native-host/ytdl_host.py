#!/usr/bin/env python3
"""Native messaging host for the ytdl Brave/Chrome extension."""

from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path

SSD_ROOT = Path("/Volumes/SSD/Music")


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


def list_folders() -> list[str]:
    if not SSD_ROOT.is_dir():
        return []

    folders: list[str] = []
    for root, dirnames, _filenames in os.walk(SSD_ROOT):
        # Skip hidden directories
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        rel = Path(root).relative_to(SSD_ROOT)
        if rel.parts:
            folders.append(rel.as_posix())

    folders.sort(key=str.lower)
    return folders


def handle_status() -> dict:
    ytdl = find_ytdl()
    return {
        "ok": True,
        "ytdl": bool(ytdl),
        "ytdl_path": ytdl,
        "ssd": SSD_ROOT.is_dir(),
        "ssd_root": str(SSD_ROOT),
    }


def handle_list_folders() -> dict:
    if not SSD_ROOT.is_dir():
        return {
            "ok": False,
            "error": f"SSD is not mounted: {SSD_ROOT}",
        }
    return {"ok": True, "folders": list_folders()}


def handle_download(url: str, folder: str) -> dict:
    ytdl = find_ytdl()
    if not ytdl:
        return {"ok": False, "error": "ytdl was not found on this computer."}

    if not url or not folder:
        return {"ok": False, "error": "url and folder are required."}

    # Prevent path escape outside Music root
    destination = (SSD_ROOT / folder).resolve()
    try:
        destination.relative_to(SSD_ROOT.resolve())
    except ValueError:
        return {"ok": False, "error": "Invalid folder path."}

    if not destination.is_dir():
        return {"ok": False, "error": f"Destination folder does not exist: {destination}"}

    env = os.environ.copy()
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
    )

    lines: list[str] = []
    assert proc.stdout is not None
    for line in proc.stdout:
        text = line.rstrip("\n")
        lines.append(text)
        send_message({"type": "progress", "line": text})

    code = proc.wait()
    output = "\n".join(lines).strip()
    if code != 0:
        return {
            "ok": False,
            "error": output or f"ytdl exited with code {code}.",
            "output": output,
            "code": code,
        }

    return {"ok": True, "output": output or "Done.", "code": 0}


def main() -> int:
    while True:
        message = read_message()
        if message is None:
            return 0

        cmd = message.get("cmd")
        try:
            if cmd == "status":
                send_message(handle_status())
            elif cmd == "list_folders":
                send_message(handle_list_folders())
            elif cmd == "download":
                send_message(
                    handle_download(
                        str(message.get("url") or ""),
                        str(message.get("folder") or ""),
                    )
                )
            else:
                send_message({"ok": False, "error": f"Unknown command: {cmd}"})
        except Exception as exc:  # noqa: BLE001 - surface to extension
            send_message({"ok": False, "error": str(exc)})


if __name__ == "__main__":
    raise SystemExit(main())
