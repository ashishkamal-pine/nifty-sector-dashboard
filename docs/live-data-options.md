# Live Data Without a Backend — Research & Plan

**Question:** can `Sector_Performance_Board.html` fetch live NSE data directly when you
click *Load Data*, with no backend, using a free API?

**Short answer:** not from a broker API — that path is closed by CORS, by credential
exposure, and by a daily manual login. But it *is* achievable another way, and the
route that works is also **better data than the current Fyers setup** — real NSE sector
indices instead of the equal-weighted proxy.

All findings below were tested against live endpoints on 2026-09-17, not taken from
vendor marketing pages.

---

## The two walls

Any "browser calls the API directly" design has to clear both:

**1. CORS.** The browser discards a cross-origin response unless the server sends
`Access-Control-Allow-Origin`. You cannot patch this from the client side — it is the
server's decision.

**2. Credential exposure.** Anything in client-side JS is public. Broker APIs use
OAuth with an app secret, so putting one in the HTML publishes your broker credentials
to anyone who opens View Source.

Broker APIs fail both. A third problem is specific to them: the access token expires
daily and renewal is an interactive browser login, so even a working integration needs
a human every morning.

---

## "What if I accept daily logins and secrets in a .env?"

A fair question, and it splits into two blockers — that concession fixes one of them
and not the other.

**Blocker 1 — a browser has no `.env`.** A `.env` file is read by a *program on a
machine you control* (Python, Node). The dashboard is a plain `.html` file; when you
open it there is no process to read `.env`, only what is literally inside the file. To
use a secret there you would have to type it into the JavaScript, where View Source and
the Network tab both expose it. So "secrets in `.env`" presupposes a backend — it is a
description of having one, not a way around needing one.

**Blocker 2 — CORS is not an auth problem.** Your JS asks Fyers for data; Fyers
answers; the browser then checks whether the response carries a header saying "this
website may read me." It does not, so the browser discards the response before your
code sees it. A valid token and a correct secret change nothing. **Only Fyers can fix
this**, by sending a header they do not send.

### So Fyers is usable — just not from the browser

| Setup | Fyers works? | Daily login painful? |
|---|---|---|
| Browser calls Fyers directly | ❌ never, regardless of willingness | — |
| **Local Python (the current setup)** | ✅ works today | No — you are already at a terminal |
| Fyers from a cloud Worker | ⚠️ technically | Yes — token dies nightly, renewal is an interactive browser login, so the Worker secret needs hand-feeding every morning |

Daily login is a perfectly reasonable trade **locally**. It is a bad one in the cloud:
a hosted service you must manually re-key each day is worse than the local script that
already exists. TOTP auto-login scripts for Fyers do exist, but they require storing
full broker credentials plus the 2FA seed — a materially larger exposure than an API key.

### The deciding factor is data, not auth

Even with every plumbing problem solved, Fyers still cannot quote **9 of the 11 sector
indices** — brokers only carry F&O-enabled indices. That limitation is precisely why
the equal-weighted proxy exists, and why weekly/monthly figures are wrong for those 9
sectors (**D3**). Yahoo returns all 11 real indices plus 3 months of history with no
key, no login and no expiry.

The recommendation is therefore not "Yahoo because Fyers is blocked" but **"Yahoo
because the data is better, and it dissolves the auth problem as a side effect."** A
Worker proxying Yahoo holds no secrets at all — nothing to leak, nothing to renew.

---

## Measured results

`Access-Control-Allow-Origin` as actually returned, with `Origin: https://example.com`:

| Provider | Status | CORS header | Browser-callable? |
|---|---|---|---|
| **Fyers** (broker) | — | none on quote endpoints | ❌ blocked |
| **Yahoo Finance** | 200 OK | **none** | ❌ blocked |
| **Twelve Data** | 401 | `*` | ✅ yes |
| **Alpha Vantage** | 200 OK | `*` | ✅ yes |
| **indianapi.in** | 400 | reflects origin + credentials | ✅ yes |
| **NSE India** (nseindia.com/api) | no response | none | ❌ blocked |
| **Stooq** | 404 | none | ❌ blocked |

Fyers' own community forum confirms the broker behaviour: login/funds/profile calls
work from a browser, but **quote requests are CORS-blocked**.

### The ones that pass CORS fail on data

- **Alpha Vantage** — free tier is **25 requests/day**. The dashboard needs 110 stocks
  plus 11 indices. Unusable at any refresh rate.
- **Twelve Data** — free tier is 800 credits/day, 8/min, and **1 credit per symbol**.
  That is ~6 full refreshes per day, and international (NSE) coverage is progressively
  gated behind the paid Grow/Pro tiers rather than included in the free Basic plan.
- **indianapi.in** — genuinely CORS-enabled and India-focused, but requires an API key
  that would sit in your client-side JS, and free-tier limits are not generous enough
  for a 121-symbol refresh.

### Broker APIs are all free — and all irrelevant here

Angel One SmartAPI, Upstox, Dhan and Shoonya all offer free API access with generous
limits. It does not matter: they are server-to-server APIs. None send CORS headers,
all need OAuth secrets, and all expire tokens daily. Free is not the constraint —
**browser-callable** is, and no broker is.

