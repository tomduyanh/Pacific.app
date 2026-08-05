"use strict";

const { contextBridge, ipcRenderer } = require("electron");

// Safe, minimal surface for the overlay renderer. No Node, no remote module.
contextBridge.exposeInMainWorld("pacific", {
  // Click-through control: call with true when the pointer enters an interactive
  // sticky note, false when it leaves (so empty overlay area stays click-through).
  setInteractive: (interactive) => ipcRenderer.send("overlay:set-interactive", interactive),

  // Moving the overlay window by dragging the character.
  dragStart: () => ipcRenderer.send("overlay:drag-start"),
  dragMove: () => ipcRenderer.send("overlay:drag-move"),
  dragEnd: () => ipcRenderer.send("overlay:drag-end"),

  // Drag-and-drop.
  prepareDrag: (item) => ipcRenderer.invoke("drag:prepare", item),
  startFileDrag: (file) => ipcRenderer.send("drag:start-file", file),

  // Clipboard (file:// is not a secure context, so go through the main process).
  copy: (text) => ipcRenderer.invoke("clipboard:write", text),

  // Backend + actions.
  backendUrl: () => ipcRenderer.invoke("backend:url"),
  openDashboard: () => ipcRenderer.send("overlay:open-dashboard"),
  captureNow: () => ipcRenderer.send("overlay:capture-now"),
  openExternal: (url) => ipcRenderer.send("open-external", url),

  // Push notifications from main (focus change / new screenshot analysis).
  onContextChanged: (cb) => {
    const handler = (_e, payload) => cb(payload);
    ipcRenderer.on("context:changed", handler);
    return () => ipcRenderer.removeListener("context:changed", handler);
  },
});
