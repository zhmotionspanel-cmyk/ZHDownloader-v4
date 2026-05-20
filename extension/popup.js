// ZH Downloader v2 — popup script

let allItems = [];
let currentTabId = null;

const listEl      = document.getElementById("item-list");
const emptyEl     = document.getElementById("empty");
const countEl     = document.getElementById("count");
const searchEl    = document.getElementById("search");
const filterEl    = document.getElementById("filter-type");
const appStatusEl = document.getElementById("app-status");
const appPingEl   = document.getElementById("app-ping");

// ── Init ──────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  loadItems();
  pingApp();
  setInterval(pingApp, 5000);

  searchEl.addEventListener("input", renderList);
  filterEl.addEventListener("change", renderList);

  document.getElementById("btn-clear").addEventListener("click", () => {
    if (!currentTabId) return;
    chrome.runtime.sendMessage({ type: "ZH_CLEAR", tabId: currentTabId });
    allItems = [];
    renderList();
  });

  document.getElementById("btn-page-url").addEventListener("click", () => {
    chrome.runtime.sendMessage({ type: "ZH_PAGE_URL" }, res => {
      showStatus(res?.ok ? "✓ Sent page URL to ZH Downloader app!" : "✗ App not running — open ZH Downloader first", res?.ok);
    });
  });
});

// ── Load items from background ────────────────────────────────────────────

function loadItems() {
  chrome.runtime.sendMessage({ type: "ZH_GET_TAB" }, res => {
    if (!res) return;
    currentTabId = res.tabId;
    allItems     = res.items || [];
    renderList();
  });
}

// Listen for live updates
chrome.runtime.onMessage.addListener(msg => {
  if (msg.type === "ZH_UPDATED" && msg.tabId === currentTabId) {
    allItems = msg.items || [];
    renderList();
  }
});

// ── Render ────────────────────────────────────────────────────────────────

function renderList() {
  const q    = searchEl.value.trim().toLowerCase();
  const type = filterEl.value;

  const filtered = allItems.filter(item => {
    if (type !== "all" && item.type !== type) return false;
    if (q && !item.name.toLowerCase().includes(q) && !item.url.toLowerCase().includes(q)) return false;
    return true;
  });

  listEl.innerHTML = "";
  emptyEl.style.display = filtered.length === 0 ? "block" : "none";
  countEl.textContent   = `${filtered.length} item${filtered.length !== 1 ? "s" : ""}`;

  filtered.forEach(item => {
    const li  = document.createElement("li");
    li.className = "item";

    const isStream = item.type === "HLS" || item.type === "DASH" || item.type === "STREAM";
    const isVideo  = ["MP4","WEBM","MKV","VIDEO","HLS","DASH","STREAM"].includes(item.type);

    // Badge
    const badge = document.createElement("span");
    badge.className  = `type-badge badge-${item.type}`;
    badge.textContent = item.type;

    // Info
    const info     = document.createElement("div");
    info.className = "item-info";
    const name     = document.createElement("span");
    name.className = "item-name";
    name.title     = item.url;
    name.textContent = item.name || shortUrl(item.url);
    const meta     = document.createElement("span");
    meta.className = "item-meta";
    meta.textContent = [item.sizeStr, item.source === "dom" ? "DOM" : "Network"].filter(Boolean).join(" · ");

    info.appendChild(name);
    info.appendChild(meta);

    // Actions
    const actions = document.createElement("div");
    actions.className = "item-actions";

    if (isStream || isVideo) {
      // Send to desktop app
      const btnApp = document.createElement("button");
      btnApp.className   = "btn-app";
      btnApp.textContent = "📤 App";
      btnApp.title       = "Send to ZH Downloader desktop app";
      btnApp.onclick     = () => {
        chrome.runtime.sendMessage({ type: "ZH_SEND_TO_APP", url: item.url }, res => {
          showStatus(res?.ok ? `✓ Sent to app!` : "✗ App not running", res?.ok);
        });
      };
      actions.appendChild(btnApp);
    }

    if (!isStream) {
      // Direct download
      const btnDl = document.createElement("button");
      btnDl.className   = "btn-dl";
      btnDl.textContent = "⬇ Save";
      btnDl.title       = "Download via browser";
      btnDl.onclick     = () => {
        chrome.runtime.sendMessage({ type: "ZH_DOWNLOAD", item }, res => {
          if (res?.ok) showStatus("✓ Download started!", true);
          else showStatus("✗ Download failed: " + (res?.err||""), false);
        });
      };
      actions.appendChild(btnDl);
    }

    // Copy URL
    const btnCopy = document.createElement("button");
    btnCopy.className   = "btn-copy";
    btnCopy.textContent = "🔗";
    btnCopy.title       = "Copy URL";
    btnCopy.onclick     = () => {
      navigator.clipboard.writeText(item.url).then(() => {
        btnCopy.textContent = "✓";
        setTimeout(() => btnCopy.textContent = "🔗", 1500);
      });
    };
    actions.appendChild(btnCopy);

    li.appendChild(badge);
    li.appendChild(info);
    li.appendChild(actions);
    listEl.appendChild(li);
  });
}

// ── App ping ──────────────────────────────────────────────────────────────

async function pingApp() {
  try {
    const r = await fetch("http://127.0.0.1:9613/ping", { signal: AbortSignal.timeout(1500) });
    const d = await r.json();
    appPingEl.className   = "ping-ok";
    appPingEl.textContent = `● App v${d.version}`;
  } catch {
    appPingEl.className   = "ping-err";
    appPingEl.textContent = "● App offline";
  }
}

// ── Status toast ──────────────────────────────────────────────────────────

let statusTimer;
function showStatus(msg, ok) {
  appStatusEl.textContent = msg;
  appStatusEl.className   = "app-status show " + (ok ? "ok" : "err");
  clearTimeout(statusTimer);
  statusTimer = setTimeout(() => {
    appStatusEl.className = "app-status";
  }, 3000);
}

// ── Helpers ───────────────────────────────────────────────────────────────

function shortUrl(url) {
  try {
    const u = new URL(url);
    return u.hostname + u.pathname.slice(0,40);
  } catch { return url.slice(0,60); }
}
