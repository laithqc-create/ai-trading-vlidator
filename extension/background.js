/**
 * background.js — MV3 Service Worker
 * Responsibilities:
 *   - Open side panel when toolbar icon clicked
 *   - Manage chart monitoring alarm (candle-close aware)
 *   - Receive screenshots from content.js and POST to backend
 *   - Forward analysis results back to side panel
 */

// API_BASE is read from chrome.storage.local so users can configure it in Settings.
// Default points to production; overridden at install time or via the extension settings tab.
const DEFAULT_API_BASE = "https://api.aitradevalidator.com";
let _apiBase = DEFAULT_API_BASE;

// Load the stored backend URL once at service-worker startup
(async () => {
  const { backendUrl } = await chrome.storage.local.get("backendUrl");
  if (backendUrl) _apiBase = backendUrl;
})();

// Accessor used by all fetch calls below
function getApiBase() { return _apiBase; }

// ── Open side panel on action click ──────────────────────────────────────────
chrome.action.onClicked.addListener((tab) => {
  chrome.sidePanel.open({ tabId: tab.id });
});

// ── Message router ────────────────────────────────────────────────────────────
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  switch (msg.type) {
    case "START_MONITORING":
      startMonitoring(msg.durationMinutes, msg.timeframe, msg.symbol, msg.token);
      sendResponse({ ok: true });
      break;

    case "STOP_MONITORING":
      stopMonitoring();
      sendResponse({ ok: true });
      break;

    case "TAKE_SCREENSHOT":
      takeScreenshot(msg.token, msg.symbol, msg.timeframe, msg.chatHistory || [])
        .then((r) => sendResponse(r))
        .catch((e) => sendResponse({ ok: false, error: e.message }));
      return true; // async

    case "ANALYZE_NEWS":
      analyzeNews(msg.text, msg.symbol, msg.token)
        .then((r) => sendResponse(r))
        .catch((e) => sendResponse({ ok: false, error: e.message }));
      return true;

    case "SEND_CHAT_MESSAGE":
      sendChatMessage(msg.message, msg.screenshotId, msg.history, msg.token)
        .then((r) => sendResponse(r))
        .catch((e) => sendResponse({ ok: false, error: e.message }));
      return true;
  }
});

// ── Monitoring alarm ──────────────────────────────────────────────────────────
const ALARM_NAME = "chart_monitor";

function timeframeToMinutes(tf) {
  const map = { "1m": 1, "5m": 5, "15m": 15, "1h": 60, "2h": 120, "3h": 180, "4h": 240, "1d": 1440, "1w": 10080 };
  return map[tf] || 60;
}

/**
 * Returns milliseconds until the NEXT candle close for the given timeframe.
 * Ensures screenshots fire exactly at candle close, not mid-candle.
 */
function msUntilNextCandleClose(tfMinutes) {
  const nowMs = Date.now();
  const tfMs = tfMinutes * 60 * 1000;
  const msIntoCandle = nowMs % tfMs;
  const msUntilClose = tfMs - msIntoCandle;
  // Add 2s buffer so the candle is fully closed on the charting platform
  return msUntilClose + 2000;
}

async function startMonitoring(durationMinutes, timeframe, symbol, token) {
  // Clear any existing alarm
  await chrome.alarms.clear(ALARM_NAME);

  const tfMinutes = timeframeToMinutes(timeframe);
  const endTime = Date.now() + durationMinutes * 60 * 1000;
  const firstFireDelay = msUntilNextCandleClose(tfMinutes);

  // Persist monitoring state
  await chrome.storage.local.set({
    monitoring: {
      active: true,
      timeframe,
      tfMinutes,
      symbol,
      token,
      endTime,
      startedAt: Date.now(),
    },
  });

  // Schedule first alarm at next candle close
  chrome.alarms.create(ALARM_NAME, {
    when: Date.now() + firstFireDelay,
    periodInMinutes: tfMinutes,
  });

  console.log(`[Monitor] Started: ${timeframe} on ${symbol}, ends in ${durationMinutes}min, first shot in ${Math.round(firstFireDelay/1000)}s`);
}

async function stopMonitoring() {
  await chrome.alarms.clear(ALARM_NAME);
  await chrome.storage.local.set({ monitoring: { active: false } });
  notifySidePanel({ type: "MONITORING_STOPPED" });
  console.log("[Monitor] Stopped.");
}

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name !== ALARM_NAME) return;

  const { monitoring } = await chrome.storage.local.get("monitoring");
  if (!monitoring?.active) return;

  // Check if duration has elapsed
  if (Date.now() >= monitoring.endTime) {
    await stopMonitoring();
    return;
  }

  // Trigger screenshot of the active tab
  notifySidePanel({ type: "MONITORING_TICK", timeframe: monitoring.timeframe });
  await triggerAutoScreenshot(monitoring);
});

async function triggerAutoScreenshot(monitoring) {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tabs.length) return;

  const tab = tabs[0];
  try {
    // Capture screenshot
    const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, { format: "png" });
    const blob = dataUrlToBlob(dataUrl);

    // POST to backend
    const result = await postScreenshot(blob, monitoring.token, monitoring.symbol, monitoring.timeframe, [], true);

    notifySidePanel({ type: "AUTO_ANALYSIS_RESULT", result, timeframe: monitoring.timeframe });
  } catch (e) {
    console.error("[Monitor] Screenshot error:", e);
    notifySidePanel({ type: "MONITORING_ERROR", error: e.message });
  }
}

// ── Manual screenshot (user-triggered) ───────────────────────────────────────
async function takeScreenshot(token, symbol, timeframe, chatHistory) {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tabs.length) throw new Error("No active tab found");

  const dataUrl = await chrome.tabs.captureVisibleTab(tabs[0].windowId, { format: "png" });
  const blob = dataUrlToBlob(dataUrl);
  return await postScreenshot(blob, token, symbol, timeframe, chatHistory, false);
}

// ── API calls ─────────────────────────────────────────────────────────────────
async function postScreenshot(blob, token, symbol, timeframe, chatHistory, isAuto) {
  const form = new FormData();
  form.append("screenshot", blob, "chart.png");
  form.append("symbol", symbol || "");
  form.append("timeframe", timeframe || "1h");
  form.append("is_auto", String(isAuto));
  if (chatHistory.length) form.append("chat_history", JSON.stringify(chatHistory));

  const res = await fetch(`${getApiBase()}/webhook/screenshot/${token}`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) throw new Error(`Backend error ${res.status}`);
  return await res.json();
}

async function analyzeNews(text, symbol, token) {
  const res = await fetch(`${getApiBase()}/api/news/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, symbol, token }),
  });
  if (!res.ok) throw new Error(`Backend error ${res.status}`);
  return await res.json();
}

async function sendChatMessage(message, screenshotId, history, token) {
  const res = await fetch(`${getApiBase()}/api/chart/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, screenshot_id: screenshotId, history, token }),
  });
  if (!res.ok) throw new Error(`Backend error ${res.status}`);
  return await res.json();
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function dataUrlToBlob(dataUrl) {
  const [header, data] = dataUrl.split(",");
  const mime = header.match(/:(.*?);/)[1];
  const binary = atob(data);
  const arr = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) arr[i] = binary.charCodeAt(i);
  return new Blob([arr], { type: mime });
}

function notifySidePanel(msg) {
  chrome.runtime.sendMessage(msg).catch(() => {
    // Side panel may be closed — ignore
  });
}
