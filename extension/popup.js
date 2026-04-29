/**
 * popup.js — AI Trade Validator Extension
 *
 * Flow:
 *   Step 1: Capture TradingView chart screenshot
 *   Step 2: Confirm ticker / signal / price
 *   Step 3: Submit → poll → display result
 */

"use strict";

// ── Constants ─────────────────────────────────────────────────────────────────
const DEFAULT_API_URL  = "";  // Set via Settings or Onboarding page
const DEFAULT_BOT_NAME = "";  // Set via Settings or Onboarding page
const POLL_INTERVAL_MS = 2000;
const MAX_POLL_ATTEMPTS = 60;   // 2 min max

// Progress messages shown during polling
const PROGRESS_STAGES = [
  { at:  0, msg: "Queuing analysis…" },
  { at:  5, msg: "Running OpenTrade.ai technical analysis…" },
  { at: 15, msg: "Calculating RSI, MACD, Bollinger Bands…" },
  { at: 25, msg: "Consulting RAGFlow knowledge base…" },
  { at: 35, msg: "Checking your personal trading rules…" },
  { at: 45, msg: "Comparing with historical patterns…" },
  { at: 55, msg: "Generating confidence score…" },
  { at: 65, msg: "Finalising verdict…" },
  { at: 75, msg: "Almost there…" },
];

// ── State ─────────────────────────────────────────────────────────────────────
let state = {
  screenshot:    null,   // base64 data URL
  requestId:     null,
  pollTimer:     null,
  pollAttempts:  0,
  description:   "",    // user's optional notes
  settings: {
    apiUrl:      DEFAULT_API_URL,
    botName:     DEFAULT_BOT_NAME,
    userId:      null,
  },
};

// ── DOM references ────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", async () => {
  await loadSettings();
  await checkCurrentTab();
  bindEvents();
  checkApiConfigured();
});

function checkApiConfigured() {
  if (!state.settings.apiUrl) {
    // Show a gentle nudge to complete setup
    const warning = document.createElement("div");
    warning.id    = "setupNudge";
    warning.style.cssText = (
      "background:#3a2e1e;border:1px solid #f9e2af;border-radius:8px;"
      "padding:8px 12px;font-size:11px;color:#f9e2af;margin-bottom:10px;"
      "cursor:pointer;text-align:center;"
    );
    warning.innerHTML = "⚠️ API not configured — <strong>click to set up</strong>";
    warning.onclick   = openSettings;
    const container   = document.querySelector(".container");
    const header      = document.querySelector(".header");
    if (container && header) {
      container.insertBefore(warning, header.nextSibling);
    }
  }
}

// ── Settings ──────────────────────────────────────────────────────────────────
async function loadSettings() {
  const stored = await chrome.storage.local.get([
    "apiUrl", "botName", "userId",
  ]);

  state.settings.apiUrl  = stored.apiUrl  || DEFAULT_API_URL;
  state.settings.botName = stored.botName || DEFAULT_BOT_NAME;
  state.settings.userId  = stored.userId  || generateUserId();

  if (!stored.userId) {
    await chrome.storage.local.set({ userId: state.settings.userId });
  }
}

async function saveSettings() {
  const apiUrl  = $("apiUrlInput").value.trim().replace(/\/$/, "");
  const botName = $("telegramBotInput").value.trim();

  state.settings.apiUrl  = apiUrl  || DEFAULT_API_URL;
  state.settings.botName = botName || DEFAULT_BOT_NAME;

  await chrome.storage.local.set({
    apiUrl:  state.settings.apiUrl,
    botName: state.settings.botName,
  });

  showStep("step1");
  showToast("Settings saved ✓");
}

// ── Tab detection ─────────────────────────────────────────────────────────────
async function checkCurrentTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const onTV = tab?.url?.includes("tradingview.com");
  $("notTVWarning").style.display = onTV ? "none" : "block";
  $("captureBtn").disabled = !onTV;
  if (!onTV) setStatus("idle");
}

// ── Event binding ─────────────────────────────────────────────────────────────
function bindEvents() {
  // Step 1
  $("captureBtn").addEventListener("click",     captureScreenshot);
  $("recaptureBtn").addEventListener("click",   captureScreenshot);
  $("nextToStep2Btn").addEventListener("click", () => showStep("step2"));

  // Step 2
  $("backToStep1Btn").addEventListener("click", () => showStep("step1"));
  $("submitBtn").addEventListener("click",       submitAnalysis);
  $("tickerInput").addEventListener("input",     () => {
    $("tickerInput").value = $("tickerInput").value.toUpperCase();
  });
  $("descriptionInput").addEventListener("input", () => {
    const len = $("descriptionInput").value.length;
    $("charCount").textContent = len;
    $("charCount").style.color = len >= 450 ? "var(--yellow)" : len >= 490 ? "var(--red)" : "";
  });

  // Step 3
  $("openTelegramBtn").addEventListener("click", openTelegram);
  $("newAnalysisBtn").addEventListener("click",  resetToStep1);
  $("copyResultBtn").addEventListener("click",   copyResult);
  $("retryBtn").addEventListener("click",        resetToStep1);

  // Settings + History
  $("settingsLink").addEventListener("click",       openSettings);
  $("historyLink").addEventListener("click",        openHistory);
  $("cancelSettingsBtn").addEventListener("click",  () => showStep("step1"));
  $("saveSettingsBtn").addEventListener("click",    saveSettings);
}

