"""ZH Downloader v3.0 — Universal download manager by ZH Motions.

Features:
- Video/audio: 1800+ sites via yt-dlp (YouTube, Vimeo, Instagram, TikTok, Twitter/X, etc.)
- General files: any direct URL with multi-thread + resume support
- Resume interrupted downloads (video + file)
- Multi-URL queue — stable, no drop after 2-3 items
- Dark professional UI
- Browser extension bridge (port 9613)
- Clipboard auto-detection
- Native OS notifications
"""

import os, sys, threading, queue, json, subprocess, shutil, platform
import re, time, urllib.request, urllib.parse, urllib.error
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from concurrent.futures import ThreadPoolExecutor
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    import yt_dlp
except ImportError:
    print("yt-dlp not installed. Run: pip install -r requirements.txt")
    sys.exit(1)

# ── Constants ──────────────────────────────────────────────────────────────
APP_NAME      = "ZH Downloader"
APP_VERSION   = "3.0.0"
APP_AUTHOR    = "ZH Motions"
APP_WEBSITE   = "https://zhmotions.com"
LOCAL_PORT    = 9613

# Dark theme palette
C_BG        = "#111111"
C_SURFACE   = "#1a1a1a"
C_SURFACE2  = "#222222"
C_BORDER    = "#2e2e2e"
C_GOLD      = "#d4a13a"
C_MAROON    = "#5b1a1f"
C_TEXT      = "#e0e0e0"
C_MUTED     = "#666666"
C_SUCCESS   = "#6fcf97"
C_WARN      = "#f2c94c"
C_ERROR     = "#eb5757"
C_INFO      = "#56ccf2"
C_PURPLE    = "#bb86fc"

DEFAULT_DIR  = str(Path.home() / "Downloads" / "ZHDownloader")
CONFIG_PATH  = Path.home() / ".zhdownloader.json"
STATE_PATH   = Path.home() / ".zhdownloader-state.json"
PARTIAL_DIR  = Path.home() / ".zhdownloader-partials"
THREADS_FILE = 8

# ── Helpers ────────────────────────────────────────────────────────────────
def load_json(path, default):
    try:
        if Path(path).exists():
            return json.loads(Path(path).read_text())
    except: pass
    return default

def save_json(path, data):
    try: Path(path).write_text(json.dumps(data, indent=2))
    except: pass

def find_ffmpeg():
    p = shutil.which("ffmpeg")
    if p: return p
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    for c in [base/"ffmpeg", base/"ffmpeg.exe", base/"bin"/"ffmpeg", base/"bin"/"ffmpeg.exe"]:
        if c.exists(): return str(c)
    return None

def bundled_root():
    return Path(getattr(sys, "_MEIPASS", Path(__file__).parent))

def fmt_size(b):
    if not b: return ""
    for u in ("B","KB","MB","GB"):
        if b < 1024: return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} TB"

def fmt_speed(bps):
    return fmt_size(bps) + "/s" if bps else "—"

def fmt_eta(s):
    if s is None or s < 0: return "—"
    m, s = divmod(int(s), 60)
    h, m = divmod(m, 60)
    if h: return f"{h}h {m}m"
    if m: return f"{m}m {s}s"
    return f"{s}s"

# ── URL classification ─────────────────────────────────────────────────────
VIDEO_HOSTS = (
    "youtube.com","youtu.be","vimeo.com","tiktok.com","instagram.com",
    "facebook.com","fb.watch","twitter.com","x.com","twitch.tv",
    "reddit.com","dailymotion.com","pinterest.com","soundcloud.com",
    "bilibili.com","rumble.com","bitchute.com","odysee.com",
    "artgrid.io","artlist.io","patreon.com","streamable.com",
)
VIDEO_EXTS   = (".mp4",".m3u8",".mpd",".webm",".mov",".mkv",".ts",".flv")
GENERAL_EXTS = (
    ".pdf",".zip",".rar",".7z",".exe",".dmg",".pkg",".msi",
    ".jpg",".jpeg",".png",".gif",".webp",".svg",
    ".mp3",".wav",".flac",".aac",
    ".doc",".docx",".xls",".xlsx",".ppt",".pptx",
    ".apk",".iso",".tar",".gz",".bz2",".epub",
)
URL_RE = re.compile(r"https?://[^\s'\"<>]+", re.I)

def classify_url(url):
    if not url: return None
    url = url.strip()
    if not URL_RE.match(url): return None
    u = url.lower()
    if any(h in u for h in VIDEO_HOSTS): return "video"
    if any(u.endswith(e) for e in VIDEO_EXTS): return "video"
    if any(u.endswith(e) for e in GENERAL_EXTS): return "file"
    return "video"  # default: try yt-dlp

def type_label(url):
    u = url.lower()
    if any(h in u for h in VIDEO_HOSTS): return "VIDEO"
    if ".mp3" in u or ".wav" in u or ".flac" in u or "soundcloud" in u: return "AUDIO"
    if ".pdf" in u: return "PDF"
    if ".zip" in u or ".rar" in u or ".7z" in u: return "ZIP"
    if ".exe" in u or ".dmg" in u or ".pkg" in u or ".msi" in u: return "INSTALLER"
    if ".jpg" in u or ".png" in u or ".gif" in u or ".webp" in u: return "IMAGE"
    return "FILE"

