import { useState, useEffect, useCallback } from "react";
import { TrendingUp, TrendingDown, Zap, ArrowUpCircle, Compass, Newspaper, LayoutGrid, CalendarClock, RefreshCw, AlertCircle } from "lucide-react";

// Relative path: works via the Vite dev-server proxy locally, and via
// same-origin requests once this is built and served by the FastAPI backend.
const API_BASE = "/api";

const C = {
  bg: "#12151B",
  panel: "#181C24",
  panelRaised: "#1F2530",
  border: "#2B313D",
  borderSoft: "#232833",
  gold: "#C9A15D",
  goldSoft: "rgba(201,161,93,0.12)",
  text: "#EDEAE3",
  textDim: "#8B93A3",
  textFaint: "#5C6472",
  gain: "#4FAE81",
  loss: "#DB6B6B",
};

const fontDisplay = "'Fraunces', Georgia, serif";
const fontBody = "'Inter', -apple-system, sans-serif";
const fontMono = "'IBM Plex Mono', 'Courier New', monospace";

const QUOTES = [
  { line: "The market can stay irrational longer than you can stay solvent.", by: "John Maynard Keynes" },
  { line: "Risk comes from not knowing what you're doing.", by: "Warren Buffett" },
  { line: "Cut your losses quickly, let your winners run.", by: "Trading floor adage" },
  { line: "It's not whether you're right or wrong, but how much you make when you're right and how much you lose when you're wrong.", by: "George Soros" },
  { line: "Amateurs think about how much money they can make. Professionals think about how much money they could lose.", by: "Jack Schwager" },
  { line: "The goal of a trader is not to trade often, but to trade well.", by: "Alexander Elder" },
];

const fmtVol = (v) => (v >= 1e6 ? (v / 1e6).toFixed(1) + "M" : v >= 1e3 ? (v / 1e3).toFixed(0) + "K" : v);
const fmtUsd = (v) => "$" + Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 });

function Change({ v }) {
  const up = v >= 0;
  return (
    <span style={{ color: up ? C.gain : C.loss, display: "inline-flex", alignItems: "center", gap: 4, fontFamily: fontMono }}>
      {up ? <TrendingUp size={13} /> : <TrendingDown size={13} />}
      {up ? "+" : ""}{Number(v).toFixed(1)}%
    </span>
  );
}

function Th({ children, align = "left" }) {
  return (
    <th style={{ textAlign: align, padding: "10px 14px", fontFamily: fontBody, fontSize: 12, fontWeight: 500, color: C.textDim, borderBottom: `1px solid ${C.border}`, whiteSpace: "nowrap" }}>
      {children}
    </th>
  );
}
function Td({ children, align = "left", mono = false, strong = false }) {
  return (
    <td style={{ textAlign: align, padding: "11px 14px", fontFamily: mono ? fontMono : fontBody, fontSize: 13.5, color: strong ? C.text : C.textDim, borderBottom: `1px solid ${C.borderSoft}`, whiteSpace: "nowrap" }}>
      {children}
    </td>
  );
}

function EmptyState({ title, detail }) {
  return (
    <div style={{ border: `1px dashed ${C.border}`, borderRadius: 6, padding: "40px 24px", textAlign: "center", color: C.textDim }}>
      <AlertCircle size={20} style={{ color: C.textFaint, marginBottom: 10 }} />
      <p style={{ margin: 0, fontSize: 14, color: C.text }}>{title}</p>
      <p style={{ margin: "6px 0 0", fontSize: 13, color: C.textFaint }}>{detail}</p>
    </div>
  );
}

