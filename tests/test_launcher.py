import json
import socket
import sys
import threading
import time
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from waitress.server import create_server

from servers import free_port, other_program_on, our_app_on
from sheet_dj import launcher
from sheet_dj.config import Config
from sheet_dj.launcher import PortState
from sheet_dj.server import HOST, create_app, log_path


@dataclass
class Recorder:
    """Stands in for the parts of the launcher that touch the desktop."""

    spawned: int = 0
    opened: list[str] = field(default_factory=list)
    dialogs: list[str] = field(default_factory=list)

    def spawn(self) -> None:
        self.spawned += 1

    def open_browser(self, url: str) -> None:
        self.opened.append(url)

    def show(self, message: str) -> None:
        self.dialogs.append(message)

    def launch(self, port: int, start_timeout: float = 0.3) -> int:
        return launcher.launch(
            Config(port=port),
            spawn=self.spawn,
            open_browser=self.open_browser,
            show=self.show,
            start_timeout=start_timeout,
        )


def test_probe_sees_a_free_port() -> None:
    assert launcher.probe(free_port()) is PortState.FREE


def test_probe_sees_this_app() -> None:
    port = free_port()
    with our_app_on(port):
        assert launcher.probe(port) is PortState.OURS


@pytest.mark.parametrize(
    ("status", "body"),
    [
        pytest.param(404, b"not found", id="other-page"),
        pytest.param(200, b'{"app": "something-else"}', id="other-app"),
        pytest.param(200, b"<html>hello</html>", id="not-json"),
        pytest.param(200, json.dumps(["sheet-dj"]).encode(), id="not-an-object"),
    ],
)
def test_probe_sees_another_program(status: int, body: bytes) -> None:
    port = free_port()
    with other_program_on(port, status, body):
        assert launcher.probe(port) is PortState.FOREIGN


def test_probe_sees_a_silent_program() -> None:
    with socket.socket() as sock:  # listens but never answers
        sock.bind((HOST, 0))
        sock.listen()
        port: int = sock.getsockname()[1]
        assert launcher.probe(port, timeout=0.2) is PortState.FOREIGN


def test_launch_attaches_to_a_running_app() -> None:
    port = free_port()
    recorder = Recorder()
    with our_app_on(port):
        assert recorder.launch(port) == 0
    assert (recorder.spawned, recorder.opened, recorder.dialogs) == (
        0,
        [launcher.app_url(port)],
        [],
    )


def test_launch_starts_the_server_then_opens_the_browser() -> None:
    port = free_port()
    recorder = Recorder()
    servers: list[threading.Thread] = []

    def spawn() -> None:
        recorder.spawn()
        server = create_server(create_app(Config(port=port)), host=HOST, port=port)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        servers.append(thread)

    result = launcher.launch(
        Config(port=port),
        spawn=spawn,
        open_browser=recorder.open_browser,
        show=recorder.show,
        start_timeout=10,
    )
    assert result == 0
    assert (recorder.spawned, recorder.opened, recorder.dialogs) == (
        1,
        [launcher.app_url(port)],
        [],
    )


@dataclass(frozen=True)
class Failure:
    """One launcher catalogue entry: how to provoke it and what the dialog must say."""

    message: Callable[[int], str]  # the dialog text, given the port
    spawns: int
    provoke: Callable[[int], AbstractContextManager[None]]


FAILURES = [
    pytest.param(
        Failure(
            message=lambda port: launcher.E20_PORT_TAKEN.format(port=port),
            spawns=0,
            provoke=lambda port: other_program_on(port, 404, b"not found"),
        ),
        id="E20",
    ),
    pytest.param(
        Failure(
            message=lambda port: launcher.E21_NOT_STARTED.format(log=log_path()),
            spawns=1,
            provoke=lambda port: nullcontext(),
        ),
        id="E21",
    ),
]


@pytest.mark.parametrize("failure", FAILURES)
def test_launcher_failures_show_a_dialog_and_leave_things_alone(failure: Failure) -> None:
    port = free_port()
    recorder = Recorder()
    with failure.provoke(port):
        result = recorder.launch(port)
        assert result == 1
        # One dialog with the plain message, no browser tab, and the right number of spawns.
        assert recorder.dialogs == [failure.message(port)]
        assert recorder.opened == []
        assert recorder.spawned == failure.spawns


def test_e20_names_the_port_and_what_to_do() -> None:
    message = launcher.E20_PORT_TAKEN.format(port=5118)
    assert "port 5118" in message
    assert "click the icon again" in message


def test_e21_names_the_log_file() -> None:
    assert "server.log" in launcher.E21_NOT_STARTED.format(log=Path("x") / "server.log")


def test_wait_until_ready_gives_up_after_the_timeout() -> None:
    now = [0.0]

    def clock() -> float:
        return now[0]

    def sleep(seconds: float) -> None:
        now[0] += seconds

    assert launcher.wait_until_ready(free_port(), 1.0, sleep=sleep, clock=clock) is False
    assert now[0] >= 1.0


@pytest.mark.parametrize(
    ("frozen", "expected"),
    [
        pytest.param(False, ["py", "-m", "sheet_dj.launcher", "--serve"], id="from-source"),
        pytest.param(True, ["py", "--serve"], id="packaged"),
    ],
)
def test_server_command(frozen: bool, expected: list[str]) -> None:
    assert launcher.server_command(frozen, "py") == expected


def test_spawn_options_detach_on_windows_with_no_console() -> None:
    options = launcher.spawn_options("win32")
    assert options["creationflags"] == launcher.DETACHED_PROCESS | launcher.CREATE_NO_WINDOW
    assert "start_new_session" not in options


def test_spawn_options_detach_on_posix() -> None:
    options = launcher.spawn_options("linux")
    assert options["start_new_session"] is True
    assert "creationflags" not in options


def test_spawned_server_answers_and_stops_when_terminated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    port = free_port()
    monkeypatch.setenv("SHEETDJ_PORT", str(port))
    # Keep the spawned server's log out of the real per-user log folder.
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    process = launcher.spawn_server()
    try:
        assert launcher.wait_until_ready(port, 60)
        assert launcher.probe(port) is PortState.OURS
    finally:
        process.terminate()
        process.wait(timeout=10)
    deadline = time.monotonic() + 10
    while launcher.probe(port) is not PortState.FREE and time.monotonic() < deadline:
        time.sleep(0.1)
    assert launcher.probe(port) is PortState.FREE


def test_a_windowless_program_gets_standard_streams(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdout", None)
    monkeypatch.setattr("sys.stderr", None)
    launcher.ensure_standard_streams()
    print("must not fail", file=sys.stderr)
    assert sys.stdout is not None
