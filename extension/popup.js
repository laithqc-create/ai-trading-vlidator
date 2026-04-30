/**
 * popup.js — AI Trade Validator Extension v1.1
 *
 * New 4-step flow:
 *   Step 1:  Capture screenshot
 *   Step 2:  Mode select — Validate My Analysis | AI Analyse My Chart
 *   Step 3a: Validate — user describes their setup, AI validates against market
 *   Step 3b: Analyse  — user picks patterns/categories, AI scans screenshot
 *   Step 4:  Result display
 *
 * Screenshot persists for 5 hours — user doesn't need to retake each session.
 */
"use strict";

// ── Constants ─────────────────────────────────────────────────────
const SCREENSHOT_TTL_MS = 5 * 60 * 60 * 1000;  // 5 hours
const POLL_INTERVAL_MS  = 2500;
const MAX_POLL          = 72;  // ~3 min max

const PROGRESS_STAGES = [
  { at:  0, msg: "Queuing analysis…" },
  { at:  5, msg: "Reading chart screenshot…" },
  { at: 12, msg: "Running OpenTrade.ai technical analysis…" },
  { at: 22, msg: "Calculating RSI, MACD, Bollinger Bands…" },
  { at: 32, msg: "Checking RAGFlow knowledge base…" },
  { at: 42, msg: "Matching patterns to historical data…" },
  { at: 55, msg: "Comparing against your analysis…" },
  { at: 65, msg: "Generating confidence score…" },
  { at: 75, msg: "Preparing detailed response…" },
  { at: 85, msg: "Almost done…" },
];

// Category → patterns map
const CATEGORIES = {
  smc:     ["Order Blocks","FVG","Breaker Blocks","Liquidity Sweeps","CHoCH","BOS",
             "Equal Highs/Lows","Mitigation Blocks","SMT Divergence","Turtle Soup","Silver Bullet"],
  classic: ["Head and Shoulders","Double Top","Double Bottom","Triangles",
             "Support/Resistance","Flags/Pennants","Cup and Handle","Wedges","Rounding Bottom"],
  scalper: ["Killzone Detection","Silver Bullet Setup","Micro Liquidity Sweeps",
             "Micro Order Blocks","Turtle Soup LTF","Judas Swing"],
  swing:   ["Market Structure BOS","Market Structure CHoCH","Previous Day Levels",
             "Previous Week Levels","OTE","Head and Shoulders Swing",
             "Cup and Handle Swing","AMD"],
};

// ── State ─────────────────────────────────────────────────────────
let state = {
  screenshot:    null,    // base64 data URL
  screenshotTs:  null,    // timestamp when captured
  requestId:     null,
  pollTimer:     null,
  pollAttempts:  0,
  mode:          null,    // 'validate' | 'analyse'
  description:   "",      // validate mode text
  selectedPatterns: [],   // analyse mode patterns
  activeCategory: "smc",
  settings: { apiUrl: "", botName: "", userId: null },
};

// ── DOM helper ────────────────────────────────────────────────────
const $ = id => document.getElementById(id);

// ── Init ──────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", async () => {
  await loadSettings();
  await restoreScreenshot();
  await checkCurrentTab();
  bindEvents();
  checkApiConfigured();
  initCategoryTabs();
  initPatternCheckboxes();
});

// ── Settings ──────────────────────────────────────────────────────
async function loadSettings() {
  const s = await chrome.storage.local.get(["apiUrl","botName","userId","savedScreenshot","savedScreenshotTs"]);
  state.settings.apiUrl  = s.apiUrl  || "";
  state.settings.botName = s.botName || "";
  state.settings.userId  = s.userId  || generateUserId();
  if (!s.userId) await chrome.storage.local.set({ userId: state.settings.userId });
}

async function restoreScreenshot() {
  const { savedScreenshot, savedScreenshotTs } = await chrome.storage.local.get(
    ["savedScreenshot","savedScreenshotTs"]
  );
  if (!savedScreenshot || !savedScreenshotTs) return;
  const age = Date.now() - savedScreenshotTs;
  if (age > SCREENSHOT_TTL_MS) {
    await chrome.storage.local.remove(["savedScreenshot","savedScreenshotTs"]);
    return;
  }
  // Restore from storage
  state.screenshot   = savedScreenshot;
  state.screenshotTs = savedScreenshotTs;
  $("screenshotPreview").src = savedScreenshot;
  $("previewContainer").style.display = "block";
  $("nextToStep2Btn").style.display   = "block";
  updateAgeChip();
  setStatus("ready");
}