// ── STEP 1 — Screenshot Capture ───────────────────────────────────────────────
async function captureScreenshot() {
  setStatus("loading");
  $("captureBtn").disabled = true;
  $("captureBtn").querySelector(".btn-text").textContent = "Capturing…";

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

    if (!tab.url.includes("tradingview.com")) {
      showError("step1-error", "Please navigate to a TradingView chart first.");
      resetCaptureBtn();
      return;
    }

    // Use chrome.tabs.captureVisibleTab (requires activeTab permission)
    chrome.tabs.captureVisibleTab(
      tab.windowId,
      { format: "png", quality: 95 },
      async (imageUrl) => {
        if (chrome.runtime.lastError) {
          showError("step1-error", chrome.runtime.lastError.message);
          resetCaptureBtn();
          return;
        }

        state.screenshot = imageUrl;

        // Show preview
        $("screenshotPreview").src    = imageUrl;
        $("previewContainer").style.display = "block";
        $("nextToStep2Btn").style.display   = "block";

        // Auto-detect ticker from page title + content script
        const ticker = await detectTicker(tab);
        const price  = await detectPrice(tab);

        if (ticker) {
          $("autoDetected").textContent    = `🔍 Detected: ${ticker}`;
          $("autoDetected").style.display  = "block";
          $("tickerInput").value           = ticker;
          $("tickerHint").textContent      = "Auto-detected from chart";
        }
        if (price) {
          $("priceInput").value = price;
        }

        setStatus("ready");
        resetCaptureBtn();
      }
    );
  } catch (err) {
    console.error("Capture error:", err);
    showError("step1-error", err.message);
    resetCaptureBtn();
  }
}

function resetCaptureBtn() {
  $("captureBtn").disabled = false;
  $("captureBtn").querySelector(".btn-text").textContent = "Capture TradingView Chart";
}

// ── Ticker + Price detection ──────────────────────────────────────────────────
async function detectTicker(tab) {
  try {
    // Method 1: Page title (most reliable — TradingView format: "AAPL: Apple Inc.")
    const [{ result: title }] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => document.title,
    });
    const titleMatch = title.match(/^([A-Z0-9]{1,10}(?:\.[A-Z]{1,5})?)\s*[:\-—]/);
    if (titleMatch) return titleMatch[1];

    // Method 2: Ask content script
    const resp = await chrome.tabs.sendMessage(tab.id, { type: "GET_TICKER" });
    return resp?.ticker || null;
  } catch {
    return null;
  }
}

async function detectPrice(tab) {
  try {
    const resp = await chrome.tabs.sendMessage(tab.id, { type: "GET_PRICE" });
    return resp?.price || null;
  } catch {
    return null;
  }
}

// ── STEP 2 — Submit Analysis ───────────────────────────────────────────────────
async function submitAnalysis() {
  const ticker      = $("tickerInput").value.trim().toUpperCase();
  const signal      = $("signalSelect").value;
  const price       = $("priceInput").value.trim();
  const description = $("descriptionInput").value.trim();
  state.description = description;

  // Validation
  if (!ticker) {
    $("tickerInput").classList.add("input-error");
    $("tickerHint").textContent = "Ticker is required";
    $("tickerHint").classList.add("hint-error");
    $("tickerInput").focus();
    return;
  }
  if (!/^[A-Z0-9.]{1,12}$/.test(ticker)) {
    $("tickerInput").classList.add("input-error");
    $("tickerHint").textContent = "Invalid ticker format";
    $("tickerHint").classList.add("hint-error");
    return;
  }

  $("tickerInput").classList.remove("input-error");
  $("tickerHint").classList.remove("hint-error");

  // Switch to step 3 loading
  showStep("step3");
  showLoading();
  setStatus("loading");
  startProgressAnimation();

  try {
    // Convert base64 screenshot to Blob
    const resp     = await fetch(state.screenshot);
    const blob     = await resp.blob();

    const formData = new FormData();
    formData.append("screenshot",   blob, "chart.png");
    formData.append("ticker",       ticker);
    formData.append("signal",       signal);
    formData.append("price",        price || "");
    formData.append("description",  description || "");
    formData.append("user_id",      state.settings.userId);

    const apiResp = await fetch(
      `${state.settings.apiUrl}/webhook/screenshot`,
      { method: "POST", body: formData }
    );

    if (!apiResp.ok) {
      const err = await apiResp.json().catch(() => ({ error: "Server error" }));
      throw new Error(err.error || `HTTP ${apiResp.status}`);
    }

    const { request_id } = await apiResp.json();
    state.requestId = request_id;

    // Begin polling
    state.pollAttempts = 0;
    state.pollTimer = setInterval(() => pollForResult(request_id), POLL_INTERVAL_MS);

  } catch (err) {
    console.error("Submit error:", err);
    stopProgressAnimation();
    showErrorState(err.message || "Submission failed. Check your API URL in Settings.");
  }
}

