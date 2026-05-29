@echo off
:: ═══════════════════════════════════════════════════
::  AI Trade Validator — One-click setup
::  Double-click this file to configure your session
:: ═══════════════════════════════════════════════════

echo.
echo  AI Trade Validator Setup
echo  ════════════════════════
echo.

:: Ask for Cloudflare URL
set /p CF_URL="Paste your Cloudflare URL (e.g. https://abc-xyz.trycloudflare.com): "

:: Strip trailing slash if present
if "%CF_URL:~-1%"=="/" set CF_URL=%CF_URL:~0,-1%

echo.
echo Writing .env with URL: %CF_URL%

:: Write the full .env file
python -c "
import sys
cf = sys.argv[1]
env = f'''TELEGRAM_BOT_TOKEN=8627310044:AAHNgygMOfPWZNDOgpyl8YhO35JVRQScKNU
TELEGRAM_WEBHOOK_URL={cf}/webhook/telegram
DATABASE_URL=sqlite+aiosqlite:///./local_dev.db
REDIS_URL=redis://localhost:6379/0
DEEPSEEK_API_KEY=sk-4fcc501132634b5d8b9cb0a28d47bf3c
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_COST_PER_GEN=0.002
API_BASE_URL={cf}
MINIAPP_BASE_URL={cf}/app
APP_ENV=development
APP_SECRET_KEY=local-dev-secret
WHOP_PRODUCT1_URL=https://whop.com
WHOP_PRODUCT2_URL=https://whop.com
WHOP_PRODUCT3_URL=https://whop.com
WHOP_PRO_URL=https://whop.com
WHOP_AFFILIATE_URL=https://whop.com
WHOP_WEBHOOK_SECRET=
WHOP_API_KEY=
POLYGON_API_KEY=
MT4_DOWNLOAD_URL={cf}/api/download/ATV_Analyzer.mq4
MT5_DOWNLOAD_URL={cf}/api/download/ATV_Analyzer.mq5
CTRADER_DOWNLOAD_URL={cf}/api/download/ATV_Analyzer.cs
RAGFLOW_BASE_URL=http://localhost:9380
RAGFLOW_API_KEY=
POSTGRES_USER=trader
POSTGRES_PASSWORD=trader_pass
POSTGRES_DB=tradevalidator
'''
open('.env', 'w', encoding='utf-8').write(env)
open('local_dev.env', 'w', encoding='utf-8').write(env)
print('Done')
" "%CF_URL%"

echo.
echo  ✓ .env written
echo.
echo  ════════════════════════════════════════
echo  Mini App URL:
echo  %CF_URL%/app
echo  ════════════════════════════════════════
echo.
echo  Now go to BotFather and set Menu Button URL to:
echo  %CF_URL%/app
echo.
echo  Then run in a new CMD window:
echo  uvicorn main:app --port 8000
echo.
pause
