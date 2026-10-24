"""
Trading Screener backend.

Run with:  uvicorn main:app --reload --port 8000

Data sources (all via the MIT-licensed day-trader-skill modules vendored in vendor/day_trader_skill):
  prices        Yahoo v8 chart endpoint (no cookie/crumb)      -> price_feed.py
  fundamentals  SEC EDGAR XBRL company facts (needs SEC_USER_AGENT) -> edgar_feed.py
  news          Yahoo headline RSS + SEC 8-K filings           -> news_feed.py
  market clock  NYSE holidays / early closes (2026-2027)       -> market_clock.py
  stop / target exit.compute exact-cent planner                -> trade_plan.py
"""
import datetime
import os
import threading

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import edgar_feed
import market_clock
import news_feed
import price_feed
import screeners
import trade_plan
from notifier import notify_new_hits
from universe import build_universe

NY_TZ = pytz.timezone("America/New_York")

app = FastAPI(title="Trading Screener API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # personal-use tool; tighten if you expose it widely
    allow_methods=["*"],
    allow_headers=["*"],
)

STATE = {
    "last_scan": None,
    "last_fundamentals_refresh": None,
    "universe": [],
    "universe_size": 0,
    "results": {k: [] for k in ("invest", "breakout_confirmed", "breakout_pre", "bounce",
                                "strategy_pullback", "strategy_wedge")},
    "fundamentals": {},   # from SEC EDGAR
    "earn_info": {},
    "names": {},          # from Yahoo chart meta
    "price_data": {},
    "news": [],
    "news_errors": [],
    "earnings": [],
    "status_message": "Starting up...",
}

_lock = threading.Lock()
_scan_in_progress = threading.Event()
_fund_in_progress = threading.Event()

LABELS = {
    "invest": "Invest", "breakout_confirmed": "Confirmed breakout", "breakout_pre": "Pre-breakout watchlist",
    "bounce": "Bounce play", "strategy_pullback": "Strategy: pullback", "strategy_wedge": "Strategy: wedge reversal",
}


def is_market_open() -> bool:
    return market_clock.is_open()


def _meta():
    """fundamentals + best-available company name for every ticker in the universe."""
    meta = {}
    for t in STATE["universe"]:
        f = dict(STATE["fundamentals"].get(t, {}))
        f["longName"] = STATE["names"].get(t) or f.get("longName") or t
        meta[t] = f
    return meta


def refresh_fundamentals_job():
    """Slow daily job: SEC EDGAR fundamentals + earnings info. Scans work without it (only Invest / Strategy need it)."""
    if _fund_in_progress.is_set():
        return
    _fund_in_progress.set()
    try:
        if not STATE["universe"]:
            STATE["universe"] = build_universe()
            STATE["universe_size"] = len(STATE["universe"])
        with _lock:
            STATE["status_message"] = "Refreshing fundamentals from SEC EDGAR..."
        fund, earn = edgar_feed.fetch_all(STATE["universe"])
        with _lock:
            if fund:
                STATE["fundamentals"], STATE["earn_info"] = fund, earn
                STATE["last_fundamentals_refresh"] = datetime.datetime.now(NY_TZ).isoformat()
            STATE["status_message"] = "Idle."
        print(f"[main] Fundamentals refreshed for {len(fund)} tickers.")
    finally:
        _fund_in_progress.clear()


def refresh_scan_job():
    """Pull fresh prices and re-run all screeners (skips if one is already running)."""
    if _scan_in_progress.is_set():
        print("[main] Skipping scan -- one is already in progress.")
        return
    _scan_in_progress.set()
    try:
        _run_scan()
    finally:
        _scan_in_progress.clear()


def _run_scan():
    if not STATE["universe"]:
        STATE["universe"] = build_universe()
        STATE["universe_size"] = len(STATE["universe"])
    tickers = STATE["universe"]
    with _lock:
        STATE["status_message"] = "Scanning..."
    price_data, names = price_feed.fetch_price_history(tickers + ["SPY"])
    spy_df = price_data.pop("SPY", None)
    names.pop("SPY", None)
    if not price_data:
        with _lock:
            STATE["status_message"] = "Price fetch failed for every ticker -- see /api/status data_health."
        return

    with _lock:
        STATE["names"].update(names)
    edgar_feed.finalize_market_cap(STATE["fundamentals"], price_data)
    meta = _meta()

    results = {
        "invest": screeners.screen_invest(price_data, meta),
        "breakout_confirmed": screeners.screen_breakout_confirmed(price_data, meta, spy_df),
        "breakout_pre": screeners.screen_breakout_pre(price_data, meta),
        "bounce": screeners.screen_bounce(price_data, meta),
        "strategy_pullback": screeners.screen_strategy_pullback(price_data, meta),
        "strategy_wedge": screeners.screen_strategy_wedge(price_data, meta),
    }
    for rows in results.values():
        trade_plan.add_plans(rows, price_data)
    for key, rows in results.items():
        notify_new_hits(key, LABELS[key], rows)

    flagged = sorted({r["t"] for rows in results.values() for r in rows})
    watch = {t: meta[t]["longName"] for t in flagged[:25]}
    try:
        news_rows, news_errors = news_feed.collect(watch)
    except Exception as e:
        news_rows, news_errors = [], [f"news: {e}"]
    earnings = build_earnings(flagged, price_data)

    with _lock:
        STATE["results"] = results
        STATE["price_data"] = price_data
        STATE["news"], STATE["news_errors"] = news_rows, news_errors
        STATE["earnings"] = earnings
        STATE["last_scan"] = datetime.datetime.now(NY_TZ).isoformat()
        STATE["status_message"] = "Idle."
    print(f"[main] Scan complete. {sum(len(r) for r in results.values())} total hits across all screeners.")


