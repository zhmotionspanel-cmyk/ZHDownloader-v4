# ZH Downloader — Student Install Guide

**Licensed exclusively to ZH Motions Students.**

---

## Quick install

### macOS

1. Download **`ZHDownloader-macOS.pkg`** from the latest release link sent in your cohort.
2. Double-click the `.pkg` file.
3. Click **Continue → Continue → Install → enter Mac password → Done**.
4. **First launch:** open **Applications** folder, **right-click** "ZH Downloader" → click **Open** → click **Open** again (one-time security bypass).
5. App launches. You're ready.

### Windows

1. Download **`ZHDownloader-Setup.msi`** from the cohort link.
2. Double-click the `.msi` file.
3. Follow installer prompts.
4. Launch from **Start Menu → ZH Downloader**.
5. If Windows shows "unrecognized app" warning, click **More info → Run anyway**.

---

## First-time setup

Open the app:

1. **Settings tab**:
   - Theme: pick whatever you like (Light, Sunset, Midnight, etc.)
   - Concurrent downloads: 2 (default) or higher
2. **Downloads tab**:
   - **Cookies** dropdown → select **chrome** (so YouTube HD/4K works)
   - **Format** → `4K (2160p)` or `HD (1080p)` — both are Premiere Pro friendly
3. **Browser**: Make sure you're logged in to YouTube / Artgrid / Artlist in **Chrome** for HD downloads.

---

## How to use

### Method 1 — paste URL

1. Copy any video URL (YouTube, Vimeo, TikTok, Artgrid, etc.)
2. Paste into the **"Paste URLs"** box (one URL per line for batch).
3. Click **↓ Download**.
4. File goes to `~/Downloads/ZHDownloader/` by default.

### Method 2 — browser extension

1. Install the included **Chrome extension** (see below).
2. Visit any video page → floating button appears bottom-right.
3. Click the button → URL auto-sends to the app → starts downloading.

### Method 3 — clipboard auto-detect

- Enable **"Watch clipboard"** checkbox.
- Copy any video URL → app auto-adds to queue.

---

## Install the browser extension (Chrome / Edge / Brave)

1. Go to `chrome://extensions/`
2. Top right: enable **Developer mode**
3. Click **Load unpacked**
4. Select the `extension/` folder from the project download
5. Pin the ZH icon to your toolbar

---

## Premiere Pro compatibility

All downloads using **HD (1080p)** or **4K (2160p)** format are auto-transcoded to:
- **Video:** H.264 (avc1) high profile, level 5.1
- **Audio:** AAC 320kbps 48kHz stereo
- **Container:** MP4 with `+faststart`

Drag the `.mp4` directly into Premiere Pro timeline. It will import without re-encoding.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| App won't open on Mac | Right-click `.app` → Open → Open Anyway |
| Windows blocks app | "More info" → "Run anyway" |
| Downloads at 360p | Set **Cookies** → `chrome` + login in browser |
| Artgrid 360p only | Need active Artgrid subscription + Chrome cookies |
| File won't open in Premiere | Use `HD (1080p)` or `4K (2160p)` format (auto-transcodes) |
| App crashes on start | Delete `~/.zhdownloader.json` and relaunch |
| Browser extension button missing | Visit a video page (YouTube watch page etc.) + wait 2s |
| Need to update | Download latest .pkg/.msi from cohort link |

---

## Important — read this

This tool is **for educational use only**. Provided to ZH Motions students for learning video editing workflows.

**Do not:**
- Share with people outside the cohort
- Resell or charge for the software
- Download copyrighted content you don't have rights to
- Use the app to violate any website's Terms of Service

**By installing you accept the full license in `LICENSE-STUDENT.txt`.**

---

## Get help

- Bugs / questions: ask in your cohort Discord / WhatsApp group
- App keeps crashing: take a screenshot of error + send to your instructor
- Feature requests: tell your instructor; they may build it in next version

---

Made by **ZH Motions** · zhmotions.com
