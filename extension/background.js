/**
 * background.js — Service Worker
 *
 * Handles:
 * - Extension install / update
 * - Badge notifications when analysis completes
 * - Context menu (right-click on TradingView)
 * - Alarm for badge cleanup
 */

"use strict";

// ── Install / Update ──────────────────────────────────────────────
chrome.runtime.onInstalled.addListener(async ({ reason }) => {
  if (reason === "install") {
    await chrome.storage.local.set({
      version:         "1.0.0",
      userId:          null,
      apiUrl:          "https://your-api.com",
      botName:         "@YourBotName",
      analysisHistory: [],
    });

    // Open onboarding page on first install
    chrome.tabs.create({
      url: chrome.runtime.getURL("onboarding.html"),
    });
  }

  // Set badge style
  chrome.action.setBadgeBackgroundColor({ color: "#89b4fa" });
  chrome.action.setBadgeTextColor({ color: "#1e1e2e" });
});

// ── Messages from popup ───────────────────────────────────────────
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "analysis_complete") {
    // Flash badge
    chrome.action.setBadgeText({ text: "✓" });
    chrome.alarms.create("clearBadge", { delayInMinutes: 0.05 }); // 3 seconds
  }

  if (message.type === "analysis_failed") {
    chrome.action.setBadgeText({ text: "!" });
    chrome.action.setBadgeBackgroundColor({ color: "#f38ba8" });
    chrome.alarms.create("clearBadge", { delayInMinutes: 0.1 });
  }

  sendResponse({ ok: true });
  return true;
});

// ── Alarm handler ─────────────────────────────────────────────────
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "clearBadge") {
    chrome.action.setBadgeText({ text: "" });
    chrome.action.setBadgeBackgroundColor({ color: "#89b4fa" });
  }
});

// ── Context menu (right-click on TradingView) ─────────────────────
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id:       "captureAndValidate",
    title:    "📸 Capture & Validate with AI",
    contexts: ["page"],
    documentUrlPatterns: ["https://*.tradingview.com/*"],
  });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === "captureAndValidate") {
    // Open popup programmatically (Chrome MV3: not always possible, so open a new popup)
    chrome.action.openPopup?.().catch(() => {
      // Fallback: just highlight the extension icon
      chrome.action.setBadgeText({ text: "👆" });
      chrome.alarms.create("clearBadge", { delayInMinutes: 0.05 });
    });
  }
});
