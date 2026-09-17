# `Sector_Performance_Tracker.xlsx` — Excel workbook

> **Status:** standalone and manual. The script that used to populate this workbook
> (`fyers_sync.py`) has been removed, so nothing writes to it now. It still works
> exactly as designed as a paste-driven tracker.

Four sheets: `Instructions`, `Sector Summary`, `Constituents`, `Drilldown`.
Self-contained and fully formula-driven — paste new prices into the input columns and
everything recalculates, including ranks, tags and the drill-down table.

## Sheet 1 — `Instructions`

35 rows of plain text in column A. Covers how the workbook stays "live", what to paste
where, the colour legend, the drill-down workflow, the timeframe switch, and a note
about future automation. Key points it states:

- **Blue text = your input. Black text = formula, do not overwrite.**
- Green fill = top performers, red fill = underperformers.
- Refresh `Prev Close (D)` daily, `(W)` weekly, `(M)` monthly.
- Rows 33-35 admit the sample-data gap: *"On 'Constituents', only the Bank sector has
  sample stock prices filled in — every other sector's cells are at 0."*

Note the text mentions Kite Connect and Angel One SmartAPI as automation options —
this predates the Fyers scripts that now exist in the repo. Also, row 20 says the
drill-down dropdown is in **B2**; it is actually in **B1**
(the dropdown is in **B1**, not B2 as the text says).

## Sheet 2 — `Sector Summary`

The control sheet. Range `A1:I14`.

**B1 — the global timeframe switch.** A dropdown (data validation, list
`"Daily,Weekly,Monthly"`) that every other sheet reads from. One place to change.

**Row 3 — headers.** Data occupies rows **4-14**, one per sector, fixed.

| Col | Header | Type |
|---|---|---|
| A | Sector | text |
| B | Index Symbol | text |
| C | Prev Close (D) | **input**, blue, `#,##0.00` |
| D | Prev Close (W) | **input**, blue, `#,##0.00` |
| E | Prev Close (M) | **input**, blue, `#,##0.00` |
| F | LTP | **input**, blue, `#,##0.00` |
| G | % Chg (Active) | formula, `0.00%` |
| H | Rank | formula |
| I | Tag | formula |

**G — active percent change** (row 4 shown; identical pattern down to 14):
```excel
=IFERROR(IF($B$1="Daily",F4/C4-1,IF($B$1="Weekly",F4/D4-1,F4/E4-1)),"")
```
A two-level `IF` on the timeframe switch, wrapped in `IFERROR` so a zero or blank
reference close yields `""` instead of `#DIV/0!`.

**H — rank:**
```excel
=IFERROR(SUMPRODUCT(($G$4:$G$14>G4)*1)+1,"")
```
Count-of-greater + 1. Ties share a rank and skip the next value.

**I — tag:**
```excel
=IF(H4=1,"Top",IF(H4=11,"Bottom",""))
```
The `11` is **hardcoded to the sector count**. Add a 12th sector and "Bottom" stops
appearing.

**Conditional formatting:**
- `G4:G14` — a 3-colour scale on percent change.
- `A4:I14` — full-row green fill where `$I4="Top"`.
- `A4:I14` — full-row red fill where `$I4="Bottom"`.

All 11 sectors are pre-filled with plausible sample index levels, so ranking and tags
demonstrate correctly out of the box.

## Sheet 3 — `Constituents`

Range `A1:I120`. Headers in row 1, data rows **2-120** (119 rows — matching the 119
sector-slots exactly).

| Col | Header | Type |
|---|---|---|
| A | Sector | text |
| B | Symbol | text |
| C-F | Prev Close D/W/M, LTP | **input**, blue |
| G | % Chg (Active) | formula |
| H | Rank in Sector | formula |
| I | Key | formula |

**G** is the same timeframe switch, reaching across sheets:
```excel
=IFERROR(IF('Sector Summary'!$B$1="Daily",F2/C2-1,IF('Sector Summary'!$B$1="Weekly",F2/D2-1,F2/E2-1)),"")
```

**H — rank within sector.** Each sector block has its own hardcoded range:
```excel
=IFERROR(SUMPRODUCT(($A$2:$A$13=A2)*($G$2:$G$13>G2))+1,"")     ← Bank block
=IFERROR(SUMPRODUCT(($A$14:$A$23=A14)*($G$14:$G$23>G14))+1,"") ← IT block
```

