# `Sector_Performance_Board.html` — the dashboard

~430 lines, single file, no build step, no runtime dependencies. Served by `app.py` at
<http://localhost:8765>.

It is a **pure view**: it holds no data of its own and does one thing — fetch
`/api/live_data.json` and render it. There is no sample data, no manual entry and no
configurable source. Opened as a `file://` path it will show "No data yet" and point
you at `python app.py`.

## Visual design

A dark "trading desk board" driven entirely by CSS custom properties on `:root`:

| Token | Value | Role |
|---|---|---|
| `--bg` / `--bg-panel` / `--bg-panel-2` | `#0B111E` / `#121A2B` / `#0E1524` | Layered dark navy |
| `--ink` / `--ink-muted` | `#ECE9DF` / `#8791A6` | Warm off-white text |
| `--gold` / `--gold-dim` | `#D7A947` / `#8A7238` | Accent, active states |
| `--green` / `--green-dim` | `#2FBE6B` / `#173321` | Gains, "Best" tag |
| `--red` / `--red-dim` | `#E5594B` / `#3A1A17` | Losses, "Worst" tag |

**Fonts** are the one external dependency: Barlow Condensed (headings), Inter (body),
JetBrains Mono (all numbers) from Google Fonts. Without a network the page still works
— it falls back to system `sans-serif`/`monospace`.

Layout caps at 1180px. The sector grid is `repeat(auto-fill, minmax(230px, 1fr))`, so
it reflows responsively. Tiles animate in with a `flapin` keyframe staggered 0.03s each.

## Controls

| Control | Does |
|---|---|
| **Daily / Weekly / Monthly** | Switches which reference close drives the percentages |
| **Auto-refresh** | Toggle; when on, fetches immediately then every 30s, and highlights gold |
| **Refresh** | Pull fresh data now |

The page also fetches once on load, so it is populated without any interaction.

## Views

### Overview
- **Hero row** — two cards: top and bottom sector for the active timeframe.
- **Sector grid** — all 11 ranked best→worst, each showing rank, name, index name,
  percent change and a **sparkline**. Rank 1 gets a green "Best today" tag; last gets
  red "Worst today".
- Clicking any tile opens the drill-down.

### Drill-down
- Back button, sector title, subtitle reading `<indexName> — <Timeframe> change`.
- Hero cards for best/worst *constituent*.
- Ranked table: Rank, Symbol, LTP, **Trend** (per-stock sparkline), % Chg.
- Top and bottom `N` rows are tinted, where `N = min(3, floor(len/2) || 1)` — so a
  7-stock sector highlights 3 at each end without overlapping.

Views toggle via `display:none` plus an `.active` class. There is no routing, so the
view is not linkable or restorable on reload.

## State and rendering

```js
state = {
  timeframe: 'daily',      // 'daily' | 'weekly' | 'monthly'
  sectors: [],             // filled by the first fetch
  constituents: [],
  selectedSector: null,
}
```

Timeframe → field, via `fieldForTf()`:

| Timeframe | Field |
|---|---|
| `daily` | `prevD` |
| `weekly` | `prevW` |
| `monthly` | `prevM` |

Key functions:

| Function | Purpose |
|---|---|
| `pctChange(row, tf)` | `(ltp - prev)/prev*100`, `null` if `prev` falsy |
| `fmtPct(v)` | `+1.23%` / `-0.45%` / `n/a` |
| `fmtPrice(v)` | `toLocaleString('en-IN')`, 2dp — Indian digit grouping |
| `rankedSectors()` | maps in `pct`, sorts desc, nulls sink via `?? -999` |
| `rankedConstituents(name)` | same, filtered to one sector |
| `renderHero(...)` | Generic — reused for both sector and constituent heroes |
| `sparkSvg(vals, ref)` | Builds the inline sparkline SVG |
| `sparkFor(row)` | Picks the series matching the active timeframe |
| `renderGrid()` | Overview tiles, or the "No data yet" message when empty |
| `renderDrilldown()` | Drill-down table |
| `renderStamp(data)` | Header line showing the data's age |
| `fetchLiveNow()` | The single data path |
| `setAuto(on)` | Starts/stops the 30s auto-refresh interval |

Rendering is full-teardown (`innerHTML = ''` then rebuild) on every change. At 11 + 117
rows that is imperceptible.

## The data path

```js
fetch('/api/live_data.json', {cache: 'no-store'})
  → res.ok check
  → res.json()
  → require data.sectors && data.constituents
  → replace state, re-render, stamp the age
```

While in flight the Refresh button reads "Loading..." and is disabled, and a `fetching`
flag blocks re-entry — so a fetch slower than the 30s tick cannot overlap the next one.

On failure it writes a red status line naming the error and telling you to start
`app.py`; state is left untouched, so a failed auto-refresh does not blank out good data.

**A refresh keeps you where you are.** If you are in a drill-down it re-renders that
drill-down with the new numbers rather than bouncing you to the overview; it only
returns to the overview if the selected sector disappeared from the payload.

Validation is shallow — presence of the two top-level keys. Rows with wrong field names
pass through and surface as `n/a`.

## Sparklines

Every hero card, sector tile and drill-down row carries an inline SVG sparkline. They
are drawn from `row.spark`, which holds three pre-downsampled series:

| Timeframe | Series | Source range |
|---|---|---|
| Daily | `spark.d` | today, 5-minute bars |
| Weekly | `spark.w` | 5 days, 15-minute bars |
| Monthly | `spark.m` | 1 month, hourly bars |

Switching timeframe swaps the series, so the shape genuinely changes rather than being
rescaled. Each is thinned to 32 points server-side.

The line is green or red to match the row's direction, over a faint filled area, with a
**dashed horizontal line at the reference price** (`prevD`/`prevW`/`prevM`) so you can
see which side of it the series has been trading.

`sparkSvg()` scales the y-axis to include the reference line, so a flat series near its
reference does not get amplified into fake volatility. `preserveAspectRatio="none"` plus
`vector-effect="non-scaling-stroke"` keeps the stroke even when the SVG is stretched to
the tile width.

**Note the sparkline for a sector comes from Yahoo's index series while the percentages
come from NSE.** The shape is right; the absolute levels can differ slightly from NSE's
official figure.

## Freshness

`renderStamp()` reads `generated_at` from the payload and shows the data's age
("2s ago", "4m ago"). This is when the **data was fetched**, not when the browser drew
it — so a stale board is visibly stale rather than silently wrong.

## Caveats

- **No persistence.** Reload re-fetches from scratch; the selected timeframe and the
  auto-refresh toggle reset.
- **Rendering uses unescaped `innerHTML`.** Safe as-is since the only source is `app.py`
  on loopback, but it would matter if a configurable source were reintroduced.
