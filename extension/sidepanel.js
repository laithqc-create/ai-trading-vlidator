/**
 * sidepanel.js
 * Full side panel logic:
 *  - Tab navigation
 *  - Plan/trial banner
 *  - Chart monitoring controls
 *  - Manual screenshot + analysis
 *  - Chat back-and-forth on screenshots
 *  - News text highlight relay
 *  - Stats loading
 *  - Settings persistence
 */

// ── State ─────────────────────────────────────────────────────────────────────
let state = {
  token: null,
  telegramId: null,
  backendUrl: "https://ai-trading-vlidator.onrender.com",
  monitoring: false,
  lastScreenshotId: null,
  chatHistory: [],
  currentSymbol: null,
};

// Null-safe getElementById — prevents crashes when an element is missing
const $id = (id) => document.getElementById(id);

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", async () => {
  try { await loadSettings(); } catch(e) { console.error("loadSettings:", e); }
  try { initTabs(); } catch(e) { console.error("initTabs:", e); }
  try { initMonitorTab(); } catch(e) { console.error("initMonitorTab:", e); }
  try { initChatTab(); } catch(e) { console.error("initChatTab:", e); }
  try { initNewsTab(); } catch(e) { console.error("initNewsTab:", e); }
  try { initSettingsTab(); } catch(e) { console.error("initSettingsTab:", e); }
  try { await loadPlanBanner(); } catch(e) { console.error("loadPlanBanner:", e); }
  try { await loadStats(); } catch(e) { console.error("loadStats:", e); }
  try { listenFromBackground(); } catch(e) { console.error("listenFromBackground:", e); }
});

// ── Settings persistence ──────────────────────────────────────────────────────
async function loadSettings() {
  const data = await chrome.storage.local.get(["token", "telegramId", "backendUrl"]);
  state.token = data.token || null;
  state.telegramId = data.telegramId || null;
  state.backendUrl = data.backendUrl || "https://ai-trading-vlidator.onrender.com";
}

async function saveSettings() {
  await chrome.storage.local.set({
    token: state.token,
    telegramId: state.telegramId,
    backendUrl: state.backendUrl,
  });
}

// ── Tab navigation ────────────────────────────────────────────────────────────
function initTabs() {
  document.querySelectorAll(".nav-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      const name = tab.dataset.tab;
      document.querySelectorAll(".nav-tab").forEach((t) => t.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
      tab.classList.add("active");
      document.getElementById(`tab-${name}`).classList.add("active");
    });
  });
}

// ── Plan banner ───────────────────────────────────────────────────────────────
async function loadPlanBanner() {
  if (!state.token && !state.telegramId) {
    setPlanBanner("Not connected", "Enter your API token in Settings to get started", true);
    return;
  }
  try {
    const [planRes, trialRes] = await Promise.all([
      apiGet("/api/user/plan"),
      apiGet("/api/trial/status"),
    ]);

    const badge       = document.getElementById("plan-badge");
    const name        = document.getElementById("plan-name-text");
    const sub         = document.getElementById("plan-sub-text");
    const upgradeBtn  = document.getElementById("btn-upgrade");

    // API returns plan_name (not plan_label) and days_left (not days_remaining)
    const planName  = planRes.plan_name  || planRes.plan_label  || planRes.plan || "Free";
    const daysLeft  = trialRes.days_left ?? trialRes.days_remaining ?? 0;
    const isTrialOn = trialRes.trial_active ?? trialRes.active ?? false;

    if (isTrialOn) {
      badge.textContent  = `Trial — ${daysLeft}d left`;
      name.textContent   = "Free Trial";
      sub.textContent    = `${daysLeft} days remaining`;
      upgradeBtn.style.display = "block";
      upgradeBtn.onclick = () => openWhop("pro");
    } else if (planRes.plan && planRes.plan !== "free") {
      badge.textContent  = planName;
      name.textContent   = planName;
      sub.textContent    = planRes.expires_at
        ? `Renews ${new Date(planRes.expires_at).toLocaleDateString()}`
        : "Active";
      upgradeBtn.style.display = "none";
    } else {
      badge.textContent  = "Free";
      name.textContent   = "Free plan";
      const trialUsed    = !isTrialOn && trialRes.trial_expires_at;
      sub.textContent    = trialUsed ? "Trial used" : "14-day trial available";
      upgradeBtn.style.display = "block";
      upgradeBtn.textContent   = trialUsed ? "Upgrade" : "Start free trial";
      upgradeBtn.onclick       = trialUsed ? () => openWhop("pro") : startTrial;
    }

    document.getElementById("sub-plan-value").textContent = planName;
  } catch (e) {
    setPlanBanner("Free", "Connect your account in Settings", true);
  }
}

function setPlanBanner(name, sub, showUpgrade) {
  document.getElementById("plan-name-text").textContent = name;
  document.getElementById("plan-sub-text").textContent = sub;
  document.getElementById("plan-badge").textContent = name;
  const btn = document.getElementById("btn-upgrade");
  btn.style.display = showUpgrade ? "block" : "none";
}

async function startTrial() {
  if (!state.token && !state.telegramId) { alert("Enter your API token in Settings first."); return; }
  try {
    const r = await apiPost("/api/trial/start", {});
    if (r.ok) {
      alert(`✅ Trial started! You have ${r.days_remaining} days of full access.`);
      await loadPlanBanner();
    } else {
      alert(r.message || "Could not start trial.");
    }
  } catch (e) {
    alert("Error starting trial. Check your connection.");
  }
}

