"""
ValidationService — Orchestrates The Trader + The Mentor

Flow:
  1. OpenTrade.ai (Trader) analyzes the ticker
  2. RAGFlow (Mentor) validates the analysis against rules/history
  3. Results are combined into a final verdict with confidence score
  4. Message is formatted for Telegram delivery
"""
import asyncio
from datetime import datetime
from typing import Optional
from loguru import logger

from opentrade.service import OpenTradeService, TraderAnalysis
from ragflow.service import RAGFlowService
from config.settings import settings

DISCLAIMER = (
    "\n\n─────────────────────────\n"
    "⚠️ *AI analysis is for informational purposes only. "
    "Not financial advice. Past performance does not guarantee future results.*"
)

# Emoji map for verdicts
VERDICT_EMOJI = {
    "CONFIRM": "✅",
    "CAUTION": "⚠️",
    "REJECT": "❌",
    "NEUTRAL": "🔄",
}

SIGNAL_EMOJI = {
    "BUY": "📈",
    "SELL": "📉",
    "HOLD": "⏸️",
}


class ValidationService:
    """
    Orchestrates the full validation pipeline:
    OpenTrade.ai (Trader) → RAGFlow (Mentor) → Final Verdict
    """

    def __init__(self):
        self.trader = OpenTradeService(settings)
        self.mentor = RAGFlowService(settings)

    # ─── Product 3: Manual Validator ─────────────────────────────────────

    async def validate_manual(
        self,
        ticker: str,
        signal: str,         # BUY / SELL / HOLD
        price: Optional[float],
        user_ragflow_dataset_id: Optional[str],
        polygon_data: Optional[dict] = None,
    ) -> dict:
        """
        Product 3: User typed /check AAPL BUY 175
        Full Trader + Mentor pipeline.
        """
        logger.info(f"Manual validation: {ticker} {signal} @{price}")

        # Step 1: OpenTrade.ai analysis
        trader_result = await self.trader.analyze(
            ticker=ticker,
            analysis_date=datetime.now().date().isoformat(),
        )

        # Step 2: RAGFlow mentor validation
        mentor_result = await self.mentor.validate_signal(
            ticker=ticker,
            signal=signal,
            trader_analysis=trader_result.to_dict(),
            user_dataset_id=user_ragflow_dataset_id,
        )

        # Step 3: Combine into final verdict
        return self._combine_results(
            ticker=ticker,
            signal=signal,
            price=price,
            trader=trader_result,
            mentor=mentor_result,
            product=3,
        )

    # ─── Product 1: Indicator Validator ──────────────────────────────────

    async def validate_indicator(
        self,
        ticker: str,
        signal: str,
        price: Optional[float],
        indicator_name: str,
        user_ragflow_dataset_id: Optional[str],
        extra_payload: Optional[dict] = None,
    ) -> dict:
        """
        Product 1: TradingView webhook triggered analysis.
        """
        logger.info(f"Indicator validation: {ticker} {signal} from {indicator_name}")

        trader_result = await self.trader.analyze(ticker=ticker)

        mentor_result = await self.mentor.validate_signal(
            ticker=ticker,
            signal=signal,
            trader_analysis=trader_result.to_dict(),
            user_dataset_id=user_ragflow_dataset_id,
        )

        result = self._combine_results(
            ticker=ticker,
            signal=signal,
            price=price,
            trader=trader_result,
            mentor=mentor_result,
            product=1,
        )
        result["indicator_name"] = indicator_name
        return result

    # ─── Product 2: EA Analyzer ──────────────────────────────────────────

    async def analyze_ea_trade(
        self,
        ticker: str,
        action: str,          # BUY / SELL
        result_outcome: str,  # WIN / LOSS
        pnl: Optional[float],
        ea_name: str,
        trade_time: Optional[str],
        user_ragflow_dataset_id: Optional[str],
    ) -> dict:
        """
        Product 2: Post-trade EA analysis.
        Explains WHY the trade won or lost.
        """
        logger.info(f"EA analysis: {ea_name} {action} {ticker} → {result_outcome}")

        # Analyze what the market looked like at that time
        analysis_date = trade_time[:10] if trade_time else None
        trader_result = await self.trader.analyze(
            ticker=ticker,
            analysis_date=analysis_date,
        )

        # Ask the mentor why this trade result happened
        mentor_result = await self.mentor.validate_signal(
            ticker=ticker,
            signal=action,
            trader_analysis=trader_result.to_dict(),
            user_dataset_id=user_ragflow_dataset_id,
        )

        return self._build_ea_analysis_message(
            ticker=ticker,
            action=action,
            result_outcome=result_outcome,
            pnl=pnl,
            ea_name=ea_name,
            trader=trader_result,
            mentor=mentor_result,
        )

    # ─── Result Combination Logic ─────────────────────────────────────────

    def _combine_results(
        self,
        ticker: str,
        signal: str,
        price: Optional[float],
        trader: TraderAnalysis,
        mentor: dict,
        product: int,
    ) -> dict:
        """Combine Trader + Mentor results into a final verdict."""

        # Base confidence from trader
        base_confidence = trader.confidence

        # Adjust with mentor's assessment
        adj = mentor.get("confidence_adjustment", 0.0)
        final_confidence = max(0.1, min(0.99, base_confidence + adj))

        # Determine verdict
        mentor_verdict = mentor.get("mentor_verdict", "NEUTRAL")
        trader_decision = trader.decision

        if mentor_verdict == "REJECT":
            verdict = "REJECT"
        elif mentor_verdict == "CONFIRM" and trader_decision == signal:
            verdict = "CONFIRM"
        elif mentor_verdict == "CAUTION" or trader_decision != signal:
            verdict = "CAUTION"
        else:
            verdict = "CONFIRM" if final_confidence >= 0.6 else "CAUTION"

        # Format the Telegram message
        message = self._format_validation_message(
            ticker=ticker,
            signal=signal,
            price=price,
            trader=trader,
            mentor=mentor,
            verdict=verdict,
            confidence=final_confidence,
            product=product,
        )

        return {
            "ticker": ticker,
            "signal": signal,
            "price": price,
            "verdict": verdict,
            "confidence_score": round(final_confidence, 2),
            "trader_analysis": trader.to_dict(),
            "mentor_context": mentor.get("reasoning", ""),
            "final_message": message,
        }

    def _format_validation_message(
        self,
        ticker: str,
        signal: str,
        price: Optional[float],
        trader: TraderAnalysis,
        mentor: dict,
        verdict: str,
        confidence: float,
        product: int,
    ) -> str:
        """Format the final message to send via Telegram (Markdown)."""

        sig_emoji = SIGNAL_EMOJI.get(signal, "")
        verdict_emoji = VERDICT_EMOJI.get(verdict, "🔄")
        conf_pct = int(confidence * 100)
        conf_bar = self._confidence_bar(confidence)

        # Header
        price_str = f" @ ${price:.2f}" if price else ""
        lines = [
            f"*🤖 AI Trade Validator*",
            f"",
            f"{sig_emoji} *{ticker}* — {signal}{price_str}",
            f"",
            f"{verdict_emoji} *Verdict: {verdict}* ({conf_pct}%)",
            f"{conf_bar}",
            f"",
            f"*📊 Technical Analysis (Trader)*",
            f"• Signal: {trader.technical_signal}",
        ]

        # Technical indicators
        if trader.rsi is not None:
            rsi_note = " 🔴 Overbought" if trader.rsi > 70 else (" 🟢 Oversold" if trader.rsi < 30 else "")
            lines.append(f"• RSI(14): {trader.rsi:.1f}{rsi_note}")

        if trader.macd is not None and trader.macd_signal is not None:
            macd_trend = "↑ Bullish" if trader.macd > trader.macd_signal else "↓ Bearish"
            lines.append(f"• MACD: {trader.macd:.3f} ({macd_trend})")

        if trader.bb_position:
            bb_map = {
                "ABOVE_UPPER": "Above upper band (overbought risk)",
                "BELOW_LOWER": "Below lower band (oversold opportunity)",
                "WITHIN": "Within bands (normal range)",
            }
            lines.append(f"• Bollinger: {bb_map.get(trader.bb_position, trader.bb_position)}")

        if trader.current_price and trader.sma_20:
            trend = "above" if trader.current_price > trader.sma_20 else "below"
            lines.append(f"• Price {trend} SMA20 ({trader.sma_20:.2f})")

        # Bull/Bear case (brief)
        lines += [
            f"",
            f"*🐂 Bull case:* _{trader.bull_case[:120]}_",
            f"*🐻 Bear case:* _{trader.bear_case[:120]}_",
        ]

        # Mentor context
        if mentor.get("relevant_rules"):
            lines += [
                f"",
                f"*📚 Mentor Rules Applied*",
            ]
            for rule in mentor["relevant_rules"][:2]:
                lines.append(f"• _{rule[:130]}_")

        # Risk
        lines += [
            f"",
            f"*⚡ Risk Level:* {trader.risk_level}",
        ]
        if trader.risk_notes:
            lines.append(f"_{trader.risk_notes[:120]}_")

        lines.append(DISCLAIMER)

        return "\n".join(lines)

    def _build_ea_analysis_message(
        self,
        ticker: str,
        action: str,
        result_outcome: str,
        pnl: Optional[float],
        ea_name: str,
        trader: TraderAnalysis,
        mentor: dict,
    ) -> dict:
        """Build the EA post-trade analysis message."""

        outcome_emoji = "✅" if result_outcome == "WIN" else "❌"
        pnl_str = f" (PnL: {'+' if pnl and pnl > 0 else ''}{pnl:.2f}%)" if pnl else ""

        lines = [
            f"*🤖 EA Trade Analysis*",
            f"",
            f"{outcome_emoji} *{ea_name}* — {action} {ticker}{pnl_str}",
            f"",
            f"*📊 Market Conditions at Trade Time*",
            f"• Technical Signal: {trader.technical_signal}",
        ]

        if trader.rsi is not None:
            lines.append(f"• RSI: {trader.rsi:.1f}")
        if trader.macd is not None and trader.macd_signal is not None:
            macd_trend = "Bullish" if trader.macd > trader.macd_signal else "Bearish"
            lines.append(f"• MACD: {macd_trend}")

        # Why did it win/lose?
        if result_outcome == "WIN":
            lines += [
                f"",
                f"*🎯 Why it Won:*",
                f"_{trader.bull_case[:200]}_",
            ]
        else:
            lines += [
                f"",
                f"*💡 Why it Lost:*",
                f"_{trader.bear_case[:200]}_",
                f"",
                f"*🔧 Next Time:*",
                f"_{self._generate_improvement_tip(trader, mentor)}_",
            ]

        # Relevant rules
        if mentor.get("relevant_rules"):
            lines += [
                f"",
                f"*📚 Applicable Rules:*",
            ]
            for rule in mentor["relevant_rules"][:2]:
                lines.append(f"• _{rule[:130]}_")

        lines.append(DISCLAIMER)
        message = "\n".join(lines)

        return {
            "ticker": ticker,
            "signal": action,
            "verdict": result_outcome,
            "confidence_score": trader.confidence,
            "trader_analysis": trader.to_dict(),
            "mentor_context": mentor.get("reasoning", ""),
            "final_message": message,
        }

    def _generate_improvement_tip(self, trader: TraderAnalysis, mentor: dict) -> str:
        """Generate an actionable improvement tip based on the analysis."""
        tips = []

        if trader.rsi and trader.rsi > 70:
            tips.append("RSI was overbought at trade time — avoid buying overbought stocks")

        if trader.macd and trader.macd_signal and trader.macd < trader.macd_signal:
            tips.append("MACD was bearish — wait for bullish crossover confirmation")

        if trader.bb_position == "ABOVE_UPPER":
            tips.append("Price was above Bollinger upper band — high reversal risk")

        if tips:
            return "; ".join(tips) + "."

        if mentor.get("relevant_rules"):
            return "Review the applicable rules above for your next trade setup."

        return "Consider adding more confirmation signals before entering the next trade."

    @staticmethod
    def _confidence_bar(confidence: float) -> str:
        """Generate a visual confidence bar."""
        filled = int(confidence * 10)
        empty = 10 - filled
        bar = "█" * filled + "░" * empty
        return f"`[{bar}]` {int(confidence * 100)}%"
