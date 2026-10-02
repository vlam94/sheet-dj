"""Create the app and serve it on this machine only."""

import logging
import sys
import webbrowser
from collections.abc import Sequence
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import cast

from flask import Flask
from platformdirs import user_log_dir
from waitress.channel import HTTPChannel
from waitress.server import BaseWSGIServer, MultiSocketServer, create_server

from sheet_dj import views
from sheet_dj.config import Config
from sheet_dj.idle import IdleWatchdog
from sheet_dj.library import Library

logger = logging.getLogger(__name__)

HOST = "127.0.0.1"  # this machine only: the app has no login
NO_BROWSER_FLAG = "--no-browser"  # the launcher opens the browser itself
LOG_FILE_NAME = "server.log"
LOG_MAX_BYTES = 1_000_000
LOG_BACKUPS = 2


def create_app(config: Config | None = None, watchdog: IdleWatchdog | None = None) -> Flask:
    """Build the app with its own library; every request counts as activity for `watchdog`."""
    config = config or Config.from_env()
    app = Flask(__name__)
    if watchdog:
        app.before_request(watchdog.touch)
    views.init_app(app, config, Library(config.max_files))
    return app


def log_path() -> Path:
    """Where the server log lives, per user."""
    return Path(user_log_dir("sheet_dj", appauthor=False)) / LOG_FILE_NAME


def configure_logging() -> None:
    """Log to a rotating file; fall back to the console when the folder cannot be written."""
    logging.basicConfig(level=logging.INFO)
    try:
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            path, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUPS, encoding="utf-8"
        )
    except OSError:
        logger.warning("Cannot write the log file; logging to the console.")
        return
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger().addHandler(handler)


def stop(server: BaseWSGIServer | MultiSocketServer) -> None:
    """Stop serving through waitress's own API (a signal would be a hard kill on Windows)."""
    logger.info("No activity for a while; stopping")
    if isinstance(server, BaseWSGIServer):
        # waitress keeps serving until every connection is gone, and a browser holds one open.
        channels = cast("dict[int, HTTPChannel]", server.active_channels)  # the stub is wrong
        for channel in list(channels.values()):
            channel.will_close = True
    server.close()


def main(argv: Sequence[str] | None = None) -> int:
    """Serve in the foreground; open the page in the browser unless `--no-browser` is given."""
    args = sys.argv[1:] if argv is None else argv
    config = Config.from_env()
    configure_logging()
    watchdog = IdleWatchdog(config.idle_minutes * 60, lambda: stop(server))
    try:
        server = create_server(create_app(config, watchdog), host=HOST, port=config.port)
    except OSError:
        # Another copy won the port between the launcher's check and now; that copy serves.
        logger.exception("Cannot listen on %s:%s", HOST, config.port)
        return 1
    if NO_BROWSER_FLAG not in args:
        # The socket is already listening, so the browser's first request waits for run() below.
        webbrowser.open(f"http://{HOST}:{config.port}/")
    watchdog.start()
    server.run()
    logger.info("Stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
