"""News via day-trader-skill's news.py: Yahoo headline RSS per ticker + SEC 8-K filings, tagged
(earnings/analyst/deal/...) and de-duplicated. SEC filings need SEC_USER_AGENT; headlines work without."""
import datetime as dt

from vendor.day_trader_skill import facts, news

TAG_IMPORTANT = {"earnings", "legal", "deal", "people", "risk", "halt", "regulatory"}


def to_rows(items, limit=40):
    rows = []
    for it in items[:limit]:
        t = it["time"]
        rows.append({
            "h": it["title"], "s": it["source"], "url": it["link"],
            "time": news.to_eastern(t).strftime("%b %d, %I:%M %p ET") if t else "",
            "ts": t.timestamp() if t else 0,
            "tickers": it.get("touches") or [it["ticker"]],
            "tags": it.get("tags", []),
            "important": bool(it.get("important")) or bool(set(it.get("tags", [])) & TAG_IMPORTANT),
        })
    return rows


def collect(watch: dict, ua=None, hours=96, limit=40):
    """watch: {ticker: company name}. -> (rows, errors)"""
    ua = facts.user_agent(ua)
    errors = []
    f = news.Fetcher(sec_ua=ua, pause=0.1)
    now = dt.datetime.now(dt.timezone.utc)
    items = news.collect(f, watch, {}, sec=bool(ua), forms=("8-K",), count=5, errors=errors)
    if not ua:
        errors.append("SEC_USER_AGENT not set: 8-K filings skipped")
    items = news.dedupe(news.tag(items, watch))
    items = news.select(items, {}, now, hours=hours, show_all=True)
    items.sort(key=lambda i: (bool(i.get("important")) or bool(set(i.get("tags", [])) & TAG_IMPORTANT),
                              i["time"].timestamp() if i["time"] else 0), reverse=True)
    return to_rows(items, limit), errors
