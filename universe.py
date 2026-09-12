"""
Builds the stock universe: S&P 500 + Nasdaq 100, de-duplicated.

Uses a static, bundled snapshot (tickers_data.py) as the primary and only
required source. See that file's docstring for why this isn't scraped live
from Wikipedia -- short version: we tried, it broke in three different ways,
and index membership barely changes often enough to justify the fragility.
"""
from tickers_data import SP500_TICKERS, NASDAQ100_TICKERS


def _clean_ticker(t: str) -> str:
    # yfinance uses '-' where the source sometimes uses '.' (e.g. BRK.B -> BRK-B)
    return t.strip().replace(".", "-")


def build_universe() -> list[str]:
    combined = sorted({_clean_ticker(t) for t in SP500_TICKERS + NASDAQ100_TICKERS})
    print(f"[universe] Loaded {len(combined)} tickers from the static S&P 500 + Nasdaq 100 snapshot.")
    return combined