def build_earnings(tickers, price_data):
    """Last reported EPS (SEC) + ESTIMATED next report date + dividend yield from the latest annual dividend/share."""
    out = []
    for t in tickers:
        e = STATE["earn_info"].get(t) or {}
        f = STATE["fundamentals"].get(t) or {}
        df = price_data.get(t)
        px = float(df["close"].iloc[-1]) if df is not None else None
        dps = f.get("divPerShare")
        nxt = e.get("nextEst")
        out.append({
            "t": t,
            "next": (datetime.date.fromisoformat(nxt).strftime("%b %d") + " (est.)") if nxt else "—",
            "last_eps": e.get("lastEps"),
            "last_eps_yoy": e.get("lastEpsYoy"),
            "last_report": e.get("lastFiled") or "—",
            "yield": f"{dps / px * 100:.1f}%" if (dps and px) else "—",
        })
    return out


@app.on_event("startup")
def startup():
    scheduler = BackgroundScheduler(timezone=NY_TZ)
    scheduler.add_job(refresh_fundamentals_job, "cron", hour=6, minute=0)
    scheduler.add_job(refresh_scan_job, "cron", day_of_week="mon-fri", hour="9-16", minute=30)
    scheduler.start()

    def initial_load():
        refresh_scan_job()            # prices first so price-only screeners show up fast
        refresh_fundamentals_job()    # then SEC fundamentals (minutes)
        refresh_scan_job()            # rescan so Invest / Strategy see fundamentals

    threading.Thread(target=initial_load, daemon=True).start()


@app.get("/api/status")
def status():
    m = market_clock.status()
    return {
        "last_scan": STATE["last_scan"],
        "last_fundamentals_refresh": STATE["last_fundamentals_refresh"],
        "universe_size": STATE["universe_size"],
        "market_open": m["open"],
        "market": m,
        "status_message": STATE["status_message"],
        "data_health": {
            "prices_ok": price_feed.HEALTH["ok"], "prices_failed": price_feed.HEALTH["failed"],
            "price_last_error": price_feed.HEALTH["last_error"],
            "sec_user_agent_set": edgar_feed.STATUS["ua_ok"],
            "fundamentals_loaded": len(STATE["fundamentals"]),
            "edgar_last_error": edgar_feed.STATUS["last_error"],
            "news_errors": STATE["news_errors"][:5],
        },
    }


@app.post("/api/refresh")
def refresh():
    threading.Thread(target=refresh_scan_job, daemon=True).start()
    return {"status": "refresh started"}


@app.get("/api/screener/invest")
def get_invest():
    return STATE["results"]["invest"]


@app.get("/api/screener/breakout/confirmed")
def get_breakout_confirmed():
    return STATE["results"]["breakout_confirmed"]


@app.get("/api/screener/breakout/pre")
def get_breakout_pre():
    return STATE["results"]["breakout_pre"]


@app.get("/api/screener/bounce")
def get_bounce():
    return STATE["results"]["bounce"]


@app.get("/api/screener/strategy/pullback")
def get_strategy_pullback():
    return STATE["results"]["strategy_pullback"]


@app.get("/api/screener/strategy/wedge")
def get_strategy_wedge():
    return STATE["results"]["strategy_wedge"]


@app.get("/api/news")
def get_news():
    return STATE["news"]


@app.get("/api/earnings")
def get_earnings():
    return STATE["earnings"]


@app.get("/api/health")
def health():
    """Used by external pingers to keep a free-tier instance awake and to trigger scans (see README)."""
    return {"ok": True, "time": datetime.datetime.now(NY_TZ).isoformat()}


# Serve the built React dashboard (frontend/dist, produced by `npm run build`)
# for every route that isn't one of the /api/* routes above. Mounted last so
# the explicit API routes are always matched first.
_frontend_dist = os.path.join(os.path.dirname(__file__), "frontend", "dist")
if os.path.isdir(_frontend_dist):
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")
else:
    print(f"[main] No frontend build found at {_frontend_dist} -- API-only mode. "
          f"Run `cd frontend && npm install && npm run build` to serve the dashboard from here too.")
