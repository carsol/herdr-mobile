"""Optional shared-passcode auth.

Set HERDR_MOBILE_PASSCODE to require a passcode. The session cookie is an HMAC
derived from the passcode, so it needs no server-side state and survives
restarts; changing the passcode invalidates every cookie.
"""

import hashlib
import hmac
import os
from http.cookies import SimpleCookie

PASSCODE = os.environ.get("HERDR_MOBILE_PASSCODE", "")
COOKIE = "herdr_mobile"


def enabled() -> bool:
    return bool(PASSCODE)


def token() -> str:
    return hmac.new(PASSCODE.encode(), b"herdr-mobile-session-v1", hashlib.sha256).hexdigest()


def check_passcode(candidate: str) -> bool:
    return hmac.compare_digest(candidate.encode(), PASSCODE.encode())


def is_authed(headers) -> bool:
    if not enabled():
        return True
    c = SimpleCookie(headers.get("Cookie", ""))
    got = c[COOKIE].value if COOKIE in c else ""
    return hmac.compare_digest(got, token())


def set_cookie_header(secure: bool) -> str:
    flags = "; HttpOnly; SameSite=Lax; Path=/; Max-Age=31536000"
    if secure:
        flags += "; Secure"
    return f"{COOKIE}={token()}{flags}"