---

## The finding that changes the design

Yahoo Finance carries **every NIFTY sector index**, free, no API key. Tested live:

| Sector | Yahoo symbol | Verified |
|---|---|---|
| Bank | `^NSEBANK` | NIFTY BANK ✅ |
| IT | `^CNXIT` | NIFTY IT ✅ |
| Auto | `^CNXAUTO` | NIFTY AUTO ✅ |
| Pharma | `^CNXPHARMA` | NIFTY PHARMA ✅ |
| FMCG | `^CNXFMCG` | NIFTY FMCG ✅ |
| Metal | `^CNXMETAL` | NIFTY METAL ✅ |
| Energy | `^CNXENERGY` | NIFTY ENERGY ✅ |
| Realty | `^CNXREALTY` | NIFTY REALTY ✅ |
| Media | `^CNXMEDIA` | NIFTY MEDIA ✅ |
| PSU Bank | `^CNXPSUBANK` | NIFTY PSU BANK ✅ |
| Fin Service | `^CNXFIN` | NIFTY FINSRV25 50 ⚠️ *(the 25/50 variant, not the full Financial Services index)* |
| *(bonus)* NIFTY 50 | `^NSEI` | NIFTY 50 ✅ |

**Why this matters so much.** The entire proxy mechanism in the original Fyers sync
existed because brokers only quote F&O-enabled indices. Yahoo quotes all of them. Switching
data source deletes four of the correctness problems in
[known-issues.md](known-issues.md) outright:

- **D3** (proxy has no real weekly/monthly) — gone, real index values
- **D4** (equal-weighted ≠ official index) — gone, these *are* the official indices
- **D1** (cold start, no history) — gone, see below
- **D2** ("closes" are last-seen prices) — gone, real daily closes

One `range=3mo&interval=1d` call returns **65 daily bars** for *stocks*, so genuine
weekly and monthly reference closes come back in the same request. `close_history.json`
and its whole cold-start problem disappear.

**Superseded — see "The complete-data answer" at the end of this document.** The
Yahoo-only findings below stand, but NSE turned out to supply complete official data
and is now the primary sector source.

**Correction after implementation:** Yahoo quotes all 11 sector indices live, but
carries daily *history* for only about three of them (`^NSEBANK`, `^CNXIT`,
`^CNXPHARMA`); the other eight return a single bar. So daily change is real-index for
all 11, while weekly/monthly uses the real index where history exists and an
equal-weighted constituent average (rescaled onto the index level) where it does not.
Those sectors are marked with `*` in the UI. **D1/D2 are fully fixed; D3 is fixed in
that all three timeframes now differ genuinely; D4 still applies to the eight
fallback sectors' weekly and monthly figures only.**

Batching works too: `/v7/finance/spark?symbols=A,B,C` returned 10 symbols in one call,
including the awkward `M&M.NS` and `BAJAJ-AUTO.NS`. All 110 stocks fit in ~3 calls.

**The catch:** Yahoo sends no CORS header. Great data, still not directly browser-callable.

---

## Options

### Option A — Cloudflare Worker proxy ★ recommended

A ~20-line serverless function that fetches Yahoo and re-serves it with a CORS header.

```
Browser (Load Data) → your Worker → Yahoo Finance → JSON + CORS → dashboard renders
```

| | |
|---|---|
| Cost | Free — 100,000 requests/day |
| Servers to run | None. No terminal, no laptop left on |
| **Secrets in the browser** | **None** — Yahoo needs no API key at all |
| Freshness | True on-demand: click = live fetch |
| Effort | One file, one `wrangler deploy` |

Because Yahoo requires no key, the Worker holds no secrets — it is a pure relay. That
is what makes this dramatically simpler than proxying a broker API.

Strictly speaking a Worker *is* a backend. But it is zero-maintenance, free, and needs
no machine of yours running, which is what "no backend" actually means in practice.

### Option B — GitHub Actions + GitHub Pages

A scheduled workflow runs the Python fetcher, commits `live_data.json` to the repo, and
Pages serves the HTML and the JSON **from the same origin** — so CORS never applies.

| | |
|---|---|
| Cost | Free (public repos) |
| Servers | None at all — genuinely backendless |
| Secrets | Live in Actions secrets, never in the browser |
| Freshness | Cron-bound: ~5 min floor, often delayed. Not on-demand |
| Effort | One workflow YAML + enable Pages |

Well-trodden pattern with many public NSE examples. The trade-off is that *Load Data*
shows you the last scheduled snapshot, not a live tick. Also needs push access to a
repo — which `pratyush0000` does not currently have on `ashishkamal-pine`.

### Option C — Direct browser call to a CORS-enabled vendor

Truly zero infrastructure, but: API key exposed in client JS, and free tiers
(25/day Alpha Vantage, ~6 refreshes/day Twelve Data) cannot feed 121 symbols. Viable
only if the universe shrinks to the 11 sector indices and you accept a key in the page.

### Option D — Keep the local Python stack

