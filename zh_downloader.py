"""
ZH Downloader v4.0 - Universal Download Manager by ZH Motions
IDM-style: queue, speed graph, per-item control, resume, scheduler
Bugs fixed: log clear, multi-URL queue drop, auto-detect, stop event reset
"""

import os, sys, threading, queue as Q, json, subprocess, shutil, platform
import re, time, urllib.request, urllib.parse, urllib.error, socket
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from concurrent.futures import ThreadPoolExecutor
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    import yt_dlp
except ImportError:
    print("Run: pip install -r requirements.txt"); sys.exit(1)

# -- Constants --------------------------------------------------------------
APP_NAME    = "ZH Downloader"
APP_VER     = "4.0.0"
APP_AUTHOR  = "ZH Motions"
APP_URL     = "https://zhmotions.com"
BRIDGE_PORT = 9613

# Colors - Sunset theme
BG      = "#160800"
SURF    = "#1e0d02"
SURF2   = "#271205"
BORDER  = "#3d1e08"
GOLD    = "#ff8c42"
MAROON  = "#8b2500"
TEXT    = "#ffddc0"
MUTED   = "#7a4a2a"
GREEN   = "#6fcf97"
YELLOW  = "#f2c94c"
RED     = "#eb5757"
BLUE    = "#56ccf2"
PURPLE  = "#bb86fc"
ACCENT  = "#ff6b35"

DEFAULT_DIR = str(Path.home() / "Downloads" / "ZHDownloader")
CFG_PATH    = Path.home() / ".zhdownloader.json"
STATE_PATH  = Path.home() / ".zhdownloader-state.json"
PARTS_DIR   = Path.home() / ".zhdownloader-parts"

THREADS = 8

# -- Helpers ----------------------------------------------------------------
def jload(p, d):
    try:
        if Path(p).exists(): return json.loads(Path(p).read_text())
    except: pass
    return d

def jsave(p, d):
    try: Path(p).write_text(json.dumps(d, indent=2))
    except: pass

def find_ff():
    p = shutil.which("ffmpeg")
    if p: return p
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    for c in [base/"ffmpeg", base/"ffmpeg.exe"]:
        if c.exists(): return str(c)
    return None

def res_path():
    return Path(getattr(sys, "_MEIPASS", Path(__file__).parent))

def sz(b):
    if not b: return ""
    for u in ("B","KB","MB","GB"):
        if b < 1024: return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} TB"

def spd(bps): return sz(bps)+"/s" if bps else "-"

def eta(s):
    if s is None or s < 0: return "-"
    m,s = divmod(int(s),60); h,m = divmod(m,60)
    if h: return f"{h}h{m}m"
    if m: return f"{m}m{s}s"
    return f"{s}s"

# -- URL classifier ---------------------------------------------------------
VH = ("youtube.com","youtu.be","vimeo.com","tiktok.com","instagram.com",
      "facebook.com","fb.watch","twitter.com","x.com","twitch.tv",
      "reddit.com","dailymotion.com","pinterest.com","soundcloud.com",
      "bilibili.com","rumble.com","bitchute.com","odysee.com","streamable.com",
      "artgrid.io","artlist.io","patreon.com")
VE = (".mp4",".m3u8",".mpd",".webm",".mov",".mkv",".ts",".flv")
FE = (".pdf",".zip",".rar",".7z",".exe",".dmg",".pkg",".msi",
      ".jpg",".jpeg",".png",".gif",".webp",".svg",".mp3",".wav",
      ".flac",".aac",".doc",".docx",".xls",".xlsx",".ppt",".pptx",
      ".apk",".iso",".tar",".gz",".bz2",".epub",".torrent")
URL_RE = re.compile(r"https?://[^\s'\"<>]+", re.I)

def classify(url):
    if not url: return None
    u = url.strip().lower()
    if not URL_RE.match(url.strip()): return None
    if any(h in u for h in VH): return "video"
    if any(u.endswith(e) for e in VE): return "video"
    if any(u.endswith(e) for e in FE): return "file"
    return "video"

def type_badge(url):
    u = url.lower()
    if any(h in u for h in VH): return "VIDEO"
    if any(x in u for x in (".mp3",".wav",".flac","soundcloud")): return "AUDIO"
    if ".pdf" in u: return "PDF"
    if any(x in u for x in (".zip",".rar",".7z")): return "ZIP"
    if any(x in u for x in (".exe",".dmg",".pkg",".msi")): return "APP"
    if any(x in u for x in (".jpg",".png",".gif",".webp")): return "IMG"
    return "FILE"

BADGE_COLORS = {
    "VIDEO": (GREEN,  "#1a3a2a"),
    "AUDIO": (BLUE,   "#1a2a3a"),
    "PDF":   (RED,    "#3a1a1a"),
    "ZIP":   (YELLOW, "#2a2a1a"),
    "APP":   (PURPLE, "#2a1a3a"),
    "IMG":   (BLUE,   "#1a2a2a"),
    "FILE":  (MUTED,  "#2a2a2a"),
}

# -- Format options ---------------------------------------------------------
# Premiere Pro needs H.264 (avc1) + AAC inside MP4. VP9/AV1 inside MP4 = won't open.
# Prefer native H.264 source (no re-encode); fall back to anything + force transcode.
_H264 = "bestvideo[vcodec^=avc1]+bestaudio[acodec^=mp4a]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]"
_H264_CAP = "bestvideo[vcodec^=avc1][height<={h}]+bestaudio[acodec^=mp4a]/bestvideo[ext=mp4][height<={h}]+bestaudio[ext=m4a]/best[ext=mp4][height<={h}]/best[height<={h}]"

FMTS = {
    # Premiere Pro compatible - prefer native avc1, transcode VP9/AV1 if needed
    "h264_best": {"label":"Best (Premiere Pro)",  "fmt":_H264,                          "merge":"mp4", "fb":"best[ext=mp4]/best", "pp_compat":True},
    "h264_2160": {"label":"4K (Premiere Pro)",    "fmt":_H264_CAP.format(h=2160),       "merge":"mp4", "fb":"best[height<=2160]", "pp_compat":True},
    "h264_1080": {"label":"1080p (Premiere Pro)", "fmt":_H264_CAP.format(h=1080),       "merge":"mp4", "fb":"best[height<=1080]", "pp_compat":True},
    "h264_720":  {"label":"720p (Premiere Pro)",  "fmt":_H264_CAP.format(h=720),        "merge":"mp4", "fb":"best[height<=720]",  "pp_compat":True},
    "h264_480":  {"label":"480p (Premiere Pro)",  "fmt":_H264_CAP.format(h=480),        "merge":"mp4", "fb":"best[height<=480]",  "pp_compat":True},
    # Standard - highest quality regardless of codec
    "best_mp4":  {"label":"Best MP4",  "fmt":"bestvideo+bestaudio/best", "merge":"mp4", "fb":"best"},
    "best":      {"label":"Best",      "fmt":"bestvideo+bestaudio/best", "fb":"best"},
    "2160p":     {"label":"4K",        "fmt":"bestvideo[height<=2160]+bestaudio/best[height<=2160]", "merge":"mp4", "fb":"best[height<=2160]"},
    "1080p":     {"label":"1080p",     "fmt":"bestvideo[height<=1080]+bestaudio/best[height<=1080]", "merge":"mp4", "fb":"best[height<=1080]"},
    "720p":      {"label":"720p",      "fmt":"bestvideo[height<=720]+bestaudio/best[height<=720]",   "merge":"mp4", "fb":"best[height<=720]"},
    "480p":      {"label":"480p",      "fmt":"bestvideo[height<=480]+bestaudio/best[height<=480]",   "merge":"mp4", "fb":"best[height<=480]"},
    # Audio
    "mp3":       {"label":"Audio MP3",     "fmt":"ba/b", "audio":"mp3"},
    "wav":       {"label":"Audio WAV",     "fmt":"ba/b", "audio":"wav"},
    "m4a":       {"label":"Audio M4A",     "fmt":"ba[ext=m4a]/ba/b", "audio":"m4a"},
}

