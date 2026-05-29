@echo off
:: ═══════════════════════════════════════════════════
::  AI Trade Validator — Start server
::  Run AFTER setup.bat and after Cloudflare is running
:: ═══════════════════════════════════════════════════
echo Starting AI Trade Validator...
echo.
uvicorn main:app --port 8000
pause
