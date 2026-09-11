"""
Builds the stock universe: S&P 500 + Nasdaq 100, de-duplicated.

Pulled from Wikipedia's constituent tables. These pages change occasionally
(index reshuffles) so this is refreshed on every full run rather than hardcoded.
"""
import io

import pandas as pd
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}

SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
NASDAQ100_URL = "https://en.wikipedia.org/wiki/Nasdaq-100"


def _clean_ticker(t: str) -> str:
    # yfinance uses '-' where Wikipedia sometimes uses '.' (e.g. BRK.B -> BRK-B)
    return t.strip().replace(".", "-")


def get_sp500_tickers() -> list[str]:
    try:
        resp = requests.get(SP500_URL, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code} from Wikipedia (possibly rate-limited or blocked)")
        tables = pd.read_html(io.StringIO(resp.text))
        df = tables[0]
        col = "Symbol" if "Symbol" in df.columns else df.columns[0]
        return [_clean_ticker(t) for t in df[col].tolist()]
    except Exception as e:
        print(f"[universe] Failed to fetch S&P 500 list: {e}")
        return []


def get_nasdaq100_tickers() -> list[str]:
    try:
        resp = requests.get(NASDAQ100_URL, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code} from Wikipedia (possibly rate-limited or blocked)")
        tables = pd.read_html(io.StringIO(resp.text))
        # The constituents table on this page varies in index; find the one with a Ticker/Symbol column
        for df in tables:
            for col in ("Ticker", "Symbol"):
                if col in df.columns:
                    return [_clean_ticker(t) for t in df[col].tolist()]
        raise RuntimeError(f"Fetched page OK but found no table with a Ticker/Symbol column (out of {len(tables)} tables)")
    except Exception as e:
        print(f"[universe] Failed to fetch Nasdaq 100 list: {e}")
        return []


def build_universe() -> list[str]:
    sp500 = get_sp500_tickers()
    nasdaq100 = get_nasdaq100_tickers()
    combined = sorted(set(sp500) | set(nasdaq100))
    if not combined:
        # Fallback so the server still runs if Wikipedia scraping breaks
        print("[universe] WARNING: falling back to a small hardcoded sample universe.")
        combined = ["AAPL", "MSFT", "NVDA", "AMD", "GOOGL", "META", "AMZN", "TSLA",
                    "AVGO", "ORCL", "CRM", "ADBE", "QCOM", "TSM", "INTC", "PLTR",
                    "V", "JNJ", "COST", "PYPL", "SNAP"]
    return combined
