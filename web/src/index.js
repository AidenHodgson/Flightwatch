// Flightwatch settings page. A Cloudflare Worker that reads and writes the D1 database.
//   /u/<token>        a person's own settings page (link is in every alert email)
//   /admin/<ADMIN_KEY> add people and copy their links

const CABINS = ["ECONOMY", "PREMIUM_ECONOMY", "BUSINESS", "FIRST"];
const CABIN_NAMES = { ECONOMY: "Economy", PREMIUM_ECONOMY: "Premium economy", BUSINESS: "Business", FIRST: "First" };
const AIRPORTS = [
  ["ATL", "Atlanta"], ["BOS", "Boston"], ["CLT", "Charlotte"], ["ORD", "Chicago"], ["DFW", "Dallas"],
  ["DEN", "Denver"], ["DTW", "Detroit"], ["IAH", "Houston"], ["LAS", "Las Vegas"], ["LAX", "Los Angeles"],
  ["MIA", "Miami"], ["MSP", "Minneapolis"], ["BNA", "Nashville"], ["MSY", "New Orleans"], ["JFK", "New York JFK"],
  ["EWR", "Newark"], ["MCO", "Orlando"], ["PHL", "Philadelphia"], ["PHX", "Phoenix"], ["SAN", "San Diego"],
  ["SFO", "San Francisco"], ["SEA", "Seattle"], ["TPA", "Tampa"], ["DCA", "Washington Reagan"], ["IAD", "Washington Dulles"],
  ["HNL", "Honolulu"], ["OGG", "Maui"], ["ANC", "Anchorage"], ["SJU", "San Juan"],
  ["CUN", "Cancun"], ["MEX", "Mexico City"], ["SJO", "San Jose, Costa Rica"], ["LIR", "Liberia, Costa Rica"],
  ["NAS", "Nassau"], ["MBJ", "Montego Bay"], ["PUJ", "Punta Cana"], ["AUA", "Aruba"], ["BOG", "Bogota"],
  ["LIM", "Lima"], ["GRU", "Sao Paulo"], ["EZE", "Buenos Aires"], ["YYZ", "Toronto"], ["YVR", "Vancouver"],
  ["LHR", "London"], ["DUB", "Dublin"], ["EDI", "Edinburgh"], ["CDG", "Paris"], ["AMS", "Amsterdam"],
  ["FRA", "Frankfurt"], ["MUC", "Munich"], ["ZRH", "Zurich"], ["FCO", "Rome"], ["MXP", "Milan"],
  ["VCE", "Venice"], ["BCN", "Barcelona"], ["MAD", "Madrid"], ["LIS", "Lisbon"], ["ATH", "Athens, Greece"],
  ["IST", "Istanbul"], ["CPH", "Copenhagen"], ["KEF", "Reykjavik"], ["PRG", "Prague"], ["VIE", "Vienna"],
  ["DXB", "Dubai"], ["DOH", "Doha"], ["TLV", "Tel Aviv"], ["CPT", "Cape Town"], ["NRT", "Tokyo Narita"],
  ["HND", "Tokyo Haneda"], ["ICN", "Seoul"], ["HKG", "Hong Kong"], ["SIN", "Singapore"], ["BKK", "Bangkok"],
  ["SYD", "Sydney"], ["AKL", "Auckland"],
];
const AIRPORT_NAME = Object.fromEntries(AIRPORTS);
const AIRLINES = [
  ["DL", "Delta"], ["AA", "American"], ["UA", "United"], ["WN", "Southwest"], ["B6", "JetBlue"],
  ["AS", "Alaska"], ["AC", "Air Canada"], ["AF", "Air France"], ["KL", "KLM"], ["VS", "Virgin Atlantic"],
  ["BA", "British Airways"], ["LH", "Lufthansa"], ["TK", "Turkish"], ["QR", "Qatar"], ["EK", "Emirates"],
  ["KE", "Korean Air"], ["NH", "ANA"], ["JL", "Japan Airlines"], ["SQ", "Singapore Airlines"], ["CX", "Cathay Pacific"],
];
const AIRLINE_CODES = new Set(AIRLINES.map(([c]) => c));

