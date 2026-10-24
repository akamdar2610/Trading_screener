"""NYSE-aware market status via day-trader-skill's alerts.market_status (holidays + early closes for 2026-2027)."""
import datetime

from vendor.day_trader_skill import alerts


def status(now_utc=None) -> dict:
    now = now_utc or datetime.datetime.now(datetime.timezone.utc)
    return alerts.market_status(now)


def is_open(now_utc=None) -> bool:
    return bool(status(now_utc)["open"])
