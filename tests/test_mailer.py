import smtplib

import pytest

from flightwatch import mailer


class FakeSMTP:
    """Acts like Gmail rejecting a bad app password."""
    accept = False
    sent = []

    def __init__(self, *a, **k):
        pass

    def ehlo(self):
        return 250, b"ok"

    def starttls(self):
        return 220, b"ok"

    def auth_plain(self, challenge=None):
        return ""

    def auth(self, mech, fn, **k):
        if not FakeSMTP.accept:
            raise smtplib.SMTPAuthenticationError(535, b"5.7.8 Username and Password not accepted")

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def smtp(monkeypatch):
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", FakeSMTP)
    for k, v in {"SMTP_HOST": "smtp.gmail.com", "SMTP_USER": "sender@example.com",
                 "SMTP_PASSWORD": "abcd efgh ijkl mnop\n"}.items():
        monkeypatch.setenv(k, v)
    FakeSMTP.sent = []
    return FakeSMTP


def test_bad_password_gives_clear_error(smtp):
    smtp.accept = False
    with pytest.raises(mailer.EmailLoginError, match="app password"):
        mailer.send("to@example.com", "s", "<p>h</p>", "t")


def test_good_password_sends(smtp):
    smtp.accept = True
    mailer.send("to@example.com", "s", "<p>h</p>", "t")
    assert len(smtp.sent) == 1


def test_empty_password(smtp, monkeypatch):
    monkeypatch.setenv("SMTP_PASSWORD", "  ")
    with pytest.raises(mailer.EmailLoginError, match="empty"):
        mailer.send("to@example.com", "s", "<p>h</p>", "t")
