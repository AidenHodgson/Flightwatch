# Flightwatch

Free flight deal alerts for you and a few friends. Flightwatch checks Google Flights once a day for the routes you care about, learns what each route normally costs, and emails you when a fare drops well below normal.

It's a small, open-source take on paid deal services like Thrifty Traveler or Going. It won't catch everything a human deal team does (see [Limits](#limits)), but it costs nothing to run.

## How it works

1. **You add people and routes.** Each person has an email and a list of routes, like ATL to Rome for 5 to 10 nights, any time in the next 6 months.
2. **A daily check runs on GitHub Actions.** Every unique route is searched once, even if several people watch it. Departure dates are sampled every 10 days across the window.
3. **Prices are saved** to a free Cloudflare D1 database, so Flightwatch builds a price history for each route.
4. **Deals get emailed.** A fare counts as a deal when it's at least 30% below the route's normal (median) price over the last 60 days, or under a max price you set. Each person gets one email with all their deals, and the same deal isn't sent twice in a week unless the price drops another 10%.

Prices come from [fli](https://github.com/punitarani/fli), an open-source library that reads Google Flights the way a browser does. There's no official Google Flights API, so if Google changes its site, a run may fail until fli is updated.

## Setup

You need a GitHub account, a free Cloudflare account, and an email account to send from.

### 1. Copy the repo

Fork this repo (or use it as a template). The code is public, but your friends' emails and routes live in your own database, never in the repo.

### 2. Create the database

In Cloudflare, go to **Storage & Databases > D1**, create a database named `flight-watch`, open its **Console**, and paste in everything from [`schema.sql`](schema.sql).

Then create an API token at **My Profile > API Tokens > Create Token > Custom token** with the permission **Account > D1 > Edit**.

### 3. Set up email

Pick one:

- **Gmail (easiest):** turn on 2-step verification, then create an [app password](https://myaccount.google.com/apppasswords). Use `smtp.gmail.com`, port `587`, your Gmail address as the user, and the app password.
- **Resend:** create an API key at [resend.com](https://resend.com). To email anyone besides yourself you'll need to verify a domain you own.

### 4. Add GitHub secrets

In your repo, go to **Settings > Secrets and variables > Actions** and add:

| Secret | What it is |
|---|---|
| `CF_ACCOUNT_ID` | Your Cloudflare account ID (on the right side of the Cloudflare dashboard) |
| `CF_API_TOKEN` | The D1 API token from step 2 |
| `D1_DATABASE_ID` | The database ID shown on the D1 database page |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` | Gmail or other SMTP settings, **or** |
| `RESEND_API_KEY` | If using Resend instead |
| `FROM_EMAIL` | The address alerts come from (optional with Gmail) |

Optional: add a repo **variable** `SAMPLE_EVERY_DAYS` (default `10`). Lower means more dates checked and a slower run.

### 5. Add people and routes

On your computer:

```bash
pip install -r requirements.txt
export CF_ACCOUNT_ID=... CF_API_TOKEN=... D1_DATABASE_ID=...

python -m flightwatch.manage add-user "Dad" dad@example.com
python -m flightwatch.manage add-watch dad@example.com ATL FCO LHR CDG --nights 5-10 --months 6
python -m flightwatch.manage list
python -m flightwatch.manage pause-watch 3
```

`add-watch` options:

- `--cabin` ECONOMY (default), PREMIUM_ECONOMY, BUSINESS or FIRST
- `--nights` trip length range, default `5-10` (searched at the midpoint)
- `--months` how far ahead to look, default `6`
- `--drop` how far below normal counts as a deal, default `30` (percent)
- `--max-price` always alert under this price, even before there's history

### 6. Test it

Go to **Actions > Check flights > Run workflow** and tick **Email everyone their cheapest fares**. Everyone gets a test email with the cheapest fare found for each route. After that it runs on its own every morning.

The first run also builds each route's price history, so real deal alerts can start from day two.

## Running locally

```bash
python -m flightwatch.main            # normal run
python -m flightwatch.main --report   # test run that emails cheapest fares
```

Without email settings, emails are printed to the screen instead of sent.

## Tests

```bash
pip install pytest
python -m pytest
```

## Limits

- **Cash fares only.** No points or miles (award) deals.
- **Sampled dates.** It checks a date every 10 days, so it can miss a one-day sale in between.
- **Mistake fares** usually vanish within hours. A daily check will catch some, but not most.
- **Round trips, 1 adult, one stop or fewer**, from a single airport per watch.
- **Scraping, not an API.** Keep it to personal use at small volume.

## License

MIT
