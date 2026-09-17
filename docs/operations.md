# Operations

## Running it

```bash
python app.py
```

Opens <http://localhost:8765>, which **fetches live data as soon as it loads**. Prints
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

## The Excel workbook

`Sector_Performance_Tracker.xlsx` is no longer written to by anything. It remains a
working **manual** tracker: paste prices into the blue input columns and all formulas,
ranks and conditional formatting recalculate. See [excel-workbook.md](excel-workbook.md).

## Version control

A `.gitignore` covers `__pycache__/` and `*.pyc`. Nothing in the current design writes
secrets — no tokens, no keys, no credentials — so the old token-leak risk is gone
entirely.