What exists today. Real-time, already working, no new moving parts — but it needs two
terminals and your machine on. It does not meet the "just click Load Data" goal.

### Comparison

| | A: Worker | B: Actions+Pages | C: Direct | D: Local (today) |
|---|---|---|---|---|
| Free | ✅ | ✅ | ✅ | ✅ |
| Nothing of yours running | ✅ | ✅ | ✅ | ❌ |
| On-demand freshness | ✅ | ❌ (~5 min+) | ✅ | ✅ |
| No secrets in browser | ✅ | ✅ | ❌ | ✅ |
| Handles all 121 symbols | ✅ | ✅ | ❌ | ✅ |
| Real sector indices | ✅ | ✅ | ⚠️ | ❌ proxy |
| Truly no backend | ⚠️ serverless | ✅ | ✅ | ❌ |

---

## Recommended plan

**Option A, in four steps.** Each stands alone and leaves the repo working.

**Step 1 — Prove the data source.** Write `yahoo_sync.py` alongside the existing Fyers
script: same `live_data.json` output shape, sourced from Yahoo, using real sector
indices and real historical closes. Nothing else changes; the dashboard cannot tell
the difference. This alone retires the proxy and fixes D1–D4.

**Step 2 — Deploy the Worker.** Port the same fetch-and-shape logic to a Cloudflare
Worker that responds to `GET /live_data.json` with `Access-Control-Allow-Origin`
scoped to your dashboard's origin.

**Step 3 — Wire up the dashboard.** Point *Load Data* at the Worker URL. Keep the CSV
paste path and the existing *Live Source* polling as they are, so nothing regresses if
the Worker is unreachable.

**Step 4 — Surface freshness.** Add `generated_at` to the JSON and show the age in the
UI. This closes **F5** — today a dead feed still displays a green "Live" badge.

Roughly one working session for steps 1–2; step 3 is small; step 4 is polish.

---

## Caveats worth stating plainly

- **Yahoo's API is unofficial.** No published contract, no ToS permitting programmatic
  redistribution, and the endpoints have changed before (the `/v7/quote` route now
  wants a cookie/crumb; `/v7/spark` and `/v8/chart` still work unauthenticated). Treat
  it as best-effort and expect occasional breakage. For anything you trade real money
  on, a licensed feed is the honest answer.
- **The data is delayed,** not tick-by-tick. Fine for a sector performance board;
  verify against NSE before relying on a specific number.
- **Rate limiting is real.** A bare Yahoo request from this machine returned HTTP 429
  during testing; adding a browser `User-Agent` fixed it. The Worker should set one and
  cache responses for a few seconds.
- **`^CNXFIN` is the Financial Services 25/50 index,** not the full NIFTY Financial
  Services index. Either accept the variant or keep the constituent-average for that
  one sector — worth confirming which you want.
- **NSE licenses real-time data through authorised vendors** (TrueData, Global
  Datafeeds). Free sources are delayed or unofficial by construction; that is a
  property of the Indian market, not of this project.


---

## The complete-data answer: NSE `/api/allIndices`

The Yahoo research above settled for a hybrid: real index daily, constituent-averaged
weekly/monthly for 8 of 11 sectors. That was half data, and it was avoidable.

**`https://www.nseindia.com/api/allIndices` returns everything needed, in one call.**
Per index it carries not just `last` and `previousClose` but also **`oneWeekAgoVal`**
and **`oneMonthAgoVal`** (with `date30dAgo` / `oneWeekAgo` date stamps, plus
`perChange30d`, `perChange365d`, `yearHigh`/`yearLow`, `pe`, `pb`, `dy`, advances/declines).

Verified live: **11 of 11 sectors complete** for daily, weekly and monthly. No proxy,
no averaging, no asterisks. It also returns the true **NIFTY FINANCIAL SERVICES**,
resolving the `^CNXFIN` 25/50 mismatch.

### What was ruled out along the way

| Source | Result |
|---|---|
| Yahoo `^CNX*` index history | **Dead end** — 1 bar only, at every range/interval/symbol spelling tested; Yahoo's own symbol search confirms no alternative symbol |
| NSE `/api/historical/indicesHistory` | HTTP 503 to scripted clients, even with cookies and correct referer |
| NSE `/api/equity-stockIndices` (constituents) | HTTP 404 — endpoint gone |
| `niftyindices.com` Backpage endpoints | Returns the homepage HTML; endpoint removed |
| Fyers history endpoint | Not testable without credentials; community reports show index history unreliable even for NIFTY 50 / BANKNIFTY, and it still needs the daily OAuth login |

### The catch

NSE aggressively blocks scripted clients. It works only with full browser-style headers
(`sec-ch-ua`, `Sec-Fetch-*`, a real User-Agent) **and** a cookie primed from the
homepage first. That is more fragile than Yahoo, so `app.py` keeps the Yahoo hybrid as
an automatic fallback and reports which path ran via `source_sectors`.

Constituents still come from Yahoo — NSE's constituent endpoint is gone, and Yahoo
gives 108 symbols with real 3-month history, which is sufficient for the drill-down.
