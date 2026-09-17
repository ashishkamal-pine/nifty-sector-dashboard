"""
fyers_sync.py
-------------
Pulls live prices from Fyers for your NIFTY sector universe, keeps its own
rolling daily-close history (so it can compute weekly/monthly reference
closes itself), and writes the results into:
  1. Sector_Performance_Tracker.xlsx  (same cells you were pasting into by hand)
  2. live_data.json                  (same shape the web app's "Load Data" expects)

Run it on a loop during market hours and both files stay current.

IMPORTANT — sector index availability:
Most brokers (Fyers included) only carry live quotes for indices that have
F&O contracts (NIFTY 50, NIFTYBANK, FINNIFTY, etc.). Narrower sectoral
indices like NIFTY IT, NIFTY AUTO, NIFTY PHARMA and so on usually AREN'T
quotable through a broker API at all — NSE publishes them, but brokers don't
carry live feeds for non-F&O indices. So for any sector where a direct index
quote isn't available, this script automatically derives a sector-level
%change as the equal-weighted average of that sector's constituent stocks —
which are always available since they're ordinary equities. This is a proxy,
not the official cap-weighted index value, but it moves the same direction
and magnitude, and it's the only zero-cost way to get sector-level numbers
for every sector rather than just the handful with F&O contracts.

SETUP:
    pip install fyers-apiv3 openpyxl
    python3 fyers_auth.py      (once per day, before starting this)
    python3 fyers_sync.py
"""

import os
import re
import json
import time
import datetime as dt
from fyers_apiv3 import fyersModel
import openpyxl

# ----------------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------------
APP_ID = os.environ.get("FYERS_APP_ID", "YOUR_APP_ID-100")
TOKEN_FILE = "access_token.txt"
EXCEL_PATH = "Sector_Performance_Tracker.xlsx"
JSON_OUTPUT_PATH = "live_data.json"
CLOSE_HISTORY_PATH = "close_history.json"
REFRESH_INTERVAL_SECONDS = 60          # how often to poll while the loop runs
MARKET_OPEN = dt.time(9, 15)
MARKET_CLOSE = dt.time(15, 30)
RUN_ONCE = os.environ.get("FYERS_RUN_ONCE", "0") == "1"   # set to run a single pass, e.g. for testing/cron

# ----------------------------------------------------------------------------
# UNIVERSE — must match Sector_Performance_Tracker.xlsx and the web app
# ----------------------------------------------------------------------------
SECTORS = {
    "Bank":        ["HDFCBANK","ICICIBANK","SBIN","KOTAKBANK","AXISBANK","INDUSINDBK","BANKBARODA","PNB","IDFCFIRSTB","AUBANK","FEDERALBNK","CANBK"],
    "IT":          ["TCS","INFY","HCLTECH","WIPRO","TECHM","LTIM","PERSISTENT","COFORGE","MPHASIS","LTTS"],
    "Auto":        ["MARUTI","M&M","TATAMOTORS","BAJAJ-AUTO","EICHERMOT","HEROMOTOCO","TVSMOTOR","ASHOKLEY","BHARATFORG","MRF","BOSCHLTD","BALKRISIND"],
    "Pharma":      ["SUNPHARMA","DRREDDY","CIPLA","DIVISLAB","LUPIN","AUROPHARMA","TORNTPHARM","ZYDUSLIFE","ALKEM","BIOCON","GLENMARK","LAURUSLABS"],
    "FMCG":        ["HINDUNILVR","ITC","NESTLEIND","BRITANNIA","TATACONSUM","DABUR","GODREJCP","MARICO","COLPAL","UBL","VBL"],
    "Metal":       ["TATASTEEL","JSWSTEEL","HINDALCO","VEDL","JINDALSTEL","SAIL","NMDC","HINDCOPPER","NATIONALUM","APLAPOLLO"],
    "Energy":      ["RELIANCE","ONGC","NTPC","POWERGRID","COALINDIA","BPCL","IOC","GAIL","TATAPOWER","ADANIGREEN"],
    "Realty":      ["DLF","GODREJPROP","OBEROIRLTY","PHOENIXLTD","PRESTIGE","LODHA","BRIGADE","SOBHA"],
    "Media":       ["ZEEL","SUNTV","PVRINOX","NETWORK18","TV18BRDCST","NAZARA","SAREGAMA"],
    "PSU Bank":    ["SBIN","BANKBARODA","PNB","CANBK","UNIONBANK","INDIANB","BANKINDIA","IOB","CENTRALBK","UCOBANK","MAHABANK"],
    "Fin Service": ["HDFCBANK","ICICIBANK","SBIN","BAJFINANCE","KOTAKBANK","AXISBANK","BAJAJFINSV","HDFCLIFE","SBILIFE","SHRIRAMFIN","CHOLAFIN","ICICIGI","ICICIPRULI","PFC","RECLTD","MUTHOOTFIN"],
}
# Best-effort direct index quote symbols (Fyers format). Only a few of these
# are likely to actually resolve — that's expected, see the note above.
SECTOR_INDEX_FYERS_SYMBOL = {
    "Bank": "NSE:NIFTYBANK-INDEX", "IT": "NSE:CNXIT-INDEX", "Auto": "NSE:CNXAUTO-INDEX",
    "Pharma": "NSE:CNXPHARMA-INDEX", "FMCG": "NSE:CNXFMCG-INDEX", "Metal": "NSE:CNXMETAL-INDEX",
    "Energy": "NSE:CNXENERGY-INDEX", "Realty": "NSE:CNXREALTY-INDEX", "Media": "NSE:CNXMEDIA-INDEX",
    "PSU Bank": "NSE:NIFTYPSUBANK-INDEX", "Fin Service": "NSE:CNXFINANCE-INDEX",
}
SECTOR_LABEL_FOR_XLSX = {  # what's shown in the "Index Symbol" column when we fall back to a proxy
    k: v.replace("NSE:", "").replace("-INDEX", "") for k, v in SECTOR_INDEX_FYERS_SYMBOL.items()
}

