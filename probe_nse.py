"""
probe_nse.py
------------
Run this when diagnose.py reports "403 Forbidden" from NSE.

A 403 with a healthy network means NSE's bot protection refused this client, not
that the site is unreachable. That decision can be made on the IP address, on the
TLS fingerprint of whatever is making the request, or on the HTTP headers. Those
need different answers, so this tries several different clients against the same
URL and reports which ones NSE accepts.

    python probe_nse.py

Reads one public page. Sends no credentials. Changes nothing.
"""

import http.client
import json
import shutil
import ssl
import subprocess
import sys
import urllib.request

sys.path.insert(0, ".")
try:
    from app import NSE_HOME, _NSE_NAV, TIMEOUT, UA, _nse_ssl_context
except Exception as e:
    sys.exit(f"Run this from the project folder.  ({e})")

HOST = "www.nseindia.com"
results = {}


def record(name, ok, detail):
    results[name] = ok
    print(f"  {'[ok]  ' if ok else '[FAIL]'} {name}")
    print(f"         {detail}")


# 1. exactly what app.py does today -----------------------------------------
def probe_urllib():
    try:
        req = urllib.request.Request(NSE_HOME, headers=_NSE_NAV)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return True, f"HTTP {r.status}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


# 2. same request, but with a browser-like TLS cipher order ------------------
#    Akamai fingerprints the ClientHello. Python's default cipher list differs
#    from Chrome's, and the order is part of the fingerprint.
CHROME_CIPHERS = (
    "ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:"
    "ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:"
    "ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:"
    "ECDHE-RSA-AES128-SHA:ECDHE-RSA-AES256-SHA:AES128-GCM-SHA256:"
    "AES256-GCM-SHA384:AES128-SHA:AES256-SHA"
)


def chrome_context():
    ctx = ssl.create_default_context()
    ctx.set_ciphers(CHROME_CIPHERS)
    try:
        ctx.set_alpn_protocols(["http/1.1"])
    except NotImplementedError:
        pass
    return ctx


def probe_cipher_order():
    try:
        conn = http.client.HTTPSConnection(HOST, 443, timeout=TIMEOUT,
                                           context=chrome_context())
        # keep-alive and browser header order; urllib forces Connection: close,
        # which no real browser sends on a first navigation
        headers = dict(_NSE_NAV)
        headers["Connection"] = "keep-alive"
        conn.request("GET", "/", headers=headers)
        r = conn.getresponse()
        r.read()
        conn.close()
        return r.status == 200, f"HTTP {r.status}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


# 2b. classical key-exchange groups, no post-quantum hybrid ------------------
#     OpenSSL 3.5 (Python 3.14) offers X25519MLKEM768 by default, which changes the
#     ClientHello a lot. OpenSSL 3.0 (Python 3.12) does not offer it at all and is
#     accepted. This is the fix app.py now applies.
def probe_classical_groups():
    ctx = ssl.create_default_context()
    if not hasattr(ctx, "set_groups"):
        return None, ("this Python cannot pin TLS groups (needs 3.13+), and so was "
                      "never offering post-quantum ones either")
    try:
        ctx.set_groups("X25519:P-256:P-384")
    except Exception as e:
        return False, f"could not pin groups: {type(e).__name__}: {e}"
    try:
        op = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))
        req = urllib.request.Request(NSE_HOME, headers=_NSE_NAV)
        with op.open(req, timeout=TIMEOUT) as r:
            return r.status == 200, f"HTTP {r.status}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


# 2c. exactly what app.py does now -------------------------------------------
def probe_app_fixed():
    try:
        op = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=_nse_ssl_context()))
        req = urllib.request.Request(NSE_HOME, headers=_NSE_NAV)
        with op.open(req, timeout=TIMEOUT) as r:
            return r.status == 200, f"HTTP {r.status}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


# 3. curl.exe - a completely different TLS stack (Schannel or its own) -------
def probe_curl():
    exe = shutil.which("curl")
    if not exe:
        return None, "curl not found on PATH"
    try:
        out = subprocess.run(
            [exe, "-sS", "-o", "NUL" if sys.platform == "win32" else "/dev/null",
             "-w", "%{http_code}", "--max-time", str(TIMEOUT),
             "-H", f"User-Agent: {UA}",
             "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
             "-H", "Accept-Language: en-GB,en;q=0.9",
             NSE_HOME],
            capture_output=True, text=True, timeout=TIMEOUT + 10)
        code = (out.stdout or "").strip()
        return code == "200", f"HTTP {code or '?'} {(out.stderr or '').strip()[:60]}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


# 4. requests, if it happens to be installed ---------------------------------
def probe_requests():
    try:
        import requests
    except ImportError:
        return None, "requests not installed (pip install requests)"
    try:
        r = requests.get(NSE_HOME, headers=_NSE_NAV, timeout=TIMEOUT)
        return r.status_code == 200, f"HTTP {r.status_code}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


print(f"\nPython {sys.version.split()[0]}   OpenSSL {ssl.OPENSSL_VERSION}")
try:
    import socket as _sock
    with _sock.create_connection((HOST, 443), timeout=TIMEOUT) as _raw:
        with ssl.create_default_context().wrap_socket(_raw, server_hostname=HOST) as _t:
            _grp = _t.group() if hasattr(_t, "group") else "unknown (needs Python 3.13+)"
            print(f"Default handshake: {_t.version()}  {_t.cipher()[0]}  key exchange {_grp}")
except Exception as _e:
    print(f"Default handshake: could not measure ({type(_e).__name__})")
print(f"Asking {NSE_HOME} the same question several different ways\n")

for name, fn in (("app.py's plain client (urllib defaults)", probe_urllib),
                 ("classical TLS groups, no post-quantum", probe_classical_groups),
                 ("app.py as it is now patched", probe_app_fixed),
                 ("browser cipher order + keep-alive", probe_cipher_order),
                 ("curl.exe (different TLS stack)", probe_curl),
                 ("requests library", probe_requests)):
    ok, detail = fn()
    if ok is None:
        print(f"  [skip] {name}\n         {detail}")
        continue
    record(name, ok, detail)

print()
good = [k for k, v in results.items() if v]
if not results:
    print("Nothing could be tested.")
elif not good:
    print("Every client was refused, including curl's separate TLS stack.")
    print("That points at the IP address rather than the client: NSE is refusing")
    print("this connection whatever asks. Options:")
    print("  - try a phone hotspot to confirm it is the address")
    print("  - some Indian ISPs are refused by NSE while others are not; a VPN set")
    print("    to an Indian city often works where the bare ISP does not")
elif len(good) == len(results):
    print("Everything succeeded now. The earlier 403 was most likely temporary")
    print("rate-limiting. Start the dashboard again and it should work.")
else:
    print("Some clients are accepted and some are refused, so this is NOT an IP")
    print("block - NSE is fingerprinting the client. Accepted:")
    for g in good:
        print(f"  - {g}")
    if results.get("app.py as it is now patched"):
        print("\nThe patched app.py client is accepted - 'python app.py' should now work.")
    else:
        print("\nThe patched client was still refused. Send this output back.")
print()
