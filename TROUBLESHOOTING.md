# ATV Troubleshooting Guide

## Common Issues & Solutions

### Authentication Issues

#### Issue: "Invalid email or password" when trying to login
**Cause:** Incorrect credentials or account doesn't exist
**Solution:**
1. Verify email is spelled correctly
2. Verify password is correct (case-sensitive)
3. Check if account was created (try registration if not)
4. Clear browser cache and try again

**Debug:**
```javascript
// In browser console:
localStorage.getItem("atv_jwt")  // Should show token if logged in
localStorage.getItem("atv_user") // Should show user object
```

---

#### Issue: "Account with this email already exists"
**Cause:** Email was already registered
**Solution:**
1. Use login page instead of registration
2. Try password reset (if implemented)
3. Use a different email address

**Note:** This is working correctly - preventing duplicate accounts

---

#### Issue: Logged in but API calls failing with 401
**Cause:** JWT token is invalid or expired
**Solution:**
1. Logout and login again to refresh token
2. Clear localStorage completely and login
3. Check browser DevTools → Application → localStorage

**Debug:**
```javascript
// Verify JWT is present and valid
const jwt = localStorage.getItem("atv_jwt");
console.log("JWT:", jwt.slice(0, 30) + "...");

// Check headers being sent
fetch(API + "/api/indicators", {
  headers: {
    "Authorization": "Bearer " + jwt
  }
}).then(r => r.json()).then(d => console.log("Response:", d));
```

---

#### Issue: Telegram login not working
**Cause:** Telegram Mini App not initialized or token not sent
**Solution:**
1. Ensure you're accessing the Mini App from Telegram
2. Check that bot username is correct in `TELEGRAM_BOT_USERNAME`
3. Verify webhook is set up correctly

**Debug:**
```javascript
// Check if Telegram is available
console.log("Telegram:", window.Telegram);
console.log("User ID:", window.Telegram?.WebApp?.initDataUnsafe?.user?.id);

// Should show: Telegram: {WebApp: {...}}
// And: User ID: 123456789
```

---

### Indicators Issues

#### Issue: "No indicators match" appears in indicator selector
**Cause:** API call failed or returned empty list
**Solution:**
1. Check browser console for error messages
2. Verify backend is running (`curl http://localhost:8000/health`)
3. Try accessing `/app/indicators` directly
4. Check network tab in DevTools for API errors

**Debug:**
```javascript
// In browser console:
fetch(API + "/api/indicators")
  .then(r => r.json())
  .then(d => console.log("Indicators:", d));

// Should show: Indicators: {ok: true, indicators: [...26 items...]}
```

---

#### Issue: Only some indicators loading
**Cause:** Partial API failure or database issue
**Solution:**
1. Refresh the page
2. Check if backend has crashed
3. Verify database connection

**Note:** All 26 indicators should always load. If some are missing, it's a server issue.

---

### Profile/Settings Issues

#### Issue: Edit billing button doesn't open sheet
**Cause:** JavaScript error or element not found
**Solution:**
1. Check browser console for JavaScript errors
2. Refresh page
3. Clear cache and reload
4. Try different browser

**Debug:**
```javascript
// Check if button exists
document.getElementById("billing-sheet")  // Should not be null

// Try opening manually
openSheet("billing-sheet");
console.log("Opened!");

// Check for JavaScript errors in console (F12)
```

---

#### Issue: "Could not save billing details" error
**Cause:** Authentication failed or API error
**Solution:**
1. Ensure you're logged in (check localStorage)
2. Check if backend is responding
3. Verify billing data is valid (especially country code)

**Debug:**
```javascript
// Verify auth is working
const jwt = localStorage.getItem("atv_jwt");
fetch(API + "/auth/me", {
  headers: {"Authorization": "Bearer " + jwt}
}).then(r => r.json()).then(d => console.log("Auth:", d));
```

---

#### Issue: Changed password but still can't login
**Cause:** Password change didn't save or used wrong credentials
**Solution:**
1. Clear browser cache
2. Try closing and reopening the app
3. Use the new password you set
4. If still failing, use password reset (if available)

