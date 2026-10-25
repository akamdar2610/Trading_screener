"""
Read-only IBKR portfolio via the Flex Web Service (no trading, no login session).

Setup (once, in IBKR Client Portal -> Performance & Reports -> Flex Queries):
  1. Create an Activity Flex Query with sections: Account Information, Open Positions (all fields), Cash Report.
     Format = XML. Save it and note its Query ID.
  2. Flex Web Service Configuration: generate a token (read-only).
  3. In Render set IBKR_FLEX_TOKEN, IBKR_FLEX_QUERY_ID and PORTFOLIO_PASSWORD.
Flex data is the last completed daily report (not real-time); prices are refreshed from Yahoo separately.
Rate limit: 1 req/s, 10/min per token -- we fetch at most a few times a day.
"""
import os
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

BASE = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/SendRequest"
UA = "trading-screener/2.0 (personal portfolio viewer)"
YAHOO_EXCH_SUFFIX = {"TSE": ".TO", "VENTURE": ".V", "LSE": ".L"}
STATUS = {"configured": False, "last_fetch": None, "last_error": None}


class FlexError(Exception):
    pass


def configured() -> bool:
    return bool(os.environ.get("IBKR_FLEX_TOKEN") and os.environ.get("IBKR_FLEX_QUERY_ID"))


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def fetch_statement_xml(token=None, query_id=None, tries=8, wait=5) -> str:
    token = token or os.environ.get("IBKR_FLEX_TOKEN")
    query_id = query_id or os.environ.get("IBKR_FLEX_QUERY_ID")
    if not token or not query_id:
        raise FlexError("IBKR_FLEX_TOKEN / IBKR_FLEX_QUERY_ID not set")
    root = ET.fromstring(_get(f"{BASE}?{urllib.parse.urlencode({'t': token, 'q': query_id, 'v': 3})}"))
    if (root.findtext("Status") or "").lower() != "success":
        raise FlexError(f"SendRequest failed: {root.findtext('ErrorCode')} {root.findtext('ErrorMessage')}")
    ref, url = root.findtext("ReferenceCode"), root.findtext("url")
    for _ in range(tries):
        time.sleep(wait)
        text = _get(f"{url}?{urllib.parse.urlencode({'t': token, 'q': ref, 'v': 3})}")
        if "<FlexQueryResponse" in text:
            return text
        r = ET.fromstring(text)
        code = r.findtext("ErrorCode")
        if code and code != "1019":  # 1019 = statement generation in progress
            raise FlexError(f"GetStatement failed: {code} {r.findtext('ErrorMessage')}")
    raise FlexError("Statement still generating; try again shortly")


def _f(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def yahoo_symbol(sym: str, exchange: str = "") -> str:
    return sym.replace(" ", "-").replace(".", "-") + YAHOO_EXCH_SUFFIX.get((exchange or "").upper(), "")


def parse_statement(xml_text: str) -> dict:
    """Flex XML -> {'base','accounts','positions','cash','as_of'}. Values converted to base currency via fxRateToBase."""
    root = ET.fromstring(xml_text)
    positions, cash, base, accounts, as_of = [], 0.0, None, [], None
    for st in root.iter("FlexStatement"):
        accounts.append(st.get("accountId"))
        info = st.find("AccountInformation")
        if info is not None and info.get("currency"):
            base = info.get("currency")
        as_of = st.get("toDate") or as_of
        for p in st.iter("OpenPosition"):
            if p.get("levelOfDetail") not in (None, "", "SUMMARY"):
                continue  # skip lot-level rows if the query included them
            fx = _f(p.get("fxRateToBase"), 1.0) or 1.0
            qty = _f(p.get("position"))
            value = _f(p.get("positionValue"))
            cost = _f(p.get("costBasisMoney"))
            upl = _f(p.get("fifoPnlUnrealized"), value - cost)
            sym = p.get("symbol") or ""
            positions.append({
                "symbol": sym, "yahoo": yahoo_symbol(sym, p.get("listingExchange")),
                "name": p.get("description") or sym, "type": p.get("assetCategory") or "",
                "currency": p.get("currency") or base, "qty": qty,
                "avg_cost": round(cost / qty / (_f(p.get("multiplier"), 1) or 1), 4) if qty else None,
                "mark": _f(p.get("markPrice")), "value": value * fx, "cost": cost * fx, "pnl": upl * fx,
                "fx": fx, "account": st.get("accountId"),
            })
        summary = None
        for c in st.iter("CashReportCurrency"):
            if c.get("currency") == "BASE_SUMMARY":
                summary = _f(c.get("endingCash"))
        if summary is None:
            summary = sum(_f(c.get("endingCash")) * (_f(c.get("fxRateToBase"), 1.0) or 1.0)
                          for c in st.iter("CashReportCurrency") if c.get("currency") != "BASE_SUMMARY")
        cash += summary
    return {"base": base or "", "accounts": accounts, "positions": positions, "cash": cash, "as_of": as_of}


def summarize(parsed: dict, live_prices: dict = None) -> dict:
    """Apply live prices (ticker -> last close, in the position's own currency) and compute totals/weights."""
    live_prices = live_prices or {}
    pos = []
    for p in parsed["positions"]:
        q = dict(p)
        lp = live_prices.get(p["yahoo"])
        if lp and p["qty"] and p["type"] == "STK":
            q["last"] = lp
            q["value"] = p["qty"] * lp * p["fx"]
            q["pnl"] = q["value"] - p["cost"]
        else:
            q["last"] = p["mark"]
        pos.append(q)
    invested = sum(p["value"] for p in pos)
    total = invested + parsed["cash"]
    for p in pos:
        p["weight"] = round(p["value"] / total * 100, 1) if total else 0
        p["pnl_pct"] = round(p["pnl"] / p["cost"] * 100, 1) if p["cost"] else None
        for k in ("value", "cost", "pnl"):
            p[k] = round(p[k], 2)
    pos.sort(key=lambda p: p["value"], reverse=True)
    pnl = sum(p["pnl"] for p in pos)
    cost = sum(p["cost"] for p in pos)
    return {"base": parsed["base"], "as_of": parsed["as_of"], "total": round(total, 2), "invested": round(invested, 2),
            "cash": round(parsed["cash"], 2), "cash_pct": round(parsed["cash"] / total * 100, 1) if total else 0,
            "unrealized_pnl": round(pnl, 2), "unrealized_pct": round(pnl / cost * 100, 1) if cost else None,
            "positions": pos}
