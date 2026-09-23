"""Mock-wide constants. TTLs mirror the stock client's cookie config
(config/auth.ts:12-25) — the real server-side lifetimes are UNCONFIRMED,
the client trusts the JWT exp claim."""

import os

# Mock-only signing key. The stock client never verifies the signature
# (jwt-decode), and this key must never sign anything a real backend accepts.
SECRET = "patriot-mock-not-a-real-secret"

ACCESS_TTL_S = int(os.environ.get("PM_ACCESS_TTL_S", "900"))
REFRESH_TTL_S = int(os.environ.get("PM_REFRESH_TTL_S", str(15 * 24 * 3600)))
WS_TOKEN_TTL_S = int(os.environ.get("PM_WS_TOKEN_TTL_S", "300"))  # [H]
HOST = os.environ.get("PM_HOST", "0.0.0.0")
PORT = int(os.environ.get("PM_PORT", "19001"))

# Dashboard (/__mock/*) Basic auth. The /api/* surface is unaffected — stock
# app traffic authenticates with Bearer tokens, not browser credentials.
DASH_USER = os.environ.get("PM_DASH_USER", "admin")
DASH_PASS = os.environ.get("PM_DASH_PASS", "testpass123")
