-- Flightwatch schema for Cloudflare D1 (SQLite)
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE,
  active INTEGER NOT NULL DEFAULT 1,
  token TEXT,                      -- secret for their settings page link
  basecamp INTEGER NOT NULL DEFAULT 0, -- 1 = also ping a Basecamp app (optional)
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_token ON users(token);

-- One row per route a person wants to watch
CREATE TABLE IF NOT EXISTS watches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  origin TEXT NOT NULL,            -- IATA code, e.g. ATL
  destination TEXT NOT NULL,       -- IATA code, e.g. FCO
  cabin TEXT NOT NULL DEFAULT 'ECONOMY',
  min_nights INTEGER NOT NULL DEFAULT 5,
  max_nights INTEGER NOT NULL DEFAULT 10,
  months_ahead INTEGER NOT NULL DEFAULT 6,
  max_price INTEGER,               -- always alert under this price (optional)
  drop_pct INTEGER NOT NULL DEFAULT 30, -- alert when this % below normal
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Every price we see, shared across users
CREATE TABLE IF NOT EXISTS prices (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  origin TEXT NOT NULL,
  destination TEXT NOT NULL,
  cabin TEXT NOT NULL,
  depart_date TEXT NOT NULL,
  return_date TEXT NOT NULL,
  price INTEGER NOT NULL,
  typical INTEGER,                 -- Google's typical price for this search
  range_low INTEGER,               -- Google's usual price range
  range_high INTEGER,
  airline TEXT,
  stops INTEGER,
  checked_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_prices_route ON prices(origin, destination, cabin, checked_at);

-- Alerts already sent, so nobody gets the same deal twice
CREATE TABLE IF NOT EXISTS alerts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  watch_id INTEGER NOT NULL REFERENCES watches(id) ON DELETE CASCADE,
  depart_date TEXT NOT NULL,
  return_date TEXT NOT NULL,
  price INTEGER NOT NULL,
  sent_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_alerts_watch ON alerts(watch_id, sent_at);
