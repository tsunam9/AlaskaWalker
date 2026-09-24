#!/usr/bin/env python3
"""Numinar mock backend entrypoint."""

from werkzeug.serving import WSGIRequestHandler, run_simple

from mock import config, create_app
from mock.ws import WebSocketInterceptHandlerMixin

app = create_app()


class NuminarRequestHandler(WebSocketInterceptHandlerMixin, WSGIRequestHandler):
    pass


if __name__ == "__main__":
    print(
        f"[numinar-mock] listening on {config.HOST}:{config.PORT} "
        f"access_ttl={config.ACCESS_TTL_S}s",
        flush=True,
    )
    run_simple(config.HOST, config.PORT, app, threaded=True,
               request_handler=NuminarRequestHandler)
