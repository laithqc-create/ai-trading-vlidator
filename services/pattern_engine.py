"""
services/pattern_engine.py
Extended candle pattern detection engine.

Categories:
  1. Classic candle patterns (16 existing)
  2. SMC / ICT patterns (8 new)
  3. Market Structure (4 new)
  4. Time & Session Analysis (4 new)
  5. Classical Chart Patterns (6 new)
  6. Strategy Models (4 new)
  7. Key Levels (6 new)

All detectors return PatternMatch objects with name, bullish, confidence, description.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime, time


@dataclass
class PatternRule:
    name: str
    enabled: bool = True
    min_body_ratio: Optional[float] = None
    max_wick_ratio: Optional[float] = None
    min_engulf_ratio: Optional[float] = None


@dataclass
class PatternMatch:
    name: str
    bullish: bool
    confidence: float
    candle_indices: List[int]
    description: str


# ── All system rules ──────────────────────────────────────────────────────────
SYSTEM_RULES = {
    # Classic
    "doji":                 PatternRule("doji"),
    "hammer":               PatternRule("hammer",              min_body_ratio=0.15),
    "inverted_hammer":      PatternRule("inverted_hammer",     min_body_ratio=0.15),
    "shooting_star":        PatternRule("shooting_star",       min_body_ratio=0.15),
    "hanging_man":          PatternRule("hanging_man",         min_body_ratio=0.15),
    "bullish_engulfing":    PatternRule("bullish_engulfing",   min_engulf_ratio=1.0),
    "bearish_engulfing":    PatternRule("bearish_engulfing",   min_engulf_ratio=1.0),
    "morning_star":         PatternRule("morning_star"),
    "evening_star":         PatternRule("evening_star"),
    "three_white_soldiers": PatternRule("three_white_soldiers"),
    "three_black_crows":    PatternRule("three_black_crows"),
    "tweezer_top":          PatternRule("tweezer_top"),
    "tweezer_bottom":       PatternRule("tweezer_bottom"),
    "piercing_line":        PatternRule("piercing_line"),
    "dark_cloud_cover":     PatternRule("dark_cloud_cover"),
    "spinning_top":         PatternRule("spinning_top"),
    # SMC / ICT
    "fair_value_gap":       PatternRule("fair_value_gap"),
    "order_block":          PatternRule("order_block"),
    "breaker_block":        PatternRule("breaker_block"),
    "liquidity_sweep":      PatternRule("liquidity_sweep"),
    "mitigation_block":     PatternRule("mitigation_block"),
    "equal_highs":          PatternRule("equal_highs"),
    "equal_lows":           PatternRule("equal_lows"),
    "rejection_block":      PatternRule("rejection_block"),
    "smt_divergence":       PatternRule("smt_divergence",      enabled=False),
    # Market Structure
    "bos":                  PatternRule("bos"),
    "choch":                PatternRule("choch"),
    "swing_high":           PatternRule("swing_high"),
    "swing_low":            PatternRule("swing_low"),
    "retracement_depth":    PatternRule("retracement_depth"),
    # Session / Time
    "killzone":             PatternRule("killzone"),
    "silver_bullet_window": PatternRule("silver_bullet_window", enabled=False),
    "amd":                  PatternRule("amd",                  enabled=False),
    "judas_swing":          PatternRule("judas_swing",          enabled=False),
    # Classical Chart Patterns
    "head_and_shoulders":   PatternRule("head_and_shoulders"),
    "double_top":           PatternRule("double_top"),
    "double_bottom":        PatternRule("double_bottom"),
    "triangle_asc":         PatternRule("triangle_asc"),
    "triangle_desc":        PatternRule("triangle_desc"),
    "triangle_sym":         PatternRule("triangle_sym"),
    "cup_and_handle":       PatternRule("cup_and_handle",       enabled=False),
    "flag":                 PatternRule("flag",                 enabled=False),
    "pennant":              PatternRule("pennant",              enabled=False),
    "wedge":                PatternRule("wedge",                enabled=False),
    # Strategy Models
    "turtle_soup":          PatternRule("turtle_soup",          enabled=False),
    "silver_bullet":        PatternRule("silver_bullet",        enabled=False),
    "power_of_three":       PatternRule("power_of_three",       enabled=False),
    "ote":                  PatternRule("ote",                  enabled=False),
    # Key Levels
    "support_resistance":   PatternRule("support_resistance"),
    "prev_day_high":        PatternRule("prev_day_high"),
    "prev_day_low":         PatternRule("prev_day_low"),
    "prev_week_high":       PatternRule("prev_week_high"),
    "prev_week_low":        PatternRule("prev_week_low"),
    "prev_month_high":      PatternRule("prev_month_high"),
    "prev_month_low":       PatternRule("prev_month_low"),
}

PATTERN_DESCRIPTIONS = {
    # Classic
    "doji":                 "Open ≈ Close; market indecision. Watch for reversal confirmation.",
    "hammer":               "Small body, long lower wick — bullish reversal after downtrend.",
    "inverted_hammer":      "Small body, long upper wick — potential bullish reversal.",
    "shooting_star":        "Small body, long upper wick after uptrend — bearish reversal signal.",
    "hanging_man":          "Small body, long lower wick after uptrend — bearish warning.",
    "bullish_engulfing":    "Bull candle body fully engulfs prior bear candle — strong buy signal.",
    "bearish_engulfing":    "Bear candle body fully engulfs prior bull candle — strong sell signal.",
    "morning_star":         "3-candle reversal: down, indecision, up — bullish at support.",
    "evening_star":         "3-candle reversal: up, indecision, down — bearish at resistance.",
    "three_white_soldiers": "3 consecutive bull candles with small wicks — strong uptrend continuation.",
    "three_black_crows":    "3 consecutive bear candles with small wicks — strong downtrend continuation.",
    "tweezer_top":          "Two candles with matching highs — bearish reversal at resistance.",
    "tweezer_bottom":       "Two candles with matching lows — bullish reversal at support.",
    "piercing_line":        "Bear candle followed by bull candle closing above midpoint — bullish.",
    "dark_cloud_cover":     "Bull candle followed by bear candle closing below midpoint — bearish.",
    "spinning_top":         "Small body, wicks on both sides — indecision, possible trend pause.",
    # SMC / ICT
    "fair_value_gap":       "Imbalance between 3 candles (FVG) — price likely returns to fill the gap.",
    "order_block":          "Last opposing candle before a strong impulse move — institutional order zone.",
    "breaker_block":        "Failed order block flipped to opposite role — price respects new level.",
    "liquidity_sweep":      "Price spikes beyond a key high/low grabbing stops before reversing.",
    "mitigation_block":     "Order block that has been partially mitigated — remaining interest zone.",
    "equal_highs":          "Two or more equal highs forming a liquidity pool above — targets beyond.",
    "equal_lows":           "Two or more equal lows forming a liquidity pool below — targets beyond.",
    "rejection_block":      "Strong wick rejection at a level with high volume — price repelled forcefully.",
    "smt_divergence":       "Two correlated pairs diverge in structure — signals manipulation/reversal.",
    # Market Structure
    "bos":                  "Break of Structure — price closes beyond last swing high/low confirming trend.",
    "choch":                "Change of Character — first opposing BOS suggesting trend reversal.",
    "swing_high":           "Local swing high identified — potential resistance or liquidity target.",
    "swing_low":            "Local swing low identified — potential support or liquidity target.",
    "retracement_depth":    "Price retraced into 0.5–0.79 Fibonacci zone — optimal entry area.",
    # Session / Time
    "killzone":             "Price is in a high-probability session window (London/NY open).",
    "silver_bullet_window": "ICT Silver Bullet time window active (10:00–11:00 NY or 2:00–3:00 NY).",
    "amd":                  "Accumulation-Manipulation-Distribution cycle detected in session.",
    "judas_swing":          "False early-session move in opposite direction before true direction.",
    # Classical Chart Patterns
    "head_and_shoulders":   "Classic reversal: left shoulder, head, right shoulder — bearish breakdown.",
    "double_top":           "Price tests same resistance twice then breaks down — bearish reversal.",
    "double_bottom":        "Price tests same support twice then breaks up — bullish reversal.",
    "triangle_asc":         "Ascending triangle: flat top, rising lows — bullish breakout expected.",
    "triangle_desc":        "Descending triangle: flat bottom, falling highs — bearish breakdown expected.",
    "triangle_sym":         "Symmetrical triangle: converging highs/lows — breakout in trend direction.",
    "cup_and_handle":       "U-shaped base with small handle pullback — bullish continuation.",
    "flag":                 "Sharp move followed by tight consolidation — continuation pattern.",
    "pennant":              "Sharp move followed by converging consolidation — continuation pattern.",
    "wedge":                "Price channel narrowing against trend — reversal signal.",
    # Strategy Models
    "turtle_soup":          "Price briefly breaks a 20-period high/low then reverses — fade the breakout.",
    "silver_bullet":        "ICT Silver Bullet: FVG entry during specific time windows with trend.",
    "power_of_three":       "ICT Power of Three: accumulation, manipulation, distribution in one session.",
    "ote":                  "Optimal Trade Entry: retracement to 0.62–0.79 fib after BOS for entry.",
    # Key Levels
    "support_resistance":   "Price is testing a significant historical support or resistance level.",
    "prev_day_high":        "Price is testing the previous day's high — key intraday level.",
    "prev_day_low":         "Price is testing the previous day's low — key intraday level.",
    "prev_week_high":       "Price is testing the previous week's high — key swing level.",
    "prev_week_low":        "Price is testing the previous week's low — key swing level.",
    "prev_month_high":      "Price is testing the previous month's high — major structural level.",
    "prev_month_low":       "Price is testing the previous month's low — major structural level.",
}

# Pattern categories for UI grouping
PATTERN_CATEGORIES = {
    "Classic Candle Patterns": [
        "doji","hammer","inverted_hammer","shooting_star","hanging_man",
        "bullish_engulfing","bearish_engulfing","morning_star","evening_star",
        "three_white_soldiers","three_black_crows","tweezer_top","tweezer_bottom",
        "piercing_line","dark_cloud_cover","spinning_top",
    ],
    "SMC & ICT Patterns": [
        "fair_value_gap","order_block","breaker_block","liquidity_sweep",
        "mitigation_block","equal_highs","equal_lows","rejection_block","smt_divergence",
    ],
    "Market Structure": [
        "bos","choch","swing_high","swing_low","retracement_depth",
    ],
    "Time & Session Analysis": [
        "killzone","silver_bullet_window","amd","judas_swing",
    ],
    "Classical Chart Patterns": [
        "head_and_shoulders","double_top","double_bottom",
        "triangle_asc","triangle_desc","triangle_sym",
        "cup_and_handle","flag","pennant","wedge",
    ],
    "Strategy Models": [
        "turtle_soup","silver_bullet","power_of_three","ote",
    ],
    "Key Levels": [
        "support_resistance","prev_day_high","prev_day_low",
        "prev_week_high","prev_week_low","prev_month_high","prev_month_low",
    ],
}


class PatternEngine:
    """Detects all pattern categories from OHLC candle data."""

    def detect(self, candles, personal_rules=None, candle_timestamps=None) -> List[dict]:
        rules = dict(SYSTEM_RULES)
        if personal_rules:
            rules = self._apply_personal_rules(rules, personal_rules)

        if len(candles) < 1:
            return []

        cs = [c if isinstance(c, dict) else (c.dict() if hasattr(c, "dict") else vars(c)) for c in candles]
        matches = []

        # ── Classic 1-candle ─────────────────────────────────────
        c = cs[-1]
        self._check_doji(c, rules, matches)
        self._check_hammer(c, rules, matches)
        self._check_inverted_hammer(c, rules, matches)
        self._check_shooting_star(c, rules, matches)
        if len(cs) >= 4: self._check_hanging_man(c, rules, matches, cs)
        self._check_spinning_top(c, rules, matches)

        # ── Classic 2-candle ─────────────────────────────────────
        if len(cs) >= 2:
            c1, c0 = cs[-2], cs[-1]
            self._check_engulfing(c1, c0, rules, matches)
            self._check_tweezer(c1, c0, rules, matches)
            self._check_piercing_dark(c1, c0, rules, matches)

        # ── Classic 3-candle ─────────────────────────────────────
        if len(cs) >= 3:
            c2, c1, c0 = cs[-3], cs[-2], cs[-1]
            self._check_morning_evening_star(c2, c1, c0, rules, matches)
            self._check_soldiers_crows(c2, c1, c0, rules, matches)

        # ── SMC / ICT ────────────────────────────────────────────
        if len(cs) >= 3:
            self._check_fvg(cs, rules, matches)
            self._check_order_block(cs, rules, matches)
            self._check_breaker_block(cs, rules, matches)
            self._check_rejection_block(cs, rules, matches)
        if len(cs) >= 5:
            self._check_liquidity_sweep(cs, rules, matches)
            self._check_equal_highs_lows(cs, rules, matches)
            self._check_mitigation_block(cs, rules, matches)

        # ── Market Structure ─────────────────────────────────────
        if len(cs) >= 5:
            self._check_bos_choch(cs, rules, matches)
            self._check_swing_highs_lows(cs, rules, matches)
        if len(cs) >= 10:
            self._check_retracement_depth(cs, rules, matches)

        # ── Session / Time ────────────────────────────────────────
        self._check_killzone(rules, matches, candle_timestamps)
        self._check_silver_bullet_window(rules, matches, candle_timestamps)
        if len(cs) >= 10:
            self._check_amd(cs, rules, matches)
            self._check_judas_swing(cs, rules, matches)

        # ── Classical Chart Patterns ─────────────────────────────
        if len(cs) >= 10:
            self._check_double_top_bottom(cs, rules, matches)
            self._check_triangles(cs, rules, matches)
        if len(cs) >= 20:
            self._check_head_and_shoulders(cs, rules, matches)

        # ── Strategy Models ──────────────────────────────────────
        if len(cs) >= 5:
            self._check_turtle_soup(cs, rules, matches)
            self._check_ote(cs, rules, matches)

        # ── Key Levels ───────────────────────────────────────────
        if len(cs) >= 20:
            self._check_support_resistance(cs, rules, matches)
        if len(cs) >= 24:
            self._check_prev_levels(cs, rules, matches)

        return [
            {
                "name":        m.name,
                "bullish":     m.bullish,
                "confidence":  round(m.confidence, 2),
                "description": m.description,
            }
            for m in sorted(matches, key=lambda x: -x.confidence)
        ]

    # ── Helpers ───────────────────────────────────────────────────

    def _body(self, c): return abs(c["c"] - c["o"])
    def _range(self, c): return max(c["h"] - c["l"], 0.0001)
    def _upper_wick(self, c): return c["h"] - max(c["o"], c["c"])
    def _lower_wick(self, c): return min(c["o"], c["c"]) - c["l"]
    def _is_bull(self, c): return c["c"] > c["o"]
    def _mid(self, c): return (c["h"] + c["l"]) / 2

    # ── Classic 1-candle ─────────────────────────────────────────

    def _check_doji(self, c, rules, matches):
        r = rules.get("doji")
        if not r or not r.enabled: return
        ratio = self._body(c) / self._range(c)
        if ratio < 0.05:
            matches.append(PatternMatch("doji", True, 0.5 + (0.05 - ratio) * 5, [-1], PATTERN_DESCRIPTIONS["doji"]))

    def _check_hammer(self, c, rules, matches):
        r = rules.get("hammer")
        if not r or not r.enabled: return
        body, rng, lw, uw = self._body(c), self._range(c), self._lower_wick(c), self._upper_wick(c)
        if body / rng > 0.1 and lw >= 2 * body and uw < body:
            matches.append(PatternMatch("hammer", True, min(1.0, lw / (body * 2)), [-1], PATTERN_DESCRIPTIONS["hammer"]))

    def _check_inverted_hammer(self, c, rules, matches):
        r = rules.get("inverted_hammer")
        if not r or not r.enabled: return
        body, rng, uw, lw = self._body(c), self._range(c), self._upper_wick(c), self._lower_wick(c)
        if body / rng > 0.1 and uw >= 2 * body and lw < body:
            matches.append(PatternMatch("inverted_hammer", True, min(1.0, uw / (body * 2)), [-1], PATTERN_DESCRIPTIONS["inverted_hammer"]))

    def _check_shooting_star(self, c, rules, matches):
        r = rules.get("shooting_star")
        if not r or not r.enabled: return
        body, uw, lw = self._body(c), self._upper_wick(c), self._lower_wick(c)
        if not self._is_bull(c) and uw >= 2 * body and lw < body * 0.5:
            matches.append(PatternMatch("shooting_star", False, min(1.0, uw / (body * 2)), [-1], PATTERN_DESCRIPTIONS["shooting_star"]))

    def _check_hanging_man(self, c, rules, matches, cs):
        r = rules.get("hanging_man")
        if not r or not r.enabled: return
        if len(cs) < 4: return
        if not all(cs[i]["c"] > cs[i-1]["c"] for i in range(-3, -1)): return
        body, rng, lw, uw = self._body(c), self._range(c), self._lower_wick(c), self._upper_wick(c)
        if body / rng > 0.1 and lw >= 2 * body and uw < body:
            matches.append(PatternMatch("hanging_man", False, 0.65, [-1], PATTERN_DESCRIPTIONS["hanging_man"]))

    def _check_spinning_top(self, c, rules, matches):
        r = rules.get("spinning_top")
        if not r or not r.enabled: return
        body, rng, uw, lw = self._body(c), self._range(c), self._upper_wick(c), self._lower_wick(c)
        if 0.05 < body / rng < 0.35 and uw > body * 0.5 and lw > body * 0.5:
            matches.append(PatternMatch("spinning_top", True, 0.45, [-1], PATTERN_DESCRIPTIONS["spinning_top"]))

    # ── Classic 2-candle ─────────────────────────────────────────

    def _check_engulfing(self, c1, c0, rules, matches):
        body1, body0 = self._body(c1), self._body(c0)
        if body1 == 0: return
        ratio = body0 / body1
        bull_r = rules.get("bullish_engulfing")
        if bull_r and bull_r.enabled and not self._is_bull(c1) and self._is_bull(c0) and ratio >= (bull_r.min_engulf_ratio or 1.0):
            matches.append(PatternMatch("bullish_engulfing", True, min(1.0, 0.6 + (ratio - 1.0) * 0.2), [-2,-1], PATTERN_DESCRIPTIONS["bullish_engulfing"]))
        bear_r = rules.get("bearish_engulfing")
        if bear_r and bear_r.enabled and self._is_bull(c1) and not self._is_bull(c0) and ratio >= (bear_r.min_engulf_ratio or 1.0):
            matches.append(PatternMatch("bearish_engulfing", False, min(1.0, 0.6 + (ratio - 1.0) * 0.2), [-2,-1], PATTERN_DESCRIPTIONS["bearish_engulfing"]))

    def _check_tweezer(self, c1, c0, rules, matches):
        tol = self._range(c1) * 0.005
        top_r = rules.get("tweezer_top")
        if top_r and top_r.enabled and abs(c1["h"] - c0["h"]) <= tol and self._is_bull(c1) and not self._is_bull(c0):
            matches.append(PatternMatch("tweezer_top", False, 0.65, [-2,-1], PATTERN_DESCRIPTIONS["tweezer_top"]))
        bot_r = rules.get("tweezer_bottom")
        if bot_r and bot_r.enabled and abs(c1["l"] - c0["l"]) <= tol and not self._is_bull(c1) and self._is_bull(c0):
            matches.append(PatternMatch("tweezer_bottom", True, 0.65, [-2,-1], PATTERN_DESCRIPTIONS["tweezer_bottom"]))

    def _check_piercing_dark(self, c1, c0, rules, matches):
        mid1 = (c1["o"] + c1["c"]) / 2
        piercing_r = rules.get("piercing_line")
        if piercing_r and piercing_r.enabled and not self._is_bull(c1) and self._is_bull(c0) and c0["c"] > mid1 and c0["o"] < c1["c"]:
            matches.append(PatternMatch("piercing_line", True, 0.70, [-2,-1], PATTERN_DESCRIPTIONS["piercing_line"]))
        dark_r = rules.get("dark_cloud_cover")
        if dark_r and dark_r.enabled and self._is_bull(c1) and not self._is_bull(c0) and c0["c"] < mid1 and c0["o"] > c1["c"]:
            matches.append(PatternMatch("dark_cloud_cover", False, 0.70, [-2,-1], PATTERN_DESCRIPTIONS["dark_cloud_cover"]))

    # ── Classic 3-candle ─────────────────────────────────────────

    def _check_morning_evening_star(self, c2, c1, c0, rules, matches):
        body2, star_r = self._body(c2), self._body(c1) / self._range(c1)
        morn_r = rules.get("morning_star")
        if morn_r and morn_r.enabled and not self._is_bull(c2) and star_r < 0.3 and self._is_bull(c0) and self._body(c0) > body2 * 0.5 and c0["c"] > (c2["o"] + c2["c"]) / 2:
            matches.append(PatternMatch("morning_star", True, 0.80, [-3,-2,-1], PATTERN_DESCRIPTIONS["morning_star"]))
        eve_r = rules.get("evening_star")
        if eve_r and eve_r.enabled and self._is_bull(c2) and star_r < 0.3 and not self._is_bull(c0) and self._body(c0) > body2 * 0.5 and c0["c"] < (c2["o"] + c2["c"]) / 2:
            matches.append(PatternMatch("evening_star", False, 0.80, [-3,-2,-1], PATTERN_DESCRIPTIONS["evening_star"]))

    def _check_soldiers_crows(self, c2, c1, c0, rules, matches):
        sol_r = rules.get("three_white_soldiers")
        if sol_r and sol_r.enabled and self._is_bull(c2) and self._is_bull(c1) and self._is_bull(c0) and c1["c"] > c2["c"] and c0["c"] > c1["c"] and self._upper_wick(c0) < self._body(c0) * 0.3 and self._upper_wick(c1) < self._body(c1) * 0.3:
            matches.append(PatternMatch("three_white_soldiers", True, 0.85, [-3,-2,-1], PATTERN_DESCRIPTIONS["three_white_soldiers"]))
        crow_r = rules.get("three_black_crows")
        if crow_r and crow_r.enabled and not self._is_bull(c2) and not self._is_bull(c1) and not self._is_bull(c0) and c1["c"] < c2["c"] and c0["c"] < c1["c"] and self._lower_wick(c0) < self._body(c0) * 0.3 and self._lower_wick(c1) < self._body(c1) * 0.3:
            matches.append(PatternMatch("three_black_crows", False, 0.85, [-3,-2,-1], PATTERN_DESCRIPTIONS["three_black_crows"]))

    # ── SMC / ICT Patterns ────────────────────────────────────────

    def _check_fvg(self, cs, rules, matches):
        """Fair Value Gap: gap between c[-3].high and c[-1].low (bullish) or c[-3].low and c[-1].high (bearish)."""
        r = rules.get("fair_value_gap")
        if not r or not r.enabled: return
        c2, c1, c0 = cs[-3], cs[-2], cs[-1]
        # Bullish FVG: c[-3].high < c[-1].low (gap above c2, below c0)
        if c2["h"] < c0["l"]:
            gap_size = (c0["l"] - c2["h"]) / self._range(c1)
            conf = min(0.9, 0.6 + gap_size * 0.3)
            matches.append(PatternMatch("fair_value_gap", True, conf, [-3,-2,-1], PATTERN_DESCRIPTIONS["fair_value_gap"]))
        # Bearish FVG: c[-3].low > c[-1].high
        elif c2["l"] > c0["h"]:
            gap_size = (c2["l"] - c0["h"]) / self._range(c1)
            conf = min(0.9, 0.6 + gap_size * 0.3)
            matches.append(PatternMatch("fair_value_gap", False, conf, [-3,-2,-1], PATTERN_DESCRIPTIONS["fair_value_gap"]))

    def _check_order_block(self, cs, rules, matches):
        """Order Block: last bearish candle before a bullish impulse (bullish OB) or last bullish before bearish impulse."""
        r = rules.get("order_block")
        if not r or not r.enabled: return
        if len(cs) < 4: return
        # Look at cs[-4] to cs[-2] for the OB, cs[-1] as the impulse
        ob, impulse = cs[-2], cs[-1]
        body_ratio = self._body(impulse) / self._range(impulse)
        if body_ratio < 0.5: return  # impulse must be strong

        if not self._is_bull(ob) and self._is_bull(impulse) and impulse["c"] > ob["h"]:
            matches.append(PatternMatch("order_block", True, 0.78, [-2,-1], PATTERN_DESCRIPTIONS["order_block"]))
        elif self._is_bull(ob) and not self._is_bull(impulse) and impulse["c"] < ob["l"]:
            matches.append(PatternMatch("order_block", False, 0.78, [-2,-1], PATTERN_DESCRIPTIONS["order_block"]))

    def _check_breaker_block(self, cs, rules, matches):
        """Breaker Block: order block that price has broken through and is now retesting from other side."""
        r = rules.get("breaker_block")
        if not r or not r.enabled: return
        if len(cs) < 6: return
        # Simplified: look for prior swing broken, current price retesting
        highs = [c["h"] for c in cs[-6:-1]]
        lows  = [c["l"] for c in cs[-6:-1]]
        c0 = cs[-1]
        swing_high = max(highs)
        swing_low  = min(lows)
        # Bearish breaker: price broke above swing high then returned below it
        if c0["c"] < swing_high and cs[-2]["c"] > swing_high:
            matches.append(PatternMatch("breaker_block", False, 0.72, [-1], PATTERN_DESCRIPTIONS["breaker_block"]))
        # Bullish breaker: price broke below swing low then returned above it
        elif c0["c"] > swing_low and cs[-2]["c"] < swing_low:
            matches.append(PatternMatch("breaker_block", True, 0.72, [-1], PATTERN_DESCRIPTIONS["breaker_block"]))

    def _check_liquidity_sweep(self, cs, rules, matches):
        """Liquidity Sweep: wick spikes beyond prior swing high/low then closes back inside."""
        r = rules.get("liquidity_sweep")
        if not r or not r.enabled: return
        prior = cs[-6:-1]
        swing_high = max(c["h"] for c in prior)
        swing_low  = min(c["l"] for c in prior)
        c0 = cs[-1]
        # Bearish sweep: wick above swing high, closes below it
        if c0["h"] > swing_high and c0["c"] < swing_high:
            wick_size = (c0["h"] - swing_high) / self._range(c0)
            matches.append(PatternMatch("liquidity_sweep", False, min(0.9, 0.65 + wick_size), [-1], PATTERN_DESCRIPTIONS["liquidity_sweep"]))
        # Bullish sweep: wick below swing low, closes above it
        elif c0["l"] < swing_low and c0["c"] > swing_low:
            wick_size = (swing_low - c0["l"]) / self._range(c0)
            matches.append(PatternMatch("liquidity_sweep", True, min(0.9, 0.65 + wick_size), [-1], PATTERN_DESCRIPTIONS["liquidity_sweep"]))

    def _check_mitigation_block(self, cs, rules, matches):
        """Mitigation Block: partially consumed order block — price returned and partially filled it."""
        r = rules.get("mitigation_block")
        if not r or not r.enabled: return
        if len(cs) < 6: return
        ob = cs[-5]  # The original order block candle
        c0 = cs[-1]
        ob_mid = (ob["h"] + ob["l"]) / 2
        # Bullish mitigation: bearish OB was bullish, price came back to midpoint area
        if not self._is_bull(ob) and c0["l"] <= ob_mid <= c0["h"]:
            matches.append(PatternMatch("mitigation_block", True, 0.70, [-5,-1], PATTERN_DESCRIPTIONS["mitigation_block"]))
        elif self._is_bull(ob) and c0["l"] <= ob_mid <= c0["h"]:
            matches.append(PatternMatch("mitigation_block", False, 0.70, [-5,-1], PATTERN_DESCRIPTIONS["mitigation_block"]))

    def _check_equal_highs_lows(self, cs, rules, matches):
        """Equal Highs/Lows: two or more recent candles with nearly identical highs or lows."""
        tol_pct = 0.001  # 0.1% tolerance
        recent = cs[-8:]

        r_high = rules.get("equal_highs")
        if r_high and r_high.enabled:
            highs = [c["h"] for c in recent]
            max_h = max(highs)
            eq_count = sum(1 for h in highs if abs(h - max_h) / max_h < tol_pct)
            if eq_count >= 2:
                matches.append(PatternMatch("equal_highs", False, min(0.85, 0.6 + eq_count * 0.08), [-1], PATTERN_DESCRIPTIONS["equal_highs"]))

        r_low = rules.get("equal_lows")
        if r_low and r_low.enabled:
            lows = [c["l"] for c in recent]
            min_l = min(lows)
            eq_count = sum(1 for l in lows if min_l > 0 and abs(l - min_l) / min_l < tol_pct)
            if eq_count >= 2:
                matches.append(PatternMatch("equal_lows", True, min(0.85, 0.6 + eq_count * 0.08), [-1], PATTERN_DESCRIPTIONS["equal_lows"]))

    def _check_rejection_block(self, cs, rules, matches):
        """Rejection Block: massive wick (>60% of range) showing strong rejection."""
        r = rules.get("rejection_block")
        if not r or not r.enabled: return
        c0 = cs[-1]
        rng = self._range(c0)
        uw, lw = self._upper_wick(c0), self._lower_wick(c0)
        if uw / rng > 0.6:
            matches.append(PatternMatch("rejection_block", False, min(0.9, 0.6 + uw / rng * 0.4), [-1], PATTERN_DESCRIPTIONS["rejection_block"]))
        elif lw / rng > 0.6:
            matches.append(PatternMatch("rejection_block", True, min(0.9, 0.6 + lw / rng * 0.4), [-1], PATTERN_DESCRIPTIONS["rejection_block"]))

    # ── Market Structure ──────────────────────────────────────────

    def _find_swings(self, cs, lookback=3):
        """Find swing highs and lows using a simple pivot approach."""
        swing_highs, swing_lows = [], []
        for i in range(lookback, len(cs) - lookback):
            if all(cs[i]["h"] >= cs[i-j]["h"] for j in range(1, lookback+1)) and \
               all(cs[i]["h"] >= cs[i+j]["h"] for j in range(1, lookback+1)):
                swing_highs.append((i, cs[i]["h"]))
            if all(cs[i]["l"] <= cs[i-j]["l"] for j in range(1, lookback+1)) and \
               all(cs[i]["l"] <= cs[i+j]["l"] for j in range(1, lookback+1)):
                swing_lows.append((i, cs[i]["l"]))
        return swing_highs, swing_lows

    def _check_bos_choch(self, cs, rules, matches):
        """BOS / CHoCH detection using swing structure."""
        bos_r  = rules.get("bos")
        choch_r = rules.get("choch")
        if not bos_r.enabled and not choch_r.enabled: return

        swing_highs, swing_lows = self._find_swings(cs[:-1], lookback=2)
        c0 = cs[-1]

        if swing_highs and bos_r and bos_r.enabled:
            last_sh = swing_highs[-1][1]
            if c0["c"] > last_sh:
                matches.append(PatternMatch("bos", True, 0.80, [-1], PATTERN_DESCRIPTIONS["bos"]))

        if swing_lows and bos_r and bos_r.enabled:
            last_sl = swing_lows[-1][1]
            if c0["c"] < last_sl:
                matches.append(PatternMatch("bos", False, 0.80, [-1], PATTERN_DESCRIPTIONS["bos"]))

        # CHoCH: BOS against the prevailing trend
        if len(swing_highs) >= 2 and len(swing_lows) >= 2 and choch_r and choch_r.enabled:
            # Downtrend (lower highs): bullish CHoCH when breaking above last swing high
            if swing_highs[-1][1] < swing_highs[-2][1] and c0["c"] > swing_highs[-1][1]:
                matches.append(PatternMatch("choch", True, 0.85, [-1], PATTERN_DESCRIPTIONS["choch"]))
            # Uptrend (higher lows): bearish CHoCH when breaking below last swing low
            elif swing_lows[-1][1] > swing_lows[-2][1] and c0["c"] < swing_lows[-1][1]:
                matches.append(PatternMatch("choch", False, 0.85, [-1], PATTERN_DESCRIPTIONS["choch"]))

    def _check_swing_highs_lows(self, cs, rules, matches):
        sh_r = rules.get("swing_high")
        sl_r = rules.get("swing_low")
        swing_highs, swing_lows = self._find_swings(cs, lookback=2)

        if sh_r and sh_r.enabled and swing_highs:
            last_i, last_h = swing_highs[-1]
            if last_i == len(cs) - 3:  # swing formed on recent candles
                matches.append(PatternMatch("swing_high", False, 0.65, [last_i], PATTERN_DESCRIPTIONS["swing_high"]))

        if sl_r and sl_r.enabled and swing_lows:
            last_i, last_l = swing_lows[-1]
            if last_i == len(cs) - 3:
                matches.append(PatternMatch("swing_low", True, 0.65, [last_i], PATTERN_DESCRIPTIONS["swing_low"]))

    def _check_retracement_depth(self, cs, rules, matches):
        """Retracement into 0.50–0.79 Fibonacci zone after a significant move."""
        r = rules.get("retracement_depth")
        if not r or not r.enabled: return
        # Find the last significant move (last 10 candles)
        window = cs[-10:]
        high = max(c["h"] for c in window)
        low  = min(c["l"] for c in window)
        move = high - low
        if move == 0: return
        c0 = cs[-1]
        # Bullish retracement: upward move, price pulled back to fib zone
        fib_50 = high - move * 0.50
        fib_79 = high - move * 0.79
        if fib_79 <= c0["c"] <= fib_50 and c0["c"] < high:
            matches.append(PatternMatch("retracement_depth", True, 0.75, [-1], PATTERN_DESCRIPTIONS["retracement_depth"]))

    # ── Session / Time ────────────────────────────────────────────

    def _current_hour_utc(self):
        return datetime.utcnow().hour

    def _check_killzone(self, rules, matches, timestamps=None):
        r = rules.get("killzone")
        if not r or not r.enabled: return
        hour = self._current_hour_utc()
        # London open: 07:00–09:00 UTC, NY open: 12:00–14:00 UTC, London close: 15:00–16:00 UTC
        in_killzone = hour in (7, 8, 12, 13, 15)
        if in_killzone:
            zone = "London Open" if hour in (7, 8) else "NY Open" if hour in (12, 13) else "London Close"
            desc = f"Active killzone: {zone}. High-probability trading window for smart money entries."
            matches.append(PatternMatch("killzone", True, 0.70, [-1], desc))

    def _check_silver_bullet_window(self, rules, matches, timestamps=None):
        r = rules.get("silver_bullet_window")
        if not r or not r.enabled: return
        hour = self._current_hour_utc()
        # ICT Silver Bullet: 10:00-11:00 NY (15:00-16:00 UTC) or 14:00-15:00 NY (19:00-20:00 UTC)
        if hour in (15, 19):
            matches.append(PatternMatch("silver_bullet_window", True, 0.72, [-1], PATTERN_DESCRIPTIONS["silver_bullet_window"]))

    def _check_amd(self, cs, rules, matches):
        """AMD: look for accumulation (tight range), manipulation (spike), distribution (trend)."""
        r = rules.get("amd")
        if not r or not r.enabled: return
        acc  = cs[-10:-7]
        manip = cs[-7:-4]
        dist  = cs[-4:]
        acc_range  = max(c["h"] for c in acc)  - min(c["l"] for c in acc)
        manip_range= max(c["h"] for c in manip) - min(c["l"] for c in manip)
        dist_range = max(c["h"] for c in dist)  - min(c["l"] for c in dist)
        if acc_range < manip_range * 0.5 and dist_range > acc_range:
            is_bull = dist[-1]["c"] > dist[0]["o"]
            matches.append(PatternMatch("amd", is_bull, 0.68, [-10,-1], PATTERN_DESCRIPTIONS["amd"]))

    def _check_judas_swing(self, cs, rules, matches):
        """Judas Swing: early-session spike opposite to main direction before reversal."""
        r = rules.get("judas_swing")
        if not r or not r.enabled: return
        hour = self._current_hour_utc()
        if hour not in (7, 8, 12, 13): return  # only at session opens
        c0, c1 = cs[-1], cs[-2]
        # Large opposing wick that reversed
        if self._upper_wick(c1) > self._body(c1) * 2 and c0["c"] < c1["c"]:
            matches.append(PatternMatch("judas_swing", False, 0.70, [-2,-1], PATTERN_DESCRIPTIONS["judas_swing"]))
        elif self._lower_wick(c1) > self._body(c1) * 2 and c0["c"] > c1["c"]:
            matches.append(PatternMatch("judas_swing", True, 0.70, [-2,-1], PATTERN_DESCRIPTIONS["judas_swing"]))

    # ── Classical Chart Patterns ──────────────────────────────────

    def _check_head_and_shoulders(self, cs, rules, matches):
        r = rules.get("head_and_shoulders")
        if not r or not r.enabled: return
        # Simplified H&S using last 20 candles: find 3 peaks with middle highest
        window = cs[-20:]
        highs = [c["h"] for c in window]
        n = len(highs)
        best = None
        for i in range(2, n-2):
            for j in range(i+2, n-1):
                ls  = max(highs[max(0,i-3):i])
                head = max(highs[i:j])
                rs  = max(highs[j:min(n,j+4)])
                if head > ls * 1.02 and head > rs * 1.02 and abs(ls - rs) / head < 0.05:
                    best = (ls, head, rs)
        if best:
            neckline = (window[0]["l"] + window[-1]["l"]) / 2
            if cs[-1]["c"] < neckline:
                matches.append(PatternMatch("head_and_shoulders", False, 0.78, [-20,-1], PATTERN_DESCRIPTIONS["head_and_shoulders"]))

    def _check_double_top_bottom(self, cs, rules, matches):
        window = cs[-15:]
        highs = [c["h"] for c in window]
        lows  = [c["l"] for c in window]
        tol   = 0.005  # 0.5%

        dt_r = rules.get("double_top")
        if dt_r and dt_r.enabled:
            max_h = max(highs)
            peaks = [i for i, h in enumerate(highs) if abs(h - max_h) / max_h < tol]
            if len(peaks) >= 2 and peaks[-1] - peaks[0] >= 3:
                if cs[-1]["c"] < max_h * (1 - tol * 2):
                    matches.append(PatternMatch("double_top", False, 0.80, [-15,-1], PATTERN_DESCRIPTIONS["double_top"]))

        db_r = rules.get("double_bottom")
        if db_r and db_r.enabled:
            min_l = min(lows)
            troughs = [i for i, l in enumerate(lows) if min_l > 0 and abs(l - min_l) / min_l < tol]
            if len(troughs) >= 2 and troughs[-1] - troughs[0] >= 3:
                if cs[-1]["c"] > min_l * (1 + tol * 2):
                    matches.append(PatternMatch("double_bottom", True, 0.80, [-15,-1], PATTERN_DESCRIPTIONS["double_bottom"]))

    def _check_triangles(self, cs, rules, matches):
        window = cs[-15:]
        highs = [c["h"] for c in window]
        lows  = [c["l"] for c in window]
        n = len(window)
        # Trend of highs and lows using first/last comparison
        high_trend = highs[-1] - highs[0]
        low_trend  = lows[-1]  - lows[0]

        asc_r = rules.get("triangle_asc")
        if asc_r and asc_r.enabled and abs(high_trend) < (max(highs) - min(highs)) * 0.1 and low_trend > 0:
            matches.append(PatternMatch("triangle_asc", True, 0.72, [-15,-1], PATTERN_DESCRIPTIONS["triangle_asc"]))

        desc_r = rules.get("triangle_desc")
        if desc_r and desc_r.enabled and abs(low_trend) < (max(lows) - min(lows)) * 0.1 and high_trend < 0:
            matches.append(PatternMatch("triangle_desc", False, 0.72, [-15,-1], PATTERN_DESCRIPTIONS["triangle_desc"]))

        sym_r = rules.get("triangle_sym")
        if sym_r and sym_r.enabled and high_trend < 0 and low_trend > 0:
            matches.append(PatternMatch("triangle_sym", True, 0.65, [-15,-1], PATTERN_DESCRIPTIONS["triangle_sym"]))

    # ── Strategy Models ───────────────────────────────────────────

    def _check_turtle_soup(self, cs, rules, matches):
        """Turtle Soup: price breaks 20-period high/low then reverses within 2 bars."""
        r = rules.get("turtle_soup")
        if not r or not r.enabled: return
        if len(cs) < 22: return
        period_high = max(c["h"] for c in cs[-22:-2])
        period_low  = min(c["l"] for c in cs[-22:-2])
        c1, c0 = cs[-2], cs[-1]
        # Bearish turtle soup: broke above period high, now reversing
        if c1["h"] > period_high and c0["c"] < period_high:
            matches.append(PatternMatch("turtle_soup", False, 0.75, [-2,-1], PATTERN_DESCRIPTIONS["turtle_soup"]))
        elif c1["l"] < period_low and c0["c"] > period_low:
            matches.append(PatternMatch("turtle_soup", True, 0.75, [-2,-1], PATTERN_DESCRIPTIONS["turtle_soup"]))

    def _check_ote(self, cs, rules, matches):
        """OTE: Optimal Trade Entry — retracement to 0.62-0.79 fib after BOS."""
        r = rules.get("ote")
        if not r or not r.enabled: return
        if len(cs) < 10: return
        window = cs[-10:]
        high = max(c["h"] for c in window)
        low  = min(c["l"] for c in window)
        move = high - low
        if move == 0: return
        c0 = cs[-1]
        fib_62 = high - move * 0.62
        fib_79 = high - move * 0.79
        if fib_79 <= c0["c"] <= fib_62:
            matches.append(PatternMatch("ote", True, 0.80, [-1], PATTERN_DESCRIPTIONS["ote"]))

    # ── Key Levels ────────────────────────────────────────────────

    def _check_support_resistance(self, cs, rules, matches):
        r = rules.get("support_resistance")
        if not r or not r.enabled: return
        window = cs[-20:]
        highs = sorted([c["h"] for c in window], reverse=True)
        lows  = sorted([c["l"] for c in window])
        c0 = cs[-1]
        tol = self._range(c0) * 0.5
        # Resistance: current price near a cluster of prior highs
        resistance_zone = highs[0]
        if abs(c0["c"] - resistance_zone) <= tol:
            matches.append(PatternMatch("support_resistance", False, 0.70, [-1], PATTERN_DESCRIPTIONS["support_resistance"]))
        # Support: current price near a cluster of prior lows
        support_zone = lows[0]
        if abs(c0["c"] - support_zone) <= tol:
            matches.append(PatternMatch("support_resistance", True, 0.70, [-1], PATTERN_DESCRIPTIONS["support_resistance"]))

    def _check_prev_levels(self, cs, rules, matches):
        """Previous day/week/month high and low levels."""
        if len(cs) < 24: return
        c0 = cs[-1]
        tol = self._range(c0) * 0.3

        # Approximate: treat last 24 candles as "previous day" for hourly data
        prev_day = cs[-25:-1]
        prev_week = cs[-min(len(cs), 120):-1] if len(cs) >= 120 else cs[:-1]

        level_checks = [
            ("prev_day_high",  max(c["h"] for c in prev_day[-24:]),  False),
            ("prev_day_low",   min(c["l"] for c in prev_day[-24:]),  True),
            ("prev_week_high", max(c["h"] for c in prev_week), False),
            ("prev_week_low",  min(c["l"] for c in prev_week), True),
        ]

        for name, level, bullish in level_checks:
            r = rules.get(name)
            if r and r.enabled and abs(c0["c"] - level) <= tol:
                matches.append(PatternMatch(name, bullish, 0.72, [-1], PATTERN_DESCRIPTIONS[name]))

    # ── Personal rules ────────────────────────────────────────────

    def _apply_personal_rules(self, rules: dict, personal_rules: list) -> dict:
        rules = dict(rules)
        for pr in personal_rules:
            name = pr.get("name", "").lower().replace(" ", "_")
            if name in rules:
                r = rules[name]
                rules[name] = PatternRule(
                    name=r.name,
                    enabled=pr.get("enabled", r.enabled),
                    min_body_ratio=pr.get("min_body_ratio", r.min_body_ratio),
                    max_wick_ratio=pr.get("max_wick_ratio", r.max_wick_ratio),
                    min_engulf_ratio=pr.get("min_engulf_ratio", r.min_engulf_ratio),
                )
        return rules
