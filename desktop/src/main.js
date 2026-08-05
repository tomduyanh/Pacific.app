"use strict";

const { app, BrowserWindow, clipboard, ipcMain, nativeImage, screen, shell } = require("electron");
const fs = require("fs");
const os = require("os");
const path = require("path");

const config = require("./config");
const backend = require("./backend");
const { NativeBridge } = require("./native-bridge");
const { captureAndSend } = require("./capture");

let dashboardWin = null;
let overlayWin = null;
let bridge = null;

const DRAG_ICON = nativeImage.createFromPath(path.join(__dirname, "assets", "drag-icon.png"));

// ── Windows ──────────────────────────────────────────────────────────────────

function createDashboardWindow() {
  dashboardWin = new BrowserWindow({
    width: 1180,
    height: 820,
    title: "Pacific — Context Dashboard",
    webPreferences: {
      preload: path.join(__dirname, "preload-dashboard.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  // The FastAPI backend serves the built React dashboard at "/".
  dashboardWin.loadURL(config.BACKEND_URL).catch(() => {
    dashboardWin.loadFile(path.join(__dirname, "overlay", "no-frontend.html"));
  });
  dashboardWin.on("closed", () => { dashboardWin = null; });
}

// ── Overlay position ─────────────────────────────────────────────────────────
// Where you put the character is a preference, so it should outlive the session.

function overlayPositionFile() {
  return path.join(app.getPath("userData"), "overlay-position.json");
}

function saveOverlayPosition() {
  if (!overlayWin || overlayWin.isDestroyed()) return;
  try {
    const [x, y] = overlayWin.getPosition();
    fs.writeFileSync(overlayPositionFile(), JSON.stringify({ x, y }), "utf8");
  } catch { /* non-fatal */ }
}

function loadOverlayPosition() {
  try {
    const { x, y } = JSON.parse(fs.readFileSync(overlayPositionFile(), "utf8"));
    if (typeof x !== "number" || typeof y !== "number") return null;
    // Only honour it if it still lands on a connected display.
    const onScreen = screen.getAllDisplays().some((d) => {
      const b = d.workArea;
      return x + 80 > b.x && x < b.x + b.width - 20 && y + 60 > b.y && y < b.y + b.height - 20;
    });
    return onScreen ? { x, y } : null;
  } catch {
    return null;
  }
}

function createOverlayWindow() {
  const { workArea } = screen.getPrimaryDisplay();
  // Sized to the character plus one bubble. Anchored bottom-right so the bubble
  // grows upward out of the fox rather than hanging off a title bar.
  const saved = loadOverlayPosition();
  const width = 372;
  const height = Math.min(320, workArea.height - 80);

  overlayWin = new BrowserWindow({
    width,
    height,
    x: saved ? saved.x : workArea.x + workArea.width - width - 20,
    y: saved ? saved.y : workArea.y + workArea.height - height - 20,
    frame: false,
    transparent: true,
    resizable: true,
    skipTaskbar: true,
    alwaysOnTop: true,
    hasShadow: false,
    focusable: true,
    webPreferences: {
      preload: path.join(__dirname, "preload-overlay.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  // Always-on-top above full-screen apps and other always-on-top windows.
  overlayWin.setAlwaysOnTop(true, "screen-saver");
  overlayWin.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });

  // Click-through where empty: ignore mouse by default; the renderer toggles this
  // off (via overlay:set-interactive) when the pointer is over a sticky note.
  overlayWin.setIgnoreMouseEvents(true, { forward: true });

  overlayWin.loadFile(path.join(__dirname, "overlay", "index.html"));
  overlayWin.on("closed", () => { overlayWin = null; });
}

// ── Native focus → backend context + screenshot ──────────────────────────────

async function postAccessibilityContext(ctx) {
  try {
    await fetch(config.BACKEND_URL + "/api/session/context", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        app_name: ctx.app_name || "",
        window_title: ctx.window_title || "",
        selected_text: ctx.selected_text || "",
        rescore: true,
      }),
    });
  } catch (err) {
    console.log("[context] post failed:", err.message);
  }
}

async function onFocusChange(ctx) {
  // Don't capture our own overlay/dashboard windows as "context".
  const appName = (ctx.app_name || "").toLowerCase();
  if (appName.includes("pacific") || appName.includes("electron")) return;

  await postAccessibilityContext(ctx);
  // Focus change is the capture trigger (plan: focus-driven, not fixed timer).
  const result = await captureAndSend(config.BACKEND_URL);
  if (overlayWin && !overlayWin.isDestroyed()) {
    overlayWin.webContents.send("context:changed", { ctx, capture: result });
  }
}

// ── IPC: overlay interactivity + drag-and-drop ───────────────────────────────

function tempFileForItem(item) {
  const safe = String(item.display_name || item.id || "context")
    .replace(/[^a-z0-9._-]+/gi, "_")
    .slice(0, 48);
  let ext = "";
  const m = /\.([a-z0-9]{1,8})$/i.exec(item.source || item.display_name || "");
  if (m) ext = m[0];
  else ext = item.kind === "file" ? ".md" : ".txt";
  const base = safe.endsWith(ext) ? safe : safe + ext;
  const dir = path.join(os.tmpdir(), "pacific-drag");
  fs.mkdirSync(dir, { recursive: true });
  const file = path.join(dir, base);
  fs.writeFileSync(file, item.content || "", "utf8");
  return file;
}

function registerIpc() {
  // Toggle click-through. interactive=true → window receives mouse events.
  ipcMain.on("overlay:set-interactive", (_e, interactive) => {
    if (overlayWin && !overlayWin.isDestroyed()) {
      overlayWin.setIgnoreMouseEvents(!interactive, { forward: true });
    }
  });

  // Materialize an item to a temp file and return its path + file:// URI so the
  // renderer can advertise text/uri-list during an HTML5 drag.
  ipcMain.handle("drag:prepare", (_e, item) => {
    const file = tempFileForItem(item);
    return { file, uri: "file://" + file.split(path.sep).join("/") };
  });

  // Start a real OS file drag (the file-promise path the plan calls for — this
  // is what makes drops into ChatGPT / Gemini / Claude file uploaders work).
  ipcMain.on("drag:start-file", (event, file) => {
    if (!file || !fs.existsSync(file)) return;
    event.sender.startDrag({ file, icon: DRAG_ICON });
  });

  ipcMain.handle("clipboard:write", (_e, text) => {
    clipboard.writeText(String(text || ""));
    return true;
  });

  ipcMain.handle("backend:url", () => config.BACKEND_URL);

  ipcMain.on("overlay:open-dashboard", () => {
    if (!dashboardWin || dashboardWin.isDestroyed()) createDashboardWindow();
    else dashboardWin.focus();
  });

  ipcMain.on("overlay:capture-now", async () => {
    const result = await captureAndSend(config.BACKEND_URL, { force: true });
    if (overlayWin && !overlayWin.isDestroyed()) {
      overlayWin.webContents.send("context:changed", { capture: result });
    }
  });

  // Dragging the character moves the window. Done manually rather than with
  // -webkit-app-region: drag, because that swallows mousedown before the
  // renderer sees it and fights the click-through toggling the overlay needs.
  // Reading the cursor from the main process sidesteps renderer-to-screen
  // coordinate translation entirely.
  let overlayDrag = null;

  ipcMain.on("overlay:drag-start", () => {
    if (!overlayWin || overlayWin.isDestroyed()) return;
    const cursor = screen.getCursorScreenPoint();
    const [x, y] = overlayWin.getPosition();
    overlayDrag = { dx: cursor.x - x, dy: cursor.y - y };
  });

  ipcMain.on("overlay:drag-move", () => {
    if (!overlayDrag || !overlayWin || overlayWin.isDestroyed()) return;
    const cursor = screen.getCursorScreenPoint();
    overlayWin.setPosition(cursor.x - overlayDrag.dx, cursor.y - overlayDrag.dy);
  });

  ipcMain.on("overlay:drag-end", () => {
    overlayDrag = null;
    saveOverlayPosition();
  });

  // The dashboard can summon the floating assistant, recreating it if the user
  // closed it earlier in the session.
  ipcMain.handle("overlay:show", () => {
    if (!overlayWin || overlayWin.isDestroyed()) createOverlayWindow();
    overlayWin.show();
    overlayWin.setAlwaysOnTop(true, "screen-saver");
    return true;
  });

  ipcMain.on("overlay:hide", () => {
    if (overlayWin && !overlayWin.isDestroyed()) overlayWin.hide();
  });

  ipcMain.handle("overlay:visible", () =>
    Boolean(overlayWin && !overlayWin.isDestroyed() && overlayWin.isVisible()));

  ipcMain.on("open-external", (_e, url) => shell.openExternal(url));
}

// ── Lifecycle ────────────────────────────────────────────────────────────────

app.whenReady().then(async () => {
  registerIpc();

  const status = await backend.start();
  if (!status.ready) {
    console.error("[backend] not reachable — start it manually or check PACIFIC_BACKEND_URL");
  }

  createOverlayWindow();
  createDashboardWindow();

  bridge = new NativeBridge();
  bridge.on("focus", (ctx) => { void onFocusChange(ctx); });
  bridge.start();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createOverlayWindow();
      createDashboardWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => {
  if (bridge) bridge.stop();
  backend.stop();
});