# Height cap regex for HLS quality extraction
_HEIGHT_RE = re.compile(r"height<=(\d+)")

# -- Download item ----------------------------------------------------------
class DL:
    _id = 0
    def __init__(self, url, idx, total):
        DL._id += 1
        self.id      = DL._id
        self.url     = url
        self.idx     = idx
        self.total   = total
        self.badge   = type_badge(url)
        self.name    = urllib.parse.unquote(
                           Path(urllib.parse.urlparse(url).path).name or url[:50])[:80]
        self.status  = "waiting"   # waiting|downloading|done|error|paused|cancelled
        self.pct     = 0.0
        self.speed_v = 0
        self.eta_v   = None
        self.size_v  = 0
        self.done_f  = ""
        # UI refs
        self.row     = None
        self._lbl_icon = None
        self._lbl_name = None
        self._lbl_meta = None
        self._prog     = None
        self._spd_hist = []   # speed history for mini graph

# -- Multi-thread file downloader -------------------------------------------
class FileDL:
    def __init__(self, url, dest, n=THREADS, prog_cb=None, log_cb=None, cancel_fn=None):
        self.url    = url
        self.dest   = Path(dest)
        self.n      = n
        self.prog   = prog_cb or (lambda *a: None)
        self.log    = log_cb or print
        self.cancel = cancel_fn or (lambda: False)
        self._lock  = threading.Lock()
        self._done  = 0
        self._total = 0
        self._t0    = 0

    def _head(self):
        req = urllib.request.Request(self.url, method="HEAD",
              headers={"User-Agent":"ZHDownloader/4.0"})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                total = int(r.headers.get("Content-Length",0))
                res   = "bytes" in r.headers.get("Accept-Ranges","")
                fname = ""
                cd = r.headers.get("Content-Disposition","")
                if "filename=" in cd:
                    fname = cd.split("filename=")[-1].strip().strip('"\'')
                return total, res, fname
        except Exception as e:
            self.log(f"[warn] HEAD: {e}")
            return 0, False, ""

    def _out(self, srv):
        if srv: return self.dest / srv
        n = urllib.parse.unquote(Path(urllib.parse.urlparse(self.url).path).name) or "download"
        return self.dest / n

    def _tick(self, n):
        with self._lock:
            self._done += n
            el = time.time()-self._t0
            s  = self._done/el if el>0 else 0
            r  = (self._total-self._done)/s if s>0 and self._total else None
            p  = self._done/self._total*100 if self._total else 0
        self.prog(p, s, r)

    def _chunk(self, s, e, part):
        ex = part.stat().st_size if part.exists() else 0
        rs = s+ex
        if ex and rs>e:
            with self._lock: self._done += ex
            return
        h = {"User-Agent":"ZHDownloader/4.0","Range":f"bytes={rs}-{e}"}
        req = urllib.request.Request(self.url, headers=h)
        with urllib.request.urlopen(req, timeout=60) as r:
            with open(part,"ab") as f:
                while True:
                    if self.cancel(): return
                    c = r.read(65536)
                    if not c: break
                    f.write(c); self._tick(len(c))

    def _single(self, out):
        ex = out.stat().st_size if out.exists() else 0
        h  = {"User-Agent":"ZHDownloader/4.0"}
        if ex: h["Range"] = f"bytes={ex}-"
        with self._lock: self._done += ex
        req = urllib.request.Request(self.url, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                if not self._total:
                    self._total = int(r.headers.get("Content-Length",0))+ex
                with open(out,"ab") as f:
                    while True:
                        if self.cancel(): return
                        c = r.read(65536)
                        if not c: break
                        f.write(c); self._tick(len(c))
        except urllib.error.HTTPError as e:
            if e.code != 416: raise

    def run(self):
        self._t0 = time.time()
        self.dest.mkdir(parents=True, exist_ok=True)
        total, res, srv = self._head()
        self._total = total
        out = self._out(srv)
        self.log(f"[file] {out.name}  {sz(total)}")
        if not res or total==0 or self.n==1:
            self._single(out)
        else:
            chunk = total//self.n
            PARTS_DIR.mkdir(parents=True, exist_ok=True)
            parts = []
            with ThreadPoolExecutor(max_workers=self.n) as pool:
                futs = []
                for i in range(self.n):
                    s = i*chunk
                    e = (s+chunk-1) if i<self.n-1 else total-1
                    p = PARTS_DIR/f"{out.stem}.part{i}"
                    parts.append(p)
                    futs.append(pool.submit(self._chunk,s,e,p))
                for f in futs: f.result()
            if self.cancel():
                self.log("[pause] chunks saved for resume")
                return None
            with open(out,"wb") as dst:
                for p in parts:
                    if p.exists(): dst.write(p.read_bytes()); p.unlink()
        if self.cancel(): return None
        self.log(f"[done] {out}")
        return str(out)

# -- HTTP bridge ------------------------------------------------------------
class Bridge(BaseHTTPRequestHandler):
    app = None
    def log_message(self,*a): pass
    def _c(self):
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Access-Control-Allow-Methods","GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers","Content-Type")
    def do_OPTIONS(self):
        self.send_response(204); self._c(); self.end_headers()
    def do_GET(self):
        if self.path=="/ping":
            self.send_response(200); self._c()
            self.send_header("Content-Type","application/json"); self.end_headers()
            self.wfile.write(json.dumps({"app":APP_NAME,"version":APP_VER,"ok":True}).encode())
        else:
            self.send_response(404); self._c(); self.end_headers()
    def do_POST(self):
        if self.path!="/download":
            self.send_response(404); self._c(); self.end_headers(); return
        try:
            n = int(self.headers.get("Content-Length","0"))
            d = json.loads(self.rfile.read(n) or b"{}")
        except: d={}
        url     = (d.get("url")     or "").strip()
        referer = (d.get("referer") or "").strip()
        if not url:
            self.send_response(400); self._c(); self.end_headers()
            self.wfile.write(b'{"ok":false}'); return
        self.app._mq.put(("ext_url", (url, referer)))
        self.send_response(200); self._c()
        self.send_header("Content-Type","application/json"); self.end_headers()
        self.wfile.write(b'{"ok":true}')

# -- Main App ---------------------------------------------------------------
class App:
    def __init__(self, root):
        self.root      = root
        self.cfg       = jload(CFG_PATH, {"dir":DEFAULT_DIR,"fmt":"best_mp4","cookies":"none","clip":True})
        self.state     = jload(STATE_PATH,{"queue":[]})
        self._mq       = Q.Queue()
        self._stop     = threading.Event()
        self._paused   = False
        self._thread   = None
        self._items    = []
        self._done_files = []
        self._clip_last  = ""
        self._clip_on    = tk.BooleanVar(value=self.cfg.get("clip",True))
        self._spd_history = []
        self._sched_time  = None
        self._sched_timer = None   # [(time, bytes)] for speed graph
        self.ff        = find_ff()

        root.title(f"{APP_NAME} v{APP_VER}")
        root.geometry("920x800")
        root.minsize(780,640)
        root.configure(bg=BG)
        # Sunset window title bar tint (macOS)
        try:
            root.tk.call("wm", "attributes", root, "-transparentcolor", "")
        except: pass

        self._ui()
        self._poll()
        self._poll_clip()
        self._start_bridge()
        self._check_resume()

        if not self.ff:
            self.log("[warn] ffmpeg not found - HD merge/audio extract may fail\n"
                     "       Mac: brew install ffmpeg | Win: choco install ffmpeg")

    # -- res ----------------------------------------------------------------
    def _r(self, n):
        r = res_path()
        for p in [r/"assets"/n, r/n, Path(__file__).parent/"assets"/n]:
            if p.exists(): return str(p)

    # -- UI -----------------------------------------------------------------
    def _ui(self):
        s = ttk.Style()
        try: s.theme_use("clam")
        except: pass
        s.configure("TFrame",      background=BG)
        s.configure("TLabel",      background=BG, foreground=TEXT, font=("Helvetica",10))
        s.configure("TCheckbutton",background=BG, foreground=MUTED, font=("Helvetica",10))
        s.map("TCheckbutton", background=[("active",BG)])
        s.configure("Main.TButton", background=GOLD, foreground="#000000",
                    font=("Helvetica",11,"bold"), padding=(18,9), borderwidth=0,
                    relief="flat", anchor="center")
        s.map("Main.TButton",
              background=[("active","#e8b84a"),("pressed","#c8911a"),("disabled","#3a3a2a")],
              foreground=[("active","#000000"),("pressed","#000000"),("disabled",MUTED)],
              relief=[("pressed","flat")])
        s.configure("Ghost.TButton", background=SURF2, foreground=TEXT,
                    font=("Helvetica",10), padding=(10,7), borderwidth=1,
                    relief="flat", anchor="center")
        s.map("Ghost.TButton",
              background=[("active",SURF),("disabled",BG)],
              foreground=[("active",TEXT),("disabled",MUTED)],
              relief=[("pressed","flat")])
        s.configure("TProgressbar", troughcolor=SURF2, background=GOLD,
                    borderwidth=0, thickness=4)

        # Header
        hdr = tk.Frame(self.root, bg="#2a0e00", height=68)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        hi = tk.Frame(hdr, bg="#2a0e00"); hi.pack(fill="both", expand=True, padx=20, pady=12)
        lp = self._r("header-logo.png")
        if lp:
            try:
                self._logo = tk.PhotoImage(file=lp)
                tk.Label(hi, image=self._logo, bg="#2a0e00", bd=0).pack(side="left", padx=(0,12))
            except: pass
        tx = tk.Frame(hi, bg="#2a0e00"); tx.pack(side="left")
        tk.Label(tx, text=APP_NAME, bg="#2a0e00", fg="#ff8c42",
                 font=("Helvetica",16,"bold")).pack(anchor="w")
        tk.Label(tx, text=f"v{APP_VER}  -  {APP_AUTHOR}  -  Universal Download Manager",
                 bg="#2a0e00", fg="#9a5020", font=("Helvetica",9)).pack(anchor="w")
        # bridge dot
        self._dot = tk.Label(hi, text="Bridge", bg="#2a0e00", fg="#7a4a2a", font=("Helvetica",9))
        self._dot.pack(side="right")

        # Body scroll
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True)
        canvas = tk.Canvas(body, bg=BG, highlightthickness=0)
        vscroll = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vscroll.set)
        vscroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        self._main = tk.Frame(canvas, bg=BG)
        self._cwin = canvas.create_window((0,0), window=self._main, anchor="nw")
        self._main.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(self._cwin, width=e.width))
        # mousewheel
        def _scroll(e):
            canvas.yview_scroll(int(-1*(e.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _scroll)

        pad = self._main

        # URL box
        self._section(pad, "URL  -  one or more links, one per line")
        self.url_box = tk.Text(pad, height=3, font=("Menlo",11),
                               bg="#1e0d02", fg="#ffd0a0", insertbackground="#ff8c42",
                               relief="flat", highlightthickness=1,
                               highlightbackground="#3d1e08", highlightcolor="#ff8c42",
                               padx=10, pady=8, selectbackground="#8b2500")
        self.url_box.pack(fill="x", padx=20, pady=(4,10))
        # paste shortcut
        self.url_box.bind("<Command-v>", lambda e: self.root.after(100, self._on_paste))
        self.url_box.bind("<Control-v>", lambda e: self.root.after(100, self._on_paste))

        # Options row
        opt = tk.Frame(pad, bg=BG); opt.pack(fill="x", padx=20, pady=(0,6))
        self._lbl(opt, "Format:").grid(row=0,column=0,sticky="w",padx=(0,6))
        self.fmt_var = tk.StringVar(value="best_mp4: Best MP4")
        fk = self.cfg.get("fmt","best_mp4")
        if fk in FMTS: self.fmt_var.set(f"{fk}: {FMTS[fk]['label']}")
        fm = tk.OptionMenu(opt, self.fmt_var, *[f"{k}: {v['label']}" for k,v in FMTS.items()])
        self._style_menu(fm); fm.configure(width=18)
        fm.grid(row=0,column=1,sticky="w",padx=(0,14))

        self._lbl(opt, "Mode:").grid(row=0,column=2,sticky="w",padx=(0,6))
        self.mode_var = tk.StringVar(value="auto: Auto-detect")
        mm = tk.OptionMenu(opt, self.mode_var,
                           "auto: Auto-detect","video: Video/Audio","file: General File")
        self._style_menu(mm); mm.configure(width=14)
        mm.grid(row=0,column=3,sticky="w",padx=(0,14))

        self._lbl(opt, "Cookies:").grid(row=0,column=4,sticky="w",padx=(0,6))
        self.ck_var = tk.StringVar(value=self.cfg.get("cookies","none"))
        cm = tk.OptionMenu(opt, self.ck_var,"none","chrome","safari","firefox","edge","brave")
        self._style_menu(cm); cm.configure(width=9)
        cm.grid(row=0,column=5,sticky="w")

        # Checkboxes
        chk = tk.Frame(pad, bg=BG); chk.pack(fill="x", padx=20, pady=(0,8))
        self.sub_var   = tk.BooleanVar()
        self.thumb_var = tk.BooleanVar()
        self.pl_var    = tk.BooleanVar()
        for v,l in [(self.sub_var,"Subtitles"),(self.thumb_var,"Thumbnail"),
                    (self.pl_var,"Full Playlist"),(self._clip_on,"Watch clipboard")]:
            ttk.Checkbutton(chk, text=l, variable=v).pack(side="left", padx=(0,16))

        # Folder
        fld = tk.Frame(pad, bg=BG); fld.pack(fill="x", padx=20, pady=(0,10))
        self._lbl(fld, "Save to:").pack(side="left", padx=(0,6))
        self.folder_var = tk.StringVar(value=self.cfg.get("dir",DEFAULT_DIR))
        self._entry(fld, self.folder_var).pack(side="left", fill="x", expand=True, padx=(0,6))
        self._ghost_btn(fld, "Browse", self._pick_folder).pack(side="left", padx=(0,4))
        self._ghost_btn(fld, "Open",   self._open_folder).pack(side="left")

        # Action buttons
        btns = tk.Frame(pad, bg=BG); btns.pack(fill="x", padx=20, pady=(0,10))
        self.btn_dl     = ttk.Button(btns, text="Download",  style="Main.TButton", command=self._start)
        self.btn_pause  = ttk.Button(btns, text="Pause",    style="Ghost.TButton", command=self._do_pause,  state="disabled")
        self.btn_cancel = ttk.Button(btns, text="Cancel",   style="Ghost.TButton", command=self._do_cancel, state="disabled")
        self.btn_dl.pack(side="left", padx=(0,8))
        self.btn_pause.pack(side="left", padx=(0,6))
        self.btn_cancel.pack(side="left")
        # right side buttons
        self._ghost_btn(btns, "Clear Log",   self._clear_log).pack(side="right")
        self._ghost_btn(btns, "Clear Queue", self._clear_queue).pack(side="right", padx=(0,6))

        # Scheduler row
        sched_row = tk.Frame(pad, bg=BG); sched_row.pack(fill="x", padx=20, pady=(0,8))
        self._lbl(sched_row, "Schedule:").pack(side="left", padx=(0,8))
        self._sched_var = tk.StringVar(value="Now")
        sched_menu = tk.OptionMenu(sched_row, self._sched_var,
                                   "Now","In 30 minutes","In 1 hour","In 2 hours",
                                   "In 6 hours","In 12 hours","Tonight 11 PM",
                                   "Tomorrow 6 AM","Tomorrow 9 AM")
        self._style_menu(sched_menu); sched_menu.configure(width=16)
        sched_menu.pack(side="left")
        self._sched_lbl = tk.Label(sched_row, text="", bg=BG, fg="#ff8c42",
                                   font=("Helvetica",10,"bold"))
        self._sched_lbl.pack(side="left", padx=(12,0))
        ttk.Button(sched_row, text="Clear schedule", style="Ghost.TButton",
                   command=self._clear_sched).pack(side="right")

        # Resume banner
        self.res_frame = tk.Frame(pad, bg="#152a15")
        self.res_lbl   = tk.Label(self.res_frame, text="", bg="#152a15", fg=GREEN,
                                  font=("Helvetica",11,"bold"), padx=14, pady=8)
        self.res_lbl.pack(side="left")
        rb = tk.Frame(self.res_frame, bg="#152a15"); rb.pack(side="right", padx=8)
        ttk.Button(rb, text="Resume", style="Main.TButton", command=self._do_resume).pack(side="left", padx=(0,6))
        ttk.Button(rb, text="Discard",  style="Ghost.TButton", command=self._discard).pack(side="left")

        # Speed + progress
        sp = tk.Frame(pad, bg=BG); sp.pack(fill="x", padx=20, pady=(0,4))
        self.prog_bar = ttk.Progressbar(sp, mode="determinate", maximum=100)
        self.prog_bar.pack(fill="x", pady=(0,4))
        info = tk.Frame(sp, bg=BG); info.pack(fill="x")
        self.status_var = tk.StringVar(value="Idle - paste URLs and press Download")
        tk.Label(info, textvariable=self.status_var, bg=BG, fg=MUTED,
                 font=("Helvetica",9)).pack(side="left")
        self.spd_var = tk.StringVar(value="")
        tk.Label(info, textvariable=self.spd_var, bg=BG, fg=GOLD,
                 font=("Helvetica",9,"bold")).pack(side="right")

        # Speed graph (mini canvas)
        self.graph = tk.Canvas(pad, bg="#1e0d02", height=40, highlightthickness=1,
                               highlightbackground="#3d1e08")
        self.graph.pack(fill="x", padx=20, pady=(0,8))
        self.graph.create_text(6, 20, text="Speed graph", fill=MUTED,
                               font=("Helvetica",8), anchor="w", tags="placeholder")

        # Queue section
        self._section(pad, "DOWNLOAD QUEUE")
        self.q_frame = tk.Frame(pad, bg=BG)
        self.q_frame.pack(fill="x", padx=20, pady=(4,0))
        self._empty_lbl = tk.Label(self.q_frame, text="No downloads yet. Paste URLs above and press Download.",
                                   bg=BG, fg=MUTED, font=("Helvetica",10))
        self._empty_lbl.pack(pady=16)

        # Log
        self._section(pad, "LOG")
        lf = tk.Frame(pad, bg=BG); lf.pack(fill="x", padx=20, pady=(4,20))
        self.log_txt = tk.Text(lf, height=7, font=("Menlo",10),
                               bg="#0d0500", fg="#5a3010", relief="flat",
                               padx=10, pady=8, wrap="word", state="disabled")
        self.log_txt.pack(side="left", fill="both", expand=True)
        ttk.Scrollbar(lf, command=self.log_txt.yview).pack(side="right", fill="y")
        for tag,col in [("ok","#6fcf97"),("warn","#f2c94c"),("err","#eb5757"),
                           ("info","#ffaa70"),("dim","#5a3010")]:
            self.log_txt.tag_configure(tag, foreground=col)

    # -- UI helpers ---------------------------------------------------------
    def _section(self, p, t):
        f = tk.Frame(p, bg=BG); f.pack(fill="x", padx=20, pady=(10,0))
        tk.Label(f, text=t, bg=BG, fg=MUTED, font=("Helvetica",9)).pack(side="left")
        tk.Frame(f, bg=BORDER, height=1).pack(side="left", fill="x", expand=True, padx=(8,0))

    def _lbl(self, p, t):
        return tk.Label(p, text=t, bg=BG, fg=MUTED, font=("Helvetica",10))

    def _entry(self, p, var):
        return tk.Entry(p, textvariable=var, bg=SURF, fg=TEXT,
                        insertbackground=GOLD, relief="flat",
                        highlightthickness=1, highlightbackground=BORDER,
                        highlightcolor=GOLD, font=("Helvetica",10))

    def _ghost_btn(self, p, t, cmd):
        return ttk.Button(p, text=t, style="Ghost.TButton", command=cmd)

    def _style_menu(self, m):
        m.configure(bg=SURF2, fg=TEXT, activebackground=MAROON, activeforeground=GOLD,
                    highlightthickness=0, font=("Helvetica",10), relief="flat",
                    bd=0, anchor="w")
        m["menu"].configure(bg=SURF2, fg=TEXT, activebackground=MAROON,
                            activeforeground=GOLD, font=("Helvetica",10))

    # -- folder -------------------------------------------------------------
    def _pick_folder(self):
        d = filedialog.askdirectory(initialdir=self.folder_var.get())
        if d: self.folder_var.set(d)

    def _open_folder(self):
        p = self.folder_var.get(); Path(p).mkdir(parents=True, exist_ok=True)
        if   platform.system()=="Darwin":  subprocess.run(["open",p])
        elif platform.system()=="Windows": os.startfile(p)
        else:                              subprocess.run(["xdg-open",p])

    # -- log ----------------------------------------------------------------
    def log(self, msg, tag=None):
        if tag is None:
            ml = msg.lower()
            if any(k in ml for k in ("?","[done]","saved","merged","complete","finished")): tag="ok"
            elif any(k in ml for k in ("[warn]","warning")): tag="warn"
            elif any(k in ml for k in ("[error]","failed","error","?")): tag="err"
            elif any(k in ml for k in ("[bridge]","[file]","[info]","[resume]","[pause]","[cancel]")): tag="info"
            else: tag="dim"
        self._mq.put(("log",(msg,tag)))

    def _clear_log(self):
        # BUG FIX: properly clear log
        self.log_txt.configure(state="normal")
        self.log_txt.delete("1.0","end")
        self.log_txt.configure(state="disabled")

    def _clear_queue(self):
        if self._is_running():
            messagebox.showwarning(APP_NAME,"Stop current download first."); return
        for w in self.q_frame.winfo_children(): w.destroy()
        self._empty_lbl = tk.Label(self.q_frame,
            text="No downloads yet. Paste URLs above and press Download.",
            bg=BG, fg=MUTED, font=("Helvetica",10))
        self._empty_lbl.pack(pady=16)
        self._items = []
        self.url_box.delete("1.0","end")

    # -- queue rows ---------------------------------------------------------
    def _build_rows(self, items):
        for w in self.q_frame.winfo_children(): w.destroy()
        if not items:
            self._empty_lbl = tk.Label(self.q_frame,
                text="No downloads yet.", bg=BG, fg=MUTED, font=("Helvetica",10))
            self._empty_lbl.pack(pady=16); return
        for item in items:
            row = tk.Frame(self.q_frame, bg="#1e0d02", highlightthickness=1,
                           highlightbackground="#3d1e08")
            row.pack(fill="x", pady=2, ipady=6, ipadx=8)
            item.row = row
            fg,bg2 = BADGE_COLORS.get(item.badge,(MUTED,SURF2))
            # status icon
            item._lbl_icon = tk.Label(row, text="x", bg="#1e0d02", fg=MUTED,
                                      font=("Helvetica",14,"bold"), width=2)
            item._lbl_icon.grid(row=0,column=0,rowspan=2,padx=(4,8))
            # badge
            tk.Label(row, text=item.badge, bg=bg2, fg=fg,
                     font=("Helvetica",9,"bold"), padx=6, pady=2).grid(
                     row=0,column=1,sticky="w",padx=(0,8))
            # name
            short = item.name if len(item.name)<=60 else item.name[:57]+"..."
            item._lbl_name = tk.Label(row, text=f"[{item.idx}/{item.total}] {short}",
                                      bg="#1e0d02", fg="#ffd0a0", font=("Helvetica",10),
                                      anchor="w", justify="left")
            item._lbl_name.grid(row=0,column=2,sticky="ew",padx=(0,8))
            # meta
            item._lbl_meta = tk.Label(row, text="Waiting...", bg="#1e0d02", fg=MUTED,
                                      font=("Helvetica",9))
            item._lbl_meta.grid(row=1,column=1,columnspan=2,sticky="w")
            # progress bar
            item._prog = ttk.Progressbar(row, mode="determinate", maximum=100, length=180)
            item._prog.grid(row=1,column=3,sticky="ew",padx=(0,8))
            item._prog["value"] = item.pct
            row.columnconfigure(2,weight=1)

    def _update_row(self, item):
        if not item.row: return
        icon,col = {
            "waiting":     ("?",MUTED),
            "downloading": ("?",GOLD),
            "done":        ("?",GREEN),
            "error":       ("?",RED),
            "paused":      ("?",YELLOW),
            "cancelled":   ("-",MUTED),
        }.get(item.status,("?",MUTED))
        item._lbl_icon.configure(text=icon,fg=col)
        item._prog["value"] = item.pct
        parts = []
        if item.size_v:  parts.append(sz(item.size_v))
        if item.speed_v: parts.append(spd(item.speed_v))
        if item.eta_v is not None: parts.append(f"ETA {eta(item.eta_v)}")
        if item.status=="done" and item.done_f:
            parts = [f"? {Path(item.done_f).name}"]
        item._lbl_meta.configure(text="  -  ".join(parts) if parts else item.status.capitalize())

    # -- speed graph --------------------------------------------------------
    def _draw_graph(self):
        g = self.graph; g.delete("graph")
        g.delete("placeholder")
        w,h = g.winfo_width(), g.winfo_height()
        if not self._spd_history or w<10: return
        vals = [v for _,v in self._spd_history[-60:]]
        mx   = max(vals) or 1
        pts  = []
        for i,v in enumerate(vals):
            x = int(i/(len(vals)-1)*w) if len(vals)>1 else w//2
            y = int(h - (v/mx)*(h-4) - 2)
            pts.extend([x,y])
        if len(pts)>=4:
            g.create_line(pts, fill="#ff8c42", width=1.5, smooth=True, tags="graph")
        g.create_text(6,6, text=f"Peak: {spd(mx)}", fill=MUTED,
                      font=("Helvetica",8), anchor="nw", tags="graph")

    # -- bridge -------------------------------------------------------------
    def _start_bridge(self):
        Bridge.app = self
        try:
            srv = ThreadingHTTPServer(("127.0.0.1",BRIDGE_PORT), Bridge)
        except OSError as e:
            self.log(f"[warn] bridge unavailable ({e})"); return
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.log(f"[bridge] http://127.0.0.1:{BRIDGE_PORT}")
        self._mq.put(("bridge_ok",None))

    # -- clipboard ----------------------------------------------------------
    CLIP_HOSTS = VH+("drive.google.com","dropbox.com","mega.nz","mediafire.com","wetransfer.com")

    def _looks_dl(self, s):
        if not s or not URL_RE.match(s.strip()): return False
        u = s.lower()
        return any(h in u for h in self.CLIP_HOSTS) or any(u.endswith(e) for e in VE+FE)

    def _poll_clip(self):
        if self._clip_on.get():
            try: clip = self.root.clipboard_get().strip()
            except: clip = ""
            if clip and clip!=self._clip_last and self._looks_dl(clip):
                self._clip_last = clip
                cur = self.url_box.get("1.0","end").strip()
                if clip not in cur:
                    self.url_box.delete("1.0","end")
                    self.url_box.insert("1.0",(cur+"\n"+clip).strip() if cur else clip)
                    self._mq.put(("status",f"? {clip[:70]}"))
                    try: self.root.bell()
                    except: pass
            elif clip: self._clip_last = clip
        self.root.after(1200, self._poll_clip)

    def _on_paste(self):
        """Auto-start if URL looks downloadable and nothing running."""
        try: clip = self.root.clipboard_get().strip()
        except: return
        if self._looks_dl(clip) and not self._is_running():
            pass  # user can press Download

    # -- queue poll ---------------------------------------------------------
    def _poll(self):
        try:
            while True:
                kind,payload = self._mq.get_nowait()
                if kind=="log":
                    msg,tag = payload
                    # BUG FIX: always enable before writing, disable after
                    self.log_txt.configure(state="normal")
                    self.log_txt.insert("end", msg+("\n" if not msg.endswith("\n") else ""), tag)
                    self.log_txt.see("end")
                    self.log_txt.configure(state="disabled")
                elif kind=="status":
                    self.status_var.set(payload)
                elif kind=="prog":
                    self.prog_bar["value"] = payload
                elif kind=="spd":
                    bps = payload
                    self.spd_var.set(spd(bps) if bps else "")
                    self._spd_history.append((time.time(),bps))
                    if len(self._spd_history)>120: self._spd_history=self._spd_history[-120:]
                    self._draw_graph()
                elif kind=="item_up":
                    self._update_row(payload)
                elif kind=="done":
                    self._on_done()
                elif kind=="bridge_ok":
                    self._dot.configure(fg=GREEN, text="Bridge")
                elif kind=="ext_url":
                    self._recv_ext(payload)
        except Q.Empty: pass
        self.root.after(80, self._poll)

    def _recv_ext(self, payload):
        url, referer = payload if isinstance(payload, tuple) else (payload, "")
        if not hasattr(self, "_referers"): self._referers = {}
        if referer: self._referers[url] = referer

        try: self.root.deiconify(); self.root.lift()
        except: pass

        self.log(f"[bridge] {url[:80]}")

        if self._is_running():
            # Running - append to queue
            cur = self.url_box.get("1.0","end").strip()
            if url not in cur:
                self.url_box.delete("1.0","end")
                self.url_box.insert("1.0",(cur+"\n"+url).strip() if cur else url)
                self.log("[bridge] Added to queue")
        else:
            # Not running - replace URL box and start immediately
            self.url_box.delete("1.0","end")
            self.url_box.insert("1.0", url)
            self.root.update_idletasks()  # Force UI refresh before start
            try: self.root.bell()
            except: pass
            self._start()

    # -- resume -------------------------------------------------------------
    def _check_resume(self):
        q = self.state.get("queue",[])
        if q:
            self.res_lbl.configure(
                text=f"?  {len(q)} download{'s' if len(q)>1 else ''} paused from last session")
            self.res_frame.pack(fill="x", padx=20, pady=(0,8))

    def _do_resume(self):
        q = self.state.get("queue",[])
        if not q: return
        urls = [i["url"] for i in q]
        self.folder_var.set(q[0].get("dir",DEFAULT_DIR))
        fk = q[0].get("fmt","best_mp4")
        if fk in FMTS: self.fmt_var.set(f"{fk}: {FMTS[fk]['label']}")
        self.url_box.delete("1.0","end")
        self.url_box.insert("1.0","\n".join(urls))
        self.log(f"[resume] {len(urls)} URL(s)")
        self.res_frame.pack_forget()
        self._start()

    def _discard(self):
        self.state["queue"]=[]; jsave(STATE_PATH,self.state)
        self.res_frame.pack_forget()
        self.log("[resume] queue discarded")

    # -- start --------------------------------------------------------------
    def _is_running(self):
        return self._thread and self._thread.is_alive()

    # -- Scheduler ----------------------------------------------------------
    def _clear_sched(self):
        if self._sched_timer:
            self.root.after_cancel(self._sched_timer)
            self._sched_timer = None
        self._sched_time = None
        self._sched_var.set("Now")
        self._sched_lbl.configure(text="")
        self.btn_dl.configure(state="normal", text="Download")
        self.log("[schedule] cleared")

    def _get_sched_delay(self):
        """Return delay in seconds based on selected option. None = now."""
        import datetime
        v = self._sched_var.get()
        now = datetime.datetime.now()
        if v == "Now": return None
        elif v == "In 30 minutes": return 30*60
        elif v == "In 1 hour":    return 60*60
        elif v == "In 2 hours":   return 2*60*60
        elif v == "In 6 hours":   return 6*60*60
        elif v == "In 12 hours":  return 12*60*60
        elif v == "Tonight 11 PM":
            t = now.replace(hour=23, minute=0, second=0, microsecond=0)
            if t <= now: t += datetime.timedelta(days=1)
            return (t - now).total_seconds()
        elif v == "Tomorrow 6 AM":
            t = (now + datetime.timedelta(days=1)).replace(hour=6, minute=0, second=0, microsecond=0)
            return (t - now).total_seconds()
        elif v == "Tomorrow 9 AM":
            t = (now + datetime.timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
            return (t - now).total_seconds()
        return None

    def _fmt_countdown(self, secs):
        h,r = divmod(int(secs),3600); m,s = divmod(r,60)
        if h: return f"{h}h {m}m {s}s"
        if m: return f"{m}m {s}s"
        return f"{s}s"

    def _countdown_tick(self, target_time, urls, out, fk):
        import datetime
        remaining = (target_time - datetime.datetime.now()).total_seconds()
        if remaining <= 0:
            self._sched_lbl.configure(text="Starting now...")
            self._sched_timer = None
            self._sched_time  = None
            self.btn_dl.configure(state="disabled", text="Scheduled...")
            self._do_start(urls, out, fk)
        else:
            self._sched_lbl.configure(text=f"? Starting in {self._fmt_countdown(remaining)}")
            self._sched_timer = self.root.after(1000,
                lambda: self._countdown_tick(target_time, urls, out, fk))

    def _start(self):
        import datetime
        raw  = self.url_box.get("1.0","end")
        urls = [u.strip() for u in raw.splitlines()
                if u.strip()
                and URL_RE.match(u.strip())
                and not u.strip().startswith("blob:")
                and not u.strip().startswith("data:")]
        if not urls:
            # Try clipboard as fallback
            try:
                clip = self.root.clipboard_get().strip()
                if clip and URL_RE.match(clip):
                    urls = [clip]
                    self.url_box.delete("1.0","end")
                    self.url_box.insert("1.0", clip)
                else:
                    messagebox.showwarning(APP_NAME,"Paste at least one valid URL."); return
            except:
                messagebox.showwarning(APP_NAME,"Paste at least one valid URL."); return

        out = self.folder_var.get().strip() or DEFAULT_DIR
        Path(out).mkdir(parents=True, exist_ok=True)
        fk = self.fmt_var.get().split(":")[0].strip()
        if fk not in FMTS: fk="best_mp4"

        self.cfg.update({"dir":out,"fmt":fk,"cookies":self.ck_var.get(),
                         "clip":self._clip_on.get()})
        jsave(CFG_PATH,self.cfg)

        delay = self._get_sched_delay()
        if delay and delay > 0:
            # Cancel any existing schedule
            if self._sched_timer:
                self.root.after_cancel(self._sched_timer)
            target = datetime.datetime.now() + datetime.timedelta(seconds=delay)
            self.btn_dl.configure(state="disabled", text="Scheduled...")
            self.btn_cancel.configure(state="normal")
            self.log(f"[schedule] Download scheduled for {target.strftime('%I:%M %p')}")
            # Build queue preview
            self._items = [DL(u,i+1,len(urls)) for i,u in enumerate(urls)]
            self._build_rows(self._items)
            self._sched_timer = self.root.after(1000,
                lambda: self._countdown_tick(target, urls, out, fk))
            return

        self._do_start(urls, out, fk)

    def _do_start(self, urls, out, fk):
        self._stop.clear()
        self._paused   = False
        self._done_files  = []
        self._spd_history = []
        self._referers    = getattr(self, "_referers", {})
        self._items = [DL(u,i+1,len(urls)) for i,u in enumerate(urls)]
        self._build_rows(self._items)
        self.btn_dl.configure(state="disabled", text="Scheduled...")
        self.btn_cancel.configure(state="normal")
        self.btn_pause.configure(state="normal")
        self.res_frame.pack_forget()
        self.prog_bar["value"]=0
        self._thread = threading.Thread(
            target=self._run, args=(urls,out,fk), daemon=True)
        self._thread.start()

    def _do_pause(self):
        self._paused=True; self._stop.set()
        self.btn_pause.configure(state="disabled")
        self.log("[pause] pausing...")

    def _do_cancel(self):
        self._paused=False; self._stop.set()
        # Also cancel scheduled download
        if self._sched_timer:
            self.root.after_cancel(self._sched_timer)
            self._sched_timer = None
            self._sched_lbl.configure(text="")
            self.btn_dl.configure(state="normal", text="Download")
            self.log("[schedule] cancelled")
        self.log("[cancel] cancelling...")

    # -- ydl opts -----------------------------------------------------------
    def _ydl_opts(self, out, fk, item, url=""):
        f = FMTS[fk]
        # HLS/stream URLs: use simple format (codec filters break HLS)
        url_l = url.lower() if url else ""
        is_youtube = any(h in url_l for h in ("youtube.com","youtu.be"))
        is_hls     = bool(url and not is_youtube and (
            ".m3u8" in url_l or "hls" in url_l or
            "artlist.io" in url_l or "artgrid.io" in url_l or
            "akamaized.net" in url_l or "cloudfront.net" in url_l or
            "cms-public" in url_l or "footage-hls" in url_l
        ))
        if is_hls:
            # HLS streams typically muxed - bestvideo+bestaudio fails.
            # Keep height cap from selected format if present.
            m = _HEIGHT_RE.search(f["fmt"])
            chosen = f"best[height<={m.group(1)}]/best" if m else "best"
        elif is_youtube:
            chosen = f["fmt"]
        elif not self.ff and "fb" in f:
            chosen = f.get("fb", f["fmt"])
        else:
            chosen = f["fmt"]

        def hook(d):
            if self._stop.is_set():
                raise yt_dlp.utils.DownloadError("user_stop")
            s = d.get("status")
            if s=="downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                done  = d.get("downloaded_bytes") or 0
                bps   = d.get("speed") or 0
                e_    = d.get("eta")
                item.pct     = (done/total*100) if total else 0
                item.speed_v = bps
                item.eta_v   = e_
                item.size_v  = total
                item.status  = "downloading"
                self._mq.put(("item_up",item))
                self._mq.put(("prog",item.pct))
                self._mq.put(("spd",bps))
                self._mq.put(("status",
                    f"[{item.idx}/{item.total}] {d.get('_percent_str','').strip()} "
                    f"- {spd(bps)} - ETA {eta(e_)}"))
            elif s=="finished":
                item.pct=100; self._mq.put(("item_up",item))
                self._mq.put(("status",f"[{item.idx}/{item.total}] Processing..."))
                # Get filename from multiple sources
                fn = (d.get("filename") or
                      (d.get("info_dict") or {}).get("filepath") or
                      (d.get("info_dict") or {}).get("_filename") or "")
                if fn:
                    # Always track latest filename; postprocessor_hook will update again
                    item.done_f = fn
                    item.name = Path(fn).name[:80]
                    self._mq.put(("item_up", item))

        def pp_hook(d):
            # Fires after postprocessor (merger, video convertor) — file ext/path may change
            if d.get("status") != "finished": return
            info = d.get("info_dict") or {}
            fn = info.get("filepath") or d.get("filename") or ""
            if fn and Path(fn).exists():
                item.done_f = fn
                item.name = Path(fn).name[:80]
                if fn not in self._done_files:
                    self._done_files.append(fn)
                self._mq.put(("item_up", item))

        opts = {
            "format":                     chosen,
            "outtmpl": {
                "default": str(Path(out)/"%(title).80s.%(ext)s"),
                "chapter": str(Path(out)/"%(title).60s - %(section_title)s.%(ext)s"),
            },
            "restrictfilenames":          False,
            "windowsfilenames":           False,
            "trim_file_name":             80,
            "noplaylist":                 not self.pl_var.get(),
            "writesubtitles":             self.sub_var.get(),
            "writeautomaticsub":          self.sub_var.get(),
            "subtitleslangs":             ["en","bn"] if self.sub_var.get() else [],
            "writethumbnail":             self.thumb_var.get(),
            "ignoreerrors":               True,
            "progress_hooks":             [hook],
            "postprocessor_hooks":        [pp_hook],
            "logger":                     _Log(self),
            "no_warnings":                False,
            # YouTube nerfed android/web clients (no HD without PoToken).
            # tv_embedded + mweb + web_safari currently serve HD without auth.
            "extractor_args":             {
                "youtube": {
                    "player_client": ["tv_embedded", "mweb", "web_safari", "ios", "android"],
                    "max_comments": ["0"],
                },
            },
            "youtube_include_dash_manifest": True,
            # Prefer highest resolution first, then h264, then aac
            "format_sort":                ["res", "fps", "vcodec:h264", "acodec:aac", "size", "br"],
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "*/*",
                "Referer": getattr(self,"_referers",{}).get(url, url) or url,
                "Origin":  "/".join(url.split("/")[:3]) if url and url.startswith("http") else "",
            },
            "geo_bypass":                 True,
            "age_limit":                  99,
            "hls_prefer_native":          False,
            "hls_use_mpegts":             True,
            "retries":                    15,
            "fragment_retries":           15,
            "concurrent_fragment_downloads": 4,
            "continuedl":                 True,
            "noprogress":                 False,
        }
        if self.ff: opts["ffmpeg_location"]=self.ff
        ck = self.ck_var.get()
        # Cookies needed for age-gated, member-only, and full 1080p+ YouTube formats
        if ck and ck != "none":
            opts["cookiesfrombrowser"] = (ck,)
        if "merge" in f and not is_hls: opts["merge_output_format"]=f["merge"]
        if is_hls:
            opts["merge_output_format"] = "mp4"
            opts["final_ext"] = "mp4"
            if self.ff:
                opts["postprocessors"] = [{"key":"FFmpegVideoConvertor","preferedformat":"mp4"}]
                _hls_args = [
                    "-c:v","libx264","-profile:v","high","-level","4.1",
                    "-preset","fast","-crf","16","-pix_fmt","yuv420p",
                    "-c:a","aac","-b:a","320k","-ar","48000","-ac","2",
                    "-movflags","+faststart","-tag:v","avc1",
                ]
                opts["postprocessor_args"] = {
                    "videoconvertor": _hls_args,
                    "ffmpeg_o1": _hls_args,
                    "ffmpeg": _hls_args,
                }
        if "audio" in f:
            opts["postprocessors"]=[{"key":"FFmpegExtractAudio",
                                     "preferredcodec":f["audio"],"preferredquality":"0"}]
        # Premiere Pro: ensure final file = H.264 (avc1) + AAC in MP4.
        # 1) format_sort prefers native avc1 (skips transcode on YouTube when possible)
        # 2) recodevideo=mp4 forces re-encode of any VP9/AV1 to H.264
        # 3) postprocessor_args injects codec params into ffmpeg call
        if f.get("pp_compat") and self.ff:
            opts["merge_output_format"] = "mp4"
            opts["final_ext"] = "mp4"
            # res first so 4K VP9 picked over 1080p H264, then prefer h264 within same res
            opts["format_sort"] = ["res", "fps", "vcodec:h264", "acodec:aac", "ext:mp4:m4a", "br"]
            # recode_video forces re-encode (overrides copy mode)
            opts["postprocessors"] = [
                {"key":"FFmpegVideoConvertor","preferedformat":"mp4"},
            ]
            _pp_args = [
                "-c:v","libx264","-profile:v","high","-level","4.1",
                "-preset","medium","-crf","18","-pix_fmt","yuv420p",
                "-c:a","aac","-b:a","320k","-ar","48000","-ac","2",
                "-movflags","+faststart","-tag:v","avc1",
            ]
            # Multiple keys: covers different yt-dlp versions and PP stages
            opts["postprocessor_args"] = {
                "videoconvertor": _pp_args,
                "ffmpeg_o1": _pp_args,
                "ffmpeg": _pp_args,
            }
        return opts

    # -- main loop ----------------------------------------------------------
    def _run(self, urls, out, fk):
        total = len(urls)
        self.state["queue"]=[{"url":u,"dir":out,"fmt":fk} for u in urls]
        jsave(STATE_PATH,self.state)

        for i,url in enumerate(urls):
            item = self._items[i]

            # BUG FIX: check stop BEFORE item, mark remaining as cancelled
            if self._stop.is_set():
                item.status = "paused" if self._paused else "cancelled"
                self._mq.put(("item_up",item))
                continue

            item.status="downloading"
            self._mq.put(("item_up",item))
            self.log(f"\n[{i+1}/{total}] {url[:100]}")

            # Warn about quality-locked sites without cookies
            ul = url.lower()
            if self.ck_var.get() == "none" and any(h in ul for h in ("artgrid","artlist","patreon","cms-public.artgrid")):
                self.log("[warn] Artgrid/Artlist/Patreon requires browser login for full quality.")
                self.log("[warn] Set Cookies dropdown to your browser (chrome/safari/etc) and re-login on the site.")
            if any(h in ul for h in ("youtube.com","youtu.be")) and self.ck_var.get() == "none":
                self.log("[info] YouTube: cookies recommended for 1080p+ and member content.")

            mode = self.mode_var.get().split(":")[0].strip()
            kind = classify(url) if mode=="auto" else mode

            try:
                if kind=="file": self._run_file(url,out,item)
                else:            self._run_video(url,out,fk,item)
            except Exception as e:
                self.log(f"[error] {e}")
                item.status="error"
                self._mq.put(("item_up",item))

            # Mark done if not explicitly stopped
            if not self._stop.is_set() and item.status not in ("error","paused","cancelled"):
                item.status="done"; item.pct=100
                self._mq.put(("item_up",item))

            # -- KEY FIX: if item errored but user did NOT cancel/pause,
            #    clear _stop so next URL starts fresh ----------------------
            if item.status == "error" and not self._paused:
                self._stop.clear()

            # Remove from resume queue
            self.state["queue"]=[q for q in self.state["queue"] if q.get("url")!=url]
            jsave(STATE_PATH,self.state)

            # Speed graph reset between items
            self._mq.put(("spd",0))
            # Small pause between items so UI updates
            import time; time.sleep(0.3)

        # Save paused queue
        if self._paused:
            rem = [{"url":self._items[j].url,"dir":out,"fmt":fk}
                   for j in range(len(urls))
                   if self._items[j].status in ("waiting","paused")]
            self.state["queue"]=rem
        else:
            self.state["queue"]=[]
        jsave(STATE_PATH,self.state)
        self._mq.put(("done",None))

    def _run_video(self, url, out, fk, item):
        opts = self._ydl_opts(out,fk,item,url)
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            # Rename UUID-based filenames to something readable
            # Always try to rename generic/UUID filenames
            if item.done_f:
                self._rename_if_uuid(item, url)
            if not self._stop.is_set():
                item.status="done"; item.pct=100
                self._mq.put(("item_up",item))
        except yt_dlp.utils.DownloadError as e:
            if "user_stop" in str(e):
                item.status="paused" if self._paused else "cancelled"
            else:
                self.log(f"[error] {e}")
                item.status="error"
                # Don't propagate - let loop continue to next URL
            self._mq.put(("item_up",item))
        except Exception as e:
            self.log(f"[error] unexpected: {e}")
            item.status="error"
            self._mq.put(("item_up",item))

    def _extract_slug_from_url(self, url, uuid_pat, generic_skip):
        """Extract human slugs from URL path. Used for both source URL and referer."""
        import re as _re2, urllib.parse as _up
        parsed   = _up.urlparse(url)
        path_dec = _up.unquote(parsed.path)
        slugs = []
        for x in path_dec.split("/"):
            if not x or len(x) <= 3: continue
            if uuid_pat.match(x): continue
            if x.isdigit(): continue   # skip numeric IDs like /clip/717762/
            if x.lower() in generic_skip: continue
            if x.endswith(".m3u8") or x.endswith(".mpd") or x.endswith(".ts"):
                stem = x.rsplit(".",1)[0]
                stem = _re2.sub(r"_[0-9]+p.*$","",stem)
                stem = _re2.sub(r"_[0-9]+$","",stem)
                if len(stem) > 3 and not uuid_pat.match(stem):
                    slugs.append(stem)
                continue
            if "footage-hls" in x or "footage-dash" in x: continue
            slugs.append(x)
        return slugs

    def _rename_if_uuid(self, item, url):
        """Rename UUID/generic filenames to readable names from URL or referer."""
        import re as _re, urllib.parse as _up
        if not item.done_f: return
        p = Path(item.done_f)
        # File may have been remuxed/converted to .mp4 — try sibling with same stem
        if not p.exists():
            parent = p.parent
            stem   = p.stem
            cand   = None
            for ext in (".mp4",".mkv",".webm",".m4a",".mp3"):
                q = parent / f"{stem}{ext}"
                if q.exists(): cand = q; break
            # Fallback: glob for any file starting with stem
            if cand is None and parent.exists():
                matches = sorted(parent.glob(f"{stem}.*"))
                if matches: cand = matches[0]
            if cand is None: return
            p = cand
            item.done_f = str(p)
        name = p.stem
        uuid_pat = _re.compile("^[0-9a-f]{8}-[0-9a-f]{4}-", _re.I)
        import re as _re2
        generic = {"footage","video","clip","download","file","media",
                   "stream","playlist","index","master","unknown",
                   "hls","dash","manifest","output","temp"}
        looks_random = bool(_re2.search(r"-[a-z0-9]{2,8}$", name.lower())) and len(name) < 30
        is_generic   = (name.lower() in generic or
                        name.lower().startswith("footage") or
                        name.lower().startswith("clip-") or
                        name.lower().startswith("video-") or
                        name.lower().startswith("b2483b") or
                        name.lower().startswith("f538fc") or
                        name.lower().startswith("9ba9997") or
                        "footage-hls" in name.lower() or
                        looks_random)
        if not uuid_pat.match(name) and not is_generic:
            return
        try:
            # Try referer URL first (artgrid clip page often has descriptive slug)
            # e.g. https://artgrid.io/clip/717762/son-father-hugging-kid
            referer = getattr(self, "_referers", {}).get(url, "")
            generic_skip = {"clip","footage","video","watch","embed","play",
                            "stream","files","media","content","download",
                            "artgrid","artlist","io","com","www"}
            slug_pool = []
            if referer:
                slug_pool += self._extract_slug_from_url(referer, uuid_pat, generic_skip)
            slug_pool += self._extract_slug_from_url(url, uuid_pat, generic_skip)
            # Query string title
            parsed = _up.urlparse(url)
            qs = _up.parse_qs(parsed.query)
            title_q = qs.get("title", qs.get("name", qs.get("filename", [])))
            if title_q:
                new_name = title_q[0]
            elif slug_pool:
                # Pick most descriptive (most words, longest)
                new_name = max(slug_pool, key=lambda s: (len(s.replace("-"," ").split()), len(s)))
            else:
                return
        except Exception:
            return
        new_name = _re.sub("[^a-zA-Z0-9 _-]", " ", new_name)
        new_name = _re.sub(" +", " ", new_name).strip()[:60]
        if not new_name or len(new_name) < 3: return
        new_path = p.parent / f"{new_name}{p.suffix}"
        counter  = 1
        while new_path.exists() and new_path != p:
            new_path = p.parent / f"{new_name} ({counter}){p.suffix}"
            counter += 1
        try:
            p.rename(new_path)
            item.done_f = str(new_path)
            item.name   = new_path.name
            self._mq.put(("item_up", item))
            self.log(f"[rename] {p.name} -> {new_path.name}")
        except Exception as e:
            self.log(f"[warn] rename failed: {e}")

    def _run_file(self, url, out, item):
        def prog(p,s,r):
            item.pct=p; item.speed_v=s; item.eta_v=r; item.status="downloading"
            self._mq.put(("item_up",item))
            self._mq.put(("prog",p))
            self._mq.put(("spd",s))
            self._mq.put(("status",f"[{item.idx}/{item.total}] {p:.0f}% - {spd(s)} - ETA {eta(r)}"))
        dl = FileDL(url,Path(out),n=THREADS,prog_cb=prog,log_cb=self.log,
                    cancel_fn=lambda: self._stop.is_set())
        res = dl.run()
        if res and res not in self._done_files:
            self._done_files.append(res); item.done_f=res
        if not self._stop.is_set():
            item.status="done"; item.pct=100
            self._mq.put(("item_up",item))

    # -- done ---------------------------------------------------------------
    def _on_done(self):
        self.btn_dl.configure(state="normal")
        self.btn_cancel.configure(state="disabled")
        self.btn_pause.configure(state="disabled")
        self._mq.put(("spd",0))
        done = sum(1 for it in self._items if it.status=="done")
        err  = sum(1 for it in self._items if it.status=="error")
        msg  = f"Done: {done} file(s) downloaded"
        if err:    msg+=f"  |  {err} error"
        if self._paused: msg+="  |  paused"
        self._mq.put(("status",msg))
        self.prog_bar["value"]=100 if not self._paused else self.prog_bar["value"]
        if self._paused:
            q=self.state.get("queue",[])
            if q:
                self.res_lbl.configure(text=f"Paused: {len(q)} items")
                self.res_frame.pack(fill="x",padx=20,pady=(0,8))
        n=len(self._done_files)
        if n>0:
            self._notify(f"Done: {n} file{'s' if n>1 else ''} downloaded",
                         Path(self._done_files[0]).name)
            try: self.root.bell()
            except: pass
        # Auto-clear URL box and log after successful download
        if done > 0 and err == 0 and not self._paused:
            self.root.after(1500, self._auto_clear)

    def _auto_clear(self):
        """Auto-clear URL box and log after successful download."""
        # Clear URL box
        self.url_box.delete("1.0","end")
        # Clear log
        self.log_txt.configure(state="normal")
        self.log_txt.delete("1.0","end")
        self.log_txt.configure(state="disabled")
        self.log("[ready] Paste URL and press Download")

    def _notify(self, title, body):
        try:
            if   platform.system()=="Darwin":
                subprocess.Popen(["osascript","-e",
                    f'display notification "{body}" with title "{APP_NAME}" subtitle "{title}" sound name "Glass"'])
            elif platform.system()=="Windows":
                ps=(f'[Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime]>$null;'
                    f'[xml]$x=\'<toast><visual><binding template="ToastText02"><text id="1">{title}</text><text id="2">{body}</text></binding></visual></toast>\';'
                    f'$t=New-Object Windows.Data.Xml.Dom.XmlDocument;$t.LoadXml($x.OuterXml);'
                    f'$n=[Windows.UI.Notifications.ToastNotification]::new($t);'
                    f'[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("{APP_NAME}").Show($n)')
                subprocess.Popen(["powershell","-Command",ps],
                                 creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
            else:
                subprocess.Popen(["notify-send",APP_NAME,f"{title}\n{body}"])
        except: pass


class _Log:
    def __init__(self,a): self.a=a
    def debug(self,m):
        if m.startswith("[debug]") or ("[download]" in m and "%" in m): return
        self.a.log(m)
    def info(self,m):    self.a.log(m)
    def warning(self,m): self.a.log(f"[warn] {m}")
    def error(self,m):   self.a.log(f"[error] {m}")


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()

if __name__=="__main__":
    main()
