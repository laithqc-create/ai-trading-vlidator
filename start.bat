@echo off
echo Starting AI Trade Validator...

cd /d "D:\disktop\Desktop\ai vali\ai-trading-vlidator"

:: Step 1: Start cloudflared in background and capture URL
echo [1/3] Starting Cloudflare tunnel...
start "cloudflared" /min cmd /c ""C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --url http://localhost:8000 > cloudflared.log 2>&1"

:: Wait for tunnel to establish
echo Waiting for tunnel URL...
timeout /t 12 /nobreak >nul

:: Extract URL from log
for /f "tokens=*" %%a in ('findstr "trycloudflare.com" cloudflared.log') do set LINE=%%a
for /f "tokens=2 delims=|" %%b in ("%LINE%") do set TUNNEL_URL=%%b
for /f "tokens=*" %%c in ("%TUNNEL_URL%") do set TUNNEL_URL=%%c

:: Fallback: parse more carefully
for /f "delims=" %%i in ('type cloudflared.log ^| findstr /i "https://.*trycloudflare"') do set RAWLINE=%%i
for /f "tokens=1* delims=https://" %%a in ("%RAWLINE%") do set PARTIAL=%%b
for /f "tokens=1" %%a in ("%PARTIAL%") do set DOMAIN=%%a
set TUNNEL_URL=https://%DOMAIN%

echo Tunnel URL: %TUNNEL_URL%

:: Step 2: Update .env
echo [2/3] Updating .env...
python -c "
import re, sys
url = sys.argv[1]
with open('.env', 'r') as f: content = f.read()
content = re.sub(r'TELEGRAM_WEBHOOK_URL=.*', f'TELEGRAM_WEBHOOK_URL={url}/webhook', content)
with open('.env', 'w') as f: f.write(content)
print('  .env updated: ' + url + '/webhook')
" "%TUNNEL_URL%"

:: Step 3: Update BotFather menu button
echo [3/3] Updating Telegram menu button...
python scripts/update_menu_button.py "%TUNNEL_URL%"

:: Step 4: Start FastAPI
echo Starting FastAPI...
start "uvicorn" cmd /k "cd /d "D:\disktop\Desktop\ai vali\ai-trading-vlidator" && uvicorn main:app --port 8000"

timeout /t 3 /nobreak >nul

:: Step 5: Start Bot
echo Starting Bot...
start "bot" cmd /k "cd /d "D:\disktop\Desktop\ai vali\ai-trading-vlidator" && python TG_Bot/main.py"

echo.
echo ✅ All services started!
echo    Tunnel: %TUNNEL_URL%
echo    Mini App: %TUNNEL_URL%/app
echo.
pause
