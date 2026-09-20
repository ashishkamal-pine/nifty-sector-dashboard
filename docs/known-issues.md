# Known Issues & Sharp Edges

Observations on the **current** codebase (`app.py`, `universe.py`, the HTML, the
workbook). Items that only applied to the removed Fyers pipeline are listed at the
bottom for reference.

---

## Reliability

### R1. NSE blocks scripted clients

The highest-risk dependency. `/api/allIndices` needs full browser-style headers plus a
cookie primed from the homepage, and NSE tightens this periodically. If it starts
failing, sector data silently degrades to the Yahoo fallback.

**Mitigated, not solved:** the fallback keeps the board working, and `source_sectors`
in the payload names which path ran. Worth checking that field if numbers look off.

### R2. Both data sources are unofficial

Neither NSE's site API nor Yahoo's chart endpoints are published, contracted
interfaces. Both have changed before and can change again without notice. There is no
version pinning possible and no deprecation warning to watch.

For a personal sector board this is an acceptable trade for "no account, no key". For
anything you trade real money on, a licensed feed is the honest answer.

### R3. No retry or backoff

A failed Yahoo batch is logged and skipped (`app.py` `fetch_bars`), so a transient
error silently drops ~20 stocks from that refresh. The `got N/108 stocks` line is the
only signal. Hitting **Refresh** again is the workaround.

### R4. Data is delayed

Neither source is tick-by-tick. Fine for ranking sectors; do not read a specific number
as the live market price.

---

## Data correctness

### D1. Weekly stock references depend on Yahoo

NSE publishes no weekly figure for individual stocks, so `prevW` comes from Yahoo. If a
symbol cannot be resolved there, its weekly falls back to the daily reference — but the
count is reported in `weekly_missing` and surfaced in the UI note, so it is never
silent. Verified 171/171 resolving as of 2026-09-17.

Yahoo batches do fail transiently (502/429); each is retried three times before being
given up on.

### D2. Duplicate stocks span sectors

SBIN appears in Bank, PSU Bank and Fin Service; 8 other symbols appear in two sectors
([data-model.md](data-model.md#cross-sector-duplicate-stocks)). Correct behaviour — they
genuinely are members of several indices — but it means those names influence multiple
sector rows, and in fallback mode the Bank / PSU Bank / Fin Service averages are
correlated by construction.

### D3. Equal-weighted fallback is not an index

Only in the Yahoo fallback path: weekly/monthly becomes a plain arithmetic mean of
constituent moves, so a small-cap counts as much as Reliance. NSE indices are free-float
market-cap weighted. Flagged with `approxWM` and a `*`, so it is visible — but it is an
approximation, not the index.


---

## Fragility

### F1. HTML injection is no longer reachable

The dashboard still renders with unescaped template literals into `innerHTML`, but the
arbitrary-URL input was removed, so the only source it reads is `app.py` on loopback.
Worth remembering if a configurable source is ever reintroduced.


---

## Resolved by the current design

## Sparkline interiors are still Yahoo's

Both ends of every sparkline are pinned to NSE: the dashed baseline is NSE's
`prevD`/`prevW`/`prevM` and the final point is snapped to the NSE LTP, so the chart
begins and ends exactly where the row's numbers say. The **points in between** are still
Yahoo's intraday bars, so the path can differ slightly from NSE's own intraday record.
Measured deviation of the last bar before snapping: median 0.000%, worst 1.31%. The
shape is right; do not read an intermediate point as an official NSE price.

## Fixed in earlier passes

These applied to the removed Fyers pipeline and no longer exist:

| Was | Why it is gone |
|---|---|
| Server exposed the access token to the network and to any website (wildcard CORS, `0.0.0.0` bind, whole-directory serving) | No token exists; `app.py` binds `127.0.0.1` and serves 3 routes |
| Plaintext `access_token.txt`, one `git add -A` from disclosure | No credentials of any kind |
| Daily interactive broker login | No account needed |
| Weekly/monthly meaningless until ~30 days of history accumulated | NSE supplies official W/M directly |
| "Closes" were really the last price seen that day | Real official closes |
| 9 of 11 sectors approximated by constituent average | All 11 on official NSE index values |
| Universe duplicated across three files with nothing enforcing agreement | `universe.py` is the single source |
| Dead feed showed a green "Live" badge indefinitely | `generated_at` + age shown in the header |
| Non-atomic writes could corrupt the history file | Nothing is written to disk |
| Real-time and Daily were the same computation under different labels | The Real-time button was removed; Daily is the default |
| Sector membership was a hardcoded list that had drifted (64 stocks missing) | Fetched live from NSE each refresh |
| Synthetic sample data in the HTML looked like real prices | Removed; the page is a pure view over live data |
| The universe was restated in the HTML and could drift | Removed with the sample data |
| Naive CSV parsing broke on quoted values | The manual-paste path was removed |
| Market-hours check used local machine time, not IST | No scheduling loop |

The removed files remain in git history at commit `37f06ed`.
