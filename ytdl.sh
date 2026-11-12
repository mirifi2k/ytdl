#!/usr/bin/env bash

set -uo pipefail

SSD_ROOT="${YTDL_ROOT:-/Volumes/SSD/Music}"

log() {
    printf '  %-12s %s\n' "$1" "$2"
}

usage() {
    echo "Usage:"
    echo "  ytdl <url> <folder>"
    echo "  ytdl <url> <artist> <track> <folder>"
    echo
    echo "Examples:"
    echo '  ytdl "https://music.youtube.com/watch?v=..." Music'
    echo '  ytdl "https://soundcloud.com/artist/track" Music'
    echo '  ytdl "https://www.youtube.com/playlist?list=..." Music'
    echo '  ytdl "https://youtube.com/watch?v=..." "Junior Jack" "Stupidisco" Music'
    echo '  ytdl "https://youtube.com/watch?v=..." "Mau P" "Drugs From Amsterdam (Original Mix)" "Music/House"'
}

# ------------------------------------------------------------
# Arguments
# ------------------------------------------------------------

if [ "$#" -ne 2 ] && [ "$#" -ne 4 ]; then
    usage
    exit 1
fi

link="$1"
manual_artist=""
manual_track=""

if [ "$#" -eq 2 ]; then
    folder="$2"
else
    manual_artist="$2"
    manual_track="$3"
    folder="$4"
fi

# ------------------------------------------------------------
# Dependencies
# ------------------------------------------------------------

