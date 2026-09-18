# `app.py` — the one-command live dashboard

```bash
python app.py
```

Opens <http://localhost:8765> and loads live NSE prices automatically.

**Needs:** Python 3.7+. That is the entire list. No `pip install`, no API key, no
login, no daily token, no second terminal.

---

## Why this shape

The dashboard is a browser page, and browsers refuse to read responses from a server
that does not send CORS headers. Neither NSE nor Yahoo Finance sends them.

`app.py` sidesteps the whole problem by being **both the web server and the fetcher**:

```
browser ──GET /────────────────► app.py ──► serves Sector_Performance_Board.html
browser ──GET /api/live_data.json──► app.py ──► NSE + Yahoo ──► JSON back
```

The page is served from `localhost:8765` and calls `localhost:8765` — **same origin,
so CORS never enters the picture.** Yahoo is called by Python, which is not a browser
and is not subject to CORS at all.

That is also why no key or login is needed: neither NSE's public index endpoint nor
Yahoo's chart endpoints require one, so there is no secret to store, expose, or renew.

## Endpoints

| Route | Returns |
|---|---|
| `/` | `Sector_Performance_Board.html` |
| `/api/live_data.json` | Fetches NSE + Yahoo **on request** and returns the payload |
| `/live_data.json` | Alias for the same payload |

Bound to **`127.0.0.1`**, not `0.0.0.0` — not reachable from your network. It serves
only these three routes, never the whole directory.

## Payload

The familiar shape plus three provenance fields:

```json
{
  "generated_at": "2026-09-17T17:47:37",
  "source": "NSE (official indices) + Yahoo (stocks)",
  "source_sectors": "NSE allIndices (official)",
  "note": "All sector figures are official NSE index values.",
  "sectors":      [{"sector":"Bank","indexSymbol":"NIFTY BANK","approxWM":false,
                    "prevD":56292.45,"prevW":56471.95,"prevM":57497.8,"ltp":56055.75}],
  "constituents": [{"sector":"IT","symbol":"TCS",
                    "prevD":2188.8,"prevW":2204.1,"prevM":2280.0,"ltp":2190.0}]
}
```

Each sector and constituent row also carries `spark: {d, w, m}` — see below.

`generated_at` is when the **data** was fetched, not when the browser drew it — the
header shows its age ("2s ago"), so a stale board is now visible as stale. That closes
issue **F5**.

## How the numbers are derived

**Constituents come from NSE**, one call per sector to
`/api/NextApi/apiClient/marketWatchApi?functionName=getIndicesData&symbol=<INDEX>`.
That returns NSE's **live index membership** — not a hardcoded list — plus per stock:

| Field | Used as |
|---|---|
| `lastPrice` | `ltp` |
| `previousClose` | `prevD` |
| `perChange30d` | `prevM`, reconstructed as `ltp / (1 + pct/100)` |

NSE publishes **no weekly figure for individual stocks**, so that one value comes from
Yahoo's `/v7/finance/spark`, batched 20 symbols per request (30+ returns HTTP 400),
taking the close on or before 7 days back from real dated bars. Failed batches are
retried 3 times; anything still unresolved is counted in `weekly_missing` and shown in
the UI note rather than silently passing off the daily figure as weekly.

> Note the two NSE endpoints use **different index names**: `allIndices` says
> "NIFTY FINANCIAL SERVICES", `marketWatchApi` wants "NIFTY FIN SERVICE".

### Sparkline series

Each row also carries `spark: {d, w, m}` — three close-price series for the three
timeframes, from Yahoo:

| Key | Range / interval | Points |
|---|---|---|
| `d` | `1d` / `5m` | ~76 → 32 |
| `w` | `5d` / `15m` | ~101 → 32 |
| `m` | `1mo` / `1h` | ~155 → 32 |

Monthly uses **hourly** bars deliberately: 8 of the 11 sector indices have no daily
bars on Yahoo at all, but every one of them has intraday and hourly. That single choice
is what makes sparklines possible for all 11 sectors rather than 3.

`fetch_sparks()` threads 8 workers over ~30 batched requests, so all three timeframes
across ~190 symbols add about a second. Series are downsampled to 32 points before
they leave the server, keeping the payload near 170 KB.

**Sector indices come from NSE, not Yahoo.** `https://www.nseindia.com/api/allIndices`
returns, for every index in a single call:

| Field | Used as |
|---|---|
| `last` | `ltp` |
| `previousClose` | `prevD` |
| `oneWeekAgoVal` | `prevW` |
| `oneMonthAgoVal` | `prevM` |

So **all 11 sectors get official NSE values for all three timeframes** - no proxy, no
averaging, no approximation. `approxWM` is `false` for every row and the UI shows no
asterisks.

This also fixes the index-identity problem: NSE returns the real
**NIFTY FINANCIAL SERVICES**, not Yahoo's `^CNXFIN` (which is the narrower
"NIFTY FINSRV25 50" variant).

NSE rejects plain scripted clients, so `app.py` sends full browser-style headers and
primes a cookie from the homepage first. If NSE is unreachable the code falls back to
the older Yahoo-index path (real index daily + constituent-averaged weekly/monthly,
flagged with `approxWM: true` and a `*`), so the dashboard degrades instead of breaking.

A deliberate subtlety: `chartPreviousClose` is **not** used for `prevD`, because over a
3-month range Yahoo reports the close at the *start* of the range, not yesterday's. A
separate `range=1d` call supplies the true previous close.

## Symbol handling

`universe.py` is the single source of truth for sector membership, NSE index names and
Yahoo symbol mappings.

Because membership comes from NSE at runtime, symbols are always current — the old
hand-maintained list had drifted badly (it was missing 64 stocks and still listed 6 that
NSE had dropped). `SYMBOL_OVERRIDES` in `universe.py` remains as a hook for tickers that
Yahoo spells differently, but is **empty**: all 171 current symbols resolve.

`SECTORS` in `universe.py` is now only the offline fallback, used when NSE is blocked.

Net: **181 constituent rows across 171 unique symbols**, 11 sectors.

## Buttons

| Button | Does |
|---|---|
| **Refresh** | Pull fresh data now |
| **Auto-refresh** | Toggle; re-fetches every 30 seconds while on |

The page fetches once on load, so it is populated before you touch anything.
Auto-refresh polls from the browser, and each tick is a **full** fetch (~8 HTTP calls to
NSE and Yahoo). At 30s that is roughly 240 upstream requests an hour, and it keeps
polling outside market hours — worth turning off when you are not watching.

## What it does *not* do

- **No background work.** The server only fetches when the page asks; the
  *Auto-refresh* toggle drives that from the browser side.
- **No writes.** Nothing touches the Excel workbook, and no `close_history.json` is
  needed — Yahoo supplies the history.

## Caveats

- Yahoo's API is **unofficial** — no contract, no ToS for redistribution, and endpoints
  have changed before. Expect occasional breakage.
- Data is **delayed**, not tick-by-tick. Fine for a sector board; verify against NSE
  before acting on a specific number.
- A `User-Agent` header is required — Yahoo returns HTTP 429 without one.
- **NSE is the weak link for reliability**, not accuracy: it blocks scripted clients
  aggressively, so the cookie priming may start failing. The Yahoo fallback exists for
  exactly that case, and the payload's `source_sectors` field tells you which path ran.
- `^CNXFIN` (Yahoo, fallback only) is **NIFTY FINSRV25 50**, not the full index. The
  primary NSE path does not have this problem.
