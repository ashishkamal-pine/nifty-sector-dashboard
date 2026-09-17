# Third-Party Connections & Dependencies

Every external touchpoint. Short version: **two free key-less data sources, one CDN for
fonts, zero Python packages beyond the standard library.**

## 1. NSE — sector indices and constituents (primary)

| Item | Detail |
|---|---|
| Endpoint | `https://www.nseindia.com/api/allIndices` |
| Auth | **None** — no key, no account, no login |
| Used by | `app.py` → `fetch_nse_sectors()` |
| Calls per refresh | 13 (1 cookie prime + 1 allIndices + 11 constituent calls) |
| Returns | 139 indices; the 11 sectoral ones are selected by name |

Per index `allIndices` supplies `last`, `previousClose`, `oneWeekAgoVal` and
`oneMonthAgoVal` — official values for all three timeframes, which is why the current
design needs no historical endpoint and no locally-accumulated price history.

A second endpoint supplies constituents:

| Item | Detail |
|---|---|
| Endpoint | `/api/NextApi/apiClient/marketWatchApi?functionName=getIndicesData&symbol=<INDEX>` |
| Used by | `app.py` → `fetch_nse_constituents()` |
| Returns | NSE's **live index membership** plus `lastPrice`, `previousClose`, `perChange30d` per stock |

This is what makes membership authoritative rather than a hand-maintained list. Note the
two endpoints use **different index names** — `allIndices` says "NIFTY FINANCIAL
SERVICES", `marketWatchApi` wants "NIFTY FIN SERVICE".

**Access requirements.** NSE rejects plain scripted clients. It works only with full
browser-style headers (a real `User-Agent`, `sec-ch-ua`, `Sec-Fetch-*`) **and** a
session cookie obtained by requesting the homepage first. This is the most fragile
dependency in the project — hence the Yahoo fallback.

**Terms.** NSE publishes this data for its own site. There is no documented public API
contract, so treat it as best-effort. NSE licenses real-time redistribution through
authorised vendors (TrueData, Global Datafeeds); this is a personal-dashboard use, not
a redistribution one.

## 2. Yahoo Finance — weekly stock reference only

| Item | Detail |
|---|---|
| Endpoint | `https://query2.finance.yahoo.com/v7/finance/spark` |
| Auth | **None** |
| Used by | `app.py` → `fetch_bars()` / `weekly_refs()` |
| Calls per refresh | 9 (171 symbols in batches of 20; 30+ per batch returns HTTP 400) |
| Returns | ~65 daily bars per symbol, from `range=3mo&interval=1d` |

Used for exactly one thing: the **weekly reference price of individual stocks**, which
NSE does not publish. Failed batches are retried 3 times; anything still unresolved is
counted in `weekly_missing` rather than silently falling back.

Also the **sector fallback** via `^CNX*` index symbols when NSE is unreachable, and
`/v1/finance/search` when diagnosing a symbol that stopped resolving.

**Requires a browser `User-Agent`** — Yahoo returns HTTP 429 without one.

**Unofficial.** No published contract and no ToS permitting programmatic
redistribution; endpoints have changed before (`/v7/finance/quote` now requires a
cookie/crumb, while `/v7/spark` and `/v8/chart` still work unauthenticated). Data is
delayed, not tick-by-tick.

## 3. Google Fonts — CDN

| Item | Detail |
|---|---|
| Host | `fonts.googleapis.com` (+ `fonts.gstatic.com`) |
| Used by | `Sector_Performance_Board.html` |
| Families | Barlow Condensed, Inter, JetBrains Mono |
| Required? | **No** — the page falls back to system fonts |

The only outbound request the browser itself makes. Remove the two `<link>` tags to go
fully offline.

## 4. Python packages

**None.** `app.py` and `universe.py` use only the standard library: `json`, `gzip`,
`datetime`, `urllib.parse`, `urllib.request`, `http.cookiejar`, `http.server`,
`socketserver`, `webbrowser`.

There is no `requirements.txt` because there is nothing to install. Verified on Python
3.12.10.

## 5. Localhost HTTP

| Item | Detail |
|---|---|
| Bind | **`127.0.0.1:8765`** — loopback only, not reachable from your network |
| Routes | `/`, `/api/live_data.json`, `/live_data.json`. Everything else 404s |
| CORS | None needed — page and data share an origin |
| Auth | None (nor needed; it is not externally reachable and holds no secrets) |

## Connections this project does NOT make

- No broker API. No trading, order, position or funds endpoints anywhere
- No credentials, tokens, API keys or secrets of any kind — nothing to leak or renew
- No database; no state is persisted at all between fetches
- No cloud services, external logging, error reporting, analytics or telemetry
- No package CDN in the HTML — no React, no charting library, no CSS framework
- No CI/CD, containers or deployment tooling

## Data provenance

Sector figures and constituent prices are **official NSE values** — indices free-float
market-cap weighted as NSE computes them. Only the weekly reference for individual
stocks comes from Yahoo.

In the Yahoo fallback path only, weekly/monthly sector figures become an
*equal-weighted* constituent average, which is **not** how NSE weights an index. Those
rows are marked `approxWM: true` with a `*` so the distinction is never hidden.

## Removed dependency: Fyers

The project previously used the Fyers broker API via the `fyers-apiv3` package, needing
an app ID, a secret key and a browser login every trading day. It was removed because
NSE provides better data — official, complete for all 11 sectors — with no account at
all. The reasoning is in [live-data-options.md](live-data-options.md).
