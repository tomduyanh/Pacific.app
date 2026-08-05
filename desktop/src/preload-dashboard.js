"use strict";

const { contextBridge, ipcRenderer } = require("electron");

// Minimal surface for the dashboard window. Its presence is also how the React
// app knows it is running inside the desktop shell rather than a browser tab,
// so it can offer to summon the floating assistant.
contextBridge.exposeInMainWorld("pacificDesktop", {
  isDesktop: true,
  showOverlay: () => ipcRenderer.invoke("overlay:show"),
  hideOverlay: () => ipcRenderer.send("overlay:hide"),
  isOverlayVisible: () => ipcRenderer.invoke("overlay:visible"),
});
