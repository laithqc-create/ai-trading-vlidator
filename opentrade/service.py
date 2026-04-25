"""
OpenTrade.ai Integration — The Trader

Wraps the OpenTrade.ai LangGraph multi-agent pipeline to provide
programmatic access from our Telegram bot system.

OpenTrade.ai agents:
1. Fundamental Analyst
2. Sentiment Analyst
3. News Analyst
4. Technical Analyst (RSI, MACD, Bollinger Bands, etc.)
5. Bull Researcher
6. Bear Researcher
7. Trader Agent
8. Risk Manager
"""
import asyncio
import json
from datetime import datetime, date
from typing import Optional
from dataclasses import dataclass, asdict

from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential


@dataclass
class TraderAnalysis:
    """Structured result from OpenTrade.ai pipeline."""
    ticker: str
    analysis_date: str

    # Core decision
    decision: str           # BUY / SELL / HOLD
    confidence: float       # 0.0 - 1.0
    risk_level: str         # LOW / MEDIUM / HIGH

    # Individual agent signals
    technical_signal: str   # BULLISH / BEARISH / NEUTRAL
    fundamental_signal: str
    sentiment_signal: str
    news_signal: str
    bull_case: str
    bear_case: str

    # Technical indicators (from TechnicalAnalyst agent)
    rsi: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    bb_position: Optional[str] = None    # ABOVE_UPPER / WITHIN / BELOW_LOWER
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    atr: Optional[float] = None
    current_price: Optional[float] = None

    # Risk Manager output
    risk_approved: bool = True
    risk_notes: str = ""

    # Full reasoning text
    reasoning: str = ""

    def to_dict(self):
        return asdict(self)


