"""
services/report_formatter.py
Formats OHLC analysis results into:
  1. Telegram message (HTML)
  2. Mini App / extension JSON report tab structure
  3. EA Analyser trade review (why entry, why win/loss)

Called after webhooks/ohlc.py returns a report dict.
"""
from __future__ import annotations
from typing import Optional


SIGNAL_EMOJI = {"BUY": "🟢", "SELL": "🔴", "NEUTRAL": "🟡"}
SIGNAL_LABEL = {"BUY": "BUY", "SELL": "SELL", "NEUTRAL": "NEUTRAL"}
GROUP_EMOJI  = {"momentum": "⚡", "trend": "📈", "volume": "📊", "volatility": "🌊"}
GROUP_LABEL  = {"momentum": "Momentum & Oscillators", "trend": "Trend & Moving Averages",
                "volume": "Volume", "volatility": "Volatility & Other"}
OUTCOME_EMOJI = {"win": "✅", "loss": "❌", "open": "📍", "sl": "🛑", "tp": "🎯", "close": "📪"}


# ── Telegram message ──────────────────────────────────────────────────────────

def format_telegram_report(report: dict, trade: Optional[dict] = None) -> str:
    """Returns formatted HTML string for Telegram sendMessage."""
    sig    = report.get("signal", "NEUTRAL")
    emoji  = SIGNAL_EMOJI.get(sig, "🟡")
    symbol = report.get("symbol", "")
    tf     = report.get("timeframe", "")
    conf   = report.get("confidence", 0)
    pattern = report.get("pattern", "")
    reason  = report.get("reason", "")
    ind     = report.get("indicators", {})
    bias    = ind.get("overall_bias", "neutral").upper()

    lines = []
    lines.append(f"{emoji} <b>{sig}</b> — {symbol} · {tf}")
    lines.append("")

    if pattern:
        lines.append(f"📐 <b>Pattern:</b> {pattern}")
    lines.append(f"🎯 <b>Confidence:</b> {conf}%")
    lines.append(f"📊 <b>Indicator bias:</b> {bias} "
                 f"({ind.get('bull_count',0)}↑ {ind.get('bear_count',0)}↓ {ind.get('neutral_count',0)}→)")
    lines.append("")
    lines.append(f"💬 <b>Analysis:</b>")
    lines.append(reason)
    lines.append("")

    # Indicators — show one line per group
    groups = ind.get("groups", {})
    if groups:
        lines.append("📋 <b>Indicators:</b>")
        for grp_name, indicators in groups.items():
            grp_emoji = GROUP_EMOJI.get(grp_name, "•")
            bull = sum(1 for v in indicators.values() if v.get("signal") == "bullish")
            bear = sum(1 for v in indicators.values() if v.get("signal") == "bearish")
            total = len(indicators)
            lines.append(f"  {grp_emoji} {GROUP_LABEL.get(grp_name, grp_name)}: "
                         f"{bull}↑ {bear}↓ / {total}")
            # Show top 3 most relevant indicators per group
            for ind_name, ind_data in list(indicators.items())[:3]:
                sig_icon = "↑" if ind_data.get("signal") == "bullish" else ("↓" if ind_data.get("signal") == "bearish" else "→")
                lines.append(f"    <code>{ind_data.get('label', ind_name)}</code> {sig_icon}")
        lines.append("")

    # Patterns detected
    patterns = report.get("patterns", [])
    if patterns:
        lines.append("🕯 <b>Patterns detected:</b>")
        for p in patterns[:4]:
            dir_icon = "↑" if p.get("bullish") else "↓"
            lines.append(f"  • {p['name'].replace('_',' ').title()} {dir_icon} ({int(p.get('confidence',0)*100)}%)")
        lines.append("")

    # Levels
    levels = report.get("levels", [])
    if levels:
        lines.append("📏 <b>Key levels:</b>")
        for lv in levels[:4]:
            lines.append(f"  • {lv.get('type','').title()}: {lv.get('price',0):.5f}")
        lines.append("")

    # EA trade context
    if trade:
        ev = trade.get("event", "")
        ev_emoji = OUTCOME_EMOJI.get(ev, "📍")
        lines.append(f"{ev_emoji} <b>Trade event:</b> {trade.get('direction','').upper()} @ {trade.get('price',0):.5f}")
        if trade.get("verdict"):
            lines.append(f"🔍 <b>Verdict:</b> {trade['verdict']}")
        if trade.get("why_entry"):
            lines.append(f"📥 <b>Why entry:</b> {trade['why_entry']}")
        if trade.get("why_result"):
            lines.append(f"📤 <b>Why result:</b> {trade['why_result']}")
        lines.append("")

    lines.append("⚠️ <i>Analytical tool only — not financial advice.</i>")
    return "\n".join(lines)