---

### Extension Issues

#### Issue: Chrome extension doesn't load
**Cause:** Extension manifest issue or browser problem
**Solution:**
1. Check Chrome extensions page (`chrome://extensions/`)
2. Enable the extension if it's disabled
3. Remove and reinstall if broken
4. Check console for errors (right-click → Inspect)

**Debug:**
```javascript
// In extension background script console:
console.log("Extension loaded!");
chrome.storage.local.get(null, items => console.log("Storage:", items));
```

---

#### Issue: Extension authentication failing
**Cause:** Token not passed correctly or expired
**Solution:**
1. Ensure Mini App authenticated successfully first
2. Check token is in URL hash: `#ext-token=...`
3. Clear extension storage and re-authenticate

---

#### Issue: Extension screenshot capture not working
**Cause:** Permissions issue or indicator not found
**Solution:**
1. Verify Chrome has permission to capture screen
2. Ensure indicator/EA name matches exactly
3. Check if chart is visible and loaded
4. Try different timeframe

---

### Payment/Whop Issues

#### Issue: "Invalid checkout link" when publishing listing
**Cause:** Whop URL is malformed or incorrect
**Solution:**
1. Copy Whop checkout URL directly from Whop dashboard
2. URL should start with `https://whop.com/checkout/`
3. Don't add tracking parameters
4. For free listings, leave Whop URL empty

**Debug:**
```javascript
// Check if URL is valid
const url = "https://whop.com/checkout/...";
try {
  new URL(url);
  console.log("URL is valid");
} catch {
  console.log("URL is invalid");
}
```

---

#### Issue: Can't start trial or upgrade to paid plan
**Cause:** Whop integration not configured or API key issue
**Solution:**
1. Check `WHOP_API_KEY` is set in environment
2. Verify `WHOP_PRODUCT_ID_*` are set to real product IDs
3. Restart backend after changing env vars
4. Check Whop account is in good standing

---

### Network/Connection Issues

#### Issue: "Network error. Please try again."
**Cause:** Backend unreachable or network problem
**Solution:**
1. Check internet connection
2. Verify backend is running: `curl http://localhost:8000/health`
3. Check firewall isn't blocking port 8000
4. Try accessing from different network

**Debug:**
```javascript
// Test connectivity
fetch(API + "/health")
  .then(r => r.json())
  .then(d => console.log("Backend OK:", d))
  .catch(e => console.log("Backend down:", e));
```

---

#### Issue: API calls timing out
**Cause:** Slow network or slow API
**Solution:**
1. Check internet speed
2. Check backend performance
3. Reduce data payload size
4. Add request timeout handling

---

#### Issue: CORS error when calling API
**Cause:** Backend CORS headers not set correctly
**Solution:**
1. Verify `CORS_ORIGINS` in `.env` includes your domain
2. Restart backend
3. Clear browser cache
4. Try different browser

**Error will look like:**
```
Access to XMLHttpRequest at 'https://api.domain.com/...' 
from origin 'https://domain.com' has been blocked by CORS policy
```

---

### Database Issues

#### Issue: "Could not load your profile" or user data missing
**Cause:** Database connection lost or user record deleted
**Solution:**
1. Check database is running: `psql $DATABASE_URL -c "SELECT 1"`
2. Verify database password is correct
3. Check disk space on database server
4. Restart database service

---

#### Issue: "Duplicate key value violates unique constraint"
**Cause:** Attempting to create record with duplicate unique field
**Solution:**
1. This shouldn't happen - check for data corruption
2. Contact support with full error message
3. May need database cleanup

---

### Performance Issues

#### Issue: App is slow or laggy
**Cause:** Slow API, slow network, or heavy computation
**Solution:**
1. Check network tab in DevTools for slow requests
2. Verify backend is responsive
3. Check browser tab CPU usage (DevTools → Performance)
4. Close other tabs/applications

**Optimize:**
- Reduce indicator count if analyzing many charts
- Close unused browser tabs
- Clear browser cache periodically
- Update browser to latest version

