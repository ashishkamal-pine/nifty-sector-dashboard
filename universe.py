"""
universe.py
-----------
Single source of truth for the sector universe: which sectors exist, which stocks
belong to each, and which Yahoo Finance symbol quotes each sector index.

app.py fetches sector membership LIVE from NSE at runtime, so NSE is authoritative.
The SECTORS dict below is only the offline fallback, refreshed from NSE on 2026-09-17.
"""

SECTORS = {
    'Bank'       : ["HDFCBANK","ICICIBANK","SBIN","AXISBANK","KOTAKBANK","INDUSINDBK","PNB","FEDERALBNK","YESBANK","IDFCFIRSTB","CANBK","BANKBARODA","UNIONBANK","AUBANK"],
    'IT'         : ["TCS","INFY","TECHM","COFORGE","HCLTECH","OFSS","WIPRO","PERSISTENT","LTM","MPHASIS"],
    'Auto'       : ["M&M","TVSMOTOR","TMPV","MARUTI","HEROMOTOCO","SONACOMS","EICHERMOT","BAJAJ-AUTO","ASHOKLEY","MOTHERSON","BHARATFORG","BOSCHLTD","UNOMINDA","TIINDIA","EXIDEIND"],
    'Pharma'     : ["DIVISLAB","LAURUSLABS","DRREDDY","SUNPHARMA","TORNTPHARM","GLAND","AUROPHARMA","WOCKPHARMA","ALKEM","ZYDUSLIFE","BIOCON","MANKIND","IPCALAB","LUPIN","CIPLA","SAILIFE","GLENMARK","PPLPHARMA","AJANTPHARM","ABBOTINDIA"],
    'FMCG'       : ["EMAMILTD","ITC","HINDUNILVR","TATACONSUM","BRITANNIA","NESTLEIND","VBL","MARICO","PATANJALI","COLPAL","GODREJCP","RADICO","DABUR","UNITDSPR","UBL"],
    'Metal'      : ["TATASTEEL","WELCORP","HINDALCO","HINDCOPPER","SAIL","HINDZINC","ADANIENT","JSWSTEEL","NATIONALUM","JSL","VEDL","JINDALSTEL","APLAPOLLO","LLOYDSME","NMDC"],
    'Energy'     : ["RELIANCE","BHEL","POWERINDIA","ONGC","GVT&D","CGPOWER","NTPC","ADANIPOWER","POWERGRID","ADANIENSOL","ABB","SIEMENS","COALINDIA","SUZLON","TATAPOWER","CASTROLIND","BPCL","ADANIGREEN","NHPC","OIL","HINDPETRO","IOC","ENRIN","JPPOWER","AEGISLOG","JSWENERGY","GAIL","NLCINDIA","INOXWIND","RPOWER","THERMAX","PETRONET","ATGL","TORNTPOWER","CESC","IGL","NAVA","NTPCGREEN","SJVN","MGL"],
    'Realty'     : ["LODHA","DLF","ANANTRAJ","GODREJPROP","PRESTIGE","OBEROIRLTY","PHOENIXLTD","BRIGADE","ABREL","SOBHA"],
    'Media'      : ["PFOCUS","ZEEL","PVRINOX","NAZARA","SAREGAMA","TIPSMUSIC","NETWORK18","SUNTV","HATHWAY","DBCORP"],
    'PSU Bank'   : ["SBIN","PNB","BANKINDIA","CANBK","MAHABANK","BANKBARODA","UNIONBANK","INDIANB","CENTRALBK","UCOBANK","PSB","IOB"],
    'Fin Service': ["HDFCBANK","ICICIBANK","BSE","SBIN","AXISBANK","HDFCLIFE","BAJFINANCE","KOTAKBANK","SHRIRAMFIN","CHOLAFIN","SBILIFE","JIOFIN","MUTHOOTFIN","PFC","LICHSGFIN","MFSL","SBICARD","ICICIGI","RECLTD","BAJAJFINSV"],
}

# Yahoo Finance symbols for the real NSE sector indices (no API key required).
# NOTE: Fin Service uses NIFTY_FIN_SERVICE.NS, NOT ^CNXFIN. ^CNXFIN resolves to
# 'NIFTY FINSRV25 50' - a different, narrower index, ~8% away in level, which made
# its sparkline and hover prices disagree with the NSE figures beside them.
# Yahoo carries live levels for all 11, but daily *history* for only a few
# (typically NSEBANK / CNXIT / CNXPHARMA); app.py falls back to a constituent
# average for weekly/monthly on the rest.
YAHOO_INDEX = {
    'Bank'       : '^NSEBANK',
    'IT'         : '^CNXIT',
    'Auto'       : '^CNXAUTO',
    'Pharma'     : '^CNXPHARMA',
    'FMCG'       : '^CNXFMCG',
    'Metal'      : '^CNXMETAL',
    'Energy'     : '^CNXENERGY',
    'Realty'     : '^CNXREALTY',
    'Media'      : '^CNXMEDIA',
    'PSU Bank'   : '^CNXPSUBANK',
    'Fin Service': 'NIFTY_FIN_SERVICE.NS',
}


