# ATV Deployment Checklist

Last updated: June 13, 2026

## ✅ Code Quality

- [x] All auth utilities tested (passwords, tokens, JWT)
- [x] Error handling improved across frontend
- [x] Indicators endpoint works with optional auth
- [x] Profile sheet buttons have proper error messages
- [x] 8/8 unit tests passing
- [x] No console errors in frontend
- [x] All endpoints documented in code comments

## 🔐 Security Checklist

### CRITICAL — Must do before production

- [ ] **Rotate exposed credentials:**
  - [ ] Telegram bot token (exposed in GitHub commit)
  - [ ] DeepSeek API key (exposed in GitHub commit)
  - **Action:** Update `TELEGRAM_BOT_TOKEN` and `DEEPSEEK_API_KEY` in Render dashboard
  
- [ ] **Verify environment variables:**
  - [ ] `JWT_SECRET` is strong (32+ chars, random)
  - [ ] `WHOP_API_KEY` is set (for payments)
  - [ ] Database credentials are secure
  - [ ] All API keys are NOT in code, only in env vars

- [ ] **Check SSL/TLS:**
  - [ ] HTTPS enabled on production domain
  - [ ] SSL certificate is valid and auto-renewed

- [ ] **Database security:**
  - [ ] PostgreSQL has strong password
  - [ ] Database backups are configured
  - [ ] No test data in production

### High Priority

- [ ] **Telegram bot:**
  - [ ] Bot username correct in env var
  - [ ] Menu URL points to production domain
  - [ ] Webhook URL is production domain
  - [ ] Webhook secret is strong

- [ ] **Whop integration:**
  - [ ] Product IDs are real (not placeholders)
  - [ ] Affiliate URL is correct
  - [ ] Webhook endpoint is secured

- [ ] **Rate limiting:**
  - [ ] Auth endpoints have rate limiting
  - [ ] API endpoints have rate limiting
  - [ ] Webhook endpoints are protected

## 📋 Configuration Checklist

### Required for MVP

- [ ] **Telegram:**
  - [ ] `TELEGRAM_BOT_TOKEN` — set to real bot token
  - [ ] `TELEGRAM_BOT_USERNAME` — set to bot username (e.g., AITradeValidatorBot)
  - [ ] Webhook URL configured in Telegram
  - [ ] Menu button URL set to `/app`

- [ ] **Whop:**
  - [ ] `WHOP_API_KEY` — set to real API key
  - [ ] `WHOP_PRODUCT_ID_PRODUCT1` — set to real product ID
  - [ ] `WHOP_PRODUCT_ID_PRODUCT2` — set to real product ID
  - [ ] `WHOP_PRODUCT_ID_PRODUCT3` — set to real product ID
  - [ ] `WHOP_PRODUCT_ID_BUNDLE` — set to real product ID
  - [ ] `WHOP_AFFILIATE_URL` — set to affiliate checkout link

- [ ] **DeepSeek:**
  - [ ] `DEEPSEEK_API_KEY` — set to real API key (rotated)
  - [ ] API calls are error-wrapped (handles rate limits)

- [ ] **Google OAuth:**
  - [ ] `GOOGLE_CLIENT_ID` — set
  - [ ] `GOOGLE_CLIENT_SECRET` — set
  - [ ] Redirect URI configured in Google Console
  - [ ] Login page has Google button

- [ ] **Database:**
  - [ ] `DATABASE_URL` — PostgreSQL connection string
  - [ ] Database exists and migrations are run
  - [ ] Backups are configured

### Optional Features

- [ ] **RAGFlow:**
  - [ ] `RAGFLOW_API_KEY` — optional, for crowd insights
  - [ ] `RAGFLOW_SYSTEM_KB_ID` — optional

- [ ] **Polygon.io:**
  - [ ] `POLYGON_API_KEY` — optional, for live market data

## 🚀 Deployment Steps

### 1. Pre-deployment checks
```bash
# Verify auth tests pass
python3 test_auth_units.py

# Check environment variables
env | grep -E "TELEGRAM|WHOP|DEEPSEEK|JWT_SECRET"
```

