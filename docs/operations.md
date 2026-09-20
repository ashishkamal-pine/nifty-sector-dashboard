# Operations

## Running it

```bash
python app.py
```

## "NSE unreachable" / "No data yet"

The dashboard being on screen only proves `app.py` is running - the page is served by it.
"NSE unreachable" means that machine could not reach nseindia.com, which is a network
question, not a dashboard one, and it varies by machine and connection. NSE in particular
blocks traffic it judges automated, and decides that **per IP address**, so the same code
can work on one connection and be refused on another.

Run the checker in the project folder:

```
python diagnose.py
```

It walks the same path `app.py` takes - DNS, TCP, TLS, the NSE homepage, the cookie-primed
index API, then Yahoo - and names the first step that fails plus what usually causes it.
It changes nothing.

Common causes, in rough order of likelihood:

| Symptom | Usual cause |
|---|---|
| TLS certificate verification failed | Antivirus or a company network inspecting HTTPS. Try `pip install --upgrade certifi`, or a different network |
| HTTP 403 from NSE | NSE's bot protection refused the **client**, which is usually not about the IP at all - see below |
| Timed out | A firewall dropping the traffic silently, or NSE rate-limiting |
| Name resolution failed | Offline, or DNS filtering |
| Connection refused | A proxy or firewall. Set `HTTPS_PROXY` before starting if the machine needs one |

The page now names the cause itself rather than only saying "unreachable", and the empty
grid distinguishes the three situations that used to share one message: still loading, the
server is up but NSE is not reachable, and the server itself is not running. The old text
told people to start `app.py` even when `app.py` was plainly already running and answering.

### A 403 from NSE is usually about the client, not the network

NSE sits behind Akamai, which fingerprints the TLS handshake and headers. Measured from
one machine on one IP address, asking `https://www.nseindia.com/` four different ways in
the same minute:

| Client | Result |
|---|---|
| `app.py`'s urllib client | **200** |
| a hand-rolled "browser-like" cipher order | 403 |
| `curl.exe` | 403 |
| `requests` | 403 |

Same address, same moment, four verdicts. So a 403 does not mean the connection is
blocked - it means that particular client was not recognised.

Narrowing the handshake makes this **worse**, not better. Measured on the accepting
machine: the default context gets 200, while pinning any single key-exchange curve
(`set_ecdh_curve`) gets 403. An attempt to pin "classical" TLS groups was written, found
to be inert - `SSLContext.set_groups()` does not exist in CPython, on 3.12 or on 3.14 -
and then reverted once it was shown that correcting it would have broken the working
case. `app.py` deliberately leaves the TLS context alone.

Client fingerprinting is not the whole story either. On an address NSE refuses, *every*
client is refused, `curl.exe` and its separate TLS stack included. Measured on two
machines:

| Client | Accepting IP | Refusing IP |
|---|---|---|
| `app.py`'s urllib | 200 | 403 |
| `curl.exe` | 403 | 403 |

So the two failure modes are distinguishable: if some clients pass, it is the client; if
none do, it is the address. That is exactly what `probe_nse.py` reports.

When a 403 appears, run:

```
python probe_nse.py
```

It asks NSE the same question with several different clients and says whether anything
is accepted. If *every* client is refused, it really is the address, and a phone hotspot
is the quickest confirmation. If some are accepted, it is fingerprinting, and the output
says which client works.

### What happens when NSE stays unreachable

The board does not sit empty. When NSE cannot be reached it falls back to Yahoo and says
so in a banner above the grid. Measured by blocking NSE on a machine that NSE accepts and
comparing every figure against the official values captured moments earlier:

| Figure | Accuracy in fallback mode |
|---|---|
| Sector daily | worst 0.15pp |
| Sector weekly | worst 0.24pp |
| Sector monthly | worst 1.43pp - **approximate** |
| Stock daily | median 0.000pp, worst 1.38pp |
| Stock weekly | median 0.000pp, worst 1.37pp |
| Stock monthly | **approximate** |
| Membership | bundled snapshot, not live NSE |

Two details decide that accuracy.

