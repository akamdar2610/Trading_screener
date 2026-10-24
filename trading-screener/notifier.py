"""
Desktop notifications. Only fires for *newly appearing* tickers in a given
screener result set compared to the previous scan, so you don't get the same
alert every hour for a stock that's still sitting in the results.

On a headless server (like Render) there's no desktop to notify -- this
degrades gracefully to a console log line in that case, rather than failing.
"""
try:
    from plyer import notification
    _NOTIFICATIONS_AVAILABLE = True
except Exception as e:
    notification = None
    _NOTIFICATIONS_AVAILABLE = False
    print(f"[notifier] Desktop notifications unavailable in this environment ({e}). Falling back to console logging.")

# key -> set of tickers seen last run
_previous_hits: dict[str, set] = {}


def notify_new_hits(screener_key: str, screener_label: str, rows: list[dict]):
    current = {r["t"] for r in rows}
    previous = _previous_hits.get(screener_key, set())
    new_tickers = current - previous
    _previous_hits[screener_key] = current

    if not new_tickers:
        return

    tickers_str = ", ".join(sorted(new_tickers)[:8])
    if len(new_tickers) > 8:
        tickers_str += f" +{len(new_tickers) - 8} more"

    if _NOTIFICATIONS_AVAILABLE:
        try:
            notification.notify(
                title=f"{screener_label}: {len(new_tickers)} new",
                message=tickers_str,
                app_name="Trading Screener",
                timeout=10,
            )
            return
        except Exception as e:
            print(f"[notifier] Desktop notification failed, logging instead: {e}")

    print(f"[notifier] {screener_label}: {len(new_tickers)} new -- {tickers_str}")
