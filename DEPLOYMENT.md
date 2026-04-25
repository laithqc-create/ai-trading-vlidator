# Deployment Guide — AI Trade Validator

## Target VPS Specs
| Component | Minimum | Recommended |
|-----------|---------|-------------|
| RAM | 8 GB | 16 GB |
| CPU | 2 vCores | 4 vCores |
| Disk | 50 GB SSD | 100 GB SSD |
| OS | Ubuntu 22.04 | Ubuntu 22.04 |
| Cost | ~$30/mo | ~$60/mo |

Providers: Hetzner (cheapest), DigitalOcean, Vultr, Contabo

---

## Step 1 — VPS Initial Setup

```bash
# As root
apt update && apt upgrade -y
apt install -y docker.io docker-compose git curl nginx certbot python3-certbot-nginx

# Create deploy user
useradd -m -s /bin/bash deploy
usermod -aG docker deploy
su - deploy
```

---

## Step 2 — Clone the Repo

```bash
git clone https://github.com/laithqc-create/ai-trading-vlidator.git
cd ai-trading-vlidator
cp .env.example .env
nano .env   # Fill in all required values
```

---

## Step 3 — Configure Environment

Required values in `.env`:
```
TELEGRAM_BOT_TOKEN=      # From @BotFather
TELEGRAM_WEBHOOK_URL=    # https://your-domain.com/webhook/telegram
POLYGON_API_KEY=         # From polygon.io (for Product 3)
STRIPE_SECRET_KEY=       # From Stripe Dashboard
STRIPE_WEBHOOK_SECRET=   # From Stripe → Developers → Webhooks
```

Optional (for full AI pipeline):
```
LLM_PROVIDER=ollama      # or openai
LLM_MODEL=llama3         # or gpt-4o-mini
RAGFLOW_API_KEY=         # From RAGFlow UI after first start
```

---

## Step 4 — Set Up Nginx + SSL

```bash
# /etc/nginx/sites-available/tradevalidator
server {
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 120s;
    }
}

# Enable site
ln -s /etc/nginx/sites-available/tradevalidator /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx

# Get SSL certificate
certbot --nginx -d your-domain.com
```

---

## Step 5 — Start Services

### Option A: Without RAGFlow (8 GB VPS, bot + DB + Redis only)

```bash
docker compose up -d postgres redis
sleep 5
docker compose up -d api worker
```

### Option B: Full Stack with RAGFlow (16 GB VPS)

```bash
docker compose --profile full up -d
```

RAGFlow UI will be available at `http://your-domain.com:9380`  
On first run: create admin account → copy API key → add to `.env`

---

## Step 6 — Run Setup Script

```bash
docker compose exec api python scripts/setup.py
```

This will:
- ✅ Register the Telegram webhook
- ✅ Seed the system knowledge base in RAGFlow
- ✅ Test all connections (Ollama, RAGFlow, Polygon, Redis, Postgres)

---

## Step 7 — Install Ollama + LLM Model

Ollama runs the LLM locally for OpenTrade.ai:

```bash
# Install Ollama on the host (outside Docker for GPU access)
curl -fsSL https://ollama.com/install.sh | sh

# Pull a model (pick based on your RAM)
ollama pull llama3          # 8GB RAM — good quality
ollama pull mistral         # 6GB RAM — faster
ollama pull phi3            # 4GB RAM — lightweight

# Ollama listens on localhost:11434 by default
# Update OLLAMA_BASE_URL in .env if needed
```

Alternatively, use OpenAI API (no GPU needed):
```
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...
```

---

## Step 8 — Configure Stripe

1. Create products in Stripe Dashboard → Products
2. Create 4 recurring prices: $19, $29, $49, $79/mo
3. Copy price IDs into `.env`
4. Add webhook endpoint: `https://your-domain.com/webhook/stripe`
5. Events to listen to:
   - `checkout.session.completed`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.payment_failed`
6. Copy webhook signing secret → `STRIPE_WEBHOOK_SECRET` in `.env`

---

## Step 9 — Verify Everything Works

```bash
# Check all containers running
docker compose ps

# View logs
docker compose logs -f api
docker compose logs -f worker

# Test bot
# Open Telegram → your bot → /start
# Try: /check AAPL BUY
```

---

## Monitoring & Maintenance

```bash
# View worker queue
docker compose exec redis redis-cli llen celery

# Restart services
docker compose restart api worker

# Update code
git pull
docker compose build api worker
docker compose up -d api worker

# Database migrations after code update
docker compose exec api alembic upgrade head
```

---

## Scaling Notes

- **CPU bottleneck**: Add more Celery workers: `--concurrency=8`
- **RAM bottleneck**: Move RAGFlow to separate VPS, set `RAGFLOW_BASE_URL` to its IP
- **LLM bottleneck**: Switch to OpenAI API (`LLM_PROVIDER=openai`) for faster responses
- **Cost optimization**: Hetzner CX31 (8GB/2vCPU) = €8/mo — enough for bot + DB + Redis
