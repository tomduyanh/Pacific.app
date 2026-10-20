"""Process plumbing shared by the stress and quality benchmarks.

Every run works on a throwaway copy of backend/, FileGram/ and data/, because
Pacific writes pool.json, session_state.json and embed_cache.json next to its
own code. The repository's data/ is never touched.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parent.parent
PY = sys.executable


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def make_workdir(pool: list[dict] | None = None) -> Path:
    """Copy the app into a temp dir, optionally replacing the context pool."""
    work = Path(tempfile.mkdtemp(prefix="pacific-bench-"))
    ignore = shutil.ignore_patterns("__pycache__", "session_state.json", "embed_cache.json")
    for name in ("backend", "FileGram", "data", "benchmarks"):
        shutil.copytree(REPO / name, work / name, ignore=ignore)
    if pool is not None:
        (work / "data" / "pool.json").write_text(json.dumps(pool), encoding="utf-8")
    return work


def wait_http(url: str, timeout: float, proc: subprocess.Popen | None = None) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc is not None and proc.poll() is not None:
            raise RuntimeError(f"process exited with {proc.returncode} before {url} came up")
        try:
            httpx.get(url, timeout=2)
            return
        except httpx.HTTPError:
            time.sleep(0.2)
    raise TimeoutError(f"{url} did not come up within {timeout}s")


class PacificServer:
    """Instrumented Pacific running from a working copy."""

    def __init__(self, workdir: Path, env: dict[str, str], log: Path | None = None):
        self.workdir = workdir
        self.port = free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        self.env = {**os.environ, **env}
        self.log = log
        self.proc: subprocess.Popen | None = None
        self.startup_s = 0.0

    def start(self, timeout: float = 600) -> "PacificServer":
        out = open(self.log, "ab") if self.log else subprocess.DEVNULL
        started = time.time()
        self.proc = subprocess.Popen(
            [PY, "-m", "uvicorn", "benchmarks.instrumented_app:app",
             "--host", "127.0.0.1", "--port", str(self.port), "--log-level", "warning"],
            cwd=self.workdir, env=self.env, stdout=out, stderr=subprocess.STDOUT,
        )
        wait_http(self.url + "/__bench/metrics", timeout, self.proc)
        self.startup_s = time.time() - started
        return self

    def metrics(self) -> dict:
        return httpx.get(self.url + "/__bench/metrics", timeout=30).json()

    def reset_metrics(self) -> None:
        httpx.post(self.url + "/__bench/reset", timeout=30)

    def kill_hard(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.send_signal(signal.SIGKILL)
            self.proc.wait(10)

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(30)
            except subprocess.TimeoutExpired:
                self.kill_hard()

    def __enter__(self) -> "PacificServer":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()
