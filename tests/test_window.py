from datetime import date

from flightwatch import airlines, window


def test_one_month():
    assert window.describe([date(2027, 10, 4), date(2027, 10, 14)], 17).startswith("October only")


def test_season_span():
    s = window.describe([date(2027, 1, 15), date(2027, 2, 4), date(2027, 2, 24)], 17)
    assert s == "mid-January to late-February (this winter)"
    assert window.share(3, 17) == "3 of 17 departure dates we checked"


def test_single_date():
    assert window.describe([date(2027, 5, 8)], 17).startswith("around May 8")


def test_airline_match_and_describe():
    opt = {"price": 1642, "airlines": ["DL", "KE"], "stops": 1}
    assert airlines.matches(opt, ["DL"])
    assert not airlines.matches(opt, ["UA"])
    assert airlines.describe(opt) == "Delta and Korean Air, 1 stop"
    assert airlines.describe({"airlines": ["DL"], "stops": 0}) == "Delta, nonstop"