// Starter routes every new person gets (they can remove any of them).
// Keep in sync with DEFAULT_ROUTES in flightwatch/manage.py.
const DEFAULT_ORIGIN = "ATL";
const DEFAULT_ROUTES = [
  // Europe: shorter trips
  ...["LHR", "CDG", "FCO", "AMS", "BCN", "MAD", "FRA", "DUB"].map((d) => [d, 5, 10]),
  // Asia: longer trips
  ...["HND", "ICN", "HKG", "SIN", "BKK", "TPE"].map((d) => [d, 7, 14]),
];

function starterInserts(env, userId, origin = DEFAULT_ORIGIN) {
  return DEFAULT_ROUTES.filter(([d]) => d !== origin).map(([d, lo, hi]) =>
    env.DB.prepare("INSERT INTO watches (user_id, origin, destination, min_nights, max_nights) VALUES (?, ?, ?, ?, ?)")
      .bind(userId, origin, d, lo, hi));
}

export default {
  async fetch(request, env) {
    try {
      return await route(request, env);
    } catch (e) {
      console.error(e);
      return page("Something went wrong", `<p>Sorry, that didn't work. Try again in a minute.</p>`, 500);
    }
  },
};

async function route(request, env) {
  const url = new URL(request.url);
  const parts = url.pathname.split("/").filter(Boolean);
  const method = request.method;

  if (parts.length === 0) return home();

  if (parts[0] === "u" && parts[1]) {
    const user = await env.DB.prepare("SELECT * FROM users WHERE token = ?").bind(parts[1]).first();
    if (!user) return page("Link not found", `<p>This link doesn't work. Ask whoever runs Flightwatch for a new one.</p>`, 404);
    const base = `/u/${parts[1]}`;
    if (method === "GET" && parts.length === 2) return userPage(env, user, base, url.searchParams.get("m"));
    if (method === "POST") {
      const form = await readForm(request);
      const action = parts.slice(2).join("/");
      const msg = await userAction(env, user, action, form);
      return redirect(`${base}?m=${encodeURIComponent(msg)}`);
    }
  }

  if (parts[0] === "admin") {
    if (!env.ADMIN_KEY || parts[1] !== env.ADMIN_KEY) return page("Not found", "<p>Not found.</p>", 404);
    const base = `/admin/${parts[1]}`;
    if (method === "GET") return adminPage(env, url, base, url.searchParams.get("m"));
    if (method === "POST" && parts[2] === "user") {
      const form = await readForm(request);
      const name = (form.get("name") || "").toString().trim();
      const email = (form.get("email") || "").toString().trim().toLowerCase();
      if (!name || !email.includes("@")) return redirect(`${base}?m=${encodeURIComponent("Need a name and email")}`);
      const token = randomToken();
      let userId;
      try {
        const r = await env.DB.prepare("INSERT INTO users (name, email, token, basecamp) VALUES (?, ?, ?, ?)")
          .bind(name, email, token, form.get("basecamp") ? 1 : 0).run();
        userId = r.meta.last_row_id;
      } catch {
        return redirect(`${base}?m=${encodeURIComponent("That email is already added")}`);
      }
      const origin = code(form.get("origin")) || DEFAULT_ORIGIN;
      if (form.get("starter")) await env.DB.batch(starterInserts(env, userId, origin));
      return redirect(`${base}?m=${encodeURIComponent(`Added ${name}${form.get("starter") ? " with the starter routes" : ""}`)}`);
    }
    if (method === "POST" && parts[2] === "link" && parts[3]) {
      await env.DB.prepare("UPDATE users SET token = ? WHERE id = ?").bind(randomToken(), parts[3]).run();
      return redirect(`${base}?m=${encodeURIComponent("New link made. The old one no longer works.")}`);
    }
  }

  return page("Not found", "<p>Not found.</p>", 404);
}

