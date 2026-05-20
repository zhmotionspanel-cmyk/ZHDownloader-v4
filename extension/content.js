// ZH Downloader content script:
//  1. Scans DOM for <video>/<audio>/<source> + reports to background.
//  2. Injects IDM-style floating "Download" overlay on detected video players.
(function () {
  if (window.__zhInjected) return;
  window.__zhInjected = true;

  const seen = new Set();
  const overlayMap = new WeakMap();

  function collect() {
    const items = [];
    const push = (url, extra = {}) => {
      if (!url || seen.has(url)) return;
      if (url.startsWith("blob:") || url.startsWith("data:")) return;
      seen.add(url);
      items.push({ url, ...extra });
    };

    document.querySelectorAll("video").forEach((v) => {
      if (v.src) push(v.src, {
        mime: v.type || "",
        name: (document.title || "video").slice(0, 60) + ".mp4",
        title: document.title || "",
        poster: v.poster || ""
      });
      v.querySelectorAll("source").forEach((s) => {
        if (s.src) push(s.src, {
          mime: s.type || "",
          name: (document.title || "video").slice(0, 60) + ".mp4",
          title: document.title || ""
        });
      });
    });

    document.querySelectorAll("audio").forEach((a) => {
      if (a.src) push(a.src, { mime: a.type || "", name: (document.title || "audio").slice(0, 60) + ".mp3" });
      a.querySelectorAll("source").forEach((s) => s.src && push(s.src, { mime: s.type || "" }));
    });

    return items;
  }

  function report() {
    const items = collect();
    if (items.length) {
      chrome.runtime.sendMessage({ type: "ZH_MEDIA_DOM", items }).catch(() => {});
    }
    attachOverlays();
  }

  // -------- FLOATING OVERLAY --------
  const STYLE_ID = "zh-dl-overlay-style";
  function ensureStyles() {
    if (document.getElementById(STYLE_ID)) return;
    const s = document.createElement("style");
    s.id = STYLE_ID;
    s.textContent = `
      .zh-dl-float {
        position: fixed !important;
        z-index: 2147483647 !important;
        display: flex !important; align-items: center; gap: 6px;
        background: linear-gradient(135deg, #5b1a1f, #3d1014) !important;
        color: #d4a13a !important;
        border: 1px solid #d4a13a !important;
        padding: 7px 11px !important;
        border-radius: 7px !important;
        font: 600 12px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
        cursor: pointer !important;
        box-shadow: 0 4px 16px rgba(0,0,0,0.55) !important;
        opacity: 0;
        transform: translateY(-4px);
        transition: opacity .2s, transform .2s, background .2s;
        pointer-events: auto !important;
        user-select: none;
        margin: 0 !important;
      }
      .zh-dl-float.visible { opacity: 1; transform: translateY(0); }
      .zh-dl-float:hover {
        background: linear-gradient(135deg, #6d2026, #5b1a1f) !important;
        color: #ffd166 !important;
      }
      .zh-dl-float.zh-loading {
        background: #2a2a2a !important;
        color: #d4a13a !important;
      }
      .zh-dl-float.zh-loading .zh-dl-dot {
        animation: zh-dl-spin 0.8s linear infinite !important;
        background: transparent !important;
        border: 2px solid #d4a13a;
        border-top-color: transparent;
        box-shadow: none !important;
      }
      .zh-dl-float.zh-success {
        background: linear-gradient(135deg, #1f4a2a, #133018) !important;
        color: #4ade80 !important;
        border-color: #4ade80 !important;
      }
      @keyframes zh-dl-spin {
        to { transform: rotate(360deg); }
      }
      .zh-dl-float .zh-dl-dot {
        width: 8px; height: 8px; border-radius: 50%;
        background: #d4a13a;
        box-shadow: 0 0 6px #d4a13a;
        animation: zh-dl-pulse 1.6s infinite ease-in-out;
      }
      @keyframes zh-dl-pulse {
        0%,100% { opacity: 1; }
        50% { opacity: 0.4; }
      }
      .zh-dl-menu {
        position: absolute;
        z-index: 2147483647;
        background: #0f0f0f;
        border: 1px solid #d4a13a;
        border-radius: 8px;
        padding: 6px;
        min-width: 200px;
        font: 12px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        box-shadow: 0 8px 30px rgba(0,0,0,0.7);
      }
      .zh-dl-menu button {
        display: block; width: 100%; text-align: left;
        background: transparent; border: 0; color: #ececec;
        padding: 8px 10px; border-radius: 5px;
        cursor: pointer; font-size: 12px;
      }
      .zh-dl-menu button:hover { background: #2a1a1c; color: #d4a13a; }
      .zh-dl-menu .zh-dl-divider { height: 1px; background: #2a2a2a; margin: 4px 0; }
      .zh-dl-menu .zh-dl-label { color: #6b6b6b; font-size: 10px; padding: 4px 10px; text-transform: uppercase; letter-spacing: 0.5px; }
    `;
    (document.head || document.documentElement).appendChild(s);
  }

  function isPlayerLikeVideo(v) {
    const rect = v.getBoundingClientRect();
    // Filter out hidden + tiny preview thumbs
    if (rect.width < 200 || rect.height < 120) return false;
    if (getComputedStyle(v).display === "none") return false;
    if (getComputedStyle(v).visibility === "hidden") return false;
    return true;
  }

  function findContainer(v) {
    // Walk up to nearest positioned element
    let el = v.parentElement;
    while (el && el !== document.body) {
      const pos = getComputedStyle(el).position;
      if (pos === "relative" || pos === "absolute" || pos === "fixed") return el;
      el = el.parentElement;
    }
    return v.parentElement || document.body;
  }

  const BRIDGE = "http://127.0.0.1:9613";

  async function sendToDesktopApp(url) {
    try {
      const res = await fetch(BRIDGE + "/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url })
      });
      if (!res.ok) throw new Error("bad status");
      return true;
    } catch {
      return false;
    }
  }

  async function oneClickDownload(btn) {
    const pageUrl = location.href;
    btn.classList.add("zh-loading");
    const sent = await sendToDesktopApp(pageUrl);
    btn.classList.remove("zh-loading");
    if (sent) {
      toast("✓ Sent to ZH Downloader — downloading now");
      btn.classList.add("zh-success");
      setTimeout(() => btn.classList.remove("zh-success"), 1500);
    } else {
      // App not running — copy URL + show install hint
      try {
        await navigator.clipboard.writeText(pageUrl);
        toast("⚠ Desktop app not running — URL copied. Open ZH Downloader app and paste.");
      } catch {
        toast("⚠ Desktop app not running. Install ZH Downloader.");
      }
    }
  }

  function toast(msg) {
    let t = document.getElementById("zh-dl-toast");
    if (t) t.remove();
    t = document.createElement("div");
    t.id = "zh-dl-toast";
    t.textContent = msg;
    t.style.cssText = `
      position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%);
      background: #5b1a1f; color: #d4a13a;
      padding: 10px 16px; border-radius: 7px;
      font: 600 12px -apple-system, BlinkMacSystemFont, sans-serif;
      box-shadow: 0 6px 20px rgba(0,0,0,0.5);
      z-index: 2147483647;
      border: 1px solid #d4a13a;
    `;
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 2200);
  }

  function positionBtn(btn, v) {
    const r = v.getBoundingClientRect();
    if (r.width < 200 || r.height < 120) {
      btn.style.display = "none";
      return;
    }
    btn.style.display = "flex";
    btn.style.top = (r.top + 12) + "px";
    btn.style.left = (r.right - btn.offsetWidth - 12) + "px";
  }

  function attachOverlays() {
    ensureStyles();
    document.querySelectorAll("video").forEach((v) => {
      if (overlayMap.has(v)) return;
      if (!isPlayerLikeVideo(v)) return;

      const btn = document.createElement("button");
      btn.className = "zh-dl-float";
      btn.type = "button";
      btn.innerHTML = `<span class="zh-dl-dot"></span><span>Download</span>`;
      btn.title = "ZH Downloader — Download this video";

      // Use pointerdown (fires before YouTube click capture)
      btn.addEventListener("pointerdown", (e) => {
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
        oneClickDownload(btn);
      }, true);
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
      }, true);

      // Attach to body so player controls can't overlay it
      document.body.appendChild(btn);

      // Position relative to video
      positionBtn(btn, v);

      const reveal = () => {
        btn.classList.add("visible");
        positionBtn(btn, v);
      };
      const hide = () => {
        setTimeout(() => {
          if (!btn.matches(":hover")) btn.classList.remove("visible");
        }, 800);
      };

      // Find largest hover surface (video itself or its container)
      const hoverTarget = findContainer(v) || v;
      hoverTarget.addEventListener("mouseenter", reveal);
      hoverTarget.addEventListener("mousemove", reveal);
      hoverTarget.addEventListener("mouseleave", hide);
      v.addEventListener("play", reveal);

      // Initial visible 4 sec
      setTimeout(reveal, 200);
      setTimeout(() => btn.classList.remove("visible"), 4800);

      // Reposition on scroll/resize/layout shifts
      const repos = () => positionBtn(btn, v);
      window.addEventListener("scroll", repos, true);
      window.addEventListener("resize", repos);
      setInterval(repos, 1000); // catch CSS-only layout changes

      overlayMap.set(v, btn);
    });
  }

  // Initial scan + observe DOM mutations
  report();
  const obs = new MutationObserver(() => report());
  obs.observe(document.documentElement, { childList: true, subtree: true });

  ["click", "play", "loadeddata"].forEach((ev) =>
    document.addEventListener(ev, report, true)
  );
})();