async function openWhop(plan) {
  try {
    const r = await apiGet(`/api/checkout/${plan}`);
    if (r.checkout_url) {
      chrome.tabs.create({ url: r.checkout_url });
      return;
    }
  } catch (e) { /* fall through to fallback */ }
  // Fallback: open Whop directly if backend unavailable
  const url = `https://whop.com/checkout?metadata[telegram_id]=${state.telegramId || ""}&plan=${plan}`;
  chrome.tabs.create({ url });
}

// ── Monitor tab ───────────────────────────────────────────────────────────────
function initMonitorTab() {
  document.getElementById("btn-detect").addEventListener("click", detectSymbol);
  document.getElementById("btn-start-monitor").addEventListener("click", startMonitor);
  document.getElementById("btn-stop").addEventListener("click", stopMonitor);
  document.getElementById("btn-screenshot").addEventListener("click", manualScreenshot);

  // Restore monitoring state
  chrome.storage.local.get("monitoring", ({ monitoring }) => {
    if (monitoring?.active && Date.now() < monitoring.endTime) {
      setMonitorActive(true, monitoring.timeframe, monitoring.symbol);
    }
  });
}

async function detectSymbol() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tabs.length) return;
  chrome.tabs.sendMessage(tabs[0].id, { type: "GET_SYMBOL" }, (resp) => {
    if (chrome.runtime.lastError || !resp) return;
    if (resp.symbol) {
      document.getElementById("input-symbol").value = resp.symbol;
      state.currentSymbol = resp.symbol;
    }
  });
}

async function startMonitor() {
  if (!state.token) { alert("Set your API token in Settings first."); return; }
  const symbol = document.getElementById("input-symbol").value.trim().toUpperCase();
  const timeframe = document.getElementById("sel-timeframe").value;
  const duration = parseInt(document.getElementById("sel-duration").value);

  if (!symbol) { alert("Enter a symbol."); return; }

  chrome.runtime.sendMessage({
    type: "START_MONITORING",
    durationMinutes: duration,
    timeframe,
    symbol,
    token: state.token,
  }, (r) => {
    if (r?.ok) setMonitorActive(true, timeframe, symbol);
  });
}

function stopMonitor() {
  chrome.runtime.sendMessage({ type: "STOP_MONITORING" }, () => {
    setMonitorActive(false);
  });
}

function setMonitorActive(active, tf, symbol) {
  state.monitoring = active;
  const dot = document.getElementById("monitor-dot");
  const info = document.getElementById("monitor-info");
  const stopBtn = document.getElementById("btn-stop");
  const startBtn = document.getElementById("btn-start-monitor");

  if (active) {
    dot.classList.add("active");
    info.textContent = `Monitoring ${symbol} · ${tf} candle close`;
    stopBtn.classList.remove("hidden");
    startBtn.textContent = "⏳ Monitoring...";
    startBtn.disabled = true;
  } else {
    dot.classList.remove("active");
    info.textContent = "Monitoring off";
    stopBtn.classList.add("hidden");
    startBtn.textContent = "▶ Start monitoring";
    startBtn.disabled = false;
  }
}

async function manualScreenshot() {
  if (!state.token) { alert("Set your API token in Settings first."); return; }
  const symbol = document.getElementById("input-symbol").value.trim().toUpperCase() || "UNKNOWN";
  const timeframe = document.getElementById("sel-timeframe").value;

  const btn = document.getElementById("btn-screenshot");
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Analysing...';

  chrome.runtime.sendMessage({
    type: "TAKE_SCREENSHOT",
    token: state.token,
    symbol,
    timeframe,
    chatHistory: state.chatHistory,
  }, (r) => {
    btn.disabled = false;
    btn.textContent = "📸 Analyse current chart";
    if (r?.ok === false) {
      alert("Analysis error: " + (r.error || "unknown"));
      return;
    }
    showAnalysisResult(r);
  });
}

function showAnalysisResult(result) {
  if (!result) return;

  state.lastScreenshotId = result.id || result.screenshot_id || null;

  const card = document.getElementById("result-card");
  const report = result.report || result;

  card.innerHTML = renderFullReport(report);
  card.classList.add("show");

  const sig = (report.signal || result.signal || result.decision || "NEUTRAL").toUpperCase();
  addChatMessage("system", `📊 Analysis complete: ${sig} — ${(report.patterns || []).map(p => p.name || p).join(", ") || "patterns detected"}`);
  document.getElementById("chat-empty").style.display = "none";
}

