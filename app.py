"""
app.py
------
The whole thing, in one command:

    python app.py

Opens http://localhost:8765 in your browser. Click "Load Data" and it fetches live
NSE prices right then and redraws the board.

WHAT IT NEEDS
  - Python 3.7+
  - Nothing else. No pip install, no API key, no login, no token, no Excel.

HOW IT WORKS
  This script is both the web server and the data fetcher. It serves the dashboard at
  "/" and exposes "/api/live_data.json". When the browser hits that endpoint, THIS
  script goes and fetches from Yahoo Finance and returns the result.

  That indirection is the entire point. Yahoo does not send CORS headers, so a browser
  cannot call it directly — but Python can, because Python is not a browser. And since
  the dashboard is served from the same origin as the API, the browser never has to
  make a cross-origin request at all.

DATA SOURCE
  Yahoo Finance's public chart/spark endpoints. No key, no account, no expiry.
  Unofficial and delayed — fine for a sector board, not for trading decisions.
  See docs/live-data-options.md.
"""

import json
import gzip
import time
import datetime as dt
import urllib.parse
import urllib.request
import concurrent.futures
import http.cookiejar
import http.server
import socketserver
import webbrowser
import rrg
from universe import (SECTORS, YAHOO_INDEX, NSE_INDEX, NSE_CONSTITUENT_INDEX,
                      TRADINGVIEW_INDEX, ALL_STOCKS, yahoo_stock, tradingview_symbol)

PORT = 8765
HTML_FILE = "Sector_Performance_Board.html"
RRG_FILE = "RRG.html"
BENCHMARK = ("^NSEI", "NIFTY 50")     # RRG benchmark
SPARK_URL = "https://query2.finance.yahoo.com/v7/finance/spark"
BATCH_SIZE = 20           # symbols per request; 30+ returns HTTP 400
RANGE = "3mo"             # enough bars to derive weekly and monthly references

# Sparkline series, one per timeframe. The range/interval pairs matter: the narrower
# sector indices have NO daily bars on Yahoo, but they do have intraday and hourly,
# which is why monthly uses 1h rather than 1d.
SPARK_RANGES = {"d": ("1d", "5m"), "w": ("5d", "15m"), "m": ("1mo", "1h")}
SPARK_POINTS = 32         # downsample target; enough shape for a 100px sparkline
TIMEOUT = 25
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")   # both APIs reject bare clients

NSE_HOME = "https://www.nseindia.com/"
NSE_ALL_INDICES = "https://www.nseindia.com/api/allIndices"
NSE_CONSTITUENTS = ("https://www.nseindia.com/api/NextApi/apiClient/marketWatchApi"
                    "?functionName=getIndicesData&symbol=")


# ---------------------------------------------------------------------------
# Yahoo fetching
# ---------------------------------------------------------------------------
def _get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        raw = r.read()
    if r.headers.get("Content-Encoding") == "gzip":
        raw = gzip.decompress(raw)
    return json.loads(raw.decode("utf-8"))


