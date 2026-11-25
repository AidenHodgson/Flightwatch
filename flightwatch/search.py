"""Price lookups through the open-source fli Google Flights scraper."""
import logging
from datetime import date, timedelta

from fli.core.builders import build_date_search_segments
from fli.core.links import google_flights_url
from fli.models import Airport, DateSearchFilters, MaxStops, PassengerInfo, SeatType
from fli.search import SearchDates

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
        self.client = SearchDates()

    def cheapest_round_trip(self, origin, destination, cabin, depart, nights):
        """Cheapest round-trip price in USD for one departure date, or None."""
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
            results = self.client.search(filters, currency="USD")
        except Exception as e:  # Google changes things, keep the run going
            log.warning("search failed %s-%s %s: %s", origin, destination, depart, e)
            return None
        if not results:
            return None
        return int(round(min(r.price for r in results)))


def booking_link(origin, destination, depart, ret):
    return google_flights_url(origin, destination, depart, ret)
