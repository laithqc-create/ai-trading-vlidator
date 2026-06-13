# ATV Quick Reference Guide

## 🚀 Quick Start

### Local Development
```bash
# Setup
cd ai-trading-vlidator
pip install --break-system-packages -r requirements.txt

# Start backend
uvicorn main:app --port 8000 --reload

# Start Telegram webhook (in another terminal)
cloudflared.exe tunnel --url http://localhost:8000

# Run tests
python3 test_auth_units.py
```

### Configuration
```bash
# Copy example env
cp .env.example .env

# Edit .env with your values:
# - TELEGRAM_BOT_TOKEN (from BotFather)
# - WHOP_API_KEY (from Whop)
# - DATABASE_URL (PostgreSQL)
# - JWT_SECRET (random 32+ chars)
```

### Endpoints Reference
| Endpoint | Method | Purpose | Auth |
|----------|--------|---------|------|
| `/auth/register` | POST | Create account | None |
| `/auth/login` | POST | Login with email | None |
| `/auth/telegram` | POST | Login with Telegram | Telegram initData |
| `/auth/me` | GET | Get current user | JWT/Telegram/Token |
| `/auth/billing` | PATCH | Update billing | JWT/Telegram/Token |
| `/auth/change-password` | POST | Change password | JWT/Telegram/Token |
| `/api/indicators` | GET | Get all indicators | Optional |
| `/api/user/plan` | GET | Get user plan | JWT/Telegram/Token |
| `/api/user/stats` | GET | Get user statistics | JWT/Telegram/Token |
| `/api/user/tokens` | GET | Get user tokens | JWT/Telegram/Token |
| `/api/user/reports` | GET | Get analysis reports | JWT/Telegram/Token |
| `/health` | GET | Health check | None |

---

## 🔑 Key Components

### Authentication Methods
1. **Email/Password** — Traditional registration and login
2. **Telegram Mini App** — OAuth via Telegram initData
3. **Google OAuth** — Sign in with Google
4. **Extension Token** — Browser extension authentication

### Tokens Generated Per User
- `atv_api_token` — Master API token (for ext/apps)
- `indicator_webhook_token` — Indicator webhook auth
- `ea_webhook_token` — EA analyzer webhook auth
- `screenshot_webhook_token` — Screenshot webhook auth

### Database
- **Engine:** PostgreSQL (async)
- **Migrations:** Alembic
- **ORM:** SQLAlchemy 2.0
- **Models:** See `db/models.py`

### Frontend
- **Login:** `/app/login`
- **Main App:** `/app`
- **Indicators:** `/app/indicators`
- **Pattern Rules:** `/app/pattern-rules`
- **API Base:** Injected per request (dynamic domain)

---

## 🐛 Debug Commands

### Check Backend
```bash
# Health check
curl http://localhost:8000/health

# Test register
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@test.com","password":"Test1234","full_name":"Test"}'

# Test login
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@test.com","password":"Test1234"}'

# Test indicators (no auth)
curl http://localhost:8000/api/indicators

# Test indicators (with token)
curl http://localhost:8000/api/indicators \
  -H "X-Telegram-User-Id: 123456789"
```

### Check Database
```bash
# Connect
psql $DATABASE_URL

# List users
SELECT id, email, telegram_id, plan_tier FROM users;

# Check tokens
SELECT id, email, atv_api_token FROM users WHERE id = 1;

# Count test data
SELECT COUNT(*) FROM users;
SELECT COUNT(*) FROM trading_signals;
```

### Check Frontend
```javascript
// In browser console

// Check auth
console.log("JWT:", localStorage.getItem("atv_jwt")?.slice(0, 20) + "...");
console.log("User:", JSON.parse(localStorage.getItem("atv_user") || "{}"));

// Test API
fetch(API_BASE + "/api/indicators")
  .then(r => r.json())
  .then(d => console.log("Indicators:", d.indicators?.length || "ERROR"));

// Check headers
const H = {
  "Content-Type": "application/json",
  "Authorization": "Bearer " + localStorage.getItem("atv_jwt"),
};
console.log("Headers:", H);
```

---

## 📋 Indicators (26 Total)

### Momentum (10)
RSI, Stochastic, Stoch RSI, MACD, CCI, Awesome Oscillator, Momentum, Williams %R, Ultimate Oscillator, Rate of Change

