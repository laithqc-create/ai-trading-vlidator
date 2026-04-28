/**
 * content.js — TradingView Content Script
 *
 * Injected into every TradingView page.
 * Responds to popup queries for:
 *   - GET_TICKER  — current symbol from chart DOM
 *   - GET_PRICE   — last price from chart DOM
 *
 * Uses DOM selectors specific to TradingView's layout.
 * Falls back gracefully if selectors change.
 */

"use strict";

// ── Message listener ──────────────────────────────────────────────
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "GET_TICKER") {
    sendResponse({ ticker: detectTicker() });
  }
  if (message.type === "GET_PRICE") {
    sendResponse({ price: detectPrice() });
  }
  return true; // keep channel open for async
});

// ── Ticker detection ──────────────────────────────────────────────
function detectTicker() {
  try {
    // Strategy 1: TradingView header symbol chip (most reliable)
    const headerSym = document.querySelector(
      '[data-name="legend-source-title"], ' +
      '.chart-markup-table .pane-legend-title__description, ' +
      '[class*="titleWrapper"] [class*="title"]'
    );
    if (headerSym) {
      const text = headerSym.textContent.trim().split(/[\s,\/]/)[0].toUpperCase();
      if (isValidTicker(text)) return text;
    }

    // Strategy 2: URL path (e.g. /chart/?symbol=AAPL or /symbols/AAPL/)
    const urlMatch = window.location.href.match(
      /[?&]symbol=([A-Z0-9:.]{1,12})|\/symbols\/([A-Z0-9:.]{1,12})\//i
    );
    if (urlMatch) {
      const sym = (urlMatch[1] || urlMatch[2]).toUpperCase().split(":").pop();
      if (isValidTicker(sym)) return sym;
    }

    // Strategy 3: Page title
    const titleMatch = document.title.match(/^([A-Z0-9]{1,10}(?:\.[A-Z]{1,5})?)\s*[:\-—]/);
    if (titleMatch && isValidTicker(titleMatch[1])) return titleMatch[1];

    // Strategy 4: Breadcrumb / symbol search bar
    const searchEl = document.querySelector(
      '[data-role="search"] input, ' +
      '[class*="symbolInput"] input, ' +
      '#header-toolbar-symbol-search input'
    );
    if (searchEl?.value) {
      const val = searchEl.value.trim().toUpperCase().split(":").pop();
      if (isValidTicker(val)) return val;
    }

    return null;
  } catch {
    return null;
  }
}

// ── Price detection ───────────────────────────────────────────────
function detectPrice() {
  try {
    // TradingView last price appears in legend or price scale
    const priceSelectors = [
      '[class*="lastPrice"]',
      '[class*="priceValue"]',
      '[data-name="legend-source-item"] [class*="price"]',
      '.chart-markup-table .pane-legend-item-value-item',
    ];

    for (const sel of priceSelectors) {
      const el = document.querySelector(sel);
      if (el) {
        const raw = el.textContent.replace(/[^0-9.]/g, "");
        const price = parseFloat(raw);
        if (!isNaN(price) && price > 0) return price.toString();
      }
    }

    return null;
  } catch {
    return null;
  }
}

// ── Helpers ───────────────────────────────────────────────────────
function isValidTicker(sym) {
  return sym && /^[A-Z0-9.]{1,12}$/.test(sym) && sym.length >= 1;
}

// ── Visual indicator that extension is active ─────────────────────
// Adds a subtle blue dot to TradingView header when extension is loaded
(function addExtensionIndicator() {
  if (document.getElementById("atv-ext-indicator")) return;
  const dot = document.createElement("div");
  dot.id = "atv-ext-indicator";
  dot.title = "AI Trade Validator is active";
  Object.assign(dot.style, {
    position:     "fixed",
    bottom:       "8px",
    right:        "8px",
    width:        "8px",
    height:       "8px",
    borderRadius: "50%",
    background:   "#89b4fa",
    opacity:      "0.7",
    zIndex:       "99999",
    pointerEvents:"none",
    transition:   "opacity 0.3s",
  });
  document.body.appendChild(dot);

  // Fade after 3 seconds
  setTimeout(() => { dot.style.opacity = "0"; }, 3000);
  setTimeout(() => { dot.remove(); }, 3500);
})();