// ---------- person's page ----------

async function userPage(env, user, base, msg) {
  const { results: watches } = await env.DB.prepare(
    "SELECT * FROM watches WHERE user_id = ? ORDER BY destination, id"
  ).bind(user.id).all();
  const { results: lows } = await env.DB.prepare(
    `SELECT origin, destination, cabin, MIN(price) AS low, COUNT(*) AS n FROM prices
     WHERE checked_at >= datetime('now', '-2 days') GROUP BY origin, destination, cabin`
  ).all();
  const lowFor = Object.fromEntries(lows.map((r) => [`${r.origin}-${r.destination}-${r.cabin}`, r.low]));

  const rows = watches.map((w) => watchCard(w, base, lowFor[`${w.origin}-${w.destination}-${w.cabin}`])).join("");
  const body = `
    ${msg ? `<div class="note">${esc(msg)}</div>` : ""}
    <p class="muted">Hi ${esc(user.name)}. Flightwatch checks your routes every few hours and emails you when a fare drops well below normal.</p>

    <section class="card">
      <div class="row between">
        <div><b>Alerts are ${user.active ? "on" : "paused"}</b><div class="muted small">${esc(user.email)}</div></div>
        <form method="post" action="${base}/alerts"><button class="${user.active ? "ghost" : ""}">${user.active ? "Pause all" : "Turn back on"}</button></form>
      </div>
      <div class="row between" style="margin-top:12px;padding-top:12px;border-top:1px solid var(--line)">
        <div><b>Check-in email ${user.digest ? "on" : "off"}</b><div class="muted small">Sunday and Wednesday at 10 AM: proof it's running, plus the closest fares</div></div>
        <form method="post" action="${base}/digest"><button class="ghost small">${user.digest ? "Turn off" : "Turn on"}</button></form>
      </div>
    </section>

    <h2>Airlines</h2>
    ${airlineForm(user, base)}

    <h2>Your routes</h2>
    ${rows || `<div class="card"><p class="muted">No routes yet. Add your own below, or start with ${DEFAULT_ROUTES.length} popular ones in Europe and Asia.</p>
      <form method="post" action="${base}/starter" class="row"><input name="origin" list="airports" value="${DEFAULT_ORIGIN}" maxlength="3" class="code" aria-label="Home airport"><button>Add starter routes</button></form></div>`}

    <h2>Add routes</h2>
    <form method="post" action="${base}/add" class="card stack">
      <label>From <input name="origin" list="airports" placeholder="ATL" required maxlength="3" class="code"></label>
      <label>To <span class="muted small">(one or more codes, separated by commas)</span>
        <input name="destinations" list="airports" placeholder="FCO, LHR, CDG" required></label>
      ${optionFields({ cabin: "ECONOMY", min_nights: 5, max_nights: 10, months_ahead: 6, drop_pct: 30, max_price: "" })}
      <button>Add</button>
    </form>
    <datalist id="airports">${AIRPORTS.map(([c, n]) => `<option value="${c}">${n}</option>`).join("")}</datalist>
    <p class="muted small">Not seeing your airport? Any 3-letter airport code works. Search "airport code" plus the city to find it.</p>`;
  return page("Your Flightwatch", body);
}