function renderFullReport(report) {
  const sig = (report.signal || "NEUTRAL").toUpperCase();
  const sigColor = sig === "BUY" ? "var(--green)" : sig === "SELL" ? "var(--red)" : "var(--yellow)";
  const sigEmoji = sig === "BUY" ? "🟢" : sig === "SELL" ? "🔴" : "🟡";
  const ind = report.indicators || {};
  const groups = ind.groups || {};
  const bias = ind.overall_bias || "neutral";
  const confidence = report.confidence || 0;

  let html = `
    <div style="margin-bottom:10px">
      <div style="font-size:16px;font-weight:700;color:${sigColor};margin-bottom:4px">${sigEmoji} ${sig}</div>
      <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:6px">
        ${report.symbol ? `<span style="font-size:10px;padding:2px 7px;border-radius:20px;background:rgba(88,166,255,.12);color:var(--accent)">📍 ${report.symbol}</span>` : ""}
        ${report.timeframe ? `<span style="font-size:10px;padding:2px 7px;border-radius:20px;background:rgba(88,166,255,.12);color:var(--accent)">⏱ ${report.timeframe}</span>` : ""}
        ${report.pattern ? `<span style="font-size:10px;padding:2px 7px;border-radius:20px;background:rgba(188,140,255,.12);color:var(--purple)">🕯 ${report.pattern}</span>` : ""}
      </div>
      ${report.reason ? `<div style="font-size:11px;color:var(--text2);line-height:1.5;margin-bottom:8px">${report.reason}</div>` : ""}
      <div style="margin-bottom:4px">
        <div style="display:flex;justify-content:space-between;font-size:10px;color:var(--text2);margin-bottom:3px">
          <span>Confidence</span><span>${confidence}%</span>
        </div>
        <div style="height:4px;background:var(--bg3);border-radius:2px;overflow:hidden">
          <div style="height:100%;width:${confidence}%;background:${sigColor};border-radius:2px;transition:width .4s"></div>
        </div>
      </div>
    </div>`;

  // Bias summary
  if (ind.overall_bias) {
    const biasColor = bias === "bullish" ? "var(--green)" : bias === "bearish" ? "var(--red)" : "var(--yellow)";
    html += `
    <div style="background:var(--bg3);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px 10px;margin-bottom:8px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
        <span style="font-size:10px;color:var(--text2)">Overall bias</span>
        <span style="font-size:11px;font-weight:600;color:${biasColor}">${bias.toUpperCase()}</span>
      </div>
      <div style="display:flex;gap:8px;font-size:11px">
        <span style="color:var(--green)">↑${ind.bull_count||0}</span>
        <span style="color:var(--red)">↓${ind.bear_count||0}</span>
        <span style="color:var(--text3)">→${ind.neutral_count||0}</span>
      </div>
    </div>`;
  }

  // Indicator groups
  if (Object.keys(groups).length) {
    const groupEmoji = {momentum:"⚡",trend:"📈",volume:"📊",volatility:"🌊"};
    const groupLabel = {momentum:"Momentum",trend:"Trend",volume:"Volume",volatility:"Volatility"};
    Object.entries(groups).forEach(([grp, items]) => {
      const bull = Object.values(items).filter(i => i.signal === "bullish").length;
      const bear = Object.values(items).filter(i => i.signal === "bearish").length;
      html += `
      <div style="background:var(--bg3);border:1px solid var(--border);border-radius:var(--radius-sm);margin-bottom:6px;overflow:hidden">
        <div style="display:flex;justify-content:space-between;align-items:center;padding:7px 10px;cursor:pointer" onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display==='none'?'block':'none'">
          <span style="font-size:11px;font-weight:600">${groupEmoji[grp]||"•"} ${groupLabel[grp]||grp}</span>
          <span style="font-size:10px;color:var(--text2)"><span style="color:var(--green)">↑${bull}</span> <span style="color:var(--red)">↓${bear}</span></span>
        </div>
        <div style="display:none;padding:0 10px 8px">
          ${Object.entries(items).map(([n, d]) => {
            const dotColor = d.signal === "bullish" ? "var(--green)" : d.signal === "bearish" ? "var(--red)" : "var(--text3)";
            return `<div style="display:flex;justify-content:space-between;align-items:center;padding:3px 0;border-bottom:1px solid var(--border)">
              <span style="font-size:10px;color:var(--text2)">${d.display||n}</span>
              <div style="display:flex;align-items:center;gap:6px">
                <span style="font-size:10px;color:var(--text)">${d.value != null ? Number(d.value).toFixed(d.value > 100 ? 1 : 4) : "—"}</span>
                <div style="width:6px;height:6px;border-radius:50%;background:${dotColor}"></div>
              </div>
            </div>`;
          }).join("")}
        </div>
      </div>`;
    });
  }

  // Patterns detected
  const patterns = report.patterns || [];
  if (patterns.length) {
    html += `<div style="font-size:10px;font-weight:600;color:var(--text3);text-transform:uppercase;letter-spacing:.05em;margin:8px 0 4px">Patterns detected</div>
    <div style="background:var(--bg3);border:1px solid var(--border);border-radius:var(--radius-sm);padding:6px 10px;margin-bottom:8px">
      ${patterns.map(p => {
        const name = (p.name || p).toString().replace(/_/g, " ");
        const bull = p.bullish !== undefined ? p.bullish : true;
        return `<div style="display:flex;justify-content:space-between;align-items:center;padding:3px 0">
          <span style="font-size:11px">${name}</span>
          <span style="font-size:10px;color:${bull ? "var(--green)" : "var(--red)"}">${bull ? "↑ Bull" : "↓ Bear"}${p.confidence ? " · " + p.confidence + "%" : ""}</span>
        </div>`;
      }).join("")}
    </div>`;
  }

  // Key levels
  const levels = report.levels || [];
  if (levels.length) {
    html += `<div style="font-size:10px;font-weight:600;color:var(--text3);text-transform:uppercase;letter-spacing:.05em;margin:4px 0">Key levels</div>
    <div style="background:var(--bg3);border:1px solid var(--border);border-radius:var(--radius-sm);padding:6px 10px">
      ${levels.map(lv => `
        <div style="display:flex;justify-content:space-between;align-items:center;padding:3px 0">
          <span style="font-size:10px;color:var(--text2)">${lv.type}</span>
          <span style="font-size:11px;font-family:monospace">${Number(lv.price).toFixed(5)}</span>
        </div>`).join("")}
    </div>`;
  }

  return html;
}

