"""
rrg.py
------
Relative Rotation Graph calculations.

An RRG plots each sector against a benchmark (NIFTY 50) on two axes:

    RS-Ratio     x-axis   is the sector relatively strong or weak?
    RS-Momentum  y-axis   is that relative strength improving or deteriorating?

Both are normalised around 100, so the crosshair at (100, 100) is the benchmark
itself and the four quadrants read:

    Leading    ratio > 100, momentum > 100   strong and still improving
    Weakening  ratio > 100, momentum < 100   strong but losing momentum
    Lagging    ratio < 100, momentum < 100   weak and still deteriorating
    Improving  ratio < 100, momentum > 100   weak but recovering

The idealised rotation is clockwise: Leading -> Weakening -> Lagging ->
Improving -> Leading. It is an idealisation, not a rule.

THE MATHS  (following the supplied reference document)

    RS_t          = 100 * S_t / B_t                      relative strength
    RS-Ratio_t    = 100 * EMA(RS, n) / EMA(EMA(RS, n), n)
    RS-Momentum_t = 100 * RS-Ratio_t / EMA(RS-Ratio, n)

This is the widely used *approximation* of JdK's proprietary RS-Ratio /
RS-Momentum, not the vendor formula, and the reference document is explicit that
it should be described as such. The quadrant boundaries at exactly 100 are the
part that carries the meaning; the absolute distance from 100 is not comparable
with a commercial RRG platform's numbers.

A consequence worth knowing: momentum is a ratio of an already double-smoothed
series to its own EMA, so it varies over a much narrower band than the ratio
axis (typically ~1/3 the spread). The chart therefore scales each axis
independently around 100 rather than forcing a square. Quadrants are unaffected.

WHERE THE PRICES COME FROM

Yahoo carries daily bars for only three of the eleven NSE sector indices, so a
daily series is not available for all of them. Hourly data *is* available for
every one, two years deep, so every series here is built the same way:

    2y of 1-hour bars  ->  last bar of each IST trading day  =  daily close
                       ->  last daily close of each ISO week =  weekly close

Resampling was validated against the real daily bars on the three indices that
have both: median deviation 0.05%, worst 0.7%. The drift exists because the
final hourly bar closes a few minutes before the official 15:30 close.

Using one method for all twelve series matters more than that last 0.05%: the
reference document requires the same timeframe and the same treatment for every
sector, and mixing real daily bars for three with resampled bars for eight would
break the comparison the whole chart rests on.
"""

import time
import datetime as dt
import urllib.parse
import concurrent.futures

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
SPARK_URL = "https://query2.finance.yahoo.com/v7/finance/spark"
HISTORY_RANGE = "2y"
HISTORY_INTERVAL = "1h"
BATCH = 20

# Smoothing. Weekly n=10 is the documented standard starting point; daily is
# noisier, so it gets a longer window as the reference document suggests.
SMOOTHING = {"weekly": 10, "daily": 20}
DEFAULT_TAIL = 12
MAX_TAIL = 30

QUADRANTS = ("Leading", "Weakening", "Lagging", "Improving")

_cache = {}
_CACHE_TTL = 120          # seconds; a refresh inside this window is served warm


