import http.client
import threading
import time
from pathlib import Path

import pytest
from waitress.server import create_server

from servers import free_port
from sheet_dj import launcher
from sheet_dj.config import Config
from sheet_dj.idle import IdleWatchdog
from sheet_dj.launcher import PortState
from sheet_dj.server import HOST, create_app, stop


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_not_expired_while_activity_continues() -> None:
    clock = FakeClock()
    watchdog = IdleWatchdog(60, lambda: None, clock=clock)
    clock.now = 59
    assert not watchdog.expired()
    watchdog.touch()
    clock.now = 118
    assert not watchdog.expired()


def test_expires_after_the_timeout_without_activity() -> None:
    clock = FakeClock()
    watchdog = IdleWatchdog(60, lambda: None, clock=clock)
    clock.now = 60
    assert watchdog.expired()


def test_stopped_watchdog_never_calls_back() -> None:
    calls: list[str] = []
    watchdog = IdleWatchdog(0.05, lambda: calls.append("idle"))
    watchdog.stop()
    watchdog.start().join(timeout=2)
    time.sleep(0.15)
    assert calls == []


class Serving:
    """The real app under waitress with a short idle timeout, as `server.main` sets it up."""

    def __init__(self, timeout: float) -> None:
        self.port = free_port()
        self.watchdog = IdleWatchdog(timeout, lambda: stop(self.server))
        self.server = create_server(
            create_app(Config(port=self.port), self.watchdog), host=HOST, port=self.port
        )
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def start(self) -> None:
        self.thread.start()
        self.watchdog.start()

    def post_heartbeat(self) -> int:
        connection = http.client.HTTPConnection(HOST, self.port, timeout=5)
        try:
            connection.request("POST", "/heartbeat")
            return connection.getresponse().status
        finally:
            connection.close()


def test_heartbeats_keep_the_server_alive_and_silence_stops_it() -> None:
    serving = Serving(timeout=0.6)
    serving.start()
    for _ in range(8):  # 1.6 s, well past the timeout: only the heartbeats keep it up
        assert serving.post_heartbeat() == 204
        time.sleep(0.2)
    assert launcher.probe(serving.port) is PortState.OURS
    serving.thread.join(timeout=10)  # now nobody calls: waitress must stop by itself
    assert not serving.thread.is_alive()
    assert launcher.probe(serving.port) is PortState.FREE


def test_server_stops_even_if_a_browser_connection_is_still_open() -> None:
    serving = Serving(timeout=0.5)
    serving.start()
    connection = http.client.HTTPConnection(HOST, serving.port, timeout=5)
    connection.request("GET", "/healthz")  # keep-alive: the connection stays open afterwards
    assert connection.getresponse().status == 200
    try:
        serving.thread.join(timeout=10)
        assert not serving.thread.is_alive()
    finally:
        connection.close()


def test_real_server_process_exits_when_idle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    port = free_port()
    monkeypatch.setenv("SHEETDJ_PORT", str(port))
    monkeypatch.setenv("SHEETDJ_IDLE_MINUTES", "0.05")  # three seconds
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    process = launcher.spawn_server()
    try:
        assert launcher.wait_until_ready(port, 60)
        assert process.wait(timeout=30) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
