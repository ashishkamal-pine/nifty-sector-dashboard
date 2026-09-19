# Relative Rotation Graph

`RRG.html` + `rrg.py`, served at <http://localhost:8765/rrg>.

A Relative Rotation Graph plots each sector against a benchmark on two axes, so you can
see **whether a sector is beating the benchmark** and **whether that lead is growing or
shrinking**, at the same time.

Everything on it is *relative*. A sector can sit in Leading while falling, if it is
falling more slowly than the market.

## The axes

| Axis | Measures | Reading |
|---|---|---|
| **RS-Ratio** (x) | relative strength vs the benchmark | right of 100 = outperforming |
| **RS-Momentum** (y) | rate of change of that relative strength | above 100 = improving |

Both are normalised around 100, so the crosshair *is* the benchmark.

## The quadrants

```
         RS-Momentum
              ▲
   IMPROVING  │  LEADING          Leading    ratio>100  mom>100
   weak but   │  strong and       Weakening  ratio>100  mom<100
   recovering │  improving        Lagging    ratio<100  mom<100
  ────────────┼────────────►      Improving  ratio<100  mom>100
   LAGGING    │  WEAKENING        RS-Ratio
   weak and   │  strong but
   worsening  │  fading
```

The idealised cycle is **clockwise**: Improving → Leading → Weakening → Lagging →
Improving. Momentum turns before strength, so a sector normally passes through
Weakening before it reaches Lagging. It is an idealisation — sectors cut across the
middle and reverse regularly.

## The maths

Implemented in `rrg.py`, following the supplied reference document:

```
RS_t          = 100 × S_t / B_t
RS-Ratio_t    = 100 × EMA(RS, n) / EMA(EMA(RS, n), n)
RS-Momentum_t = 100 × RS-Ratio_t / EMA(RS-Ratio, n)
```

| Timeframe | Series | n | Note |
|---|---|---|---|
| Weekly (default) | weekly closes | 10 | the documented standard |
| Daily | daily closes | 20 | noisier, so smoothed harder |

> This is the widely used **approximation** of JdK's proprietary RS-Ratio /
> RS-Momentum, not the vendor formula — the reference document is explicit that it
> should be described as such. Quadrant membership and direction are faithful; the
> absolute distance from 100 will not match a commercial RRG platform, so do not compare
> raw numbers across tools.

### Why the axes scale independently

RS-Momentum is a ratio of an already double-smoothed series to its own EMA, so it varies
over roughly a third of the range RS-Ratio does — measured live, RS-Ratio spanned 5.3
points while RS-Momentum spanned 1.7. Forcing one shared scale would flatten every tail
into a horizontal line.

Each axis is therefore scaled independently and symmetrically around 100. The centre
lines stay at exactly 100, so **quadrant membership is unaffected** — only the visual
aspect changes.

## Where the prices come from

Yahoo carries daily bars for only three of the eleven NSE sector indices. Hourly data
exists for all of them, two years deep, so every series — including the benchmark — is
built identically:

```
2y of 1-hour bars → last bar of each IST trading day → daily close
                  → last daily close of each ISO week → weekly close
```

**Validated against the real daily bars** on the three indices that have both:
median deviation 0.05%, worst 0.7%. The drift is because the final hourly bar closes a
few minutes before the official 15:30 close.

Using one method for all twelve series matters more than that 0.05%: the reference
document requires the same treatment for every sector, and mixing real daily bars for
three with resampled bars for eight would break the comparison the chart rests on.

## Scopes

| Scope | Plots | Benchmark |
|---|---|---|
| All sectors | the 11 NSE sector indices | NIFTY 50 |
| *sector* — constituents | that sector's live NSE membership | NIFTY 50 **or** the sector's own index |

Clicking a sector — on the chart or in the table — drills into its constituents.

For stocks, **vs Sector** is usually the more useful question: it asks which names are
leading *within* the sector, rather than re-measuring the sector's own bias. Measured
live on Metal, the split against NIFTY 50 was 9/2/3/1 (nearly everything Leading, because
the whole sector was strong) versus 4/2/4/5 against NIFTY METAL — far more informative.

## API

```
GET /api/rrg.json?scope=sectors|sector&name=<sector>&tf=weekly|daily&tail=N&bench=nifty|sector
```

```json
{
  "as_of": "2026-09-18", "benchmark": "NIFTY 50",
  "timeframe": "weekly", "smoothing": 10, "tail": 12,
  "points": [
    {"name":"Metal","label":"NIFTY METAL","tv":"NSE:CNXMETAL",
     "ratio":101.844,"mom":100.418,"quadrant":"Leading","heading":76.0,
     "tail":[{"d":"2026-07-06","x":100.9,"y":99.8}]}
  ]
}
```

