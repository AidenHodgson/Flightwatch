# Flightwatch

Free flight deal alerts for you and a few friends. Flightwatch checks Google Flights every 3 hours for the routes you care about, learns what each route normally costs, and emails you when a fare drops well below normal.

It's a small, open-source take on paid deal services like Thrifty Traveler or Going. It won't catch everything a human deal team does (see [Limits](#limits)), but it costs nothing to run.

## How it works

1. **You add people, they pick routes.** You add someone from the admin page and send them their private link. On their settings page they add routes (like ATL to Rome for 5 to 10 nights, any time in the next 6 months), pick a cabin, set how big a drop counts as a deal, set a max price, or pause alerts.
2. **A check runs every 3 hours on GitHub Actions.** Every unique route is searched once, even if several people watch it. Departure dates are sampled every 10 days across the window.
3. **Prices are saved** to a free Cloudflare D1 database, so Flightwatch builds a price history for each route.
4. **Deals get emailed**, each with a "Manage your routes" button that opens that person's settings page. A fare counts as a deal when it's at least 30% below the route's normal (median) price over the last 60 days, or under a max price you set. Each person gets one email with all their deals, and the same deal isn't sent twice in a week unless the price drops another 10%.

Prices come from [fli](https://github.com/punitarani/fli), an open-source library that reads Google Flights the way a browser does. There's no official Google Flights API, so if Google changes its site, a run may fail until fli is updated.

## Setup

You need a GitHub account, a free Cloudflare account, and an email account to send from.

### 1. Copy the repo

Fork this repo (or use it as a template). The code is public, but your friends' emails and routes live in your own database, never in the repo.

### 2. Create the database

In Cloudflare, go to **Storage & Databases > D1**, create a database named `flight-watch`, open its **Console**, and paste in everything from [`schema.sql`](schema.sql).

Then create an API token at **My Profile > API Tokens > Create Token > Custom token** with two permissions: **Account > D1 > Edit** and **Account > Workers Scripts > Edit** (the second one lets GitHub deploy the settings page).

### 3. Set up email

Pick one:

- **Gmail (easiest, free, no extra service):** make a dedicated Gmail account (like `yourname.flightwatch@gmail.com`), turn on 2-step verification, then create an [app password](https://myaccount.google.com/apppasswords). Use `smtp.gmail.com`, port `587`, that Gmail address as the user, and the app password. Gmail allows about 500 emails a day.
- **Resend:** create an API key at [resend.com](https://resend.com). To email anyone besides yourself you'll need to verify a domain you own.

### 4. Add GitHub secrets

The settings that aren't secret (database ID, email server, sender address, site URL) sit at the top of the `env:` block in `.github/workflows/check.yml`. Change those to yours. Anything you also add as a secret or variable with the same name wins over the file.


In your repo, go to **Settings > Secrets and variables > Actions** and add:

| Secret | What it is |
|---|---|
| `CF_ACCOUNT_ID` | Your Cloudflare account ID (on the right side of the Cloudflare dashboard) |
| `CF_API_TOKEN` | The D1 API token from step 2 |
| `D1_DATABASE_ID` | The database ID shown on the D1 database page |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` | Gmail or other SMTP settings, **or** |
| `RESEND_API_KEY` | If using Resend instead |
| `FROM_EMAIL` | The address alerts come from (optional with Gmail) |
| `BASECAMP_URL`, `BASECAMP_POST_TOKEN` | Optional. Sends alerts for users marked "Basecamp" to a [Basecamp](#basecamp-pings-optional) app instead of email |

Also add a repo **variable** (same page, Variables tab) named `SITE_URL` once the settings page is live (step 5), like `https://flightwatch.yourname.workers.dev`. It's used for the links in emails.

Optional: add a repo **variable** `SAMPLE_EVERY_DAYS` (default `10`). Lower means more dates checked and a slower run.

### 5. Put the settings page online

Go to **Actions > Deploy settings page > Run workflow**. It deploys the page to Cloudflare Workers, a free hosting service, and the run log shows its address (something like `https://flightwatch.yourname.workers.dev`). Save that as the `SITE_URL` variable from step 4.

Then give the admin page a password. Make a long random one (`python -c "import secrets; print(secrets.token_urlsafe(24))"`) and add it in Cloudflare under **Workers & Pages > flightwatch > Settings > Variables and Secrets** as a secret named `ADMIN_KEY` (or run `cd web && npx wrangler secret put ADMIN_KEY`). It stays set across deploys.

It redeploys on its own whenever anything in `web/` changes.

### 6. Add people

Open `https://<your SITE_URL>/admin/<your ADMIN_KEY>`. Bookmark it, since it's your admin page. From there you can:

- Add someone by name, email and home airport. They start with 14 starter routes (8 in Europe for 5 to 10 nights, 6 in Asia for 7 to 14 nights) unless you untick the box
- Copy their private settings link, or tap "Email it to them"
- Make a new link if someone's gets shared around (the old one stops working)

Each person then opens their link and adds their own routes. Anyone with a link can edit that person's routes, so treat it like a password. People can only get in if you add them.

**Or from the command line:**

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

### 7. Test it

Go to **Actions > Check flights > Run workflow** and tick **Email everyone their cheapest fares**. Everyone gets a test email with the cheapest fare found for each route. After that it runs on its own every 3 hours. A deal only gets sent once a week unless the price drops another 10%, so frequent checks won't spam anyone.

The first run also builds each route's price history, so real deal alerts can start from day two.

## Basecamp pings (optional)

[Basecamp](https://github.com/AidenHodgson/basecamp) is a personal message board app. If you mark a person "Basecamp" on the admin page and set `BASECAMP_URL` and `BASECAMP_POST_TOKEN`, their deals post there as alerts (which push to their phone) instead of email. If the post fails, it falls back to email. Ignore this if you don't use Basecamp.

## Running it on your own server

GitHub Actions is the easy default, but you can run the checker anywhere with Python, like a home server:

```bash
pip install -r requirements.txt
# put the same secrets in a .env file or your shell, then add a cron job:
17 */3 * * * cd /path/to/Flightwatch && python -m flightwatch.main
```

Turn off the GitHub schedule (delete the `schedule:` lines in `.github/workflows/check.yml`) so both don't run.

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

To try the settings page locally:

```bash
cd web && npm install
npx wrangler d1 execute flight-watch --local --file ../schema.sql
npx wrangler dev --local --var ADMIN_KEY:test
# then open http://localhost:8787/admin/test
```

## Limits

- **Cash fares only.** No points or miles (award) deals.
- **Not instant.** Checks run every 3 hours, and GitHub sometimes starts them late.
- **Sampled dates.** It checks a date every 10 days, so it can miss a one-day sale in between.
- **Mistake fares** usually vanish within hours. A daily check will catch some, but not most.
- **Round trips, 1 adult, one stop or fewer**, from a single airport per watch.
- **Scraping, not an API.** Keep it to personal use at small volume.

## License

MIT