function airlineForm(user, base) {
  const chosen = new Set((user.airlines || "").split(",").map((x) => x.trim()).filter(Boolean));
  const mode = user.airline_mode || "prefer";
  const summary = chosen.size
    ? `${[...chosen].map((c) => (AIRLINES.find(([k]) => k === c) || [c, c])[1]).join(", ")}${mode === "only" ? " only" : ", others if needed"}`
    : "Any airline";
  return `
    <details class="card">
      <summary><div><b>${esc(summary)}</b><div class="muted small">Which airlines count for your alerts</div></div></summary>
      <form method="post" action="${base}/airlines" class="stack">
        <div class="chips">${AIRLINES.map(([c, n]) => `<label class="chip"><input type="checkbox" name="airline" value="${c}"${chosen.has(c) ? " checked" : ""}> ${n}</label>`).join("")}</div>
        <label class="row nogap"><input type="radio" name="mode" value="prefer"${mode !== "only" ? " checked" : ""} style="width:auto"> Use these, but show other airlines on routes they don't fly</label>
        <label class="row nogap"><input type="radio" name="mode" value="only"${mode === "only" ? " checked" : ""} style="width:auto"> Only these airlines, always</label>
        <p class="muted small">A trip counts if any flight in it is on your airline, so Delta includes Delta plus a partner like KLM or Korean Air. Leave everything unticked for any airline.</p>
        <button>Save airlines</button>
      </form>
    </details>`;
}

function watchCard(w, base, low) {
  const name = (c) => (AIRPORT_NAME[c] ? `${c} <span class="muted">${AIRPORT_NAME[c]}</span>` : c);
  return `
    <details class="card${w.active ? "" : " paused"}">
      <summary>
        <div><b>${name(w.origin)} &rarr; ${name(w.destination)}</b>
          <div class="muted small">${CABIN_NAMES[w.cabin] || w.cabin}, ${w.min_nights}-${w.max_nights} nights, next ${w.months_ahead} months${w.active ? "" : " &middot; paused"}</div></div>
        <div class="price">${low ? `$${low.toLocaleString("en-US")}<div class="muted small">lowest lately</div>` : ""}</div>
      </summary>
      <form method="post" action="${base}/watch/${w.id}" class="stack">
        ${optionFields(w)}
        <div class="row">
          <button>Save</button>
          <button formaction="${base}/watch/${w.id}/toggle" class="ghost">${w.active ? "Pause" : "Resume"}</button>
          <button formaction="${base}/watch/${w.id}/delete" class="ghost danger">Remove</button>
        </div>
      </form>
    </details>`;
}

function optionFields(w) {
  return `
    <label>Cabin <select name="cabin">${CABINS.map((c) => `<option value="${c}"${c === w.cabin ? " selected" : ""}>${CABIN_NAMES[c]}</option>`).join("")}</select></label>
    <div class="row">
      <label>Shortest trip <input name="min_nights" type="number" min="1" max="30" value="${w.min_nights}"> nights</label>
      <label>Longest trip <input name="max_nights" type="number" min="1" max="30" value="${w.max_nights}"> nights</label>
    </div>
    <label>Look this far ahead <select name="months_ahead">${[1, 2, 3, 4, 6, 9, 11].map((m) => `<option value="${m}"${m == w.months_ahead ? " selected" : ""}>${m} month${m > 1 ? "s" : ""}</option>`).join("")}</select></label>
    <label>Alert me when it's this much below normal
      <select name="drop_pct">${[15, 20, 25, 30, 40, 50].map((p) => `<option value="${p}"${p == w.drop_pct ? " selected" : ""}>${p}%</option>`).join("")}</select></label>
    <label>Or whenever it's under <span class="muted small">(optional)</span>
      <span class="row nogap"><span class="prefix">$</span><input name="max_price" type="number" min="1" value="${w.max_price ?? ""}" placeholder="no limit"></span></label>`;
}

function readOptions(form) {
  const int = (k, d, lo, hi) => {
    const v = parseInt(form.get(k), 10);
    return Number.isFinite(v) ? Math.min(hi, Math.max(lo, v)) : d;
  };
  let min = int("min_nights", 5, 1, 30), max = int("max_nights", 10, 1, 30);
  if (min > max) [min, max] = [max, min];
  const cabin = CABINS.includes(form.get("cabin")) ? form.get("cabin") : "ECONOMY";
  const mp = parseInt(form.get("max_price"), 10);
  return {
    cabin, min, max,
    months: int("months_ahead", 6, 1, 11),
    drop: int("drop_pct", 30, 5, 80),
    maxPrice: Number.isFinite(mp) && mp > 0 ? mp : null,
  };
}