# ---------------------------------------------------------------------------
# fetching
# ---------------------------------------------------------------------------
def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def _fetch_batch(get_json, symbols):
    qs = urllib.parse.urlencode({"symbols": ",".join(symbols),
                                 "range": HISTORY_RANGE, "interval": HISTORY_INTERVAL})
    for attempt in range(3):
        try:
            data = get_json(f"{SPARK_URL}?{qs}")
            break
        except Exception:
            if attempt == 2:
                return {}
            time.sleep(1.0 * (attempt + 1))
    out = {}
    for item in (data.get("spark", {}).get("result") or []):
        try:
            resp = item["response"][0]
        except (KeyError, IndexError):
            continue
        ts = resp.get("timestamp") or []
        closes = (resp.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
        daily = {}
        for t, c in zip(ts, closes):
            if c is None:
                continue
            daily[dt.datetime.fromtimestamp(t, IST).date()] = float(c)
        if len(daily) > 30:
            out[item["symbol"]] = daily
    return out


def fetch_daily_closes(get_json, symbols):
    """{yahoo_symbol: {date: close}} - two years of daily closes, resampled from hourly."""
    symbols = sorted({s for s in symbols if s})
    out = {}
    batches = list(_chunks(symbols, BATCH))
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        for res in ex.map(lambda b: _fetch_batch(get_json, b), batches):
            out.update(res)
    return out


# ---------------------------------------------------------------------------
# maths
# ---------------------------------------------------------------------------
def ema(values, n):
    k = 2.0 / (n + 1)
    out, e = [], None
    for v in values:
        e = v if e is None else v * k + e * (1 - k)
        out.append(e)
    return out


def to_weekly(dates, values):
    """Last observation of each ISO week."""
    wk = {}
    for d, v in zip(dates, values):
        wk[d.isocalendar()[:2]] = (d, v)
    pairs = [wk[k] for k in sorted(wk)]
    return [p[0] for p in pairs], [p[1] for p in pairs]


def rrg_series(sec_closes, bench_closes, timeframe="weekly", n=None):
    """
    -> (dates, rs_ratio[], rs_momentum[]) aligned on dates both series share.
    Returns ([], [], []) when there is not enough history to smooth.
    """
    n = n or SMOOTHING.get(timeframe, 10)
    dates = sorted(set(sec_closes) & set(bench_closes))
    if len(dates) < n * 3:
        return [], [], []

    rs = [100.0 * sec_closes[d] / bench_closes[d] for d in dates]
    if timeframe == "weekly":
        dates, rs = to_weekly(dates, rs)
    if len(dates) < n * 2 + 2:
        return [], [], []

    e1 = ema(rs, n)
    e2 = ema(e1, n)
    ratio = [100.0 * a / b if b else 100.0 for a, b in zip(e1, e2)]
    er = ema(ratio, n)
    mom = [100.0 * a / b if b else 100.0 for a, b in zip(ratio, er)]
    return dates, ratio, mom


def quadrant_of(ratio, mom):
    if ratio >= 100 and mom >= 100:
        return "Leading"
    if ratio >= 100 and mom < 100:
        return "Weakening"
    if ratio < 100 and mom < 100:
        return "Lagging"
    return "Improving"


def heading_of(tail):
    """Compass bearing of the last leg, in degrees clockwise from north (up)."""
    if len(tail) < 2:
        return None
    import math
    dx = tail[-1]["x"] - tail[-2]["x"]
    dy = tail[-1]["y"] - tail[-2]["y"]
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return None
    return round((math.degrees(math.atan2(dx, dy)) + 360) % 360, 1)


# ---------------------------------------------------------------------------
# assembly
# ---------------------------------------------------------------------------
def build(get_json, members, bench_symbol, bench_label,
          timeframe="weekly", tail=DEFAULT_TAIL, asof=None):
    """
    members      [{"name","symbol","label","tv"}]  symbol = yahoo symbol
    bench_symbol yahoo symbol of the benchmark
    -> payload dict
    """
    tail = max(2, min(int(tail or DEFAULT_TAIL), MAX_TAIL))
    n = SMOOTHING.get(timeframe, 10)

    wanted = [m["symbol"] for m in members] + [bench_symbol]
    closes = fetch_daily_closes(get_json, wanted)
    bench = closes.get(bench_symbol) or {}

    points, skipped = [], []
    for m in members:
        sec = closes.get(m["symbol"])
        if not sec or not bench:
            skipped.append(m["name"])
            continue
        dates, ratio, mom = rrg_series(sec, bench, timeframe, n)
        if not dates:
            skipped.append(m["name"])
            continue
        cut = max(0, len(dates) - tail)
        pts = [{"d": dates[i].isoformat(), "x": round(ratio[i], 3), "y": round(mom[i], 3)}
               for i in range(cut, len(dates))]
        points.append({
            "name": m["name"],
            "label": m.get("label") or m["name"],
            "tv": m.get("tv"),
            "ratio": pts[-1]["x"],
            "mom": pts[-1]["y"],
            "quadrant": quadrant_of(pts[-1]["x"], pts[-1]["y"]),
            "heading": heading_of(pts),
            "tail": pts,
        })

    points.sort(key=lambda p: -p["ratio"])
    last_date = max((p["tail"][-1]["d"] for p in points), default=None)
    return {
        "generated_at": (asof or dt.datetime.now()).isoformat(timespec="seconds"),
        "as_of": last_date,
        "benchmark": bench_label,
        "timeframe": timeframe,
        "smoothing": n,
        "tail": tail,
        "method": ("RS = 100*S/B; RS-Ratio = 100*EMA(RS,n)/EMA(EMA(RS,n),n); "
                   "RS-Momentum = 100*RS-Ratio/EMA(RS-Ratio,n). RRG-style "
                   "approximation, not the proprietary JdK formula."),
        "source": "Yahoo 2y hourly, resampled to daily then weekly closes",
        "skipped": skipped,
        "points": points,
    }


def cached_build(key, fn):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < _CACHE_TTL:
        return hit[1]
    val = fn()
    _cache[key] = (time.time(), val)
    return val
