"""
Implements the four screener categories exactly as specified:

1. Invest        - fundamentals-first, long-term
2. Breakout      - Confirmed / Pre-breakout watchlist
3. Bounce play   - early recovery setups
4. Strategy      - Uptrend pullback (Fib) / Weekly wedge reversal (approximate)

Each screen_* function returns a list of row dicts ready to serve as JSON.

NOTE on sectors: free Yahoo data classifies companies with GICS-style sectors
("Technology", "Communication Services", etc.), not the "Electronic
Technology" / "Technology Services" taxonomy. We treat sector == "Technology"
as the closest available proxy for both of those. Good enough for a
screener; treat sector as a directional filter, not gospel.
"""
import pandas as pd
from indicators import (
    sma, ema, rsi, bollinger_band_width_pct, avg_dollar_volume, relative_volume,
    trend_structure, find_swing_points, closest_fib_zone, wedge_regression,
)

MIN_LIQUIDITY_DOLLAR_VOL = 5_000_000       # breakout screeners
BOUNCE_MIN_SHARE_VOL = 400_000
BOUNCE_MIN_DOLLAR_VOL = 200_000_000
STRATEGY_MIN_DOLLAR_VOL = 200_000_000
STRATEGY_MIN_MARKET_CAP = 10_000_000_000
INVEST_MIN_MARKET_CAP = 2_000_000_000


def _name(t, fundamentals):
    f = fundamentals.get(t, {})
    return f.get("longName") or t


def _base_fields(t, df, fundamentals):
    close = df["close"]
    prev_close = close.iloc[-2] if len(close) > 1 else close.iloc[-1]
    chg = (close.iloc[-1] / prev_close - 1) * 100 if prev_close else 0
    return {
        "t": t,
        "n": _name(t, fundamentals),
        "px": round(float(close.iloc[-1]), 2),
        "chg": round(float(chg), 2),
        "o": round(float(df["open"].iloc[-1]), 2),
        "h": round(float(df["high"].iloc[-1]), 2),
        "l": round(float(df["low"].iloc[-1]), 2),
        "vol": int(df["volume"].iloc[-1]),
    }


# ---------------------------------------------------------------- INVEST ---
def screen_invest(price_data: dict, fundamentals: dict) -> list[dict]:
    rows = []
    for t, f in fundamentals.items():
        df = price_data.get(t)
        if df is None or len(df) < 210:
            continue
        try:
            close = df["close"]
            ma200 = sma(close, 200).iloc[-1]
            if pd.isna(ma200) or close.iloc[-1] <= ma200:
                continue
            if (f.get("marketCap") or 0) < INVEST_MIN_MARKET_CAP:
                continue
            roe = f.get("roe")
            if roe is None or roe * 100 < 15:
                continue
            de = f.get("debtToEquity")
            if de is not None and (de / 100) > 1.5:
                continue
            eps_growth = f.get("epsGrowth5y")
            if eps_growth is None or eps_growth < 10:
                continue
            if f.get("epsPositiveAllYears") is False:
                continue
            if not f.get("isFinancial"):
                cr = f.get("currentRatio")
                if cr is None or cr < 1.5:
                    continue
            peg = f.get("pegRatio")
            if peg is not None and peg > 2:
                continue

            row = _base_fields(t, df, fundamentals)
            row.update({
                "cap": round((f.get("marketCap") or 0) / 1e9, 1),
                "eps5": eps_growth,
                "roe": round(roe * 100, 1),
                "cr": round(f.get("currentRatio") or 0, 2),
                "peg": round(peg, 2) if peg else None,
            })
            rows.append(row)
        except Exception:
            continue
    return sorted(rows, key=lambda r: r["cap"], reverse=True)