// ── Chat tab ──────────────────────────────────────────────────────────────────
function initChatTab() {
  document.getElementById("btn-chat-send").addEventListener("click", sendChatMessage);
  document.getElementById("chat-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") sendChatMessage();
  });
}

async function sendChatMessage() {
  const input = document.getElementById("chat-input");
  const msg = input.value.trim();
  if (!msg) return;
  if (!state.token) { alert("Set your API token first."); return; }

  input.value = "";
  addChatMessage("user", msg);

  // Add to history
  state.chatHistory.push({ role: "user", content: msg });

  const sendBtn = document.getElementById("btn-chat-send");
  sendBtn.disabled = true;

  chrome.runtime.sendMessage({
    type: "SEND_CHAT_MESSAGE",
    message: msg,
    screenshotId: state.lastScreenshotId,
    history: state.chatHistory,
    token: state.token,
  }, (r) => {
    sendBtn.disabled = false;
    if (r?.ok === false) {
      addChatMessage("ai", "Error: " + (r.error || "Could not reach backend."));
      return;
    }
    const reply = r.reply || r.message || "No response.";
    addChatMessage("ai", reply);
    state.chatHistory.push({ role: "assistant", content: reply });
  });
}

function addChatMessage(role, text) {
  const area = document.getElementById("chat-area");
  const div = document.createElement("div");
  div.className = `chat-msg ${role}`;
  div.textContent = text;
  area.appendChild(div);
  area.scrollTop = area.scrollHeight;
}

// ── News tab ──────────────────────────────────────────────────────────────────
// ── News tab — real trader RSS feed ──────────────────────────────────────────
const NEWS_FEEDS = [
  { url: "https://www.forexlive.com/feed/news",          tag: "forex",  label: "ForexLive" },
  { url: "https://www.dailyfx.com/feeds/all",            tag: "forex",  label: "DailyFX" },
  { url: "https://cointelegraph.com/rss",                tag: "crypto", label: "CoinTelegraph" },
  { url: "https://feeds.content.dowjones.io/public/rss/mw_realtimeheadlines", tag: "macro", label: "MarketWatch" },
  { url: "https://www.investing.com/rss/news.rss",       tag: "macro",  label: "Investing.com" },
  { url: "https://www.fxstreet.com/rss/news",            tag: "forex",  label: "FXStreet" },
];

let _newsItems = [];
let _newsFilter = "all";

function setNewsFilter(filter, el) {
  _newsFilter = filter;
  document.querySelectorAll(".chip").forEach(c => c.classList.remove("active"));
  el.classList.add("active");
  renderNewsFeed();
}

function initNewsTab() {
  loadNewsFeed();
}

async function loadNewsFeed() {
  const el = document.getElementById("news-feed");
  if (!el) return;
  el.innerHTML = `<div style="text-align:center;color:var(--text3);font-size:12px;padding:20px">Loading news…</div>`;

  const proxy = "https://api.allorigins.win/get?url=";
  const results = [];

  await Promise.allSettled(NEWS_FEEDS.map(async feed => {
    try {
      const res = await fetch(proxy + encodeURIComponent(feed.url));
      const data = await res.json();
      const parser = new DOMParser();
      const xml = parser.parseFromString(data.contents, "text/xml");
      const items = Array.from(xml.querySelectorAll("item")).slice(0, 8);
      items.forEach(item => {
        const title = item.querySelector("title")?.textContent?.trim();
        const link  = item.querySelector("link")?.textContent?.trim();
        const pubDate = item.querySelector("pubDate")?.textContent?.trim();
        const desc  = item.querySelector("description")?.textContent?.replace(/<[^>]*>/g,"").trim().slice(0,120);
        if (title) results.push({ title, link, desc, tag: feed.tag, source: feed.label,
          ts: pubDate ? new Date(pubDate).getTime() : Date.now() });
      });
    } catch {}
  }));

  // Sort newest first
  _newsItems = results.sort((a, b) => b.ts - a.ts);
  renderNewsFeed();
}

function renderNewsFeed() {
  const el = document.getElementById("news-feed");
  if (!el) return;
  const items = _newsFilter === "all" ? _newsItems : _newsItems.filter(i => i.tag === _newsFilter);
  if (!items.length) {
    el.innerHTML = `<div style="text-align:center;color:var(--text3);font-size:12px;padding:20px">No news loaded. Check your connection.</div>`;
    return;
  }
  el.innerHTML = items.map(i => `
    <div class="news-item" onclick="openNewsLink('${encodeURIComponent(i.link)}')">
      <div class="news-title">${i.title}</div>
      ${i.desc ? `<div style="font-size:10px;color:var(--text3);margin:3px 0;line-height:1.4">${i.desc}…</div>` : ""}
      <div class="news-meta">
        <span class="news-tag">${i.tag}</span>
        <span>${i.source}</span>
        <span>${timeAgo(i.ts)}</span>
      </div>
    </div>`).join("");
}

function openNewsLink(encodedUrl) {
  const url = decodeURIComponent(encodedUrl);
  if (chrome?.tabs?.create) {
    chrome.tabs.create({ url });
  } else {
    window.open(url, "_blank");
  }
}