// ── Polling ───────────────────────────────────────────────────────────────────
async function pollForResult(requestId) {
  state.pollAttempts++;

  if (state.pollAttempts > MAX_POLL_ATTEMPTS) {
    clearInterval(state.pollTimer);
    stopProgressAnimation();
    showErrorState("Analysis timed out after 2 minutes. Check Telegram for results.");
    return;
  }

  try {
    const resp = await fetch(
      `${state.settings.apiUrl}/webhook/screenshot/result/${requestId}`
    );
    if (!resp.ok) return; // transient error — keep polling

    const data = await resp.json();

    if (data.status === "completed") {
      clearInterval(state.pollTimer);
      stopProgressAnimation();
      displayResult(data);

      // Save to history
      await saveToHistory(requestId, data);

      // Notify background
      chrome.runtime.sendMessage({ type: "analysis_complete" });
    }

    if (data.status === "failed") {
      clearInterval(state.pollTimer);
      stopProgressAnimation();
      showErrorState(data.error || "Analysis failed. Please try again.");
    }

  } catch {
    // Network hiccup — keep polling silently
  }
}

// ── Display Result ────────────────────────────────────────────────────────────
function displayResult(data) {
  const verdict    = (data.verdict    || "CAUTION").toUpperCase();
  const confidence = Math.round((data.confidence_score || data.confidence || 0.5) * 100);
  const reasoning  = data.reasoning  || data.final_message || "Analysis complete.";
  const indicators = data.trader_analysis || {};

  // Verdict badge
  const verdictConfig = {
    CONFIRM: { emoji: "✅", label: "CONFIRM",  cls: "confirm" },
    CAUTION: { emoji: "⚠️", label: "CAUTION",  cls: "caution" },
    REJECT:  { emoji: "❌", label: "REJECT",   cls: "reject"  },
  };
  const vc = verdictConfig[verdict] || verdictConfig.CAUTION;

  $("verdictIcon").textContent = vc.emoji;
  $("verdictText").textContent = vc.label;
  $("verdictBadge").className  = `verdict-badge ${vc.cls}`;

  // Confidence bar (animate in)
  $("confidenceValue").textContent = `${confidence}%`;
  setTimeout(() => {
    $("confidenceFill").style.width = `${confidence}%`;
    $("confidenceFill").style.background = confidence >= 65
      ? "#a6e3a1" : confidence >= 45 ? "#f9e2af" : "#f38ba8";
  }, 100);

  // Reasoning — strip Telegram markdown, show plain text summary
  const cleanReasoning = reasoning
    .replace(/\*\*(.*?)\*\*/g, "$1")
    .replace(/\*(.*?)\*/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\n{3,}/g, "\n\n")
    .split("\n")
    .slice(0, 8)
    .join("\n")
    .trim();
  $("reasoningBox").textContent = cleanReasoning;

  // Show user's notes in result if they added any
  const notes = state.description.trim();
  if (notes) {
    $("userNotesText").textContent     = notes;
    $("userNotesResult").style.display = "block";
  } else {
    $("userNotesResult").style.display = "none";
  }

  // Key indicators row
  const rows = [];
  if (indicators.rsi    != null) rows.push({ label: "RSI",  value: indicators.rsi.toFixed(1) });
  if (indicators.macd   != null) rows.push({ label: "MACD", value: indicators.macd.toFixed(3) });
  if (indicators.bb_position)   rows.push({ label: "BB",   value: indicators.bb_position.replace(/_/g, " ") });
  if (indicators.current_price) rows.push({ label: "Price", value: `$${indicators.current_price}` });

  if (rows.length) {
    $("indicatorRow").innerHTML = rows
      .map(r => `<div class="indicator-chip"><span class="chip-label">${r.label}</span><span class="chip-value">${r.value}</span></div>`)
      .join("");
  }

  // Show result
  $("loadingContainer").style.display = "none";
  $("resultContainer").style.display  = "block";
  $("errorContainer").style.display   = "none";
  setStatus("done");
}

