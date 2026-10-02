"""What the desktop icon runs: start the server if it is not running, then open the browser."""

import http.client
import json
import logging
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from collections.abc import Callable, Mapping, Sequence
from enum import Enum
from typing import Any

from sheet_dj import server
from sheet_dj.config import APP_NAME, Config

logger = logging.getLogger(__name__)

SERVE_FLAG = "--serve"  # run the server in this process instead of launching one
DIALOG_TITLE = "Sheet DJ"
PROBE_TIMEOUT = 5.0  # seconds; a busy server must not be mistaken for another program
START_TIMEOUT = 30.0  # seconds; the first start loads music21, which can be slow on Windows
POLL_INTERVAL = 0.25

E20_PORT_TAKEN = (
    "Sheet DJ could not start because another program is using port {port}. "
    "Close that program and click the icon again."
)
E21_NOT_STARTED = (
    "Sheet DJ did not start in time. Click the icon again. "
    "If it still does not open, send the file {log} to whoever set this up."
)

# Windows process-creation flags, written out because `subprocess` only has them on Windows.
DETACHED_PROCESS = 0x00000008
CREATE_NO_WINDOW = 0x08000000


class PortState(Enum):
    FREE = "free"  # nothing listens
    OURS = "ours"  # this app answers
    FOREIGN = "foreign"  # something else is there


def healthz_url(port: int) -> str:
    return f"http://{server.HOST}:{port}/healthz"


def app_url(port: int) -> str:
    return f"http://{server.HOST}:{port}/"


def probe(port: int, timeout: float = PROBE_TIMEOUT) -> PortState:
    """Find out who, if anyone, answers on `port`."""
    # An empty proxy map: a system proxy must never be asked about this machine.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(healthz_url(port), timeout=timeout) as response:
            body = json.loads(response.read(1024))
    except urllib.error.HTTPError:
        return PortState.FOREIGN
    except urllib.error.URLError as exc:
        refused = isinstance(exc.reason, ConnectionRefusedError)
        return PortState.FREE if refused else PortState.FOREIGN
    except (OSError, http.client.HTTPException, ValueError):
        return PortState.FOREIGN
    ours = isinstance(body, dict) and body.get("app") == APP_NAME
    return PortState.OURS if ours else PortState.FOREIGN


def server_command(frozen: bool, executable: str) -> list[str]:
    """The command that runs the server, from source or from the packaged program."""
    if frozen:
        return [executable, SERVE_FLAG]
    return [executable, "-m", "sheet_dj.launcher", SERVE_FLAG]


def spawn_options(platform: str) -> Mapping[str, Any]:
    """`Popen` options that detach the server from the launcher, with no console window."""
    options: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if platform == "win32":
        options["creationflags"] = DETACHED_PROCESS | CREATE_NO_WINDOW
    else:
        options["start_new_session"] = True
    return options


def spawn_server() -> subprocess.Popen[bytes]:
    """Start the server in the background; it outlives the launcher."""
    command = server_command(bool(getattr(sys, "frozen", False)), sys.executable)
    return subprocess.Popen(command, **spawn_options(sys.platform))


def wait_until_ready(
    port: int,
    timeout: float = START_TIMEOUT,
    *,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> bool:
    """Wait for this app to answer on `port`; False when `timeout` seconds pass first."""
    deadline = clock() + timeout
    while clock() < deadline:
        if probe(port) is PortState.OURS:
            return True
        sleep(POLL_INTERVAL)
    return False


def show_error(message: str) -> None:
    """Show `message` in a native dialog: the launcher has no page to show it on."""
    try:
        import tkinter
        from tkinter import messagebox
    except ImportError:
        logger.error("tkinter is missing; the message was: %s", message)
        return
    try:
        root = tkinter.Tk()
        root.withdraw()
        messagebox.showerror(DIALOG_TITLE, message, parent=root)
        root.destroy()
    except tkinter.TclError:  # no display
        logger.error("Cannot show a dialog; the message was: %s", message)


def launch(
    config: Config,
    *,
    spawn: Callable[[], object] = spawn_server,
    open_browser: Callable[[str], object] = webbrowser.open,
    show: Callable[[str], None] = show_error,
    start_timeout: float = START_TIMEOUT,
) -> int:
    """Open the app in the browser, starting the server first when needed. Returns an exit code."""
    state = probe(config.port)
    if state is PortState.FOREIGN:
        logger.error("Port %s is used by another program", config.port)
        show(E20_PORT_TAKEN.format(port=config.port))
        return 1
    if state is PortState.FREE:
        spawn()
        if not wait_until_ready(config.port, start_timeout):
            logger.error("The server did not answer within %s seconds", start_timeout)
            show(E21_NOT_STARTED.format(log=server.log_path()))
            return 1
    open_browser(app_url(config.port))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point of the icon (`sheet-dj`); with `--serve`, the server itself."""
    args = sys.argv[1:] if argv is None else argv
    if SERVE_FLAG in args:
        return server.main([server.NO_BROWSER_FLAG])
    server.configure_logging()
    return launch(Config.from_env())


if __name__ == "__main__":
    sys.exit(main())
