"""
Fundamentals + earnings info from SEC EDGAR, via day-trader-skill's facts.py (Fetcher, ticker_ciks,
analyse). Free, official, no cookie/crumb, and not blocked on cloud hosts -- but SEC REQUIRES a
User-Agent containing your name and email: set SEC_USER_AGENT="Your Name you@example.com" on Render.

Output per ticker matches the keys screeners.py already uses (marketCap is filled in later, once a
price is known, by finalize_market_cap()).

Approximations (be aware): PEG is not computed (left None -> that filter is skipped); EPS growth is a
CAGR over the available annual diluted-EPS values (up to 5 years back); ROE = latest annual net income /
year-end equity; debt = long-term debt incl. current portion. Companies reporting under IFRS/20-F (most
ADRs) have no us-gaap facts and simply drop out of the Invest screen.
"""
import datetime as dt
import os

from vendor.day_trader_skill import facts

NAME_OVERRIDE_TECH = {  # fallback if SEC returns no SIC code
    "AAPL", "MSFT", "NVDA", "AVGO", "AMD", "INTC", "QCOM", "TXN", "MU", "AMAT", "LRCX", "KLAC", "ADI", "MRVL",
    "ORCL", "CRM", "ADBE", "NOW", "INTU", "PANW", "CRWD", "SNPS", "CDNS", "ANET", "CSCO", "IBM", "PLTR", "WDAY",
    "FTNT", "ADSK", "DELL", "HPQ", "HPE", "NXPI", "MCHP", "ON", "MPWR", "SMCI", "TEAM", "DDOG", "ZS",
}
STATUS = {"ok": 0, "failed": 0, "ua_ok": False, "last_error": None}


def sector_from_sic(sic, ticker=None):
    """-> (sector, industry). 'Technology' covers electronic tech + tech services (+ semis, software)."""
    try:
        s = int(sic)
    except (TypeError, ValueError):
        return ("Technology", "Electronic Technology") if ticker in NAME_OVERRIDE_TECH else ("Unknown", "Unknown")
    if 6000 <= s <= 6799:
        return "Financial Services", "Financials"
    if 3570 <= s <= 3579 or 3600 <= s <= 3699 or s in (3810, 3820, 3825, 3826, 3829, 3844, 3845):
        return "Technology", "Electronic Technology"
    if 7370 <= s <= 7379 or s in (7200, 7389, 4813):
        return "Technology", "Technology Services"
    return "Other", "Other"


def _latest_instant(fl, concept, unit_hint=None):
    """Most recent balance-sheet (no 'start') value: (value, end) from 10-K/10-Q facts."""
    best = None
    for f in facts.facts_for(fl, concept, unit_hint):
        if "start" in f or f.get("form", "").split("/")[0] not in ("10-K", "10-Q"):
            continue
        key = (f["end"], f.get("filed", ""))
        if best is None or key > best[0]:
            best = (key, f["val"], f["end"])
    return (best[1], best[2]) if best else (None, None)


def _annual(fl, concept, unit_hint=None):
    """{end: value} for ~12-month 10-K duration facts (latest filing wins)."""
    out = {}
    for f in facts.facts_for(fl, concept, unit_hint):
        if "start" not in f or f.get("form", "").split("/")[0] != "10-K":
            continue
        days = (dt.date.fromisoformat(f["end"]) - dt.date.fromisoformat(f["start"])).days
        if not 340 <= days <= 380:
            continue
        if f["end"] not in out or f.get("filed", "") >= out[f["end"]][1]:
            out[f["end"]] = (f["val"], f.get("filed", ""))
    return {e: v[0] for e, v in out.items()}


def _first(fl, concepts, unit_hint=None, fn=_annual):
    for c in concepts:
        r = fn(fl, c, unit_hint)
        if r and (r if isinstance(r, dict) else r[0] is not None):
            return r
    return {} if fn is _annual else (None, None)


