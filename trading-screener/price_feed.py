"""
Price feed built on the day-trader-skill scanner module (vendor/day_trader_skill/scan.py).

Uses Yahoo's v8 *chart* endpoint, one symbol per request. Unlike yfinance's .info /
.history() calls, this endpoint needs no cookie or "crumb", which is what produced the
401 "User is unable to access this feature" errors on Render.

Fallback: if the skill's plain-urllib request is refused (some datacenter IPs get
403/429/401), the same URL is retried through a curl_cffi browser-impersonating session.
"""
import concurrent.futures
import json

import pandas as pd

from vendor.day_trader_skill import scan

try:
    from curl_cffi import requests as _cr
    _SESSION = _cr.Session(impersonate="chrome")
except Exception:  # pragma: no cover
    _SESSION = None

RANGE = "2y"          # 200-day MA + weekly wedge lookback
MAX_WORKERS = 4       # polite; Yahoo rate-limits bursts
MIN_BARS = 60
HEALTH = {"ok": 0, "failed": 0, "last_error": None}


def series_to_frame(series: dict):
    """scan.parse_chart output -> OHLCV DataFrame indexed by New York date, or None."""
    idx = pd.to_datetime(series["t"], unit="s", utc=True).tz_convert("America/New_York").tz_localize(None).normalize()
    df = pd.DataFrame({"open": series["o"], "high": series["h"], "low": series["l"],
                       "close": series["c"], "volume": series["v"]}, index=idx)
    df = df.dropna(subset=["close", "open", "high", "low"])
    df["volume"] = df["volume"].fillna(0)
    if len(df) and df["volume"].iloc[-1] == 0:   # Yahoo sometimes returns an empty latest bar
        df = df.iloc[:-1]
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df if len(df) >= MIN_BARS else None


def _get_text(path: str) -> str:
    try:
        return scan.yahoo_get(path)
    except Exception as first:
        if _SESSION is None:
            raise
        for host in scan.YAHOO_HOSTS:
            r = _SESSION.get(host + path, timeout=20)
            if r.status_code == 200:
                return r.text
        raise first


def fetch_one(sym: str):
    """-> (df or None, display name or None)"""
    try:
        text = _get_text(scan.chart_path(sym, RANGE, "1d"))
        series = scan.parse_chart(text, sym)
        meta = series.get("meta") or {}
        return series_to_frame(series), (meta.get("longName") or meta.get("shortName"))
    except Exception as e:
        HEALTH["last_error"] = f"{sym}: {e}"
        return None, None


def fetch_price_history(tickers):
    """-> (dict ticker -> DataFrame, dict ticker -> name)"""
    HEALTH.update(ok=0, failed=0)
    frames, names = {}, {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        for t, (df, name) in zip(tickers, pool.map(fetch_one, tickers)):
            if df is None:
                HEALTH["failed"] += 1
                continue
            HEALTH["ok"] += 1
            frames[t] = df
            if name:
                names[t] = name
            if HEALTH["ok"] % 50 == 0:
                print(f"[price] {HEALTH['ok']} ok / {HEALTH['failed']} failed")
    print(f"[price] done: {HEALTH['ok']} ok, {HEALTH['failed']} failed. last error: {HEALTH['last_error']}")
    return frames, names
