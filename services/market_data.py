"""
services/market_data.py
Market data fetching via Polygon.io (Products 1 & 2).

The PolygonService is the module-level name that tests mock.
Mock path: services.market_data.PolygonService
"""
import httpx
from typing import Optional
from config.settings import settings


class PolygonService:
    """Fetch OHLC bars and snapshots from Polygon.io REST API."""

    BASE = "https://api.polygon.io"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or getattr(settings, "POLYGON_API_KEY", "")

    async def get_snapshot(self, ticker: str) -> dict:
        """Get latest quote + daily OHLC snapshot for a ticker."""
        url = f"{self.BASE}/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params={"apiKey": self.api_key})
            resp.raise_for_status()
            data = resp.json()
        return data.get("ticker", {})

    async def get_bars(self, ticker: str, timespan: str = "day", limit: int = 50) -> list[dict]:
        """Get recent OHLC bars for a ticker."""
        from datetime import date, timedelta
        to_date = date.today().isoformat()
        from_date = (date.today() - timedelta(days=limit * 2)).isoformat()
        url = f"{self.BASE}/v2/aggs/ticker/{ticker}/range/1/{timespan}/{from_date}/{to_date}"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params={"apiKey": self.api_key, "limit": limit})
            resp.raise_for_status()
            data = resp.json()
        return data.get("results", [])
