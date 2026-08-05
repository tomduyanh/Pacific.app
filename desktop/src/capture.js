"use strict";

// Subsystem A — frame capture. Grabs the current screen via Electron's
// desktopCapturer (no getUserMedia prompt needed in the main process) and posts
// it to the backend's live-tick VLM endpoint. Triggered on window-focus changes
// rather than a fixed timer, with a min-interval guard mirroring the backend
// rate limit, so we spend compute only when the situation actually changed.

const { desktopCapturer, screen } = require("electron");
const { CAPTURE_MIN_INTERVAL_SEC, CAPTURE_MAX_WIDTH } = require("./config");

let lastCaptureMs = 0;
let inFlight = false;

async function grabFrameBase64() {
  const primary = screen.getPrimaryDisplay();
  const { width, height } = primary.size;
  const scale = width > CAPTURE_MAX_WIDTH ? CAPTURE_MAX_WIDTH / width : 1;
  const thumbnailSize = { width: Math.round(width * scale), height: Math.round(height * scale) };

  const sources = await desktopCapturer.getSources({ types: ["screen"], thumbnailSize });
  if (!sources.length) return null;
  const img = sources[0].thumbnail;
  if (!img || img.isEmpty()) return null;
  return img.toJPEG(80).toString("base64");
}

async function captureAndSend(backendUrl, { force = false } = {}) {
  const now = Date.now();
  if (!force && now - lastCaptureMs < CAPTURE_MIN_INTERVAL_SEC * 1000) {
    return { skipped: true, reason: "rate_limit" };
  }
  if (inFlight) return { skipped: true, reason: "in_flight" };

  inFlight = true;
  try {
    const base64 = await grabFrameBase64();
    if (!base64) return { skipped: true, reason: "empty_frame" };
    lastCaptureMs = Date.now();

    const res = await fetch(backendUrl + "/api/session/screen/live-tick", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image_base64: base64, mime_type: "image/jpeg", apply: true }),
    });
    if (!res.ok) return { error: `live-tick ${res.status}` };
    return await res.json();
  } catch (err) {
    return { error: err.message };
  } finally {
    inFlight = false;
  }
}

module.exports = { captureAndSend };
