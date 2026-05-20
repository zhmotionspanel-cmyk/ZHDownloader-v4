// ZH Downloader v2 — background service worker
// Sniffs ALL media + general files across the browser

const MEDIA_EXT    = /\.(mp4|m3u8|mpd|webm|mov|mkv|flv|avi|m4v|m4a|mp3|aac|ogg|wav|flac)(\?|$)/i;
const FILE_EXT     = /\.(pdf|zip|rar|7z|exe|dmg|pkg|msi|apk|iso|tar|gz|bz2|docx?|xlsx?|pptx?|jpg|jpeg|png|gif|webp|svg|psd|ai|epub|torrent)(\?|$)/i;
const SEGMENT_EXT  = /\.(ts|m4s|fmp4)(\?|$)/i;
const SKIP_KW      = /(chunk-stream|segment-|seg-\d|\/seg\/|\/chunk\/|\.vtt(\?|$)|\.srt(\?|$))/i;
const MEDIA_TYPE   = /^(video|audio)\//i;
const MEDIA_KW     = /(videoplayback|manifest\.mpd|master\.m3u8|playlist\.m3u8)/i;

const tabState = new Map();

function getTabBucket(tabId) {
  if (!tabState.has(tabId)) tabState.set(tabId, []);
  return tabState.get(tabId);
}

function isWanted(url, ctype) {
  if (!url) return false;
  if (SEGMENT_EXT.test(url)) return false;
  if (SKIP_KW.test(url)) return false;
  if (ctype && (MEDIA_TYPE.test(ctype) || ctype.includes("application/pdf") || ctype.includes("application/zip") || ctype.includes("application/octet-stream"))) return true;
  if (MEDIA_EXT.test(url) || FILE_EXT.test(url) || MEDIA_KW.test(url)) return true;
  return false;
}

function classify(url, ctype) {
  const u = url.toLowerCase();
  if (u.includes(".m3u8") || u.includes("master.m3u8")) return "HLS";
  if (u.includes(".mpd"))  return "DASH";
  if (u.match(/\.mp4(\?|$)/))  return "MP4";
  if (u.match(/\.webm(\?|$)/)) return "WEBM";
  if (u.match(/\.mkv(\?|$)/))  return "MKV";
  if (u.match(/\.(mp3|m4a|aac|ogg|wav|flac)(\?|$)/)) return "AUDIO";
  if (u.match(/\.pdf(\?|$)/))  return "PDF";
  if (u.match(/\.(zip|rar|7z|tar|gz)(\?|$)/)) return "ZIP";
  if (u.match(/\.(exe|dmg|pkg|msi|apk)(\?|$)/)) return "INSTALLER";
  if (u.match(/\.(jpg|jpeg|png|gif|webp|svg)(\?|$)/)) return "IMAGE";
  if (u.match(/\.(docx?|xlsx?|pptx?)(\?|$)/)) return "DOC";
  if (u.includes("videoplayback")) return "STREAM";
  if (ctype && ctype.startsWith("video/")) return "VIDEO";
  if (ctype && ctype.startsWith("audio/")) return "AUDIO";
  if (ctype && ctype.includes("pdf")) return "PDF";
  return "FILE";
}

function fileNameFromUrl(url) {
  try {
    const u    = new URL(url);
    const name = u.pathname.split("/").filter(Boolean).pop() || u.hostname;
    return decodeURIComponent(name).slice(0, 100);
  } catch { return "file"; }
}

function fmtSize(bytes) {
  if (!bytes || bytes === 0) return "";
  if (bytes > 1073741824) return (bytes/1073741824).toFixed(1)+" GB";
  if (bytes > 1048576)    return (bytes/1048576).toFixed(1)+" MB";
  if (bytes > 1024)       return (bytes/1024).toFixed(0)+" KB";
  return bytes+" B";
}

function pushItem(tabId, item) {
  const bucket = getTabBucket(tabId);
  if (bucket.some(b => b.url === item.url)) return;
  bucket.unshift(item);
  if (bucket.length > 80) bucket.length = 80;
  updateBadge(tabId);
  broadcast(tabId);
}

function updateBadge(tabId) {
  const count = getTabBucket(tabId).length;
  chrome.action.setBadgeBackgroundColor({ color: "#d4a13a" });
  chrome.action.setBadgeTextColor({ color: "#0a0a0a" }).catch(()=>{});
  chrome.action.setBadgeText({ tabId, text: count > 0 ? String(count) : "" });
}

