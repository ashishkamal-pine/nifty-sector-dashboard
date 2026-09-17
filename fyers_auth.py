"""
fyers_auth.py
-------------
Generates (or refreshes) your Fyers API access token.

Fyers access tokens expire once a day (they reset a little after midnight IST),
so you'll re-run this once each trading day before you start fyers_sync.py.

ONE-TIME SETUP (do this first):
1. Go to https://myapi.fyers.in/dashboard and create an app.
   - Redirect URL can be anything you control, even "https://google.com" —
     you're just reading the auth_code out of the redirected URL by hand below.
2. Copy the App ID (looks like "ABCD1234-100") and Secret Key into the
   CONFIG section below (or set them as environment variables, see bottom).

DAILY USE:
    python3 fyers_auth.py
Follow the printed URL, log in, and paste the redirected URL back in when asked.
This writes a fresh access_token.txt that fyers_sync.py reads automatically.
"""

import os
import re
from fyers_apiv3 import fyersModel

# ----------------------------------------------------------------------------
# CONFIG — fill these in, or set as environment variables of the same name
# ----------------------------------------------------------------------------
APP_ID = os.environ.get("FYERS_APP_ID", "YOUR_APP_ID-100")          # e.g. "ABCD1234-100"
SECRET_KEY = os.environ.get("FYERS_SECRET_KEY", "YOUR_SECRET_KEY")
REDIRECT_URI = os.environ.get("FYERS_REDIRECT_URI", "https://google.com")

TOKEN_FILE = "access_token.txt"


def main():
    if "YOUR_APP_ID" in APP_ID or "YOUR_SECRET_KEY" in SECRET_KEY:
        print("Fill in APP_ID / SECRET_KEY at the top of this file first "
              "(or set FYERS_APP_ID / FYERS_SECRET_KEY / FYERS_REDIRECT_URI env vars).")
        return

    session = fyersModel.SessionModel(
        client_id=APP_ID,
        redirect_uri=REDIRECT_URI,
        response_type="code",
        grant_type="authorization_code",
        secret_key=SECRET_KEY,
        state="sector_tool",
    )

    auth_url = session.generate_authcode()
    print("\n1. Open this URL, log in, and approve the app:\n")
    print(auth_url)
    print("\n2. You'll land on your redirect URL with '...&auth_code=XXXX&...' in the address bar.")
    redirected_url = input("3. Paste that full redirected URL here: ").strip()

    match = re.search(r"auth_code=([^&]+)", redirected_url)
    if not match:
        print("Couldn't find 'auth_code=' in what you pasted — paste the full URL from the address bar.")
        return
    auth_code = match.group(1)

    session.set_token(auth_code)
    response = session.generate_token()

    if response.get("s") != "ok" or "access_token" not in response:
        print("Token generation failed. Fyers said:")
        print(response)
        return

    access_token = response["access_token"]
    with open(TOKEN_FILE, "w") as f:
        f.write(access_token)

    print(f"\nAccess token saved to {TOKEN_FILE}. Good until it expires (usually next day, ~6am IST).")
    print("You can now run: python3 fyers_sync.py")


if __name__ == "__main__":
    main()
