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
| HTTP 403 from NSE | NSE is refusing that IP. VPNs, office networks and data-centre IPs are common casualties; a home connection or phone hotspot usually works |
| Timed out | A firewall dropping the traffic silently, or NSE rate-limiting |
| Name resolution failed | Offline, or DNS filtering |
| Connection refused | A proxy or firewall. Set `HTTPS_PROXY` before starting if the machine needs one |

The page now names the cause itself rather than only saying "unreachable", and the empty
grid distinguishes the three situations that used to share one message: still loading, the
server is up but NSE is not reachable, and the server itself is not running. The old text
told people to start `app.py` even when `app.py` was plainly already running and answering.

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