# ── Mini App / extension report tab ──────────────────────────────────────────

def format_app_report(report: dict) -> dict:
    """
    Returns a clean dict for the Mini App report tab and extension report card.
    Structured for easy rendering — no HTML, just data.
    """
    sig     = report.get("signal", "NEUTRAL")
    ind     = report.get("indicators", {})
    groups  = ind.get("groups", {})
    patterns = report.get("patterns", [])

    # Build indicator summary cards
    ind_cards = []
    for grp_name, indicators in groups.items():
        items = []
        for name, data in indicators.items():
            items.append({
                "name":    name,
                "display": data.get("display", name),
                "label":   data.get("label", ""),
                "signal":  data.get("signal", "neutral"),
                "value":   data.get("value"),
                "extra":   data.get("extra", {}),
            })
        ind_cards.append({
            "group":   grp_name,
            "label":   GROUP_LABEL.get(grp_name, grp_name),
            "emoji":   GROUP_EMOJI.get(grp_name, "•"),
            "bull":    sum(1 for i in items if i["signal"] == "bullish"),
            "bear":    sum(1 for i in items if i["signal"] == "bearish"),
            "items":   items,
        })

    return {
        "signal":      sig,
        "signal_emoji": SIGNAL_EMOJI.get(sig, "🟡"),
        "symbol":      report.get("symbol", ""),
        "timeframe":   report.get("timeframe", ""),
        "pattern":     report.get("pattern", ""),
        "confidence":  report.get("confidence", 0),
        "reason":      report.get("reason", ""),
        "overall_bias": ind.get("overall_bias", "neutral"),
        "bull_count":  ind.get("bull_count", 0),
        "bear_count":  ind.get("bear_count", 0),
        "total_indicators": ind.get("total", 0),
        "indicator_groups": ind_cards,
        "patterns":    [
            {"name": p["name"].replace("_"," ").title(),
             "bullish": p.get("bullish", True),
             "confidence": int(p.get("confidence", 0) * 100),
             "description": p.get("description", "")}
            for p in patterns
        ],
        "levels": report.get("levels", []),
        "trade":  report.get("trade"),
    }


# ── EA analyser full trade report ─────────────────────────────────────────────

def format_ea_trade_report(report: dict) -> dict:
    """
    Dedicated EA Analyser report format.
    Shown in Mini App EA Analyser report tab and Telegram message.
    """
    trade  = report.get("trade", {})
    event  = trade.get("event", "")
    direction = trade.get("direction", "").upper()
    price  = trade.get("price", 0)

    title_map = {
        "open":  f"EA opened {direction} @ {price:.5f}",
        "close": f"EA closed {direction} @ {price:.5f}",
        "sl":    f"Stop Loss hit — {direction} @ {price:.5f}",
        "tp":    f"Take Profit hit — {direction} @ {price:.5f}",
    }
    title = title_map.get(event, f"EA trade event: {direction} @ {price:.5f}")

    app_report = format_app_report(report)
    app_report.update({
        "ea_title":   title,
        "event":      event,
        "event_emoji": OUTCOME_EMOJI.get(event, "📍"),
        "verdict":    trade.get("verdict", ""),
        "why_entry":  trade.get("why_entry", ""),
        "why_result": trade.get("why_result", ""),
    })
    return app_report