function timeAgo(ts) {
  const mins = Math.floor((Date.now() - ts) / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs/24)}d ago`;
}

async function analyseSelectedNews() {
  const symbol = (document.getElementById("news-symbol")?.value || "").trim() || "EURUSD";
  // Get selected text from the page
  let selectedText = "";
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const res = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => window.getSelection()?.toString() || "",
    });
    selectedText = res?.[0]?.result || "";
  } catch {}

  if (!selectedText && _newsItems.length) {
    // Use latest headline if nothing selected
    selectedText = _newsItems[0].title;
  }
  if (!selectedText) { alert("Select a news headline on the page first."); return; }

  const el = document.getElementById("news-result");
  if (!el) return;
  el.style.display = "block";
  el.innerHTML = `<span style="color:var(--text3)">⏳ Analysing impact on ${symbol}…</span>`;

  try {
    const result = await apiPost("/api/news/analyze", { text: selectedText, symbol,
      token: state.token, telegram_id: state.telegramId });
    el.innerHTML = `<strong style="color:var(--accent)">${symbol} Impact</strong><br>
      <span style="font-size:10px;color:var(--text3);font-style:italic">"${selectedText.slice(0,100)}…"</span><br><br>
      ${result.analysis || result.message || "No data."}`;
  } catch(e) {
    el.innerHTML = `<span style="color:var(--red)">Error: ${e.message}</span>`;
  }
}

// ── Settings tab ──────────────────────────────────────────────────────────────
function initSettingsTab() {
  renderSettingsValues();

  document.getElementById("btn-set-tgid").addEventListener("click", async () => {
    const val = prompt("Enter your Telegram User ID:", state.telegramId || "");
    if (val && /^\d+$/.test(val.trim())) {
      state.telegramId = val.trim();
      await saveSettings();
      renderSettingsValues();
      loadPlanBanner();
      loadStats();
    }
  });

  document.getElementById("btn-set-token").addEventListener("click", async () => {
    const val = prompt("Enter your ATV API token:\n\nGet it from:\n• Telegram bot → /tokens\n• Mini App → Profile tab → Tokens", state.token || "");
    if (val?.trim()) {
      state.token = val.trim();
      await saveSettings();
      renderSettingsValues();
    }
  });

  document.getElementById("btn-set-backend").addEventListener("click", async () => {
    const val = prompt("Backend URL:", state.backendUrl);
    if (val?.trim()) {
      state.backendUrl = val.trim().replace(/\/$/, "");
      await saveSettings();
      renderSettingsValues();
    }
  });

  document.getElementById("btn-manage-sub").addEventListener("click", () => openWhop("pro"));
  document.getElementById("btn-affiliate").addEventListener("click", async () => {
    try {
      const r = await apiGet("/api/affiliate/link");
      chrome.tabs.create({ url: r.url });
    } catch(e) {
      chrome.tabs.create({ url: `https://whop.com/affiliate?ref=${state.telegramId || ""}` });
    }
  });

  document.getElementById("btn-clear-history").addEventListener("click", async () => {
    if (!confirm("Clear all local history?")) return;
    await chrome.storage.local.remove(["newsHistory"]);
    state.chatHistory = [];
    document.getElementById("chat-area").innerHTML = '<div class="chat-empty" id="chat-empty">Take a screenshot first, then ask questions about the chart.</div>';
    renderNewsHistory([]);
  });
}

function renderSettingsValues() {
  document.getElementById("setting-tg-id").textContent = state.telegramId || "Not set";
  document.getElementById("setting-token").textContent = state.token ? state.token.slice(0, 8) + "…" : "Not set";
  document.getElementById("setting-backend").textContent = state.backendUrl;
}

// ── Stats ─────────────────────────────────────────────────────────────────────
async function loadStats() {
  if (!state.token && !state.telegramId) return;
  try {
    const stats = await apiGet("/api/user/stats");
    const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
    set("stat-validations", stats.validations ?? "—");
    set("stat-accuracy",    stats.accuracy ? `${stats.accuracy}%` : "—");
    set("stat-generations", stats.generations ?? "—");
  } catch (e) { /* silent */ }
}

// ── Messages from background ──────────────────────────────────────────────────
function listenFromBackground() {
  chrome.runtime.onMessage.addListener((msg) => {
    switch (msg.type) {
      case "AUTO_ANALYSIS_RESULT":
        showAnalysisResult(msg.result);
        break;
      case "MONITORING_STOPPED":
        setMonitorActive(false);
        break;
      case "MONITORING_ERROR":
        addChatMessage("system", "⚠️ Monitoring error: " + msg.error);
        break;
      case "MONITORING_TICK":
        addChatMessage("system", `⏱ Candle closed (${msg.timeframe}) — capturing chart...`);
        break;
      case "NEWS_TEXT_SELECTED":
        handleNewsSelection(msg.text, msg.symbol);
        break;
    }
  });
}

async function handleNewsSelection(text, detectedSymbol) {
  const symbol = document.getElementById("news-symbol").value.trim().toUpperCase()
    || (detectedSymbol || "").toUpperCase()
    || "UNKNOWN";

  document.getElementById("news-symbol").value = symbol;
  addChatMessage("system", `📰 Analysing news impact on ${symbol}…`);

  if (!state.token) { alert("Set API token in Settings first."); return; }

  chrome.runtime.sendMessage({
    type: "ANALYZE_NEWS",
    text,
    symbol,
    token: state.token,
  }, (r) => {
    if (r?.ok === false) {
      alert("News analysis error: " + (r.error || "unknown"));
      return;
    }
    showNewsResult({ ...r, symbol }, text);
  });
}

// ── Mini App opener ───────────────────────────────────────────────────────────
function openMiniApp(section) {
  const base = state.backendUrl + "/app";
  chrome.tabs.create({ url: `${base}#${section}` });
}

