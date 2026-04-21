const BASE = "/api";

async function request(method, path, body) {
  const res = await fetch(BASE + path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`${method} ${path} -> ${res.status}`);
  return res.json();
}

export const api = {
  getState: () => request("GET", "/state"),
  postMessage: (message) => request("POST", "/message", { message }),
  rescore: () => request("POST", "/rescore"),
  attach: (id) => request("POST", `/attach/${encodeURIComponent(id)}`),
  detach: (id) => request("DELETE", `/attach/${encodeURIComponent(id)}`),
  dismiss: (id) => request("POST", `/dismiss/${encodeURIComponent(id)}`),
  addEvent: (event) => request("POST", "/session/event", { event }),
  analyzeScreen: (body) => request("POST", "/session/screen/analyze", body),
  liveScreenTick: (body) => request("POST", "/session/screen/live-tick", body),
  clearSession: () => request("POST", "/session/clear"),
  uploadContext: (body) => request("POST", "/context/upload", body),
};