### Trend (8)
Moving Average, Bollinger Bands, ADX, Ichimoku Cloud, Parabolic SAR, Supertrend, Keltner Channels, MA Ribbon

### Volume (4)
OBV, VWAP, A/D Line, CMF

### Volatility (4)
ATR, Donchian Channels, Aroon, Pivot Points

---

## 🔐 Security Checklist

Before deployment:
- [ ] Rotate Telegram bot token (currently exposed in GitHub)
- [ ] Rotate DeepSeek API key (currently exposed in GitHub)
- [ ] Set strong JWT_SECRET (32+ random chars)
- [ ] Enable SSL/HTTPS on production
- [ ] Configure CORS to your domain only
- [ ] Set database password to strong value
- [ ] Enable database backups
- [ ] Configure rate limiting
- [ ] Set up monitoring and alerts

---

## 🚨 Common Issues

| Issue | Solution |
|-------|----------|
| "No indicators match" | Check `/api/indicators` returns 200, verify API_BASE |
| Can't register | Check email format, password 8+ chars, email not taken |
| JWT expired | Logout and login again to refresh token |
| 401 Unauthorized | Check JWT in localStorage or Telegram user ID header |
| Database connection error | Verify DATABASE_URL, check if DB is running |
| CORS error | Check CORS_ORIGINS in .env includes your domain |
| Telegram Mini App not working | Ensure accessed from within Telegram app |

---

## 📊 Performance Targets

| Metric | Target |
|--------|--------|
| Page load | < 2 seconds |
| API response | < 1 second |
| Indicators load | < 2 seconds |
| Sheet animation | 200-300ms |
| Login flow | < 2 seconds |

---

## 🔗 Useful Links

- **GitHub:** https://github.com/laithqc-create/ai-trading-vlidator
- **Deployment:** https://ai-trading-vlidator.onrender.com
- **Telegram Bot:** BotFather on Telegram
- **Whop Dashboard:** https://dashboard.whop.com
- **Google Console:** https://console.cloud.google.com

---

## 📚 Documentation Files

| File | Purpose |
|------|---------|
| `README.md` | Project overview and architecture |
| `PROGRESS.md` | Development progress tracking |
| `DEPLOYMENT_CHECKLIST.md` | Deployment procedures |
| `FRONTEND_UX_GUIDE.md` | Frontend development guide |
| `TROUBLESHOOTING.md` | User-facing support guide |
| `INDICATORS_FIX_SUMMARY.md` | Technical details of indicator fix |
| `SESSION_SUMMARY_JUNE13.md` | This session's work summary |

---

## 🎯 One-Minute Startup

```bash
# 1. Install dependencies (if needed)
pip install --break-system-packages -r requirements.txt

# 2. Start database (if local)
# (Assuming PostgreSQL is running)

# 3. Run migrations
alembic upgrade head

# 4. Start backend
uvicorn main:app --port 8000

# 5. Start tunnel (for webhooks)
cloudflared.exe tunnel --url http://localhost:8000

# 6. Test
curl http://localhost:8000/health

# ✅ Ready to go!
```

---

## 🔄 Deployment One-Liner

```bash
# Push to main branch
git add -A && git commit -m "Deploy: $(date)" && git push origin main

# Render will auto-deploy on push
# Monitor: https://dashboard.render.com
```

---

## 📞 Support Matrix

| Issue Type | Tool | Location |
|------------|------|----------|
| Frontend errors | Browser DevTools | F12 → Console |
| API errors | Network tab | F12 → Network |
| Backend errors | Logs | `docker logs atv-backend` |
| Database errors | Logs | Check PostgreSQL logs |
| Telegram errors | Telegram logs | TG bot settings |
| Payment errors | Whop dashboard | https://dashboard.whop.com |

---

## ✅ Status Indicators

**System Status:**
- Backend: Check `/health` endpoint
- Database: Check PostgreSQL connection
- Telegram: Check webhook status via Telegram API
- Payment: Check Whop API key is valid
- Frontend: Check indicators load

**Quick Health Check:**
```bash
# All in one
curl http://localhost:8000/health && \
  curl http://localhost:8000/api/indicators | jq '.ok' && \
  echo "✅ System OK"
```

---

**Last Updated:** June 13, 2026
**Status:** Production-ready (pending credential rotation)
