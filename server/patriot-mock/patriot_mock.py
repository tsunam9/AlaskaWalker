#!/usr/bin/env python3
"""Patriot Grassroots / ValidNation mock backend — entrypoint.

Usage:  python3 patriot_mock.py
Env:    PM_HOST (default 0.0.0.0), PM_PORT (default 19001),
        PM_ACCESS_TTL_S (900), PM_REFRESH_TTL_S,
        PM_WS_TOKEN_TTL_S.

Wire contracts: see mock/__init__.py docstring and per-blueprint docstrings.
"""

from mock import config, create_app

app = create_app()

if __name__ == "__main__":
    print(f"[patriot-mock] listening on {config.HOST}:{config.PORT} "
          f"access_ttl={config.ACCESS_TTL_S}s refresh_ttl={config.REFRESH_TTL_S}s",
          flush=True)
    app.run(host=config.HOST, port=config.PORT)
