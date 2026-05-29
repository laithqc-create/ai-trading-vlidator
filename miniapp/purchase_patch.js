/**
 * miniapp_purchase_patch.js
 * Add this script block to miniapp/index.html (or your Mini App JS file).
 *
 * Adds:
 *   - Trial banner shown to FREE users who haven't trialled
 *   - "Start free trial" button
 *   - "Subscribe" buttons per product that redirect to Whop
 *   - Affiliate link in profile/settings section
 *
 * Assumes:
 *   - window.TELEGRAM_USER_ID is set from Telegram.WebApp.initDataUnsafe.user.id
 *   - API_BASE is your backend base URL
 */

const API_BASE = window.API_BASE || "https://your-backend.example.com";

// ── Run on page load ──────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", async () => {
  const tgUser = window.Telegram?.WebApp?.initDataUnsafe?.user;
  if (!tgUser?.id) return;

  window.TELEGRAM_USER_ID = String(tgUser.id);
  await initTrialAndPurchase();
});

async function initTrialAndPurchase() {
  const tgId = window.TELEGRAM_USER_ID;
  if (!tgId) return;

  const headers = { "X-Telegram-User-Id": tgId };

  try {
    const [planRes, trialRes] = await Promise.all([
      fetch(`${API_BASE}/api/user/plan`, { headers }).then(r => r.json()),
      fetch(`${API_BASE}/api/trial/status`, { headers }).then(r => r.json()),
    ]);

    renderPlanBanner(planRes, trialRes, tgId);
    renderPurchaseButtons(planRes, trialRes, tgId);
    renderAffiliateLink(tgId);
  } catch (e) {
    console.warn("[Purchase] Could not load plan/trial:", e);
  }
}

// ── Trial / plan banner ───────────────────────────────────────────────────────
function renderPlanBanner(plan, trial, tgId) {
  // Insert a banner at the top of the Mini App body (before first section)
  const existing = document.getElementById("atv-plan-banner");
  if (existing) existing.remove();

  const banner = document.createElement("div");
  banner.id = "atv-plan-banner";
  banner.style.cssText = `
    padding: 10px 16px; margin: 0 0 16px;
    border-radius: 10px; font-size: 13px;
    display: flex; align-items: center; justify-content: space-between;
    gap: 10px;
  `;

  if (trial.active) {
    banner.style.background = "rgba(88,166,255,0.12)";
    banner.style.border = "1px solid rgba(88,166,255,0.3)";
    banner.innerHTML = `
      <div>
        <span style="font-weight:600; color:#58a6ff">Free Trial</span>
        <span style="color:#8b949e; font-size:12px"> — ${trial.days_remaining} day${trial.days_remaining !== 1 ? 's' : ''} remaining</span>
      </div>
      <button onclick="openCheckout('pro', '${tgId}')" style="
        background:#1f6feb; border:none; color:#fff; padding:5px 12px;
        border-radius:6px; font-size:12px; cursor:pointer; font-weight:500;
      ">Upgrade</button>
    `;
  } else if (plan.plan !== "free") {
    banner.style.background = "rgba(63,185,80,0.08)";
    banner.style.border = "1px solid rgba(63,185,80,0.2)";
    banner.innerHTML = `
      <div>
        <span style="font-weight:600; color:#3fb950">${plan.plan_label}</span>
        ${plan.expires_at ? `<span style="color:#8b949e; font-size:12px"> — renews ${new Date(plan.expires_at).toLocaleDateString()}</span>` : ''}
      </div>
      <button onclick="openCheckout('pro', '${tgId}')" style="
        background:transparent; border:1px solid #3fb950; color:#3fb950;
        padding:5px 12px; border-radius:6px; font-size:12px; cursor:pointer;
      ">Manage</button>
    `;
  } else if (!trial.used) {
    // Free, never trialled — most prominent
    banner.style.background = "rgba(188,140,255,0.1)";
    banner.style.border = "1px solid rgba(188,140,255,0.3)";
    banner.innerHTML = `
      <div>
        <span style="font-weight:600; color:#bc8cff">14-day free trial available</span><br>
        <span style="color:#8b949e; font-size:12px">Full access to all products, no card needed</span>
      </div>
      <button id="atv-trial-btn" onclick="startTrialFromMiniApp('${tgId}')" style="
        background:#bc8cff; border:none; color:#0d1117; padding:6px 14px;
        border-radius:6px; font-size:12px; cursor:pointer; font-weight:600;
      ">Start free trial</button>
    `;
  } else {
    // Free, trial used
    banner.style.background = "rgba(248,81,73,0.08)";
    banner.style.border = "1px solid rgba(248,81,73,0.2)";
    banner.innerHTML = `
      <div>
        <span style="font-weight:600; color:#f85149">Trial ended</span>
        <span style="color:#8b949e; font-size:12px"> — subscribe to keep access</span>
      </div>
      <button onclick="openCheckout('pro', '${tgId}')" style="
        background:#f85149; border:none; color:#fff; padding:5px 12px;
        border-radius:6px; font-size:12px; cursor:pointer; font-weight:500;
      ">Subscribe</button>
    `;
  }

  // Insert before first child of body or main content container
  const container = document.querySelector(".miniapp-content, main, #content, body");
  if (container) container.insertBefore(banner, container.firstChild);
}