downloader="yt-dlp"
if [[ "$link" =~ ^https?://(www\.|m\.)?soundcloud\.com/ ]] ||
   [[ "$link" =~ ^https?://(on\.soundcloud\.com|soundcloud\.app\.goo\.gl)/ ]]; then
    downloader="scdl"
fi

PYTHON_BIN="${YTDL_PYTHON:-python3}"

for command in "$downloader" ffmpeg ffprobe "$PYTHON_BIN"; do
    if ! command -v "$command" >/dev/null 2>&1; then
        echo "ERROR: '$command' is not installed or not in PATH." >&2
        exit 1
    fi
done

if ! "$PYTHON_BIN" -c 'import mutagen' >/dev/null 2>&1; then
    echo "ERROR: mutagen is required by Python '$PYTHON_BIN'." >&2
    echo "Install it in that Python environment, or set YTDL_PYTHON to a Python with mutagen installed." >&2
    exit 1
fi

# ------------------------------------------------------------
# Metadata parser
# ------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
METADATA_SCRIPT="$SCRIPT_DIR/metadata_parser.py"

if [ ! -f "$METADATA_SCRIPT" ]; then
    echo "ERROR: metadata_parser.py not found: $METADATA_SCRIPT" >&2
    exit 1
fi

# ------------------------------------------------------------
# Destination
# ------------------------------------------------------------

if [ ! -d "$SSD_ROOT" ]; then
    echo "ERROR: Download folder does not exist: $SSD_ROOT" >&2
    exit 1
fi

destination="$SSD_ROOT/$folder"

if [ ! -d "$destination" ]; then
    echo "ERROR: Destination folder does not exist: $destination" >&2
    exit 1
fi

log "Destination:" "$destination"

if [ -n "$manual_artist" ]; then
    log "Metadata:" "manual"
else
    log "Metadata:" "automatic"
fi

# ------------------------------------------------------------
# Playlist pages download the full list; watch URLs remain single-track downloads.
# ------------------------------------------------------------

playlist=false
if [ "$downloader" = "yt-dlp" ]; then
    playlist="$("$PYTHON_BIN" - "$link" <<'PYURL'
import re
import sys
from urllib.parse import urlparse, parse_qs
url = urlparse(sys.argv[1])
print("true" if (url.scheme in ("http", "https")
    and re.fullmatch(r"(www\.|m\.|music\.)?youtube\.com", url.hostname or "")
    and url.path == "/playlist" and parse_qs(url.query).get("list")) else "false")
PYURL
)"
fi
if [ "$playlist" = true ] && [ "$#" -eq 4 ]; then
    echo "ERROR: Manual artist/track overrides are only supported for individual tracks." >&2
    exit 1
fi
playlist_args=(--no-playlist)
if [ "$playlist" = true ]; then
    playlist_args=(--yes-playlist --no-abort-on-error)
fi

# ------------------------------------------------------------
# Temporary directory
# ------------------------------------------------------------

tmpdir="$(mktemp -d)" || exit 1

cleanup() {
    rm -rf -- "$tmpdir"
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

info_file="$tmpdir/info.txt"

# ------------------------------------------------------------
# Download
# ------------------------------------------------------------

echo "Downloading..."

if [ "$downloader" = "scdl" ]; then
    scdl -l "$link" --path "$tmpdir" --no-playlist --no-original
else
    yt-dlp \
    --quiet \
    "${playlist_args[@]}" \
    --progress \
    --progress-delta 1 \
    --progress-template 'download:  %(progress._percent_str)s | %(progress._speed_str)s | ETA %(progress._eta_str)s' \
    -f "bestaudio[ext=m4a]/bestaudio/best" \
    -x \
    -o "$tmpdir/%(autonumber)s-%(id)s.%(ext)s" \
    --print-to-file \
        'after_move:%(filepath)s|||%(artist)s|||%(track)s|||%(title)s' \
        "$info_file" \
    "$link"
fi

status=$?

download_status="$status"
if [ "$status" -ne 0 ] && [ "$playlist" != true ]; then
    echo "ERROR: $downloader failed with exit code $status." >&2
    exit "$status"
fi

# ------------------------------------------------------------
# Read downloader metadata
# ------------------------------------------------------------

if [ "$downloader" = "scdl" ]; then
    # scdl embeds the source metadata. Inspect audio rather than parsing its logs
    # or assuming a filename/extension (streams can be MP3 or M4A).
    "$PYTHON_BIN" - "$tmpdir" "$info_file" <<'PYSC'
import json
import subprocess
import sys
from pathlib import Path

files = []
for path in Path(sys.argv[1]).rglob("*"):
    if not path.is_file():
        continue
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_format", "-show_streams", "-of", "json", str(path)],
        capture_output=True, text=True,
    )
    if probe.returncode:
        continue
    data = json.loads(probe.stdout)
    if any(stream.get("codec_type") == "audio" for stream in data.get("streams", [])):
        tags = {key.lower(): value for key, value in data.get("format", {}).get("tags", {}).items()}
        files.append((path, tags))
if len(files) != 1:
    sys.exit(f"ERROR: scdl must download exactly one audio track; found {len(files)}.")
path, tags = files[0]
# Leave track empty so artist/title patterns in SoundCloud titles take priority
# over the uploader name, while retaining artist as a fallback.
values = [str(path), tags.get("artist", ""), "", tags.get("title") or path.stem]
Path(sys.argv[2]).write_text("|||".join(values) + "\n")
PYSC
    if [ "$?" -ne 0 ]; then
        exit 1
    fi
fi

if [ ! -s "$info_file" ]; then
    echo "ERROR: $downloader did not report the downloaded file." >&2
    exit 1
fi

processed=0
failed=0
while IFS= read -r info || [ -n "$info" ]; do

    # Bash IFS treats each | independently, so split the
    # literal ||| separator using parameter expansion instead.

    if [[ "$info" != *"|||"* ]]; then
        echo "ERROR: Invalid downloader metadata output." >&2
        failed=$((failed + 1))
        continue
    fi

    downloaded_file="${info%%|||*}"
    remaining="${info#*|||}"

    yt_artist="${remaining%%|||*}"
    remaining="${remaining#*|||}"

    yt_track="${remaining%%|||*}"
    yt_title="${remaining#*|||}"

    [ "$yt_artist" = "NA" ] && yt_artist=""
    [ "$yt_track" = "NA" ] && yt_track=""
    [ "$yt_title" = "NA" ] && yt_title=""

    if [ ! -f "$downloaded_file" ]; then
        echo "ERROR: Downloaded file not found: $downloaded_file" >&2
        failed=$((failed + 1))
        continue
    fi

    # ------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------

    echo "Download complete."

    if [ -n "$manual_artist" ]; then
        log "Artist:" "$manual_artist"
        log "Track:" "$manual_track"
    else
        log "Artist:" "${yt_artist:-<none>}"
        log "Track:" "${yt_track:-<none>}"
        log "Title:" "${yt_title:-<none>}"
    fi

    # ------------------------------------------------------------
    # Build parser arguments
    # ------------------------------------------------------------

    python_args=(
        "$METADATA_SCRIPT"
        "$downloaded_file"
        --yt-title "$yt_title"
        --yt-artist "$yt_artist"
        --yt-track "$yt_track"
        --destination "$destination"
    )

    if [ -n "$manual_artist" ]; then
        python_args+=(
            --artist "$manual_artist"
            --track "$manual_track"
        )
    fi

    # ------------------------------------------------------------
    # Tag, rename and move
    # ------------------------------------------------------------

    "$PYTHON_BIN" "${python_args[@]}"
    status=$?

    if [ "$status" -ne 0 ]; then
        echo "ERROR: Metadata processing failed." >&2
        failed=$((failed + 1))
    else
        processed=$((processed + 1))
    fi
done < "$info_file"

log "Saved:" "$processed track(s)"
if [ "$download_status" -ne 0 ] || [ "$failed" -ne 0 ] || [ "$processed" -eq 0 ]; then
    echo "ERROR: Download incomplete; $failed track(s) failed metadata processing. See above for download errors." >&2
    exit 1
fi
echo "Done."
