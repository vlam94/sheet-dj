"""Create the app and serve it on this machine only."""

import logging
import webbrowser
from logging.handlers import RotatingFileHandler
from pathlib import Path

from flask import Flask
from platformdirs import user_log_dir
from waitress.server import create_server

from sheet_dj import views
from sheet_dj.config import Config
from sheet_dj.library import Library

HOST = "127.0.0.1"  # this machine only: the app has no login
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
        logging.getLogger(__name__).warning("Cannot write the log file; logging to the console.")
        return
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger().addHandler(handler)


def main() -> None:
    """Serve in the foreground and open the page in the browser."""
    config = Config.from_env()
    configure_logging()
    server = create_server(create_app(config), host=HOST, port=config.port)
    # The socket is already listening, so the browser's first request waits for run() below.
    webbrowser.open(f"http://{HOST}:{config.port}/")
    server.run()


if __name__ == "__main__":
    main()