// ── Purchase buttons per product ──────────────────────────────────────────────
function renderPurchaseButtons(plan, trial, tgId) {
  // Find all elements with data-product attribute and inject subscribe buttons
  // Add data-product="product1|product2|product3|pro" to your product cards in HTML
  document.querySelectorAll("[data-product]").forEach((card) => {
    const productKey = card.getAttribute("data-product");
    const hasAccess = checkAccess(plan, trial, productKey);

    // Remove existing purchase buttons first
    card.querySelectorAll(".atv-purchase-btn").forEach(b => b.remove());

    if (!hasAccess) {
      const btn = document.createElement("button");
      btn.className = "atv-purchase-btn";
      btn.textContent = trial.used ? "Subscribe to access" : "Start free trial";
      btn.style.cssText = `
        width:100%; margin-top:10px; padding:9px;
        background:#1f6feb; border:none; color:#fff;
        border-radius:8px; font-size:13px; font-weight:500; cursor:pointer;
      `;
      btn.onclick = trial.used
        ? () => openCheckout(productKey, tgId)
        : () => startTrialFromMiniApp(tgId);
      card.appendChild(btn);
    } else {
      const badge = document.createElement("span");
      badge.className = "atv-purchase-btn";
      badge.textContent = trial.active ? "✓ Trial" : "✓ Active";
      badge.style.cssText = `
        display:inline-block; margin-top:6px; padding:3px 10px;
        background:rgba(63,185,80,0.15); color:#3fb950;
        border-radius:20px; font-size:11px; font-weight:500;
      `;
      card.appendChild(badge);
    }
  });
}

function checkAccess(plan, trial, productKey) {
  if (trial.active) return true;
  if (plan.plan === "pro") return true;
  return plan.plan === productKey;
}

// ── Affiliate link ────────────────────────────────────────────────────────────
function renderAffiliateLink(tgId) {
  // Find affiliate placeholder elements
  document.querySelectorAll("[data-affiliate-placeholder]").forEach((el) => {
    el.innerHTML = `
      <a href="https://whop.com/affiliate/YOUR_AFFILIATE_LINK?ref=${tgId}"
         target="_blank"
         style="color:#58a6ff; font-size:13px; text-decoration:none; display:flex; align-items:center; gap:5px;">
        🤝 Earn with our affiliate program →
      </a>
    `;
  });
}

// ── Actions ───────────────────────────────────────────────────────────────────
async function startTrialFromMiniApp(tgId) {
  const btn = document.getElementById("atv-trial-btn");
  if (btn) { btn.textContent = "Starting…"; btn.disabled = true; }

  try {
    const res = await fetch(`${API_BASE}/api/trial/start`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Telegram-User-Id": tgId,
      },
      body: JSON.stringify({}),
    });
    const data = await res.json();

    if (data.ok) {
      // Show Telegram native alert if available
      if (window.Telegram?.WebApp?.showAlert) {
        window.Telegram.WebApp.showAlert(
          `🎉 Trial started! You have ${data.days_remaining} days of full access.`,
          () => initTrialAndPurchase()
        );
      } else {
        alert(`✅ Trial started — ${data.days_remaining} days remaining.`);
        await initTrialAndPurchase();
      }
    } else {
      alert(data.message || "Could not start trial.");
      if (btn) { btn.textContent = "Start free trial"; btn.disabled = false; }
    }
  } catch (e) {
    alert("Network error. Please try again.");
    if (btn) { btn.textContent = "Start free trial"; btn.disabled = false; }
  }
}

async function openCheckout(plan, tgId) {
  try {
    const res = await fetch(`${API_BASE}/api/checkout/${plan}`, {
      headers: { "X-Telegram-User-Id": tgId },
    });
    const data = await res.json();
    if (data.ok && data.checkout_url) {
      if (window.Telegram?.WebApp?.openLink) {
        window.Telegram.WebApp.openLink(data.checkout_url);
      } else {
        window.open(data.checkout_url, "_blank");
      }
    }
  } catch (e) {
    console.error("[Checkout]", e);
  }
}
