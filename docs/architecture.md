# Architecture

## The one idea holding it together

Every part of this project agrees on a single row shape:

```
(name, reference_close_D, reference_close_W, reference_close_M, LTP)
```

Percent change is always `LTP / reference_close - 1`, and the active timeframe just
selects *which* reference close to divide by. That is the entire model. The Excel
formulas and the JavaScript implement the same arithmetic independently, which is why
they stay consistent without sharing code.

## Component map

```
    ┌────────────────────────────┐     ┌────────────────────────┐
    │  NSE                       │     │  Yahoo Finance         │
    │  /api/allIndices           │     │  /v7/finance/spark     │
    │  /…marketWatchApi          │     │  weekly reference only │
    └─────────────┬──────────────┘     └───────────┬────────────┘
                  │ 11 sectors D+W+M               │ 171 stocks
                  │ 181 constituents D+M           │ 1 field each
                  └───────────────┬────────────────┘
                                   │
                        ┌──────────▼──────────┐
                        │      app.py         │
                        │  fetch + shape      │
                        │  serve on :8765     │
                        └──────────┬──────────┘
                                   │  same-origin HTTP
                        ┌──────────▼───────────────────┐
                        │ Sector_Performance_Board.html│
                        │   (browser)                  │
                        └──────────────────────────────┘

        Sector_Performance_Tracker.xlsx  —  standalone, manual, not wired in
```

## Why `app.py` is both server and fetcher

A browser refuses to read a cross-origin response unless the server sends
`Access-Control-Allow-Origin`. Neither NSE nor Yahoo sends it, so the page cannot call
them directly — this is a browser rule, not an authentication problem, and no API key
or login would change it.

`app.py` dissolves the issue by serving the page and the data from the **same origin**:

```
browser ──GET /──────────────────► app.py  →  the HTML
browser ──GET /api/live_data.json─► app.py  →  calls NSE + Yahoo  →  JSON
```

The browser only ever talks to `localhost:8765`. NSE and Yahoo are called by Python,
which is not a browser and is not subject to CORS at all. That single indirection is
what makes a no-account, no-key setup possible.

## Sequence of a refresh

1. Browser `GET /api/live_data.json`.
2. **Sectors** — prime a cookie from the NSE homepage, then one call to
   `/api/allIndices`. Per index it yields `last`, `previousClose`, `oneWeekAgoVal` and
   `oneMonthAgoVal` — official levels for all three timeframes.
3. **Constituents** — one call per sector to `marketWatchApi`, giving NSE's *live index
   membership* plus `lastPrice`, `previousClose` and `perChange30d` per stock. `prevM`
   is reconstructed from that percentage.
4. **Weekly stock reference** — the only gap NSE leaves. The resulting symbol list goes
   to Yahoo in batches of 20, and the close on or before 7 days back is taken from real
   dated bars. Symbols with no weekly are counted in `weekly_missing`, never silently
   substituted.
5. Shape into `{generated_at, source, sectors[], constituents[]}` and return.
6. Browser replaces state, re-renders, and stamps the data's age in the header.

Typical end-to-end: **about 5 seconds**, roughly 22 HTTP calls (12 NSE + 9 Yahoo).

## Fallback behaviour

If NSE is unreachable — it blocks scripted clients aggressively — `app.py` falls back
to Yahoo's `^CNX*` index symbols. Yahoo has live levels for all 11 but daily *history*
for only about three, so in fallback mode weekly/monthly for the remainder is derived
from an equal-weighted constituent average, rescaled onto the index level. Those rows
carry `approxWM: true` and a `*` on the symbol.

The payload's `source_sectors` field always states which path ran, so an approximation
is never silent.

## Boundaries and coupling

- **Loose: HTML ↔ JSON.** The dashboard renders any payload with `sectors` and
  `constituents`. It is not tied to NSE or Yahoo; swapping the data source means
  changing only `app.py`.
- **Single source of truth: `universe.py`.** Sector membership, Yahoo symbol overrides
  and NSE index names all live in one file.
- **The HTML holds no data.** It is a pure view — no sample data, no manual entry — so
  it cannot disagree with `universe.py`.
- **Fully detached:** the Excel workbook. Nothing reads or writes it.

## What changed from the original design

The project began as a Fyers broker integration that polled on a timer, kept its own
`close_history.json`, and wrote into both the workbook and a JSON file served by a
second process. That required a daily interactive login and a stored plaintext token,
and could not quote 9 of 11 sector indices — so it approximated them.

The current design removes the broker entirely. NSE supplies official complete figures
for every sector with no credentials, which eliminated the token, the login, the
self-built history file, the approximation, and two of the three processes.
