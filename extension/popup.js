// ZH Downloader — popup logic. Renders sniffed media list, handles filter, download, copy.

const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

let state = { tabId: null, items: [], filter: "all", pageUrl: "" };

function fmtBytes(b) {
  if (!b) return "";
  const u = ["B", "KB", "MB", "GB"];
  let i = 0; let n = b;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(n >= 10 ? 0 : 1)} ${u[i]}`;
}

function audioOrVideo(t) {
  if (t === "AUDIO") return "audio";
  return "video";
}

function updateStats() {
  const all = state.items.length;
  const vid = state.items.filter((i) => ["MP4", "WEBM", "VIDEO", "STREAM"].includes(i.type)).length;
  const aud = state.items.filter((i) => i.type === "AUDIO").length;
  const str = state.items.filter((i) => ["HLS", "DASH"].includes(i.type)).length;
  $("#countAll").textContent = all;
  $("#countVideo").textContent = vid;
  $("#countAudio").textContent = aud;
  $("#countStream").textContent = str;
}

function render() {
  updateStats();
  const list = $("#list");
  const filtered = state.filter === "all"
    ? state.items
    : state.items.filter((i) => i.type === state.filter);

  if (!filtered.length) {
    list.innerHTML = `
      <div class="zh-empty">
        <div class="zh-empty-icon">⬇</div>
        <div class="zh-empty-title">${state.items.length ? "No matches" : "No media yet"}</div>
        <div class="zh-empty-sub">${
          state.items.length
            ? "Try a different filter."
            : "Play the video on this page. ZH Downloader will sniff it automatically."
        }</div>
      </div>`;
    return;
  }

  list.innerHTML = filtered.map((item, i) => {
    const size = fmtBytes(item.size);
    const hostname = (() => { try { return new URL(item.url).hostname; } catch { return ""; } })();
    const meta = [size, hostname, item.mime].filter(Boolean).join(" · ");
    return `
      <div class="zh-item" data-i="${i}">
        <div class="zh-type ${item.type}">${item.type}</div>
        <div class="zh-item-body">
          <div class="zh-item-name" title="${escapeHtml(item.url)}">${escapeHtml(item.name || item.url)}</div>
          <div class="zh-item-meta">${escapeHtml(meta)}</div>
        </div>
        <div class="zh-item-actions">
          <button class="zh-copy-btn" data-action="copy" data-url="${escapeHtml(item.url)}">⎘</button>
          <button class="zh-dl-btn" data-action="dl" data-i="${state.items.indexOf(item)}">⬇</button>
        </div>
      </div>`;
  }).join("");

  list.querySelectorAll("[data-action=copy]").forEach((b) =>
    b.addEventListener("click", () => copyUrl(b.dataset.url))
  );
  list.querySelectorAll("[data-action=dl]").forEach((b) =>
    b.addEventListener("click", () => downloadItem(parseInt(b.dataset.i, 10)))
  );
}

function escapeHtml(s) {
  return String(s || "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

function toast(msg) {
  const t = document.createElement("div");
  t.className = "zh-toast";
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 1800);
}

async function copyUrl(url) {
  try {
    await navigator.clipboard.writeText(url);
    toast("URL copied");
  } catch {
    toast("Copy failed");
  }
}

function downloadItem(i) {
  const item = state.items[i];
  if (!item) return;
  chrome.runtime.sendMessage({ type: "ZH_DOWNLOAD", item }, async (res) => {
    if (!res) { toast("Download failed"); return; }
    if (res.copied && res.hint === "hls") {
      // For HLS, copy page URL instead — desktop app handles via yt-dlp
      try {
        await navigator.clipboard.writeText(state.pageUrl || item.url);
        toast("Page URL copied — paste in desktop app");
      } catch {
        toast("HLS stream — use 'Copy Page URL' button");
      }
    }
    else if (res.ok) toast("Download started");
    else toast("Failed: " + (res.err || "unknown"));
  });
}

function loadTab() {
  chrome.runtime.sendMessage({ type: "ZH_GET_TAB" }, (res) => {
    if (!res) return;
    state.tabId = res.tabId;
    state.items = res.items || [];
    state.pageUrl = res.url || "";
    $("#pageTitle").textContent = res.title || res.url || "—";
    render();
  });
}

// Listen for live updates from background.
chrome.runtime.onMessage.addListener((msg) => {
  if (msg && msg.type === "ZH_MEDIA_UPDATED" && msg.tabId === state.tabId) {
    state.items = msg.items;
    render();
  }
});

// Filter chips
$$(".zh-chip").forEach((c) =>
  c.addEventListener("click", () => {
    $$(".zh-chip").forEach((x) => x.classList.remove("active"));
    c.classList.add("active");
    state.filter = c.dataset.filter;
    render();
  })
);

$("#refreshBtn").addEventListener("click", loadTab);
$("#clearBtn").addEventListener("click", () => {
  if (state.tabId == null) return;
  chrome.runtime.sendMessage({ type: "ZH_CLEAR", tabId: state.tabId });
  state.items = [];
  render();
  toast("Cleared");
});
$("#openDesktopHelp").addEventListener("click", (e) => {
  e.preventDefault();
  toast("Run the ZH Downloader .app / .exe — paste any URL there");
});

$("#copyPageBtn").addEventListener("click", async () => {
  if (!state.pageUrl) { toast("No page URL"); return; }
  try {
    await navigator.clipboard.writeText(state.pageUrl);
    toast("Page URL copied — paste in desktop app");
  } catch {
    toast("Copy failed");
  }
});

loadTab();
