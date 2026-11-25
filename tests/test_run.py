"""End-to-end run with a local SQLite stand-in for D1 and fake prices."""
import sqlite3
from pathlib import Path

from flightwatch import main


class FakeD1:
    def __init__(self):
        self.c = sqlite3.connect(":memory:")
        self.c.row_factory = sqlite3.Row
        self.c.executescript(Path(__file__).parent.parent.joinpath("schema.sql").read_text())

    def query(self, sql, params=None):
        cur = self.c.execute(sql, params or [])
        self.c.commit()
        return [dict(r) for r in cur.fetchall()]

    execute = query


class FakeChecker:
    def __init__(self, price):
        self.price = price

    def cheapest_round_trip(self, *a):
        return self.price


def test_run_sends_deal_once(monkeypatch):
    db = FakeD1()
    db.execute("INSERT INTO users (name, email) VALUES ('Dad', 'dad@x.com')")
    db.execute("INSERT INTO watches (user_id, origin, destination) VALUES (1, 'ATL', 'FCO')")
    for _ in range(20):
        db.execute("INSERT INTO prices (origin,destination,cabin,depart_date,return_date,price) "
                   "VALUES ('ATL','FCO','ECONOMY','2027-01-01','2027-01-08',900)")
    sent = []
    monkeypatch.setattr(main, "D1", lambda: db)
    monkeypatch.setattr(main.mailer, "send", lambda *a: sent.append(a))

    monkeypatch.setattr(main, "PriceChecker", lambda: FakeChecker(880))
    main.run()
    assert sent == []  # normal price, no alert

    monkeypatch.setattr(main, "PriceChecker", lambda: FakeChecker(550))
    main.run()
    assert len(sent) == 1 and "$550" in sent[0][3]

    main.run()
    assert len(sent) == 1  # same deal not re-sent

    main.run(report=True)
    assert len(sent) == 2 and "test report" in sent[1][1]


def test_basecamp_user_and_manage_link(monkeypatch):
    db = FakeD1()
    db.execute("INSERT INTO users (name, email, token, basecamp) VALUES ('Aiden', 'a@x.com', 'tok123', 1)")
    db.execute("INSERT INTO users (name, email, token) VALUES ('Dad', 'dad@x.com', 'dadtok')")
    db.execute("INSERT INTO watches (user_id, origin, destination, max_price) VALUES (1, 'ATL', 'LHR', 700)")
    db.execute("INSERT INTO watches (user_id, origin, destination, max_price) VALUES (2, 'ATL', 'LHR', 700)")
    posted, sent = [], []
    monkeypatch.setenv("SITE_URL", "https://fw.example.com")
    monkeypatch.setattr(main, "D1", lambda: db)
    monkeypatch.setattr(main, "PriceChecker", lambda: FakeChecker(650))
    monkeypatch.setattr(main.notify, "enabled", lambda: True)
    monkeypatch.setattr(main.notify, "post_basecamp", lambda d, url: posted.append((d, url)))
    monkeypatch.setattr(main.mailer, "send", lambda *a: sent.append(a))
    main.run()
    assert len(posted) == 1 and posted[0][1] == "https://fw.example.com/u/tok123"
    assert len(sent) == 1 and sent[0][0] == "dad@x.com" and "/u/dadtok" in sent[0][3]