def fundamentals_from_facts(fl: dict, sic=None, ticker=None) -> dict:
    """Pure function: companyfacts JSON (+ SIC) -> the fundamentals dict used by screeners.py."""
    eps = _first(fl, ["EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted"], "USD/shares")
    ends = sorted(eps)[-6:]  # up to 5 yearly intervals
    eps_vals = [eps[e] for e in ends]
    growth = positive = None
    if len(eps_vals) >= 2:
        positive = all(v > 0 for v in eps_vals)
        if eps_vals[0] > 0 and eps_vals[-1] > 0:
            growth = round(((eps_vals[-1] / eps_vals[0]) ** (1 / (len(eps_vals) - 1)) - 1) * 100, 1)
    ni = _first(fl, ["NetIncomeLoss", "ProfitLoss"], "USD")
    equity, eq_end = _latest_instant(fl, "StockholdersEquity", "USD")
    ni_latest = ni.get(max(ni)) if ni else None
    roe = (ni_latest / equity) if (ni_latest is not None and equity and equity > 0) else None
    ca, _ = _latest_instant(fl, "AssetsCurrent", "USD")
    cl, _ = _latest_instant(fl, "LiabilitiesCurrent", "USD")
    cur = round(ca / cl, 2) if ca and cl else None
    lt, _ = _latest_instant(fl, "LongTermDebtNoncurrent", "USD")
    cd, _ = _latest_instant(fl, "LongTermDebtCurrent", "USD")
    if lt is None and cd is None:
        lt, _ = _latest_instant(fl, "LongTermDebt", "USD")
    debt = (lt or 0) + (cd or 0) if (lt is not None or cd is not None) else None
    de = round(debt / equity * 100, 1) if (debt is not None and equity and equity > 0) else (0.0 if (equity and equity > 0 and debt is None) else None)
    shares = None
    for f in fl.get("facts", {}).get("dei", {}).get("EntityCommonStockSharesOutstanding", {}).get("units", {}).get("shares", []):
        if shares is None or f["end"] >= shares[0]:
            shares = (f["end"], f["val"])
    dps = _first(fl, ["CommonStockDividendsPerShareDeclared", "CommonStockDividendsPerShareCashPaid"], "USD/shares")
    dps_latest = dps.get(max(dps)) if dps else None
    sector, industry = sector_from_sic(sic, ticker)
    return {
        "sector": sector, "industry": industry, "isFinancial": sector == "Financial Services",
        "shares": shares[1] if shares else None, "marketCap": 0,
        "roe": roe, "currentRatio": cur, "debtToEquity": de, "pegRatio": None,
        "epsGrowth5y": growth, "epsPositiveAllYears": positive, "divPerShare": dps_latest,
    }


def earnings_info(fl: dict) -> dict:
    """Last reported quarter + ESTIMATED next report (typically last report + ~91 days). Not a confirmed date."""
    try:
        res = facts.analyse(fl, quarters=1)
        row = res["rows"][0]
    except Exception:
        return {}
    next_est = None
    try:
        filed = dt.date.fromisoformat(row["filed"])
        next_est = filed + dt.timedelta(days=91)
    except Exception:
        pass
    return {"lastEps": row.get("eps_diluted"), "lastEpsYoy": row.get("eps_yoy"), "lastQuarterEnd": row.get("end"),
            "lastFiled": row.get("filed"), "nextEst": next_est.isoformat() if next_est else None}


def fetch_all(tickers, ua=None, pause=0.12):
    """-> (fundamentals dict, earnings dict). Returns ({}, {}) with STATUS['last_error'] set if no valid UA."""
    ua = facts.user_agent(ua)
    STATUS.update(ok=0, failed=0, ua_ok=bool(ua), last_error=None)
    if not ua:
        STATUS["last_error"] = "SEC_USER_AGENT not set (needs 'Your Name you@example.com')"
        print("[edgar] " + STATUS["last_error"])
        return {}, {}
    fx = facts.Fetcher(ua, pause=pause)
    try:
        ciks = facts.ticker_ciks(fx)
    except Exception as e:
        STATUS["last_error"] = f"ticker list: {e}"
        print("[edgar] " + STATUS["last_error"])
        return {}, {}
    fund, earn = {}, {}
    for i, t in enumerate(tickers):
        key = t.replace("-", ".")
        if key not in ciks:
            STATUS["failed"] += 1
            continue
        cik = ciks[key][0]
        try:
            fl = fx.json(facts.FACTS_URL % cik, f"companyfacts-CIK{cik}.json")
            try:
                sic = fx.json(facts.SUBMISSIONS_URL % cik, f"submissions-CIK{cik}.json").get("sic")
            except Exception:
                sic = None
            fund[t] = fundamentals_from_facts(fl, sic, t)
            fund[t]["longName"] = ciks[key][1]
            earn[t] = earnings_info(fl)
            STATUS["ok"] += 1
        except Exception as e:
            STATUS["failed"] += 1
            STATUS["last_error"] = f"{t}: {e}"
        if (i + 1) % 50 == 0:
            print(f"[edgar] {i + 1}/{len(tickers)} (ok {STATUS['ok']}, failed {STATUS['failed']})")
    print(f"[edgar] done: {STATUS['ok']} ok, {STATUS['failed']} not available (ADRs/no XBRL are expected)")
    return fund, earn


def finalize_market_cap(fund: dict, price_data: dict):
    """marketCap = SEC shares outstanding x latest close (approximation: ignores multi-class share counts)."""
    for t, f in fund.items():
        df = price_data.get(t)
        if df is not None and f.get("shares"):
            f["marketCap"] = float(f["shares"]) * float(df["close"].iloc[-1])
