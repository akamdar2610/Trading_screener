"""Swing-trade plan (stop / target / R) using day-trader-skill's exit.compute for exact-cent, validated math.

Stop = 'recent swing low minus 0.5 ATR' (rounded down by exit.py); target = 2R above entry.
This is a starting point for your own analysis, not advice. Long-side only."""
from decimal import Decimal

import pandas as pd

from vendor.day_trader_skill import exit as exit_mod


def _atr(df, n=14):
    pc = df["close"].shift()
    tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)
    return float(tr.rolling(n).mean().iloc[-1])


def plan_for(df, target_r=2, swing_days=10):
    """-> {'stop','target','risk_pct','r'} or None if exit.py refuses the plan."""
    try:
        entry = float(df["close"].iloc[-1])
        stop_raw = float(df["low"].iloc[-swing_days:].min()) - 0.5 * _atr(df)
        p = exit_mod.compute(Decimal(str(round(entry, 2))), "price", Decimal(str(round(stop_raw, 2))),
                             "r", Decimal(str(target_r)))
        return {"stop": float(p["stop"]), "target": float(p["target"]),
                "risk_pct": round(float(p["risk"]) / entry * 100, 1), "r": float(p["target_r"])}
    except Exception:
        return None


def add_plans(rows, price_data):
    for r in rows:
        df = price_data.get(r["t"])
        r["plan"] = plan_for(df) if df is not None else None
    return rows
