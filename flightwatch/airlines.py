"""Airline names and matching. Codes are the 2-letter IATA codes Google uses."""

NAMES = {
    "DL": "Delta", "AA": "American", "UA": "United", "WN": "Southwest", "B6": "JetBlue",
    "AS": "Alaska", "NK": "Spirit", "F9": "Frontier", "AC": "Air Canada", "AF": "Air France",
    "KL": "KLM", "VS": "Virgin Atlantic", "BA": "British Airways", "IB": "Iberia",
    "EI": "Aer Lingus", "LH": "Lufthansa", "LX": "Swiss", "AZ": "ITA Airways",
    "TK": "Turkish", "QR": "Qatar", "EK": "Emirates", "KE": "Korean Air", "NH": "ANA",
    "JL": "Japan Airlines", "SQ": "Singapore Airlines", "CX": "Cathay Pacific",
    "BR": "EVA Air", "CI": "China Airlines", "TG": "Thai", "AM": "Aeromexico",
}


def name(code):
    return NAMES.get(code, code)


def parse(value):
    """'DL, ua' -> ['DL', 'UA']"""
    return [c.strip().upper() for c in (value or "").replace(";", ",").split(",") if c.strip()]


def matches(option, wanted):
    """An itinerary counts for an airline if any leg is on it.
    So 'Delta' includes Delta plus a partner leg, like Delta then Korean Air."""
    return any(a in wanted for a in option["airlines"])


def describe(option):
    """'Delta, nonstop' or 'Delta and Korean Air, 1 stop'"""
    seen = []
    for a in option["airlines"]:
        if a not in seen:
            seen.append(a)
    who = " and ".join(name(a) for a in seen[:2]) + (" and others" if len(seen) > 2 else "")
    stops = option.get("stops")
    how = "nonstop" if stops == 0 else f"{stops} stop" + ("s" if stops and stops > 1 else "") if stops is not None else ""
    return ", ".join(x for x in (who, how) if x)
