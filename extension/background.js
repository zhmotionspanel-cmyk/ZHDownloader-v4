// ZH Downloader — background service worker.
// Sniffs media requests across the browser, dedupes per tab, persists in chrome.storage.session.

const MEDIA_EXT = /\.(mp4|m3u8|mpd|webm|mov|mkv|flv|avi|m4v|m4a|mp3|aac|ogg|wav|flac)(\?|$)/i;
// HLS segment formats — hide from list, keep only manifest .m3u8
const SEGMENT_EXT = /\.(ts|m4s|aac|fmp4)(\?|$)/i;
const MEDIA_TYPE = /^(video|audio)\//i;
const MEDIA_KEYWORDS = /(videoplayback|manifest\.mpd|master\.m3u8|playlist\.m3u8)/i;
// Skip noisy small chunks
const SKIP_KEYWORDS = /(chunk-stream|segment-|seg-\d|\/seg\/|\/chunk\/)/i;

const tabState = new Map();

function getTabBucket(tabId) {
  if (!tabState.has(tabId)) tabState.set(tabId, []);
  return tabState.get(tabId);
}

function isMediaLike(url, type) {
  if (!url) return false;
  // Reject HLS/DASH segments (only keep manifests)
  if (SEGMENT_EXT.test(url)) return false;
  if (SKIP_KEYWORDS.test(url)) return false;
  if (type && MEDIA_TYPE.test(type)) {
    // Allow video/audio mime types but reject if it's clearly a segment by content-type
    if (type.includes("video/mp2t") || type.includes("video/iso.segment")) return false;
    return true;
  }
  if (MEDIA_EXT.test(url)) return true;
  if (MEDIA_KEYWORDS.test(url)) return true;
  return false;
}

function classify(url, type) {
  const u = url.toLowerCase();
  if (u.includes(".m3u8") || u.includes("master.m3u8") || u.includes("playlist.m3u8")) return "HLS";
  if (u.includes(".mpd")) return "DASH";
  if (u.match(/\.mp4(\?|$)/)) return "MP4";
  if (u.match(/\.webm(\?|$)/)) return "WEBM";
  if (u.match(/\.(mp3|m4a|aac|ogg|wav|flac)(\?|$)/)) return "AUDIO";
  if (u.includes("videoplayback")) return "STREAM";
  if (type && type.startsWith("video/")) return "VIDEO";
  if (type && type.startsWith("audio/")) return "AUDIO";
  return "MEDIA";
}

function fileNameFromUrl(url) {
  try {
    const u = new URL(url);
    const name = u.pathname.split("/").filter(Boolean).pop() || u.hostname;
    return decodeURIComponent(name).slice(0, 80);
  } catch {
    return "media";
  }
}

function pushMedia(tabId, item) {
  const bucket = getTabBucket(tabId);
  if (bucket.some((b) => b.url === item.url)) return;
  bucket.unshift(item);
  if (bucket.length > 50) bucket.length = 50;
  updateBadge(tabId);
  broadcast(tabId);
}

function updateBadge(tabId) {
  const count = getTabBucket(tabId).length;
  chrome.action.setBadgeBackgroundColor({ color: "#d4a13a" });
  chrome.action.setBadgeTextColor({ color: "#0a0a0a" }).catch(() => {});
  chrome.action.setBadgeText({ tabId, text: count > 0 ? String(count) : "" });
}

function broadcast(tabId) {
  chrome.runtime.sendMessage({ type: "ZH_MEDIA_UPDATED", tabId, items: getTabBucket(tabId) }).catch(() => {});
}

chrome.webRequest.onResponseStarted.addListener(
  (details) => {
    if (details.tabId < 0) return;
    const headers = (details.responseHeaders || []).reduce((m, h) => {
      m[h.name.toLowerCase()] = h.value;
      return m;
    }, {});
    const ctype = headers["content-type"] || "";
    if (!isMediaLike(details.url, ctype)) return;
    const size = parseInt(headers["content-length"] || "0", 10);
    pushMedia(details.tabId, {
      url: details.url,
      type: classify(details.url, ctype),
      mime: ctype,
      size,
      name: fileNameFromUrl(details.url),
      source: "network",
      ts: Date.now()
    });
  },
  { urls: ["<all_urls>"] },
  ["responseHeaders"]
);

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || !msg.type) return;

  if (msg.type === "ZH_MEDIA_DOM" && sender.tab) {
    for (const item of msg.items || []) {
      pushMedia(sender.tab.id, {
        url: item.url,
        type: classify(item.url, item.mime || ""),
        mime: item.mime || "",
        size: 0,
        name: item.name || fileNameFromUrl(item.url),
        source: "dom",
        title: item.title || "",
        poster: item.poster || "",
        ts: Date.now()
      });
    }
  }

  if (msg.type === "ZH_GET_TAB") {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (!tabs.length) {
        sendResponse({ tabId: null, items: [] });
        return;
      }
      const tabId = tabs[0].id;
      sendResponse({
        tabId,
        url: tabs[0].url,
        title: tabs[0].title,
        items: getTabBucket(tabId)
      });
    });
    return true;
  }

  if (msg.type === "ZH_CLEAR" && msg.tabId != null) {
    tabState.set(msg.tabId, []);
    updateBadge(msg.tabId);
    broadcast(msg.tabId);
  }

  if (msg.type === "ZH_DOWNLOAD") {
    handleDownload(msg.item).then((res) => sendResponse(res));
    return true;
  }
});

async function handleDownload(item) {
  if (!item || !item.url) return { ok: false, err: "no url" };
  // HLS/DASH manifests can't be downloaded directly — copy URL and warn user.
  if (item.type === "HLS" || item.type === "DASH") {
    // Open offscreen page to copy (service workers can't access navigator.clipboard)
    chrome.notifications.create({
      type: "basic",
      iconUrl: "icons/icon128.png",
      title: "ZH Downloader",
      message: "HLS/DASH stream — use 'Copy Page URL' button + paste in desktop ZH Downloader app."
    });
    return { ok: true, copied: true, hint: "hls" };
  }
  try {
    const id = await chrome.downloads.download({
      url: item.url,
      filename: item.name || fileNameFromUrl(item.url),
      saveAs: false
    });
    return { ok: true, id };
  } catch (e) {
    return { ok: false, err: String(e) };
  }
}

chrome.tabs.onRemoved.addListener((tabId) => {
  tabState.delete(tabId);
});

chrome.webNavigation && chrome.webNavigation.onCommitted &&
  chrome.webNavigation.onCommitted.addListener((d) => {
    if (d.frameId === 0) {
      tabState.set(d.tabId, []);
      updateBadge(d.tabId);
    }
  });
