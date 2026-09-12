# Trading Screener

A FastAPI backend that scans S&P 500 + Nasdaq 100 stocks against your four
screeners (Invest, Breakout, Bounce Play, Strategy), plus a React dashboard
(`frontend/`) that displays the results. The backend serves the built
dashboard itself, so the whole thing deploys as **one service**.

## Running locally

**Backend + frontend build together (matches how it runs on Render):**

```bash
python3 -m venv venv && source venv/bin/activate    # Windows: venv\Scripts\activate
pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..
uvicorn main:app --reload --port 8000
```

Open `http://localhost:8000` — that's the dashboard, served by the same
process as the API.

**Or, for frontend live-reload while developing the UI:**

```bash
# terminal 1
uvicorn main:app --reload --port 8000
# terminal 2
cd frontend && npm install && npm run dev
```

Open the URL Vite prints (usually `http://localhost:5173`) — its dev server
proxies `/api/*` calls to the backend on port 8000.

On startup the backend will:
1. Build the universe (S&P 500 + Nasdaq 100 tickers from Wikipedia)
2. Pull fundamentals for every ticker (slow the first time — a few minutes for ~600 tickers)
3. Run the first full scan
4. Then automatically re-scan every hour, 9:30am–4pm ET, Monday–Friday
5. Refresh fundamentals once daily at 6am ET

Locally, you'll get a desktop notification whenever a *new* ticker shows up
in a screener. **On a hosted server this falls back to a console log line**
instead — there's no desktop to notify on Render, so this is expected
behavior, not a bug.

## Deploying to Render (free tier)

1. Push this whole folder to a GitHub repo.
2. In Render: **New → Blueprint**, point it at your repo. It'll read
   `render.yaml` and configure everything automatically (build command,
   start command, Python version). Click **Apply**.
   - If you'd rather set it up manually instead of using the blueprint:
     **New → Web Service** → connect your repo → set:
     - Build Command: `pip install -r requirements.txt && cd frontend && npm install && npm run build`
     - Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
3. Once deployed, your dashboard and API are both live at your
   `https://your-app-name.onrender.com` URL — no separate frontend hosting
   needed.

### Free tier: the spin-down problem, and how to work around it

Render's free tier spins your service down after ~15 minutes with no
incoming HTTP traffic. Since the hourly scan scheduler runs *inside* that
same process, a sleeping instance won't wake itself up to run its 9:30am–4pm
scans — it just stays asleep until someone loads the page.

**Fix: use a free external pinger to hit the app every 10 minutes.** This
keeps the instance awake *and* you can point it at `/api/refresh` directly
so it also triggers a fresh scan each time it pings, rather than just
keeping the lights on:

1. Sign up for a free account at [cron-job.org](https://cron-job.org) or
   [UptimeRobot](https://uptimerobot.com).
2. Create a job that sends a `POST` request to
   `https://your-app-name.onrender.com/api/refresh` every 10–15 minutes,
   restricted to market hours if the service supports scheduling windows.
3. That's it — the in-process scheduler still runs as a backup for whenever
   the instance happens to already be awake, but the external pinger is what
   makes the hourly refresh actually reliable on a free instance.

Without this, the dashboard will still work fine — it just may show
data from whenever the instance last happened to be awake, not truly hourly.

## Endpoints

| Endpoint | Returns |
|---|---|
| `GET /api/status` | last scan time, universe size, market open/closed |
| `GET /api/screener/invest` | Invest screener matches |
| `GET /api/screener/breakout/confirmed` | Confirmed breakout matches |
| `GET /api/screener/breakout/pre` | Pre-breakout watchlist matches |
| `GET /api/screener/bounce` | Bounce play matches |
| `GET /api/screener/strategy/pullback` | Uptrend pullback matches |
| `GET /api/screener/strategy/wedge` | Weekly wedge reversal candidates |
| `GET /api/news` | Headlines for currently flagged tickers |
| `GET /api/earnings` | Earnings dates & dividend info for flagged tickers |
| `POST /api/refresh` | Triggers an immediate re-scan (used by the dashboard's "Refresh now" button, and by the external pinger described above) |
| `GET /api/health` | Simple liveness check — what an external pinger should hit to keep a free instance awake |

## Notes and known limitations

- **The universe (S&P 500 + Nasdaq 100 tickers) is a static snapshot**, not
  scraped live from Wikipedia. We tried live-scraping and hit three different
  failure modes across two rounds of fixes (a pandas API change, a missing
  parser library, and Wikipedia removing the Nasdaq-100 constituent table
  entirely) — since index membership only changes a few times a year, a
  static list bundled in `tickers_data.py` is far more reliable than
  re-scraping on every server start. **To refresh it** (recommended every
  few months), pull an updated list from a source like
  [stockanalysis.com/list/sp-500-stocks](https://stockanalysis.com/list/sp-500-stocks/)
  and [stockanalysis.com/list/nasdaq-100-stocks](https://stockanalysis.com/list/nasdaq-100-stocks/)
  and replace the two lists in `tickers_data.py`.
- **Fundamentals data source is free Yahoo Finance data (yfinance).** It's
  unauthenticated and occasionally rate-limits or has gaps — this is normal
  for free data, not a bug. If a screener returns fewer results than
  expected, it's often a missing fundamentals field for some tickers rather
  than an error.
- **Sector classification**: Yahoo classifies companies as "Technology",
  "Communication Services", etc. (GICS-style), not the "Electronic
  Technology" / "Technology Services" taxonomy from your original brief.
  The Strategy screener treats Yahoo's "Technology" sector as the closest
  available proxy for both — good enough to narrow the list, not a precise
  category match.
- **EPS 5-year growth** uses whatever annual history yfinance's free income
  statement exposes, which is typically ~4 years, not a true 5-year figure.
  Treat it as a solid growth trend indicator rather than an exact number.
- **Weekly wedge detection is a heuristic** (converging linear regression
  through swing highs/lows), not true pattern recognition. It's meant to
  narrow down candidates for you to visually confirm on a chart, per your
  own approach.
- If desktop notifications don't fire, check that `plyer` supports
  notifications on your OS (works out of the box on Windows/macOS; Linux
  may need a notification daemon like `notify-osd` or `dunst` installed).

## Tuning thresholds

All the screener thresholds (market cap floors, RSI ranges, volume
multipliers, etc.) live as constants at the top of `screeners.py` and inline
in each `screen_*` function — edit them directly and restart the server to
adjust the strictness of any screener.
