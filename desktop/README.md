# Pacific Desktop

A native desktop shell that turns the Pacific recommender into an ambient context broker: a passive assistant that watches what you're doing, ranks the most relevant context right now, and floats it above every window as draggable sticky notes — one drag away from any AI chat assistant.

It wraps the FastAPI backend and provides:

| Feature | Where it lives |
|---|---|
| **Screen capture & understanding** | `src/capture.js` (focus-triggered frames via `desktopCapturer` → backend VLM) + `src/native-bridge.js` and `native/*` (active app, window title, selected text via Accessibility API / UI Automation) |
| **Context store & profiling** | backend `profile.py`: rolling user profile (writing style, active projects, collaborators, doc types) + proactive context-type suggestions |
| **Ranking & recommendation** | backend pipeline (`backend/scoring.py`) |
| **Floating overlay & drag-and-drop** | `src/main.js` + `src/overlay/*`: frameless, always-on-top, click-through-where-empty window with draggable sticky notes and OS-level drag-and-drop |

## Architecture

```
┌─────────────────────────── Electron (main.js) ───────────────────────────┐
│  spawns ──► Python backend (uvicorn backend.main:app)  ◄── HTTP ──┐       │
│                                                                    │       │
│  NativeBridge ──focus──► POST /api/session/context ──► rescore     │       │
│       │                  + desktopCapturer frame ──► /live-tick     │       │
│       ▼                                                             │       │
│  Overlay window (frameless, always-on-top)  ◄── GET /api/state ─────┘       │
│     • sticky notes  → drag (text/plain, text/uri-list, OS file)            │
│     • context-type chips                                                   │
│  Dashboard window → loads the React app served by the backend             │
└───────────────────────────────────────────────────────────────────────────┘
```

## Run

```bash
# 1. Backend deps (from repo root) + build the dashboard once
pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..

# 2. Desktop app
cd desktop
npm install
npm start          # spawns the backend, opens the overlay + dashboard
```

Useful env vars:

- `PACIFIC_NO_SPAWN=1` — attach to a backend you started yourself.
- `PACIFIC_BACKEND_URL=http://127.0.0.1:8000` — point at a custom backend.
- `PACIFIC_PYTHON=python3.11` — choose the interpreter used to spawn uvicorn.
- `EMBEDDING_PROVIDER=gemini` + `GEMINI_API_KEY=...` (in repo-root `.env`) for
  real embeddings and screen VLM analysis. Defaults to deterministic mock
  embeddings so the loop runs with no keys.

## Drag-and-drop into AI chats

Each sticky note supports two drag modes (test each chat target individually — their drop handlers differ):

- **Drag the card body** → sets `text/plain` (the content) and `text/uri-list`
  (a `file://` URI). Works for chat inputs that accept dropped/pasted text.
- **Drag the `⇲ file` handle** → starts a real **OS file drag** (file promise via
  Electron `webContents.startDrag`). Works for the file-upload zones in ChatGPT,
  Gemini, and Claude web.

## Native capture helpers

`active-win` (optional dependency) gives app + window title cross-platform with
no build step. For selected-text capture and higher fidelity, build the native
helper for your platform — see `native/macos/README.md` and
`native/windows/README.md`. The bridge auto-detects a built helper and prefers
it; otherwise it falls back to `active-win`, then to screenshots only.

## Status / limitations

- Frames are captured via Electron `desktopCapturer`; the `native/*` helpers
  currently provide the structured-text channel. ScreenCaptureKit / Graphics
  Capture frame streaming is stubbed with instructions in each helper's README.
- In-memory state and local JSON storage are used for session and vector cache persistence.
