"""Real local servers for the launcher and idle tests."""

import http.server
import socket
import threading
from collections.abc import Iterator
from contextlib import contextmanager

from waitress.server import create_server

from sheet_dj.config import Config
from sheet_dj.server import HOST, create_app


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind((HOST, 0))
        port: int = sock.getsockname()[1]
    return port


@contextmanager
def our_app_on(port: int) -> Iterator[None]:
    """The real app, served by waitress, as the launcher finds it."""
    server = create_server(create_app(Config(port=port)), host=HOST, port=port)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        yield
    finally:
        server.close()
        thread.join(timeout=5)


@contextmanager
def other_program_on(port: int, status: int, body: bytes) -> Iterator[None]:
    """Some other web server that happens to hold the port."""

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = http.server.ThreadingHTTPServer((HOST, port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
