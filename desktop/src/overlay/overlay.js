"use strict";

// Overlay renderer (Subsystem D).
//
// Click the fox to show or hide its current suggestions; drag it to move the
// overlay. Context bubbles can be copied or dragged into another app.
//
// Talks to the backend over HTTP; coordinates click-through and native file
// drag through the preload bridge (window.pacific).

const P = window.pacific;

let BACKEND = "http://127.0.0.1:8000";
const els = {
  stage: document.getElementById("stage"),
  bubbles: document.getElementById("bubbles"),
  fox: document.getElementById("fox"),
  foxToggle: document.getElementById("fox-toggle"),
  collapse: document.getElementById("btn-collapse"),
  companion: document.getElementById("companion"),
  count: document.getElementById("count"),
  bar: document.getElementById("bar"),
  status: document.getElementById("status"),
  dot: document.getElementById("dot"),
  capture: document.getElementById("btn-capture"),
  toast: document.getElementById("toast"),
};

// ── Click-through coordination ───────────────────────────────────────────────
// The window ignores mouse events by default (set in main). Whenever the pointer
// is over an interactive element we flip it interactive, then back when it
// leaves — so empty overlay space stays click-through to the apps underneath.
const hovered = new Set();
let dragging = false;   // while moving the window the pointer leaves the fox

function syncInteractive() {
  P.setInteractive(dragging || hovered.size > 0);
}

function makeInteractive(el) {
  el.addEventListener("pointerenter", () => { hovered.add(el); syncInteractive(); });
  el.addEventListener("pointerleave", () => { hovered.delete(el); syncInteractive(); });
}

// ── Dragging the character moves the whole overlay ───────────────────────────
// The main process reads the cursor and repositions the window; the renderer
// only reports that a gesture is in progress. `dragging` pins the window
// interactive for the duration, because the pointer routinely leaves the fox
// mid-gesture and the hover handler would otherwise make it click-through and
// drop the drag.
function makeWindowDraggable(handle) {
  let suppressClick = false;
  handle.addEventListener("click", (e) => {
    if (!suppressClick || e.detail === 0) return; // Keyboard activation still works.
    e.preventDefault();
    e.stopImmediatePropagation();
    suppressClick = false;
  }, true);

  handle.addEventListener("mousedown", (e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    handle.focus({ preventScroll: true });
    suppressClick = false;
    let moved = false;
    const startX = e.screenX;
    const startY = e.screenY;

    dragging = true;
    syncInteractive();
    // Record the original window offset, but don't move on a simple click.
    P.dragStart();

    const onMove = (event) => {
      if (!moved && Math.hypot(event.screenX - startX, event.screenY - startY) < 5) return;
      moved = true;
      suppressClick = true;
      els.fox.classList.add("grabbing");
      P.dragMove();
    };
    const finish = () => {
      dragging = false;
      els.fox.classList.remove("grabbing");
      P.dragEnd();
      syncInteractive();
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      window.removeEventListener("blur", onBlur);
    };
    const onUp = (event) => { if (event.button === 0) finish(); };
    const onBlur = () => { suppressClick = true; finish(); };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    window.addEventListener("blur", onBlur);
  });
}

function toggleSuggestions() {
  const collapsed = els.stage.classList.toggle("collapsed");
  const expanded = String(!collapsed);
  els.foxToggle.setAttribute("aria-expanded", expanded);
  els.foxToggle.title = `Click to ${collapsed ? "show" : "hide"} suggestions · Drag to move`;
  els.collapse.setAttribute("aria-expanded", expanded);
  els.collapse.title = collapsed ? "Show suggestions" : "Hide suggestions";
  els.collapse.textContent = collapsed ? "▴" : "▾";
  // Hidden bubbles must not leave empty overlay space intercepting clicks.
  if (collapsed) {
    for (const el of hovered) {
      if (els.bubbles.contains(el)) hovered.delete(el);
    }
  }
  syncInteractive();
}

// ── HTTP helpers ─────────────────────────────────────────────────────────────
async function api(method, path, body) {
  const res = await fetch(BACKEND + path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`${method} ${path} -> ${res.status}`);
  return res.json();
}