class OpenTradeService:
    """
    Service that runs the OpenTrade.ai LangGraph pipeline.

    OpenTrade.ai is imported as a Python package (installed from GitHub).
    We call its TradingGraph programmatically rather than using its CLI/Streamlit UI.
    """

    def __init__(self, settings):
        self.settings = settings
        self._graph = None
        self._initialized = False

    def _get_llm_config(self) -> dict:
        """Build LLM config dict for OpenTrade.ai."""
        return {
            "provider": self.settings.LLM_PROVIDER,
            "model": self.settings.LLM_MODEL,
            "ollama_base_url": self.settings.OLLAMA_BASE_URL,
            "lmstudio_base_url": self.settings.LMSTUDIO_BASE_URL,
            "openai_api_key": self.settings.OPENAI_API_KEY or "",
        }

    def _initialize_graph(self):
        """Lazy-initialize the OpenTrade.ai TradingGraph."""
        if self._initialized:
            return

        try:
            # Import OpenTrade.ai modules
            from opentrade_ai.graph.trading_graph import TradingGraph
            from opentrade_ai.config import AppConfig
            from opentrade_ai.llm.provider import LLMProvider

            llm_cfg = self._get_llm_config()
            provider = LLMProvider(
                provider=llm_cfg["provider"],
                model=llm_cfg["model"],
                ollama_base_url=llm_cfg.get("ollama_base_url"),
                lmstudio_base_url=llm_cfg.get("lmstudio_base_url"),
                openai_api_key=llm_cfg.get("openai_api_key"),
            )

            config = AppConfig(
                llm_provider=llm_cfg["provider"],
                llm_model=llm_cfg["model"],
                risk_tolerance="moderate",
            )

            self._graph = TradingGraph(llm_provider=provider, config=config)
            self._initialized = True
            logger.info("OpenTrade.ai TradingGraph initialized.")

        except ImportError as e:
            logger.warning(
                f"OpenTrade.ai not installed as package ({e}). "
                "Using fallback technical analysis."
            )
            self._graph = None
            self._initialized = True

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    async def analyze(
        self,
        ticker: str,
        analysis_date: Optional[str] = None,
        risk_tolerance: str = "moderate",
    ) -> TraderAnalysis:
        """
        Run the full OpenTrade.ai multi-agent pipeline for a ticker.

        Falls back to direct technical analysis if LangGraph pipeline fails.
        """
        if analysis_date is None:
            analysis_date = date.today().isoformat()

        self._initialize_graph()

        if self._graph is not None:
            return await self._run_langgraph_pipeline(ticker, analysis_date, risk_tolerance)
        else:
            return await self._run_fallback_analysis(ticker, analysis_date)

    async def _run_langgraph_pipeline(
        self,
        ticker: str,
        analysis_date: str,
        risk_tolerance: str,
    ) -> TraderAnalysis:
        """Run OpenTrade.ai LangGraph pipeline in executor (it's synchronous)."""
        loop = asyncio.get_event_loop()

        def _run_sync():
            """Run LangGraph synchronously (it uses sync calls internally)."""
            try:
                result = self._graph.run(
                    ticker=ticker,
                    date=analysis_date,
                    risk_tolerance=risk_tolerance,
                )
                return result
            except Exception as e:
                logger.error(f"LangGraph pipeline error for {ticker}: {e}")
                raise

        try:
            result = await loop.run_in_executor(None, _run_sync)
            return self._parse_graph_result(ticker, analysis_date, result)
        except Exception as e:
            logger.warning(f"LangGraph failed, using fallback: {e}")
            return await self._run_fallback_analysis(ticker, analysis_date)

    def _parse_graph_result(
        self,
        ticker: str,
        analysis_date: str,
        result: dict,
    ) -> TraderAnalysis:
        """
        Parse OpenTrade.ai TradingGraph output into our TraderAnalysis struct.

        The LangGraph result is a dict with agent outputs stored in the state.
        Key fields: final_decision, risk_assessment, technical_analysis, etc.
        """
        try:
            # Extract from LangGraph state dict
            final_decision = result.get("final_decision", {})
            technical = result.get("technical_analysis", {})
            risk = result.get("risk_assessment", {})
            fundamental = result.get("fundamental_analysis", {})
            sentiment = result.get("sentiment_analysis", {})
            news = result.get("news_analysis", {})
            bull = result.get("bull_research", {})
            bear = result.get("bear_research", {})

            # Parse decision
            decision_text = str(final_decision.get("action", "HOLD")).upper()
            if "BUY" in decision_text:
                decision = "BUY"
            elif "SELL" in decision_text:
                decision = "SELL"
            else:
                decision = "HOLD"

            # Parse confidence (LangGraph agents may return as decimal or percent)
            raw_conf = final_decision.get("confidence", 0.6)
            confidence = float(raw_conf) if raw_conf <= 1.0 else float(raw_conf) / 100.0

            # Technical indicators
            indicators = technical.get("indicators", {})

            return TraderAnalysis(
                ticker=ticker,
                analysis_date=analysis_date,
                decision=decision,
                confidence=confidence,
                risk_level=risk.get("risk_level", "MEDIUM"),
                technical_signal=technical.get("signal", "NEUTRAL"),
                fundamental_signal=fundamental.get("signal", "NEUTRAL"),
                sentiment_signal=sentiment.get("signal", "NEUTRAL"),
                news_signal=news.get("signal", "NEUTRAL"),
                bull_case=str(bull.get("summary", "No bullish case provided.")),
                bear_case=str(bear.get("summary", "No bearish case provided.")),
                rsi=indicators.get("rsi"),
                macd=indicators.get("macd"),
                macd_signal=indicators.get("macd_signal"),
                bb_position=indicators.get("bb_position"),
                sma_20=indicators.get("sma_20"),
                sma_50=indicators.get("sma_50"),
                atr=indicators.get("atr"),
                current_price=technical.get("current_price"),
                risk_approved=risk.get("approved", True),
                risk_notes=str(risk.get("notes", "")),
                reasoning=str(final_decision.get("reasoning", "")),
            )
        except Exception as e:
            logger.error(f"Error parsing LangGraph result: {e}\nResult: {result}")
            # Return a safe fallback
            return TraderAnalysis(
                ticker=ticker,
                analysis_date=analysis_date,
                decision="HOLD",
                confidence=0.5,
                risk_level="MEDIUM",
                technical_signal="NEUTRAL",
                fundamental_signal="NEUTRAL",
                sentiment_signal="NEUTRAL",
                news_signal="NEUTRAL",
                bull_case="Unable to parse bullish analysis.",
                bear_case="Unable to parse bearish analysis.",
                reasoning=f"Analysis parsing error: {e}",
            )

    async def _run_fallback_analysis(
        self,
        ticker: str,
        analysis_date: str,
    ) -> TraderAnalysis:
        """
        Fallback: Direct technical analysis using yfinance + ta library.
        Used when OpenTrade.ai LangGraph pipeline is unavailable.
        """
        loop = asyncio.get_event_loop()

        def _compute():
            import yfinance as yf
            import pandas as pd

            try:
                stock = yf.Ticker(ticker)
                hist = stock.history(period="3mo")

                if hist.empty:
                    raise ValueError(f"No data for {ticker}")

                close = hist["Close"]
                volume = hist["Volume"]

                # RSI (manual calculation)
                delta = close.diff()
                gain = delta.where(delta > 0, 0).rolling(14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                rs = gain / loss
                rsi = float(100 - (100 / (1 + rs.iloc[-1])))

                # MACD
                ema12 = close.ewm(span=12).mean()
                ema26 = close.ewm(span=26).mean()
                macd_line = ema12 - ema26
                signal_line = macd_line.ewm(span=9).mean()
                macd = float(macd_line.iloc[-1])
                macd_sig = float(signal_line.iloc[-1])

                # Bollinger Bands
                sma20 = close.rolling(20).mean()
                std20 = close.rolling(20).std()
                bb_upper = sma20 + 2 * std20
                bb_lower = sma20 - 2 * std20
                current_price = float(close.iloc[-1])
                if current_price > float(bb_upper.iloc[-1]):
                    bb_pos = "ABOVE_UPPER"
                elif current_price < float(bb_lower.iloc[-1]):
                    bb_pos = "BELOW_LOWER"
                else:
                    bb_pos = "WITHIN"

                sma50 = float(close.rolling(50).mean().iloc[-1])

                # Simple signal logic
                bullish_signals = 0
                bearish_signals = 0

                if rsi < 35:
                    bullish_signals += 1
                elif rsi > 65:
                    bearish_signals += 1

                if macd > macd_sig:
                    bullish_signals += 1
                else:
                    bearish_signals += 1

                if current_price > float(sma20.iloc[-1]):
                    bullish_signals += 1
                else:
                    bearish_signals += 1

                if bullish_signals > bearish_signals:
                    decision = "BUY"
                    confidence = 0.5 + (bullish_signals - bearish_signals) * 0.1
                    tech_signal = "BULLISH"
                elif bearish_signals > bullish_signals:
                    decision = "SELL"
                    confidence = 0.5 + (bearish_signals - bullish_signals) * 0.1
                    tech_signal = "BEARISH"
                else:
                    decision = "HOLD"
                    confidence = 0.5
                    tech_signal = "NEUTRAL"

                # ATR (volatility)
                high_low = hist["High"] - hist["Low"]
                atr = float(high_low.rolling(14).mean().iloc[-1])

                return {
                    "decision": decision,
                    "confidence": min(confidence, 0.95),
                    "tech_signal": tech_signal,
                    "rsi": round(rsi, 2),
                    "macd": round(macd, 4),
                    "macd_signal": round(macd_sig, 4),
                    "bb_position": bb_pos,
                    "sma_20": round(float(sma20.iloc[-1]), 2),
                    "sma_50": round(sma50, 2),
                    "atr": round(atr, 2),
                    "current_price": round(current_price, 2),
                }
            except Exception as e:
                logger.error(f"Fallback analysis failed for {ticker}: {e}")
                return {
                    "decision": "HOLD",
                    "confidence": 0.5,
                    "tech_signal": "NEUTRAL",
                    "error": str(e),
                }

        data = await loop.run_in_executor(None, _compute)
        error = data.get("error")

        return TraderAnalysis(
            ticker=ticker,
            analysis_date=analysis_date,
            decision=data.get("decision", "HOLD"),
            confidence=data.get("confidence", 0.5),
            risk_level="MEDIUM",
            technical_signal=data.get("tech_signal", "NEUTRAL"),
            fundamental_signal="N/A (fallback mode)",
            sentiment_signal="N/A (fallback mode)",
            news_signal="N/A (fallback mode)",
            bull_case="Technical indicators suggest buying opportunity." if data.get("decision") == "BUY" else "Neutral to bearish technical picture.",
            bear_case="Technical indicators suggest caution." if data.get("decision") in ("SELL", "HOLD") else "No strong bearish signals.",
            rsi=data.get("rsi"),
            macd=data.get("macd"),
            macd_signal=data.get("macd_signal"),
            bb_position=data.get("bb_position"),
            sma_20=data.get("sma_20"),
            sma_50=data.get("sma_50"),
            atr=data.get("atr"),
            current_price=data.get("current_price"),
            risk_approved=True,
            risk_notes="Fallback analysis — LangGraph pipeline unavailable." if not error else f"Analysis error: {error}",
            reasoning="Direct technical analysis via yfinance (fallback mode).",
        )