async function saveSettings() {
  const apiUrl  = $("apiUrlInput").value.trim().replace(/\/$/, "");
  const botName = $("telegramBotInput").value.trim();
  state.settings.apiUrl  = apiUrl;
  state.settings.botName = botName;
  await chrome.storage.local.set({ apiUrl, botName });
  showStep("step1");
  showToast("Settings saved ✓");
  checkApiConfigured();
}

// ── Tab detection ─────────────────────────────────────────────────
async function checkCurrentTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const onTV  = tab?.url?.includes("tradingview.com");
  $("notTVWarning").style.display = onTV ? "none" : "block";
  $("captureBtn").disabled = !onTV;
}

function checkApiConfigured() {
  const nudge = $("setupNudge");
  nudge.style.display = state.settings.apiUrl ? "none" : "block";
}

// ── Event bindings ────────────────────────────────────────────────
function bindEvents() {
  // Step 1
  $("captureBtn").addEventListener("click",    captureScreenshot);
  $("recaptureBtn").addEventListener("click",  captureScreenshot);
  $("nextToStep2Btn").addEventListener("click", () => {
    populateStep3Thumbs();
    showStep("step2");
  });

  // Step 2
  $("backToStep1Btn").addEventListener("click", () => showStep("step1"));

  // Step 3a
  $("userAnalysisInput").addEventListener("input", () => {
    const len = $("userAnalysisInput").value.length;
    $("analysisCharCount").textContent = len;
    if (len >= 750) $("analysisCharCount").style.color = "var(--yellow)";
    else if (len >= 790) $("analysisCharCount").style.color = "var(--red)";
    else $("analysisCharCount").style.color = "";
  });
  $("tickerInput").addEventListener("input", () => {
    $("tickerInput").value = $("tickerInput").value.toUpperCase();
  });
  $("submitValidateBtn").addEventListener("click",  submitValidate);

  // Step 3b
  $("submitAnalyseBtn").addEventListener("click",   submitAnalyse);
  $("selectAllCat").addEventListener("change",      toggleSelectCategory);
  $("selectAllAll").addEventListener("change",      toggleSelectAll);

  // Step 4
  $("openTelegramBtn").addEventListener("click",    openTelegram);
  $("newAnalysisBtn").addEventListener("click",     resetToStep1);
  $("copyResultBtn").addEventListener("click",      copyResult);
  $("retryBtn").addEventListener("click",           resetToStep1);

  // Settings
  $("settingsLink").addEventListener("click", openSettings);
  $("saveSettingsBtn").addEventListener("click", saveSettings);
  $("historyLink").addEventListener("click", () =>
    chrome.tabs.create({ url: chrome.runtime.getURL("history.html") })
  );
}

// ── Category tabs ─────────────────────────────────────────────────
function initCategoryTabs() {
  document.querySelectorAll(".cat-tab").forEach(tab => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".cat-tab").forEach(t => t.classList.remove("active"));
      document.querySelectorAll(".pattern-grid").forEach(g => g.classList.remove("active-cat"));
      tab.classList.add("active");
      const cat = tab.dataset.cat;
      state.activeCategory = cat;
      $(`cat-${cat}`).classList.add("active-cat");
      // Sync select-all-cat checkbox
      $("selectAllCat").checked = isCategoryFullySelected(cat);
    });
  });
}

function initPatternCheckboxes() {
  document.querySelectorAll(".pattern-grid input[type=checkbox]").forEach(cb => {
    cb.addEventListener("change", () => {
      updateSelectedPatterns();
      updateSubmitBtn();
      updatePatternSummary();
      // Sync selectAllCat
      $("selectAllCat").checked = isCategoryFullySelected(state.activeCategory);
    });
  });
}

function isCategoryFullySelected(cat) {
  const grid = $(`cat-${cat}`);
  if (!grid) return false;
  const cbs = grid.querySelectorAll("input[type=checkbox]");
  return Array.from(cbs).every(c => c.checked);
}

function toggleSelectCategory() {
  const checked = $("selectAllCat").checked;
  const grid    = $(`cat-${state.activeCategory}`);
  grid.querySelectorAll("input[type=checkbox]").forEach(cb => { cb.checked = checked; });
  updateSelectedPatterns();
  updateSubmitBtn();
  updatePatternSummary();
}