function setStatus(text) { els.status.textContent = text || ""; }

let toastTimer = null;
function toast(msg) {
  els.toast.hidden = false;
  els.toast.textContent = msg;
  requestAnimationFrame(() => els.toast.classList.add("show"));
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    els.toast.classList.remove("show");
    setTimeout(() => { els.toast.hidden = true; }, 220);
  }, 1400);
}

function setBusy(busy) {
  els.dot.classList.toggle("busy", busy);
  els.capture.classList.toggle("spinning", busy);
}

function kindClass(kind) {
  return { meta: "kind-meta", file: "kind-file", data: "kind-data", people: "kind-people" }[kind] || "kind-file";
}

// ── Companion ────────────────────────────────────────────────────────────────
// The overlay sees only server state, so it uses the data-driven subset of the
// rules in frontend/src/companionState.js (no "attaching"/"done" — those are
// reactions to a click, which happens in the dashboard).

function companionFor(state, suggestions) {
  const reason = (state.suggest_diag || {}).reason || "";
  const attachedCount = (state.attached || []).length;

  if (suggestions.length > 1) return { emote: "presenting", text: `${suggestions.length} things might help` };
  if (suggestions.length === 1) return { emote: "offering", text: "One thing might help" };
  if (reason === "no_clear_signal") return { emote: "empty", text: "Nothing stands out yet" };
  if (attachedCount >= 3) return { emote: "connected", text: `Holding ${attachedCount} pieces` };
  if ((state.session_events || []).length > 0) return { emote: "watching", text: "Following along" };
  return { emote: "idle", text: "Watching your screen" };
}

function renderCompanion(state, suggestions) {
  const { emote, text } = companionFor(state, suggestions);
  const src = `${BACKEND}/character/${emote}.webp`;
  if (els.companion.getAttribute("src") !== src) {
    els.companion.src = src;
    els.fox.dataset.emote = emote;
    els.companion.classList.remove("pop");
    void els.companion.offsetWidth;   // restart the animation
    els.companion.classList.add("pop");
  }
  const ctx = state.active_app
    ? `${state.active_app}${state.window_title ? " · " + state.window_title : ""}`
    : "";
  setStatus(ctx || text);
}

// ── The bubbles ──────────────────────────────────────────────────────────────
// Every suggestion is visible at once, stacked out of the character. Cycling a
// single card hid most of what Pacific had found, which defeats the point.

let shownIds = "";   // so a background refresh doesn't rebuild an untouched stack

