# Frontend UX Improvements Guide

Last updated: June 13, 2026

## Recent Improvements (June 13)

### ✅ Indicators Window
- **Fixed:** Empty indicators list → now shows all 26 indicators
- **Improved:** Better error messages in console
- **Change:** `/api/indicators` now works without authentication

### ✅ Profile Sheet Buttons
- **Enhanced:** Better error handling for Edit (billing) and Change (password)
- **Added:** Console logging for debugging
- **Improved:** Input validation before API calls
- **Better:** Toast messages show actual error details

### ✅ Error Handling
- **All endpoints:** Now show human-readable errors instead of generic "Failed"
- **Console logs:** API responses logged for debugging
- **Network errors:** Distinguished from HTTP errors

## Current Frontend Issues to Watch

### 1. Sheet Opening/Closing
**Status:** Working correctly, but improved with logging
**Issue tracker:** None currently
**Next step:** User testing in production

### 2. Token Display
**Current behavior:** 
- Tokens are generated on registration
- Saved to localStorage in index.html  
- Displayed on profile page (masked: `token••••••••`)
- Can be copied with click

**Potential improvements:**
- [ ] Add "Token created/updated" timestamp
- [ ] Add "Last used" timestamp
- [ ] Add token regeneration button (for security)
- [ ] Add token revocation option

### 3. Authentication Flow
**Current flow:**
1. User registers → tokens generated
2. JWT saved to localStorage
3. Redirected to `/app`
4. Headers constructed from localStorage + Telegram
5. API calls include auth headers

**Issue:** If localStorage isn't working, requests fail silently
**Solution:** Added better error messages

### 4. Form Validation
**Current state:** Basic validation in place
- [ ] Email format validated
- [x] Password strength (8+ chars)
- [x] Billing fields optional
- [ ] Could add real-time validation UI

## Best Practices Applied

### ✅ Error Handling
```javascript
// GOOD: Detailed error messages
try {
  const res = await fetch(...);
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
} catch(e) {
  console.error("Details:", e);
  showToast(e.message || "Failed", "err");
}

// BAD: Silent failure
try {
  await fetch(...);
  updateUI();
} catch { }
```

### ✅ Headers Construction
```javascript
// GOOD: Multiple auth methods
const H = {
  "Content-Type": "application/json",
  ...(_jwt        ? {"Authorization": `Bearer ${_jwt}`}    : {}),
  ...(TG_ID       ? {"X-Telegram-User-Id": TG_ID}          : {}),
  ...(_atvToken   ? {"X-ATV-Token": _atvToken}              : {}),
};

// This ensures:
// - JWT users (email/Google) work
// - Telegram users work
// - Extension users work
```

### ✅ localStorage Usage
```javascript
// Save after registration
localStorage.setItem("atv_jwt",   data.access_token);
localStorage.setItem("atv_token", data.user.tokens.api);
localStorage.setItem("atv_user",  JSON.stringify(data.user));

// Load on page init
const _jwt = localStorage.getItem("atv_jwt") || "";
const user = JSON.parse(localStorage.getItem("atv_user") || "{}");

// Clear on logout
localStorage.removeItem("atv_jwt");
localStorage.removeItem("atv_token");
localStorage.removeItem("atv_user");
```

## Areas for Future Improvement

### Performance
- [ ] Lazy load pages instead of rendering all at once
- [ ] Cache indicators list (only changes admin can update)
- [ ] Debounce API calls on rapid input
- [ ] Compress response payloads

### Accessibility
- [ ] Add ARIA labels to buttons
- [ ] Keyboard navigation for sheets
- [ ] Screen reader support
- [ ] Color contrast checks

### Mobile Optimization
- [ ] Optimize for small screens
- [ ] Touch-friendly button sizes (48px minimum)
- [ ] Swipe gestures for sheet close
- [ ] Mobile-specific navigation

### Security
- [ ] Implement Content Security Policy (CSP)
- [ ] Add CSRF token to forms
- [ ] Sanitize user input before display
- [ ] Implement token rotation

## Code Quality Checklist

For any new frontend code:

