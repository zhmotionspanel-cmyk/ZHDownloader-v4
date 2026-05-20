"""ZH Downloader — personal video/audio grabber for ZH Motions students.
Works on YouTube, Vimeo, Instagram, TikTok, Twitter/X, Facebook, Twitch, and 1800+ sites.
Cross-platform: Windows + macOS + Linux.
"""

import os
import sys
import threading
import queue
import json
import subprocess
import shutil
import platform
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    import yt_dlp
except ImportError:
    print("yt-dlp not installed. Run: pip install -r requirements.txt")
    sys.exit(1)


APP_NAME = "ZH Downloader"
APP_VERSION = "1.1.0"
APP_AUTHOR = "ZH Motions"
APP_BUNDLE_ID = "com.zhmotions.downloader"
APP_WEBSITE = "https://zhmotions.com"
APP_COPYRIGHT = "© 2026 ZH Motions"
LOCAL_PORT = 9613
BRAND_GOLD = "#d4a13a"
BRAND_MAROON = "#5b1a1f"
BRAND_CREAM = "#fdf6ec"
BRAND_DARK = "#0f0f0f"

DEFAULT_DOWNLOAD_DIR = str(Path.home() / "Downloads" / "ZHDownloader")
CONFIG_PATH = Path.home() / ".zhdownloader.json"
STATE_PATH = Path.home() / ".zhdownloader-state.json"


def load_state():
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except Exception:
            pass
    return {"queue": []}


def save_state(state):
    try:
        STATE_PATH.write_text(json.dumps(state, indent=2))
    except Exception:
        pass


def load_config():
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except Exception:
            pass
    return {"download_dir": DEFAULT_DOWNLOAD_DIR, "format": "best_mp4"}


def save_config(cfg):
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
    except Exception:
        pass


def find_ffmpeg():
    """Return path to ffmpeg or None. Checks PATH then bundled location."""
    p = shutil.which("ffmpeg")
    if p:
        return p
    # bundled (next to executable)
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    for candidate in [base / "ffmpeg", base / "ffmpeg.exe", base / "bin" / "ffmpeg", base / "bin" / "ffmpeg.exe"]:
        if candidate.exists():
            return str(candidate)
    return None


def _bundled_root():
    """Return root dir for bundled assets — PyInstaller temp dir if frozen, else script dir."""
    return Path(getattr(sys, "_MEIPASS", Path(__file__).parent))


FORMAT_OPTIONS = {
    "best_mp4": {
        "label": "Best Quality (MP4)",
        "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b",
        "merge_output_format": "mp4",
    },
    "best_any": {
        "label": "Best Quality (Any Format)",
        "format": "bv*+ba/b",
        "merge_output_format": None,
    },
    "1080p": {
        "label": "1080p MP4",
        "format": "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4]/bv*[height<=1080]+ba/b[height<=1080]",
        "merge_output_format": "mp4",
    },
    "720p": {
        "label": "720p MP4",
        "format": "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720][ext=mp4]/bv*[height<=720]+ba/b[height<=720]",
        "merge_output_format": "mp4",
    },
    "audio_mp3": {
        "label": "Audio Only (MP3)",
        "format": "ba/b",
        "extract_audio": "mp3",
    },
    "audio_wav": {
        "label": "Audio Only (WAV)",
        "format": "ba/b",
        "extract_audio": "wav",
    },
}


class _BridgeHandler(BaseHTTPRequestHandler):
    """HTTP bridge — receives URLs from browser extension, auto-downloads."""
    app = None  # set after DownloaderApp init

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, fmt, *args):
        return  # silence default stderr logging

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path == "/ping":
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "app": "ZH Downloader",
                "version": APP_VERSION,
                "ok": True
            }).encode())
            return
        self.send_response(404)
        self._cors()
        self.end_headers()

    def do_POST(self):
        if self.path != "/download":
            self.send_response(404)
            self._cors()
            self.end_headers()
            return
        try:
            n = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(n) if n > 0 else b"{}"
            data = json.loads(body or "{}")
        except Exception:
            data = {}
        url = (data.get("url") or "").strip()
        if not url:
            self.send_response(400)
            self._cors()
            self.end_headers()
            self.wfile.write(b'{"ok":false,"err":"missing url"}')
            return
        try:
            self.app.enqueue_url(url)
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "queued": url}).encode())
        except Exception as e:
            self.send_response(500)
            self._cors()
            self.end_headers()
            self.wfile.write(json.dumps({"ok": False, "err": str(e)}).encode())