ALL_STOCK_SYMBOLS = sorted({sym for syms in SECTORS.values() for sym in syms})


def fyers_symbol(nse_symbol):
    return f"NSE:{nse_symbol}-EQ"


# ----------------------------------------------------------------------------
# FYERS CLIENT
# ----------------------------------------------------------------------------
def load_client():
    if not os.path.exists(TOKEN_FILE):
        raise SystemExit(f"No {TOKEN_FILE} found — run fyers_auth.py first.")
    token = open(TOKEN_FILE).read().strip()
    return fyersModel.FyersModel(client_id=APP_ID, token=token, log_path=".", log_level="ERROR")


def chunked(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def fetch_quotes(fyers, symbols):
    """Returns {symbol: {'ltp': float, 'prev_close': float or None}}. Skips symbols Fyers rejects."""
    out = {}
    for batch in chunked(symbols, 50):
        try:
            resp = fyers.quotes(data={"symbols": ",".join(batch)})
        except Exception as e:
            print(f"  quotes() call failed for batch starting {batch[0]}: {e}")
            continue
        if resp.get("s") != "ok":
            print(f"  quotes() batch error: {resp}")
            continue
        for item in resp.get("d", []):
            sym = item.get("n") or item.get("symbol")
            v = item.get("v", {})
            if item.get("s") != "ok" or not v:
                continue
            ltp = v.get("lp")
            prev_close = v.get("prev_close_price") or v.get("pdc") or v.get("prev_close")
            if ltp is None:
                continue
            out[sym] = {"ltp": float(ltp), "prev_close": float(prev_close) if prev_close else None}
    return out


# ----------------------------------------------------------------------------
# ROLLING CLOSE HISTORY (self-built, so weekly/monthly refs don't depend on
# Fyers' historical-index endpoint, which is unreliable for non-F&O indices)
# ----------------------------------------------------------------------------
def load_history():
    if os.path.exists(CLOSE_HISTORY_PATH):
        with open(CLOSE_HISTORY_PATH) as f:
            return json.load(f)
    return {}


def save_history(history):
    with open(CLOSE_HISTORY_PATH, "w") as f:
        json.dump(history, f)


def update_history(history, key, price, today_str):
    history.setdefault(key, {})[today_str] = price


def lookback_price(history, key, days_back, today):
    """Nearest available close at or before (today - days_back), searching up to 5 days earlier."""
    series = history.get(key, {})
    if not series:
        return None
    target = today - dt.timedelta(days=days_back)
    for delta in range(0, 6):
        d = (target - dt.timedelta(days=delta)).isoformat()
        if d in series:
            return series[d]
    return None


def most_recent_before(history, key, today_str):
    series = history.get(key, {})
    dates = sorted(d for d in series if d < today_str)
    return series[dates[-1]] if dates else None


# ----------------------------------------------------------------------------
# MAIN SYNC PASS
# ----------------------------------------------------------------------------
def run_once():
    fyers = load_client()
    history = load_history()
    today = dt.date.today()
    today_str = today.isoformat()

    print(f"[{dt.datetime.now().strftime('%H:%M:%S')}] Fetching stock quotes...")
    stock_quotes = fetch_quotes(fyers, [fyers_symbol(s) for s in ALL_STOCK_SYMBOLS])
    print(f"  got {len(stock_quotes)} / {len(ALL_STOCK_SYMBOLS)} stock quotes")

    print("Attempting direct sector index quotes (most will fail — that's expected)...")
    index_quotes = fetch_quotes(fyers, list(SECTOR_INDEX_FYERS_SYMBOL.values()))
    print(f"  got {len(index_quotes)} / {len(SECTOR_INDEX_FYERS_SYMBOL)} direct index quotes")

    # --- update rolling history + build constituent rows ---
    constituents_out = []
    sector_pct_from_constituents = {s: [] for s in SECTORS}

    for sector, syms in SECTORS.items():
        for sym in syms:
            fsym = fyers_symbol(sym)
            q = stock_quotes.get(fsym)
            if not q:
                continue
            key = f"stock:{sym}"
            update_history(history, key, q["ltp"], today_str)
            prev_d = most_recent_before(history, key, today_str) or q["prev_close"] or q["ltp"]
            prev_w = lookback_price(history, key, 7, today) or prev_d
            prev_m = lookback_price(history, key, 30, today) or prev_d
            constituents_out.append({
                "sector": sector, "symbol": sym,
                "prevD": round(prev_d, 2), "prevW": round(prev_w, 2), "prevM": round(prev_m, 2),
                "ltp": round(q["ltp"], 2),
            })
            if prev_d:
                sector_pct_from_constituents[sector].append((q["ltp"] - prev_d) / prev_d * 100)

    # --- sector-level rows: real index quote if we got one, else the proxy ---
    sectors_out = []
    for sector in SECTORS:
        fsym = SECTOR_INDEX_FYERS_SYMBOL[sector]
        q = index_quotes.get(fsym)
        key = f"index:{sector}"
        if q:
            update_history(history, key, q["ltp"], today_str)
            prev_d = most_recent_before(history, key, today_str) or q["prev_close"] or q["ltp"]
            prev_w = lookback_price(history, key, 7, today) or prev_d
            prev_m = lookback_price(history, key, 30, today) or prev_d
            sectors_out.append({
                "sector": sector, "indexSymbol": SECTOR_LABEL_FOR_XLSX[sector],
                "prevD": round(prev_d, 2), "prevW": round(prev_w, 2), "prevM": round(prev_m, 2),
                "ltp": round(q["ltp"], 2),
            })
        else:
            # proxy: equal-weighted average %change of the sector's constituents,
            # expressed on a synthetic 100-base so the existing %chg formulas
            # (ltp/prev - 1) reproduce the exact same number either way.
            pct_list = sector_pct_from_constituents[sector]
            if not pct_list:
                continue  # no data at all this run; leave existing values alone downstream
            avg_pct = sum(pct_list) / len(pct_list)
            sectors_out.append({
                "sector": sector, "indexSymbol": SECTOR_LABEL_FOR_XLSX[sector] + " (proxy)",
                "prevD": 100.00, "prevW": 100.00, "prevM": 100.00,
                "ltp": round(100 * (1 + avg_pct / 100), 2),
            })

    save_history(history)

    # --- write JSON for the web app ---
    with open(JSON_OUTPUT_PATH, "w") as f:
        json.dump({"sectors": sectors_out, "constituents": constituents_out}, f, indent=None)
    print(f"Wrote {JSON_OUTPUT_PATH}")

    # --- write into the Excel workbook, matching rows by name (not fixed row #s) ---
    if os.path.exists(EXCEL_PATH):
        update_excel(sectors_out, constituents_out)
        print(f"Updated {EXCEL_PATH}")
    else:
        print(f"({EXCEL_PATH} not found next to this script — skipping Excel update, JSON still written)")


def update_excel(sectors_out, constituents_out):
    wb = openpyxl.load_workbook(EXCEL_PATH)

    ss = wb["Sector Summary"]
    sector_row = {}
    for row in ss.iter_rows(min_row=4, max_row=14):
        name = row[0].value
        if name:
            sector_row[name] = row[0].row
    for s in sectors_out:
        r = sector_row.get(s["sector"])
        if not r:
            continue
        ss.cell(row=r, column=3, value=s["prevD"])
        ss.cell(row=r, column=4, value=s["prevW"])
        ss.cell(row=r, column=5, value=s["prevM"])
        ss.cell(row=r, column=6, value=s["ltp"])

    cst = wb["Constituents"]
    const_row = {}
    for row in cst.iter_rows(min_row=2):
        sector, symbol = row[0].value, row[1].value
        if sector and symbol:
            const_row[(sector, symbol)] = row[0].row
        if row[0].value is None:
            break
    for c in constituents_out:
        r = const_row.get((c["sector"], c["symbol"]))
        if not r:
            continue
        cst.cell(row=r, column=3, value=c["prevD"])
        cst.cell(row=r, column=4, value=c["prevW"])
        cst.cell(row=r, column=5, value=c["prevM"])
        cst.cell(row=r, column=6, value=c["ltp"])

    wb.save(EXCEL_PATH)


def in_market_hours():
    now = dt.datetime.now().time()
    return MARKET_OPEN <= now <= MARKET_CLOSE


def main():
    if RUN_ONCE:
        run_once()
        return
    print("Starting sync loop. Ctrl+C to stop.")
    while True:
        if in_market_hours():
            try:
                run_once()
            except Exception as e:
                print("Error during sync pass:", e)
        else:
            print(f"[{dt.datetime.now().strftime('%H:%M:%S')}] Outside market hours, sleeping...")
        time.sleep(REFRESH_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
