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

Stage 3 *depends on* stage 2 rather than racing it. Sparks needs the symbol list, and
the browser asks for both at once, so reading the constituents cache opportunistically
could miss and silently fall back to the static universe in `universe.py` — correct only
for as long as that happens to match NSE. It now goes through the store, which returns
the cached copy instantly in the normal case and single-flights onto the in-progress
build on a cold start. Cold, both requested in parallel: no deadlock, and zero stocks
without a sparkline.

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

## The 2-second stall that dwarfed all of it

`localhost` resolves to `::1` before `127.0.0.1` on Windows, but the server bound only
the IPv4 loopback. Binding one stack does not make the other fail fast — Windows drops
the IPv6 SYN rather than refusing it, so the client sat in a connect timeout before
falling back. Measured on this machine, per connection:

| Target | Connect |
|---|---|
| `localhost` | **2064 / 2017 / 2050 ms** |
| `127.0.0.1` | 16 / 0 / 0 ms |

`app.py` opens the browser at `http://localhost:8765/`, so this was being paid on the
normal path, on every fresh connection, and it dwarfed every other cost on the page.

`Server6` now listens on `::1` alongside the IPv4 server, so the stall is gone whichever
name is used. It is still loopback-only — the dashboard is not exposed on the network.
If the machine has no IPv6 the bind fails, the v4 server carries on, and the startup
banner says which address to use.

After: `localhost` connects in 5/22/0/17ms, and every route — `/`, `/rrg`, and all four
API endpoints — answers in 1–34ms.

## Sparklines cannot assume stage order

Stages 2 (constituents) and 3 (sparks) race, and neither may assume the other has
landed. Merging sparks on receipt alone lost **every stock sparkline** whenever sparks
won: the merge mapped over a still-empty `state.constituents`, then the constituents
reply overwrote the rows with sparkless ones. Sector tiles survived only because stage 1
had already filled `state.sectors` — which is exactly the 11-tiles / 0-rows split that
showed up on screen.

Sparks are now kept as their own payload (`state.sparks`) and re-applied by
`applySparks()` whenever either side arrives, including after stage 1 on a refresh so
tiles keep their trends instead of blanking. Verified by forcing each ordering with a
1.2s delay injected into `fetch`: 15/15 row sparklines and 11/11 tile sparklines in both
orderings and on a plain refresh.

The same class of bug on the server — `sparks` and `constituents` having different
freshness windows, so a newly added NSE constituent had no sparkline for up to 90s
silently — is handled by `build_sparks` recording `covers`, and `build_constituents`
calling `Store.drop("sparks")` when membership actually changes. The check costs 1.3ms
per 200 calls and does not fire when membership is unchanged.

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