// ── API helpers ───────────────────────────────────────────────────────────────
async function apiGet(path) {
  const headers = {};
  if (state.token)      headers["X-ATV-Token"]        = state.token;
  if (state.telegramId) headers["X-Telegram-User-Id"] = state.telegramId;
  const res = await fetch(state.backendUrl + path, { headers });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function apiPost(path, body) {
  const headers = { "Content-Type": "application/json" };
  if (state.token)      headers["X-ATV-Token"]        = state.token;
  if (state.telegramId) headers["X-Telegram-User-Id"] = state.telegramId;
  const res = await fetch(state.backendUrl + path, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

// ── App sub-tab navigation ─────────────────────────────────────────────────────

function switchSubTab(el, name) {
  document.querySelectorAll(".app-sub-tab").forEach(t => {
    t.classList.remove("active");
    t.style.color = "var(--text3)";
    t.style.borderBottomColor = "transparent";
  });
  document.querySelectorAll(".app-sub-panel").forEach(p => { p.style.display = "none"; p.classList.remove("active"); });
  el.classList.add("active");
  el.style.color = "var(--accent)";
  el.style.borderBottomColor = "var(--accent)";
  const panel = document.getElementById(`subtab-${name}`);
  if (panel) { panel.style.display = "block"; panel.classList.add("active"); }
  if (name === "validator") { extRenderPatterns(); extLoadValidationHistory(); }
  if (name === "ea") extLoadEAHistory();
  if (name === "builder") extLoadProjects();
  if (name === "market") extLoadMarket();
}

// ── Extension: Indicator Validator ────────────────────────────────────────────

const EXT_PATTERNS = [
  { name: "bullish_engulfing", label: "Bullish Engulfing", emoji: "🟢" },
  { name: "bearish_engulfing", label: "Bearish Engulfing", emoji: "🔴" },
  { name: "doji",              label: "Doji",              emoji: "➕" },
  { name: "hammer",            label: "Hammer",            emoji: "🔨" },
  { name: "shooting_star",     label: "Shooting Star",     emoji: "💫" },
  { name: "morning_star",      label: "Morning Star",      emoji: "🌅" },
  { name: "evening_star",      label: "Evening Star",      emoji: "🌆" },
  { name: "three_white_soldiers", label: "3 White Soldiers", emoji: "🪖" },
  { name: "three_black_crows",    label: "3 Black Crows",    emoji: "🦅" },
];

let _extEnabledPatterns = new Set(EXT_PATTERNS.map(p => p.name));
let _extToken = null;

async function extRenderPatterns() {
  const el = document.getElementById("ext-pattern-list");
  if (!el) return;

  // Try to load saved preferences from backend
  try {
    if (state.token && !_extToken) _extToken = state.token;
    const r = await apiGet("/api/patterns");
    if (r.preferences) {
      r.preferences.forEach(p => { if (!p.enabled) _extEnabledPatterns.delete(p.name); });
    }
  } catch(e) { /* use defaults */ }

  el.innerHTML = EXT_PATTERNS.map(p => {
    const on = _extEnabledPatterns.has(p.name);
    return `<div style="display:flex;align-items:center;gap:8px;padding:5px 0;border-bottom:1px solid var(--border)">
      <span style="font-size:13px">${p.emoji}</span>
      <span style="flex:1;font-size:12px;color:var(--text)">${p.label}</span>
      <label style="position:relative;width:30px;height:16px;cursor:pointer">
        <input type="checkbox" ${on ? "checked" : ""} onchange="extTogglePattern('${p.name}',this.checked)"
          style="opacity:0;width:100%;height:100%;position:absolute;cursor:pointer;margin:0">
        <span style="position:absolute;inset:0;background:${on ? "var(--accent)" : "var(--bg3)"};border-radius:8px;transition:.2s"></span>
        <span style="position:absolute;top:2px;${on ? "right:2px" : "left:2px"};width:12px;height:12px;background:#fff;border-radius:50%;transition:.2s"></span>
      </label>
    </div>`;
  }).join("");
}

function extTogglePattern(name, enabled) {
  if (enabled) _extEnabledPatterns.add(name); else _extEnabledPatterns.delete(name);
  apiPost(`/api/patterns/${name}`, { enabled }).catch(() => {});
}

const EXT_PLATFORM_DATA = {
  tradingview:  { steps: "1. Open indicator → Edit → Alerts tab\n2. Set Webhook URL above\n3. Paste JSON template into Message body", template: t => ({ token: t, ticker: "{{ticker}}", close: "{{close}}", timeframe: "{{interval}}", platform: "tradingview" }) },
  metatrader:   { steps: "1. Download ATV_Analyzer.mq5 from EA Analyser tab\n2. Set UserToken in EA inputs\n3. Allow WebRequest in Tools → Options", template: t => ({ token: t, ticker: "SYMBOL", platform: "metatrader" }) },
  matchtrader:  { steps: "1. Go to Alerts → Webhook\n2. Paste your webhook URL\n3. Use JSON template as payload body", template: t => ({ token: t, ticker: "{{symbol}}", platform: "matchtrader" }) },
  ctrader:      { steps: "1. Download ATV_Analyzer.cs from EA Analyser tab\n2. Set UserToken in cBot parameters\n3. Deploy from cAlgo", template: t => ({ token: t, ticker: "SYMBOL", platform: "ctrader" }) },
  daxtrader:    { steps: "1. Go to Automation → Webhooks\n2. Create webhook with URL above\n3. Use JSON template as payload", template: t => ({ token: t, ticker: "{{instrument}}", platform: "daxtrader" }) },
  takeprofit:   { steps: "1. Bots → Webhook trigger\n2. Paste webhook URL\n3. Set Content-Type: application/json", template: t => ({ token: t, ticker: "{{symbol}}", platform: "takeprofit" }) },
};

async function extSelectPlatform(platform) {
  if (!platform) return;
  const box = document.getElementById("ext-webhook-box");
  if (!box) return;

  // Get token
  let token = state.token || "—";
  try {
    const r = await apiGet("/api/user/tokens");
    token = r.indicator || r.screenshot || token;
  } catch(e) {}

  const pd = EXT_PLATFORM_DATA[platform];
  if (!pd) return;

  const url = `${state.backendUrl}/webhook/indicator/${token}`;
  document.getElementById("ext-webhook-url").textContent = url;
  document.getElementById("ext-json-template").textContent = JSON.stringify(pd.template(token), null, 2);
  document.getElementById("ext-platform-steps").innerHTML = pd.steps.replace(/\n/g, "<br>");
  box.style.display = "block";
}

function extCopyWebhook() {
  const url = document.getElementById("ext-webhook-url").textContent;
  navigator.clipboard.writeText(url).then(() => {
    const btn = document.querySelector('[onclick="extCopyWebhook()"]');
    if (btn) { btn.textContent = "Copied!"; setTimeout(() => btn.textContent = "Copy", 1500); }
  });
}

async function extLoadValidationHistory() {
  const el = document.getElementById("ext-validation-list");
  if (!el) return;
  try {
    const r = await apiGet("/api/validations/history?limit=5");
    const vals = r.validations || [];
    if (!vals.length) {
      el.innerHTML = '<div style="color:var(--text2);font-size:11px;text-align:center;padding:10px">No signals yet</div>';
      return;
    }
    el.innerHTML = vals.map(v => {
      const vc = v.verdict === "CONFIRMED" ? "var(--green)" : v.verdict === "REJECTED" ? "var(--red)" : "var(--text2)";
      const ve = v.verdict === "CONFIRMED" ? "✅" : v.verdict === "REJECTED" ? "❌" : "⚠️";
      const conf = v.confidence ? ` · ${(v.confidence * 100).toFixed(0)}%` : "";
      return `<div style="background:var(--bg2);border-radius:4px;padding:7px 9px;margin-bottom:5px">
        <div style="display:flex;align-items:center;gap:6px">
          <span>${ve}</span>
          <span style="font-size:12px;font-weight:600;color:var(--text)">${v.ticker}</span>
          <span style="font-size:11px;color:var(--text2)">${v.signal || ""}</span>
          <span style="margin-left:auto;font-size:11px;font-weight:600;color:${vc}">${v.verdict || v.status}${conf}</span>
        </div>
        ${v.reason ? `<div style="font-size:10px;color:var(--text3);margin-top:3px">${v.reason.slice(0, 80)}…</div>` : ""}
      </div>`;
    }).join("");
  } catch(e) {
    el.innerHTML = `<div style="color:var(--text2);font-size:11px;text-align:center;padding:10px">${e.message}</div>`;
  }
}

// ── Extension: EA Analyser ─────────────────────────────────────────────────────

function extDownloadBot(platform) {
  const urls = { mt5: "/api/download/ATV_Analyzer.mq5", mt4: "/api/download/ATV_Analyzer.mq4", ctrader: "/api/download/ATV_Analyzer.cs" };
  window.open(state.backendUrl + urls[platform], "_blank");
}

async function extLoadEAHistory() {
  const el = document.getElementById("ext-ea-list");
  if (!el) return;
  try {
    const r = await apiGet("/api/ea/history?limit=5");
    const trades = r.trades || [];
    if (!trades.length) {
      el.innerHTML = '<div style="color:var(--text2);font-size:11px;text-align:center;padding:10px">No trades yet</div>';
      return;
    }
    el.innerHTML = trades.map(t => {
      const rc = t.result === "WIN" ? "var(--green)" : t.result === "LOSS" ? "var(--red)" : "var(--text2)";
      const pnl = t.pnl != null ? ` (${t.pnl >= 0 ? "+" : ""}${t.pnl.toFixed(2)})` : "";
      return `<div style="background:var(--bg2);border-radius:4px;padding:7px 9px;margin-bottom:5px">
        <div style="display:flex;align-items:center;gap:6px">
          <span style="font-size:12px;font-weight:600;color:var(--text)">${t.ea_name}</span>
          <span style="font-size:11px;color:var(--text2)">${t.ticker} ${t.action}</span>
          <span style="margin-left:auto;font-size:11px;font-weight:600;color:${rc}">${t.result}${pnl}</span>
        </div>
        ${t.analysis ? `<div style="font-size:10px;color:var(--text3);margin-top:3px">${t.analysis.slice(0, 100)}…</div>` : ""}
      </div>`;
    }).join("");
  } catch(e) {
    el.innerHTML = `<div style="color:var(--text2);font-size:11px;text-align:center;padding:10px">${e.message}</div>`;
  }
}

// ── Extension: App Builder ─────────────────────────────────────────────────────

let _extProjectId = null;

function extAgreeChanged(checked) {
  const body = document.getElementById("ext-builder-body");
  if (body) { body.style.opacity = checked ? "1" : ".4"; body.style.pointerEvents = checked ? "auto" : "none"; }
  if (checked) extLoadProjects();
}

async function extLoadProjects() {
  const el = document.getElementById("ext-projects-list");
  if (!el) return;
  try {
    const r = await apiGet("/api/appbuilder/projects");
    const projects = r.projects || [];
    if (!projects.length) {
      el.innerHTML = '<div style="color:var(--text2);font-size:11px;text-align:center;padding:8px">No projects yet</div>';
      return;
    }
    el.innerHTML = projects.map(p => {
      const lang = (p.language || p.platform || "MQL5").toUpperCase();
      return `<div style="background:var(--bg2);border-radius:4px;padding:7px 9px;margin-bottom:4px;cursor:pointer;display:flex;align-items:center;gap:8px" onclick="extOpenProject('${p.id}','${p.name}')">
        <div style="flex:1"><div style="font-size:12px;font-weight:600;color:var(--text)">${p.name}</div>
        <div style="font-size:10px;color:var(--text3)">${lang} · ${p.total_steps || 0} steps</div></div>
        <span style="font-size:10px;color:var(--text3)">${p.status || "building"}</span>
      </div>`;
    }).join("");
  } catch(e) {
    el.innerHTML = `<div style="color:var(--text2);font-size:11px;text-align:center;padding:8px">${e.message}</div>`;
  }
}

function extOpenProject(id, name) {
  _extProjectId = id;
  const chat = document.getElementById("ext-build-chat");
  if (chat) {
    chat.style.display = "block";
    document.getElementById("ext-build-messages").innerHTML =
      `<div style="font-size:11px;color:var(--text2)">📁 "${name}" — type your next instruction</div>`;
  }
}

async function extNewProject() {
  const name = prompt("Project name:");
  const desc = prompt("What should it do? (brief description):");
  if (!name || !desc) return;
  const lang = document.getElementById("ext-build-lang")?.value || "mql5";
  try {
    const r = await apiPost("/api/appbuilder/projects", { name, description: desc, language: lang });
    _extProjectId = r.project_id || r.id;
    await extLoadProjects();
    const chat = document.getElementById("ext-build-chat");
    if (chat) {
      chat.style.display = "block";
      document.getElementById("ext-build-messages").innerHTML =
        `<div style="font-size:11px;color:var(--text2)">🤖 Project "${name}" created. Tell me what to build first.</div>`;
    }
  } catch(e) { alert("Error: " + e.message); }
}

async function extSendBuildMsg() {
  const input = document.getElementById("ext-build-input");
  const msg = input?.value.trim();
  if (!msg || !_extProjectId) return;
  input.value = "";
  const msgs = document.getElementById("ext-build-messages");
  const userDiv = document.createElement("div");
  userDiv.style.cssText = "font-size:11px;color:var(--text);text-align:right;margin:4px 0";
  userDiv.textContent = msg;
  msgs.appendChild(userDiv);

  const aiDiv = document.createElement("div");
  aiDiv.style.cssText = "font-size:11px;color:var(--text2);margin:4px 0";
  aiDiv.textContent = "⏳ Building…";
  msgs.appendChild(aiDiv);
  msgs.scrollTop = msgs.scrollHeight;

  try {
    const r = await apiPost(`/api/appbuilder/projects/${_extProjectId}/build`, { message: msg });
    aiDiv.textContent = r.agent_notes || r.plan || "Step complete.";
    if (r.warnings?.length) r.warnings.forEach(w => {
      const wd = document.createElement("div");
      wd.style.cssText = "font-size:10px;color:var(--yellow);margin:2px 0";
      wd.textContent = "⚠️ " + w;
      msgs.appendChild(wd);
    });
  } catch(e) { aiDiv.textContent = "Error: " + e.message; }
  msgs.scrollTop = msgs.scrollHeight;
}

// ── Extension: Marketplace ────────────────────────────────────────────────────

async function extLoadMarket() {
  const el = document.getElementById("ext-market-list");
  if (!el) return;
  el.innerHTML = '<div style="color:var(--text2);font-size:11px;text-align:center;padding:12px">Loading…</div>';
  try {
    const r = await apiGet("/api/marketplace?limit=20");
    const listings = r.listings || [];
    if (!listings.length) {
      el.innerHTML = '<div style="color:var(--text2);font-size:11px;text-align:center;padding:12px">No listings yet</div>';
      return;
    }
    el.innerHTML = listings.map(l => {
      const price = l.listing_type === "free" ? "Free" : l.listing_type === "rent" ? `$${l.price_usd}/mo` : `$${l.price_usd}`;
      const btn = l.listing_type === "free" ? "Download" : l.listing_type === "rent" ? "Rent" : "Buy";
      return `<div style="background:var(--bg2);border-radius:4px;padding:8px 9px;margin-bottom:5px">
        <div style="display:flex;align-items:center;gap:6px;margin-bottom:3px">
          <span style="font-size:13px">${l.icon || "📦"}</span>
          <span style="font-size:12px;font-weight:600;color:var(--text);flex:1">${l.name}</span>
          <span style="font-size:11px;color:var(--accent)">${price}</span>
        </div>
        <div style="font-size:10px;color:var(--text3);margin-bottom:5px">${l.description || ""}</div>
        <button class="btn btn-sm" style="padding:3px 10px;font-size:10px" onclick="extBuyListing('${l.id}','${l.listing_type}')">${btn}</button>
      </div>`;
    }).join("");
  } catch(e) {
    el.innerHTML = `<div style="color:var(--text2);font-size:11px;text-align:center;padding:12px">${e.message}</div>`;
  }
}

async function extBuyListing(id, type) {
  if (type === "free") { alert("Download starting…"); return; }
  try {
    const r = await apiGet(`/api/checkout/marketplace?listing_id=${id}`);
    if (r.checkout_url) window.open(r.checkout_url, "_blank");
  } catch(e) { alert("Checkout: " + e.message); }
}
