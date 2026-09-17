# Data Model & File Formats

## The sector universe

**Membership is fetched live from NSE at runtime** — 11 sectors, 181 slots, 171 unique
symbols as of 2026-09-17. The `SECTORS` dict in `universe.py` is only the offline
fallback (refreshed from NSE on the same date); the XLSX `Constituents` sheet still
carries the original, now-outdated list.

| # | Sector | Count | NSE index name (primary) | Yahoo symbol (fallback) |
|---|---|---|---|---|
| 1 | Bank | 12 | NIFTY BANK | `^NSEBANK` |
| 2 | IT | 10 | NIFTY IT | `^CNXIT` |
| 3 | Auto | 12 | NIFTY AUTO | `^CNXAUTO` |
| 4 | Pharma | 12 | NIFTY PHARMA | `^CNXPHARMA` |
| 5 | FMCG | 11 | NIFTY FMCG | `^CNXFMCG` |
| 6 | Metal | 10 | NIFTY METAL | `^CNXMETAL` |
| 7 | Energy | 10 | NIFTY ENERGY | `^CNXENERGY` |
| 8 | Realty | 8 | NIFTY REALTY | `^CNXREALTY` |
| 9 | Media | 7 | NIFTY MEDIA | `^CNXMEDIA` |
| 10 | PSU Bank | 11 | NIFTY PSU BANK | `^CNXPSUBANK` |
| 11 | Fin Service | 16 | NIFTY FINANCIAL SERVICES | `^CNXFIN` ⚠️ |

⚠️ Yahoo's `^CNXFIN` is *NIFTY FINSRV25 50* — the narrower 25/50 variant. The primary
NSE path returns the real NIFTY Financial Services index, so this only matters in
fallback mode.

### Cross-sector duplicate stocks

Quoted once, emitted once per sector membership:

| Symbol | Sectors | Count |
|---|---|---|
| SBIN | Bank, PSU Bank, Fin Service | 3 |
| HDFCBANK | Bank, Fin Service | 2 |
| ICICIBANK | Bank, Fin Service | 2 |
| KOTAKBANK | Bank, Fin Service | 2 |
| AXISBANK | Bank, Fin Service | 2 |
| BANKBARODA | Bank, PSU Bank | 2 |
| PNB | Bank, PSU Bank | 2 |
| CANBK | Bank, PSU Bank | 2 |

Live values are therefore identical across sectors for these names.

### Symbol overrides

Three tickers no longer map 1:1 to a Yahoo listing (`SYMBOL_OVERRIDES` in `universe.py`):

| NSE ticker | Yahoo | Effect |
|---|---|---|
| `TATAMOTORS` | `TMCV` | remapped |
| `TV18BRDCST` | *(none)* | dropped — `NETWORK18` already covers Media |
| `LTIM` | *(none)* | dropped |

Net: **108 symbols fetched, 117 constituent rows** rather than 119.

## Symbol formats

| Kind | Format | Example |
|---|---|---|
| Equity (Yahoo) | `<SYMBOL>.NS` | `HDFCBANK.NS` |
| Index (Yahoo, fallback) | `^<INDEX>` | `^NSEBANK` |
| Index (NSE, primary) | full name | `NIFTY BANK` |
| Display / JSON | bare NSE symbol | `HDFCBANK` |

Built by `yahoo_stock()` in `universe.py`. The universe contains symbols with
punctuation — `M&M` and `BAJAJ-AUTO` — which are URL-encoded before use.

## The core row shape

Both row types share the same five fields:

| Field | Type | Meaning |
|---|---|---|
| `sector` | string | Sector name, matching the universe exactly |
| `indexSymbol` *(sector rows)* | string | Display label; gets `*` appended in fallback mode |
| `symbol` *(constituent rows)* | string | Bare NSE stock symbol |
| `prevD` | float | Reference close for **Daily** |
| `prevW` | float | Reference close for **Weekly** |
| `prevM` | float | Reference close for **Monthly** |
| `ltp` | float | Last traded price / current index level |

Percent change, everywhere: `(ltp - prev) / prev * 100`.

## `/api/live_data.json` payload

Built by `app.py` → `build_payload()`, consumed by the dashboard. Nothing is written to
disk — this exists only in the HTTP response.

```json
{
  "generated_at": "2026-09-17T17:47:37",
  "source": "NSE (official indices) + Yahoo (stocks)",
  "source_sectors": "NSE allIndices (official)",
  "note": "All sector figures are official NSE index values.",
  "sectors": [
    {"sector":"Bank","indexSymbol":"NIFTY BANK","approxWM":false,
     "prevD":56292.45,"prevW":56471.95,"prevM":57497.8,"ltp":56055.75}
  ],
  "constituents": [
    {"sector":"IT","symbol":"TCS",
     "prevD":2188.8,"prevW":2204.1,"prevM":2280.0,"ltp":2190.0}
  ]
}
```

| Field | Purpose |
|---|---|
| `generated_at` | When the **data** was fetched. The header shows its age, so staleness is visible |
| `source` / `source_sectors` | Which path ran — official NSE or the Yahoo fallback |
| `note` | Human-readable summary of the above |
| `approxWM` | Per sector: `true` if weekly/monthly is a constituent average |

All floats are rounded to 2dp. The dashboard validates only that `sectors` and
`constituents` exist.

## Where the reference closes come from

**Sectors (primary, NSE `/api/allIndices`)** — one call supplies all three directly:

| Field | Source field |
|---|---|
| `ltp` | `last` |
| `prevD` | `previousClose` |
| `prevW` | `oneWeekAgoVal` |
| `prevM` | `oneMonthAgoVal` |

**Sectors (fallback, Yahoo)** — `prevD` from a `range=1d` call's `chartPreviousClose`;
`prevW`/`prevM` from index history where it exists, otherwise an equal-weighted
constituent average rescaled as `ltp / (1 + avg_pct/100)`.

**Constituents (Yahoo)** — the close on or before 1, 7 and 30 calendar days back,
walked backwards through real dated bars from a `range=3mo&interval=1d` fetch. Walking
real dates skips weekends and market holidays automatically.

> `chartPreviousClose` is deliberately **not** used for constituent `prevD`: over a
> 3-month range Yahoo reports the close at the *start* of the range, not yesterday's.
