"""
services/indicator_engine.py
Full 30+ indicator engine — all calculated from raw OHLC on the backend.
No indicator data needed from the trading platform.

Groups:
  momentum   — RSI, Stoch, Stoch RSI, MACD, CCI, AO, Momentum, Williams %R, UO, ROC
  trend      — MA, BB, ADX, Ichimoku, SAR, Supertrend, Keltner, MA Ribbon
  volume     — OBV, VWAP, A/D, CMF
  volatility — ATR, Donchian, Aroon, Pivot Points
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd
import pandas_ta as ta

INDICATOR_DEFAULTS = {
    "rsi":         {"period": 14},
    "stoch":       {"k": 14, "d": 3, "smooth": 3},
    "stoch_rsi":   {"period": 14, "rsi_period": 14, "k": 3, "d": 3},
    "macd":        {"fast": 12, "slow": 26, "signal": 9},
    "cci":         {"period": 20},
    "ao":          {"fast": 5, "slow": 34},
    "momentum":    {"period": 10},
    "williams_r":  {"period": 14},
    "uo":          {"fast": 7, "medium": 14, "slow": 28},
    "roc":         {"period": 9},
    "ma":          {"period": 20, "type": "ema"},
    "bb":          {"period": 20, "std": 2.0},
    "adx":         {"period": 14},
    "ichimoku":    {"tenkan": 9, "kijun": 26, "senkou": 52},
    "sar":         {"step": 0.02, "max": 0.2},
    "supertrend":  {"period": 10, "multiplier": 3.0},
    "keltner":     {"period": 20, "multiplier": 2.0},
    "ma_ribbon":   {"periods": [8, 13, 21, 34, 55, 89]},
    "obv":         {},
    "vwap":        {},
    "ad":          {},
    "cmf":         {"period": 20},
    "atr":         {"period": 14},
    "donchian":    {"period": 20},
    "aroon":       {"period": 25},
    "pivot_points": {"type": "traditional"},
}

INDICATOR_GROUPS = {
    "momentum":   ["rsi","stoch","stoch_rsi","macd","cci","ao","momentum","williams_r","uo","roc"],
    "trend":      ["ma","bb","adx","ichimoku","sar","supertrend","keltner","ma_ribbon"],
    "volume":     ["obv","vwap","ad","cmf"],
    "volatility": ["atr","donchian","aroon","pivot_points"],
}

INDICATOR_DISPLAY = {
    "rsi": "RSI", "stoch": "Stochastic", "stoch_rsi": "Stoch RSI",
    "macd": "MACD", "cci": "CCI", "ao": "Awesome Oscillator",
    "momentum": "Momentum", "williams_r": "Williams %R",
    "uo": "Ultimate Oscillator", "roc": "Rate of Change",
    "ma": "Moving Average", "bb": "Bollinger Bands", "adx": "ADX",
    "ichimoku": "Ichimoku Cloud", "sar": "Parabolic SAR",
    "supertrend": "Supertrend", "keltner": "Keltner Channels",
    "ma_ribbon": "MA Ribbon", "obv": "OBV", "vwap": "VWAP",
    "ad": "A/D Line", "cmf": "CMF", "atr": "ATR",
    "donchian": "Donchian Channels", "aroon": "Aroon",
    "pivot_points": "Pivot Points",
}


@dataclass
class IndicatorResult:
    name: str
    value: Optional[float]
    signal: str   # bullish | bearish | neutral
    label: str
    extra: dict = field(default_factory=dict)


class IndicatorEngine:

    def calculate_for_report(
        self,
        candles: list,
        enabled: list | None = None,
        user_settings: dict | None = None,
    ) -> dict:
        if len(candles) < 5:
            return {"groups": {}, "overall_bias": "neutral", "bull_count": 0, "bear_count": 0, "total": 0}

        df = self._df(candles)
        settings = {n: {**d, **(( user_settings or {}).get(n, {}))} for n, d in INDICATOR_DEFAULTS.items()}
        to_calc = enabled or list(INDICATOR_DEFAULTS.keys())

        raw = {}
        for name in to_calc:
            try:
                r = self._calc(name, df, settings.get(name, {}))
                if r:
                    raw[name] = r
            except Exception:
                pass

        groups = {}
        for group, names in INDICATOR_GROUPS.items():
            grp = {}
            for n in names:
                if n in raw:
                    r = raw[n]
                    grp[n] = {"display": INDICATOR_DISPLAY.get(n, n),
                              "label": r.label, "signal": r.signal,
                              "value": r.value, "extra": r.extra}
            if grp:
                groups[group] = grp

        sigs = [r.signal for r in raw.values()]
        bull = sigs.count("bullish"); bear = sigs.count("bearish")
        bias = "bullish" if bull > bear else ("bearish" if bear > bull else "neutral")
        return {"groups": groups, "overall_bias": bias,
                "bull_count": bull, "bear_count": bear,
                "neutral_count": sigs.count("neutral"), "total": len(sigs)}

    def _df(self, candles):
        df = pd.DataFrame(candles)
        df.columns = [c.lower() for c in df.columns]
        rename = {"o":"open","h":"high","l":"low","c":"close","v":"volume","t":"time"}
        df = df.rename(columns={k:v for k,v in rename.items() if k in df.columns})
        for col in ("open","high","low","close"):
            df[col] = pd.to_numeric(df.get(col, 0), errors="coerce")
        df["volume"] = pd.to_numeric(df.get("volume", 0), errors="coerce").fillna(0)
        return df.sort_values("time").reset_index(drop=True)

    def _last(self, s) -> Optional[float]:
        try:
            v = s.dropna().iloc[-1]; return float(v) if pd.notna(v) else None
        except: return None

    def _prev(self, s) -> Optional[float]:
        try:
            v = s.dropna().iloc[-2]; return float(v) if pd.notna(v) else None
        except: return None

    def _calc(self, name, df, s) -> Optional[IndicatorResult]:
        c=df["close"]; h=df["high"]; l=df["low"]; v=df["volume"]

        if name=="rsi":
            val=ta.rsi(c,length=s["period"]); v2=self._last(val)
            if v2 is None: return None
            sig="bullish" if v2<30 else ("bearish" if v2>70 else "neutral")
            lbl=f"RSI({s['period']}): {v2:.1f} — {'Oversold ↑' if v2<30 else 'Overbought ↓' if v2>70 else 'Neutral'}"
            return IndicatorResult(name,v2,sig,lbl)

        if name=="macd":
            m=ta.macd(c,fast=s["fast"],slow=s["slow"],signal=s["signal"])
            if m is None or m.empty: return None
            mv=self._last(m.iloc[:,0]); sv=self._last(m.iloc[:,1]); hv=self._last(m.iloc[:,2])
            if mv is None: return None
            sig="bullish" if (hv or 0)>0 else "bearish"
            return IndicatorResult(name,mv,sig,
                f"MACD({s['fast']},{s['slow']},{s['signal']}): {mv:.5f} Hist:{hv:.5f}",
                {"signal":sv,"histogram":hv})

        if name=="stoch":
            st=ta.stoch(h,l,c,k=s["k"],d=s["d"],smooth_k=s["smooth"])
            if st is None or st.empty: return None
            kv=self._last(st.iloc[:,0]); dv=self._last(st.iloc[:,1])
            if kv is None: return None
            sig="bullish" if kv<20 else ("bearish" if kv>80 else "neutral")
            return IndicatorResult(name,kv,sig,f"Stoch({s['k']},{s['d']}): K={kv:.1f} D={dv:.1f}",{"k":kv,"d":dv})

        if name=="stoch_rsi":
            sr=ta.stochrsi(c,length=s["period"],rsi_length=s["rsi_period"],k=s["k"],d=s["d"])
            if sr is None or sr.empty: return None
            kv=self._last(sr.iloc[:,0]); dv=self._last(sr.iloc[:,1])
            if kv is None: return None
            sig="bullish" if kv<20 else ("bearish" if kv>80 else "neutral")
            return IndicatorResult(name,kv,sig,f"StochRSI: K={kv:.1f} D={dv:.1f}",{"k":kv,"d":dv})

        if name=="cci":
            val=ta.cci(h,l,c,length=s["period"]); v2=self._last(val)
            if v2 is None: return None
            sig="bullish" if v2<-100 else ("bearish" if v2>100 else "neutral")
            return IndicatorResult(name,v2,sig,f"CCI({s['period']}): {v2:.1f}")

        if name=="ao":
            val=ta.ao(h,l,fast=s["fast"],slow=s["slow"]); v2=self._last(val)
            if v2 is None: return None
            return IndicatorResult(name,v2,"bullish" if v2>0 else "bearish",f"AO: {v2:.5f}")

        if name=="momentum":
            val=ta.mom(c,length=s["period"]); v2=self._last(val)
            if v2 is None: return None
            return IndicatorResult(name,v2,"bullish" if v2>0 else "bearish",f"Mom({s['period']}): {v2:.5f}")

        if name=="williams_r":
            val=ta.willr(h,l,c,length=s["period"]); v2=self._last(val)
            if v2 is None: return None
            sig="bullish" if v2<-80 else ("bearish" if v2>-20 else "neutral")
            return IndicatorResult(name,v2,sig,f"W%R({s['period']}): {v2:.1f}")

        if name=="uo":
            val=ta.uo(h,l,c,fast=s["fast"],medium=s["medium"],slow=s["slow"]); v2=self._last(val)
            if v2 is None: return None
            sig="bullish" if v2<30 else ("bearish" if v2>70 else "neutral")
            return IndicatorResult(name,v2,sig,f"UO: {v2:.1f}")

        if name=="roc":
            val=ta.roc(c,length=s["period"]); v2=self._last(val)
            if v2 is None: return None
            return IndicatorResult(name,v2,"bullish" if v2>0 else "bearish",f"ROC({s['period']}): {v2:.2f}%")

        if name=="ma":
            fn={"sma":ta.sma,"ema":ta.ema,"wma":ta.wma,"hma":ta.hma}
            val=fn.get(s.get("type","ema"),ta.ema)(c,length=s["period"]); v2=self._last(val)
            price=self._last(c)
            if v2 is None or price is None: return None
            sig="bullish" if price>v2 else "bearish"
            return IndicatorResult(name,v2,sig,f"{s.get('type','EMA').upper()}({s['period']}): {v2:.5f}")

        if name=="bb":
            b=ta.bbands(c,length=s["period"],std=s["std"])
            if b is None or b.empty: return None
            upper=self._last(b.iloc[:,2]); mid=self._last(b.iloc[:,1]); lower=self._last(b.iloc[:,0])
            price=self._last(c)
            if upper is None or price is None: return None
            sig="bullish" if price<lower else ("bearish" if price>upper else "neutral")
            return IndicatorResult(name,mid,sig,f"BB({s['period']}): U={upper:.5f} M={mid:.5f} L={lower:.5f}",
                {"upper":upper,"middle":mid,"lower":lower})

        if name=="adx":
            val=ta.adx(h,l,c,length=s["period"])
            if val is None or val.empty: return None
            av=self._last(val.iloc[:,0]); dp=self._last(val.iloc[:,1]); dn=self._last(val.iloc[:,2])
            if av is None: return None
            sig="bullish" if (dp or 0)>(dn or 0) else "bearish"
            return IndicatorResult(name,av,sig,f"ADX({s['period']}): {av:.1f} {'Strong' if av>25 else 'Weak'} +DI={dp:.1f} -DI={dn:.1f}",
                {"adx":av,"dmp":dp,"dmn":dn})

        if name=="sar":
            val=ta.psar(h,l,af0=s["step"],max_af=s["max"])
            if val is None or val.empty: return None
            sv=self._last(val.iloc[:,0]); price=self._last(c)
            if sv is None or price is None: return None
            sig="bullish" if price>sv else "bearish"
            return IndicatorResult(name,sv,sig,f"SAR: {sv:.5f} ({'Bull' if sig=='bullish' else 'Bear'})")

        if name=="supertrend":
            val=ta.supertrend(h,l,c,length=s["period"],multiplier=s["multiplier"])
            if val is None or val.empty: return None
            sv=self._last(val.iloc[:,0]); tr=self._last(val.iloc[:,1])
            if sv is None: return None
            sig="bullish" if (tr or 0)>0 else "bearish"
            return IndicatorResult(name,sv,sig,f"ST({s['period']},{s['multiplier']}): {sv:.5f} {'↑' if sig=='bullish' else '↓'}")

        if name=="keltner":
            val=ta.kc(h,l,c,length=s["period"],scalar=s["multiplier"])
            if val is None or val.empty: return None
            upper=self._last(val.iloc[:,2]); mid=self._last(val.iloc[:,1]); lower=self._last(val.iloc[:,0])
            price=self._last(c)
            if upper is None or price is None: return None
            sig="bullish" if price<lower else ("bearish" if price>upper else "neutral")
            return IndicatorResult(name,mid,sig,f"KC: U={upper:.5f} M={mid:.5f} L={lower:.5f}",
                {"upper":upper,"middle":mid,"lower":lower})

        if name=="ma_ribbon":
            vals={}
            for p in s["periods"]:
                v2=self._last(ta.ema(c,length=p))
                if v2 is not None: vals[f"ema{p}"]=round(v2,5)
            if not vals: return None
            price=self._last(c); vlist=list(vals.values())
            sig="bullish" if price>vlist[-1] else "bearish"
            return IndicatorResult(name,vlist[0],sig,
                f"Ribbon: {' '.join(f'E{p}={v:.4f}' for p,v in zip(s['periods'],vlist))}",vals)

        if name=="obv":
            val=ta.obv(c,v); v2=self._last(val); prev=self._prev(val)
            if v2 is None: return None
            return IndicatorResult(name,v2,"bullish" if v2>(prev or 0) else "bearish",f"OBV: {v2:.0f}")

        if name=="vwap":
            val=ta.vwap(h,l,c,v); v2=self._last(val); price=self._last(c)
            if v2 is None or price is None: return None
            sig="bullish" if price>v2 else "bearish"
            return IndicatorResult(name,v2,sig,f"VWAP: {v2:.5f} Price {'above' if sig=='bullish' else 'below'}")

        if name=="ad":
            val=ta.ad(h,l,c,v); v2=self._last(val); prev=self._prev(val)
            if v2 is None: return None
            return IndicatorResult(name,v2,"bullish" if v2>(prev or 0) else "bearish",f"A/D: {v2:.0f}")

        if name=="cmf":
            val=ta.cmf(h,l,c,v,length=s["period"]); v2=self._last(val)
            if v2 is None: return None
            return IndicatorResult(name,v2,"bullish" if v2>0 else "bearish",f"CMF({s['period']}): {v2:.3f}")

        if name=="atr":
            val=ta.atr(h,l,c,length=s["period"]); v2=self._last(val)
            if v2 is None: return None
            return IndicatorResult(name,v2,"neutral",f"ATR({s['period']}): {v2:.5f}")

        if name=="donchian":
            val=ta.donchian(h,l,length=s["period"])
            if val is None or val.empty: return None
            upper=self._last(val.iloc[:,2]); mid=self._last(val.iloc[:,1]); lower=self._last(val.iloc[:,0])
            price=self._last(c)
            if upper is None or price is None: return None
            sig="bullish" if price>mid else "bearish"
            return IndicatorResult(name,mid,sig,f"Donchian({s['period']}): U={upper:.5f} M={mid:.5f} L={lower:.5f}",
                {"upper":upper,"middle":mid,"lower":lower})

        if name=="aroon":
            val=ta.aroon(h,l,length=s["period"])
            if val is None or val.empty: return None
            up=self._last(val.iloc[:,0]); dn=self._last(val.iloc[:,1])
            if up is None: return None
            return IndicatorResult(name,up,"bullish" if up>dn else "bearish",
                f"Aroon({s['period']}): Up={up:.1f} Dn={dn:.1f}",{"up":up,"down":dn})

        if name=="pivot_points":
            last=candles[-1] if hasattr(self,"_candles_ref") else {}
            H=df["high"].iloc[-2] if len(df)>1 else df["high"].iloc[-1]
            L=df["low"].iloc[-2]  if len(df)>1 else df["low"].iloc[-1]
            C=df["close"].iloc[-2] if len(df)>1 else df["close"].iloc[-1]
            P=(H+L+C)/3; R1=2*P-L; R2=P+(H-L); S1=2*P-H; S2=P-(H-L)
            price=self._last(c)
            sig="bullish" if (price or 0)>P else "bearish"
            return IndicatorResult(name,float(P),sig,
                f"Pivot: P={P:.5f} R1={R1:.5f} S1={S1:.5f} R2={R2:.5f} S2={S2:.5f}",
                {"P":float(P),"R1":float(R1),"R2":float(R2),"S1":float(S1),"S2":float(S2)})

        if name=="ichimoku":
            try:
                ich=ta.ichimoku(h,l,c,tenkan=s["tenkan"],kijun=s["kijun"],senkou=s["senkou"])
                df2=ich[0] if isinstance(ich,tuple) else ich
                if df2 is None or df2.empty: return None
                tv=self._last(df2.iloc[:,0]); kv=self._last(df2.iloc[:,1]); price=self._last(c)
                if tv is None or price is None: return None
                sig="bullish" if tv>kv else "bearish"
                return IndicatorResult(name,tv,sig,
                    f"Ichimoku: Tenkan={tv:.5f} Kijun={kv:.5f}",{"tenkan":tv,"kijun":kv})
            except Exception: return None

        return None