function toggleSelectAll() {
  const checked = $("selectAllAll").checked;
  document.querySelectorAll(".pattern-grid input[type=checkbox]").forEach(cb => {
    cb.checked = checked;
  });
  $("selectAllCat").checked = checked;
  updateSelectedPatterns();
  updateSubmitBtn();
  updatePatternSummary();
}

function updateSelectedPatterns() {
  state.selectedPatterns = Array.from(
    document.querySelectorAll(".pattern-grid input[type=checkbox]:checked")
  ).map(cb => cb.value);
}

function updateSubmitBtn() {
  $("submitAnalyseBtn").disabled = state.selectedPatterns.length === 0;
  if (state.selectedPatterns.length > 0) {
    $("submitAnalyseBtn").textContent =
      `🔍 Analyse ${state.selectedPatterns.length} Pattern${state.selectedPatterns.length > 1 ? "s" : ""}`;
  } else {
    $("submitAnalyseBtn").textContent = "🔍 Run Pattern Analysis";
  }
}

function updatePatternSummary() {
  const n       = state.selectedPatterns.length;
  const summary = $("patternSummary");
  if (n === 0) { summary.style.display = "none"; return; }
  summary.style.display = "block";
  const preview = state.selectedPatterns.slice(0, 4).join(", ");
  const more    = n > 4 ? ` +${n - 4} more` : "";
  summary.textContent = `✓ ${n} selected: ${preview}${more}`;
}

// ── Mode selection ────────────────────────────────────────────────
function selectMode(mode) {
  state.mode = mode;
  document.querySelectorAll(".mode-card").forEach(c => c.classList.remove("selected"));
  $(`mode${mode.charAt(0).toUpperCase() + mode.slice(1)}`).classList.add("selected");

  if (mode === "validate") {
    showStep("step3a");
  } else {
    showStep("step3b");
  }
}

function populateStep3Thumbs() {
  const src    = state.screenshot || "";
  const ticker = $("tickerInput").value || "?";
  const signal = $("signalSelect").value || "BUY";

  ["step3aThumb","step3bThumb"].forEach(id => {
    const el = $(id);
    if (el) el.src = src;
  });
  ["step3aTicker","step3bTicker"].forEach(id => {
    const el = $(id);
    if (el) el.textContent = `${ticker} · ${signal}`;
  });
}

// ── Step 1 — Capture ─────────────────────────────────────────────
async function captureScreenshot() {
  setStatus("loading");
  $("captureBtn").disabled = true;
  $("captureBtn").querySelector(".btn-text").textContent = "Capturing…";

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

    if (!tab?.url?.includes("tradingview.com")) {
      showToast("Navigate to TradingView first");
      resetCaptureBtn();
      return;
    }

    chrome.tabs.captureVisibleTab(tab.windowId, { format: "png", quality: 95 }, async (imgUrl) => {
      if (chrome.runtime.lastError) {
        showToast("Capture failed: " + chrome.runtime.lastError.message);
        resetCaptureBtn(); return;
      }

      state.screenshot   = imgUrl;
      state.screenshotTs = Date.now();

      // Persist for 5h
      await chrome.storage.local.set({
        savedScreenshot:   imgUrl,
        savedScreenshotTs: state.screenshotTs,
      });

      $("screenshotPreview").src = imgUrl;
      $("previewContainer").style.display = "block";
      $("nextToStep2Btn").style.display   = "block";
      updateAgeChip();

      // Auto-detect ticker
      const ticker = await detectTicker(tab);
      const price  = await detectPrice(tab);
      if (ticker) {
        $("autoDetected").textContent   = `🔍 ${ticker}`;
        $("autoDetected").style.display = "block";
        $("tickerInput").value = ticker;
      }
      if (price) $("priceInput").value = price;

      setStatus("ready");
      resetCaptureBtn();
    });
  } catch (e) {
    showToast("Error: " + e.message);
    resetCaptureBtn();
  }
}

function resetCaptureBtn() {
  $("captureBtn").disabled = false;
  $("captureBtn").querySelector(".btn-text").textContent = "Capture TradingView Chart";
}

function updateAgeChip() {
  if (!state.screenshotTs) return;
  const ageMs  = Date.now() - state.screenshotTs;
  const ageMin = Math.round(ageMs / 60000);
  const chip   = $("screenshotAge");
  if (ageMin < 1)       chip.textContent = "📸 Just captured";
  else if (ageMin < 60) chip.textContent = `📸 ${ageMin}m ago`;
  else                  chip.textContent = `📸 ${Math.floor(ageMin/60)}h ${ageMin%60}m ago`;

  const ttlLeft = SCREENSHOT_TTL_MS - (Date.now() - state.screenshotTs);
  chip.style.color = ttlLeft < 30 * 60000 ? "var(--yellow)" : "";
}