function ScreenerTable({ columns, rows, loading, error }) {
  if (loading) {
    return <EmptyState title="Loading results..." detail="Pulling the latest scan from the server." />;
  }
  if (error) {
    return (
      <EmptyState
        title="Can't reach the screener server"
        detail={`Make sure the backend is deployed and reachable — this app expects an /api route on the same server.`}
      />
    );
  }
  if (!rows || rows.length === 0) {
    return <EmptyState title="No matches right now" detail="Nothing in the universe currently meets this screener's criteria. Check back after the next scan." />;
  }
  return (
    <div style={{ overflowX: "auto", border: `1px solid ${C.border}`, borderRadius: 6 }}>
      <table style={{ borderCollapse: "collapse", width: "100%", minWidth: 720 }}>
        <thead>
          <tr>{columns.map((c) => <Th key={c.key} align={c.align}>{c.label}</Th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.t || i} onMouseEnter={(e) => (e.currentTarget.style.background = C.panelRaised)} onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
              {columns.map((c) => (
                <Td key={c.key} align={c.align} mono={c.mono} strong={c.strong}>
                  {c.render ? c.render(r) : r[c.key]}
                </Td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const baseCols = [
  { key: "t", label: "Ticker", strong: true },
  { key: "n", label: "Name" },
  { key: "px", label: "Price", align: "right", mono: true, render: (r) => fmtUsd(r.px) },
  { key: "chg", label: "Chg", align: "right", render: (r) => <Change v={r.chg} /> },
  { key: "o", label: "Open", align: "right", mono: true, render: (r) => fmtUsd(r.o) },
  { key: "h", label: "High", align: "right", mono: true, render: (r) => fmtUsd(r.h) },
  { key: "l", label: "Low", align: "right", mono: true, render: (r) => fmtUsd(r.l) },
  { key: "vol", label: "Volume", align: "right", mono: true, render: (r) => fmtVol(r.vol) },
];

const SCREENERS = {
  invest: {
    label: "Invest",
    icon: LayoutGrid,
    tagline: "Fundamentals-first, long-term holds",
    variants: {
      main: {
        label: "All candidates",
        endpoint: "/screener/invest",
        cols: [...baseCols,
          { key: "cap", label: "Mkt cap", align: "right", mono: true, render: (r) => "$" + r.cap + "B" },
          { key: "eps5", label: "EPS gr. 5y", align: "right", mono: true, render: (r) => r.eps5 + "%" },
          { key: "roe", label: "ROE", align: "right", mono: true, render: (r) => r.roe + "%" },
          { key: "cr", label: "Curr. ratio", align: "right", mono: true, render: (r) => Number(r.cr).toFixed(1) },
          { key: "peg", label: "PEG", align: "right", mono: true, render: (r) => (r.peg != null ? Number(r.peg).toFixed(1) : "—") },
        ],
      },
    },
  },
  breakout: {
    label: "Breakout",
    icon: Zap,
    tagline: "Confirmed moves and setups forming",
    variants: {
      confirmed: {
        label: "Confirmed breakout",
        endpoint: "/screener/breakout/confirmed",
        cols: [...baseCols,
          { key: "rvol", label: "Rel. vol", align: "right", mono: true, render: (r) => (r.rvol != null ? r.rvol.toFixed(1) + "x" : "—") },
          { key: "rsi", label: "RSI", align: "right", mono: true },
          { key: "days", label: "Days since", align: "right", mono: true },
        ],
      },
      pre: {
        label: "Pre-breakout watchlist",
        endpoint: "/screener/breakout/pre",
        cols: [...baseCols,
          { key: "bb", label: "BB width", align: "right", mono: true, render: (r) => r.bb + "%" },
          { key: "base", label: "Days in base", align: "right", mono: true },
        ],
      },
    },
  },
  bounce: {
    label: "Bounce play",
    icon: ArrowUpCircle,
    tagline: "Reclaiming the 20-day, still under the 50",
    variants: {
      main: {
        label: "All candidates",
        endpoint: "/screener/bounce",
        cols: [...baseCols,
          { key: "dvol", label: "$ vol/day", align: "right", mono: true, render: (r) => "$" + r.dvol + "M" },
          { key: "rvol", label: "Rel. vol", align: "right", mono: true, render: (r) => Number(r.rvol).toFixed(1) + "x" },
          { key: "swing", label: "Above swing low", align: "right", mono: true, render: (r) => r.swing + "%" },
        ],
      },
    },
  },
  strategy: {
    label: "Strategy",
    icon: Compass,
    tagline: "Your playbook: pullbacks and wedge reversals",
    variants: {
      pullback: {
        label: "Uptrend pullback",
        endpoint: "/screener/strategy/pullback",
        cols: [...baseCols,
          { key: "sector", label: "Sector" },
          { key: "fib", label: "Fib zone", align: "right", mono: true },
          { key: "sup", label: "Dist. to support", align: "right", mono: true, render: (r) => r.sup + "%" },
        ],
      },
      wedge: {
        label: "Weekly wedge reversal",
        endpoint: "/screener/strategy/wedge",
        cols: [...baseCols,
          { key: "sector", label: "Sector" },
          { key: "weeks", label: "Weeks forming", align: "right", mono: true },
          { key: "status", label: "Status" },
        ],
      },
    },
  },
};

function useFetch(path, deps) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setError(false);
    fetch(API_BASE + path)
      .then((res) => {
        if (!res.ok) throw new Error("bad response");
        return res.json();
      })
      .then((json) => {
        setData(json);
        setLoading(false);
      })
      .catch(() => {
        setError(true);
        setLoading(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    load();
  }, [load]);

  return { data, loading, error, reload: load };
}

export default function TradingDashboard() {
  const [tab, setTab] = useState("screener");
  const [screener, setScreener] = useState("invest");
  const [variant, setVariant] = useState("main");
  const [quoteIdx, setQuoteIdx] = useState(0);
  const [refreshing, setRefreshing] = useState(false);

  const active = SCREENERS[screener];
  const variantKeys = Object.keys(active.variants);
  const activeVariant = active.variants[variant] || active.variants[variantKeys[0]];

  const status = useFetch("/status", []);
  const table = useFetch(activeVariant.endpoint, [activeVariant.endpoint]);
  const news = useFetch("/news", [tab]);
  const earnings = useFetch("/earnings", [tab]);

  const selectScreener = (key) => {
    setScreener(key);
    setVariant(Object.keys(SCREENERS[key].variants)[0]);
  };

  const triggerRefresh = () => {
    setRefreshing(true);
    fetch(API_BASE + "/refresh", { method: "POST" })
      .then(() => {
        setTimeout(() => {
          table.reload();
          status.reload();
          setRefreshing(false);
        }, 1500);
      })
      .catch(() => setRefreshing(false));
  };

  const statusData = status.data;

  return (
    <div style={{ background: C.bg, minHeight: "100vh", fontFamily: fontBody, color: C.text, padding: "32px 28px" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,500;1,9..144,400&family=Inter:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');
        * { box-sizing: border-box; }
        button:focus-visible, [tabindex]:focus-visible { outline: 2px solid ${C.gold}; outline-offset: 2px; }
        @media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>

      <div style={{ maxWidth: 1180, margin: "0 auto" }}>
        {/* Header */}
        <div style={{ marginBottom: 22, display: "flex", justifyContent: "space-between", alignItems: "flex-end", flexWrap: "wrap", gap: 12 }}>
          <div>
            <h1 style={{ fontFamily: fontDisplay, fontWeight: 500, fontSize: 34, margin: 0, letterSpacing: "-0.01em" }}>
              Welcome, Aayush
            </h1>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 6, color: C.textDim, fontSize: 13.5, flexWrap: "wrap" }}>
              <span style={{ width: 6, height: 6, borderRadius: "50%", background: statusData?.market_open ? C.gain : C.textFaint, display: "inline-block" }} />
              <span>{statusData?.market_open ? "Market open, NYSE" : "Market closed"}</span>
              {statusData?.last_scan && (
                <span style={{ color: C.textFaint, fontFamily: fontMono, fontSize: 12.5 }}>
                  Last scan {new Date(statusData.last_scan).toLocaleTimeString()}
                </span>
              )}
              {statusData?.universe_size ? (
                <span style={{ color: C.textFaint, fontSize: 12.5 }}>· {statusData.universe_size} tickers scanned</span>
              ) : null}
            </div>
          </div>
          <button
            onClick={triggerRefresh}
            disabled={refreshing}
            style={{
              background: "transparent", border: `1px solid ${C.border}`, color: C.textDim, borderRadius: 5,
              padding: "8px 14px", fontSize: 12.5, cursor: refreshing ? "default" : "pointer", fontFamily: fontBody,
              display: "flex", alignItems: "center", gap: 7,
            }}
          >
            <RefreshCw size={13} style={{ animation: refreshing ? "spin 1s linear infinite" : "none" }} />
            {refreshing ? "Refreshing..." : "Refresh now"}
          </button>
        </div>

        {/* Quote band */}
        <div style={{ background: C.panel, border: `1px solid ${C.border}`, borderLeft: `3px solid ${C.gold}`, borderRadius: 6, padding: "20px 24px", marginBottom: 28, display: "flex", justifyContent: "space-between", alignItems: "flex-end", gap: 20 }}>
          <div>
            <p style={{ fontFamily: fontDisplay, fontStyle: "italic", fontSize: 19, lineHeight: 1.5, margin: 0, maxWidth: 640, color: C.text }}>
              "{QUOTES[quoteIdx].line}"
            </p>
            <p style={{ marginTop: 8, marginBottom: 0, fontSize: 13, color: C.textDim }}>— {QUOTES[quoteIdx].by}</p>
          </div>
          <button
            onClick={() => setQuoteIdx((i) => (i + 1) % QUOTES.length)}
            style={{ background: "transparent", border: `1px solid ${C.border}`, color: C.textDim, borderRadius: 5, padding: "7px 14px", fontSize: 12.5, cursor: "pointer", whiteSpace: "nowrap", fontFamily: fontBody }}
          >
            Next quote
          </button>
        </div>

        {/* Main nav */}
        <div style={{ display: "flex", justifyContent: "center", gap: 28, borderBottom: `1px solid ${C.border}`, marginBottom: 24 }}>
          {[{ key: "screener", label: "Screener", Icon: LayoutGrid }, { key: "news", label: "News", Icon: Newspaper }].map(({ key, label, Icon }) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              style={{
                background: "none", border: "none", cursor: "pointer", padding: "0 0 12px 0",
                fontFamily: fontBody, fontSize: 15, fontWeight: 500,
                color: tab === key ? C.text : C.textFaint,
                borderBottom: tab === key ? `2px solid ${C.gold}` : "2px solid transparent",
                display: "flex", alignItems: "center", gap: 7,
              }}
            >
              <Icon size={16} /> {label}
            </button>
          ))}
        </div>

        {tab === "screener" && (
          <div style={{ display: "flex", gap: 24 }}>
            {/* Sidebar */}
            <div style={{ width: 210, flexShrink: 0 }}>
              {Object.entries(SCREENERS).map(([key, s]) => {
                const Icon = s.icon;
                const isActive = screener === key;
                return (
                  <div key={key} style={{ marginBottom: 4 }}>
                    <button
                      onClick={() => selectScreener(key)}
                      style={{
                        width: "100%", textAlign: "left", background: isActive ? C.goldSoft : "transparent",
                        border: "none", borderRadius: 6, padding: "10px 12px", cursor: "pointer",
                        display: "flex", alignItems: "center", gap: 9,
                        color: isActive ? C.gold : C.textDim, fontFamily: fontBody, fontSize: 14, fontWeight: 500,
                      }}
                    >
                      <Icon size={16} /> {s.label}
                    </button>
                    {isActive && Object.keys(s.variants).length > 1 && (
                      <div style={{ marginLeft: 30, marginTop: 2, marginBottom: 6 }}>
                        {Object.entries(s.variants).map(([vk, v]) => (
                          <button
                            key={vk}
                            onClick={() => setVariant(vk)}
                            style={{
                              display: "block", width: "100%", textAlign: "left", background: "none", border: "none",
                              cursor: "pointer", padding: "6px 0", fontFamily: fontBody, fontSize: 13,
                              color: variant === vk ? C.text : C.textFaint,
                            }}
                          >
                            {v.label}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {/* Table area */}
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ marginBottom: 14 }}>
                <h2 style={{ fontFamily: fontDisplay, fontSize: 21, fontWeight: 500, margin: 0 }}>{activeVariant.label}</h2>
                <p style={{ color: C.textDim, fontSize: 13.5, margin: "4px 0 0" }}>
                  {active.tagline} · {table.data ? `${table.data.length} matches` : "—"}
                </p>
              </div>
              <ScreenerTable columns={activeVariant.cols} rows={table.data} loading={table.loading} error={table.error} />
            </div>
          </div>
        )}

        {tab === "news" && (
          <div style={{ display: "flex", gap: 28 }}>
            <div style={{ flex: 1.4, minWidth: 0 }}>
              <h2 style={{ fontFamily: fontDisplay, fontSize: 21, fontWeight: 500, margin: "0 0 14px" }}>Market pulse</h2>
              {news.loading && <EmptyState title="Loading news..." detail="Pulling the latest headlines for your flagged tickers." />}
              {news.error && <EmptyState title="Can't reach the screener server" detail={`Make sure the backend is deployed and reachable.`} />}
              {!news.loading && !news.error && (!news.data || news.data.length === 0) && (
                <EmptyState title="No news yet" detail="News populates once the first scan flags some tickers to follow." />
              )}
              {news.data && news.data.map((n, i) => (
                <a key={i} href={n.url} target="_blank" rel="noreferrer" style={{ textDecoration: "none", color: "inherit", display: "block", borderBottom: `1px solid ${C.borderSoft}`, padding: "14px 0" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                    <h3 style={{ fontFamily: fontBody, fontWeight: 600, fontSize: 15, margin: 0, color: C.text }}>{n.h}</h3>
                    <span style={{ color: C.textFaint, fontSize: 12.5, whiteSpace: "nowrap", fontFamily: fontMono }}>{n.time}</span>
                  </div>
                  <span style={{ color: C.textFaint, fontSize: 12.5 }}>{n.s}</span>
                </a>
              ))}
            </div>

            <div style={{ flex: 1, minWidth: 0 }}>
              <h2 style={{ fontFamily: fontDisplay, fontSize: 21, fontWeight: 500, margin: "0 0 6px", display: "flex", alignItems: "center", gap: 8 }}>
                <CalendarClock size={18} style={{ color: C.gold }} /> Earnings & dividends
              </h2>
              <p style={{ color: C.textDim, fontSize: 13, margin: "0 0 14px" }}>For tickers currently flagged across your screeners</p>
              {earnings.loading && <EmptyState title="Loading..." detail="Fetching earnings and dividend data." />}
              {earnings.error && <EmptyState title="Can't reach the screener server" detail={`Make sure the backend is deployed and reachable.`} />}
              {!earnings.loading && !earnings.error && (!earnings.data || earnings.data.length === 0) && (
                <EmptyState title="Nothing flagged yet" detail="This fills in once a screener scan produces results." />
              )}
              {earnings.data && earnings.data.length > 0 && (
                <div style={{ border: `1px solid ${C.border}`, borderRadius: 6, overflow: "hidden" }}>
                  <table style={{ borderCollapse: "collapse", width: "100%" }}>
                    <thead>
                      <tr>
                        <Th>Ticker</Th>
                        <Th align="right">Next earnings</Th>
                        <Th align="right">EPS est.</Th>
                        <Th align="right">Div. yield</Th>
                        <Th align="right">Ex-div</Th>
                      </tr>
                    </thead>
                    <tbody>
                      {earnings.data.map((r) => (
                        <tr key={r.t}>
                          <Td strong>{r.t}</Td>
                          <Td align="right" mono>{r.next}</Td>
                          <Td align="right" mono>{r.est != null ? Number(r.est).toFixed(2) : "—"}</Td>
                          <Td align="right" mono>{r.yield}</Td>
                          <Td align="right" mono>{r.exdiv}</Td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
