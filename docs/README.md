# NIFTY Sector Dashboard — Documentation

A local dashboard for tracking NSE sector performance across Daily / Weekly / Monthly
timeframes. Runs on your machine, fetches live data on demand, needs no account.

## Quickstart

```bash
python app.py
```

Opens <http://localhost:8765> and **loads live NSE data automatically**. Hit
**Refresh** for a fresh pull, or turn on **Auto-refresh** to update every 30 seconds.

Two pages, linked by the tabs at the top:

- **`/`** — the performance board: sector cards, drill-downs, sparklines
- **`/rrg`** — the [Relative Rotation Graph](rrg.md): where each sector sits against
  NIFTY 50 and which way it is rotating

**Requirements:** Python 3.7+. That is the whole list — no `pip install`, no API key,
no login, no token.

## What this project is

| Piece | File | Role |
|---|---|---|
| Web dashboard | `Sector_Performance_Board.html` | The performance board |
| Rotation graph | `RRG.html` + `rrg.py` | Relative Rotation Graph at `/rrg` |
| Server + fetcher | `app.py` | Serves the page and pulls live data on request |
| Connectivity check | `diagnose.py` | Says whether this machine can actually reach NSE and Yahoo, step by step. Run it when the board says "NSE unreachable" |
| NSE client probe | `probe_nse.py` | Asks NSE with several different clients to tell a fingerprint block apart from an IP block. Run it when `diagnose.py` reports 403 |
| Sector universe | `universe.py` | Single source of truth: sectors, stocks, index names |

Data comes from two free, key-less sources, with NSE authoritative:

- **Sector indices → NSE** (`/api/allIndices`) — official values, complete daily,
  weekly and monthly for all 11 sectors
- **Constituent membership + prices → NSE** (`marketWatchApi`) — the live index
  constitution, with official previous close and 30-day change
- **Weekly stock reference → Yahoo Finance** — the one figure NSE does not publish
  for individual stocks

## Document index

| Doc | Covers |
|---|---|
| [app.md](app.md) | `app.py` — how the fetching works, endpoints, symbol handling |
| [performance.md](performance.md) | How loading, caching and prefetching work, with measurements |
| [rrg.md](rrg.md) | The Relative Rotation Graph: the maths, the data, how to read it |
| [architecture.md](architecture.md) | End-to-end data flow and why it is shaped this way |
| [data-model.md](data-model.md) | The universe, shared row schema, every file format |
| [web-dashboard.md](web-dashboard.md) | The HTML: UI, state, rendering |
| [third-party.md](third-party.md) | Every external connection and dependency |
| [operations.md](operations.md) | Running it, troubleshooting, maintenance |
| [known-issues.md](known-issues.md) | Remaining sharp edges — **worth reading** |
| [live-data-options.md](live-data-options.md) | The research behind the data-source choice |

## The page needs the server

`Sector_Performance_Board.html` no longer carries sample data or a manual-entry path —
it is a pure view over what `app.py` serves. Opened directly from the filesystem it
will show "No data yet" and tell you to start the server. That is deliberate: the old
built-in sample numbers were synthetic but looked real.

## History

The project originally pulled from the **Fyers broker API** (`fyers_auth.py`,
`fyers_sync.py`, `serve_live_data.py`). That approach required a daily interactive
login, stored a plaintext access token, and — because brokers only carry live feeds for
F&O-enabled indices — could not quote 9 of the 11 sector indices, so it approximated
them with an equal-weighted constituent average.

Those files were removed once NSE proved to supply complete official data for all 11
sectors with no login at all. `Sector_Performance_Tracker.xlsx` — a formula-driven
manual tracker that nothing read or wrote — was removed with them.

Everything remains in git history at commit `37f06ed` and can be restored with
`git checkout 37f06ed -- <file>`. The reasoning is recorded in
[live-data-options.md](live-data-options.md).