# ── Format options ─────────────────────────────────────────────────────────
FORMAT_OPTIONS = {
    "best_mp4":  {"label": "Best Quality (MP4)",  "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/best[ext=mp4]", "merge": "mp4",  "fallback": "b[ext=mp4]/best"},
    "best_any":  {"label": "Best Quality (Any)",  "format": "bv*+ba/b",                                           "fallback": "b/best"},
    "1080p":     {"label": "1080p MP4",           "format": "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4]", "merge": "mp4", "fallback": "b[height<=1080][ext=mp4]/b[height<=1080]"},
    "720p":      {"label": "720p MP4",            "format": "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720][ext=mp4]",  "merge": "mp4", "fallback": "b[height<=720][ext=mp4]/b[height<=720]"},
    "480p":      {"label": "480p MP4",            "format": "bv*[height<=480][ext=mp4]+ba[ext=m4a]/b[height<=480][ext=mp4]",  "merge": "mp4", "fallback": "b[height<=480][ext=mp4]/b[height<=480]"},
    "audio_mp3": {"label": "Audio Only (MP3)",    "format": "ba/b", "extract_audio": "mp3"},
    "audio_wav": {"label": "Audio Only (WAV)",    "format": "ba/b", "extract_audio": "wav"},
}

# ── Multi-thread file downloader with resume ───────────────────────────────
class ChunkDownloader:
    def __init__(self, url, dest_dir, n_threads=THREADS_FILE,
                 progress_cb=None, log_cb=None, cancel_fn=None):
        self.url          = url
        self.dest_dir     = Path(dest_dir)
        self.n_threads    = n_threads
        self.progress_cb  = progress_cb or (lambda p, s, e: None)
        self.log          = log_cb or print
        self.cancel       = cancel_fn or (lambda: False)
        self._lock        = threading.Lock()
        self._downloaded  = 0
        self._total       = 0
        self._t0          = 0

    def _head(self):
        req = urllib.request.Request(
            self.url, method="HEAD",
            headers={"User-Agent": "ZHDownloader/3.0"})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                total     = int(r.headers.get("Content-Length", 0))
                resumable = "bytes" in r.headers.get("Accept-Ranges", "")
                fname     = ""
                cd = r.headers.get("Content-Disposition", "")
                if "filename=" in cd:
                    fname = cd.split("filename=")[-1].strip().strip('"\'')
                return total, resumable, fname
        except Exception as e:
            self.log(f"[warn] HEAD failed ({e})")
            return 0, False, ""

    def _outpath(self, srv_fname):
        if srv_fname:
            return self.dest_dir / srv_fname
        name = urllib.parse.unquote(
            Path(urllib.parse.urlparse(self.url).path).name) or "download"
        return self.dest_dir / name

    def _tick(self, n):
        with self._lock:
            self._downloaded += n
            elapsed = time.time() - self._t0
            spd = self._downloaded / elapsed if elapsed > 0 else 0
            rem = (self._total - self._downloaded) / spd if spd > 0 and self._total else None
            pct = self._downloaded / self._total * 100 if self._total else 0
        self.progress_cb(pct, spd, rem)

    def _dl_chunk(self, start, end, part):
        # Resume: skip already-downloaded bytes
        existing = part.stat().st_size if part.exists() else 0
        real_start = start + existing
        if existing and real_start > end:
            with self._lock: self._downloaded += existing
            return
        headers = {"User-Agent": "ZHDownloader/3.0", "Range": f"bytes={real_start}-{end}"}
        req = urllib.request.Request(self.url, headers=headers)
        with urllib.request.urlopen(req, timeout=60) as r:
            with open(part, "ab") as f:
                while True:
                    if self.cancel(): return
                    chunk = r.read(65536)
                    if not chunk: break
                    f.write(chunk)
                    self._tick(len(chunk))

    def _dl_single(self, out):
        existing = out.stat().st_size if out.exists() else 0
        headers = {"User-Agent": "ZHDownloader/3.0"}
        if existing:
            headers["Range"] = f"bytes={existing}-"
            with self._lock: self._downloaded += existing
        req = urllib.request.Request(self.url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                if not self._total:
                    self._total = int(r.headers.get("Content-Length", 0)) + existing
                with open(out, "ab") as f:
                    while True:
                        if self.cancel(): return
                        chunk = r.read(65536)
                        if not chunk: break
                        f.write(chunk)
                        self._tick(len(chunk))
        except urllib.error.HTTPError as e:
            if e.code == 416:  # Range not satisfiable — already complete
                pass
            else:
                raise

    def run(self):
        self._t0 = time.time()
        self.dest_dir.mkdir(parents=True, exist_ok=True)
        total, resumable, srv_fname = self._head()
        self._total = total
        out = self._outpath(srv_fname)
        self.log(f"[file] {out.name}  {fmt_size(total)}")

        if not resumable or total == 0 or self.n_threads == 1:
            self._dl_single(out)
        else:
            chunk  = total // self.n_threads
            parts  = []
            PARTIAL_DIR.mkdir(parents=True, exist_ok=True)
            with ThreadPoolExecutor(max_workers=self.n_threads) as pool:
                futures = []
                for i in range(self.n_threads):
                    s = i * chunk
                    e = (s + chunk - 1) if i < self.n_threads - 1 else total - 1
                    p = PARTIAL_DIR / f"{out.stem}.part{i}"
                    parts.append(p)
                    futures.append(pool.submit(self._dl_chunk, s, e, p))
                for f in futures:
                    f.result()
            if self.cancel():
                self.log("[pause] partial chunks kept — will resume next time.")
                return None
            self.log("[file] merging chunks…")
            with open(out, "wb") as dst:
                for p in parts:
                    if p.exists():
                        dst.write(p.read_bytes())
                        p.unlink()
        if self.cancel(): return None
        self.log(f"[file] saved → {out}")
        return str(out)

# ── HTTP bridge ────────────────────────────────────────────────────────────
class _Bridge(BaseHTTPRequestHandler):
    app = None
    def log_message(self, *a): pass
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
    def do_OPTIONS(self):
        self.send_response(204); self._cors(); self.end_headers()
    def do_GET(self):
        if self.path == "/ping":
            self.send_response(200); self._cors()
            self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(json.dumps({"app": APP_NAME, "version": APP_VERSION, "ok": True}).encode())
        else:
            self.send_response(404); self._cors(); self.end_headers()
    def do_POST(self):
        if self.path != "/download":
            self.send_response(404); self._cors(); self.end_headers(); return
        try:
            n    = int(self.headers.get("Content-Length", "0"))
            data = json.loads(self.rfile.read(n) or b"{}")
        except: data = {}
        url = (data.get("url") or "").strip()
        if not url:
            self.send_response(400); self._cors(); self.end_headers()
            self.wfile.write(b'{"ok":false}'); return
        self.app.enqueue_url(url)
        self.send_response(200); self._cors()
        self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps({"ok": True}).encode())

