"""Decide what counts as a deal. No network here, so it's easy to test."""
from statistics import median

MIN_HISTORY = 15          # price samples needed before we trust "normal"
MIN_DAYS = 3              # ...spread over at least this many different days
REALERT_DAYS = 7          # wait this long before re-sending a similar deal
# (runs happen every few hours, so this also stops the same deal pinging you all day)
REALERT_BETTER_PCT = 10   # unless the new price is this much lower


def baseline(history, days_seen=MIN_DAYS):
    """Typical price for a route: the median of recent samples.

    Returns None until there's enough history, so nothing counts as a sale
    in the first few days. One day of prices only says what fares cost today,
    not whether today is unusually cheap.
    """
    if len(history) < MIN_HISTORY or days_seen < MIN_DAYS:
        return None
    return median(history)


def is_sale(price, typical, range_low, drop_pct):
    """A sale by Google's own numbers: below the route's usual price range
    AND at least drop_pct below its typical price. Works from the first run."""
    if not typical or not range_low:
        return False
    return price < range_low and price <= typical * (1 - drop_pct / 100)


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
