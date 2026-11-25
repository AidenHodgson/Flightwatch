"""Turn a list of sale dates into a short, human time range."""
from datetime import date

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
SEASON = {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
          6: "summer", 7: "summer", 8: "summer", 9: "fall", 10: "fall", 11: "fall"}


def _part(d):
    return "early" if d.day <= 10 else "mid" if d.day <= 20 else "late"


def short(d):
    return f"{MONTHS[d.month - 1][:3]} {d.day}"


def describe(sale_dates, checked_count=None):
    """sale_dates: departure dates (date objects) that were on sale.

    Returns e.g. 'October only' or 'mid-January to early-March (this winter)'.
    """
    ds = sorted(sale_dates)
    if not ds:
        return ""
    first, last = ds[0], ds[-1]
    if (first.year, first.month) == (last.year, last.month):
        span = f"{MONTHS[first.month - 1]} only" if len(ds) > 1 else f"around {short(first)}"
    else:
        span = f"{_part(first)}-{MONTHS[first.month - 1]} to {_part(last)}-{MONTHS[last.month - 1]}"
        seasons = {SEASON[d.month] for d in ds}
        if len(seasons) == 1:
            span += f" (this {seasons.pop()})"
    return span


def share(sale_count, checked_count):
    return f"{sale_count} of {checked_count} departure dates we checked" if checked_count else ""