// ── Ticker/price detection ────────────────────────────────────────
async function detectTicker(tab) {
  try {
    const [{ result: title }] = await chrome.scripting.executeScript({
      target: { tabId: tab.id }, func: () => document.title,
    });
    const m = title.match(/^([A-Z0-9]{1,10}(?:\.[A-Z]{1,5})?)\s*[:\-—]/);
    if (m) return m[1];
    const resp = await chrome.tabs.sendMessage(tab.id, { type: "GET_TICKER" });
    return resp?.ticker || null;
  } catch { return null; }
}

async function detectPrice(tab) {
  try {
    const resp = await chrome.tabs.sendMessage(tab.id, { type: "GET_PRICE" });
    return resp?.price || null;
  } catch { return null; }
}

// ── Submit: Validate My Analysis ─────────────────────────────────
async function submitValidate() {
  const ticker = $("tickerInput").value.trim().toUpperCase();
  const signal = $("signalSelect").value;
  const analysis = $("userAnalysisInput").value.trim();
  const price  = $("priceInput").value.trim();
  const sl     = $("slInput").value.trim();
  const tp     = $("tpInput").value.trim();

  if (!ticker) { $("tickerInput").focus(); showToast("Enter a ticker"); return; }
  if (!analysis || analysis.length < 20) {
    $("userAnalysisInput").focus();
    showToast("Describe your analysis (min 20 chars)");
    return;
  }

  state.description = analysis;
  $("step4Label").textContent = "Validating Your Analysis";
  $("loadingTitle").textContent = "Validating your analysis against live market data…";
  $("confidenceLabel").textContent = "Market Alignment";
  showStep("step4");
  showLoading();
  setStatus("loading");
  startProgress();

  try {
    const blob     = await (await fetch(state.screenshot)).blob();
    const form     = new FormData();
    form.append("screenshot",   blob, "chart.png");
    form.append("ticker",       ticker);
    form.append("signal",       signal);
    form.append("price",        price || "");
    form.append("description",  analysis);
    form.append("sl",           sl || "");
    form.append("tp",           tp || "");
    form.append("mode",         "validate");
    form.append("user_id",      state.settings.userId);

    const resp = await fetch(`${state.settings.apiUrl}/webhook/screenshot`, {
      method: "POST", body: form,
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${await resp.text()}`);
    const { request_id } = await resp.json();
    state.requestId = request_id;
    state.pollAttempts = 0;
    state.pollTimer = setInterval(() => pollResult(request_id), POLL_INTERVAL_MS);
  } catch (e) {
    stopProgress();
    showErrorState(e.message);
  }
}

// ── Submit: AI Pattern Analysis ───────────────────────────────────
async function submitAnalyse() {
  const ticker   = $("tickerInput").value.trim().toUpperCase();
  const signal   = $("signalSelect").value;
  const patterns = state.selectedPatterns;

  if (!ticker) { showStep("step2"); showToast("Enter a ticker"); return; }
  if (!patterns.length) { showToast("Select at least one pattern"); return; }

  $("step4Label").textContent = "AI Chart Analysis";
  $("loadingTitle").textContent = `Scanning for ${patterns.length} pattern${patterns.length > 1 ? "s" : ""}…`;
  $("confidenceLabel").textContent = "Pattern Match Score";
  showStep("step4");
  showLoading();
  setStatus("loading");
  startProgress();

  try {
    const blob = await (await fetch(state.screenshot)).blob();
    const form = new FormData();
    form.append("screenshot",  blob, "chart.png");
    form.append("ticker",      ticker);
    form.append("signal",      signal);
    form.append("description", buildPatternPrompt(patterns));
    form.append("patterns",    JSON.stringify(patterns));
    form.append("mode",        "analyse");
    form.append("user_id",     state.settings.userId);

    const resp = await fetch(`${state.settings.apiUrl}/webhook/screenshot`, {
      method: "POST", body: form,
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${await resp.text()}`);
    const { request_id } = await resp.json();
    state.requestId = request_id;
    state.pollAttempts = 0;
    state.pollTimer = setInterval(() => pollResult(request_id), POLL_INTERVAL_MS);
  } catch (e) {
    stopProgress();
    showErrorState(e.message);
  }
}

function buildPatternPrompt(patterns) {
  return (
    `Analyse this chart for the following patterns and structures: ${patterns.join(", ")}. ` +
    `For each pattern found, describe: (1) where it appears on the chart (price level/zone), ` +
    `(2) the quality/strength of the setup, (3) the implication for price direction. ` +
    `If a pattern is NOT present, state that clearly. ` +
    `Provide drawing instructions so the trader can mark them on their own chart.`
  );
}

// ── Polling ───────────────────────────────────────────────────────
async function pollResult(requestId) {
  state.pollAttempts++;
  if (state.pollAttempts > MAX_POLL) {
    clearInterval(state.pollTimer);
    stopProgress();
    showErrorState("Analysis timed out. Check Telegram for results.");
    return;
  }

  try {
    const resp = await fetch(
      `${state.settings.apiUrl}/webhook/screenshot/result/${requestId}`
    );
    if (!resp.ok) return;
    const data = await resp.json();
    if (data.status === "completed") {
      clearInterval(state.pollTimer);
      stopProgress();
      displayResult(data);
      await saveToHistory(requestId, data);
      chrome.runtime.sendMessage({ type: "analysis_complete" });
    }
    if (data.status === "failed") {
      clearInterval(state.pollTimer);
      stopProgress();
      showErrorState(data.error || "Analysis failed.");
    }
  } catch { /* keep polling */ }
}

// ── Display result ────────────────────────────────────────────────
function displayResult(data) {
  const verdict    = (data.verdict || "CAUTION").toUpperCase();
  const confidence = Math.round((data.confidence_score || data.confidence || 0.5) * 100);
  const mode       = data.mode || state.mode || "validate";
  const patterns   = data.pattern_results || null;
  const reasoning  = data.reasoning || "";
  const ta         = data.trader_analysis || {};

  // Verdict badge
  const vc = {
    CONFIRM: { emoji: "✅", cls: "confirm" },
    CAUTION: { emoji: "⚠️", cls: "caution" },
    REJECT:  { emoji: "❌", cls: "reject"  },
  }[verdict] || { emoji: "⚠️", cls: "caution" };

  $("verdictIcon").textContent = vc.emoji;
  $("verdictText").textContent = verdict;
  $("verdictBadge").className  = `verdict-badge ${vc.cls}`;

  // Confidence bar
  $("confidenceValue").textContent = `${confidence}%`;
  setTimeout(() => {
    $("confidenceFill").style.width = `${confidence}%`;
    $("confidenceFill").style.background =
      confidence >= 65 ? "var(--green)" : confidence >= 45 ? "var(--yellow)" : "var(--red)";
  }, 80);

  // Main result body
  const clean = reasoning
    .replace(/\*\*(.*?)\*\*/g, "$1")
    .replace(/\*(.*?)\*/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .trim();
  $("resultBody").textContent = clean.slice(0, 500) + (clean.length > 500 ? "…" : "");

  // Pattern cards (analyse mode)
  if (patterns && patterns.length > 0) {
    $("patternCards").style.display = "grid";
    $("patternCards").innerHTML = patterns.map(p => `
      <div class="pattern-card ${p.found ? 'found' : 'not-found'}">
        <div class="pc-header">
          <span class="pc-icon">${p.found ? "✅" : "➖"}</span>
          <span class="pc-name">${p.name}</span>
        </div>
        ${p.found ? `
          <div class="pc-zone">${p.zone || ""}</div>
          <div class="pc-note">${p.note || ""}</div>
          ${p.draw_instruction ? `<div class="pc-draw">✏️ ${p.draw_instruction}</div>` : ""}
        ` : `<div class="pc-note not-found-note">${p.note || "Not detected on this chart."}</div>`}
      </div>`).join("");
  } else {
    $("patternCards").style.display = "none";
  }

  // User notes echo-back (validate mode)
  if (mode === "validate" && state.description) {
    $("userNotesText").textContent     = state.description.slice(0, 300);
    $("userNotesResult").style.display = "block";
  }

  // Indicator chips
  const chips = [];
  if (ta.rsi   != null) chips.push({ l: "RSI",   v: ta.rsi.toFixed(1) });
  if (ta.macd  != null) chips.push({ l: "MACD",  v: ta.macd.toFixed(3) });
  if (ta.bb_position)   chips.push({ l: "BB",    v: ta.bb_position.replace(/_/g, " ") });
  if (ta.current_price) chips.push({ l: "Price", v: `$${ta.current_price}` });

  $("indicatorRow").innerHTML = chips.map(c =>
    `<div class="indicator-chip">
       <span class="chip-label">${c.l}</span>
       <span class="chip-value">${c.v}</span>
     </div>`
  ).join("");

  $("loadingContainer").style.display = "none";
  $("resultContainer").style.display  = "block";
  $("errorContainer").style.display   = "none";
  setStatus("done");
}

// ── Helpers ───────────────────────────────────────────────────────
function showStep(id) {
  document.querySelectorAll(".step").forEach(s => s.classList.remove("active"));
  $(id).classList.add("active");
}

function showLoading() {
  $("loadingContainer").style.display = "flex";
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
  dot.title = { idle:"Ready", loading:"Processing…", ready:"Screenshot ready", done:"Done" }[s] || s;
}

let _progressTimer = null;
function startProgress() {
  $("progressFill").style.width = "0%";
  let pct = 0;
  _progressTimer = setInterval(() => {
    pct = Math.min(pct + 0.5, 88);
    $("progressFill").style.width = `${pct}%`;
    const attemptPct = (state.pollAttempts / MAX_POLL) * 100;
    const stage = [...PROGRESS_STAGES].reverse().find(s => attemptPct >= s.at) || PROGRESS_STAGES[0];
    $("progressLabel").textContent = stage.msg;
  }, 250);
}

function stopProgress() {
  clearInterval(_progressTimer);
  $("progressFill").style.width = "100%";
}

function openTelegram() {
  const bot = state.settings.botName.replace(/^@/, "") || "YourBotName";
  chrome.tabs.create({ url: `https://t.me/${bot}` });
}

function openSettings() {
  $("apiUrlInput").value      = state.settings.apiUrl;
  $("telegramBotInput").value = state.settings.botName;
  $("userIdDisplay").value    = state.settings.userId;
  showStep("settingsPanel");
}

function resetToStep1() {
  clearInterval(state.pollTimer);
  state.requestId    = null;
  state.pollAttempts = 0;
  state.mode         = null;
  state.description  = "";
  state.selectedPatterns = [];

  $("userAnalysisInput").value  = "";
  $("analysisCharCount").textContent = "0";
  $("tickerInput").classList.remove("input-error");
  document.querySelectorAll(".pattern-grid input[type=checkbox]").forEach(c => c.checked = false);
  document.querySelectorAll(".mode-card").forEach(c => c.classList.remove("selected"));
  $("selectAllCat").checked = false;
  $("selectAllAll").checked = false;
  updateSubmitBtn();
  updatePatternSummary();

  setStatus(state.screenshot ? "ready" : "idle");
  showStep("step1");
}

function copyResult() {
  const v = $("verdictText").textContent;
  const c = $("confidenceValue").textContent;
  const r = $("resultBody").textContent;
  const n = state.description ? `\n\nMy analysis: ${state.description}` : "";
  navigator.clipboard.writeText(
    `AI Trade Validator\nVerdict: ${v} (${c})\n\n${r}${n}\n\n⚠️ Not financial advice.`
  ).then(() => showToast("Copied ✓"));
}

async function saveToHistory(requestId, result) {
  const { analysisHistory = [] } = await chrome.storage.local.get("analysisHistory");
  analysisHistory.unshift({
    id:          requestId,
    ticker:      $("tickerInput").value,
    signal:      $("signalSelect").value,
    mode:        state.mode,
    description: state.description,
    patterns:    state.selectedPatterns,
    verdict:     result.verdict,
    confidence:  result.confidence_score || result.confidence,
    timestamp:   Date.now(),
  });
  await chrome.storage.local.set({
    analysisHistory:             analysisHistory.slice(0, 50),
    [`analysis_${requestId}`]:   result,
  });
}

function generateUserId() {
  return "ext_" + Date.now().toString(36) + Math.random().toString(36).slice(2, 9);
}

let _toastTimer = null;
function showToast(msg) {
  clearTimeout(_toastTimer);
  let t = document.getElementById("toast");
  if (!t) {
    t = Object.assign(document.createElement("div"), { id:"toast", className:"toast" });
    document.body.appendChild(t);
  }
  t.textContent = msg;
  t.classList.add("show");
  _toastTimer = setTimeout(() => t.classList.remove("show"), 2200);
}
