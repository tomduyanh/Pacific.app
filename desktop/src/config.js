"use strict";

const path = require("path");

// Repo root is one level above desktop/. The Python backend (FastAPI) lives there.
const REPO_ROOT = path.resolve(__dirname, "..", "..");

module.exports = {
  REPO_ROOT,
  // Where the backend listens. Override with PACIFIC_BACKEND_URL to point at an
  // already-running server (e.g. during development).
  BACKEND_HOST: process.env.PACIFIC_BACKEND_HOST || "127.0.0.1",
  BACKEND_PORT: parseInt(process.env.PACIFIC_BACKEND_PORT || "8000", 10),
  get BACKEND_URL() {
    return process.env.PACIFIC_BACKEND_URL || `http://${this.BACKEND_HOST}:${this.BACKEND_PORT}`;
  },
  // Set PACIFIC_NO_SPAWN=1 to attach to a backend you started yourself.
  SPAWN_BACKEND: process.env.PACIFIC_NO_SPAWN !== "1",
  // Min seconds between screen-capture VLM calls (mirrors backend rate limit).
  CAPTURE_MIN_INTERVAL_SEC: parseFloat(process.env.PACIFIC_CAPTURE_INTERVAL_SEC || "5"),
  CAPTURE_MAX_WIDTH: 1280,
  IS_DEV: process.env.PACIFIC_DEV === "1",
};
