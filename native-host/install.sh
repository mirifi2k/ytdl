#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST_SRC="$SCRIPT_DIR/ytdl_host.py"
HOST_NAME="com.razvan.ytdl"
INSTALL_DIR="${HOME}/.local/share/ytdl-native-host"
HOST_DST="$INSTALL_DIR/ytdl_host.py"

BRAVE_NM_DIR="${HOME}/Library/Application Support/BraveSoftware/Brave-Browser/NativeMessagingHosts"
CHROME_NM_DIR="${HOME}/Library/Application Support/Google/Chrome/NativeMessagingHosts"

usage() {
  cat <<EOF
Usage: $(basename "$0") <extension-id>

Installs the ytdl native messaging host for Brave (and Chrome, if present).

1. Open brave://extensions
2. Enable Developer mode
3. Load unpacked → select the extension/ folder in this repo
4. Copy the extension ID
5. Run:  ./native-host/install.sh <extension-id>
EOF
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
  exit 0
fi

EXT_ID="${1:-}"
if [ -z "$EXT_ID" ]; then
  usage >&2
  exit 1
fi

if [[ ! "$EXT_ID" =~ ^[a-p]{32}$ ]]; then
  echo "ERROR: Extension ID should be 32 characters a-p (got: $EXT_ID)" >&2
  exit 1
fi

if [ ! -f "$HOST_SRC" ]; then
  echo "ERROR: Missing host script: $HOST_SRC" >&2
  exit 1
fi

mkdir -p "$INSTALL_DIR"
cp "$HOST_SRC" "$HOST_DST"
chmod +x "$HOST_DST"

# Prefer python3 from PATH; fall back to common locations
PYTHON_BIN="$(command -v python3 || true)"
if [ -z "$PYTHON_BIN" ]; then
  for candidate in /usr/bin/python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
    if [ -x "$candidate" ]; then
      PYTHON_BIN="$candidate"
      break
    fi
  done
fi

if [ -z "$PYTHON_BIN" ]; then
  echo "ERROR: python3 not found." >&2
  exit 1
fi

# Ensure shebang points at a real interpreter when launched by Brave
TMP_HOST="$(mktemp)"
{
  echo "#!${PYTHON_BIN}"
  tail -n +2 "$HOST_DST"
} >"$TMP_HOST"
mv "$TMP_HOST" "$HOST_DST"
chmod +x "$HOST_DST"

write_manifest() {
  local dest_dir="$1"
  mkdir -p "$dest_dir"
  local dest="$dest_dir/${HOST_NAME}.json"
  python3 - "$HOST_DST" "$EXT_ID" "$dest" <<'PY'
import json, sys
host_path, ext_id, dest = sys.argv[1:4]
manifest = {
    "name": "com.razvan.ytdl",
    "description": "Native host for the ytdl Brave extension",
    "path": host_path,
    "type": "stdio",
    "allowed_origins": [f"chrome-extension://{ext_id}/"],
}
with open(dest, "w", encoding="utf-8") as f:
    json.dump(manifest, f, indent=2)
    f.write("\n")
print(dest)
PY
}

echo "Installed host → $HOST_DST"
write_manifest "$BRAVE_NM_DIR"
echo "Registered with Brave → $BRAVE_NM_DIR/${HOST_NAME}.json"

if [ -d "$(dirname "$CHROME_NM_DIR")" ]; then
  write_manifest "$CHROME_NM_DIR"
  echo "Registered with Chrome → $CHROME_NM_DIR/${HOST_NAME}.json"
fi

echo
echo "Reload the ytdl extension in brave://extensions, then open a YouTube video."
