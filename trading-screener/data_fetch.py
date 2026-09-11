"""
Data access layer. Two speeds of data on purpose:

- Price/volume history: cheap-ish to pull in bulk, refreshed every scan (hourly).
- Fundamentals (market cap, ROE, EPS history, etc.): slow to pull one ticker at a
  time via yfinance, and don't change intraday, so refreshed once a day.
"""
import time
import pandas as pd
import yfinance as yf

PRICE_PERIOD = "18mo"  # enough history for 200-day MA + weekly wedge lookback


def fetch_price_history(tickers: list[str]) -> dict[str, pd.DataFrame]:
    """Bulk-download daily OHLCV for all tickers. Returns {ticker: DataFrame}."""
    print(f"[data] Downloading price history for {len(tickers)} tickers...")
    raw = yf.download(
        tickers,
        period=PRICE_PERIOD,
        interval="1d",
        group_by="ticker",
        threads=True,
        auto_adjust=False,
        progress=False,
    )

    out = {}
    for t in tickers:
        try:
            df = raw[t].dropna(how="all")
            if df.empty or len(df) < 60:
                continue
            df = df.rename(columns=str.lower)
            out[t] = df
        except Exception:
            continue
    print(f"[data] Got usable price history for {len(out)} tickers.")
    return out


def _safe_get(info: dict, key: str, default=None):
    v = info.get(key, default)
    return v if v is not None else default


def fetch_fundamentals(tickers: list[str], sleep_between: float = 0.05) -> dict[str, dict]:
    """
    Per-ticker fundamentals via yfinance .info and .income_stmt.
    This is the slow part (one HTTP call per ticker) -- intended to run
    once a day, not on every hourly scan. A small sleep avoids hammering
    Yahoo's endpoint hard enough to get rate-limited.
    """
    print(f"[data] Fetching fundamentals for {len(tickers)} tickers (this takes a while)...")
    out = {}
    for i, t in enumerate(tickers):
        try:
            tk = yf.Ticker(t)
            info = tk.info or {}

            eps_growth_5y, eps_positive_all_years = _eps_growth_from_statements(tk)

            out[t] = {
                "sector": _safe_get(info, "sector", "Unknown"),
                "industry": _safe_get(info, "industry", "Unknown"),
                "marketCap": _safe_get(info, "marketCap", 0),
                "roe": _safe_get(info, "returnOnEquity", None),
                "currentRatio": _safe_get(info, "currentRatio", None),
                "debtToEquity": _safe_get(info, "debtToEquity", None),
                "trailingPE": _safe_get(info, "trailingPE", None),
                "pegRatio": _safe_get(info, "pegRatio") or _safe_get(info, "trailingPegRatio", None),
                "epsGrowth5y": eps_growth_5y,
                "epsPositiveAllYears": eps_positive_all_years,
                "isFinancial": _safe_get(info, "sector", "") == "Financial Services",
            }
        except Exception as e:
            print(f"[data] fundamentals failed for {t}: {e}")
        if sleep_between:
            time.sleep(sleep_between)
        if (i + 1) % 50 == 0:
            print(f"[data] fundamentals progress: {i + 1}/{len(tickers)}")
    return out


def _eps_growth_from_statements(tk: yf.Ticker):
    """
    Best-effort annual EPS growth from yfinance's income statement.
    Free Yahoo data typically exposes ~4 years of annual financials, not 5 --
    this uses whatever is available and is a good-enough proxy, not exact.
    Returns (cagr_percent_or_None, all_years_positive_bool_or_None).
    """
    try:
        stmt = tk.income_stmt
        if stmt is None or stmt.empty or "Diluted EPS" not in stmt.index:
            return None, None
        eps_row = stmt.loc["Diluted EPS"].dropna()
        eps_row = eps_row.sort_index()  # oldest -> newest
        values = eps_row.tolist()
        if len(values) < 2:
            return None, None
        first, last = values[0], values[-1]
        years = len(values) - 1
        all_positive = all(v > 0 for v in values)
        if first <= 0:
            return None, all_positive  # can't compute a clean CAGR off a non-positive base
        cagr = ((last / first) ** (1 / years) - 1) * 100
        return round(cagr, 1), all_positive
    except Exception:
        return None, None