function makeBubble(item, index, isTop) {
  const el = document.createElement("div");
  el.className = `bubble ${isTop ? "is-top" : ""}`;
  el.style.setProperty("--i", String(index));
  el.setAttribute("draggable", "true");

  el.innerHTML = `
    <button class="bubble-close" title="Not this one">&times;</button>
    <div class="bubble-head">
      <span class="kind-badge"></span>
      <span class="bubble-title"></span>
    </div>
    <p class="bubble-desc"></p>
    <div class="bubble-actions">
      <span class="drag-pill" title="Drag straight into a chat's upload area">
        <span class="drag-glyph">&#8690;</span> Drag me in
      </span>
      <button class="ghost btn-copy" title="Copy the text">Copy</button>
      <button class="ghost btn-keep" title="Keep this in the working context">Keep</button>
    </div>`;

  const kind = el.querySelector(".kind-badge");
  kind.className = `kind-badge ${kindClass(item.kind)}`;
  kind.textContent = item.kind;
  const title = el.querySelector(".bubble-title");
  title.textContent = item.display_name;
  title.title = item.display_name;
  el.querySelector(".bubble-desc").textContent = item.description || "";

  // Pre-materialize a temp file so we can advertise text/uri-list and start a
  // native file drag without async work mid-gesture.
  let prepared = null;
  P.prepareDrag(item).then((p) => { prepared = p; }).catch(() => {});

  // Text drag: chat inputs that accept dropped text (text/plain) and targets
  // that read text/uri-list. The whole bubble is the drag surface.
  el.addEventListener("dragstart", (e) => {
    e.dataTransfer.effectAllowed = "copy";
    e.dataTransfer.setData("text/plain", item.content || "");
    if (prepared) e.dataTransfer.setData("text/uri-list", prepared.uri);
    el.classList.add("dragging");
  });
  el.addEventListener("dragend", () => el.classList.remove("dragging"));

  // File drag: real OS file drag (file promise) — the path that lands a file in
  // ChatGPT / Gemini / Claude upload zones. Canonical Electron recipe: cancel
  // the HTML5 drag and hand off to the main process startDrag.
  const pill = el.querySelector(".drag-pill");
  pill.setAttribute("draggable", "true");
  pill.addEventListener("dragstart", (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (prepared) P.startFileDrag(prepared.file);
  });

  const copyBtn = el.querySelector(".btn-copy");
  copyBtn.addEventListener("click", async (e) => {
    e.stopPropagation();
    try {
      await P.copy(item.content || "");
      copyBtn.classList.add("copied");
      copyBtn.textContent = "Copied";
      toast("Copied ✓");
      setTimeout(() => { copyBtn.classList.remove("copied"); copyBtn.textContent = "Copy"; }, 1200);
    } catch { setStatus("Copy failed"); }
  });

  el.querySelector(".btn-keep").addEventListener("click", async (e) => {
    e.stopPropagation();
    try {
      await api("POST", `/api/attach/${encodeURIComponent(item.id)}`);
      toast("Kept ✓");
      await refresh();
    } catch (err) { setStatus(err.message); }
  });

  el.querySelector(".bubble-close").addEventListener("click", async (e) => {
    e.stopPropagation();
    el.classList.add("leaving");
    try {
      await api("POST", `/api/dismiss/${encodeURIComponent(item.id)}`);
      await refresh();
    } catch (err) { setStatus(err.message); }
  });

  makeInteractive(el);
  return el;
}

function renderBubbles(suggestions) {
  // Only rebuild when the set actually changes, so a 4s refresh never
  // interrupts a drag or resets a "Copied" label.
  const sig = suggestions.map((s) => s.id).join("|");
  if (sig === shownIds) return;
  shownIds = sig;

  els.bubbles.innerHTML = "";
  suggestions.forEach((item, i) => {
    // Best last: it ends up nearest the fox, right above the tail.
    els.bubbles.appendChild(makeBubble(item, suggestions.length - 1 - i, i === 0));
  });
  const nodes = Array.from(els.bubbles.children).reverse();
  nodes.forEach((n) => els.bubbles.appendChild(n));
}

// ── Refresh loop ─────────────────────────────────────────────────────────────
let refreshing = false;
async function refresh() {
  if (refreshing) return;
  refreshing = true;
  try {
    const state = await api("GET", "/api/state");
    els.dot.classList.remove("offline");

    const suggestions = (state.pool || []).filter((i) => i.status === "suggested");
    els.count.hidden = suggestions.length < 2;
    els.count.textContent = String(suggestions.length);
    renderBubbles(suggestions);

    renderCompanion(state, suggestions);
  } catch (err) {
    els.dot.classList.add("offline");
    setStatus("Offline — retrying…");
  } finally {
    refreshing = false;
  }
}

// ── Wire up ──────────────────────────────────────────────────────────────────
async function init() {
  try { BACKEND = await P.backendUrl(); } catch { /* keep default */ }

  makeInteractive(els.fox);
  makeWindowDraggable(els.foxToggle);
  els.foxToggle.addEventListener("click", toggleSuggestions);

  els.capture.addEventListener("click", () => {
    setBusy(true);
    P.captureNow();
    setTimeout(() => setBusy(false), 1500);
  });
  document.getElementById("btn-dashboard").addEventListener("click", () => { P.openDashboard(); });
  els.collapse.addEventListener("click", toggleSuggestions);

  P.onContextChanged(() => { setBusy(true); refresh().finally(() => setBusy(false)); });

  await refresh();
  setInterval(refresh, 4000); // safety net; focus events drive most refreshes
}

init();
