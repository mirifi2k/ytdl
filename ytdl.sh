#!/usr/bin/env bash

set -uo pipefail

SSD_ROOT="/Volumes/SSD/Music"

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

for command in yt-dlp ffmpeg ffprobe python3; do
    if ! command -v "$command" >/dev/null 2>&1; then
        echo "ERROR: '$command' is not installed or not in PATH." >&2
        exit 1
    fi
done

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
    echo "ERROR: SSD is not mounted: $SSD_ROOT" >&2
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
# Prevent playlist downloads
# ------------------------------------------------------------

if [[ "$link" == *"&list="* ]]; then
    link="${link%%&list=*}"
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

yt-dlp \
    --quiet \
    --no-playlist \
    --progress \
    --progress-delta 1 \
    --progress-template 'download:  %(progress._percent_str)s | %(progress._speed_str)s | ETA %(progress._eta_str)s' \
    -f "bestaudio[ext=m4a]/bestaudio/best" \
    -x \
    -o "$tmpdir/%(id)s.%(ext)s" \
    --print-to-file \
        'after_move:%(filepath)s|||%(artist)s|||%(track)s|||%(title)s' \
        "$info_file" \
    "$link"

status=$?

if [ "$status" -ne 0 ]; then
    echo "ERROR: yt-dlp failed with exit code $status." >&2
    exit "$status"
fi

# ------------------------------------------------------------
# Read yt-dlp metadata
# ------------------------------------------------------------

if [ ! -s "$info_file" ]; then
    echo "ERROR: yt-dlp did not report the downloaded file." >&2
    exit 1
fi

info="$(tail -n 1 "$info_file")"

# Bash IFS treats each | independently, so split the
# literal ||| separator using parameter expansion instead.

if [[ "$info" != *"|||"* ]]; then
    echo "ERROR: Invalid yt-dlp metadata output." >&2
    exit 1
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
    exit 1
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

python3 "${python_args[@]}"
status=$?

if [ "$status" -ne 0 ]; then
    echo "ERROR: Metadata processing failed." >&2
    exit "$status"
fi

echo "Done."
