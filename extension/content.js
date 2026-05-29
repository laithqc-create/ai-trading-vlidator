/**
 * content.js — injected into every page
 * Responsibilities:
 *   - Detect current ticker/symbol on TradingView, MT Web, etc.
 *   - Handle news text selection → send to background for analysis
 *   - Respond to ping from side panel to confirm injection
 */

// ── Symbol detection ──────────────────────────────────────────────────────────
function detectSymbol() {
  const host = location.hostname;

  // TradingView: ticker in URL path /chart/XXXXXX/ or title "BTCUSD · 1D · BINANCE"
  if (host.includes("tradingview.com")) {
    // Try URL first — /chart/<id>/?symbol=NASDAQ:AAPL
    const urlParam = new URLSearchParams(location.search).get("symbol");
    if (urlParam) return urlParam.split(":").pop();

    // Try page title
    const titleMatch = document.title.match(/^([A-Z0-9.]+)\s·/);
    if (titleMatch) return titleMatch[1];

    // Try the DOM ticker element
    const tvTicker = document.querySelector('[data-symbol-short]');
    if (tvTicker) return tvTicker.getAttribute('data-symbol-short');
  }

  // MetaTrader Web
  if (host.includes("metatrader") || host.includes("mt4") || host.includes("mt5")) {
    const el = document.querySelector('.symbol-name, .instrument-name');
    if (el) return el.textContent.trim();
  }

  // Generic: look for a visible uppercase ticker-like text near the top
  const candidates = Array.from(document.querySelectorAll('h1, h2, [class*="symbol"], [class*="ticker"], [class*="instrument"]'));
  for (const el of candidates) {
    const text = el.textContent.trim();
    if (/^[A-Z]{2,6}(USD|EUR|GBP|JPY|BTC|ETH)?$/.test(text)) return text;
  }

  return null;
}

// ── News text selection ───────────────────────────────────────────────────────
let highlightBtn = null;

document.addEventListener("mouseup", () => {
  const selection = window.getSelection();
  if (!selection || selection.toString().trim().length < 20) {
    removeHighlightBtn();
    return;
  }

  const text = selection.toString().trim();
  const range = selection.getRangeAt(0);
  const rect = range.getBoundingClientRect();

  removeHighlightBtn();

  highlightBtn = document.createElement("div");
  highlightBtn.id = "atv-highlight-btn";
  highlightBtn.textContent = "📰 Analyse news impact";

  // position:fixed uses viewport coords — do NOT add scrollY
  const topPx = Math.min(rect.bottom + 8, window.innerHeight - 48);
  const leftPx = Math.max(0, Math.min(rect.left, window.innerWidth - 220));

  Object.assign(highlightBtn.style, {
    position:        "fixed",
    top:             `${topPx}px`,
    left:            `${leftPx}px`,
    background:      "linear-gradient(135deg,#1f6feb,#58a6ff)",
    color:           "#ffffff",
    padding:         "7px 14px",
    borderRadius:    "20px",
    fontSize:        "13px",
    fontFamily:      "-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif",
    fontWeight:      "500",
    cursor:          "pointer",
    zIndex:          "2147483647",
    boxShadow:       "0 4px 16px rgba(31,111,235,0.5),0 1px 4px rgba(0,0,0,0.3)",
    userSelect:      "none",
    whiteSpace:      "nowrap",
    border:          "none",
    outline:         "none",
    transition:      "opacity 0.15s",
    opacity:         "0",
    pointerEvents:   "auto",
  });

  highlightBtn.addEventListener("click", () => {
    const symbol = detectSymbol();
    chrome.runtime.sendMessage({
      type: "NEWS_TEXT_SELECTED",
      text,
      symbol,
    });
    removeHighlightBtn();
  });

  document.body.appendChild(highlightBtn);
  // Fade in on next frame
  requestAnimationFrame(() => { highlightBtn.style.opacity = "1"; });
});

document.addEventListener("mousedown", (e) => {
  if (highlightBtn && !highlightBtn.contains(e.target)) {
    removeHighlightBtn();
  }
});

function removeHighlightBtn() {
  if (highlightBtn) {
    highlightBtn.remove();
    highlightBtn = null;
  }
}

// ── Message listener ──────────────────────────────────────────────────────────
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "GET_SYMBOL") {
    sendResponse({ symbol: detectSymbol() });
  }
  if (msg.type === "PING") {
    sendResponse({ ok: true });
  }
});
