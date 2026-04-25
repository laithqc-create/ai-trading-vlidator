#!/usr/bin/env python3
"""
EA Monitor Script — runs on the user's VPS alongside their EA.

Watches an MT4/MT5 EA log file and POSTs completed trades
to the AI Trade Validator webhook for analysis.

Usage:
    python ea_monitor.py --webhook-url https://yourserver.com/webhook/ea/TOKEN \
                         --logfile /path/to/EA.log \
                         --ea-name "MyEA"

The script:
  1. Tails the EA log file in real time
  2. Detects trade open/close entries
  3. Sends completed trades to your webhook
"""
import argparse
import json
import re
import time
import requests
from datetime import datetime
from pathlib import Path


# ─── Log line patterns (MT4/MT5 format) ──────────────────────────────────────

# MT4 pattern: "2024.01.15 10:23:45 SuperEA EURUSD,M15: buy 0.10 at 1.08520"
MT4_OPEN_PATTERN = re.compile(
    r"(\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}:\d{2})\s+\S+\s+(\w+),\w+:\s+(buy|sell)\s+([\d.]+)\s+at\s+([\d.]+)",
    re.IGNORECASE,
)

# MT4 close pattern: "2024.01.15 10:45:00 SuperEA closed buy 0.10 EURUSD at 1.08750, profit 23.00"
MT4_CLOSE_PATTERN = re.compile(
    r"(\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}:\d{2})\s+\S+\s+closed\s+(buy|sell)\s+([\d.]+)\s+(\w+)\s+at\s+([\d.]+),\s+profit\s+([-\d.]+)",
    re.IGNORECASE,
)

# Generic close pattern
GENERIC_CLOSE_PATTERN = re.compile(
    r"(buy|sell).*?(win|loss|profit|closed).*?([\w]+).*?([+-]?[\d.]+)",
    re.IGNORECASE,
)


class EAMonitor:
    def __init__(self, webhook_url: str, logfile: str, ea_name: str, poll_interval: float = 1.0):
        self.webhook_url = webhook_url
        self.logfile = Path(logfile)
        self.ea_name = ea_name
        self.poll_interval = poll_interval
        self._sent_hashes = set()   # prevent duplicate sends

    def run(self):
        print(f"[EA Monitor] Watching {self.logfile}")
        print(f"[EA Monitor] EA: {self.ea_name}")
        print(f"[EA Monitor] Webhook: {self.webhook_url}")
        print(f"[EA Monitor] Press Ctrl+C to stop\n")

        if not self.logfile.exists():
            print(f"[ERROR] Log file not found: {self.logfile}")
            return

        # Start from end of file
        with open(self.logfile, "r") as f:
            f.seek(0, 2)    # Seek to end
            position = f.tell()

        while True:
            try:
                with open(self.logfile, "r") as f:
                    f.seek(position)
                    new_lines = f.readlines()
                    position = f.tell()

                for line in new_lines:
                    self._process_line(line.strip())

            except FileNotFoundError:
                print(f"[WARN] Log file disappeared, waiting...")
            except Exception as e:
                print(f"[ERROR] {e}")

            time.sleep(self.poll_interval)

    def _process_line(self, line: str):
        if not line:
            return

        # Try MT4 close pattern
        m = MT4_CLOSE_PATTERN.search(line)
        if m:
            trade_time, action, volume, ticker, close_price, profit = m.groups()
            pnl = float(profit)
            result = "WIN" if pnl > 0 else "LOSS"
            self._send_trade(
                ticker=ticker.upper(),
                action=action.upper(),
                result=result,
                pnl=pnl,
                trade_time=trade_time,
                raw_line=line,
            )
            return

        # Generic keyword detection
        if any(kw in line.lower() for kw in ["closed", "profit", "loss", "win"]):
            trade = self._parse_generic(line)
            if trade:
                self._send_trade(**trade, raw_line=line)

    def _parse_generic(self, line: str) -> dict | None:
        """Best-effort generic parsing for non-standard EA logs."""
        line_lower = line.lower()

        # Detect action
        if "buy" in line_lower:
            action = "BUY"
        elif "sell" in line_lower:
            action = "SELL"
        else:
            return None

        # Detect result
        if "win" in line_lower or ("profit" in line_lower and "+" in line):
            result = "WIN"
        elif "loss" in line_lower or ("profit" in line_lower and "-" in line):
            result = "LOSS"
        else:
            return None

        # Extract ticker (uppercase 3-6 char word)
        ticker_match = re.search(r"\b([A-Z]{3,6}(?:USD|EUR|GBP|JPY)?)\b", line)
        ticker = ticker_match.group(1) if ticker_match else "UNKNOWN"

        # Extract PnL
        pnl_match = re.search(r"([+-]?\d+\.?\d*)", line)
        pnl = float(pnl_match.group(1)) if pnl_match else 0.0

        return {
            "ticker": ticker,
            "action": action,
            "result": result,
            "pnl": pnl,
            "trade_time": datetime.now().isoformat(),
        }

    def _send_trade(
        self,
        ticker: str,
        action: str,
        result: str,
        pnl: float,
        trade_time: str,
        raw_line: str = "",
    ):
        """POST trade data to the webhook."""
        payload = {
            "ea_name": self.ea_name,
            "ticker": ticker,
            "action": action,
            "result": result,
            "pnl": pnl,
            "trade_time": trade_time,
        }

        # Dedup by hash of payload
        payload_hash = hash(json.dumps(payload, sort_keys=True))
        if payload_hash in self._sent_hashes:
            return
        self._sent_hashes.add(payload_hash)

        try:
            resp = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            print(f"[SENT] {action} {ticker} → {result} ({pnl:+.2f}) — {resp.status_code}")
        except requests.RequestException as e:
            print(f"[ERROR] Failed to send trade: {e}")
            # Remove from sent set so it can be retried
            self._sent_hashes.discard(payload_hash)


def main():
    parser = argparse.ArgumentParser(description="EA Monitor — AI Trade Validator")
    parser.add_argument("--webhook-url", required=True, help="Your personal webhook URL")
    parser.add_argument("--logfile", required=True, help="Path to EA log file")
    parser.add_argument("--ea-name", default="MyEA", help="Name of your EA")
    parser.add_argument("--interval", type=float, default=1.0, help="Poll interval in seconds")

    args = parser.parse_args()

    monitor = EAMonitor(
        webhook_url=args.webhook_url,
        logfile=args.logfile,
        ea_name=args.ea_name,
        poll_interval=args.interval,
    )
    monitor.run()


if __name__ == "__main__":
    main()
