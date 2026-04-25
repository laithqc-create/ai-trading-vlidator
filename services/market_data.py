"""
Polygon.io market data service — used for Product 3 (Manual Validator).

Provides current OHLCV data for the AI analysis pipeline.
Polygon.io is a licensed data provider ($29-199/mo) — legal for commercial use.
"""
import httpx
from typing import Optional
from loguru import logger
from config.settings import settings


class PolygonService:
    BASE_URL = "https://api.polygon.io"

    def __init__(self):
        self.api_key = settings.POLYGON_API_KEY

    async def get_snapshot(self, ticker: str) -> Optional[dict]:
        """Get the latest snapshot (current day OHLCV + price) for a ticker."""
        if not self.api_key:
            return None

        async with httpx.AsyncClient(timeout=10) as client:
            try:
                resp = await client.get(
                    f"{self.BASE_URL}/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}",
                    params={"apiKey": self.api_key},
                )
                resp.raise_for_status()
                data = resp.json()
                ticker_data = data.get("ticker", {})
                day = ticker_data.get("day", {})
                return {
                    "ticker": ticker,
                    "open": day.get("o"),
                    "high": day.get("h"),
                    "low": day.get("l"),
                    "close": day.get("c"),
                    "volume": day.get("v"),
                    "vwap": day.get("vw"),
                    "prev_close": ticker_data.get("prevDay", {}).get("c"),
                    "change_pct": ticker_data.get("todaysChangePerc"),
                }
            except Exception as e:
                logger.warning(f"Polygon snapshot failed for {ticker}: {e}")
                return None

    async def get_previous_close(self, ticker: str) -> Optional[float]:
        """Get previous day's closing price."""
        if not self.api_key:
            return None
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                resp = await client.get(
                    f"{self.BASE_URL}/v2/aggs/ticker/{ticker}/prev",
                    params={"apiKey": self.api_key},
                )
                resp.raise_for_status()
                results = resp.json().get("results", [])
                if results:
                    return results[0].get("c")
                return None
            except Exception as e:
                logger.warning(f"Polygon prev_close failed for {ticker}: {e}")
                return None

    async def get_news(self, ticker: str, limit: int = 5) -> list:
        """Get latest news for a ticker — used for sentiment context."""
        if not self.api_key:
            return []
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                resp = await client.get(
                    f"{self.BASE_URL}/v2/reference/news",
                    params={"ticker": ticker, "limit": limit, "apiKey": self.api_key},
                )
                resp.raise_for_status()
                articles = resp.json().get("results", [])
                return [
                    {
                        "title": a.get("title", ""),
                        "published": a.get("published_utc", ""),
                        "sentiment": a.get("insights", [{}])[0].get("sentiment", "neutral")
                        if a.get("insights") else "neutral",
                    }
                    for a in articles
                ]
            except Exception as e:
                logger.warning(f"Polygon news failed for {ticker}: {e}")
                return []
