"use strict";

// Manages the Python FastAPI backend lifecycle: spawn uvicorn, wait until it is
// reachable, and tear it down on quit. When PACIFIC_NO_SPAWN=1 it simply waits
// for an externally-started server.

const { spawn } = require("child_process");
const http = require("http");
const { REPO_ROOT, BACKEND_URL, BACKEND_HOST, BACKEND_PORT, SPAWN_BACKEND } = require("./config");

let proc = null;

function ping(url) {
  return new Promise((resolve) => {
    const req = http.get(url + "/api/state", { timeout: 1500 }, (res) => {
      res.resume();
      resolve(res.statusCode > 0 && res.statusCode < 500);
    });
    req.on("error", () => resolve(false));
    req.on("timeout", () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function waitUntilReady(url, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await ping(url)) return true;
    await new Promise((r) => setTimeout(r, 500));
  }
  return false;
}

async function start() {
  if (await ping(BACKEND_URL)) {
    return { spawned: false, ready: true };
  }

  if (!SPAWN_BACKEND) {
    const ready = await waitUntilReady(BACKEND_URL);
    return { spawned: false, ready };
  }

  const defaultPython = process.platform === "win32" ? "python" : "python3";
  const python = process.env.PACIFIC_PYTHON || defaultPython;
  proc = spawn(
    python,
    ["-m", "uvicorn", "backend.main:app", "--host", BACKEND_HOST, "--port", String(BACKEND_PORT)],
    { cwd: REPO_ROOT, env: process.env, stdio: "inherit" }
  );
  proc.on("exit", (code) => {
    console.log(`[backend] uvicorn exited with code ${code}`);
    proc = null;
  });

  const ready = await waitUntilReady(BACKEND_URL);
  return { spawned: true, ready };
}

function stop() {
  if (proc) {
    proc.kill();
    proc = null;
  }
}

module.exports = { start, stop, BACKEND_URL };
