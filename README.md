# ZH Downloader

Personal video grabber for ZH Motions students. Download footage from 1800+ sites
(YouTube, Vimeo, Instagram, TikTok, X/Twitter, Facebook, Twitch, Pinterest, Reddit + many more).

Two parts:

1. **Browser Extension** — auto-sniffs media on any page.
2. **Desktop App** — paste any URL, choose quality/format, download with yt-dlp.

ZH Motions dark theme: maroon `#5b1a1f` + gold `#d4a13a` + black `#0a0a0a`.

---

## Quick Start (Any Platform)

> **No Python knowledge needed.** Just double-click the launcher for your OS.

| Platform | File to double-click | What it does |
|----------|----------------------|--------------|
| **Windows** | `ZH-Downloader-Win.bat` | Checks Python, installs deps, launches app |
| **macOS** | `ZH-Downloader-Mac.command` | Checks Python, installs deps, launches app |
| **Linux** | `ZH-Downloader-Linux.sh` | Checks Python, installs deps, launches app |

**First run:** Takes 1-2 minutes (installs packages). **Later runs:** Instant.

### Windows — Step by step
1. Double-click `ZH-Downloader-Win.bat`
2. If Python is missing → the script tells you exactly what to do + opens the download page
3. First time: waits 1-2 min to install packages (shows progress)
4. App opens — done!

### macOS — Step by step
1. Double-click `ZH-Downloader-Mac.command`
2. macOS may ask: *"Are you sure you want to open this?"* → Click **Open**
3. First time: waits 1-2 min to install packages
4. App opens — done!

   > If blocked: right-click the file → Open → Open

### Linux — Step by step
1. Open Terminal in the folder
2. Run: `bash ZH-Downloader-Linux.sh`
3. If tkinter is missing, the script tells you the exact `apt`/`dnf`/`pacman` command
4. App opens — done!

---

## Want a standalone .exe / .app? (No Python at all)

Use the build scripts to create a single file that anyone can run without Python:

### Windows → `.exe`
```cmd
build_win.bat
```
Output: `dist\ZHDownloader.exe` — share this file, no install needed.

### macOS → `.dmg` + `.pkg`
```bash
chmod +x build_mac.sh && ./build_mac.sh
```
Output: `ZHDownloader-macOS.dmg` + `ZHDownloader-macOS.pkg`

### Auto-build via GitHub Actions
Push to `main` branch → GitHub automatically builds `.exe` + `.msi` for Windows.
Find the files under **Actions → latest run → Artifacts**.

---

## Browser Extension (Chrome / Edge / Brave)

### Install
1. Open `chrome://extensions/`
2. Toggle **Developer mode** (top right)
3. Click **Load unpacked**
4. Select the `extension/` folder
5. Pin the gold ZH icon to toolbar

### Use
- Visit any video page → start the player
- Gold badge shows count of sniffed media
- Click icon → see list with type chips (MP4 / WEBM / HLS / DASH / AUDIO)
- Direct files (MP4, WEBM, MP3): click ⬇ to download via browser
- Streams (HLS / DASH): click ⬇ → URL is copied → paste into desktop app

---

## App Features

- Paste one or multiple URLs (one per line)
- Formats: Best MP4 / Best Any / 1080p / 720p / Audio MP3 / Audio WAV
- Optional: subtitles, thumbnail, full playlist download
- Auto-detect URLs from clipboard
- Browser extension one-click integration
- Pause & resume downloads
- Saves to `~/Downloads/ZHDownloader/` by default

---

## ffmpeg

ffmpeg is needed for:
- Merging HD video + audio (1080p, 4K)
- Audio extraction (MP3, WAV)
- HLS/DASH stream downloads

**Install:**
- Windows: `choco install ffmpeg` or [download here](https://www.gyan.dev/ffmpeg/builds/)
- macOS: `brew install ffmpeg`
- Linux: `sudo apt install ffmpeg`

The launcher scripts will warn you if ffmpeg is missing.

---

## File Map

```
ZHDownloader/
├─ ZH-Downloader-Win.bat        # Windows launcher (double-click)
├─ ZH-Downloader-Mac.command    # macOS launcher (double-click)
├─ ZH-Downloader-Linux.sh       # Linux launcher
├─ zh_downloader.py             # Desktop app (Tkinter GUI)
├─ requirements.txt             # yt-dlp
├─ build_mac.sh                 # PyInstaller → .app → .dmg + .pkg
├─ build_win.bat                # PyInstaller → .exe + .msi
├─ extension/                   # Chrome/Edge/Brave extension
│  ├─ manifest.json
│  ├─ background.js
│  ├─ content.js
│  └─ popup.html / popup.css / popup.js
└─ assets/
   ├─ AppIcon.ico / AppIcon.icns
   └─ header-logo.png
```

---

## Notes

- **Personal use only.** Internal tool for ZH Motions students to grab reference footage.
- Respect copyright. Don't redistribute downloaded material commercially without rights.
- HLS / DASH streams need the desktop app (ffmpeg merges segments).
- Keep yt-dlp updated: `.venv\Scripts\pip install --upgrade yt-dlp` (Win) or `source .venv/bin/activate && pip install --upgrade yt-dlp` (Mac/Linux)
