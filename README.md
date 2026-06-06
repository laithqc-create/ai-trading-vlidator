# AI Trade Validator (ATV)

AI-powered trading analysis platform — Telegram Mini App, Chrome extension, MT4/MT5/cTrader EA bots, and a no-code App Builder.

## Products

| Product | Description | Connection method |
|---|---|---|
| **Signal Validator** | Validate TradingView / indicator signals before entry | Webhook POST |
| **EA Analyzer** | AI analysis on every MT4/MT5/cTrader trade | EA bot → OHLC webhook |
| **Manual Validator** | Screenshot-based AI chart analysis | Chrome extension |
| **App Builder** | Agentic AI code generator for trading apps | Mini App chat |
| **Marketplace** | Sell/rent/share built apps | Whop integration |

---

## Quick Start (Docker)

### 1. Clone and configure

```bash
git clone https://github.com/laithqc-create/ai-trading-vlidator.git
cd ai-trading-vlidator
cp .env.example .env
# Edit .env with your API keys (see Configuration below)
```

### 2. Start everything

```bash
docker compose up -d
```

This starts: PostgreSQL, Redis, FastAPI app (port 8000), Celery worker, Celery beat, Nginx (ports 80/443).

### 3. Register Telegram webhook

```bash
curl http://localhost:8000/setup-webhook
```

### 4. Open the Mini App

Set your Telegram Bot's menu button URL to `https://your-domain.com/app`.

---

## Configuration (`.env`)

```env
# Core
DATABASE_URL=postgresql+asyncpg://trader:trader_pass@db:5432/tradevalidator
REDIS_URL=redis://redis:6379/0

# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_WEBHOOK_URL=https://your-domain.com/telegram/webhook

# DeepSeek AI
DEEPSEEK_API_KEY=your_deepseek_key
DEEPSEEK_MODEL=deepseek-chat

# Whop (payments)
WHOP_API_KEY=your_whop_api_key
WHOP_WEBHOOK_SECRET=your_whop_webhook_secret
WHOP_AFFILIATE_URL=https://whop.com/your-product/affiliate
WHOP_PRODUCT1_URL=https://whop.com/checkout/plan_xxx   # Signal Validator
WHOP_PRODUCT2_URL=https://whop.com/checkout/plan_yyy   # EA Analyzer
WHOP_PRODUCT3_URL=https://whop.com/checkout/plan_zzz   # Manual Validator
WHOP_PRO_URL=https://whop.com/checkout/plan_pro        # Pro Bundle

# Optional: RAGFlow (for crowd insights KB)
RAGFLOW_API_KEY=
RAGFLOW_SYSTEM_KB_ID=
```

---

## Architecture

```
User (Telegram)
  │
  ├─ Mini App (miniapp/index.html)         ← served at /app
  │    ├─ Signal Validator tab             ← calls /api/user/last-report?source=indicator
  │    ├─ EA Analyzer tab                  ← calls /api/user/last-report?source=ea
  │    ├─ App Builder tab                  ← calls /api/appbuilder/projects
  │    └─ Marketplace tab                  ← calls /api/marketplace
  │
  ├─ Chrome Extension (extension/)         ← screenshot → /webhook/screenshot/{token}
  │
  ├─ EA Bots (bots/)
  │    ├─ MT5: ATV_Analyzer.mq5            ← candles → /api/ohlc/analyze
  │    ├─ MT4: ATV_Analyzer.mq4
  │    └─ cTrader: ATV_Analyzer.cs
  │
  └─ TradingView / Indicators              ← /webhook/indicator/{token}

FastAPI Backend (main.py)
  ├─ /webhook/indicator/{token}            ← Product 1: signal validation
  ├─ /webhook/ea/{token}                   ← Product 2: EA trade logging
  ├─ /webhook/screenshot/{token}           ← Product 3: chart screenshot analysis
  ├─ /api/ohlc/analyze                     ← OHLC candle analysis (EA bots)
  ├─ /api/user/*                           ← user plan, tokens, reports, stats
  ├─ /api/trial/*                          ← 14-day trial management
  ├─ /api/marketplace/*                    ← app marketplace
  ├─ /api/appbuilder/*                     ← agentic app builder
  ├─ /api/patterns/*                       ← per-user pattern rule overrides
  ├─ /api/indicators/*                     ← indicator preferences
  ├─ /api/checkout/{plan}                  ← Whop checkout redirect
  ├─ /webhook/whop                         ← Whop purchase/cancellation events
  └─ /app, /app/indicators, /app/pattern-rules  ← Mini App static pages

Celery Workers
  ├─ validate_indicator_task               ← async AI validation + Telegram notify
  ├─ analyze_ea_task                       ← async EA analysis + Telegram notify
  ├─ reset_daily_counters (midnight)       ← free tier counter reset
  ├─ expire_stale_validations (hourly)     ← clean up stuck validations
  ├─ expire_trials_task (02:00 UTC)        ← downgrade expired trials
  └─ aggregate_crowd_insights (weekly)     ← anonymized win/loss stats
```

---

## Database

Migrations are run automatically by Docker Compose on startup via Alembic.

To run manually:
```bash
alembic upgrade head
```

Tables: `users`, `validations`, `user_rules`, `ea_logs`, `analysis_reports`, `app_projects`, `app_build_steps`, `marketplace_listings`, `marketplace_purchases`, `marketplace_reviews`, `user_indicator_prefs`, `user_pattern_rules`.

---

## Telegram Bot Commands

| Command | Description |
|---|---|
| `/start` | Welcome + trial offer for new users |
| `/help` | Full command list |
| `/status` | Plan, trial days, validation count |
| `/subscribe` | Upgrade plans with Whop checkout |
| `/history` | Last 10 signal validations |
| `/connect_indicator` | Webhook URL + payload format |
| `/connect_ea` | EA analyzer token |
| `/connect_extension` | Chrome extension token |
| `/tokens` | All tokens at once |
| `/my_rules` | Personal trading rules |
| `/add_rule` | Add a rule (inline or FSM) |
| `/delete_rule <n>` | Remove rule by number |
| `/trial` | Start/check 14-day free trial |
| `/build` | Open App Builder in chat |

---

## Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run backend locally
uvicorn main:app --reload

# Run bot locally (polling)
python -m TG_Bot.main

# Run Celery worker
celery -A workers.celery_app.celery_app worker --loglevel=info

# Run tests
pytest tests/ -v
```

---

## EA Bot Setup

1. Download from Mini App → Signal Validator → Setup tab, or `/api/download/ATV_Analyzer.mq5`
2. Open in MetaEditor
3. Set `WebhookToken` input to your EA token (from `/connect_ea` or Mini App tokens tab)
4. Set `ServerURL` to your backend URL
5. Attach to any chart — AI analysis draws on chart after each candle close

---

## Chrome Extension Setup

1. Download from `/api/download/extension.zip`
2. Chrome → Extensions → Load unpacked → select extracted folder
3. Open the side panel, go to Settings, paste your screenshot token (from `/connect_extension`)
4. Extension auto-captures screenshots at candle close on any chart page

---

## Payments (Whop)

1. Create products on [Whop](https://whop.com) for each plan tier
2. Add checkout URLs to `.env` (`WHOP_PRODUCT1_URL`, etc.)
3. Set Whop webhook URL to `https://your-domain.com/webhook/whop`
4. Set `WHOP_WEBHOOK_SECRET` in `.env`

Whop events handled: `membership.went_valid` (activate), `membership.went_invalid` (cancel/expire), `membership.was_refunded` (cancel).
