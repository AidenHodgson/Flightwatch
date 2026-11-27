from datetime import datetime

from flightwatch import digest
from tests.test_run import FakeD1


def _db():
    db = FakeD1()
    db.execute("INSERT INTO users (name, email, token, digest) VALUES ('Aiden', 'a@x.com', 't', 1)")
    db.execute("INSERT INTO users (name, email, digest) VALUES ('Dad', 'd@x.com', 0)")
    db.execute("INSERT INTO watches (user_id, origin, destination) VALUES (1, 'ATL', 'DUB')")
    db.execute("INSERT INTO watches (user_id, origin, destination) VALUES (1, 'ATL', 'LHR')")
    for dest, price, typ in [("DUB", 719, 983), ("DUB", 800, 983), ("LHR", 776, 640)]:
        db.execute("INSERT INTO prices (origin,destination,cabin,depart_date,return_date,price,typical,checked_at) "
                   "VALUES ('ATL', ?, 'ECONOMY', '2027-05-09', '2027-05-17', ?, ?, datetime('now','-1 hours'))", [dest, price, typ])
    return db


def _patch(monkeypatch, db, when):
    sent = []
    monkeypatch.setattr(digest, "D1", lambda: db)
    monkeypatch.setattr(digest.mailer, "send", lambda *a: sent.append(a))

    class FakeDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return when.replace(tzinfo=tz)
    monkeypatch.setattr(digest, "datetime", FakeDT)
    return sent


def test_sends_once_on_sunday_after_10(monkeypatch):
    db = _db()
    sent = _patch(monkeypatch, db, datetime(2026, 11, 29, 10, 5))  # Sunday
    digest.run()
    digest.run()  # a second GitHub try the same morning does nothing
    assert len(sent) == 1 and sent[0][0] == "a@x.com"
    assert sent[0][1] == "Flightwatch check-in: running, no sales yet"
    assert "Dublin: $719, 27% under its usual $983" in sent[0][3]


def test_not_before_10_or_on_other_days(monkeypatch):
    db = _db()
    sent = _patch(monkeypatch, db, datetime(2026, 11, 29, 9, 30))
    digest.run()
    sent2 = _patch(monkeypatch, db, datetime(2026, 11, 27, 10, 30))  # Friday
    digest.run()
    assert sent == [] and sent2 == []


def test_warns_when_no_checks_ran(monkeypatch):
    db = _db()
    db.execute("DELETE FROM prices")
    sent = _patch(monkeypatch, db, datetime(2026, 12, 2, 10, 15))  # Wednesday
    digest.run()
    assert sent[0][1] == "Flightwatch hasn't checked prices lately"
