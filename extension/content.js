// ZH Downloader v2 — content script
// Scans DOM for video, audio, and downloadable file links

(function() {
  'use strict';

  const FILE_EXT = /\.(mp4|webm|mkv|mov|flv|m4v|mp3|m4a|aac|wav|flac|ogg|pdf|zip|rar|7z|exe|dmg|pkg|msi|apk|iso|tar\.gz|tar|gz|bz2|docx?|xlsx?|pptx?|jpg|jpeg|png|gif|webp|psd|epub|torrent)(\?|$)/i;

  function collectItems() {
    const items = [];
    const seen  = new Set();

    function add(url, mime, name, title, poster) {
      if (!url || seen.has(url)) return;
      try { new URL(url); } catch { return; }
      seen.add(url);
      items.push({ url, mime: mime||"", name: name||"", title: title||"", poster: poster||"" });
    }

    // <video> and <audio> elements
    document.querySelectorAll("video, audio").forEach(el => {
      const src = el.src || el.currentSrc;
      if (src) add(src, el.type||"", "", document.title, el.poster||"");
      el.querySelectorAll("source").forEach(s => {
        if (s.src) add(s.src, s.type||"", "", document.title, "");
      });
    });

    // <source> anywhere
    document.querySelectorAll("source[src]").forEach(s => {
      if (s.src) add(s.src, s.type||"", "", document.title, "");
    });

    // <a href> links matching file extensions
    document.querySelectorAll("a[href]").forEach(a => {
      const href = a.href;
      if (href && FILE_EXT.test(href)) {
        const name = a.textContent?.trim().slice(0,80) || "";
        add(href, "", name, document.title, "");
      }
    });

    // <iframe> src that looks like media
    document.querySelectorAll("iframe[src]").forEach(f => {
      if (FILE_EXT.test(f.src)) add(f.src, "", "", document.title, "");
    });

    // Open Graph / meta tags for video
    document.querySelectorAll("meta[property='og:video'], meta[property='og:video:url'], meta[property='og:audio']").forEach(m => {
      if (m.content) add(m.content, "", "", document.title, "");
    });

    return items;
  }

  function scan() {
    const items = collectItems();
    if (items.length > 0) {
      chrome.runtime.sendMessage({ type: "ZH_DOM", items });
    }
  }

  // Initial scan
  scan();

  // Re-scan on DOM changes (lazy-loaded content, SPAs)
  let timer;
  const observer = new MutationObserver(() => {
    clearTimeout(timer);
    timer = setTimeout(scan, 800);
  });
  observer.observe(document.body || document.documentElement, {
    childList: true, subtree: true
  });

  // Re-scan on page visibility (tab switch)
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) scan();
  });
})();
