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
BATCH_SIZE = 40          # tickers per yf.download() call
BATCH_PAUSE_SECONDS = 1.5  # brief pause between batches so we don't burst Yahoo (or a small cloud instance) with hundreds of concurrent requests at once


def fetch_price_history(tickers: list[str]) -> dict[str, pd.DataFrame]:
    """
    Bulk-download daily OHLCV for all tickers, in small batches rather than
    one giant concurrent request. On a resource-constrained host (e.g. a
    free-tier cloud instance), firing off requests for 500+ tickers at once
    via yfinance's internal thread pool tends to hang or get rate-limited;
    batching keeps peak concurrency low while still being reasonably fast.
    """
    out = {}
    total_batches = (len(tickers) + BATCH_SIZE - 1) // BATCH_SIZE
    print(f"[data] Downloading price history for {len(tickers)} tickers in {total_batches} batches of {BATCH_SIZE}...")

    for i in range(0, len(tickers), BATCH_SIZE):
        batch = tickers[i:i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        try:
            raw = yf.download(
                batch,
                period=PRICE_PERIOD,
                interval="1d",
                group_by="ticker",
                threads=True,
                auto_adjust=False,
                progress=False,
                timeout=20,
            )
            for t in batch:
                try:
                    df = raw[t].dropna(how="all") if len(batch) > 1 else raw.dropna(how="all")
                    if df.empty or len(df) < 60:
                        continue
                    df = df.rename(columns=str.lower)
                    out[t] = df
                except Exception:
                    continue
        except Exception as e:
            print(f"[data] Batch {batch_num}/{total_batches} failed entirely: {e}")

        print(f"[data] price history batch {batch_num}/{total_batches} done -- {len(out)} usable so far")
        if i + BATCH_SIZE < len(tickers):
            time.sleep(BATCH_PAUSE_SECONDS)

    print(f"[data] Got usable price history for {len(out)}/{len(tickers)} tickers.")
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
