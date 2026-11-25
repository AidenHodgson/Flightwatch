from datetime import date

from flightwatch import deals
from flightwatch.search import sample_departures


def test_no_baseline_until_enough_history():
    assert deals.baseline([500] * 5) is None
    assert deals.baseline([500] * 20) == 500


def test_is_deal():
    assert deals.is_deal(340, 500, 30)
    assert not deals.is_deal(360, 500, 30)
    assert deals.is_deal(600, None, 30, max_price=650)
    assert not deals.is_deal(300, None, 30)


def test_should_alert_dedupes():
    assert deals.should_alert(400, [])
    assert not deals.should_alert(390, [400])
    assert deals.should_alert(350, [400])


def test_sample_departures():
    ds = sample_departures(1, every_days=10, today=date(2026, 1, 1))
    assert ds[0] == date(2026, 1, 15)
    assert all(d <= date(2026, 1, 31) for d in ds)