**I — join key**, `=A2&"|"&H2` → `"Bank|1"`. This is what `Drilldown` looks up against.

### Sector block layout

| Sector | Rows | Count | Sample data? |
|---|---|---|---|
| Bank | 2-13 | 12 | ✅ filled |
| IT | 14-23 | 10 | ❌ all zeros |
| Auto | 24-35 | 12 | ❌ all zeros |
| Pharma | 36-47 | 12 | ❌ all zeros |
| FMCG | 48-58 | 11 | ❌ all zeros |
| Metal | 59-68 | 10 | ❌ all zeros |
| Energy | 69-78 | 10 | ❌ all zeros |
| Realty | 79-86 | 8 | ❌ all zeros |
| Media | 87-93 | 7 | ❌ all zeros |
| PSU Bank | 94-104 | 11 | ❌ all zeros |
| Fin Service | 105-120 | 16 | ❌ all zeros |

Because the block ranges are baked into the `H` formulas, **inserting or deleting rows
inside a block will silently corrupt neighbouring blocks' ranks**. Adding a stock means
editing the range in every formula of that block.

## Sheet 4 — `Drilldown`

Range `A1:H24`. A lookup view over `Constituents`.

| Cell | Content |
|---|---|
| **B1** | **Sector dropdown** — data validation list `='Sector Summary'!$A$4:$A$14` |
| B2 | `='Sector Summary'!$B$1` — mirrors the global timeframe, read-only |
| H2 | `=COUNTIF(Constituents!$A:$A,$B$1)` — member count of the selected sector |
| B4 | Best performer — `INDEX/MATCH` on rank 1 |
| B5 | Worst performer — `INDEX/MATCH` on rank `$H$2` |
| A8:D8 | Headers: Rank, Symbol, LTP, % Chg (Active) |
| A9:A24 | Static rank numbers **1-16** |
| B9:D24 | `INDEX/MATCH` pulls |

The pull pattern, e.g. `B9`:
```excel
=IFERROR(INDEX(Constituents!$B:$B,MATCH($B$1&"|"&A9,Constituents!$I:$I,0)),"")
```
It builds `"Bank|1"` and matches it against the `Key` column. `C9` and `D9` are the
same with columns `$F:$F` (LTP) and `$G:$G` (% change).

**Capacity is exactly 16 rows** — which happens to equal Fin Service, the largest
sector. There is no headroom; a 17th constituent in any sector would not appear.

**Conditional formatting on `A9:D24`:**
- `$A9<=3` — green, top 3
- `AND($A9>$H$2-3, $A9<=$H$2)` — red, bottom 3 of the *actual* member count
- `$A9>$H$2` — greys out rows beyond the sector's size

That third rule is what makes a 7-stock sector look clean in a 16-row table.

**The `B4` formula has a latent flaw:**
```excel
=IFERROR(INDEX(B9:B24,MATCH(1,A9:A24,0))&"  ("&TEXT(INDEX(D9:D24,1),"0.00%")&")","")
```
The symbol lookup uses `MATCH(1,...)` correctly, but the percentage uses a hardcoded
`INDEX(D9:D24,1)`. Both resolve to row 9 today because `A9` is literally `1`, so the
output is correct — but the two halves would diverge if the rank column were ever
reordered. `B5` does it properly with `MATCH($H$2,...)` on both halves.

## Automation status

Nothing writes to this workbook. The `fyers_sync.py` script that used to populate
columns C-F was removed along with the Fyers integration, so the workbook is now a
purely **manual** tool — which is how it was originally designed to work.

To repopulate it from live data you would write values into C-F on `Sector Summary`
(rows 4-14, matched by sector name in column A) and on `Constituents` (rows 2-120,
matched by the sector+symbol pair), leaving the formula columns G/H/I untouched.
`app.py` already produces exactly those numbers at `/api/live_data.json`.

Two things to know if you do: `openpyxl` drops cached formula results on save (Excel
recalculates on open, so this is cosmetic), and the file must not be open in Excel
while a script writes to it or the save fails with a lock error.
