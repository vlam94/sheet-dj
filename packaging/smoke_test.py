"""Run a built program and use it like a person: load a score, build a set list, download it.

    python packaging/smoke_test.py build/dist/sheet-dj/sheet-dj      (sheet-dj.exe on Windows)

Standard library only, so it runs against the packaged program from any Python.
"""

import io
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
import zipfile
from pathlib import Path

SCORE = Path(__file__).parent.parent / "tests" / "fixtures" / "input" / "medley_two_songs.musicxml"
START_TIMEOUT = 90  # seconds; the first start loads music21


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
    return port


def request(url: str, data: bytes | None = None, content_type: str | None = None) -> bytes:
    req = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET")
    if content_type:
        req.add_header("Content-Type", content_type)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=60) as response:
        body: bytes = response.read()
    return body


def multipart(name: str, path: Path) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    head = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; '
        f'filename="{path.name}"\r\nContent-Type: application/xml\r\n\r\n'
    ).encode()
    return head + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode(), (
        f"multipart/form-data; boundary={boundary}"
    )


def wait_for_app(base: str, process: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + START_TIMEOUT
    while time.monotonic() < deadline:
        if process.poll() is not None:
            sys.exit(f"The program exited early with code {process.returncode}")
        try:
            if json.loads(request(base + "healthz")) == {"app": "sheet-dj"}:
                return
        except OSError:
            time.sleep(0.5)
    sys.exit("The program did not answer in time")


def main(program: str) -> None:
    port = free_port()
    base = f"http://127.0.0.1:{port}/"
    with tempfile.TemporaryDirectory() as state:
        env = {
            **os.environ,
            "SHEETDJ_PORT": str(port),
            "XDG_STATE_HOME": state,  # keeps the Linux log out of the real per-user folder
            "LOCALAPPDATA": state,  # (Windows ignores these two and logs to the real folder)
        }
        process = subprocess.Popen([program, "--serve"], env=env)
        try:
            wait_for_app(base, process)
            body, content_type = multipart("scores", SCORE)
            page = request(base + "scores", body, content_type).decode("utf-8")
            ids = re.findall(r'data-id="(\w+)"', page)
            assert len(ids) == 2, f"expected two songs on the page, found {len(ids)}"
            form = "&".join(f"song={i}" for i in ids) + "&name=smoke"
            archive = request(base + "export", form.encode(), "application/x-www-form-urlencoded")
            names = sorted(zipfile.ZipFile(io.BytesIO(archive)).namelist())
            assert names == ["smoke.musicxml", "smoke_tuba.csv"], names
        finally:
            process.terminate()
            process.wait(timeout=30)
    print("OK: loaded a score, built a set list and downloaded it")


if __name__ == "__main__":
    main(sys.argv[1])