def _chunked(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def fetch_bars(symbols, rng=RANGE):
    """
    Returns {yahoo_symbol: {"ltp": float, "prev_close": float|None,
                            "bars": [(date, close), ...] ascending}}.

    For stocks, one batched 3-month request returns the live price and ~65 daily bars,
    so daily / weekly / monthly all come from a single round trip.

    Note `prev_close` is only yesterday's close when rng == "1d"; over a longer range
    Yahoo reports the close at the START of that range instead.
    """
    out = {}
    for batch in _chunked(symbols, BATCH_SIZE):
        qs = urllib.parse.urlencode({"symbols": ",".join(batch), "range": rng, "interval": "1d"})
        data = None
        for attempt in range(3):                   # Yahoo 429s/502s are common and transient
            try:
                data = _get_json(f"{SPARK_URL}?{qs}")
                break
            except Exception as e:
                if attempt == 2:
                    print(f"  ! batch failed after 3 tries ({batch[0]}...): {e}")
                else:
                    time.sleep(1.5 * (attempt + 1))
        if data is None:
            continue
        for item in (data.get("spark", {}).get("result") or []):
            sym = item.get("symbol")
            try:
                resp = item["response"][0]
            except (KeyError, IndexError):
                continue
            meta = resp.get("meta", {})
            ts = resp.get("timestamp") or []
            closes = (resp.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
            bars = [
                (dt.datetime.fromtimestamp(t, dt.timezone.utc).date(), float(c))
                for t, c in zip(ts, closes) if c is not None
            ]
            if not bars:
                continue
            ltp = meta.get("regularMarketPrice")
            pc = meta.get("chartPreviousClose")
            out[sym] = {
                "ltp": float(ltp) if ltp is not None else bars[-1][1],
                "prev_close": float(pc) if pc is not None else None,
                "bars": bars,
            }
    return out


# ---------------------------------------------------------------------------
# NSE (primary sector source)
#
# /api/allIndices returns, for every index in one call:
#     last, previousClose, oneWeekAgoVal, oneMonthAgoVal
# i.e. official daily / weekly / monthly reference levels with no approximation.
# NSE rejects plain scripted clients, so this needs full browser-ish headers and a
# cookie primed from the homepage first.
# ---------------------------------------------------------------------------
_NSE_BASE = {
    "User-Agent": UA,
    "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "sec-ch-ua": '"Chromium";v="125", "Not.A/Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Connection": "keep-alive",
}
_NSE_NAV = dict(_NSE_BASE, **{
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Sec-Fetch-Dest": "document", "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none", "Upgrade-Insecure-Requests": "1",
})
_NSE_API = dict(_NSE_BASE, **{
    "Accept": "*/*",
    "Referer": "https://www.nseindia.com/market-data/live-market-indices",
    "Sec-Fetch-Dest": "empty", "Sec-Fetch-Mode": "cors", "Sec-Fetch-Site": "same-origin",
})


def _nse_opener():
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    req = urllib.request.Request(NSE_HOME, headers=_NSE_NAV)
    with op.open(req, timeout=TIMEOUT) as r:     # prime cookies
        r.read()
    return op


def fetch_nse_sectors(op):
    """
    {sector: {"ltp","prevD","prevW","prevM","indexName"}} for every sector,
    or {} if NSE is unreachable. One HTTP call (plus one to prime cookies).
    """
    req = urllib.request.Request(NSE_ALL_INDICES, headers=_NSE_API)
    with op.open(req, timeout=TIMEOUT) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
    rows = {i.get("index"): i for i in json.loads(raw).get("data", [])}

    out = {}
    for sector, name in NSE_INDEX.items():
        v = rows.get(name)
        if not v:
            continue
        ltp, p_d = v.get("last"), v.get("previousClose")
        p_w, p_m = v.get("oneWeekAgoVal"), v.get("oneMonthAgoVal")
        if not all(isinstance(x, (int, float)) and x for x in (ltp, p_d, p_w, p_m)):
            continue                              # incomplete -> let the fallback handle it
        out[sector] = {"ltp": float(ltp), "prevD": float(p_d),
                       "prevW": float(p_w), "prevM": float(p_m), "indexName": name}
    return out


def fetch_nse_constituents(op, index_name):
    """
    Authoritative live membership + prices for one sector index.

    Returns [{symbol, ltp, prevD, prevM}]. NSE gives previousClose (daily) and
    perChange30d (monthly) but carries NO weekly field for individual stocks, so
    prevM is reconstructed from the percentage and prevW is filled in from Yahoo
    afterwards.
    """
    url = NSE_CONSTITUENTS + urllib.parse.quote(index_name)
    req = urllib.request.Request(url, headers=dict(_NSE_API, **{
        "Referer": "https://www.nseindia.com/market-data/live-equity-market"}))
    with op.open(req, timeout=TIMEOUT) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
    rows = json.loads(raw)["data"]["data"]

    out = []
    for r_ in rows:
        if not r_.get("series"):
            continue                       # the index's own row, not a constituent
        sym, ltp, p_d = r_.get("symbol"), r_.get("lastPrice"), r_.get("previousClose")
        if not sym or not isinstance(ltp, (int, float)) or not isinstance(p_d, (int, float)):
            continue
        pm = r_.get("perChange30d")
        prev_m = ltp / (1 + pm / 100) if isinstance(pm, (int, float)) and pm != -100 else p_d
        out.append({"symbol": sym, "ltp": float(ltp),
                    "prevD": float(p_d), "prevM": float(prev_m)})
    return out


def _spark_series(symbols, rng, iv):
    """{symbol: [close, ...]} for one range/interval. Close-only, gaps dropped."""
    qs = urllib.parse.urlencode({"symbols": ",".join(symbols), "range": rng, "interval": iv})
    out = {}
    for attempt in range(3):
        try:
            data = _get_json(f"{SPARK_URL}?{qs}")
            break
        except Exception:
            if attempt == 2:
                return out
            time.sleep(1.0 * (attempt + 1))
    for item in (data.get("spark", {}).get("result") or []):
        try:
            resp = item["response"][0]
        except (KeyError, IndexError):
            continue
        closes = (resp.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
        vals = [float(c) for c in closes if c is not None]
        if len(vals) >= 2:
            out[item["symbol"]] = vals
    return out


def _downsample(vals, n=SPARK_POINTS):
    """Evenly thin a series to at most n points, always keeping the last one."""
    if len(vals) <= n:
        return [round(v, 2) for v in vals]
    step = (len(vals) - 1) / (n - 1)
    return [round(vals[int(round(i * step))], 2) for i in range(n)]


def fetch_sparks(symbols):
    """
    {symbol: {"d": [...], "w": [...], "m": [...]}} - one downsampled series per
    timeframe. Batched 20 symbols per request and threaded, so all three timeframes
    across ~180 symbols take about a second rather than thirty.
    """
    symbols = [s for s in symbols if s]
    jobs = [(key, chunk) for key in SPARK_RANGES for chunk in _chunked(symbols, BATCH_SIZE)]
    out = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(_spark_series, ch, *SPARK_RANGES[k]): k for k, ch in jobs}
        for fut in concurrent.futures.as_completed(futs):
            key = futs[fut]
            try:
                series = fut.result()
            except Exception:
                continue
            for sym, vals in series.items():
                out.setdefault(sym, {})[key] = _downsample(vals)
    return out


def references(bars):
    """
    Derive (prevD, prevW, prevM) from dated daily bars.

    Deliberately NOT using meta.chartPreviousClose: over a 3-month range that field is
    the close three months ago, not yesterday's.
    """
    last_date = bars[-1][0]

    def close_on_or_before(cutoff):
        for d, c in reversed(bars):
            if d <= cutoff:
                return c
        return None

    prev_d = close_on_or_before(last_date - dt.timedelta(days=1)) or bars[-1][1]
    prev_w = close_on_or_before(last_date - dt.timedelta(days=7)) or prev_d
    prev_m = close_on_or_before(last_date - dt.timedelta(days=30)) or prev_d
    return prev_d, prev_w, prev_m


def _mean(xs):
    return sum(xs) / len(xs) if xs else None


def _mean(xs):
    return sum(xs) / len(xs) if xs else None


def weekly_refs(symbols):
    """
    {symbol: prevW} from Yahoo. This is the ONE thing NSE does not provide for
    individual stocks, so Yahoo is used for nothing else at constituent level.
    """
    ymap = {}
    for sym in symbols:
        y = yahoo_stock(sym)
        if y:
            ymap.setdefault(y, sym)
    bars = fetch_bars(list(ymap))
    out = {}
    for ysym, data in bars.items():
        b = data["bars"]
        if not b:
            continue
        cutoff = b[-1][0] - dt.timedelta(days=7)
        for d, c in reversed(b):
            if d <= cutoff:
                out[ymap[ysym]] = c
                break
    return out


def build_payload():
    """
    Sectors and constituents both come from NSE, which is authoritative for index
    levels AND for index membership. Yahoo is used for exactly one thing: the weekly
    reference price of individual stocks, which NSE does not publish.

    Falls back to the older Yahoo-index + hardcoded-universe path if NSE is blocked.
    """
    started = dt.datetime.now()
    print(f"[{started:%H:%M:%S}] fetching from NSE...")

    # ---- sectors: official daily / weekly / monthly in one call ----
    try:
        op = _nse_opener()
        nse = fetch_nse_sectors(op)
        print(f"  NSE indices: {len(nse)}/{len(SECTORS)} (official D/W/M)")
    except Exception as e:
        op, nse = None, {}
        print(f"  ! NSE indices unreachable ({str(e)[:60]})")

    # ---- constituents: live membership + daily/monthly, per sector ----
    by_sector, nse_const_ok = {}, 0
    if op is not None:
        for sector, name in NSE_CONSTITUENT_INDEX.items():
            try:
                rows = fetch_nse_constituents(op, name)
                if rows:
                    by_sector[sector] = rows
                    nse_const_ok += 1
            except Exception as e:
                print(f"  ! constituents failed for {sector} ({str(e)[:40]})")
        print(f"  NSE constituents: {nse_const_ok}/{len(NSE_CONSTITUENT_INDEX)} sectors, "
              f"{sum(len(v) for v in by_sector.values())} rows")

    # ---- Yahoo: weekly reference only ----
    constituents, approx, weekly_missing = [], [], 0
    if by_sector:
        symbols = sorted({r["symbol"] for rows in by_sector.values() for r in rows})
        wk = weekly_refs(symbols)
        missing = [x for x in symbols if x not in wk]
        print(f"  Yahoo weekly refs: {len(wk)}/{len(symbols)} symbols" +
              (f"  ! no weekly for {len(missing)}: {', '.join(missing[:6])}"
               f"{'...' if len(missing) > 6 else ''}" if missing else ""))
        weekly_missing = len(missing)
        for sector, rows in by_sector.items():
            for r in rows:
                p_w = wk.get(r["symbol"]) or r["prevD"]     # no weekly -> daily
                constituents.append({
                    "sector": sector, "symbol": r["symbol"],
                    "prevD": round(r["prevD"], 2), "prevW": round(p_w, 2),
                    "prevM": round(r["prevM"], 2), "ltp": round(r["ltp"], 2),
                })
    else:
        # fallback: hardcoded universe, all prices and history from Yahoo
        print("  ! falling back to the hardcoded universe + Yahoo prices")
        stock_syms = [y for y in (yahoo_stock(x) for x in ALL_STOCKS) if y]
        stocks = fetch_bars(stock_syms)
        print(f"  got {len(stocks)}/{len(stock_syms)} stocks from Yahoo")
        for sector, syms in SECTORS.items():
            for sym in syms:
                y = yahoo_stock(sym)
                q = stocks.get(y) if y else None
                if not q:
                    continue
                p_d, p_w, p_m = references(q["bars"])
                constituents.append({
                    "sector": sector, "symbol": sym,
                    "prevD": round(p_d, 2), "prevW": round(p_w, 2),
                    "prevM": round(p_m, 2), "ltp": round(q["ltp"], 2),
                })

    # ---- assemble sector rows ----
    pct = {}
    for c in constituents:
        for key, field in (("w", "prevW"), ("m", "prevM")):
            if c[field]:
                pct.setdefault(c["sector"], {}).setdefault(key, []).append(
                    (c["ltp"] - c[field]) / c[field] * 100)

    idx_hist = idx_today = {}
    if len(nse) < len(SECTORS):                    # only pay for Yahoo indices if needed
        index_syms = [YAHOO_INDEX[x] for x in SECTORS]
        idx_hist = fetch_bars(index_syms)
        idx_today = fetch_bars(index_syms, rng="1d")

    sectors = []
    for sector, ysym in YAHOO_INDEX.items():
        n = nse.get(sector)
        if n:
            sectors.append({
                "sector": sector, "indexSymbol": n["indexName"], "approxWM": False,
                "prevD": round(n["prevD"], 2), "prevW": round(n["prevW"], 2),
                "prevM": round(n["prevM"], 2), "ltp": round(n["ltp"], 2),
            })
            continue
        today = idx_today.get(ysym)
        if not today:
            print(f"  ! no index quote for {sector} ({ysym}) - sector omitted")
            continue
        ltp = today["ltp"]
        prev_d = today.get("prev_close") or ltp
        bars = (idx_hist.get(ysym) or {}).get("bars") or []
        if len(bars) > 5:
            _, prev_w, prev_m = references(bars)
            is_approx = False
        else:
            is_approx = True
            aw = _mean((pct.get(sector) or {}).get("w") or [])
            am = _mean((pct.get(sector) or {}).get("m") or [])
            prev_w = ltp / (1 + aw / 100) if aw not in (None, -100) else prev_d
            prev_m = ltp / (1 + am / 100) if am not in (None, -100) else prev_d
            approx.append(sector)
        sectors.append({
            "sector": sector, "indexSymbol": ysym.lstrip("^") + ("*" if is_approx else ""),
            "approxWM": is_approx,
            "prevD": round(prev_d, 2), "prevW": round(prev_w, 2),
            "prevM": round(prev_m, 2), "ltp": round(ltp, 2),
        })

    # ---- sparkline series for every row, one per timeframe ----
    want = [YAHOO_INDEX[r["sector"]] for r in sectors]
    want += [yahoo_stock(c["symbol"]) for c in constituents]
    sparks = fetch_sparks(sorted({w for w in want if w}))
    for r in sectors:
        r["spark"] = sparks.get(YAHOO_INDEX[r["sector"]], {})
        r["tv"] = TRADINGVIEW_INDEX.get(r["sector"])
    for c in constituents:
        c["spark"] = sparks.get(yahoo_stock(c["symbol"]) or "", {})
        c["tv"] = tradingview_symbol(c["symbol"])
    with_spark = sum(1 for x in sectors + constituents if x["spark"].get("d"))
    print(f"  sparklines: {with_spark}/{len(sectors) + len(constituents)} rows")

    elapsed = (dt.datetime.now() - started).total_seconds()
    print(f"  built {len(sectors)} sectors / {len(constituents)} constituents in {elapsed:.1f}s")
    if approx:
        print(f"  * weekly/monthly averaged from constituents for: {', '.join(approx)}")
    return {
        "generated_at": started.isoformat(timespec="seconds"),
        "source": (("NSE (official)" if nse else "Yahoo (fallback)") +
                   (" + Yahoo (weekly refs)" if by_sector else " + Yahoo (prices)")),
        "source_sectors": "NSE allIndices (official)" if nse else "Yahoo (fallback)",
        "source_constituents": ("NSE live membership" if by_sector
                                else "hardcoded universe + Yahoo"),
        "weekly_missing": weekly_missing,
        "note": (("All sector figures are official NSE index values."
                  if not approx else
                  "* = weekly/monthly derived from constituent average (no index history)") +
                 (f"  |  {weekly_missing} stock(s) have no weekly reference; "
                  "their weekly shows the daily change" if weekly_missing else "")),
        "sectors": sectors,
        "constituents": constituents,
    }


# ---------------------------------------------------------------------------
# RRG
# ---------------------------------------------------------------------------
def build_rrg(scope="sectors", name=None, timeframe="weekly", tail=rrg.DEFAULT_TAIL,
              bench="nifty"):
    """
    scope="sectors"  -> the 11 sector indices vs NIFTY 50
    scope="sector"   -> one sector's constituents, vs NIFTY 50 or vs their own index
    """
    timeframe = "daily" if timeframe == "daily" else "weekly"

    if scope == "sector" and name in SECTORS:
        # authoritative membership when NSE is reachable, hardcoded list otherwise
        syms = None
        try:
            rows = fetch_nse_constituents(_nse_opener(), NSE_CONSTITUENT_INDEX[name])
            syms = [r["symbol"] for r in rows] or None
        except Exception as e:
            print(f"  ! RRG: live membership failed for {name} ({str(e)[:40]}) - using fallback")
        syms = syms or SECTORS[name]
        members = [{"name": x, "symbol": yahoo_stock(x), "label": x,
                    "tv": tradingview_symbol(x)} for x in syms]
        members = [m for m in members if m["symbol"]]
        if bench == "sector":
            bench_sym, bench_label = YAHOO_INDEX[name], NSE_INDEX[name]
        else:
            bench_sym, bench_label = BENCHMARK
        title = name
    else:
        scope, name = "sectors", None
        members = [{"name": s_, "symbol": YAHOO_INDEX[s_], "label": NSE_INDEX[s_],
                    "tv": TRADINGVIEW_INDEX[s_]} for s_ in SECTORS]
        bench_sym, bench_label = BENCHMARK
        title = "NSE sectors"

    started = dt.datetime.now()
    print(f"[{started:%H:%M:%S}] RRG {scope}"
          f"{'/' + name if name else ''} {timeframe} vs {bench_label}...")
    out = rrg.build(_get_json, members, bench_sym, bench_label, timeframe, tail)
    out["scope"] = scope
    out["sector"] = name
    out["title"] = title
    out["sectors"] = list(SECTORS)
    print(f"  {len(out['points'])} plotted, {len(out['skipped'])} skipped, "
          f"{(dt.datetime.now() - started).total_seconds():.1f}s")
    return out


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------
class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path

        if path in ("/", "/index.html"):
            return self._send_file(HTML_FILE, "text/html; charset=utf-8")

        if path in ("/rrg", "/rrg.html"):
            return self._send_file(RRG_FILE, "text/html; charset=utf-8")

        if path == "/api/rrg.json":
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            one = lambda k, d=None: (q.get(k) or [d])[0]
            key = (one("scope", "sectors"), one("name"), one("tf", "weekly"),
                   one("tail", str(rrg.DEFAULT_TAIL)), one("bench", "nifty"))
            fresh = one("force") in ("1", "true", "yes")
            try:
                make = lambda: build_rrg(scope=key[0], name=key[1], timeframe=key[2],
                                         tail=key[3], bench=key[4])
                payload = make() if fresh else rrg.cached_build(key, make)
                if fresh:
                    rrg.put_cache(key, payload)     # keep the warm copy in step
                body = json.dumps(payload).encode()
            except Exception as e:
                print("  ! RRG failed:", e)
                return self._send_json({"error": str(e)}, code=502)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return

        if path in ("/api/live_data.json", "/live_data.json"):
            try:
                body = json.dumps(build_payload()).encode()
            except Exception as e:
                print("  ! fetch failed:", e)
                return self._send_json({"error": str(e)}, code=502)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return

        return self.send_error(404)

    def _send_file(self, name, ctype):
        try:
            with open(name, "rb") as f:
                body = f.read()
        except FileNotFoundError:
            return self.send_error(404, f"{name} not found next to app.py")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass    # the fetch itself already logs; keep the console readable


class Server(socketserver.ThreadingTCPServer):
    # Deliberately NOT allow_reuse_address: on Windows that lets a second instance
    # bind the same port, leaving a stale server answering with old code. Better to
    # fail loudly with "Address already in use".
    daemon_threads = True


if __name__ == "__main__":
    url = f"http://localhost:{PORT}/"
    # 127.0.0.1, not "" — do not expose this on the local network.
    with Server(("127.0.0.1", PORT), Handler) as httpd:
        print(f"Dashboard running at {url}")
        print('Click "Load Data" in the page to pull fresh prices. Ctrl+C to stop.\n')
        try:
            webbrowser.open(url)
        except Exception:
            pass
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")
