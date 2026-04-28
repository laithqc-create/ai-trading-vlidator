# AI Trade Validator — Browser Extension

Capture TradingView charts with one click and validate trades with AI.

## Supported Browsers
- Chrome (primary, MV3)
- Edge (Chromium-based, same files)
- Firefox (MV3 with minor adaptation — see Firefox section)

## File Structure
```
extension/
├── manifest.json          Extension manifest v3
├── popup.html             3-step popup UI
├── popup.js               Screenshot capture, polling, result display
├── background.js          Service worker (badge, context menu)
├── content.js             TradingView DOM: ticker + price detection
├── styles.css             Dark theme UI (Catppuccin Mocha)
├── generate_icons.py      Generates PNG icons from Python (Pillow)
├── icons/
│   ├── icon16.png         16×16 toolbar icon
│   ├── icon48.png         48×48 extension management
│   └── icon128.png        128×128 Chrome Web Store
└── README.md              This file
```

## Development Setup

### 1. Generate icons (if not already generated)
```bash
cd extension/
python3 generate_icons.py
```

### 2. Update API URL
Edit `popup.js` — change `DEFAULT_API_URL`:
```js
const DEFAULT_API_URL = "https://your-actual-domain.com";
```
Or set it via the in-extension Settings panel after loading.

### 3. Load in Chrome
1. Go to `chrome://extensions/`
2. Enable **Developer mode** (top right toggle)
3. Click **Load unpacked**
4. Select the `extension/` folder
5. The extension icon appears in your toolbar

### 4. Test locally with ngrok
```bash
# Terminal 1: Start backend
docker compose up -d

# Terminal 2: Expose via ngrok
ngrok http 8000

# Copy the https URL → paste into extension Settings panel
```

### 5. Test the flow
1. Navigate to any TradingView chart (e.g. https://www.tradingview.com/chart/)
2. Click the extension icon
3. Click **📸 Capture TradingView Chart**
4. Confirm ticker and signal
5. Click **🚀 Submit for AI Analysis**
6. Wait 30-60 seconds for result

## User Flow
```
Step 1  Capture
  ↓ chrome.tabs.captureVisibleTab()
  ↓ content.js detects ticker from DOM / URL / page title
  ↓ Screenshot preview shown

Step 2  Confirm
  ↓ User verifies ticker, signal (BUY/SELL/HOLD), optional price

Step 3  Analyze
  ↓ POST /webhook/screenshot (multipart: image + ticker + signal + user_id)
  ↓ Backend queues Celery task
  ↓ Extension polls GET /webhook/screenshot/result/{request_id} every 2s
  ↓ Result: CONFIRM ✅ / CAUTION ⚠️ / REJECT ❌ + confidence + reasoning
```

## Backend Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/webhook/screenshot` | Submit screenshot for analysis |
| GET | `/webhook/screenshot/result/{id}` | Poll for result |

### POST payload (multipart/form-data)
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| screenshot | File | Yes | PNG/JPEG, max 10 MB |
| ticker | string | Yes | e.g. "AAPL" |
| signal | string | Yes | BUY / SELL / HOLD |
| price | string | No | Entry price |
| user_id | string | Yes | Generated locally, stored in chrome.storage |

### GET response
```json
{
  "status": "completed",
  "verdict": "CONFIRM",
  "confidence_score": 0.78,
  "reasoning": "RSI 28 — oversold. MACD bullish crossover.",
  "trader_analysis": { "rsi": 28.4, "macd": 0.12, ... },
  "completed_at": "2026-04-26T10:30:00"
}
```

## Rate Limits
- 20 screenshot submissions per minute per user_id
- Returns HTTP 429 if exceeded

## Error Handling
| Error | Cause | User sees |
|-------|-------|-----------|
| "Not on TradingView" | Wrong tab | Warning banner, capture disabled |
| Invalid ticker | Empty or non-alphanumeric | Red input border + hint |
| HTTP 429 | Rate limit | Error message in popup |
| Timeout (2 min) | Analysis stuck | "Timed out — check Telegram" message |
| Network error | API unreachable | Retry button |

## Firefox Adaptation
Firefox MV3 has minor differences:
1. Replace `chrome.*` with `browser.*` (or use WebExtensions polyfill)
2. `captureVisibleTab` requires explicit permission grant in Firefox
3. Submit to Firefox Add-ons: https://addons.mozilla.org/developers/

```bash
# Install polyfill
# Add to extension/lib/browser-polyfill.min.js
# Load in manifest.json content_scripts before content.js
```

## Chrome Web Store Submission
1. Zip the extension folder: `zip -r extension.zip extension/ -x "*.py" -x "__pycache__/*"`
2. Go to https://chrome.google.com/webstore/devconsole
3. Pay one-time $5 developer fee
4. Upload zip → fill store listing → submit for review (~3-7 days)

## Privacy Policy (required for store)
The extension:
- Captures screenshots **only** when the user clicks the button (no automation)
- Sends screenshot to your own backend for AI analysis
- Stores only a generated anonymous user_id locally
- Does not collect names, emails, or browsing history
- No data sold to third parties

## Changelog
### v1.0.0
- Initial release
- 3-step popup (capture → confirm → result)
- Auto-detection of ticker from TradingView DOM/URL/title
- Confidence bar + indicator chips in result view
- Copy result to clipboard
- Settings panel (API URL + Telegram bot name)
- Analysis history stored locally (last 50)
- Context menu: right-click → Capture & Validate
- Badge notification on completion
