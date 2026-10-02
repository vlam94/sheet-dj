"""Stop the server once nobody has used it for a while."""

import threading
import time
from collections.abc import Callable

CHECK_SECONDS = 15.0  # how often the watchdog looks at the clock


class IdleWatchdog:
    """Calls `on_idle` once, when `timeout` seconds pass without a `touch()`."""

    def __init__(
        self,
        timeout: float,
        on_idle: Callable[[], None],
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._timeout = timeout
        self._on_idle = on_idle
        self._clock = clock
        self._last_touch = clock()
        self._stopped = threading.Event()

    def touch(self) -> None:
        """Record activity: a request reached the server."""
        self._last_touch = self._clock()

    def expired(self) -> bool:
        """True when the quiet time has reached the timeout."""
        return self._clock() - self._last_touch >= self._timeout

    def start(self) -> threading.Thread:
        """Watch in a background thread that never keeps the process alive."""
        thread = threading.Thread(target=self._watch, name="idle-watchdog", daemon=True)
        thread.start()
        return thread

    def stop(self) -> None:
        """Stop watching without calling `on_idle`."""
        self._stopped.set()

    def _watch(self) -> None:
        interval = min(CHECK_SECONDS, self._timeout)
        while not self._stopped.wait(interval):
            if self.expired():
                self._on_idle()
                return
