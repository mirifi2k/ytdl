# ytdl

CLI plus a Brave extension for downloading the current YouTube video or SoundCloud track into a folder under a configurable download root (default: `/Volumes/SSD/Music`).

## CLI

```bash
ytdl <url> <folder>
ytdl <url> <artist> <track> <folder>
```

SoundCloud track URLs use [scdl](https://github.com/scdl-org/scdl); YouTube URLs use `yt-dlp`. Install `scdl` (for example, `pipx install scdl`), `yt-dlp`, `ffmpeg` (including `ffprobe`), and Python 3 with `mutagen`. Ensure these commands are on the native host's PATH (`/opt/homebrew/bin` and `/usr/local/bin` are included).

The extension uses the native host's Python for metadata processing. For CLI use, set `YTDL_PYTHON=/path/to/python` to select an environment with `mutagen`; otherwise `python3` from PATH is used. Dependencies are checked before downloading.

```bash
ytdl "https://soundcloud.com/artist/track" "Music/House"
ytdl "https://soundcloud.com/artist/track" "Artist" "Track" "Music/House"
```

SoundCloud downloads use the best available stream, then the same metadata parsing, tagging, and renaming as YouTube. Manual artist/track overrides work for both. Open individual tracks rather than profiles or playlists; private track URLs retain their access token.

`folder` is relative to `/Volumes/SSD/Music`. Set `YTDL_ROOT` to use another root, e.g. `YTDL_ROOT="$HOME/Music" ytdl <url> House`.

## Brave extension

Browsers cannot run local CLIs or list `/Volumes` directly, so the extension talks to a small **native messaging host** that invokes `ytdl`.

### 1. Load the extension

1. Open `brave://extensions`
2. Enable **Developer mode**
3. **Load unpacked** → select the `extension/` folder in this repo
4. Copy the extension **ID**

### 2. Install the native host

```bash
./native-host/install.sh <extension-id>
```

This installs the host under `~/.local/share/ytdl-native-host/` and registers it with Brave.

### 3. Use it

1. Ensure your download folder exists
2. Ensure `ytdl` is on your `PATH` (e.g. `/usr/local/bin/ytdl`)
3. Open a YouTube (or YouTube Music) watch page, or a SoundCloud track page
4. Click the **ytdl** toolbar icon
5. Enter an absolute path in **Download folder** and click **Save** (for example, `/Users/you/Music`). The extension remembers it across popup and browser restarts. `~` paths are also supported.
6. Pick a subfolder and click **Download**. The list includes all non-hidden folders recursively; choose **. (Download folder)** to download directly into the root.

You can close the popup while downloading. The toolbar badge shows ↓ while downloading, ✓ when finished, or ! if it fails. Reopen the popup to see progress and the result. One download runs at a time; keep Brave running until it finishes.

Click **Cancel download** to stop the active download. The button shows **Canceling…** until the downloader and its child processes stop and temporary files are cleaned up. You can then select a folder and start another track. Update the native host after installing this feature.

### Reload after changes

Reload the extension on `brave://extensions`, and re-run `install.sh` if you change `native-host/ytdl_host.py`. For this update, also update the installed `ytdl` CLI from `ytdl.sh` so it honors the selected root.
