"""Pacific launcher — start the backend and open the dashboard.

Double-click Pacific.bat (Windows) or ./pacific.sh (macOS/Linux), or run
`python run.py` directly. Handles first-run setup so there is nothing to
remember:

  * picks the repo venv's interpreter when there is one, else the current one
  * installs Python dependencies if they're missing
  * builds the frontend if frontend/dist isn't there
  * attaches to an already-running Pacific instead of failing on a busy port
  * waits for the server to answer, then opens the browser

Flags:
  --no-browser   start the server without opening a browser
  --port N       listen on N instead of 8000
  --desktop      launch the Electron overlay app instead of the browser UI
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "frontend" / "dist" / "index.html"
DEFAULT_PORT = 8000
HOST = "127.0.0.1"

REQUIRED_MODULES = ("fastapi", "uvicorn", "httpx", "numpy", "rank_bm25", "pydantic")


# ── console helpers ──────────────────────────────────────────────────────────

def say(msg: str = "") -> None:
    print(msg, flush=True)


def step(msg: str) -> None:
    print("  " + msg, flush=True)


def die(msg: str, hint: str = "") -> "NoReturn":  # noqa: F821
    say()
    say("  [!] " + msg)
    if hint:
        say("      " + hint)
    say()
    raise SystemExit(1)


# ── environment checks ───────────────────────────────────────────────────────

def venv_python() -> str:
    """Prefer the repo's virtualenv, so a global interpreter without the deps
    doesn't send us down the pip-install path every launch."""
    candidates = [
        ROOT / ".venv" / "Scripts" / "python.exe",   # Windows
        ROOT / ".venv" / "bin" / "python",           # POSIX
    ]
    for c in candidates:
        if c.is_file():
            return str(c)
    return sys.executable


def missing_modules(python: str) -> list:
    probe = "import importlib.util,sys;print(json.dumps([m for m in %r if importlib.util.find_spec(m) is None]))" % (
        list(REQUIRED_MODULES),
    )
    try:
        out = subprocess.run(
            [python, "-c", "import json;" + probe],
            capture_output=True, text=True, timeout=60,
        )
        if out.returncode == 0:
            return json.loads(out.stdout.strip() or "[]")
    except Exception:
        pass
    return []


def ensure_python_deps(python: str) -> None:
    missing = missing_modules(python)
    if not missing:
        return
    step("Installing Python dependencies (%s) ..." % ", ".join(missing))
    r = subprocess.run(
        [python, "-m", "pip", "install", "-r", str(ROOT / "requirements.txt"),
         "--quiet", "--disable-pip-version-check"],
        cwd=str(ROOT),
    )
    if r.returncode != 0:
        die("pip install failed.",
            "Try manually:  %s -m pip install -r requirements.txt" % python)


def npm_cmd() -> str:
    for name in ("npm.cmd", "npm"):
        found = shutil.which(name)
        if found:
            return found
    return ""


def ensure_frontend() -> None:
    if DIST.is_file():
        return
    npm = npm_cmd()
    if not npm:
        die("frontend/dist is missing and npm was not found.",
            "Install Node.js, or build elsewhere and copy frontend/dist here.")
    fe = ROOT / "frontend"
    if not (fe / "node_modules").is_dir():
        step("Installing frontend packages (first run only, ~1 min) ...")
        if subprocess.run([npm, "install", "--no-audit", "--no-fund"], cwd=str(fe)).returncode != 0:
            die("npm install failed.")
    step("Building the dashboard (first run only) ...")
    if subprocess.run([npm, "run", "build"], cwd=str(fe)).returncode != 0:
        die("Frontend build failed.")


# ── port / readiness ─────────────────────────────────────────────────────────

def port_busy(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.35)
        return s.connect_ex((HOST, port)) == 0


def is_pacific(port: int) -> bool:
    try:
        with urllib.request.urlopen("http://%s:%d/api/state" % (HOST, port), timeout=2) as r:
            return r.status == 200 and "pool" in json.loads(r.read().decode("utf-8"))
    except Exception:
        return False


def free_port(start: int) -> int:
    for p in range(start, start + 20):
        if not port_busy(p):
            return p
    die("No free port between %d and %d." % (start, start + 19))