// ── UI helpers ────────────────────────────────────────────────────────────────
function showStep(stepId) {
  document.querySelectorAll(".step").forEach(s => s.classList.remove("active"));
  $(stepId).classList.add("active");
}

function showLoading() {
  $("loadingContainer").style.display = "block";
  $("resultContainer").style.display  = "none";
  $("errorContainer").style.display   = "none";
}

function showErrorState(msg) {
  $("loadingContainer").style.display = "none";
  $("resultContainer").style.display  = "none";
  $("errorContainer").style.display   = "block";
  $("errorMessage").textContent       = msg;
  setStatus("idle");
}

function setStatus(s) {
  const dot = $("statusDot");
  dot.className = `status-dot ${s}`;
  dot.title = { idle: "Ready", loading: "Processing…", ready: "Screenshot captured", done: "Done" }[s] || s;
}

// Progress animation
let progressInterval = null;
function startProgressAnimation() {
  $("progressFill").style.width = "0%";
  let pct = 0;
  progressInterval = setInterval(() => {
    pct = Math.min(pct + 0.8, 90);
    $("progressFill").style.width = `${pct}%`;

    // Update label based on stage
    const stage = [...PROGRESS_STAGES].reverse().find(s => pct >= s.at / MAX_POLL_ATTEMPTS * 100);
    const attemptPct = (state.pollAttempts / MAX_POLL_ATTEMPTS) * 100;
    const stageMsg = [...PROGRESS_STAGES].reverse().find(s => attemptPct >= (s.at / MAX_POLL_ATTEMPTS));
    if (stageMsg) $("progressLabel").textContent = stageMsg.msg;
  }, 300);
}

function stopProgressAnimation() {
  clearInterval(progressInterval);
  $("progressFill").style.width = "100%";
}

// ── Actions ───────────────────────────────────────────────────────────────────
function openTelegram() {
  const botName = state.settings.botName.replace(/^@/, "");
  chrome.tabs.create({ url: `https://t.me/${botName}` });
}

function resetToStep1() {
  clearInterval(state.pollTimer);
  state.screenshot   = null;
  state.requestId    = null;
  state.pollAttempts = 0;

  $("previewContainer").style.display  = "none";
  $("nextToStep2Btn").style.display    = "none";
  $("autoDetected").style.display      = "none";
  $("tickerInput").value               = "";
  $("priceInput").value                = "";
  $("descriptionInput").value          = "";
  $("charCount").textContent           = "0";
  $("tickerHint").textContent          = "";
  $("tickerInput").classList.remove("input-error");
  state.description                    = "";

  setStatus("idle");
  showStep("step1");
}

function copyResult() {
  const verdict    = $("verdictText").textContent;
  const confidence = $("confidenceValue").textContent;
  const reasoning  = $("reasoningBox").textContent;
  const notes      = state.description.trim();
  const notesLine  = notes ? `\n\n📝 My notes: ${notes}` : "";
  const text       = `AI Trade Validator Result\nVerdict: ${verdict} (${confidence})\n\n${reasoning}${notesLine}\n\n⚠️ Not financial advice.`;

  navigator.clipboard.writeText(text).then(() => showToast("Copied ✓"));
}

function openHistory() {
  chrome.tabs.create({ url: chrome.runtime.getURL("history.html") });
}

function openSettings() {
  $("apiUrlInput").value         = state.settings.apiUrl;
  $("telegramBotInput").value    = state.settings.botName;
  $("userIdDisplay").value       = state.settings.userId;
  showStep("settingsPanel");
}

// ── History storage ───────────────────────────────────────────────────────────
async function saveToHistory(requestId, result) {
  const { analysisHistory = [] } = await chrome.storage.local.get("analysisHistory");
  analysisHistory.unshift({
    id:        requestId,
    ticker:      $("tickerInput").value,
    signal:      $("signalSelect").value,
    description: state.description || "",
    verdict:     result.verdict,
    confidence: result.confidence_score || result.confidence,
    timestamp: Date.now(),
  });
  // Keep last 50
  await chrome.storage.local.set({
    analysisHistory: analysisHistory.slice(0, 50),
    [`analysis_${requestId}`]: result,
  });
}

// ── Utilities ─────────────────────────────────────────────────────────────────
function generateUserId() {
  return "ext_" + Date.now().toString(36) + Math.random().toString(36).slice(2, 9);
}

let toastTimer = null;
function showToast(msg) {
  clearTimeout(toastTimer);
  let toast = document.getElementById("toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "toast";
    toast.className = "toast";
    document.body.appendChild(toast);
  }
  toast.textContent = msg;
  toast.classList.add("show");
  toastTimer = setTimeout(() => toast.classList.remove("show"), 2000);
}
