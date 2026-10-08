"""Fyers login: get today's access token and cache it in .fyers_token.json.

Opens the Fyers authorization page in the debuggable Chrome (port 9222),
waits for the redirect to https://127.0.0.1/?auth_code=..., and exchanges
the code for an access token. Tokens expire daily (around 6 AM IST).
"""
import json
import os
import time
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv
from fyers_apiv3 import fyersModel

ROOT = Path(__file__).resolve().parent.parent
TOKEN_FILE = ROOT / ".fyers_token.json"
load_dotenv(ROOT / ".env")

APP_ID = os.environ["FYERS_APP_ID"]
SECRET = os.environ["FYERS_SECRET_KEY"]
REDIRECT = os.environ.get("FYERS_REDIRECT_URI", "https://127.0.0.1")


def _session():
    return fyersModel.SessionModel(
        client_id=APP_ID, secret_key=SECRET, redirect_uri=REDIRECT,
        response_type="code", grant_type="authorization_code",
    )


def cached_token():
    if TOKEN_FILE.exists():
        data = json.loads(TOKEN_FILE.read_text())
        if data.get("date") == date.today().isoformat():
            return data["access_token"]
    return None


def _codes_from_tabs() -> list:
    """auth_codes visible in any Chrome tab (the 127.0.0.1 redirect shows as an error page,
    so Playwright's page.url misses it, but Chrome's target list keeps the real URL).
    Newest first by the JWT issue time."""
    import base64
    import urllib.request
    try:
        tabs = json.loads(urllib.request.urlopen("http://127.0.0.1:9222/json", timeout=5).read())
    except Exception:
        return []
    out = []
    for t in tabs:
        qs = parse_qs(urlparse(t.get("url", "")).query)
        if "auth_code" in qs:
            code = qs["auth_code"][0]
            try:
                body = code.split(".")[1]
                iat = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))).get("iat", 0)
            except Exception:
                iat = 0
            out.append((iat, code, t.get("id")))
    return [c for c in sorted(out, reverse=True)]


def exchange(auth_code: str) -> str:
    session = _session()
    session.set_token(auth_code)
    resp = session.generate_token()
    if "access_token" not in resp:
        raise RuntimeError(f"Token exchange failed: {resp.get('message', resp)}")
    TOKEN_FILE.write_text(json.dumps({"date": date.today().isoformat(),
                                      "access_token": resp["access_token"]}))
    return resp["access_token"]


def login_via_browser(timeout_s: int = 300) -> str:
    from playwright.sync_api import sync_playwright

    session = _session()
    url = session.generate_authcode()
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        page = browser.contexts[0].new_page()
        try:
            page.goto(url)
        except Exception:
            pass  # redirect to https://127.0.0.1 has no server behind it -- expected
        print("Fyers authorization page opened -- complete any prompts in the browser.")
        deadline = time.time() + timeout_s
        auth_code = None
        while time.time() < deadline:
            qs = parse_qs(urlparse(page.url).query)
            if "auth_code" in qs:
                auth_code = qs["auth_code"][0]
                break
            fresh = [c for iat, c, _ in _codes_from_tabs() if iat >= time.time() - timeout_s - 60]
            if fresh:
                auth_code = fresh[0]
                break
            page.wait_for_timeout(1000)
        page.close()
    if not auth_code:
        raise RuntimeError("Timed out waiting for Fyers redirect with auth_code")

    return exchange(auth_code)


def _b64(s: str) -> str:
    import base64
    return base64.b64encode(s.encode()).decode()


def totp_configured() -> bool:
    return all(os.environ.get(k) for k in ("FYERS_CLIENT_ID", "FYERS_PIN", "FYERS_TOTP_SECRET"))


def login_via_totp() -> str:
    """Headless login with the account's own TOTP (Fyers 'External 2FA TOTP'), no browser, no human.
    Needs FYERS_CLIENT_ID, FYERS_PIN, FYERS_TOTP_SECRET in .env. Read-only use: prices only."""
    import pyotp
    import requests
    s = requests.Session()
    base = "https://api-t2.fyers.in/vagator/v2"

    def post(url, **kw):
        r = s.post(url, timeout=30, **kw)
        try:
            j = r.json()
        except ValueError:
            raise RuntimeError(f"Fyers TOTP login: non-JSON reply from {url} ({r.status_code})")
        if r.status_code not in (200, 308) or j.get("s") == "error":     # token step answers 308 + Url
            raise RuntimeError(f"Fyers TOTP login failed at {url.rsplit('/', 1)[-1]}: {j.get('message', j)}")
        return j

    r1 = post(f"{base}/send_login_otp_v2", json={"fy_id": _b64(os.environ["FYERS_CLIENT_ID"]), "app_id": "2"})
    totp = pyotp.TOTP(os.environ["FYERS_TOTP_SECRET"])
    if totp.interval - time.time() % totp.interval < 5:      # code about to roll over: wait for the next one
        time.sleep(6)
    r2 = post(f"{base}/verify_otp", json={"request_key": r1["request_key"], "otp": totp.now()})
    r3 = post(f"{base}/verify_pin_v2", json={"request_key": r2["request_key"], "identity_type": "pin",
                                             "identifier": _b64(os.environ["FYERS_PIN"])})
    app, app_type = APP_ID.rsplit("-", 1)
    r4 = post("https://api-t1.fyers.in/api/v3/token",
              headers={"authorization": f"Bearer {r3['data']['access_token']}"},
              json={"fyers_id": os.environ["FYERS_CLIENT_ID"], "app_id": app, "redirect_uri": REDIRECT,
                    "appType": app_type, "code_challenge": "", "state": "canslim", "scope": "", "nonce": "",
                    "response_type": "code", "create_cookie": True})
    url = r4.get("Url") or (r4.get("data") or {}).get("auth") or ""
    code = parse_qs(urlparse(url).query).get("auth_code", [None])[0]
    if not code:
        raise RuntimeError("Fyers TOTP login: no auth_code in the token reply")
    return exchange(code)


def get_client() -> fyersModel.FyersModel:
    token = cached_token()
    if not token and totp_configured():
        try:
            token = login_via_totp()
            print("Fyers: logged in with TOTP (no browser needed).")
        except Exception as e:
            print(f"Fyers: TOTP login failed ({e}); falling back to the browser login.")
    token = token or login_via_browser()
    return fyersModel.FyersModel(client_id=APP_ID, token=token, is_async=False, log_path="")


if __name__ == "__main__":
    fyers = get_client()
    prof = fyers.get_profile()
    print("profile call:", prof.get("s"), prof.get("message", ""))