# -------------------------------------------------------------- BREAKOUT ---
def screen_breakout_confirmed(price_data: dict, fundamentals: dict, spy_df: pd.DataFrame) -> list[dict]:
    rows = []
    spy_3mo = _pct_change_n(spy_df, 63) if spy_df is not None else None

    for t, df in price_data.items():
        if len(df) < 210:
            continue
        try:
            close = df["close"]
            last = close.iloc[-1]
            prior_20_high = close.iloc[-21:-1].max()
            if last <= prior_20_high:
                continue
            breakout_level = prior_20_high
            pct_above = (last - breakout_level) / breakout_level * 100
            if not (0 <= pct_above <= 5):
                continue

            avg_vol20 = df["volume"].iloc[-21:-1].mean()
            if avg_vol20 == 0 or df["volume"].iloc[-1] < 1.5 * avg_vol20:
                continue

            ma50, ma150 = sma(close, 50).iloc[-1], sma(close, 150).iloc[-1]
            if pd.isna(ma50) or pd.isna(ma150) or not (last > ma50 > ma150):
                continue

            r = rsi(close, 14).iloc[-1]
            if pd.isna(r) or not (50 <= r <= 70):
                continue

            dollar_vol = avg_dollar_volume(df)
            if pd.isna(dollar_vol) or dollar_vol < MIN_LIQUIDITY_DOLLAR_VOL:
                continue

            stock_3mo = _pct_change_n(df, 63)
            if spy_3mo is not None and stock_3mo is not None and stock_3mo <= spy_3mo:
                continue

            rvol = relative_volume(df)
            row = _base_fields(t, df, fundamentals)
            row.update({
                "rvol": round(float(rvol), 2) if not pd.isna(rvol) else None,
                "rsi": round(float(r), 1),
                "days": int((close.iloc[-21:] > prior_20_high).sum()),
            })
            rows.append(row)
        except Exception:
            continue
    return sorted(rows, key=lambda r: r["chg"], reverse=True)


def screen_breakout_pre(price_data: dict, fundamentals: dict) -> list[dict]:
    rows = []
    for t, df in price_data.items():
        if len(df) < 150:
            continue
        try:
            close = df["close"]
            last = close.iloc[-1]

            ma50 = sma(close, 50).iloc[-1]
            if pd.isna(ma50) or last <= ma50:
                continue

            bb_width = bollinger_band_width_pct(close, 20)
            current_bb = bb_width.iloc[-1]
            six_month_min = bb_width.iloc[-126:].min()
            if pd.isna(current_bb) or current_bb > six_month_min * 1.1:
                continue  # not near a volatility-contraction low

            high_20 = close.iloc[-20:].max()
            within_base = (close.iloc[-5:] >= high_20 * 0.90) & (close.iloc[-5:] <= high_20 * 1.0)
            if not within_base.all():
                continue

            avg_vol20 = df["volume"].iloc[-20:].mean()
            if df["volume"].iloc[-5:].mean() >= avg_vol20:
                continue  # want volume drying up, not picking up yet

            resistance = close.iloc[-60:].max()
            dist_to_resistance = (resistance - last) / resistance * 100
            if not (0 <= dist_to_resistance <= 3):
                continue

            dollar_vol = avg_dollar_volume(df)
            if pd.isna(dollar_vol) or dollar_vol < MIN_LIQUIDITY_DOLLAR_VOL:
                continue

            days_in_base = int(within_base.sum())
            row = _base_fields(t, df, fundamentals)
            row.update({
                "bb": round(float(current_bb), 2),
                "base": days_in_base,
            })
            rows.append(row)
        except Exception:
            continue
    return sorted(rows, key=lambda r: r["bb"])


# ---------------------------------------------------------------- BOUNCE ---
def screen_bounce(price_data: dict, fundamentals: dict) -> list[dict]:
    rows = []
    for t, df in price_data.items():
        if len(df) < 60:
            continue
        try:
            close = df["close"]
            last = close.iloc[-1]

            ma20 = sma(close, 20).iloc[-1]
            ema50 = ema(close, 50).iloc[-1]
            if pd.isna(ma20) or pd.isna(ema50):
                continue
            if not (last > ma20 and last < ema50):
                continue

            swing_low = df["low"].iloc[-10:].min()
            proximity = (last - swing_low) / swing_low * 100
            if not (0 <= proximity <= 5):
                continue

            avg_share_vol = df["volume"].iloc[-20:].mean()
            if avg_share_vol < BOUNCE_MIN_SHARE_VOL:
                continue

            dollar_vol = avg_dollar_volume(df)
            if pd.isna(dollar_vol) or dollar_vol < BOUNCE_MIN_DOLLAR_VOL:
                continue

            rvol = relative_volume(df)
            if pd.isna(rvol) or rvol <= 1:
                continue

            row = _base_fields(t, df, fundamentals)
            row.update({
                "dvol": round(dollar_vol / 1e6, 1),
                "rvol": round(float(rvol), 2),
                "swing": round(float(proximity), 2),
            })
            rows.append(row)
        except Exception:
            continue
    return sorted(rows, key=lambda r: r["rvol"], reverse=True)