- [ ] Error handling with try/catch
- [ ] Console logging for debugging
- [ ] User feedback (toast messages)
- [ ] Input validation before API calls
- [ ] Proper HTML element IDs
- [ ] CSS variables used (not hardcoded colors)
- [ ] Mobile-responsive design
- [ ] Accessibility considerations

## Common Patterns

### Loading State
```javascript
const btn = document.querySelector(".btn-primary");
btn.disabled = true;
btn.textContent = "Loading...";

try {
  await doSomething();
  showToast("Success ✓", "ok");
} catch(e) {
  showToast(e.message, "err");
} finally {
  btn.disabled = false;
  btn.textContent = "Original text";
}
```

### API Call with Error Handling
```javascript
async function apiFetch(path, method="GET", body=null) {
  const opts = {method, headers:H};
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(API_BASE + path, opts);
  if (!r.ok) {
    const e = await r.json().catch(()=>({}));
    throw new Error(e.detail || `HTTP ${r.status}`);
  }
  return r.json();
}
```

### Sheet Management
```javascript
function openSheet(id) {
  const el = document.getElementById(id);
  if (!el) {
    console.warn(`Sheet '${id}' not found`);
    return;
  }
  el.classList.add("show");
  console.log(`Opened sheet: ${id}`);
}

function closeSheet(id) {
  document.getElementById(id)?.classList.remove("show");
}
```

### Toast Notifications
```javascript
function showToast(message, type="ok") {
  const toast = document.getElementById("toast");
  toast.textContent = message;
  toast.className = `toast show ${type}`;
  setTimeout(() => toast.classList.remove("show"), 3000);
}
```

## Testing Checklist for New Features

Before deploying a new frontend feature:

- [ ] Works in Chrome
- [ ] Works in Firefox
- [ ] Works in Safari
- [ ] Works on mobile (iPhone/Android)
- [ ] Works without JavaScript errors (check console)
- [ ] Works without auth (fallback handling)
- [ ] Works with slow network (loading states)
- [ ] Works with network errors (error messages)
- [ ] Accessible with keyboard navigation
- [ ] Responsive on all screen sizes

## Performance Metrics

Target metrics for good UX:

- **First Paint:** < 1s
- **Time to Interactive:** < 2s
- **API Response:** < 1s (95th percentile)
- **Sheet animation:** 200-300ms
- **Toast notification:** 3s auto-dismiss
- **Button feedback:** Instant (< 100ms)

## Debugging Guide

### Frontend Issues

**Symptom:** Indicators window shows "No indicators match"
```javascript
// Open DevTools Console (F12)
// Check:
1. fetch(API + "/api/indicators").then(r => r.json()).then(d => console.log(d))
2. localStorage.getItem("atv_jwt")
3. localStorage.getItem("atv_token")
4. window.Telegram?.WebApp?.initDataUnsafe?.user
```

**Symptom:** Sheet doesn't open
```javascript
// Check:
1. document.getElementById("billing-sheet")  // Should exist
2. document.getElementById("billing-sheet").classList  // Check .show class
3. Open DevTools and click button, check console
```

**Symptom:** Tokens not saving
```javascript
// Check:
1. Network tab → /auth/register response → contains tokens?
2. localStorage → atv_token exists?
3. console.log(localStorage)  // View all localStorage
```

### Common Fixes

| Issue | Solution |
|-------|----------|
| Blank page | Check console for errors, verify API_BASE is correct |
| Can't login | Verify JWT saved to localStorage, check network tab |
| Buttons don't work | F12 → check JavaScript errors, verify element IDs |
| Slow loading | Check network tab, look for slow API calls |
| Mobile layout broken | Check viewport meta tag, test on actual device |

## Browser Compatibility

**Supported:**
- Chrome/Chromium (recommended)
- Firefox
- Safari 13+
- Edge

**Not tested:**
- IE11 (not supported)
- Opera (should work)
- Mobile browsers (tested on Chrome/Safari)

## References

- **Architecture:** See README.md
- **API Documentation:** See API comments in code
- **Database Schema:** See db/models.py
- **Environment Variables:** See .env.example
