// ZH Downloader v4 — content script
// Clean rewrite: floating button + mini window + download interception

(function() {
'use strict';

// ── Config ──────────────────────────────────────────────────────────────
const FILE_EXT = /\.(mp4|webm|mkv|mov|flv|m4v|mp3|m4a|aac|wav|flac|ogg|pdf|zip|rar|7z|exe|dmg|pkg|msi|apk|iso|gz|bz2|docx?|xlsx?|pptx?|jpg|jpeg|png|gif|webp|epub|torrent)(\?|$)/i;
const VIDEO_HOSTS = ["youtube.com","youtu.be","vimeo.com","tiktok.com","instagram.com","facebook.com","twitter.com","x.com","twitch.tv","reddit.com","dailymotion.com","soundcloud.com","bilibili.com","rumble.com","streamable.com","artgrid.io","artlist.io","pinterest.com"];
const IS_VIDEO_SITE = VIDEO_HOSTS.some(h => location.hostname.includes(h));

// ── State ────────────────────────────────────────────────────────────────
const state = {
  items:     [],
  floatBtn:  null,
  miniWin:   null,
  winOpen:   false,
  drag: { active:false, moved:false, startX:0, startY:0, origLeft:0, origTop:0 },
};

// ── CSS ──────────────────────────────────────────────────────────────────
const S = document.createElement("style");
S.textContent = `
#_zhfb{position:fixed;bottom:80px;right:20px;z-index:2147483647;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;cursor:default}
#_zhfb-wrap{display:flex;align-items:center;gap:8px;
  background:#1c0800;border:1.5px solid #ff6b35;border-radius:50px;
  padding:8px 14px 8px 10px;box-shadow:0 4px 20px rgba(255,80,20,.4);
  transition:box-shadow .15s}
#_zhfb:hover #_zhfb-wrap{box-shadow:0 6px 28px rgba(255,80,20,.6)}
#_zhfb-icon{width:24px;height:24px;border-radius:6px;flex-shrink:0;pointer-events:none}
#_zhfb-label{font-size:13px;font-weight:600;color:#ff8c42;
  white-space:nowrap;pointer-events:none;user-select:none}
#_zhmw{position:fixed;width:320px;z-index:2147483647;display:none;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  background:#160800;border:1px solid #3d1e08;border-radius:12px;
  box-shadow:0 8px 40px rgba(0,0,0,.7)}
#_zhmw.show{display:block}
#_zhmw-hdr{display:flex;align-items:center;gap:8px;padding:10px 14px;
  background:#1c0800;border-bottom:1px solid #2e1005;
  border-radius:12px 12px 0 0;cursor:move;user-select:none}
#_zhmw-hdr img{width:20px;height:20px;border-radius:5px;pointer-events:none}
#_zhmw-title{flex:1;font-size:12px;font-weight:600;color:#ff8c42;pointer-events:none}
#_zhmw-x{width:16px;height:16px;border-radius:50%;background:#eb5757;
  border:none;cursor:pointer;color:#fff;font-size:10px;
  display:flex;align-items:center;justify-content:center;flex-shrink:0}
#_zhmw-body{padding:8px 12px;max-height:260px;overflow-y:auto}
#_zhmw-body::-webkit-scrollbar{width:3px}
#_zhmw-body::-webkit-scrollbar-thumb{background:#3d1e08;border-radius:3px}
#_zhmw-foot{padding:8px 12px;border-top:1px solid #2e1005;display:flex;gap:6px}
._zhitem{background:#1e0d02;border:1px solid #2e1005;border-radius:8px;
  padding:8px 10px;margin-bottom:6px}
._zhtop{display:flex;align-items:center;gap:6px;margin-bottom:4px}
._zhbadge{font-size:9px;font-weight:700;padding:2px 5px;
  border-radius:3px;flex-shrink:0}
._zhbadge.v{background:#1a3a2a;color:#6fcf97}
._zhbadge.a{background:#1a2a3a;color:#56ccf2}
._zhbadge.h{background:#2a1a3a;color:#bb86fc}
._zhbadge.f{background:#2a2a1a;color:#f2c94c}
._zhname{font-size:11px;color:#ffddc0;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis;flex:1}
._zhsz{font-size:10px;color:rgba(255,140,66,.5);flex-shrink:0}
._zhprog{height:3px;background:#2e1005;border-radius:3px;
  margin-bottom:4px;overflow:hidden}
._zhpf{height:100%;background:linear-gradient(90deg,#ff6b35,#ffaa55);
  border-radius:3px;transition:width .3s}
._zhpf.done{background:#6fcf97;width:100%}
._zhst{font-size:10px;color:rgba(255,140,66,.4);margin-bottom:4px}
._zhacts{display:flex;gap:5px}
._zhbtn{flex:1;padding:6px 8px;border-radius:6px;border:none;
  font-size:12px;font-weight:600;cursor:pointer}
._zhbtn.p{background:#ff6b35;color:#fff}
._zhbtn.p:hover{background:#ff8c50}
._zhbtn.g{background:#2e1005;color:#ff8c42;border:1px solid #3d1e08}
._zhbtn.g:hover{background:#3d1e08}
._zhfbtn{flex:1;padding:7px;border-radius:7px;border:none;
  font-size:12px;font-weight:600;cursor:pointer}
._zhfbtn.p{background:#ff6b35;color:#fff}
._zhfbtn.g{background:#1e0d02;color:#ff8c42;border:1px solid #3d1e08}
#_zhtoast{position:fixed;z-index:2147483647;top:16px;left:50%;
  transform:translateX(-50%);padding:9px 18px;border-radius:8px;
  font-family:-apple-system,sans-serif;font-size:13px;font-weight:500;
  box-shadow:0 4px 20px rgba(0,0,0,.5);display:none;white-space:nowrap;
  pointer-events:none}
#_zhtoast.ok{background:#1a2e1a;color:#6fcf97;border:1px solid #6fcf97}
#_zhtoast.err{background:#2e1a1a;color:#eb5757;border:1px solid #eb5757}
`;
document.head.appendChild(S);

// ── Toast ────────────────────────────────────────────────────────────────
let _toastTimer;
function toast(msg, type) {
  let el = document.getElementById("_zhtoast");
  if (!el) {
    el = document.createElement("div");
    el.id = "_zhtoast";
    document.body.appendChild(el);
  }
  el.textContent = msg;
  el.className   = type === "err" ? "err" : "ok";
  el.style.display = "block";
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => { el.style.display = "none"; }, 2800);
}

// ── Helpers ──────────────────────────────────────────────────────────────
function fmtSz(b) {
  if (!b) return "";
  if (b > 1073741824) return (b/1073741824).toFixed(1)+" GB";
  if (b > 1048576)    return (b/1048576).toFixed(1)+" MB";
  if (b > 1024)       return (b/1024).toFixed(0)+" KB";
  return b+"B";
}
function badgeCls(t) {
  if (["HLS","DASH","STREAM"].includes(t)) return "h";
  if (["MP4","WEBM","VIDEO","MKV"].includes(t)) return "v";
  if (t === "AUDIO") return "a";
  return "f";
}
function shortName(url) {
  try {
    const p = decodeURIComponent(new URL(url).pathname.split("/").filter(Boolean).pop() || "");
    return p.slice(0, 45) || url.slice(0, 45);
  } catch { return url.slice(0, 45); }
}

// ── Items ────────────────────────────────────────────────────────────────
function addItem(item) {
  if (state.items.some(i => i.url === item.url)) return false;
  state.items.unshift(item);
  if (state.items.length > 40) state.items.length = 40;
  renderItems();
  updateLabel();
  return true;
}

function renderItems() {
  const body = document.getElementById("_zhmw-body");
  if (!body) return;
  if (!state.items.length) {
    body.innerHTML = '<div style="text-align:center;color:rgba(255,140,66,.35);font-size:12px;padding:20px 0">No media detected yet.<br>Play a video or visit a file page.</div>';
    return;
  }
  body.innerHTML = state.items.map((it, i) => `
    <div class="_zhitem">
      <div class="_zhtop">
        <span class="_zhbadge ${badgeCls(it.type)}">${it.type}</span>
        <span class="_zhname" title="${it.url}">${it.name || shortName(it.url)}</span>
        <span class="_zhsz">${it.size || ""}</span>
      </div>
      <div class="_zhprog"><div class="_zhpf ${it.pct >= 100 ? 'done' : ''}" style="width:${it.pct||0}%"></div></div>
      <div class="_zhst">${it.status || "Ready"}</div>
      <div class="_zhacts">
        <button class="_zhbtn p" onclick="_zhDL(${i})">Download</button>
        <button class="_zhbtn g" onclick="_zhCopy(${i})">Copy URL</button>
      </div>
    </div>`).join("");
}

function updateLabel() {
  const lbl = document.getElementById("_zhfb-label");
  if (lbl) lbl.textContent = state.items.length > 0 ? `Download (${state.items.length})` : "Download";
}

// ── Global handlers (called from innerHTML) ───────────────────────────────
window._zhDL = function(i) {
  const it = state.items[i];
  if (!it) return;
  state.items[i].status = "Sending...";
  renderItems();
  chrome.runtime.sendMessage(
    { type: "ZH_SEND_TO_APP", url: it.url, referer: it.referer || location.href },
    function(res) {
      if (res && res.ok) {
        state.items[i].status = "Sent to app!";
        renderItems();
        toast("Sent to ZH Downloader!");
      } else {
        state.items[i].status = "Ready";
        renderItems();
        toast("Open ZH Downloader app first!", "err");
      }
    }
  );
};

window._zhCopy = function(i) {
  const it = state.items[i];
  if (!it) return;
  navigator.clipboard.writeText(it.url)
    .then(() => toast("URL copied!"))
    .catch(() => {
      const el = document.createElement("textarea");
      el.value = it.url;
      document.body.appendChild(el);
      el.select();
      document.execCommand("copy");
      el.remove();
      toast("URL copied!");
    });
};

window._zhPageDL = function() {
  chrome.runtime.sendMessage(
    { type: "ZH_SEND_TO_APP", url: location.href },
    function(res) {
      toast(res && res.ok ? "Sent page to app!" : "Open ZH Downloader app first!", res && res.ok ? "ok" : "err");
    }
  );
};

// ── Mini window ───────────────────────────────────────────────────────────
function buildMiniWin() {
  if (state.miniWin) return;
  const div = document.createElement("div");
  div.id = "_zhmw";
  div.innerHTML = `
    <div id="_zhmw-hdr">
      <img src="${chrome.runtime.getURL("icons/icon48.png")}" alt="">
      <span id="_zhmw-title">ZH Downloader</span>
      <button id="_zhmw-x">x</button>
    </div>
    <div id="_zhmw-body"></div>
    <div id="_zhmw-foot">
      <button class="_zhfbtn g" onclick="document.getElementById('_zhmw').classList.remove('show');_zhState.winOpen=false">Hide</button>
      <button class="_zhfbtn p" onclick="_zhPageDL()">Download Page</button>
    </div>`;
  document.body.appendChild(div);
  state.miniWin = div;

  document.getElementById("_zhmw-x").onclick = function() {
    state.miniWin.classList.remove("show");
    state.winOpen = false;
  };

  // Drag header
  const hdr = document.getElementById("_zhmw-hdr");
  let mDown = false, mX = 0, mY = 0, mL = 0, mT = 0;
  hdr.addEventListener("mousedown", function(e) {
    if (e.target.id === "_zhmw-x") return;
    mDown = true;
    mX = e.clientX; mY = e.clientY;
    const r = div.getBoundingClientRect();
    mL = r.left; mT = r.top;
    div.style.right = "auto"; div.style.bottom = "auto";
    div.style.left = mL+"px"; div.style.top = mT+"px";
    e.preventDefault();
  });
  document.addEventListener("mousemove", function(e) {
    if (!mDown) return;
    div.style.left = (mL + e.clientX - mX) + "px";
    div.style.top  = (mT + e.clientY - mY) + "px";
  });
  document.addEventListener("mouseup", function() { mDown = false; });

  renderItems();
}

// expose state for inline onclick
window._zhState = state;

function toggleWin() {
  buildMiniWin();
  state.winOpen = !state.winOpen;
  if (state.winOpen) {
    state.miniWin.classList.add("show");
    // Position above/beside the float button
    const fb = state.floatBtn;
    if (fb) {
      const r = fb.getBoundingClientRect();
      const winW = 320, winH = 320;
      let left = r.right - winW;
      let top  = r.top - winH - 8;
      if (left < 4) left = 4;
      if (top < 4) top = r.bottom + 8;
      state.miniWin.style.right  = "auto";
      state.miniWin.style.bottom = "auto";
      state.miniWin.style.left   = left + "px";
      state.miniWin.style.top    = top  + "px";
    }
    renderItems();
  } else {
    state.miniWin.classList.remove("show");
  }
}

// ── Floating button ───────────────────────────────────────────────────────
function buildFloatBtn() {
  if (state.floatBtn) return;
  const btn = document.createElement("div");
  btn.id = "_zhfb";
  btn.innerHTML = `
    <div id="_zhfb-wrap">
      <img id="_zhfb-icon" src="${chrome.runtime.getURL("icons/icon48.png")}" alt="">
      <span id="_zhfb-label">Download</span>
    </div>`;
  document.body.appendChild(btn);
  state.floatBtn = btn;

  // ── Drag + Click (completely separate) ──────────────────────────────
  const d = state.drag;

  btn.addEventListener("mousedown", function(e) {
    if (e.button !== 0) return;
    d.active  = true;
    d.moved   = false;
    d.startX  = e.clientX;
    d.startY  = e.clientY;
    const r   = btn.getBoundingClientRect();
    d.origLeft = r.left;
    d.origTop  = r.top;
    // Switch to absolute positioning for drag
    btn.style.right  = "auto";
    btn.style.bottom = "auto";
    btn.style.left   = r.left + "px";
    btn.style.top    = r.top  + "px";
    e.preventDefault();
    e.stopPropagation();
  });

  document.addEventListener("mousemove", function(e) {
    if (!d.active) return;
    const dx = e.clientX - d.startX;
    const dy = e.clientY - d.startY;
    if (Math.abs(dx) > 4 || Math.abs(dy) > 4) d.moved = true;
    if (d.moved) {
      btn.style.left = (d.origLeft + dx) + "px";
      btn.style.top  = (d.origTop  + dy) + "px";
    }
  });

  document.addEventListener("mouseup", function(e) {
    if (!d.active) return;
    const wasMoved = d.moved;
    d.active = false;
    d.moved  = false;
    if (!wasMoved) {
      // Pure click — toggle window
      toggleWin();
    }
  });
}

// ── Show float button ─────────────────────────────────────────────────────
function showFloatBtn() {
  if (document.body) buildFloatBtn();
  else document.addEventListener("DOMContentLoaded", buildFloatBtn);
}

if (IS_VIDEO_SITE) showFloatBtn();

// YouTube: show only on /watch pages
if (location.hostname.includes("youtube.com")) {
  let lastPath = location.pathname;
  new MutationObserver(function() {
    if (location.pathname !== lastPath) {
      lastPath = location.pathname;
      if (location.pathname === "/watch" && !state.floatBtn) showFloatBtn();
    }
  }).observe(document.documentElement, { childList: true, subtree: false });
}

// ── Background → content messages ────────────────────────────────────────
chrome.runtime.onMessage.addListener(function(msg) {
  if (msg.type !== "ZH_UPDATED") return;
  let added = 0;
  (msg.items || []).forEach(function(it) {
    if (addItem({
      url:     it.url,
      type:    it.type,
      name:    it.name || shortName(it.url),
      size:    it.sizeStr || "",
      referer: it.referer || location.href,
      pct:     0,
      status:  "Ready",
    })) added++;
  });
  if (added > 0 && !state.floatBtn) showFloatBtn();
});

// ── DOM scan ──────────────────────────────────────────────────────────────
function scan() {
  const seen = new Set(state.items.map(i => i.url));
  // Videos
  document.querySelectorAll("video,audio").forEach(function(el) {
    [el.src, el.currentSrc].concat(
      Array.from(el.querySelectorAll("source")).map(s => s.src)
    ).filter(s => s && !seen.has(s)).forEach(function(s) {
      addItem({ url:s, type:"VIDEO", name:document.title.slice(0,40),
                size:"", referer:location.href, pct:0, status:"Ready" });
      seen.add(s);
    });
  });
  // File links
  document.querySelectorAll("a[href]").forEach(function(a) {
    if (a.href && FILE_EXT.test(a.href) && !seen.has(a.href)) {
      addItem({ url:a.href, type:"FILE",
                name:(a.textContent||"").trim().slice(0,40)||shortName(a.href),
                size:"", referer:location.href, pct:0, status:"Ready" });
      seen.add(a.href);
    }
  });
}

scan();
let _scanTimer;
new MutationObserver(function() {
  clearTimeout(_scanTimer);
  _scanTimer = setTimeout(scan, 1000);
}).observe(document.body || document.documentElement, { childList:true, subtree:true });

document.addEventListener("visibilitychange", function() {
  if (!document.hidden) scan();
});

// ── Click intercept ───────────────────────────────────────────────────────
document.addEventListener("click", function(e) {
  const el = e.target.closest("a[href],[download]");
  if (!el) return;
  let url = "";
  if (el.tagName === "A" && el.href && (el.hasAttribute("download") || FILE_EXT.test(el.href))) {
    url = el.href;
  }
  if (!url) {
    url = el.getAttribute("data-url") || el.getAttribute("data-download-url") || "";
  }
  if (!url || !FILE_EXT.test(url)) return;
  e.preventDefault();
  e.stopPropagation();
  addItem({ url, type:"FILE", name:shortName(url), size:"",
            referer:location.href, pct:0, status:"Ready" });
  showFloatBtn();
  buildMiniWin();
  state.winOpen = true;
  state.miniWin.classList.add("show");
  toast("Click Download in the panel to start");
}, true);

})();
