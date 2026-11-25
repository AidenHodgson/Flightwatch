"""Price lookups through the open-source fli Google Flights scraper."""
import logging
from datetime import date, timedelta

from fli.core.builders import build_date_search_segments
from fli.core.links import google_flights_url
from fli.models import Airport, DateSearchFilters, MaxStops, PassengerInfo, SeatType
from fli.search import SearchDates
from fli.search._tfs import build_tfs, fetch_payload, page_url
from fli.search.dates import _flights_in

log = logging.getLogger(__name__)

CABINS = {
    "ECONOMY": SeatType.ECONOMY,
    "PREMIUM_ECONOMY": SeatType.PREMIUM_ECONOMY,
    "BUSINESS": SeatType.BUSINESS,
    "FIRST": SeatType.FIRST,
}


def sample_departures(months_ahead, every_days=10, start_days=14, today=None):
    """Departure dates to check: every N days from 2 weeks out to months_ahead."""
    today = today or date.today()
    end = today + timedelta(days=30 * months_ahead)
    d = today + timedelta(days=start_days)
    out = []
    while d <= end:
        out.append(d)
        d += timedelta(days=every_days)
    return out


class PriceChecker:
    def __init__(self):
        self.client = SearchDates()  # only used for its HTTP client and rate limits

    def check(self, origin, destination, cabin, depart, nights):
        """Cheapest round trip for one departure date, plus Google's price insights.

        Returns {"price", "typical", "range_low", "range_high"} or None.
        typical and the range come from the same box Google Flights shows as
        "prices are currently low/typical/high"; they're None if Google didn't
        include them.
        """
        if origin not in Airport.__members__ or destination not in Airport.__members__:
            log.warning("unknown airport code in %s-%s, skipping", origin, destination)
            return None
        ret = depart + timedelta(days=nights)
        segments, trip_type = build_date_search_segments(
            origin=Airport[origin],
            destination=Airport[destination],
            start_date=depart.isoformat(),
            trip_duration=nights,
            is_round_trip=True,
        )
        filters = DateSearchFilters(
            trip_type=trip_type,
            passenger_info=PassengerInfo(adults=1),
            flight_segments=segments,
            stops=MaxStops.ONE_STOP_OR_FEWER,
            seat_type=CABINS.get(cabin, SeatType.ECONOMY),
            from_date=depart.isoformat(),
            to_date=depart.isoformat(),
            duration=nights,
        )
        try:
            url = page_url(build_tfs(filters, travel_dates=[depart.isoformat(), ret.isoformat()]), "USD")
            payload = fetch_payload(self.client.client, url)
        except Exception as e:  # Google changes things, keep the run going
            log.warning("search failed %s-%s %s: %s", origin, destination, depart, e)
            return None
        if not payload:
            return None
        insights = parse_insights(payload)
        prices = []
        try:
            prices = [f.price for f in _flights_in(payload) if getattr(f, "price", None)]
        except Exception as e:
            log.warning("could not read flights %s-%s %s: %s", origin, destination, depart, e)
        price = min(prices) if prices else insights.get("current")
        if not price:
            return None
        return {
            "price": int(round(price)),
            "typical": insights.get("typical"),
            "range_low": insights.get("range_low"),
            "range_high": insights.get("range_high"),
        }

    def cheapest_round_trip(self, origin, destination, cabin, depart, nights):
        r = self.check(origin, destination, cabin, depart, nights)
        return r["price"] if r else None


def parse_insights(payload):
    """Read Google's price insights block from a search page payload.

    Shape seen Nov 2026, payload[5]:
      [level, [_, current], [_, typical], [_, typical - current], [_, range_low], [_, range_high], ...]
    Anything unexpected returns {} so a Google change never breaks a run.
    """
    try:
        block = payload[5]
        val = lambda i: int(block[i][1]) if block[i] and block[i][1] is not None else None
        out = {"level": block[0], "current": val(1), "typical": val(2),
               "range_low": val(4), "range_high": val(5)}
        if out["typical"] and out["range_low"] and out["range_high"] and out["range_low"] <= out["range_high"]:
            return out
    except (IndexError, TypeError, ValueError):
        pass
    return {}


def booking_link(origin, destination, depart, ret):
    return google_flights_url(origin, destination, depart, ret)