async function userAction(env, user, action, form) {
  if (action === "alerts") {
    await env.DB.prepare("UPDATE users SET active = ? WHERE id = ?").bind(user.active ? 0 : 1, user.id).run();
    return user.active ? "Alerts paused" : "Alerts are back on";
  }
  if (action === "digest") {
    await env.DB.prepare("UPDATE users SET digest = ? WHERE id = ?").bind(user.digest ? 0 : 1, user.id).run();
    return user.digest ? "Check-in emails off" : "Check-in emails on";
  }
  if (action === "airlines") {
    const picked = form.getAll("airline").map(String).filter((c) => AIRLINE_CODES.has(c));
    const mode = form.get("mode") === "only" ? "only" : "prefer";
    await env.DB.prepare("UPDATE users SET airlines = ?, airline_mode = ? WHERE id = ?")
      .bind(picked.length ? picked.join(",") : null, mode, user.id).run();
    return picked.length ? "Airlines saved" : "Any airline now counts";
  }
  if (action === "starter") {
    const { n } = await env.DB.prepare("SELECT COUNT(*) AS n FROM watches WHERE user_id = ?").bind(user.id).first();
    if (n > 0) return "Starter routes are only for an empty list";
    const origin = code(form.get("origin")) || DEFAULT_ORIGIN;
    await env.DB.batch(starterInserts(env, user.id, origin));
    return `Added ${DEFAULT_ROUTES.length} starter routes from ${origin}`;
  }
  if (action === "add") {
    const origin = code(form.get("origin"));
    const dests = (form.get("destinations") || "").toString().split(/[\s,]+/).map(code).filter(Boolean);
    if (!origin || dests.length === 0) return "Use 3-letter airport codes, like ATL or FCO";
    const o = readOptions(form);
    const { n } = await env.DB.prepare("SELECT COUNT(*) AS n FROM watches WHERE user_id = ?").bind(user.id).first();
    const room = Math.max(0, 15 - n);
    const adding = [...new Set(dests)].filter((d) => d !== origin).slice(0, room);
    if (adding.length === 0) return "You're at the limit of 15 routes. Remove one first.";
    await env.DB.batch(adding.map((d) =>
      env.DB.prepare(`INSERT INTO watches (user_id, origin, destination, cabin, min_nights, max_nights, months_ahead, drop_pct, max_price)
                      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`)
        .bind(user.id, origin, d, o.cabin, o.min, o.max, o.months, o.drop, o.maxPrice)
    ));
    return `Added ${adding.map((d) => `${origin} to ${d}`).join(", ")}`;
  }
  const m = action.match(/^watch\/(\d+)(?:\/(toggle|delete))?$/);
  if (m) {
    const id = m[1];
    const w = await env.DB.prepare("SELECT * FROM watches WHERE id = ? AND user_id = ?").bind(id, user.id).first();
    if (!w) return "That route isn't yours";
    if (m[2] === "toggle") {
      await env.DB.prepare("UPDATE watches SET active = ? WHERE id = ?").bind(w.active ? 0 : 1, id).run();
      return `${w.origin} to ${w.destination} ${w.active ? "paused" : "resumed"}`;
    }
    if (m[2] === "delete") {
      await env.DB.batch([
        env.DB.prepare("DELETE FROM alerts WHERE watch_id = ?").bind(id),
        env.DB.prepare("DELETE FROM watches WHERE id = ?").bind(id),
      ]);
      return `Removed ${w.origin} to ${w.destination}`;
    }
    const o = readOptions(form);
    await env.DB.prepare(`UPDATE watches SET cabin = ?, min_nights = ?, max_nights = ?, months_ahead = ?, drop_pct = ?, max_price = ? WHERE id = ?`)
      .bind(o.cabin, o.min, o.max, o.months, o.drop, o.maxPrice, id).run();
    return `Saved ${w.origin} to ${w.destination}`;
  }
  return "Unknown action";
}

