"""
Run this once after starting cloudflared to register the Mini App button.
Usage: python scripts/update_menu_button.py https://your-tunnel.trycloudflare.com
"""
import sys, asyncio
from aiogram import Bot
from aiogram.types import MenuButtonWebApp, WebAppInfo

async def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/update_menu_button.py <tunnel_base_url>")
        print("Example: python scripts/update_menu_button.py https://abc.trycloudflare.com")
        sys.exit(1)

    base = sys.argv[1].rstrip("/")
    app_url = f"{base}/app"

    import os
    from dotenv import load_dotenv
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("ERROR: TELEGRAM_BOT_TOKEN not found in .env")
        sys.exit(1)

    bot = Bot(token=token)
    await bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(text="Open App", web_app=WebAppInfo(url=app_url))
    )
    print(f"✅ Menu button set to: {app_url}")
    await bot.session.close()

asyncio.run(main())
