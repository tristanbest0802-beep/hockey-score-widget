"""Local HTTP server for the OBS browser source: /widget (page) and /state (JSON)."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable

from hockey_widget.widget_state import LOGO_TYPES

WIDGET_HTML = (Path(__file__).parent / "widget.html").read_bytes()


def make_server(port: int, get_state: Callable[[], dict],
                get_logo: Callable[[str], Path | None] = lambda _abbrev: None) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            if path in ("/", "/widget"):
                self._send(200, "text/html; charset=utf-8", WIDGET_HTML)
            elif path == "/state":
                self._send(200, "application/json", json.dumps(get_state()).encode("utf-8"))
            elif path.startswith("/logo/") and path[6:].isalnum() and len(path) <= 10:
                logo = get_logo(path[6:])
                try:
                    self._send(200, LOGO_TYPES[logo.suffix.lower()], logo.read_bytes())
                except (AttributeError, KeyError, OSError):  # no custom logo, wrong type, file gone
                    self._send(404, "text/plain", b"not found")
            else:
                self._send(404, "text/plain", b"not found")

        def _send(self, code: int, kind: str, body: bytes) -> None:
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args) -> None:  # silence: OBS polls every second
            pass

    # Bound to localhost only: nothing on the network can reach it.
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def start_server(port: int, get_state: Callable[[], dict],
                 get_logo: Callable[[str], Path | None] = lambda _abbrev: None) -> ThreadingHTTPServer:
    server = make_server(port, get_state, get_logo)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
