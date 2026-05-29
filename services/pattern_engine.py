"""
services/pattern_engine.py
Real candle pattern detection engine.
Detects 16 patterns using OHLC math, supports per-pattern user rule overrides.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class PatternRule:
    """User-defined or system rule for a pattern."""
    name: str
    enabled: bool = True
    # Optional user overrides — if set, replaces system threshold
    min_body_ratio: Optional[float] = None      # body / total range
    max_wick_ratio: Optional[float] = None      # wick / total range
    min_engulf_ratio: Optional[float] = None    # engulfing: how much to exceed prev body


@dataclass
class PatternMatch:
    name: str
    bullish: bool                      # True = bullish signal, False = bearish
    confidence: float                  # 0.0–1.0
    candle_indices: List[int]          # which candles (from end of array) form the pattern
    description: str


# ── System default rules ───────────────────────────────────────────
SYSTEM_RULES = {
    "doji":                PatternRule("doji",                min_body_ratio=0.0, max_wick_ratio=1.0),
    "hammer":              PatternRule("hammer",              min_body_ratio=0.15),
    "inverted_hammer":     PatternRule("inverted_hammer",     min_body_ratio=0.15),
    "shooting_star":       PatternRule("shooting_star",       min_body_ratio=0.15),
    "hanging_man":         PatternRule("hanging_man",         min_body_ratio=0.15),
    "bullish_engulfing":   PatternRule("bullish_engulfing",   min_engulf_ratio=1.0),
    "bearish_engulfing":   PatternRule("bearish_engulfing",   min_engulf_ratio=1.0),
    "morning_star":        PatternRule("morning_star"),
    "evening_star":        PatternRule("evening_star"),
    "three_white_soldiers":PatternRule("three_white_soldiers"),
    "three_black_crows":   PatternRule("three_black_crows"),
    "tweezer_top":         PatternRule("tweezer_top"),
    "tweezer_bottom":      PatternRule("tweezer_bottom"),
    "piercing_line":       PatternRule("piercing_line"),
    "dark_cloud_cover":    PatternRule("dark_cloud_cover"),
    "spinning_top":        PatternRule("spinning_top"),
}

# User-readable descriptions
PATTERN_DESCRIPTIONS = {
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
}


class PatternEngine:
    """
    Detects candle patterns from a list of Candle objects.
    Applies user-defined rule overrides where provided.
    """

    def detect(self, candles, personal_rules: Optional[List[dict]] = None) -> List[dict]:
        """
        Run all enabled pattern detectors.
        Returns list of matched patterns with confidence and metadata.
        """
        # Merge user rules over system rules
        rules = dict(SYSTEM_RULES)
        if personal_rules:
            rules = self._apply_personal_rules(rules, personal_rules)

        if len(candles) < 1:
            return []

        # Convert to raw dicts if needed
        cs = [c.dict() if hasattr(c, "dict") else c for c in candles]

        matches = []

        # 1-candle patterns (on last candle)
        if len(cs) >= 1:
            c = cs[-1]
            self._check_doji(c, rules, matches)
            self._check_hammer(c, rules, matches)
            self._check_inverted_hammer(c, rules, matches)
            self._check_shooting_star(c, rules, matches)
            self._check_hanging_man(c, rules, matches, cs)
            self._check_spinning_top(c, rules, matches)

        # 2-candle patterns
        if len(cs) >= 2:
            c1, c0 = cs[-2], cs[-1]
            self._check_engulfing(c1, c0, rules, matches)
            self._check_tweezer(c1, c0, rules, matches)
            self._check_piercing_dark(c1, c0, rules, matches)

        # 3-candle patterns
        if len(cs) >= 3:
            c2, c1, c0 = cs[-3], cs[-2], cs[-1]
            self._check_morning_evening_star(c2, c1, c0, rules, matches)
            self._check_soldiers_crows(c2, c1, c0, rules, matches)

        return [
            {
                "name":        m.name,
                "bullish":     m.bullish,
                "confidence":  round(m.confidence, 2),
                "description": m.description,
            }
            for m in sorted(matches, key=lambda x: -x.confidence)
        ]

    # ── 1-candle detectors ────────────────────────────────────────

    def _body(self, c) -> float:
        return abs(c["c"] - c["o"])

    def _range(self, c) -> float:
        return c["h"] - c["l"] if c["h"] != c["l"] else 0.0001

    def _upper_wick(self, c) -> float:
        return c["h"] - max(c["o"], c["c"])

    def _lower_wick(self, c) -> float:
        return min(c["o"], c["c"]) - c["l"]

    def _is_bull(self, c) -> bool:
        return c["c"] > c["o"]

    def _check_doji(self, c, rules, matches):
        r = rules.get("doji")
        if not r or not r.enabled: return
        body  = self._body(c)
        rng   = self._range(c)
        ratio = body / rng
        if ratio < 0.05:
            matches.append(PatternMatch(
                "doji", True, 0.5 + (0.05 - ratio) * 5,
                [-1], PATTERN_DESCRIPTIONS["doji"]
            ))

    def _check_hammer(self, c, rules, matches):
        r = rules.get("hammer")
        if not r or not r.enabled: return
        body  = self._body(c)
        rng   = self._range(c)
        lw    = self._lower_wick(c)
        uw    = self._upper_wick(c)
        if body / rng > 0.1 and lw >= 2 * body and uw < body:
            conf = min(1.0, lw / (body * 2))
            matches.append(PatternMatch("hammer", True, conf, [-1], PATTERN_DESCRIPTIONS["hammer"]))

    def _check_inverted_hammer(self, c, rules, matches):
        r = rules.get("inverted_hammer")
        if not r or not r.enabled: return
        body = self._body(c)
        rng  = self._range(c)
        uw   = self._upper_wick(c)
        lw   = self._lower_wick(c)
        if body / rng > 0.1 and uw >= 2 * body and lw < body:
            conf = min(1.0, uw / (body * 2))
            matches.append(PatternMatch("inverted_hammer", True, conf, [-1], PATTERN_DESCRIPTIONS["inverted_hammer"]))

    def _check_shooting_star(self, c, rules, matches):
        r = rules.get("shooting_star")
        if not r or not r.enabled: return
        body = self._body(c)
        rng  = self._range(c)
        uw   = self._upper_wick(c)
        lw   = self._lower_wick(c)
        if not self._is_bull(c) and uw >= 2 * body and lw < body * 0.5:
            conf = min(1.0, uw / (body * 2))
            matches.append(PatternMatch("shooting_star", False, conf, [-1], PATTERN_DESCRIPTIONS["shooting_star"]))

    def _check_hanging_man(self, c, rules, matches, cs):
        r = rules.get("hanging_man")
        if not r or not r.enabled: return
        # Needs prior uptrend (last 3 candles rising)
        if len(cs) < 4: return
        uptrend = all(cs[i]["c"] > cs[i-1]["c"] for i in range(-3, -1))
        if not uptrend: return
        body = self._body(c)
        rng  = self._range(c)
        lw   = self._lower_wick(c)
        uw   = self._upper_wick(c)
        if body / rng > 0.1 and lw >= 2 * body and uw < body:
            matches.append(PatternMatch("hanging_man", False, 0.65, [-1], PATTERN_DESCRIPTIONS["hanging_man"]))

    def _check_spinning_top(self, c, rules, matches):
        r = rules.get("spinning_top")
        if not r or not r.enabled: return
        body = self._body(c)
        rng  = self._range(c)
        uw   = self._upper_wick(c)
        lw   = self._lower_wick(c)
        if 0.05 < body / rng < 0.35 and uw > body * 0.5 and lw > body * 0.5:
            matches.append(PatternMatch("spinning_top", True, 0.45, [-1], PATTERN_DESCRIPTIONS["spinning_top"]))

    # ── 2-candle detectors ────────────────────────────────────────

    def _check_engulfing(self, c1, c0, rules, matches):
        bull_r = rules.get("bullish_engulfing")
        bear_r = rules.get("bearish_engulfing")
        body1 = self._body(c1)
        body0 = self._body(c0)
        if body1 == 0: return
        ratio = body0 / body1

        if bull_r and bull_r.enabled:
            min_r = bull_r.min_engulf_ratio or 1.0
            if not self._is_bull(c1) and self._is_bull(c0) and ratio >= min_r:
                conf = min(1.0, 0.6 + (ratio - 1.0) * 0.2)
                matches.append(PatternMatch("bullish_engulfing", True, conf, [-2,-1], PATTERN_DESCRIPTIONS["bullish_engulfing"]))

        if bear_r and bear_r.enabled:
            min_r = bear_r.min_engulf_ratio or 1.0
            if self._is_bull(c1) and not self._is_bull(c0) and ratio >= min_r:
                conf = min(1.0, 0.6 + (ratio - 1.0) * 0.2)
                matches.append(PatternMatch("bearish_engulfing", False, conf, [-2,-1], PATTERN_DESCRIPTIONS["bearish_engulfing"]))

    def _check_tweezer(self, c1, c0, rules, matches):
        tol = (c1["h"] - c1["l"]) * 0.005   # 0.5% of range tolerance

        top_r = rules.get("tweezer_top")
        if top_r and top_r.enabled and abs(c1["h"] - c0["h"]) <= tol:
            if self._is_bull(c1) and not self._is_bull(c0):
                matches.append(PatternMatch("tweezer_top", False, 0.65, [-2,-1], PATTERN_DESCRIPTIONS["tweezer_top"]))

        bot_r = rules.get("tweezer_bottom")
        if bot_r and bot_r.enabled and abs(c1["l"] - c0["l"]) <= tol:
            if not self._is_bull(c1) and self._is_bull(c0):
                matches.append(PatternMatch("tweezer_bottom", True, 0.65, [-2,-1], PATTERN_DESCRIPTIONS["tweezer_bottom"]))

    def _check_piercing_dark(self, c1, c0, rules, matches):
        mid1 = (c1["o"] + c1["c"]) / 2

        piercing_r = rules.get("piercing_line")
        if piercing_r and piercing_r.enabled:
            if not self._is_bull(c1) and self._is_bull(c0) and c0["c"] > mid1 and c0["o"] < c1["c"]:
                matches.append(PatternMatch("piercing_line", True, 0.70, [-2,-1], PATTERN_DESCRIPTIONS["piercing_line"]))

        dark_r = rules.get("dark_cloud_cover")
        if dark_r and dark_r.enabled:
            if self._is_bull(c1) and not self._is_bull(c0) and c0["c"] < mid1 and c0["o"] > c1["c"]:
                matches.append(PatternMatch("dark_cloud_cover", False, 0.70, [-2,-1], PATTERN_DESCRIPTIONS["dark_cloud_cover"]))

    # ── 3-candle detectors ────────────────────────────────────────

    def _check_morning_evening_star(self, c2, c1, c0, rules, matches):
        body2 = self._body(c2)
        body1 = self._body(c1)
        body0 = self._body(c0)
        star_r = body1 / max(self._range(c1), 0.0001)

        morn_r = rules.get("morning_star")
        if morn_r and morn_r.enabled:
            if (not self._is_bull(c2) and star_r < 0.3 and self._is_bull(c0)
                    and body0 > body2 * 0.5 and c0["c"] > (c2["o"] + c2["c"]) / 2):
                matches.append(PatternMatch("morning_star", True, 0.80, [-3,-2,-1], PATTERN_DESCRIPTIONS["morning_star"]))

        eve_r = rules.get("evening_star")
        if eve_r and eve_r.enabled:
            if (self._is_bull(c2) and star_r < 0.3 and not self._is_bull(c0)
                    and body0 > body2 * 0.5 and c0["c"] < (c2["o"] + c2["c"]) / 2):
                matches.append(PatternMatch("evening_star", False, 0.80, [-3,-2,-1], PATTERN_DESCRIPTIONS["evening_star"]))

    def _check_soldiers_crows(self, c2, c1, c0, rules, matches):
        sol_r = rules.get("three_white_soldiers")
        if sol_r and sol_r.enabled:
            if (self._is_bull(c2) and self._is_bull(c1) and self._is_bull(c0)
                    and c1["c"] > c2["c"] and c0["c"] > c1["c"]
                    and self._upper_wick(c0) < self._body(c0) * 0.3
                    and self._upper_wick(c1) < self._body(c1) * 0.3):
                matches.append(PatternMatch("three_white_soldiers", True, 0.85, [-3,-2,-1], PATTERN_DESCRIPTIONS["three_white_soldiers"]))

        crow_r = rules.get("three_black_crows")
        if crow_r and crow_r.enabled:
            if (not self._is_bull(c2) and not self._is_bull(c1) and not self._is_bull(c0)
                    and c1["c"] < c2["c"] and c0["c"] < c1["c"]
                    and self._lower_wick(c0) < self._body(c0) * 0.3
                    and self._lower_wick(c1) < self._body(c1) * 0.3):
                matches.append(PatternMatch("three_black_crows", False, 0.85, [-3,-2,-1], PATTERN_DESCRIPTIONS["three_black_crows"]))

    # ── Personal rule merging ─────────────────────────────────────

    def _apply_personal_rules(self, rules: dict, personal_rules: list) -> dict:
        """
        Merge user-defined rules into the system rules dict.
        personal_rules format: list of dicts with keys:
          name, enabled, min_body_ratio, max_wick_ratio, min_engulf_ratio
        """
        rules = dict(rules)  # copy
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