# -------------------------------------------------------------- STRATEGY ---
def screen_strategy_pullback(price_data: dict, fundamentals: dict) -> list[dict]:
    rows = []
    for t, f in fundamentals.items():
        df = price_data.get(t)
        if df is None or len(df) < 210:
            continue
        try:
            if (f.get("marketCap") or 0) < STRATEGY_MIN_MARKET_CAP:
                continue
            if f.get("sector") != "Technology":
                continue

            close = df["close"]
            last = close.iloc[-1]
            ma200 = sma(close, 200).iloc[-1]
            if pd.isna(ma200) or last <= ma200:
                continue

            if trend_structure(close.iloc[-120:], order=3, lookback_swings=4) != "uptrend":
                continue

            highs, lows = find_swing_points(close.iloc[-120:], order=3)
            if not highs or not lows:
                continue
            last_high_idx, last_high_px = highs[-1]
            preceding_lows = [l for l in lows if l[0] < last_high_idx]
            if not preceding_lows:
                continue
            swing_low_px = preceding_lows[-1][1]

            fib_label, fib_dist = closest_fib_zone(last, swing_low_px, last_high_px, tolerance_pct=4.0)
            if fib_label is None:
                continue

            dollar_vol = avg_dollar_volume(df)
            if pd.isna(dollar_vol) or dollar_vol < STRATEGY_MIN_DOLLAR_VOL:
                continue

            sup_dist = abs(last - swing_low_px) / swing_low_px * 100

            row = _base_fields(t, df, fundamentals)
            row.update({
                "sector": "Technology Services" if "Services" in (f.get("industry") or "") else "Electronic Technology",
                "fib": fib_label,
                "sup": round(float(sup_dist), 2),
            })
            rows.append(row)
        except Exception:
            continue
    return sorted(rows, key=lambda r: r["sup"])


def screen_strategy_wedge(price_data: dict, fundamentals: dict) -> list[dict]:
    rows = []
    for t, f in fundamentals.items():
        df = price_data.get(t)
        if df is None or len(df) < 260:
            continue
        try:
            if (f.get("marketCap") or 0) < STRATEGY_MIN_MARKET_CAP:
                continue
            if f.get("sector") != "Technology":
                continue

            weekly = df.resample("W").agg({
                "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum",
            }).dropna()
            if len(weekly) < 20:
                continue

            recent = weekly.iloc[-20:]
            prior_trend = trend_structure(recent["close"], order=2, lookback_swings=3)
            if prior_trend != "downtrend":
                continue

            highs, lows = find_swing_points(recent["close"], order=2)
            wedge = wedge_regression(highs, lows)
            if wedge is None or not wedge["converging"] or wedge["slope_highs"] >= 0 or wedge["slope_lows"] >= 0:
                continue

            last_close = recent["close"].iloc[-1]
            upper_line = wedge["upper_line_at_end"]
            dollar_vol = avg_dollar_volume(df)
            if pd.isna(dollar_vol) or dollar_vol < STRATEGY_MIN_DOLLAR_VOL:
                continue

            if last_close > upper_line:
                last_vol = recent["volume"].iloc[-1]
                avg_vol = recent["volume"].mean()
                status = "Broke above, volume confirming" if last_vol > avg_vol else "Broke above, low volume"
            elif last_close > upper_line * 0.98:
                status = "Testing upper trendline"
            else:
                continue  # not close enough to the trigger to be actionable yet

            row = _base_fields(t, df, fundamentals)
            row.update({
                "sector": "Technology Services" if "Services" in (f.get("industry") or "") else "Electronic Technology",
                "weeks": len(recent),
                "status": status,
            })
            rows.append(row)
        except Exception:
            continue
    return rows


def _pct_change_n(df: pd.DataFrame, n: int):
    close = df["close"] if "close" in df.columns else df
    if len(close) <= n:
        return None
    return (close.iloc[-1] / close.iloc[-n - 1] - 1) * 100