---

#### Issue: Chart analysis taking too long
**Cause:** Complex pattern detection or slow backend
**Solution:**
1. Reduce number of indicators
2. Use simpler patterns first
3. Check backend logs for errors
4. Try with smaller chart/timeframe

---

### Data Loss Issues

#### Issue: Settings/preferences were reset
**Cause:** localStorage was cleared
**Solution:**
1. localStorage is cleared when: clearing browser data, private browsing, browser crash
2. Solution: Make sure to save settings regularly
3. Consider cloud sync (not yet implemented)

**Prevention:**
- Don't clear browsing data while using the app
- Log out properly (don't just close browser)
- Use persistent browser if possible

---

## Advanced Debugging

### Enable Debug Logging
Add to browser console:
```javascript
// Log all API calls
const originalFetch = window.fetch;
window.fetch = function(...args) {
  console.log("API Call:", args[0], args[1]);
  return originalFetch.apply(this, args);
};
```

### Check Backend Logs
```bash
# Docker
docker logs atv-backend -f --tail 100

# Systemd
journalctl -u atv -f -n 100

# Direct (if running locally)
# Check terminal where uvicorn is running
```

### Monitor Network Traffic
1. Open DevTools (F12)
2. Go to Network tab
3. Reload page
4. Look for:
   - Failed requests (red)
   - Slow requests (>1s)
   - Large responses

### Check Browser Storage
1. Open DevTools (F12)
2. Go to Application → Storage
3. Check:
   - localStorage: atv_jwt, atv_token, atv_user
   - sessionStorage
   - IndexedDB

---

## Getting Help

### Information to provide when reporting issues:
1. **Browser:** Chrome 120, Safari 17, etc.
2. **Device:** Desktop/Mobile, OS version
3. **Error message:** Exact message from screen or console
4. **Reproduction steps:** How to reproduce the issue
5. **Console errors:** Paste from DevTools → Console
6. **Network errors:** Screenshot of Network tab

### Resources:
- **API Docs:** See comments in `auth/router.py`, `main.py`
- **Architecture:** See `README.md`
- **Database Schema:** See `db/models.py`
- **Environment:** See `.env.example`

---

## FAQ

**Q: Can I have multiple accounts?**
A: Yes, one email account and multiple Telegram accounts can exist. Email/Telegram/Google are separate auth methods.

**Q: How long do tokens last?**
A: JWT tokens expire after 30 days. Use refresh token endpoint to get new one (if implemented).

**Q: Is my data encrypted?**
A: Passwords are hashed with bcrypt. Data in transit uses HTTPS. Data at rest not encrypted (consider adding).

**Q: What if I forget my password?**
A: No password reset implemented yet. Contact support to reset.

**Q: Can I delete my account?**
A: No account deletion implemented yet. Contact support.

**Q: Why do I need to authorize the bot?**
A: Telegram bot needs permission to send you messages and access your Mini App.

---

## Reporting Bugs

When reporting a bug, include:

1. Steps to reproduce
2. Expected behavior
3. Actual behavior
4. Browser console errors (copy full output)
5. Network tab screenshot
6. Environmental info (browser, OS, device)

Example:
```
Steps:
1. Register account
2. Go to indicators
3. Click "Momentum" filter
4. Wait 5 seconds

Expected: Indicators filter to momentum only
Actual: "No indicators match" appears
Error: Console shows "HTTP 500" on /api/indicators call

Browser: Chrome 120
OS: Windows 11
```

---

## Performance Metrics

Check these in DevTools → Network tab:

| Metric | Good | Warning | Bad |
|--------|------|---------|-----|
| Page Load | <2s | 2-5s | >5s |
| API Response | <1s | 1-3s | >3s |
| Sheet Animation | 200-300ms | 300-500ms | >500ms |
| Indicator Load | <2s | 2-5s | >5s |
| Screenshot Capture | <3s | 3-10s | >10s |

If metrics are in "Bad" range, report it as a performance issue.
