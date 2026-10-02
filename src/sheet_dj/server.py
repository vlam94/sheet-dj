"""Create the app and serve it on this machine only."""

import logging
import sys
import webbrowser
from collections.abc import Sequence
from logging.handlers import RotatingFileHandler
from pathlib import Path

from flask import Flask
from platformdirs import user_log_dir
from waitress.server import create_server

from sheet_dj import views
from sheet_dj.config import Config
from sheet_dj.library import Library

logger = logging.getLogger(__name__)

HOST = "127.0.0.1"  # this machine only: the app has no login
NO_BROWSER_FLAG = "--no-browser"  # the launcher opens the browser itself
LOG_FILE_NAME = "server.log"
LOG_MAX_BYTES = 1_000_000
LOG_BACKUPS = 2


def create_app(config: Config | None = None) -> Flask:
    """Build the app with its own library."""
    config = config or Config.from_env()
    app = Flask(__name__)
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


def main(argv: Sequence[str] | None = None) -> int:
    """Serve in the foreground; open the page in the browser unless `--no-browser` is given."""
    args = sys.argv[1:] if argv is None else argv
    config = Config.from_env()
    configure_logging()
    try:
        server = create_server(create_app(config), host=HOST, port=config.port)
    except OSError:
        # Another copy won the port between the launcher's check and now; that copy serves.
        logger.exception("Cannot listen on %s:%s", HOST, config.port)
        return 1
    if NO_BROWSER_FLAG not in args:
        # The socket is already listening, so the browser's first request waits for run() below.
        webbrowser.open(f"http://{HOST}:{config.port}/")
    server.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
