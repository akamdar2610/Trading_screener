"""
Trading Screener backend.

Run with:  uvicorn main:app --reload --port 8000

Endpoints (all GET unless noted):
  /api/status
  /api/screener/invest
  /api/screener/breakout/confirmed
  /api/screener/breakout/pre
  /api/screener/bounce
  /api/screener/strategy/pullback
  /api/screener/strategy/wedge
  /api/news
  /api/earnings
  /api/refresh   (POST) - triggers an immediate rescan in the background
"""
import datetime
import os
import threading

import pytz
import yfinance as yf
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import screeners
from data_fetch import fetch_price_history, fetch_fundamentals
from notifier import notify_new_hits
from universe import build_universe

NY_TZ = pytz.timezone("America/New_York")

app = FastAPI(title="Trading Screener API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # local personal-use tool; tighten this if you ever expose it beyond localhost
    allow_methods=["*"],
    allow_headers=["*"],
)

STATE = {
    "last_scan": None,
    "last_fundamentals_refresh": None,
    "universe_size": 0,
    "results": {
        "invest": [],
        "breakout_confirmed": [],
        "breakout_pre": [],
        "bounce": [],
        "strategy_pullback": [],
        "strategy_wedge": [],
    },
    "fundamentals": {},
    "price_data": {},
    "news": [],
    "earnings": [],
    "status_message": "Starting up...",
}

_lock = threading.Lock()


def is_market_open() -> bool:
    now = datetime.datetime.now(NY_TZ)
    if now.weekday() >= 5:
        return False
    open_t = now.replace(hour=9, minute=30, second=0, microsecond=0)
    close_t = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return open_t <= now <= close_t


def refresh_fundamentals_job():
    """Slow, once-a-day job: rebuild universe + pull fundamentals for all of it."""
    with _lock:
        STATE["status_message"] = "Refreshing universe & fundamentals..."
    tickers = build_universe()
    fundamentals = fetch_fundamentals(tickers)
    with _lock:
        STATE["fundamentals"] = fundamentals
        STATE["universe_size"] = len(tickers)
        STATE["last_fundamentals_refresh"] = datetime.datetime.now(NY_TZ).isoformat()
        STATE["status_message"] = "Fundamentals refreshed."
    print(f"[main] Fundamentals refreshed for {len(fundamentals)} tickers.")


def refresh_scan_job():
    """Hourly job: pull fresh price history and re-run all screeners."""
    fundamentals = STATE["fundamentals"]
    if not fundamentals:
        print("[main] Skipping scan -- fundamentals not loaded yet.")
        return

    tickers = list(fundamentals.keys())
    with _lock:
        STATE["status_message"] = "Scanning..."
    price_data = fetch_price_history(tickers + ["SPY"])
    spy_df = price_data.pop("SPY", None)

    results = {
        "invest": screeners.screen_invest(price_data, fundamentals),
        "breakout_confirmed": screeners.screen_breakout_confirmed(price_data, fundamentals, spy_df),
        "breakout_pre": screeners.screen_breakout_pre(price_data, fundamentals),
        "bounce": screeners.screen_bounce(price_data, fundamentals),
        "strategy_pullback": screeners.screen_strategy_pullback(price_data, fundamentals),
        "strategy_wedge": screeners.screen_strategy_wedge(price_data, fundamentals),
    }

    labels = {
        "invest": "Invest",
        "breakout_confirmed": "Confirmed breakout",
        "breakout_pre": "Pre-breakout watchlist",
        "bounce": "Bounce play",
        "strategy_pullback": "Strategy: pullback",
        "strategy_wedge": "Strategy: wedge reversal",
    }
    for key, rows in results.items():
        notify_new_hits(key, labels[key], rows)

    flagged_tickers = sorted({r["t"] for rows in results.values() for r in rows})
    news = fetch_news(flagged_tickers[:15])
    earnings = fetch_earnings_dividends(flagged_tickers)

    with _lock:
        STATE["results"] = results
        STATE["price_data"] = price_data
        STATE["news"] = news
        STATE["earnings"] = earnings
        STATE["last_scan"] = datetime.datetime.now(NY_TZ).isoformat()
        STATE["status_message"] = "Idle."
    print(f"[main] Scan complete. {sum(len(r) for r in results.values())} total hits across all screeners.")


def fetch_news(tickers: list[str]) -> list[dict]:
    items = []
    seen_titles = set()
    for t in tickers:
        try:
            for n in (yf.Ticker(t).news or [])[:3]:
                title = n.get("title")
                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)
                items.append({
                    "h": title,
                    "s": n.get("publisher", "Unknown"),
                    "time": datetime.datetime.fromtimestamp(
                        n.get("providerPublishTime", 0), tz=NY_TZ
                    ).strftime("%b %d, %I:%M %p") if n.get("providerPublishTime") else "",
                    "url": n.get("link", ""),
                    "tickers": [t],
                })
        except Exception:
            continue
    items.sort(key=lambda x: x["time"], reverse=True)
    return items[:20]


def fetch_earnings_dividends(tickers: list[str]) -> list[dict]:
    out = []
    for t in tickers:
        try:
            tk = yf.Ticker(t)
            info = tk.info or {}
            cal = tk.calendar or {}
            next_earnings = None
            if isinstance(cal, dict) and cal.get("Earnings Date"):
                d = cal["Earnings Date"]
                next_earnings = d[0].strftime("%b %d") if isinstance(d, list) and d else None
            div_yield = info.get("dividendYield")
            ex_div_ts = info.get("exDividendDate")
            ex_div = (
                datetime.datetime.fromtimestamp(ex_div_ts, tz=NY_TZ).strftime("%b %d")
                if ex_div_ts else "—"
            )
            out.append({
                "t": t,
                "next": next_earnings or "—",
                "est": info.get("epsForward") or info.get("forwardEps"),
                "yield": f"{div_yield * 100:.1f}%" if div_yield else "—",
                "exdiv": ex_div,
            })
        except Exception:
            continue
    return out


@app.on_event("startup")
def startup():
    scheduler = BackgroundScheduler(timezone=NY_TZ)
    scheduler.add_job(refresh_fundamentals_job, "cron", hour=6, minute=0)
    scheduler.add_job(refresh_scan_job, "cron", day_of_week="mon-fri", hour="9-16", minute=30)
    scheduler.start()

    def initial_load():
        refresh_fundamentals_job()
        refresh_scan_job()

    threading.Thread(target=initial_load, daemon=True).start()


@app.get("/api/status")
def status():
    return {
        "last_scan": STATE["last_scan"],
        "last_fundamentals_refresh": STATE["last_fundamentals_refresh"],
        "universe_size": STATE["universe_size"],
        "market_open": is_market_open(),
        "status_message": STATE["status_message"],
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
