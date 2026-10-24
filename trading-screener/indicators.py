"""
Technical indicator + swing-structure helpers shared across screeners.
"""
import numpy as np
import pandas as pd


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window).mean()


def ema(series: pd.Series, window: int) -> pd.Series:
    return series.ewm(span=window, adjust=False).mean()


def rsi(series: pd.Series, window: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window).mean()
    avg_loss = loss.rolling(window).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def bollinger_band_width_pct(series: pd.Series, window: int = 20, num_std: float = 2.0) -> pd.Series:
    mid = series.rolling(window).mean()
    std = series.rolling(window).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    return ((upper - lower) / mid) * 100


def atr_pct(df: pd.DataFrame, window: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(window).mean()
    return (atr / close) * 100


def avg_dollar_volume(df: pd.DataFrame, window: int = 20) -> float:
    dollar_vol = df["close"] * df["volume"]
    return dollar_vol.rolling(window).mean().iloc[-1]


def relative_volume(df: pd.DataFrame, window: int = 20) -> float:
    avg_vol = df["volume"].rolling(window).mean().iloc[-2]  # avg excluding today
    today_vol = df["volume"].iloc[-1]
    if not avg_vol or np.isnan(avg_vol) or avg_vol == 0:
        return np.nan
    return today_vol / avg_vol


def find_swing_points(series: pd.Series, order: int = 3):
    """
    Simple local-extrema swing detector: a point is a swing high if it's the
    max within +/- `order` bars, a swing low if it's the min. Returns
    (list of (index_position, price) highs, list of (index_position, price) lows).
    """
    values = series.values
    highs, lows = [], []
    for i in range(order, len(values) - order):
        window = values[i - order: i + order + 1]
        if values[i] == window.max() and (window == values[i]).sum() == 1:
            highs.append((i, values[i]))
        if values[i] == window.min() and (window == values[i]).sum() == 1:
            lows.append((i, values[i]))
    return highs, lows


def trend_structure(series: pd.Series, order: int = 3, lookback_swings: int = 4) -> str:
    """
    Classifies recent swing structure as 'uptrend' (higher highs & higher lows),
    'downtrend' (lower highs & lower lows), or 'mixed'.
    """
    highs, lows = find_swing_points(series, order=order)
    if len(highs) < 2 or len(lows) < 2:
        return "mixed"
    recent_highs = [p for _, p in highs[-lookback_swings:]]
    recent_lows = [p for _, p in lows[-lookback_swings:]]
    hh = all(recent_highs[i] < recent_highs[i + 1] for i in range(len(recent_highs) - 1))
    hl = all(recent_lows[i] < recent_lows[i + 1] for i in range(len(recent_lows) - 1))
    lh = all(recent_highs[i] > recent_highs[i + 1] for i in range(len(recent_highs) - 1))
    ll = all(recent_lows[i] > recent_lows[i + 1] for i in range(len(recent_lows) - 1))
    if hh and hl:
        return "uptrend"
    if lh and ll:
        return "downtrend"
    return "mixed"


def fib_levels(swing_low: float, swing_high: float) -> dict:
    diff = swing_high - swing_low
    return {
        "23.6%": swing_high - 0.236 * diff,
        "38.2%": swing_high - 0.382 * diff,
        "50.0%": swing_high - 0.5 * diff,
        "61.8%": swing_high - 0.618 * diff,
    }


def closest_fib_zone(price: float, swing_low: float, swing_high: float, tolerance_pct: float = 4.0):
    """Returns the label of the fib level the price is currently closest to, if within tolerance_pct, else None."""
    levels = fib_levels(swing_low, swing_high)
    best_label, best_dist = None, None
    for label, level_price in levels.items():
        dist_pct = abs(price - level_price) / level_price * 100
        if best_dist is None or dist_pct < best_dist:
            best_label, best_dist = label, dist_pct
    if best_dist is not None and best_dist <= tolerance_pct:
        return best_label, best_dist
    return None, None


def wedge_regression(highs: list[tuple], lows: list[tuple]):
    """
    Fits a line through swing highs and through swing lows (index position vs price).
    Returns (slope_highs, slope_lows, converging_bool) or None if not enough points.
    'Converging' means the gap between the two lines is shrinking over time --
    the geometric signature of a wedge (as opposed to a parallel channel).
    """
    if len(highs) < 2 or len(lows) < 2:
        return None
    hx, hy = zip(*highs)
    lx, ly = zip(*lows)
    slope_h, intercept_h = np.polyfit(hx, hy, 1)
    slope_l, intercept_l = np.polyfit(lx, ly, 1)

    x_start = min(min(hx), min(lx))
    x_end = max(max(hx), max(lx))
    gap_start = (slope_h * x_start + intercept_h) - (slope_l * x_start + intercept_l)
    gap_end = (slope_h * x_end + intercept_h) - (slope_l * x_end + intercept_l)
    converging = gap_end < gap_start and gap_end > 0

    return {
        "slope_highs": slope_h,
        "slope_lows": slope_l,
        "upper_line_at_end": slope_h * x_end + intercept_h,
        "converging": converging,
    }