def wait_ready(port: int, timeout: float = 90.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_pacific(port):
            return True
        time.sleep(0.4)
    return False


def open_when_ready(url: str, port: int, timeout: float = 90.0) -> None:
    """Poll until the server answers, then open the browser once."""
    if wait_ready(port, timeout):
        say()
        step("Dashboard ready  ->  " + url)
        say()
        try:
            webbrowser.open(url)
        except Exception:
            step("(could not open a browser automatically - open the URL above)")
        return
    step("Server did not become ready in %ds - open %s manually." % (int(timeout), url))


# ── modes ────────────────────────────────────────────────────────────────────

def run_desktop(python: str, port: int) -> int:
    """Launch the Electron shell: dashboard window + always-on-top overlay.

    The launcher owns the backend rather than letting Electron spawn it. Electron
    spawned uvicorn with stdio inherited from whatever console started it, so a
    console signal reaching that group killed the server out from under the app
    (observed: exit 0xC000013A, STATUS_CONTROL_C_EXIT). Starting it here and
    pointing Electron at it with PACIFIC_NO_SPAWN gives one backend code path
    for both modes and a clean shutdown.
    """
    npm = npm_cmd()
    desktop = ROOT / "desktop"
    if not npm:
        die("npm not found - the desktop app needs Node.js.",
            "Install it from https://nodejs.org and run this again.")
    if not (desktop / "node_modules").is_dir():
        step("Installing desktop packages (first run only, ~2 min) ...")
        if subprocess.run([npm, "install", "--no-audit", "--no-fund"], cwd=str(desktop)).returncode != 0:
            die("npm install failed in desktop/.")

    ensure_frontend()

    url = "http://%s:%d" % (HOST, port)
    backend_proc = None

    if is_pacific(port):
        step("Attaching to the Pacific already running on %s" % url)
    else:
        if port_busy(port):
            die("Port %d is held by something that isn't Pacific." % port,
                "Close it, or pass --port to use another.")
        step("Starting the backend on %s ..." % url)
        backend_proc = subprocess.Popen(
            [python, "-m", "uvicorn", "backend.main:app", "--host", HOST, "--port", str(port)],
            cwd=str(ROOT),
        )
        if not wait_ready(port):
            backend_proc.terminate()
            die("The backend did not come up.",
                "Run `python run.py` on its own to see the error.")

    env = dict(os.environ)
    env.setdefault("PACIFIC_PYTHON", python)
    env["PACIFIC_NO_SPAWN"] = "1"          # the launcher owns the backend
    env["PACIFIC_BACKEND_URL"] = url
    # Editors that are themselves Electron apps (VS Code, Cursor) export
    # ELECTRON_RUN_AS_NODE=1 into their integrated terminals. Inheriting it makes
    # our electron binary boot as plain Node, so require("electron") returns the
    # npm shim's path string and main.js dies on `nativeImage` being undefined.
    env.pop("ELECTRON_RUN_AS_NODE", None)

    step("Opening the Pacific desktop app ...")
    say("  (close the app window to quit)")
    say()
    try:
        return subprocess.run([npm, "start"], cwd=str(desktop), env=env).returncode
    except KeyboardInterrupt:
        return 0
    finally:
        if backend_proc is not None:
            step("Stopping the backend ...")
            backend_proc.terminate()
            try:
                backend_proc.wait(timeout=10)
            except Exception:
                backend_proc.kill()


def run_server(python: str, port: int, open_browser: bool) -> int:
    url = "http://%s:%d" % (HOST, port)

    if open_browser:
        threading.Thread(target=open_when_ready, args=(url, port), daemon=True).start()

    step("Starting the backend on %s ..." % url)
    say("  (leave this window open; press Ctrl+C to stop)")
    say()
    cmd = [python, "-m", "uvicorn", "backend.main:app", "--host", HOST, "--port", str(port)]
    try:
        return subprocess.run(cmd, cwd=str(ROOT)).returncode
    except KeyboardInterrupt:
        return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Start Pacific.")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--desktop", action="store_true", help="launch the Electron overlay")
    args = ap.parse_args()

    say()
    say("  Pacific - Context Dashboard")
    say("  " + "-" * 27)
    say()

    python = venv_python()
    step("Python: %s" % python)
    ensure_python_deps(python)

    port = args.port
    if args.desktop:
        return run_desktop(python, port)

    ensure_frontend()

    if port_busy(port):
        if is_pacific(port):
            url = "http://%s:%d" % (HOST, port)
            step("Pacific is already running - opening %s" % url)
            say()
            if not args.no_browser:
                webbrowser.open(url)
            return 0
        port = free_port(port + 1)
        step("Port %d is taken; using %d instead." % (args.port, port))

    return run_server(python, port, not args.no_browser)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        say()
        step("Stopped.")
        raise SystemExit(0)