function broadcast(tabId) {
  chrome.runtime.sendMessage({ type: "ZH_UPDATED", tabId, items: getTabBucket(tabId) }).catch(()=>{});
}

// Sniff network requests
chrome.webRequest.onResponseStarted.addListener(details => {
  if (details.tabId < 0) return;
  const headers = (details.responseHeaders||[]).reduce((m,h) => { m[h.name.toLowerCase()] = h.value; return m; }, {});
  const ctype   = headers["content-type"] || "";
  if (!isWanted(details.url, ctype)) return;
  const size    = parseInt(headers["content-length"]||"0", 10);
  pushItem(details.tabId, {
    url:    details.url,
    type:   classify(details.url, ctype),
    mime:   ctype,
    size,
    sizeStr: fmtSize(size),
    name:   fileNameFromUrl(details.url),
    source: "network",
    ts:     Date.now()
  });
}, { urls: ["<all_urls>"] }, ["responseHeaders"]);

// Messages from popup/content
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg?.type) return;

  // DOM-scanned items from content.js
  if (msg.type === "ZH_DOM" && sender.tab) {
    for (const item of msg.items||[]) {
      pushItem(sender.tab.id, {
        url:    item.url,
        type:   classify(item.url, item.mime||""),
        mime:   item.mime||"",
        size:   0,
        sizeStr:"",
        name:   item.name || fileNameFromUrl(item.url),
        source: "dom",
        title:  item.title||"",
        ts:     Date.now()
      });
    }
  }

  // Popup asking for current tab info
  if (msg.type === "ZH_GET_TAB") {
    chrome.tabs.query({ active:true, currentWindow:true }, tabs => {
      if (!tabs.length) { sendResponse({ tabId:null, items:[] }); return; }
      const tab = tabs[0];
      sendResponse({ tabId: tab.id, url: tab.url, title: tab.title, items: getTabBucket(tab.id) });
    });
    return true;
  }

  // Clear tab items
  if (msg.type === "ZH_CLEAR" && msg.tabId != null) {
    tabState.set(msg.tabId, []);
    updateBadge(msg.tabId);
    broadcast(msg.tabId);
  }

  // Send URL to desktop app
  if (msg.type === "ZH_SEND_TO_APP") {
    sendToApp(msg.url).then(r => sendResponse(r));
    return true;
  }

  // Direct browser download
  if (msg.type === "ZH_DOWNLOAD") {
    handleDownload(msg.item).then(r => sendResponse(r));
    return true;
  }

  // Download current page URL
  if (msg.type === "ZH_PAGE_URL") {
    chrome.tabs.query({ active:true, currentWindow:true }, tabs => {
      if (!tabs.length) { sendResponse({ ok:false }); return; }
      sendToApp(tabs[0].url).then(r => sendResponse(r));
    });
    return true;
  }
});

// Send URL to ZH Downloader desktop app via HTTP bridge
async function sendToApp(url) {
  try {
    const r = await fetch("http://127.0.0.1:9613/download", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ url }),
    });
    const data = await r.json();
    if (data.ok) {
      chrome.notifications.create({
        type: "basic", iconUrl: "icons/icon128.png",
        title: "ZH Downloader", message: `Sent to app: ${url.slice(0,60)}…`
      });
    }
    return data;
  } catch(e) {
    chrome.notifications.create({
      type: "basic", iconUrl: "icons/icon128.png",
      title: "ZH Downloader — App not running",
      message: "Open ZH Downloader app first, then try again."
    });
    return { ok:false, err: String(e) };
  }
}

async function handleDownload(item) {
  if (!item?.url) return { ok:false, err:"no url" };
  // Streams → send to desktop app
  if (item.type === "HLS" || item.type === "DASH" || item.type === "STREAM") {
    return sendToApp(item.url);
  }
  // Direct files → browser download
  try {
    const id = await chrome.downloads.download({
      url: item.url,
      filename: item.name || fileNameFromUrl(item.url),
      saveAs: false
    });
    return { ok:true, id };
  } catch(e) {
    return { ok:false, err:String(e) };
  }
}

// Cleanup on tab close/navigate
chrome.tabs.onRemoved.addListener(tabId => tabState.delete(tabId));
chrome.webNavigation.onCommitted.addListener(d => {
  if (d.frameId === 0) { tabState.set(d.tabId, []); updateBadge(d.tabId); }
});
