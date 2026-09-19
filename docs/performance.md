# Loading & caching

The dashboard used to wait about five seconds before drawing anything, because one
endpoint built everything before returning. Profiling showed the wait was almost
entirely for data that was not on screen yet.

| Stage | Cost | Who needs it |
|---|---|---|
| NSE cookie + `allIndices` | **0.16s** | the sector grid — and nothing else |
| NSE constituents (11 calls) | 2.15s | the drill-down |
| Yahoo weekly refs + sparklines | 2.56s | the sparklines |

The grid is 2 KB of the 171 KB payload and needs 3% of the work. So the work is now
split, cached, and delivered in the order the page can use it.

## Three stages, rendered as they land

`Sector_Performance_Board.html` loads in sequence and renders at each step:

1. **`/api/sectors.json`** → the grid paints
2. **`/api/constituents.json`** → the drill-down becomes available
3. **`/api/sparks.json`** → sparklines fill in

Stages 2 and 3 run in parallel behind the grid, and the Refresh button re-enables as
soon as stage 1 lands. A stage failing leaves the earlier ones intact — a sparkline
outage cannot blank the board. The header shows what is still arriving.

## Stale-while-revalidate

`store.py` sits in front of every build:

| Age | Behaviour |
|---|---|
| < `fresh` | served from cache |
| `fresh` … `max_stale` | **served immediately**, rebuilt in the background |
| > `max_stale` | too old to show; build and wait |

Freshness windows reflect how fast each thing moves and what it costs: sectors 30s,
constituents 45s, sparklines 90s, RRG 120s.

**Single flight.** Concurrent requests for the same key produce one build, not several
— verified with 8 simultaneous cold reads resulting in exactly 1 build. Without it,
two tabs or an auto-refresh landing on a manual one would double upstream traffic.

**The cache is bounded.** The RRG key space is 11 sectors × 2 timeframes × 5 tails ×
2 benchmarks, so entries are dropped once older than an hour, and the oldest go first
past a 64-entry cap. Eviction never disturbs a build in progress.

**Failures do not poison the cache.** A background rebuild that throws leaves the last
good value in place, and a failed build does not wedge the key for later callers.

## A newer load supersedes an older one

Stages 2 and 3 continue after the grid is up, so a refresh can be requested while the
previous one is still finishing. Each load takes a ticket; a newer load invalidates
older ones and results from a superseded load are discarded rather than overwriting
fresher data.

The earlier design used a single in-flight flag, which re-enabled the button after
stage 1 but kept blocking until stage 3 — so a click during the background stages was
silently swallowed by a button that looked perfectly usable. Auto-refresh still skips a
tick while a load is genuinely running, so ticks cannot pile up.

The same scheme now covers the rotation page, where the blocking guard caused a worse
symptom: the segmented controls set `aria-pressed` the instant they are clicked, so
changing timeframe mid-load left the button reading **Daily** while the chart still
showed weekly data.

A superseded load must also stay quiet on the way out. Its **failure** is discarded
too — without that, an old request failing after a newer one succeeded marked the stage
as errored while 181 good rows sat in memory, and the drill-down said
"Could not load constituents" for the ~1.8s until something else corrected it.

## Warming and prefetching

The server warms `sectors → constituents → sparks → rrg` on a background thread at
startup, so the first visitor usually finds everything ready.

Each page then prefetches what is most likely next, once idle: the board prefetches the
rotation graph; the rotation graph prefetches the board, the other timeframe, and the
alternate benchmark for the sector being viewed.

## Measured

| Path | Before | After |
|---|---|---|
| First load, grid visible | ~5000ms | **312ms** warm · 557ms cold |
| First load, everything | ~5000ms | 648ms |
| **Manual refresh**, grid repainted | ~5000ms | **216ms** (button usable at 232ms; the rest continues behind) |
| Auto-refresh | ~5000ms | 648ms |
| `/api/sectors.json` warm | — | **5ms** |
| RRG sectors warm | ~540ms | 45ms |
| RRG, a combination never requested before | ~540ms | 1541ms (inherent — nothing to reuse) |

HTML itself serves in 3ms, so the shell is on screen effectively immediately in every case.

## Endpoints

| Route | Contents | Fresh |
|---|---|---|
| `/api/sectors.json` | 11 sector rows, no sparklines (~2 KB) | 30s |
| `/api/constituents.json` | 181 stock rows (~23 KB) | 45s |
| `/api/sparks.json` | spark series keyed by sector and symbol (~146 KB) | 90s |
| `/api/live_data.json` | all three combined, assembled from the cached parts | — |
| `/api/rrg.json` | rotation data per scope/timeframe/tail/benchmark | 120s |
| `/api/cache.json` | what is currently warm, and how old | — |

`?force=1` bypasses the cache on any of them and refreshes the stored copy.

Verified after the split: the three parts reproduce the combined payload exactly — same
counts, identical values, sparklines on every row, and the NSE cross-check still passes.
