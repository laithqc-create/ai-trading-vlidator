# Indicators Window Fix — June 13, 2026

## Problem
**Screenshot Issue:** The indicator settings panel shows "No indicators match." instead of displaying all 26 built-in MetaTrader indicators (RSI, MACD, Stochastic, etc.).

## Root Cause Analysis
The indicator selector was empty because:

1. **Authentication Required:** The `/api/indicators` endpoint had `require=True` in `resolve_user()`, meaning unauthenticated users got a 401 error.
2. **Silent Failure:** The frontend's `load()` function wasn't checking response status or showing errors properly, so it silently failed and displayed "No indicators match."
3. **Telegram Mini App Issue:** If the page was accessed from a browser (not Telegram Mini App), no auth headers were being sent, causing the auth failure.

## What Was Fixed

### 1. **Made `/api/indicators` endpoint work with optional authentication**
   - **File:** `pattern_editor/endpoints.py` (line 99)
   - **Change:** Changed `resolve_user(request, db, require=True)` → `resolve_user(request, db, require=False)`
   - **Effect:** Unauthenticated users now get all 26 indicators with system defaults
   - **Authenticated users:** Can still save their preferences

### 2. **Improved error handling in frontend**
   - **File:** `miniapp/indicator_selector.html` (lines 128-152)
   - **Changes:**
     - Check HTTP response status (`if (!res.ok)`)
     - Show actual error messages instead of generic "Failed to load"
     - Log API response for debugging when it returns 0 indicators
   - **Effect:** Users now see "Failed to load: HTTP 401: ..." instead of silent failure

### 3. **Fixed Telegram Mini App WebApp initialization**
   - **File:** `miniapp/indicator_selector.html` (lines 120-126)
   - **Change:** Added explicit `window.Telegram.WebApp.ready()` call before loading
   - **Effect:** Ensures Telegram Mini App is fully initialized before trying to read `initDataUnsafe.user.id`

## Technical Details

### Indicators Engine (26 total)
```
Momentum (10):     RSI, Stochastic, Stoch RSI, MACD, CCI, Awesome Oscillator, Momentum, Williams %R, Ultimate Oscillator, Rate of Change
Trend (8):         Moving Average, Bollinger Bands, ADX, Ichimoku Cloud, Parabolic SAR, Supertrend, Keltner Channels, MA Ribbon
Volume (4):        OBV, VWAP, A/D Line, CMF
Volatility (4):    ATR, Donchian Channels, Aroon, Pivot Points
```

### Response Structure (from `/api/indicators`)
```javascript
{
  ok: true,
  indicators: [
    {
      name: "rsi",
      display: "RSI",
      group: "momentum",
      enabled: true,
      defaults: { period: 14 },
      settings: {}
    },
    // ... 25 more indicators
  ],
  groups: {
    momentum: { label: "Momentum & Oscillators", names: [...] },
    // ... other groups
  }
}
```

## Testing

To verify the fix works:

1. **Access the indicator settings page:**
   - Via Telegram Mini App: `/app/indicators` (with Mini App context)
   - Via browser: Navigate to any route that includes the indicator selector

2. **Expected behavior:**
   - Page should load with spinner briefly
   - Then display all 26 indicators in 4 groups
   - Categories (All, Momentum, Trend, Volume, Volatility) should filter properly
   - Without authentication: can view but can't save changes
   - With authentication: can toggle and save preferences

3. **Error handling:**
   - If backend is down: "Failed to load: Failed to fetch"
   - If auth fails: "Failed to load: HTTP 401: ..."
   - If API returns error: "Failed to load: API returned error"

## Impact on Other Systems

✅ **No breaking changes:**
- Authentication system still works as before
- Authenticated users' saved preferences are unaffected
- All other endpoints remain unchanged

✅ **Benefits:**
- Users can now view indicators without registration (good UX)
- Clearer error messages for debugging
- Telegram Mini App initialization more reliable

## Files Changed
- `pattern_editor/endpoints.py` — Made auth optional for GET
- `miniapp/indicator_selector.html` — Better error handling & Telegram init
- `PROGRESS.md` — Updated documentation

## Commits
- `4bb7880` — Error handling improvements
- `7f2e7de` — Indicators endpoint + Telegram init fix
- `fe4500b` — Progress update

## Next Steps

1. **Test in production/staging** to verify indicators display correctly
2. **Investigate remaining issues:**
   - Profile sheet buttons (Edit billing, Change password)
   - Auth registration flow (tokens may or may not be generating)
   - Distinct user creation

3. **Security:** Rotate exposed GitHub PAT & API keys on Render dashboard