class DownloaderApp:
    def __init__(self, root):
        self.root = root
        self.cfg = load_config()
        self.msg_queue = queue.Queue()
        self.active_thread = None
        self.cancel_flag = False
        self.ffmpeg_path = find_ffmpeg()
        self._last_clip = ""
        self._clip_watch = tk.BooleanVar(value=self.cfg.get("clip_watch", True))
        self._last_files = []  # paths of files downloaded in last batch
        self._batch_count = 0
        self.state = load_state()
        self.paused = False

        root.title(f"{APP_NAME} v{APP_VERSION}")
        root.geometry("780x640")
        root.minsize(680, 560)
        root.configure(bg=BRAND_CREAM)

        self._build_ui()
        self._poll_queue()
        self._poll_clipboard()
        self._start_bridge()
        self._check_resume_on_launch()

        if not self.ffmpeg_path:
            self.log("[warn] ffmpeg not found. Audio extraction + format merging may fail.\n"
                    "       Install: brew install ffmpeg (Mac) | choco install ffmpeg (Win) | apt install ffmpeg (Linux)\n")

    def _resource_path(self, filename):
        """Look up bundled asset (works in dev + PyInstaller frozen build)."""
        root = _bundled_root()
        for candidate in [root / "assets" / filename, root / filename, Path(__file__).parent / "assets" / filename]:
            if candidate.exists():
                return str(candidate)
        return None

    def _build_ui(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Brand.TButton", background=BRAND_MAROON, foreground="white",
                        font=("Helvetica", 11, "bold"), padding=10, borderwidth=0)
        style.map("Brand.TButton", background=[("active", BRAND_GOLD)])
        style.configure("Ghost.TButton", padding=8)
        style.configure("TLabel", background=BRAND_CREAM, foreground=BRAND_DARK,
                        font=("Helvetica", 10))
        style.configure("Header.TLabel", background=BRAND_CREAM, foreground=BRAND_MAROON,
                        font=("Helvetica", 18, "bold"))
        style.configure("Sub.TLabel", background=BRAND_CREAM, foreground="#666",
                        font=("Helvetica", 9))

        # Header with logo
        header = tk.Frame(self.root, bg=BRAND_CREAM)
        header.pack(fill="x", padx=20, pady=(18, 10))

        # Logo (left side)
        logo_path = self._resource_path("header-logo.png")
        if logo_path and Path(logo_path).exists():
            try:
                self._logo_img = tk.PhotoImage(file=logo_path)
                logo_lbl = tk.Label(header, image=self._logo_img, bg=BRAND_CREAM, bd=0)
                logo_lbl.pack(side="left", padx=(0, 14))
            except Exception:
                pass

        # Text block (right side)
        text_block = tk.Frame(header, bg=BRAND_CREAM)
        text_block.pack(side="left", fill="x", expand=True)
        ttk.Label(text_block, text="ZH Downloader", style="Header.TLabel").pack(anchor="w")
        ttk.Label(text_block,
                  text=f"v{APP_VERSION} · by {APP_AUTHOR} · {APP_WEBSITE}",
                  style="Sub.TLabel").pack(anchor="w", pady=(2, 0))
        ttk.Label(text_block,
                  text="Personal footage downloader • 1800+ sites • YouTube, Vimeo, Instagram, TikTok, X, Facebook, Twitch & more",
                  style="Sub.TLabel").pack(anchor="w", pady=(1, 0))

        # Set window icon (works on Linux + Windows; macOS uses .icns at bundle level)
        try:
            if logo_path and Path(logo_path).exists():
                icon_img = tk.PhotoImage(file=logo_path)
                self.root.iconphoto(True, icon_img)
        except Exception:
            pass

        # URL section
        url_frame = tk.Frame(self.root, bg=BRAND_CREAM)
        url_frame.pack(fill="x", padx=20, pady=(10, 6))
        ttk.Label(url_frame, text="Video URL(s) — one per line:").pack(anchor="w")
        self.url_text = tk.Text(url_frame, height=4, font=("Menlo", 11),
                                bg="white", fg=BRAND_DARK, relief="flat",
                                highlightthickness=1, highlightbackground="#ccc",
                                highlightcolor=BRAND_GOLD, padx=8, pady=6)
        self.url_text.pack(fill="x", pady=(4, 0))

        # Controls row
        ctrl = tk.Frame(self.root, bg=BRAND_CREAM)
        ctrl.pack(fill="x", padx=20, pady=8)

        ttk.Label(ctrl, text="Format:").grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.format_var = tk.StringVar(value=self.cfg.get("format", "best_mp4"))
        fmt_combo = ttk.Combobox(ctrl, textvariable=self.format_var, state="readonly", width=28,
                                 values=[f"{k}: {v['label']}" for k, v in FORMAT_OPTIONS.items()])
        # set display value
        cur_key = self.format_var.get()
        if cur_key in FORMAT_OPTIONS:
            fmt_combo.set(f"{cur_key}: {FORMAT_OPTIONS[cur_key]['label']}")
        fmt_combo.grid(row=0, column=1, sticky="w")
        fmt_combo.bind("<<ComboboxSelected>>",
                       lambda e: self.format_var.set(fmt_combo.get().split(":")[0]))

        self.subtitles_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(ctrl, text="Subtitles", variable=self.subtitles_var).grid(row=0, column=2, padx=(16, 0))

        self.thumbnail_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(ctrl, text="Thumbnail", variable=self.thumbnail_var).grid(row=0, column=3, padx=(10, 0))

        self.playlist_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(ctrl, text="Full Playlist", variable=self.playlist_var).grid(row=0, column=4, padx=(10, 0))

        ttk.Checkbutton(ctrl, text="Auto-detect copied URLs", variable=self._clip_watch,
                        command=self._save_clip_pref).grid(row=0, column=5, padx=(10, 0))

        # Second row: browser cookies + advanced options
        ctrl2 = tk.Frame(self.root, bg=BRAND_CREAM)
        ctrl2.pack(fill="x", padx=20, pady=(0, 4))

        ttk.Label(ctrl2, text="Use cookies from:").grid(row=0, column=0, sticky="w")
        self.cookies_browser = tk.StringVar(value=self.cfg.get("cookies_browser", "none"))
        cookies_combo = ttk.Combobox(ctrl2, textvariable=self.cookies_browser, state="readonly", width=18,
                                     values=["none", "chrome", "safari", "firefox", "edge", "brave"])
        cookies_combo.grid(row=0, column=1, sticky="w", padx=(6, 0))
        cookies_combo.bind("<<ComboboxSelected>>", lambda e: self._save_cookies_pref())

        ttk.Label(ctrl2, text="(needed for logged-in sites like Artgrid, Patreon, IG private)",
                  style="Sub.TLabel").grid(row=0, column=2, sticky="w", padx=(8, 0))

        # Download folder row
        folder_frame = tk.Frame(self.root, bg=BRAND_CREAM)
        folder_frame.pack(fill="x", padx=20, pady=6)
        ttk.Label(folder_frame, text="Save to:").pack(side="left")
        self.folder_var = tk.StringVar(value=self.cfg.get("download_dir", DEFAULT_DOWNLOAD_DIR))
        folder_entry = ttk.Entry(folder_frame, textvariable=self.folder_var)
        folder_entry.pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(folder_frame, text="Browse…", style="Ghost.TButton",
                   command=self._pick_folder).pack(side="left")
        ttk.Button(folder_frame, text="Open", style="Ghost.TButton",
                   command=self._open_folder).pack(side="left", padx=(6, 0))

        # Action buttons
        actions = tk.Frame(self.root, bg=BRAND_CREAM)
        actions.pack(fill="x", padx=20, pady=(8, 6))
        self.dl_btn = ttk.Button(actions, text="⬇  Download", style="Brand.TButton",
                                 command=self._start_download)
        self.dl_btn.pack(side="left")
        self.pause_btn = ttk.Button(actions, text="⏸ Pause", style="Ghost.TButton",
                                    command=self._pause, state="disabled")
        self.pause_btn.pack(side="left", padx=(8, 0))
        self.cancel_btn = ttk.Button(actions, text="✕ Cancel", style="Ghost.TButton",
                                     command=self._cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Clear Log", style="Ghost.TButton",
                   command=self._clear_log).pack(side="right")

        # Prominent Resume banner — only shown when paused queue exists.
        # Maroon + gold gradient — eye-catching, can't miss.
        self.resume_banner = tk.Frame(self.root, bg=BRAND_MAROON, relief="flat", bd=0)
        # Don't pack yet — _refresh_resume_banner controls visibility
        self.resume_banner_label = tk.Label(
            self.resume_banner,
            text="",
            bg=BRAND_MAROON,
            fg=BRAND_GOLD,
            font=("Helvetica", 12, "bold"),
            padx=14, pady=12
        )
        self.resume_banner_label.pack(side="left")
        rbtns = tk.Frame(self.resume_banner, bg=BRAND_MAROON)
        rbtns.pack(side="right", padx=10, pady=8)
        self.resume_btn = ttk.Button(rbtns, text="▶  Resume Now", style="Brand.TButton",
                                     command=self._resume_queue)
        self.resume_btn.pack(side="left", padx=(0, 6))
        ttk.Button(rbtns, text="✕ Discard", style="Ghost.TButton",
                   command=self._discard_queue).pack(side="left")

        # Progress
        self.progress = ttk.Progressbar(self.root, mode="determinate", maximum=100)
        self.progress.pack(fill="x", padx=20, pady=(6, 4))
        self.status_var = tk.StringVar(value="Idle.")
        ttk.Label(self.root, textvariable=self.status_var, style="Sub.TLabel").pack(anchor="w", padx=20)

        # Log
        log_frame = tk.Frame(self.root, bg=BRAND_CREAM)
        log_frame.pack(fill="both", expand=True, padx=20, pady=(8, 18))
        self.log_text = tk.Text(log_frame, font=("Menlo", 10), bg=BRAND_DARK, fg="#dcdcdc",
                                relief="flat", padx=10, pady=8, wrap="word")
        self.log_text.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scroll.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=scroll.set, state="disabled")

    # ------ UI handlers ------
    def _pick_folder(self):
        d = filedialog.askdirectory(initialdir=self.folder_var.get())
        if d:
            self.folder_var.set(d)

    def _open_folder(self):
        path = self.folder_var.get()
        Path(path).mkdir(parents=True, exist_ok=True)
        if platform.system() == "Darwin":
            subprocess.run(["open", path])
        elif platform.system() == "Windows":
            os.startfile(path)  # noqa
        else:
            subprocess.run(["xdg-open", path])

    def _clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def log(self, msg):
        self.msg_queue.put(("log", msg))

    def set_status(self, s):
        self.msg_queue.put(("status", s))

    def set_progress(self, pct):
        self.msg_queue.put(("progress", pct))

    def _save_clip_pref(self):
        self.cfg["clip_watch"] = self._clip_watch.get()
        save_config(self.cfg)

    def _save_cookies_pref(self):
        self.cfg["cookies_browser"] = self.cookies_browser.get()
        save_config(self.cfg)

    # ---- HTTP bridge for browser extension ----
    def _start_bridge(self):
        _BridgeHandler.app = self
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", LOCAL_PORT), _BridgeHandler)
        except OSError as e:
            self.log(f"[bridge] port {LOCAL_PORT} unavailable ({e}); browser one-click disabled.")
            return
        self._bridge = srv
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        self.log(f"[bridge] listening on http://127.0.0.1:{LOCAL_PORT}  — browser extension can send URLs.")

    def enqueue_url(self, url):
        """Called from HTTP bridge (background thread). Marshal to UI thread."""
        self.msg_queue.put(("enqueue", url))

    URL_RE = __import__("re").compile(r"https?://[^\s'\"<>]+", __import__("re").I)
    KNOWN_HOSTS = (
        "youtube.com", "youtu.be", "vimeo.com", "tiktok.com", "instagram.com",
        "facebook.com", "fb.watch", "twitter.com", "x.com", "twitch.tv",
        "reddit.com", "dailymotion.com", "pinterest.com", "soundcloud.com",
        "bilibili.com", "rumble.com", "bitchute.com", "odysee.com"
    )

    def _looks_like_video_url(self, s):
        if not s:
            return False
        s = s.strip()
        m = self.URL_RE.match(s)
        if not m:
            return False
        u = m.group(0).lower()
        if any(h in u for h in self.KNOWN_HOSTS):
            return True
        if any(ext in u for ext in (".mp4", ".m3u8", ".mpd", ".webm", ".mov", ".mkv")):
            return True
        return False

    def _poll_clipboard(self):
        if self._clip_watch.get():
            try:
                clip = self.root.clipboard_get()
            except tk.TclError:
                clip = ""
            if clip and clip != self._last_clip and self._looks_like_video_url(clip):
                self._last_clip = clip
                self._handle_clipboard_url(clip.strip())
            else:
                self._last_clip = clip
        self.root.after(1200, self._poll_clipboard)

    def _on_download_complete(self):
        files = list(self._last_files)
        n = len(files)
        if n == 0:
            self.set_status("No files saved (all errored or skipped).")
            return
        title = f"✓ Downloaded {n} file{'s' if n > 1 else ''}"
        first = Path(files[0])
        out_dir = first.parent if first.exists() else Path(self.folder_var.get())
        self.set_status(f"{title} → {out_dir}")
        self._show_done_banner(files, out_dir)
        self._native_notify(title, str(first.name) if first.exists() else str(out_dir))
        try:
            self.root.bell()
        except Exception:
            pass

    def _show_done_banner(self, files, out_dir):
        # Remove old banner if exists
        if getattr(self, "_banner", None):
            try:
                self._banner.destroy()
            except Exception:
                pass
        bn = tk.Frame(self.root, bg="#1f4a2a", relief="flat", bd=0)
        bn.pack(fill="x", padx=20, pady=(6, 0), before=self.progress)
        self._banner = bn

        n = len(files)
        msg = f"✓  Downloaded {n} file{'s' if n > 1 else ''}"
        lbl = tk.Label(bn, text=msg, bg="#1f4a2a", fg="#a3e9c5",
                       font=("Helvetica", 12, "bold"), padx=12, pady=10)
        lbl.pack(side="left")

        # Filename preview (first only, truncated)
        if files:
            short = Path(files[0]).name
            if len(short) > 50:
                short = short[:47] + "…"
            tk.Label(bn, text=short, bg="#1f4a2a", fg="#7fc99c",
                     font=("Menlo", 10)).pack(side="left", padx=(0, 8))

        # Buttons
        btn_frame = tk.Frame(bn, bg="#1f4a2a")
        btn_frame.pack(side="right", padx=8, pady=6)

        def open_file():
            if files and Path(files[0]).exists():
                self._open_path(files[0])
            else:
                self._open_path(str(out_dir))

        def reveal():
            if files and Path(files[0]).exists():
                self._reveal_in_finder(files[0])
            else:
                self._open_path(str(out_dir))

        def dismiss():
            try:
                bn.destroy()
                self._banner = None
            except Exception:
                pass

        ttk.Button(btn_frame, text="▶ Open", style="Brand.TButton",
                   command=open_file).pack(side="left", padx=(0, 4))
        ttk.Button(btn_frame, text="📂 Show in Finder", style="Ghost.TButton",
                   command=reveal).pack(side="left", padx=(0, 4))
        ttk.Button(btn_frame, text="✕", style="Ghost.TButton",
                   command=dismiss).pack(side="left")

        # Auto-dismiss after 30s
        self.root.after(30000, dismiss)

    def _open_path(self, path):
        try:
            if platform.system() == "Darwin":
                subprocess.run(["open", str(path)])
            elif platform.system() == "Windows":
                os.startfile(str(path))  # noqa
            else:
                subprocess.run(["xdg-open", str(path)])
        except Exception as e:
            self.log(f"[open] failed: {e}")

    def _reveal_in_finder(self, path):
        try:
            if platform.system() == "Darwin":
                subprocess.run(["open", "-R", str(path)])
            elif platform.system() == "Windows":
                subprocess.run(["explorer", "/select,", str(path)])
            else:
                subprocess.run(["xdg-open", str(Path(path).parent)])
        except Exception as e:
            self.log(f"[reveal] failed: {e}")

    def _native_notify(self, title, body):
        try:
            if platform.system() == "Darwin":
                # Use AppleScript display notification
                script = f'display notification "{body}" with title "{APP_NAME}" subtitle "{title}" sound name "Glass"'
                subprocess.Popen(["osascript", "-e", script])
            elif platform.system() == "Windows":
                # Best effort PowerShell toast (Win10+)
                ps = (
                    '[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null; '
                    f'[xml]$x = \'<toast><visual><binding template="ToastText02"><text id="1">{title}</text><text id="2">{body}</text></binding></visual></toast>\'; '
                    '$t = New-Object Windows.Data.Xml.Dom.XmlDocument; $t.LoadXml($x.OuterXml); '
                    '$n = [Windows.UI.Notifications.ToastNotification]::new($t); '
                    f'[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("{APP_NAME}").Show($n)'
                )
                subprocess.Popen(["powershell", "-Command", ps],
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            else:
                subprocess.Popen(["notify-send", APP_NAME, f"{title}\n{body}"])
        except Exception:
            pass

    def _receive_url(self, url):
        """URL pushed from browser extension via HTTP bridge — auto-start download."""
        cur = self.url_text.get("1.0", "end").strip()
        if url in cur:
            self.log(f"[bridge] already queued: {url[:60]}…")
            return
        new_val = (cur + "\n" + url).strip() if cur else url
        self.url_text.delete("1.0", "end")
        self.url_text.insert("1.0", new_val)
        # Lift window so user sees download starting
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
            self.root.bell()
        except Exception:
            pass
        self.log(f"[bridge] received from browser: {url}")
        # Auto-start if nothing downloading
        if self.active_thread is None or not self.active_thread.is_alive():
            self._start_download()
        else:
            self.set_status(f"Queued: {url[:60]}… (will start after current)")

    def _handle_clipboard_url(self, url):
        # Skip if URL already in textbox
        existing = self.url_text.get("1.0", "end")
        if url in existing:
            return
        # Toast-like banner using status bar
        self.set_status(f"📋 Detected: {url[:60]}…  Press ⬇ Download to grab.")
        # Paste into textbox automatically (append if not empty)
        cur = existing.strip()
        new_val = (cur + "\n" + url).strip() if cur else url
        self.url_text.delete("1.0", "end")
        self.url_text.insert("1.0", new_val)
        # Soft chime via bell
        try:
            self.root.bell()
        except Exception:
            pass

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()
                if kind == "log":
                    self.log_text.configure(state="normal")
                    self.log_text.insert("end", payload + ("\n" if not payload.endswith("\n") else ""))
                    self.log_text.see("end")
                    self.log_text.configure(state="disabled")
                elif kind == "status":
                    self.status_var.set(payload)
                elif kind == "progress":
                    self.progress["value"] = payload
                elif kind == "done":
                    self.dl_btn.configure(state="normal")
                    self.cancel_btn.configure(state="disabled")
                    self.pause_btn.configure(state="disabled")
                    self._refresh_resume_banner()
                    self._on_download_complete()
                elif kind == "enqueue":
                    self._receive_url(payload)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    # ------ download logic ------
    def _start_download(self):
        urls = [u.strip() for u in self.url_text.get("1.0", "end").splitlines() if u.strip()]
        if not urls:
            messagebox.showwarning(APP_NAME, "Paste at least one URL.")
            return

        out_dir = self.folder_var.get().strip() or DEFAULT_DOWNLOAD_DIR
        Path(out_dir).mkdir(parents=True, exist_ok=True)

        fmt_key = self.format_var.get()
        if fmt_key not in FORMAT_OPTIONS:
            fmt_key = "best_mp4"

        # persist
        self.cfg["download_dir"] = out_dir
        self.cfg["format"] = fmt_key
        save_config(self.cfg)

        self.cancel_flag = False
        self.paused = False
        self.dl_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.pause_btn.configure(state="normal")
        # Banner stays hidden while downloading; will reappear if pause keeps queue
        self.resume_banner.pack_forget()
        self.progress["value"] = 0

        self.active_thread = threading.Thread(
            target=self._run_download, args=(urls, out_dir, fmt_key), daemon=True
        )
        self.active_thread.start()

    def _cancel(self):
        self.cancel_flag = True
        self.paused = False
        self.log("[cancel] requested — finishing current segment + clearing queue.")

    def _pause(self):
        # Pause = cancel current job but keep queue + .part files for resume
        if self.active_thread is None or not self.active_thread.is_alive():
            return
        self.cancel_flag = True
        self.paused = True
        self.pause_btn.configure(state="disabled")
        self.log("[pause] requested — partial file kept. Click ▶ Resume Queue to continue.")

    def _check_resume_on_launch(self):
        """If state has pending queue, log notice + show resume banner."""
        queue = self.state.get("queue", [])
        if queue:
            self.log(f"[resume] {len(queue)} download(s) paused from last session.")
        self._refresh_resume_banner()

    def _refresh_resume_banner(self):
        """Show/hide top banner based on queue state."""
        queue = self.state.get("queue", [])
        if queue:
            count = len(queue)
            first_url = queue[0].get("url", "")
            label = f"⏸  {count} download{'s' if count > 1 else ''} paused"
            if first_url:
                short = first_url if len(first_url) <= 60 else first_url[:57] + "…"
                label += f"  ·  {short}"
            self.resume_banner_label.configure(text=label)
            # Pack banner BELOW header, ABOVE URL section (re-pack each call to ensure correct position)
            try:
                self.resume_banner.pack(fill="x", padx=20, pady=(0, 6), before=self.url_text.master)
            except Exception:
                self.resume_banner.pack(fill="x", padx=20, pady=(0, 6))
        else:
            self.resume_banner.pack_forget()

    def _discard_queue(self):
        """Clear paused queue + remove banner. Doesn't touch .part files on disk."""
        self.state["queue"] = []
        save_state(self.state)
        self._refresh_resume_banner()
        self.log("[resume] queue discarded.")
        self.set_status("Queue cleared.")

    def _resume_queue(self):
        """Pick up paused queue from state file and restart download."""
        queue = self.state.get("queue", [])
        if not queue:
            self.set_status("No paused downloads to resume.")
            self.resume_btn.pack_forget()
            return
        # Use first item's out_dir + fmt — assume consistent batch
        first = queue[0]
        out_dir = first.get("out_dir", DEFAULT_DOWNLOAD_DIR)
        fmt_key = first.get("fmt", "best_mp4")
        urls = [q["url"] for q in queue]
        # Repopulate URL textbox + folder
        self.url_text.delete("1.0", "end")
        self.url_text.insert("1.0", "\n".join(urls))
        self.folder_var.set(out_dir)
        if fmt_key in FORMAT_OPTIONS:
            self.format_var.set(fmt_key)
        self.log(f"[resume] {len(urls)} URL(s) — yt-dlp auto-continues from .part files.")
        self._start_download()

    def _build_ydl_opts(self, out_dir, fmt_key):
        fmt = FORMAT_OPTIONS[fmt_key]
        opts = {
            "format": fmt["format"],
            "outtmpl": str(Path(out_dir) / "%(title)s [%(id)s].%(ext)s"),
            "noplaylist": not self.playlist_var.get(),
            "writesubtitles": self.subtitles_var.get(),
            "writeautomaticsub": self.subtitles_var.get(),
            "subtitleslangs": ["en", "bn"] if self.subtitles_var.get() else [],
            "writethumbnail": self.thumbnail_var.get(),
            "ignoreerrors": True,
            "no_warnings": False,
            "progress_hooks": [self._progress_hook],
            "logger": _YDLLogger(self),
            "concurrent_fragment_downloads": 4,
            "retries": 5,
            "fragment_retries": 5,
        }
        if self.ffmpeg_path:
            opts["ffmpeg_location"] = self.ffmpeg_path
        cb = self.cookies_browser.get()
        if cb and cb != "none":
            opts["cookiesfrombrowser"] = (cb,)
        if "merge_output_format" in fmt and fmt["merge_output_format"]:
            opts["merge_output_format"] = fmt["merge_output_format"]
        if "extract_audio" in fmt:
            opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": fmt["extract_audio"],
                "preferredquality": "0",
            }]
        if self.thumbnail_var.get():
            opts.setdefault("postprocessors", []).append({
                "key": "FFmpegThumbnailsConvertor",
                "format": "jpg",
            })
        return opts

    def _progress_hook(self, d):
        if self.cancel_flag:
            raise yt_dlp.utils.DownloadError("cancelled by user")
        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            if total:
                pct = (done / total) * 100
                self.set_progress(pct)
            speed = d.get("speed") or 0
            eta = d.get("eta") or 0
            self.set_status(f"Downloading… {d.get('_percent_str','')} • {d.get('_speed_str','')} • ETA {eta}s")
        elif status == "finished":
            self.set_status("Processing…")
            self.set_progress(100)
            fn = d.get("filename") or (d.get("info_dict") or {}).get("filepath")
            if fn and fn not in self._last_files:
                self._last_files.append(fn)

    def _run_download(self, urls, out_dir, fmt_key):
        # Resume support: yt-dlp resumes .part files automatically via continuedl=True (default).
        # Persist URL list so app restart can offer to resume.
        opts = self._build_ydl_opts(out_dir, fmt_key)
        self._last_files = []
        self._batch_count = len(urls)
        total = len(urls)
        # Snapshot queue to state file so crash/quit still has resume point
        self.state["queue"] = [{"url": u, "out_dir": out_dir, "fmt": fmt_key} for u in urls]
        save_state(self.state)
        for i, url in enumerate(urls, 1):
            if self.cancel_flag:
                if self.paused:
                    self.log("[pause] kept in queue — will resume on restart or Resume button.")
                else:
                    self.log("[cancel] stopped, queue cleared.")
                    self.state["queue"] = []
                    save_state(self.state)
                break
            self.log(f"\n[{i}/{total}] → {url}")
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([url])
            except yt_dlp.utils.DownloadError as e:
                if "cancelled" in str(e):
                    if self.paused:
                        self.log("[pause] partial saved — resume keeps .part file.")
                    else:
                        self.log("[cancel] aborted.")
                    break
                self.log(f"[error] {e}")
            except Exception as e:
                self.log(f"[error] {e}")
            # Drop completed URL from queue
            self.state["queue"] = [q for q in self.state.get("queue", []) if q.get("url") != url]
            save_state(self.state)
        # If we finished normally (not paused), clear queue
        if not self.paused:
            self.state["queue"] = []
            save_state(self.state)
        self.msg_queue.put(("done", None))


class _YDLLogger:
    def __init__(self, app):
        self.app = app

    def debug(self, msg):
        if msg.startswith("[debug] "):
            return
        if msg.startswith("[download]") and "%" in msg:
            return  # progress hook handles
        self.app.log(msg)

    def info(self, msg):
        self.app.log(msg)

    def warning(self, msg):
        self.app.log(f"[warn] {msg}")

    def error(self, msg):
        self.app.log(f"[error] {msg}")


def main():
    root = tk.Tk()
    DownloaderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