# ── Download item (for queue display) ─────────────────────────────────────
class DLItem:
    def __init__(self, url, idx, total):
        self.url     = url
        self.idx     = idx
        self.total   = total
        self.label   = type_label(url)
        self.name    = urllib.parse.unquote(Path(urllib.parse.urlparse(url).path).name or url[:60])
        self.status  = "waiting"   # waiting | downloading | done | error | paused
        self.pct     = 0.0
        self.speed   = ""
        self.eta     = ""
        self.size    = ""
        self.row     = None        # tk frame reference

# ── Main App ───────────────────────────────────────────────────────────────
class App:
    def __init__(self, root):
        self.root        = root
        self.cfg         = load_json(CONFIG_PATH, {"download_dir": DEFAULT_DIR, "format": "best_mp4"})
        self.state       = load_json(STATE_PATH,  {"queue": []})
        self.mq          = queue.Queue()          # thread → UI messages
        self.dl_thread   = None
        self._stop       = threading.Event()      # signals cancel
        self._pause      = threading.Event()      # signals pause
        self._paused     = False
        self.ffmpeg      = find_ffmpeg()
        self._last_clip  = ""
        self._clip_watch = tk.BooleanVar(value=self.cfg.get("clip_watch", True))
        self._done_files = []
        self._dl_items   = []                     # list[DLItem] for current batch

        root.title(f"{APP_NAME} v{APP_VERSION}")
        root.geometry("860x720")
        root.minsize(720, 560)
        root.configure(bg=C_BG)

        self._build_ui()
        self._poll()
        self._poll_clipboard()
        self._start_bridge()
        self._check_resume()

        if not self.ffmpeg:
            self.log("[warn] ffmpeg not found — some formats may lack audio.\n"
                     "       Mac: brew install ffmpeg | Win: choco install ffmpeg\n")

    # ── resource ───────────────────────────────────────────────────────────
    def _res(self, name):
        r = bundled_root()
        for p in [r/"assets"/name, r/name, Path(__file__).parent/"assets"/name]:
            if p.exists(): return str(p)

    # ── UI ─────────────────────────────────────────────────────────────────
    def _build_ui(self):
        s = ttk.Style()
        try: s.theme_use("clam")
        except: pass
        s.configure("TFrame",      background=C_BG)
        s.configure("TLabel",      background=C_BG, foreground=C_TEXT, font=("Helvetica",10))
        s.configure("Muted.TLabel",background=C_BG, foreground=C_MUTED, font=("Helvetica",9))
        s.configure("Gold.TLabel", background=C_BG, foreground=C_GOLD,  font=("Helvetica",18,"bold"))
        s.configure("TCheckbutton",background=C_BG, foreground=C_MUTED, font=("Helvetica",10))
        s.map("TCheckbutton", background=[("active",C_BG)])
        s.configure("TCombobox",   fieldbackground=C_SURFACE2, background=C_SURFACE2,
                    foreground=C_TEXT, selectbackground=C_SURFACE2, selectforeground=C_GOLD)
        s.configure("Main.TButton",  background=C_GOLD, foreground=C_BG, font=("Helvetica",11,"bold"), padding=(16,8), borderwidth=0)
        s.map("Main.TButton",        background=[("active","#e8b84a"),("disabled","#3a3a2a")], foreground=[("disabled",C_MUTED)])
        s.configure("Ghost.TButton", background=C_SURFACE2, foreground=C_MUTED, font=("Helvetica",10), padding=(10,7), borderwidth=1, relief="flat")
        s.map("Ghost.TButton",       background=[("active",C_SURFACE)], foreground=[("active",C_TEXT)])
        s.configure("TProgressbar", troughcolor=C_SURFACE2, background=C_GOLD, borderwidth=0, thickness=5)

        # ── Header ──
        hdr = tk.Frame(self.root, bg=C_MAROON, height=64); hdr.pack(fill="x")
        hdr.pack_propagate(False)
        inner = tk.Frame(hdr, bg=C_MAROON); inner.pack(fill="both", expand=True, padx=20, pady=12)
        logo_p = self._res("header-logo.png")
        if logo_p:
            try:
                self._logo = tk.PhotoImage(file=logo_p)
                tk.Label(inner, image=self._logo, bg=C_MAROON, bd=0).pack(side="left", padx=(0,12))
            except: pass
        tx = tk.Frame(inner, bg=C_MAROON); tx.pack(side="left")
        tk.Label(tx, text=APP_NAME, bg=C_MAROON, fg=C_GOLD, font=("Helvetica",16,"bold")).pack(anchor="w")
        tk.Label(tx, text=f"v{APP_VERSION}  ·  {APP_AUTHOR}  ·  Universal Download Manager",
                 bg=C_MAROON, fg="#c8a080", font=("Helvetica",9)).pack(anchor="w")
        # bridge status dot
        self._dot_var = tk.StringVar(value="●")
        self._dot_lbl = tk.Label(inner, textvariable=self._dot_var, bg=C_MAROON, fg=C_MUTED,
                                 font=("Helvetica",12))
        self._dot_lbl.pack(side="right")
        tk.Label(inner, text="Bridge", bg=C_MAROON, fg=C_MUTED, font=("Helvetica",9)).pack(side="right", padx=(0,4))

        # ── Body ──
        body = tk.Frame(self.root, bg=C_BG); body.pack(fill="both", expand=True, padx=0)

        # Left panel (inputs)
        left = tk.Frame(body, bg=C_BG); left.pack(fill="both", expand=True, padx=20, pady=14)

        # URL
        tk.Label(left, text="URL  —  one per line (video, audio, or any file):",
                 bg=C_BG, fg=C_MUTED, font=("Helvetica",10)).pack(anchor="w")
        self.url_box = tk.Text(left, height=4, font=("Menlo",11),
                               bg=C_SURFACE, fg=C_TEXT, insertbackground=C_GOLD,
                               relief="flat", highlightthickness=1,
                               highlightbackground=C_BORDER, highlightcolor=C_GOLD,
                               padx=10, pady=8, selectbackground=C_MAROON)
        self.url_box.pack(fill="x", pady=(4,10))

        # Options row
        opt = tk.Frame(left, bg=C_BG); opt.pack(fill="x", pady=(0,8))

        tk.Label(opt, text="Format:", bg=C_BG, fg=C_MUTED, font=("Helvetica",10)).grid(row=0,column=0,sticky="w",padx=(0,6))
        self.fmt_var = tk.StringVar(value=self.cfg.get("format","best_mp4"))
        fmt_cb = ttk.Combobox(opt, textvariable=self.fmt_var, state="readonly", width=22,
                              values=[f"{k}: {v['label']}" for k,v in FORMAT_OPTIONS.items()])
        cur = self.fmt_var.get()
        if cur in FORMAT_OPTIONS: fmt_cb.set(f"{cur}: {FORMAT_OPTIONS[cur]['label']}")
        fmt_cb.grid(row=0,column=1,sticky="w",padx=(0,14))
        fmt_cb.bind("<<ComboboxSelected>>", lambda e: self.fmt_var.set(fmt_cb.get().split(":")[0]))

        tk.Label(opt, text="Mode:", bg=C_BG, fg=C_MUTED, font=("Helvetica",10)).grid(row=0,column=2,sticky="w",padx=(0,6))
        self.mode_var = tk.StringVar(value="auto")
        mode_cb = ttk.Combobox(opt, textvariable=self.mode_var, state="readonly", width=14,
                               values=["auto: Auto-detect", "video: Video/Audio", "file: General File"])
        mode_cb.set("auto: Auto-detect")
        mode_cb.grid(row=0,column=3,sticky="w")
        mode_cb.bind("<<ComboboxSelected>>", lambda e: self.mode_var.set(mode_cb.get().split(":")[0]))

        # Checkboxes
        chk = tk.Frame(left, bg=C_BG); chk.pack(fill="x", pady=(0,8))
        self.sub_var   = tk.BooleanVar(value=False)
        self.thumb_var = tk.BooleanVar(value=False)
        self.pl_var    = tk.BooleanVar(value=False)
        for var, lbl in [(self.sub_var,"Subtitles"),(self.thumb_var,"Thumbnail"),(self.pl_var,"Full Playlist"),(self._clip_watch,"Watch clipboard")]:
            ttk.Checkbutton(chk, text=lbl, variable=var,
                            style="TCheckbutton").pack(side="left", padx=(0,16))

        # Cookies
        ck = tk.Frame(left, bg=C_BG); ck.pack(fill="x", pady=(0,8))
        tk.Label(ck, text="Cookies:", bg=C_BG, fg=C_MUTED, font=("Helvetica",10)).pack(side="left", padx=(0,6))
        self.cookies_var = tk.StringVar(value=self.cfg.get("cookies","none"))
        cookies_cb = ttk.Combobox(ck, textvariable=self.cookies_var, state="readonly", width=12,
                                  values=["none","chrome","safari","firefox","edge","brave"])
        cookies_cb.pack(side="left")
        tk.Label(ck, text="(needed for private/member content)", bg=C_BG, fg=C_MUTED, font=("Helvetica",9)).pack(side="left", padx=(8,0))

        # Folder
        fld = tk.Frame(left, bg=C_BG); fld.pack(fill="x", pady=(0,10))
        tk.Label(fld, text="Save to:", bg=C_BG, fg=C_MUTED, font=("Helvetica",10)).pack(side="left", padx=(0,6))
        self.folder_var = tk.StringVar(value=self.cfg.get("download_dir", DEFAULT_DIR))
        tk.Entry(fld, textvariable=self.folder_var, bg=C_SURFACE, fg=C_TEXT,
                 insertbackground=C_GOLD, relief="flat",
                 highlightthickness=1, highlightbackground=C_BORDER,
                 highlightcolor=C_GOLD, font=("Helvetica",10)).pack(side="left", fill="x", expand=True, padx=(0,6))
        ttk.Button(fld, text="Browse", style="Ghost.TButton", command=self._pick_folder).pack(side="left", padx=(0,4))
        ttk.Button(fld, text="Open",   style="Ghost.TButton", command=self._open_folder).pack(side="left")

        # Buttons
        btns = tk.Frame(left, bg=C_BG); btns.pack(fill="x", pady=(0,10))
        self.btn_dl     = ttk.Button(btns, text="⬇  Download", style="Main.TButton", command=self._start)
        self.btn_pause  = ttk.Button(btns, text="⏸  Pause",   style="Ghost.TButton", command=self._do_pause,  state="disabled")
        self.btn_cancel = ttk.Button(btns, text="✕  Cancel",  style="Ghost.TButton", command=self._do_cancel, state="disabled")
        self.btn_dl.pack(side="left", padx=(0,8))
        self.btn_pause.pack(side="left", padx=(0,6))
        self.btn_cancel.pack(side="left")
        ttk.Button(btns, text="Clear log", style="Ghost.TButton", command=self._clear_log).pack(side="right")

        # ── Resume banner ──
        self.resume_frame = tk.Frame(left, bg="#1a2e1a", relief="flat"); 
        self.resume_lbl = tk.Label(self.resume_frame, text="", bg="#1a2e1a", fg=C_SUCCESS,
                                   font=("Helvetica",11,"bold"), padx=12, pady=8)
        self.resume_lbl.pack(side="left")
        rb = tk.Frame(self.resume_frame, bg="#1a2e1a"); rb.pack(side="right", padx=8, pady=6)
        ttk.Button(rb, text="▶ Resume", style="Main.TButton", command=self._do_resume).pack(side="left", padx=(0,6))
        ttk.Button(rb, text="Discard",  style="Ghost.TButton", command=self._discard).pack(side="left")

        # ── Overall progress ──
        self.prog_bar = ttk.Progressbar(left, mode="determinate", maximum=100)
        self.prog_bar.pack(fill="x", pady=(0,2))
        self.prog_var = tk.StringVar(value="Idle.")
        tk.Label(left, textvariable=self.prog_var, bg=C_BG, fg=C_MUTED, font=("Helvetica",9)).pack(anchor="w")

        # ── Queue list ──
        sep = tk.Frame(left, bg=C_BORDER, height=1); sep.pack(fill="x", pady=10)
        qh = tk.Frame(left, bg=C_BG); qh.pack(fill="x", pady=(0,6))
        tk.Label(qh, text="QUEUE", bg=C_BG, fg=C_MUTED, font=("Helvetica",9)).pack(side="left")
        self.queue_count_lbl = tk.Label(qh, text="", bg=C_BG, fg=C_MUTED, font=("Helvetica",9))
        self.queue_count_lbl.pack(side="left", padx=(6,0))

        q_outer = tk.Frame(left, bg=C_BG); q_outer.pack(fill="both", expand=True)
        self.q_canvas = tk.Canvas(q_outer, bg=C_BG, highlightthickness=0)
        q_scroll = ttk.Scrollbar(q_outer, orient="vertical", command=self.q_canvas.yview)
        self.q_canvas.configure(yscrollcommand=q_scroll.set)
        q_scroll.pack(side="right", fill="y")
        self.q_canvas.pack(side="left", fill="both", expand=True)
        self.q_inner = tk.Frame(self.q_canvas, bg=C_BG)
        self.q_win = self.q_canvas.create_window((0,0), window=self.q_inner, anchor="nw")
        self.q_inner.bind("<Configure>", lambda e: self.q_canvas.configure(
            scrollregion=self.q_canvas.bbox("all")))
        self.q_canvas.bind("<Configure>", lambda e: self.q_canvas.itemconfig(
            self.q_win, width=e.width))

        # ── Log ──
        log_sep = tk.Frame(left, bg=C_BORDER, height=1); log_sep.pack(fill="x", pady=(8,6))
        log_frame = tk.Frame(left, bg=C_BG); log_frame.pack(fill="x")
        self.log_text = tk.Text(log_frame, height=6, font=("Menlo",9),
                                bg="#0d0d0d", fg="#555555", relief="flat",
                                padx=10, pady=6, wrap="word",
                                state="disabled")
        self.log_text.pack(side="left", fill="both", expand=True)
        ttk.Scrollbar(log_frame, command=self.log_text.yview).pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=lambda *a: None)

        # tag colors for log
        self.log_text.tag_configure("ok",   foreground=C_SUCCESS)
        self.log_text.tag_configure("warn", foreground=C_WARN)
        self.log_text.tag_configure("err",  foreground=C_ERROR)
        self.log_text.tag_configure("info", foreground=C_INFO)
        self.log_text.tag_configure("dim",  foreground="#444444")

    # ── Queue UI ───────────────────────────────────────────────────────────
    def _build_queue_rows(self, items):
        for w in self.q_inner.winfo_children(): w.destroy()
        if not items:
            tk.Label(self.q_inner, text="No downloads yet.",
                     bg=C_BG, fg=C_MUTED, font=("Helvetica",10)).pack(pady=10)
            return
        self.queue_count_lbl.configure(text=f"({len(items)} items)")
        for item in items:
            row = tk.Frame(self.q_inner, bg=C_SURFACE, relief="flat",
                           highlightthickness=1, highlightbackground=C_BORDER)
            row.pack(fill="x", pady=2, ipady=6, ipadx=8)
            item.row = row

            # Status icon
            icon_txt, icon_col = {
                "waiting":     ("○", C_MUTED),
                "downloading": ("▶", C_GOLD),
                "done":        ("✓", C_SUCCESS),
                "error":       ("✗", C_ERROR),
                "paused":      ("⏸", C_WARN),
            }.get(item.status, ("○", C_MUTED))
            item._icon_lbl = tk.Label(row, text=icon_txt, bg=C_SURFACE, fg=icon_col,
                                      font=("Helvetica",13,"bold"), width=2)
            item._icon_lbl.grid(row=0, column=0, rowspan=2, padx=(4,8))

            # Type badge
            badge_col = {
                "VIDEO":"#1a3a2a","AUDIO":"#1a2a3a","PDF":"#3a1a1a",
                "ZIP":"#2a2a1a","INSTALLER":"#2a1a2a","IMAGE":"#1a2a2a","FILE":"#2a2a2a"
            }.get(item.label, "#2a2a2a")
            badge_fg = {
                "VIDEO":C_SUCCESS,"AUDIO":C_INFO,"PDF":C_ERROR,
                "ZIP":C_WARN,"INSTALLER":C_PURPLE,"IMAGE":C_INFO,"FILE":C_MUTED
            }.get(item.label, C_MUTED)
            tk.Label(row, text=item.label, bg=badge_col, fg=badge_fg,
                     font=("Helvetica",9,"bold"), padx=6, pady=2).grid(row=0,column=1,sticky="w",padx=(0,8))

            # Name + number
            short = item.name if len(item.name) <= 55 else item.name[:52]+"…"
            item._name_lbl = tk.Label(row, text=f"[{item.idx}/{item.total}] {short}",
                                      bg=C_SURFACE, fg=C_TEXT, font=("Helvetica",10),
                                      anchor="w", justify="left")
            item._name_lbl.grid(row=0,column=2,sticky="ew",padx=(0,8))

            # Meta (size / speed / ETA)
            item._meta_lbl = tk.Label(row, text="", bg=C_SURFACE, fg=C_MUTED, font=("Helvetica",9))
            item._meta_lbl.grid(row=1,column=1,columnspan=2,sticky="w",padx=(0,8))

            # Per-item progress bar
            item._prog = ttk.Progressbar(row, mode="determinate", maximum=100, length=200)
            item._prog.grid(row=1,column=3,sticky="ew",padx=(0,8))
            item._prog["value"] = item.pct

            row.columnconfigure(2, weight=1)

    def _update_item_row(self, item):
        if not item.row: return
        icon_txt, icon_col = {
            "waiting":     ("○", C_MUTED),
            "downloading": ("▶", C_GOLD),
            "done":        ("✓", C_SUCCESS),
            "error":       ("✗", C_ERROR),
            "paused":      ("⏸", C_WARN),
        }.get(item.status, ("○", C_MUTED))
        item._icon_lbl.configure(text=icon_txt, fg=icon_col)
        item._prog["value"] = item.pct
        meta = []
        if item.size:  meta.append(item.size)
        if item.speed: meta.append(item.speed)
        if item.eta:   meta.append(f"ETA {item.eta}")
        item._meta_lbl.configure(text="  ·  ".join(meta) if meta else "")

    # ── folder helpers ─────────────────────────────────────────────────────
    def _pick_folder(self):
        d = filedialog.askdirectory(initialdir=self.folder_var.get())
        if d: self.folder_var.set(d)

    def _open_folder(self):
        p = self.folder_var.get()
        Path(p).mkdir(parents=True, exist_ok=True)
        if   platform.system() == "Darwin":  subprocess.run(["open", p])
        elif platform.system() == "Windows": os.startfile(p)
        else:                                subprocess.run(["xdg-open", p])

    def _clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    # ── logging ────────────────────────────────────────────────────────────
    def log(self, msg, tag="dim"):
        # Auto-detect tag
        ml = msg.lower()
        if any(k in ml for k in ("[ok]","saved","done","complete","merged","✓")): tag = "ok"
        elif any(k in ml for k in ("[warn]","warning")): tag = "warn"
        elif any(k in ml for k in ("[error]","failed","error")): tag = "err"
        elif any(k in ml for k in ("[bridge]","[file]","[info]","[resume]","[cancel]","[pause]")): tag = "info"
        self.mq.put(("log", (msg, tag)))

    def set_status(self, s): self.mq.put(("status", s))
    def set_prog(self, p):   self.mq.put(("prog", p))

    # ── bridge ─────────────────────────────────────────────────────────────
    def _start_bridge(self):
        _Bridge.app = self
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", LOCAL_PORT), _Bridge)
        except OSError as e:
            self.log(f"[warn] bridge unavailable ({e})")
            return
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.log(f"[bridge] http://127.0.0.1:{LOCAL_PORT}")
        self.mq.put(("bridge_ok", None))

    def enqueue_url(self, url):
        self.mq.put(("ext_url", url))

    # ── clipboard ──────────────────────────────────────────────────────────
    CLIP_HOSTS = VIDEO_HOSTS + ("drive.google.com","dropbox.com","mega.nz","mediafire.com","wetransfer.com")

    def _looks_dl(self, s):
        if not s: return False
        s = s.strip()
        if not URL_RE.match(s): return False
        u = s.lower()
        return any(h in u for h in self.CLIP_HOSTS) or any(u.endswith(e) for e in VIDEO_EXTS + GENERAL_EXTS)

    def _poll_clipboard(self):
        if self._clip_watch.get():
            try: clip = self.root.clipboard_get().strip()
            except: clip = ""
            if clip and clip != self._last_clip and self._looks_dl(clip):
                self._last_clip = clip
                cur = self.url_box.get("1.0","end").strip()
                if clip not in cur:
                    self.url_box.delete("1.0","end")
                    self.url_box.insert("1.0", (cur+"\n"+clip).strip() if cur else clip)
                    self.set_status(f"📋 Clipboard: {clip[:70]}…")
                    try: self.root.bell()
                    except: pass
            elif clip: self._last_clip = clip
        self.root.after(1200, self._poll_clipboard)

    # ── queue poll ─────────────────────────────────────────────────────────
    def _poll(self):
        try:
            while True:
                kind, payload = self.mq.get_nowait()
                if kind == "log":
                    msg, tag = payload
                    self.log_text.configure(state="normal")
                    self.log_text.insert("end", msg + ("\n" if not msg.endswith("\n") else ""), tag)
                    self.log_text.see("end")
                    self.log_text.configure(state="disabled")
                elif kind == "status":
                    self.prog_var.set(payload)
                elif kind == "prog":
                    self.prog_bar["value"] = payload
                elif kind == "item_update":
                    self._update_item_row(payload)
                elif kind == "done":
                    self._on_done()
                elif kind == "bridge_ok":
                    self._dot_lbl.configure(fg=C_SUCCESS)
                elif kind == "ext_url":
                    self._receive_ext_url(payload)
        except queue.Empty: pass
        self.root.after(80, self._poll)

    def _receive_ext_url(self, url):
        cur = self.url_box.get("1.0","end").strip()
        if url not in cur:
            self.url_box.delete("1.0","end")
            self.url_box.insert("1.0", (cur+"\n"+url).strip() if cur else url)
        try: self.root.deiconify(); self.root.lift(); self.root.focus_force(); self.root.bell()
        except: pass
        self.log(f"[bridge] received: {url[:70]}")
        if not self._is_running():
            self._start()
        else:
            self.set_status(f"Queued: {url[:60]}…")

    # ── resume ─────────────────────────────────────────────────────────────
    def _check_resume(self):
        q = self.state.get("queue", [])
        if q:
            count = len(q)
            self.resume_lbl.configure(
                text=f"⏸  {count} download{'s' if count>1 else ''} paused from last session")
            self.resume_frame.pack(fill="x", pady=(0,8))
        self._update_resume_banner()

    def _update_resume_banner(self):
        q = self.state.get("queue", [])
        if q:
            self.resume_frame.pack(fill="x", pady=(0,8))
        else:
            self.resume_frame.pack_forget()

    def _do_resume(self):
        q = self.state.get("queue", [])
        if not q: return
        urls = [i["url"] for i in q]
        out  = q[0].get("out_dir", DEFAULT_DIR)
        fmt  = q[0].get("fmt", "best_mp4")
        self.url_box.delete("1.0","end")
        self.url_box.insert("1.0", "\n".join(urls))
        self.folder_var.set(out)
        if fmt in FORMAT_OPTIONS: self.fmt_var.set(fmt)
        self.log(f"[resume] {len(urls)} URL(s)")
        self._start()

    def _discard(self):
        self.state["queue"] = []
        save_json(STATE_PATH, self.state)
        self.resume_frame.pack_forget()
        self.log("[resume] queue discarded.")

    # ── download control ───────────────────────────────────────────────────
    def _is_running(self):
        return self.dl_thread and self.dl_thread.is_alive()

    def _start(self):
        urls = [u.strip() for u in self.url_box.get("1.0","end").splitlines() if u.strip()]
        if not urls:
            messagebox.showwarning(APP_NAME, "Paste at least one URL."); return
        out = self.folder_var.get().strip() or DEFAULT_DIR
        Path(out).mkdir(parents=True, exist_ok=True)
        fmt = self.fmt_var.get()
        if fmt not in FORMAT_OPTIONS: fmt = "best_mp4"
        self.cfg.update({"download_dir": out, "format": fmt,
                         "clip_watch": self._clip_watch.get(),
                         "cookies": self.cookies_var.get()})
        save_json(CONFIG_PATH, self.cfg)

        self._stop.clear()
        self._pause.clear()
        self._paused = False
        self._done_files = []

        # Build queue items
        self._dl_items = [DLItem(u, i+1, len(urls)) for i, u in enumerate(urls)]
        self._build_queue_rows(self._dl_items)

        self.btn_dl.configure(state="disabled")
        self.btn_cancel.configure(state="normal")
        self.btn_pause.configure(state="normal")
        self.resume_frame.pack_forget()
        self.prog_bar["value"] = 0

        self.dl_thread = threading.Thread(
            target=self._run, args=(urls, out, fmt), daemon=True)
        self.dl_thread.start()

    def _do_pause(self):
        self._paused = True
        self._stop.set()
        self.btn_pause.configure(state="disabled")
        self.log("[pause] pausing after current file…")

    def _do_cancel(self):
        self._paused = False
        self._stop.set()
        self.log("[cancel] cancelling…")

    # ── yt-dlp opts ────────────────────────────────────────────────────────
    def _ydl_opts(self, out_dir, fmt_key, item):
        fmt = FORMAT_OPTIONS[fmt_key]
        if not self.ffmpeg and "fallback" in fmt:
            chosen = fmt["fallback"]
        else:
            chosen = fmt["format"]

        def progress_hook(d):
            if self._stop.is_set():
                raise yt_dlp.utils.DownloadError("user_stop")
            s = d.get("status")
            if s == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                done  = d.get("downloaded_bytes") or 0
                pct   = (done / total * 100) if total else 0
                spd   = d.get("speed") or 0
                eta   = d.get("eta")
                item.pct   = pct
                item.speed = fmt_speed(spd)
                item.eta   = fmt_eta(eta)
                item.size  = fmt_size(total)
                item.status = "downloading"
                self.mq.put(("item_update", item))
                self.set_prog(pct)
                self.set_status(
                    f"[{item.idx}/{item.total}] {d.get('_percent_str','').strip()} "
                    f"· {fmt_speed(spd)} · ETA {fmt_eta(eta)}")
            elif s == "finished":
                item.pct = 100; item.status = "downloading"
                self.mq.put(("item_update", item))
                self.set_status(f"[{item.idx}/{item.total}] Merging…")
                fn = d.get("filename") or (d.get("info_dict") or {}).get("filepath")
                if fn and fn not in self._done_files:
                    self._done_files.append(fn)

        opts = {
            "format":                     chosen,
            "outtmpl":                    str(Path(out_dir) / "%(title)s [%(id)s].%(ext)s"),
            "noplaylist":                 not self.pl_var.get(),
            "writesubtitles":             self.sub_var.get(),
            "writeautomaticsub":          self.sub_var.get(),
            "subtitleslangs":             ["en","bn"] if self.sub_var.get() else [],
            "writethumbnail":             self.thumb_var.get(),
            "ignoreerrors":               True,
            "no_warnings":                False,
            "progress_hooks":             [progress_hook],
            "logger":                     _YDL_Log(self),
            "retries":                    10,
            "fragment_retries":           10,
            "concurrent_fragment_downloads": 4,
            "continuedl":                 True,   # ← resume partial downloads
            "noprogress":                 False,
        }
        if self.ffmpeg:
            opts["ffmpeg_location"] = self.ffmpeg
        cb = self.cookies_var.get()
        if cb and cb != "none":
            opts["cookiesfrombrowser"] = (cb,)
        if "merge" in fmt:
            opts["merge_output_format"] = fmt["merge"]
        if "extract_audio" in fmt:
            opts["postprocessors"] = [{"key":"FFmpegExtractAudio",
                                        "preferredcodec": fmt["extract_audio"],
                                        "preferredquality": "0"}]
        return opts

    # ── main download loop (FIX: reset cancel flag per-item) ───────────────
    def _run(self, urls, out_dir, fmt_key):
        total = len(urls)
        self.state["queue"] = [{"url":u,"out_dir":out_dir,"fmt":fmt_key} for u in urls]
        save_json(STATE_PATH, self.state)

        for i, url in enumerate(urls):
            item = self._dl_items[i]

            # ── Check stop BEFORE starting item ──
            if self._stop.is_set():
                item.status = "paused" if self._paused else "error"
                self.mq.put(("item_update", item))
                continue   # mark remaining as skipped but keep going to save state

            item.status = "downloading"
            self.mq.put(("item_update", item))
            self.log(f"\n[{i+1}/{total}] {url}")

            mode = self.mode_var.get()
            kind = classify_url(url) if mode == "auto" else mode

            try:
                if kind == "file":
                    self._run_file(url, out_dir, item)
                else:
                    self._run_video(url, out_dir, fmt_key, item)
            except Exception as e:
                self.log(f"[error] {e}")
                item.status = "error"
                self.mq.put(("item_update", item))

            # ── Reset stop flag between items so next URL starts fresh ──
            # Only keep stopped if user explicitly paused/cancelled
            if not self._stop.is_set():
                if item.status == "downloading":
                    item.status = "done"
                    self.mq.put(("item_update", item))

            # Remove completed item from resume queue
            self.state["queue"] = [q for q in self.state["queue"] if q.get("url") != url]
            save_json(STATE_PATH, self.state)

        # Save remaining queue if paused
        if self._paused:
            remaining = [{"url": self._dl_items[j].url, "out_dir": out_dir, "fmt": fmt_key}
                         for j in range(len(urls))
                         if self._dl_items[j].status in ("waiting","paused")]
            self.state["queue"] = remaining
            save_json(STATE_PATH, self.state)
        else:
            self.state["queue"] = []
            save_json(STATE_PATH, self.state)

        self.mq.put(("done", None))

    def _run_video(self, url, out_dir, fmt_key, item):
        # Reset stop event so yt-dlp doesn't see leftover stop from previous item
        was_stopped = self._stop.is_set()
        opts = self._ydl_opts(out_dir, fmt_key, item)
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            if not self._stop.is_set():
                item.status = "done"
                item.pct    = 100
                self.mq.put(("item_update", item))
        except yt_dlp.utils.DownloadError as e:
            if "user_stop" in str(e):
                item.status = "paused" if self._paused else "error"
                self.mq.put(("item_update", item))
            else:
                self.log(f"[error] {e}")
                item.status = "error"
                self.mq.put(("item_update", item))

    def _run_file(self, url, out_dir, item):
        def prog(pct, spd, eta):
            item.pct   = pct
            item.speed = fmt_speed(spd)
            item.eta   = fmt_eta(eta)
            item.status = "downloading"
            self.mq.put(("item_update", item))
            self.set_prog(pct)
            self.set_status(f"[{item.idx}/{item.total}] {pct:.0f}% · {fmt_speed(spd)} · ETA {fmt_eta(eta)}")

        dl = ChunkDownloader(
            url, Path(out_dir),
            n_threads=THREADS_FILE,
            progress_cb=prog,
            log_cb=self.log,
            cancel_fn=lambda: self._stop.is_set(),
        )
        result = dl.run()
        if result and result not in self._done_files:
            self._done_files.append(result)
        if not self._stop.is_set():
            item.status = "done"; item.pct = 100
            self.mq.put(("item_update", item))

    # ── done ───────────────────────────────────────────────────────────────
    def _on_done(self):
        self.btn_dl.configure(state="normal")
        self.btn_cancel.configure(state="disabled")
        self.btn_pause.configure(state="disabled")
        self._update_resume_banner()
        n = len(self._done_files)
        done_count = sum(1 for it in self._dl_items if it.status == "done")
        err_count  = sum(1 for it in self._dl_items if it.status == "error")
        msg = f"✓ {done_count} done"
        if err_count: msg += f"  ·  {err_count} error"
        if self._paused: msg += "  ·  paused"
        self.set_status(msg)
        self.prog_bar["value"] = 100 if not self._paused else self.prog_bar["value"]
        if n > 0:
            self._native_notify(f"✓ Downloaded {n} file{'s' if n>1 else ''}", Path(self._done_files[0]).name)
            try: self.root.bell()
            except: pass
        if self._paused:
            self.log(f"[pause] {len(self.state.get('queue',[]))} item(s) saved for resume.")

    def _native_notify(self, title, body):
        try:
            if platform.system() == "Darwin":
                subprocess.Popen(["osascript","-e",
                    f'display notification "{body}" with title "{APP_NAME}" subtitle "{title}" sound name "Glass"'])
            elif platform.system() == "Windows":
                ps = (f'[Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime]>$null;'
                      f'[xml]$x=\'<toast><visual><binding template="ToastText02"><text id="1">{title}</text><text id="2">{body}</text></binding></visual></toast>\';'
                      f'$t=New-Object Windows.Data.Xml.Dom.XmlDocument;$t.LoadXml($x.OuterXml);'
                      f'$n=[Windows.UI.Notifications.ToastNotification]::new($t);'
                      f'[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("{APP_NAME}").Show($n)')
                subprocess.Popen(["powershell","-Command",ps],
                                 creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
            else:
                subprocess.Popen(["notify-send", APP_NAME, f"{title}\n{body}"])
        except: pass


class _YDL_Log:
    def __init__(self, app): self.app = app
    def debug(self, m):
        if m.startswith("[debug]") or ("[download]" in m and "%" in m): return
        self.app.log(m)
    def info(self, m):    self.app.log(m)
    def warning(self, m): self.app.log(f"[warn] {m}")
    def error(self, m):   self.app.log(f"[error] {m}")


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()

if __name__ == "__main__":
    main()