**The previous close comes from `range=1d`, not from the history bars.** Yahoo's daily
bars have gaps - 17 Sep was missing for many stocks - so `bars[-2]` silently becomes the
day before the previous close. That put 54 of 171 stocks out by more than 0.5pp, worst
4.68pp. `meta.chartPreviousClose` from a `range=1d` request matches NSE's `prevD`
exactly, which is why the fallback issues two requests per batch rather than one.

**"One month ago" is the same date a calendar month back**, not a flat 30 days. Measured
against NSE's own `oneMonthAgoVal`: 30 days is worst 2.16pp out, the calendar month
1.43pp. Neither is exact, because NSE's reference date is its own and cannot be read
while NSE is down - hence the approximate label rather than a silent number.

The residual stock error is Yahoo's live price lagging NSE's, not the reference: on the
worst names the previous close agrees to the paisa while the last traded price does not.
That is irreducible without NSE.

If Yahoo is blocked but NSE is not, prices and percentages are still correct - only the
sparklines and the rotation page go empty.

If the port is already taken, `app.py` exits with a single line saying so rather than a
traceback, and makes no upstream requests on the way out. The already-running instance is
left completely alone.

Opens <http://localhost:8765> (served on both `127.0.0.1` and `::1`; see performance.md), which **fetches live data as soon as it loads**. Prints
a line per fetch. Ctrl+C to stop.

**Requirements:** Python 3.7+ and an internet connection. No `pip install`, no account,
no API key, no login, no token, no config file.

### Healthy output

```
[17:51:07] fetching 108 stocks + 11 indices...
  NSE: 11/11 sector indices (official D/W/M)
  got 108/108 stocks
  built 11 sectors / 117 constituents in 1.4s
```

`11/11` from NSE is the good case — every sector on official values. If you instead see
`! NSE unreachable ... falling back to Yahoo indices`, the board still works but
weekly/monthly for most sectors becomes a constituent average, marked with `*`.

117 constituents rather than 119 is expected: two symbols in the universe no longer
exist on Yahoo. See [app.md](app.md#symbol-handling).

## The buttons

| Button | Does |
|---|---|
| **Refresh** | Pull fresh data now |
| **Auto-refresh** | Toggle; when on, re-fetches every 30 seconds |

The page also fetches once automatically on load, so normally you do not have to press
anything.

## The page requires the server

The HTML is a pure view now — no sample data, no manual entry. Opened as a `file://`
path it shows "No data yet" and points you at `python app.py`.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| "No data yet" / `Could not load live data` | Server not started, or started in another folder | Run `python app.py` from the repo directory |
| `! NSE unreachable` | NSE blocked the request | Usually transient — hit **Refresh** again. Fallback data is still shown, marked `*` |
| Sector symbols show a `*` | Running on the Yahoo fallback | Check `source_sectors` in `/api/live_data.json` |
| `got 104/108 stocks` | Yahoo rate-limited or dropped a batch | Retry; if a symbol is permanently gone, add it to `SYMBOL_OVERRIDES` |
| `OSError: Address already in use` | Port 8765 taken | Stop the other process, or change `PORT` in `app.py` |
| Numbers look stale | Nothing has re-fetched since load | The header shows the data's age; hit **Refresh** or enable **Auto-refresh** |

## Maintenance

Everything about the universe lives in `universe.py`.

**Adding a stock to a sector** — add the symbol to the right list in `SECTORS`. That is
all; `ALL_STOCKS` derives from it automatically. If Yahoo lists it under a different
ticker, add a `SYMBOL_OVERRIDES` entry.

**Adding a sector** — add it to `SECTORS`, `NSE_INDEX` (the official name exactly as
`/api/allIndices` reports it) and `YAHOO_INDEX` (for the fallback).

**A symbol stops resolving** — usually a merger, demerger or rename. Find the current
ticker with Yahoo's symbol search, then map it in `SYMBOL_OVERRIDES`, or set it to
`None` to drop it deliberately rather than have it fail silently.

**Watch the counts.** The `got N/108 stocks` line is the early-warning signal for symbol
drift.

## Version control

A `.gitignore` covers `__pycache__/` and `*.pyc`. Nothing in the current design writes
secrets — no tokens, no keys, no credentials — so the old token-leak risk is gone
entirely.
