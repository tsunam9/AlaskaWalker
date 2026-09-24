"""Mock-wide, environment-overridable settings."""

import os

SECRET = os.environ.get("PM_JWT_SECRET", "numinar-mock-not-a-real-secret")
AUDIENCE = "https://api.numinar.com"
ISSUER = "https://auth.numinar.com/"
CLIENT_ID = "329jKTvPKBUjOSnY9sYnf0m7Z0gkzTTm"
ACCESS_TTL_S = int(os.environ.get("PM_ACCESS_TTL_S", "900"))
REFRESH_TTL_S = int(os.environ.get("PM_REFRESH_TTL_S", str(30 * 24 * 3600)))
OTP_TTL_S = int(os.environ.get("PM_OTP_TTL_S", "900"))
HOST = os.environ.get("PM_HOST", "0.0.0.0")
PORT = int(os.environ.get("PM_PORT", "19002"))
DASH_USER = os.environ.get("PM_DASH_USER", "admin")
DASH_PASS = os.environ.get("PM_DASH_PASS", "testpass123")
