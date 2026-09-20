"""
diagnose.py
-----------
Run this when the dashboard shows "NSE unreachable" or "No data yet".

It walks the same path app.py takes, one step at a time, and says exactly which
step fails and what to do about it. It changes nothing and needs no arguments:

    python diagnose.py
"""

import gzip
import json
import socket
import ssl
import sys
import urllib.error
import urllib.request

sys.path.insert(0, ".")
try:
    from app import (NSE_HOME, NSE_ALL_INDICES, _NSE_NAV, _NSE_API, TIMEOUT,
                     _nse_opener, UA)
except Exception as e:                                    # pragma: no cover
    sys.exit(f"Could not import app.py - run this from the project folder.  ({e})")

OK, BAD, WARN = "  [ok]  ", "  [FAIL]", "  [warn]"
hints = []


def step(label, fn):
    try:
        detail = fn()
        print(f"{OK} {label}" + (f" - {detail}" if detail else ""))
        return True
    except Exception as e:
        print(f"{BAD} {label}")
        print(f"         {type(e).__name__}: {e}")
        explain(e)
        return False


def explain(e):
    s = f"{type(e).__name__}: {e}".lower()
    if "certificate" in s or "ssl" in s:
        hints.append(
            "TLS certificate verification failed. Usually antivirus or a company\n"
            "     network inspecting HTTPS, or a Python install without root\n"
            "     certificates. Try:  pip install --upgrade certifi\n"
            "     On a managed/office laptop this is often deliberate - try a home\n"
            "     network or a phone hotspot to confirm.")
    elif "name or service" in s or "getaddrinfo" in s or "name resolution" in s:
        hints.append(
            "DNS could not resolve nseindia.com. The machine is offline, or a\n"
            "     DNS/content filter is blocking it. Try opening\n"
            "     https://www.nseindia.com in a browser on that machine.")
    elif "timed out" in s or "timeout" in s:
        hints.append(
            "The connection opened but NSE never answered. Usually a firewall\n"
            "     silently dropping traffic, or NSE rate-limiting this IP.\n"
            "     Wait a minute and retry; if it persists, try another network.")
    elif "403" in s or "401" in s:
        hints.append(
            "NSE refused the request (403/401). NSE blocks traffic it thinks is\n"
            "     automated, and that decision is per-IP. A VPN, a shared office\n"
            "     network or a data-centre IP will often be refused.\n"
            "     Try a normal home connection or a phone hotspot.")
    elif "connection refused" in s or "unreachable" in s:
        hints.append(
            "The network refused the connection outright - typically a proxy or\n"
            "     firewall. If the machine needs a proxy, set it before starting:\n"
            "       set HTTPS_PROXY=http://user:pass@proxyhost:port")


print("\nEnvironment")
print(f"  Python {sys.version.split()[0]}  on  {sys.platform}")
print(f"  OpenSSL {ssl.OPENSSL_VERSION}")
try:
    import certifi
    print(f"  certifi {certifi.__version__}")
except Exception:
    print("  certifi not installed")
for var in ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY"):
    import os
    if os.environ.get(var) or os.environ.get(var.lower()):
        print(f"  {var}={os.environ.get(var) or os.environ.get(var.lower())}")

print("\nReaching NSE")


def dns():
    return ", ".join(sorted({a[4][0] for a in socket.getaddrinfo("www.nseindia.com", 443)}))


def tcp():
    s = socket.create_connection(("www.nseindia.com", 443), timeout=TIMEOUT)
    s.close()
    return "port 443 open"


def tls():
    ctx = ssl.create_default_context()
    with socket.create_connection(("www.nseindia.com", 443), timeout=TIMEOUT) as raw:
        with ctx.wrap_socket(raw, server_hostname="www.nseindia.com") as s:
            cert = s.getpeercert()
            issuer = dict(x[0] for x in cert["issuer"]).get("organizationName", "?")
            return f"certificate issued by {issuer}"


def homepage():
    req = urllib.request.Request(NSE_HOME, headers=_NSE_NAV)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return f"HTTP {r.status}"


ok = step("DNS resolves www.nseindia.com", dns)
ok = step("TCP connect to port 443", tcp) and ok
ok = step("TLS handshake", tls) and ok
ok = step("NSE homepage responds", homepage) and ok

if ok:
    def api():
        op = _nse_opener()                       # primes the cookies, as app.py does
        req = urllib.request.Request(NSE_ALL_INDICES, headers=_NSE_API)
        with op.open(req, timeout=TIMEOUT) as r:
            raw = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
        n = len(json.loads(raw).get("data", []))
        if not n:
            raise RuntimeError("the API answered but returned no index rows")
        return f"{n} indices returned"
    ok = step("NSE index API (with cookies)", api) and ok

print("\nReaching Yahoo (sparklines and the RRG only)")


def yahoo():
    req = urllib.request.Request(
        "https://query2.finance.yahoo.com/v7/finance/spark?symbols=%5ENSEI&range=1d&interval=5m",
        headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
    json.loads(raw)
    return "HTTP 200"


yok = step("Yahoo spark API", yahoo)

print()
if ok and yok:
    print("Everything the dashboard needs is reachable from this machine.")
    print("If the page still says 'NSE unreachable', press Refresh - the message")
    print("may be left over from an earlier failed attempt.")
else:
    if ok and not yok:
        print("NSE works, Yahoo does not: prices and percentages will be correct,")
        print("but sparklines and the rotation page will be empty.")
    for h in hints:
        print(f"\n  -> {h}")
print()
