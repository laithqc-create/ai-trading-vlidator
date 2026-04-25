# AI Trade Validator — Telegram Bot

A Telegram-based AI trading advisor that validates trading signals using:
- **OpenTrade.ai** (The Trader) — LangGraph multi-agent technical analysis
- **RAGFlow** (The Mentor) — knowledge base, rules, historical context

## Products
| # | Product | Price | Input |
|---|---------|-------|-------|
| 1 | Indicator Validator | $29/mo | TradingView webhook |
| 2 | EA Analyzer | $49/mo | EA log file |
| 3 | Manual Validator | $19/mo | `/check AAPL BUY 175` |

## Quick Start

```bash
# 1. Clone and configure
cp .env.example .env
# Fill in your API keys in .env

# 2. Start all services
docker compose up -d

# 3. Set Telegram webhook
python scripts/set_webhook.py
```

## Architecture
```
Telegram User
     ↓
FastAPI Webhook Server (port 8000)
     ↓
Celery Worker (async processing)
     ↓
┌──────────────────┬──────────────────┐
│  OpenTrade.ai    │    RAGFlow       │
│  (The Trader)    │   (The Mentor)   │
│  - Yahoo Finance │  - User rules    │
│  - RSI/MACD/BB   │  - History KB    │
│  - 8 AI agents   │  - RAG context   │
└──────────────────┴──────────────────┘
     ↓
Telegram Bot sends result to user
```

## Stack
- **Bot**: python-telegram-bot 20.x
- **API**: FastAPI + Uvicorn
- **Queue**: Celery + Redis
- **AI (Trader)**: OpenTrade.ai (LangGraph + local LLM via Ollama)
- **AI (Mentor)**: RAGFlow (Docker, self-hosted)
- **Market Data**: Yahoo Finance (Products 1 & 2), Polygon.io (Product 3)
- **Payments**: Stripe
- **DB**: PostgreSQL (users/subscriptions), Redis (cache/queue)