### 2. Database setup
```bash
# Run migrations
alembic upgrade head

# Verify tables exist
psql $DATABASE_URL -c "\dt"
```

### 3. Start services
```bash
# If using Docker
docker compose up -d

# If using systemd
systemctl start atv
systemctl enable atv

# If using uvicorn
uvicorn main:app --port 8000 --host 0.0.0.0 --reload=false
```

### 4. Configure Telegram webhook
```bash
# Set webhook URL
curl "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook?url=https://your-domain.com/webhook/telegram"

# Verify webhook
curl "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getWebhookInfo"
```

### 5. Test endpoints
```bash
# Health check
curl https://your-domain.com/health

# Auth test
curl -X POST https://your-domain.com/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"TestPassword123"}'

# Indicators test
curl https://your-domain.com/api/indicators \
  -H "X-Telegram-User-Id: 12345"
```

### 6. Monitor
```bash
# Check logs
docker logs atv-backend -f
# or
journalctl -u atv -f

# Monitor metrics
curl https://your-domain.com/health
```

## 🧪 Testing After Deployment

### Manual tests
- [ ] **Register:** Create new email account, verify tokens saved to localStorage
- [ ] **Login:** Login with email/password, verify JWT works
- [ ] **Profile:** Open profile, verify name displays, test Edit/Change buttons
- [ ] **Indicators:** Open indicator selector, verify all 26 indicators load
- [ ] **Telegram:** Send `/start` to bot, verify auth token generated
- [ ] **Chrome Extension:** Verify it loads and can authenticate
- [ ] **Marketplace:** Verify product listing works
- [ ] **Trial:** Verify trial start endpoint works

### Automated tests
```bash
# Run all tests
pytest tests/ -v

# Run auth tests specifically
python3 test_auth_units.py
python3 test_auth_flow.py  # Requires database
```

## 📊 Monitoring & Maintenance

### Daily checks
- [ ] Backend is responding (health check)
- [ ] No error logs in past 24h
- [ ] Database disk usage is normal
- [ ] API rate limits not being hit

### Weekly checks
- [ ] User count trending (growth/retention)
- [ ] Trial conversion rate
- [ ] Payment processing success rate
- [ ] Telegram bot response time

### Monthly checks
- [ ] Database backup integrity
- [ ] SSL certificate expiry (should be auto-renewed)
- [ ] Dependencies security updates
- [ ] Cost review (cloud resources)

## 🔔 Alerts to Configure

- [ ] Backend is down (HTTP 5xx)
- [ ] Database connection lost
- [ ] API quota exceeded (Whop, Telegram, DeepSeek)
- [ ] Disk space low
- [ ] Authentication failures spike
- [ ] Webhook delivery failures

## 📝 Post-Deployment Documentation

Create/update:
- [ ] API documentation (Swagger/OpenAPI)
- [ ] Admin handbook (user management, refunds, etc.)
- [ ] Troubleshooting guide (common issues)
- [ ] Architecture diagram (deployment topology)
- [ ] Disaster recovery plan

## ✅ Sign-off Checklist

Before considering deployment "complete":

- [ ] All security items checked
- [ ] All configuration items set
- [ ] Manual tests passed
- [ ] Automated tests passed
- [ ] Monitoring configured
- [ ] Backups working
- [ ] Team trained on operations
- [ ] Runbook/playbook documented

---

## Notes for This Deployment

**Laith's notes:**
- Windows local dev in Erbil region
- Render.com deployment
- PostgreSQL + Redis
- Telegram Mini App primary interface
- Chrome extension secondary

**Known limitations:**
- Regional firewall may block some APIs (Telegram wrapped in try/except)
- No ARM64 Docker support (x86_64 only)
- Email SMTP not configured (check provider)

**Next priorities after deployment:**
1. Monitor user growth and bugs
2. Collect feedback on UI/UX
3. Optimize API performance
4. Add more patterns/indicators if needed
