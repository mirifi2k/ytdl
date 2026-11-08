# ytdl

CLI plus a Brave extension for downloading the current YouTube video into a folder under `/Volumes/SSD/Music`.

## CLI

```bash
ytdl <url> <folder>
ytdl <url> <artist> <track> <folder>
```

`folder` is relative to `/Volumes/SSD/Music`.

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

1. Mount the SSD so `/Volumes/SSD/Music` exists
2. Ensure `ytdl` is on your `PATH` (e.g. `/usr/local/bin/ytdl`)
3. Open a YouTube (or YouTube Music) watch page
4. Click the **ytdl** toolbar icon
5. Pick a folder and click **Download**

Keep the popup open until the download finishes.

### Reload after changes

Reload the extension on `brave://extensions`, and re-run `install.sh` if you change `native-host/ytdl_host.py`.