# Official NSE index names, as returned by /api/allIndices. This is the PRIMARY
# sector source: that one endpoint carries last / previousClose / oneWeekAgoVal /
# oneMonthAgoVal for every index, so daily, weekly and monthly are all official
# values with no approximation. YAHOO_INDEX above is only the fallback.
NSE_INDEX = {
    "Bank":        "NIFTY BANK",
    "IT":          "NIFTY IT",
    "Auto":        "NIFTY AUTO",
    "Pharma":      "NIFTY PHARMA",
    "FMCG":        "NIFTY FMCG",
    "Metal":       "NIFTY METAL",
    "Energy":      "NIFTY ENERGY",
    "Realty":      "NIFTY REALTY",
    "Media":       "NIFTY MEDIA",
    "PSU Bank":    "NIFTY PSU BANK",
    "Fin Service": "NIFTY FINANCIAL SERVICES",
}

# Index names for the CONSTITUENT endpoint
# (/api/NextApi/apiClient/marketWatchApi?functionName=getIndicesData&symbol=...).
# NOTE: this endpoint uses a DIFFERENT name space from /api/allIndices - notably
# "NIFTY FIN SERVICE" here vs "NIFTY FINANCIAL SERVICES" there. Verified 2026-09-17.
NSE_CONSTITUENT_INDEX = {
    "Bank":        "NIFTY BANK",
    "IT":          "NIFTY IT",
    "Auto":        "NIFTY AUTO",
    "Pharma":      "NIFTY PHARMA",
    "FMCG":        "NIFTY FMCG",
    "Metal":       "NIFTY METAL",
    "Energy":      "NIFTY ENERGY",
    "Realty":      "NIFTY REALTY",
    "Media":       "NIFTY MEDIA",
    "PSU Bank":    "NIFTY PSU BANK",
    "Fin Service": "NIFTY FIN SERVICE",
}

# SECTORS above is now only a FALLBACK used when NSE's constituent endpoint is
# unreachable. NSE is authoritative for membership at runtime.

# TradingView chart symbols. Clicking a row deep-links to
# https://in.tradingview.com/chart/?symbol=<this>
# No API and no key involved - it is only a URL. All 12 verified against
# TradingView's own symbol search on 2026-09-19 (171/171 stocks, 11/11 indices).
TRADINGVIEW_INDEX = {
    "Bank":        "NSE:BANKNIFTY",
    "IT":          "NSE:CNXIT",
    "Auto":        "NSE:CNXAUTO",
    "Pharma":      "NSE:CNXPHARMA",
    "FMCG":        "NSE:CNXFMCG",
    "Metal":       "NSE:CNXMETAL",
    "Energy":      "NSE:CNXENERGY",
    "Realty":      "NSE:CNXREALTY",
    "Media":       "NSE:CNXMEDIA",
    "PSU Bank":    "NSE:CNXPSUBANK",
    "Fin Service": "NSE:CNXFINANCE",   # the full index, not the 25/50 variant
}

# NSE ticker -> TradingView ticker, where they differ. Ampersands pass through
# unchanged (M&M, GVT&D both resolve); only the hyphen needs remapping.
TRADINGVIEW_OVERRIDES = {"BAJAJ-AUTO": "BAJAJ_AUTO"}


def tradingview_symbol(sym):
    """Bare NSE stock symbol -> fully qualified TradingView symbol."""
    return "NSE:" + TRADINGVIEW_OVERRIDES.get(sym, sym)


# Symbols where the NSE ticker above no longer maps 1:1 to a Yahoo listing.
# Value None = Yahoo has no listing; the stock is skipped deliberately, not lost
# silently. Checked 2026-09-17 against Yahoo's symbol search.
# Empty as of 2026-09-17: every symbol in NSE's current lists resolves on Yahoo
# (171/171 verified). The earlier TATAMOTORS / LTIM / TV18BRDCST entries are gone
# because NSE no longer lists those tickers in these indices at all.
SYMBOL_OVERRIDES = {}


def yahoo_stock(sym):
    """Bare NSE symbol -> Yahoo symbol, or None if Yahoo has no listing for it."""
    if sym in SYMBOL_OVERRIDES:
        mapped = SYMBOL_OVERRIDES[sym]
        return mapped + ".NS" if mapped else None
    return sym + ".NS"


ALL_STOCKS = sorted({s for syms in SECTORS.values() for s in syms})
