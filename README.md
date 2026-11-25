# Flightwatch

Free flight deal alerts for you and a few friends. Flightwatch checks Google Flights every 3 hours for the routes you care about, learns what each route normally costs, and emails you when a fare drops well below normal.

It's a small, open-source take on paid deal services like Thrifty Traveler or Going. It won't catch everything a human deal team does (see [Limits](#limits)), but it costs nothing to run.

## How it works

1. **You add people, they pick routes.** You add someone from the admin page and send them their private link. On their settings page they add routes (like ATL to Rome for 5 to 10 nights, any time in the next 6 months), pick a cabin, set how big a drop counts as a deal, set a max price, or pause alerts.
2. **A check runs every 3 hours on GitHub Actions.** Every unique route is searched once, even if several people watch it. Departure dates are sampled every 10 days across the window.
3. **Prices are saved** to a free Cloudflare D1 database, so Flightwatch builds a price history for each route.
4. **Only sales get emailed**, each with a "Manage your routes" button that opens that person's settings page. A fare counts as a sale when it's **below the usual price range Google shows for that trip and at least 30% under its typical price** (the same numbers behind Google Flights' "prices are currently low" note). Because Google supplies those numbers on every search, sales can be spotted from the very first run. If Google ever leaves them out, Flightwatch falls back to its own price history, and only calls something a sale once a route has 3 days of history. Each person gets one email with all their sales, and the same deal isn't sent twice in a week unless the price drops another 10%. (You can also set a max price per route if you want an alert whenever it's under a number, sale or not. It's off by default.)

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

Go to **Actions > Check flights > Run workflow** and tick **Also send everyone a short test email**. Everyone gets a short "Flightwatch is set up" note (no fares) so you know email works. After that it runs on its own every 3 hours. A deal only gets sent once a week unless the price drops another 10%, so frequent checks won't spam anyone.

Sale alerts can start from the first run, since Google supplies each trip's typical price.

## Airlines

Each person can pick airlines on their settings page. A trip counts for an airline if any flight in it is on that airline, so Delta includes Delta plus a partner leg like KLM or Korean Air. Two modes:

- **Prefer** (default): only those airlines, except on routes they don't fly on any date checked, where the best other airline is shown and labeled as such.
- **Only**: those airlines, always.

Google's typical price is for the whole route (all airlines), so a sale on your airline means it's cheap compared to everyone, not just to itself.

## What a sale email shows

For each route: the sale price next to the usual price, percent off and dollars saved, the airline and stops, the cheapest dates, **when the sale runs** (for example "February only" or "mid-January to late-February (this winter)") and how many of the checked departure dates are on sale, plus Google's usual range for the trip. Sales also need to save at least $150, so small dips never send an email.

## If email stops working

Prices are always saved, and any sale that couldn't be sent waits and goes out on the next run that can send. Flightwatch also opens one GitHub issue called "Flightwatch can't send email" with the exact reason and the waiting deals. GitHub notifies you about it, and it closes itself once email works again. The issue never includes anyone's email address.

The usual Gmail problem is "rejected the login" (error 535). That means the app password doesn't belong to the `SMTP_USER` account. App passwords are tied to whichever Google account was signed in when you made it, so on a phone that's signed in to several accounts, switch to the sender account first (tap your profile picture at myaccount.google.com), make sure 2-Step Verification is on, create the app password, and update `SMTP_PASSWORD`.

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
python -m flightwatch.main --test     # also sends everyone a short setup email
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