// ---------- admin ----------

async function adminPage(env, url, base, msg) {
  const { results: users } = await env.DB.prepare(
    `SELECT u.*, (SELECT COUNT(*) FROM watches w WHERE w.user_id = u.id) AS routes
     FROM users u ORDER BY u.name`
  ).all();
  const { n: priceCount } = await env.DB.prepare("SELECT COUNT(*) AS n FROM prices").first();
  const origin = url.origin;
  const rows = users.map((u) => {
    const link = u.token ? `${origin}/u/${u.token}` : "";
    return `<div class="card">
      <div class="row between"><div><b>${esc(u.name)}</b> <span class="muted small">${esc(u.email)}${u.basecamp ? " &middot; Basecamp" : ""}${u.active ? "" : " &middot; paused"}</span>
        <div class="muted small">${u.routes} route${u.routes == 1 ? "" : "s"}</div></div>
        <form method="post" action="${base}/link/${u.id}"><button class="ghost small">New link</button></form></div>
      ${link ? `<input readonly value="${link}" onclick="this.select()" class="small">
        <div class="row"><a href="${link}">Open</a><a href="mailto:${esc(u.email)}?subject=${encodeURIComponent("You're on Flightwatch (free flight sale alerts)")}&body=${encodeURIComponent(inviteText(u.name, link))}">Email it to them</a></div>` : ""}
    </div>`;
  }).join("");
  const body = `
    ${msg ? `<div class="note">${esc(msg)}</div>` : ""}
    <p class="muted">${users.length} people &middot; ${priceCount.toLocaleString("en-US")} prices saved</p>
    <h2>Add someone</h2>
    <form method="post" action="${base}/user" class="card stack">
      <label>Name <input name="name" required></label>
      <label>Email <input name="email" type="email" required></label>
      <label>Home airport <input name="origin" list="airports" value="${DEFAULT_ORIGIN}" maxlength="3" class="code"></label>
      <label class="row nogap"><input type="checkbox" name="starter" checked style="width:auto"> Start with the ${DEFAULT_ROUTES.length} starter routes (Europe and Asia)</label>
      <label class="row nogap"><input type="checkbox" name="basecamp" style="width:auto"> Send their alerts to Basecamp instead of email</label>
      <button>Add</button>
    </form>
    <datalist id="airports">${AIRPORTS.map(([c, n]) => `<option value="${c}">${n}</option>`).join("")}</datalist>
    <h2>People</h2>
    ${rows || `<p class="muted">Nobody yet.</p>`}`;
  return page("Flightwatch admin", body);
}

function inviteText(name, link) {
  return `Hey ${name},

I added you to Flightwatch, a free flight sale alert tool I built. It checks Google Flights every few hours for routes you pick and only emails you when a fare is actually on sale.

Your private settings page (it's your login, so don't share it):
${link}

How it works: every fare is compared to Google's own typical price for that exact trip. You only get an email when a fare is below the usual range, at least 30% under typical, and saves at least $150. Each email shows the price vs normal, the airline, the cheapest dates, how long the sale runs, and a link to Google Flights.

Setup:
1. Open your link. You may already have starter routes from Atlanta to Europe and Asia.
2. Remove routes you don't want, or add your own under "Add routes" (several airport codes at once works, like FCO, LIS, ATH).
3. Tap a route to change cabin, trip length, how far ahead to look, or how big a drop counts.
4. Optional: pick your airlines under Airlines.
5. Optional: turn on the check-in email for a Sunday and Wednesday update.

Alerts come from "Flightwatch", so add it to your contacts if one lands in spam. Big sales don't happen every day, so quiet is normal.`;
}

// ---------- helpers ----------

async function readForm(request) {
  const type = request.headers.get("content-type") || "";
  return type.includes("form") ? await request.formData() : new FormData();
}

function home() {
  return page("Flightwatch", `<p>Free flight deal alerts for a few friends.</p>
    <p class="muted">If you've been added, use the link in your Flightwatch email to change your routes.</p>
    <p class="muted small">Open source on <a href="https://github.com/AidenHodgson/Flightwatch">GitHub</a>.</p>`);
}

function code(v) {
  const c = (v || "").toString().trim().toUpperCase();
  return /^[A-Z]{3}$/.test(c) ? c : null;
}

function randomToken() {
  const b = new Uint8Array(18);
  crypto.getRandomValues(b);
  return btoa(String.fromCharCode(...b)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function redirect(to) {
  return new Response(null, { status: 303, headers: { Location: to } });
}

function page(title, body, status = 200) {
  return new Response(`<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<title>${esc(title)}</title><style>${CSS}</style></head>
<body><main><header><a href="/" class="logo">&#9992; Flightwatch</a></header><h1>${esc(title)}</h1>${body}</main></body></html>`,
    { status, headers: { "content-type": "text/html; charset=utf-8", "referrer-policy": "no-referrer" } });
}

const CSS = `
:root{--bg:#f6f5f2;--card:#fff;--ink:#16181d;--muted:#6b7078;--line:#e4e2dc;--accent:#0b6e4f;--danger:#b42318}
@media (prefers-color-scheme:dark){:root{--bg:#121315;--card:#1c1d21;--ink:#eceae5;--muted:#9a9ea6;--line:#2d2f34;--accent:#4cc49a;--danger:#f97066}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:560px;margin:0 auto;padding:20px 16px 60px}header{margin-bottom:8px}.logo{font-weight:700;color:var(--ink);text-decoration:none}
h1{font-size:26px;margin:8px 0 4px}h2{font-size:17px;margin:28px 0 10px}a{color:var(--accent)}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px;margin:10px 0}
.paused{opacity:.6}summary{list-style:none;cursor:pointer;display:flex;justify-content:space-between;gap:12px}summary::-webkit-details-marker{display:none}
details[open] summary{margin-bottom:12px;padding-bottom:12px;border-bottom:1px solid var(--line)}
.price{text-align:right;font-weight:700;color:var(--accent);white-space:nowrap}
.muted{color:var(--muted)}.small{font-size:13px}.stack{display:flex;flex-direction:column;gap:12px}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}.row>label{flex:1;min-width:130px}.between{justify-content:space-between}.nogap{gap:6px;flex-wrap:nowrap}
label{display:flex;flex-direction:column;gap:4px;font-size:14px;font-weight:600}
input,select{font:inherit;padding:10px 12px;border:1px solid var(--line);border-radius:10px;background:var(--bg);color:var(--ink);width:100%}
.code{text-transform:uppercase;max-width:120px}.prefix{font-weight:400}
button{font:inherit;font-weight:600;padding:10px 16px;border-radius:10px;border:1px solid var(--accent);background:var(--accent);color:#fff;cursor:pointer}
button.ghost{background:transparent;color:var(--accent)}button.danger{border-color:var(--danger);color:var(--danger)}button.small{padding:6px 10px;font-size:13px}
label.row{flex-direction:row;align-items:center;font-weight:500}
.chips{display:flex;flex-wrap:wrap;gap:8px}.chip{flex-direction:row;align-items:center;gap:6px;font-weight:500;border:1px solid var(--line);border-radius:999px;padding:6px 12px;background:var(--bg)}.chip input{width:auto;margin:0}
.note{background:var(--card);border-left:4px solid var(--accent);padding:10px 14px;border-radius:8px;margin:12px 0}`;
