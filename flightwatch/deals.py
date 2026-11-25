"""Decide what counts as a deal. No network here, so it's easy to test."""
from statistics import median

MIN_HISTORY = 15          # price samples needed before we trust "normal"
REALERT_DAYS = 7          # wait this long before re-sending a similar deal
REALERT_BETTER_PCT = 10   # unless the new price is this much lower


def baseline(history):
    """Typical price for a route: the median of recent samples."""
    if len(history) < MIN_HISTORY:
        return None
    return median(history)


def is_deal(price, normal, drop_pct, max_price=None):
    if max_price is not None and price <= max_price:
        return True
    if normal is None:
        return False
    return price <= normal * (1 - drop_pct / 100)


def should_alert(price, recent_alert_prices):
    """recent_alert_prices: prices already alerted for this watch in REALERT_DAYS."""
    if not recent_alert_prices:
        return True
    best_sent = min(recent_alert_prices)
    return price <= best_sent * (1 - REALERT_BETTER_PCT / 100)