`heading` is the compass bearing of the last leg in degrees clockwise from north, so 45°
(NE) means up-and-right. Responses are cached for 120s.

## Verification

| Check | Result |
|---|---|
| Quadrant logic vs the reference document's worked example | **4/4 match** |
| `ema()` vs hand-computed reference | exact |
| Hourly→daily resampling vs real daily bars | median 0.05%, max 0.7% |
| RS-Ratio ranking vs actual 6-month relative performance | **Spearman ρ = 0.86** |
| Benchmark plotted against itself | exactly **100.000000 / 100.000000** |
| EMA seeding bias (full vs half history) | converged, Δ ≤ 0.003 |
| ISO-week grouping across a year boundary | correct |
| All sectors' tails on identical dates | yes |
| Chart, table, legend vs the payload | 0 mismatches |
| All 11 sectors drilled, both benchmarks | 0 skipped |
| Tail lengths 4 / 8 / 12 / 20 / 30 | all honoured |
| Weekly spacing 7 days, daily spacing 1 day | correct |
| 6 concurrent heavy builds | all HTTP 200 |
| Malformed `scope` / `bench` / `tail` | degrade, no 5xx |
| Dialog focus trap, inert background, scroll lock | correct |

The rank correlation is strongly positive but not 1.0, which is correct — RS-Ratio is a
smoothed *trend* measure over a different window, not a point-to-point return.

## How the chart behaves

**Dots only by default.** Eleven overlapping tails is noise; one tail in isolation is
the thing you actually want to read. Hovering a dot — or a row in the Positions table —
reveals that series' tail, dims everything else, and shows a card with its RS-Ratio,
RS-Momentum, quadrant and heading. The card is anchored to the dot rather than the
cursor so it does not jitter.

**Labels are pruned by measurement, not by guesswork.** Every label is drawn, then its
real `getBBox()` is compared against the ones already kept; anything that would overlap
is hidden. Points furthest from the centre get first refusal, since those are the ones
worth naming, and the hovered point always keeps its label. Estimating label width from
character count was hopeless — measured per-character width ranges 5.3px to 8.1px
depending on the letters — and left 21 overlapping pairs on a 40-stock sector. The
header says how many are unlabelled.

There are no gridlines or tick numbers: the quadrant fills already say which side of 100
a dot is on, and the exact values are in the card and the table.

**The axes scale to the dots, not the tails.** Measured on live data, tails span 1.6× the
dots on the x-axis and 2.7× on the y — scaling to them squeezed every dot into the middle
third of the plot. At 1.8× the dot range the dots get roughly 55% of the plot, which costs
about 14 of 132 tail points; those are always the oldest, faintest end, and they are
clipped to the plot rect rather than allowed to escape the panel.

## Reading it properly

The dot is only where a sector is now. The tail is usually the more useful half:

- **Long tail** — moving decisively; **short knotted tail** — no real signal
- **Leading but curling down** — heading for Weakening
- **Lagging but curling up** — possible recovery, unconfirmed
- **Improving, pushing up-and-right** — early strength, the most interesting quadrant

An RRG is not a signal on its own. Pair it with price trend, breadth, and what the
sector's own constituents are doing.

## Known limits

- **Approximation, not the vendor formula** — see above.
- **Two years of history** caps the longest tail and means the EMAs are seeded from the
  start of that window rather than from an infinite past.
- **Recently listed names are less settled.** The smoothing needs history to converge.
  Measured by dropping the oldest quarter of each series and recomputing: 105 weeks of
  history moves 0.000, 48 weeks moves 0.014, 30 weeks moves 0.096 — a couple of percent
  of the axis. Anything with fewer than `4n` periods is flagged **short** in the table
  and listed in `short_history`, rather than silently mixed in with settled names.
- **Daily mode is noisy**, as the reference document warns; weekly is the default for a
  reason.
- **Resampled closes** are a few minutes early versus the official close.
- **Dense clusters go unlabelled** rather than overlapping. The count is shown in the
  chart header and every dot still names itself on hover.
- **A long tail can be clipped** at the plot edge, because the axes are scaled to the
  dots. The trimmed part is always the oldest end.
- **Mid-week, the newest weekly point is a partial week** and will keep moving until
  Friday's close. The page says so with a banner when the latest point is not a Friday.
