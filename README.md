# Pacific

A context recommender that watches what you're working on and surfaces the
documents, data and people you're about to need.

## Run it

**Windows** — double-click **`Pacific.bat`**

**macOS / Linux** — `./pacific.sh`

**Any platform** — `python run.py`

That's the whole setup. The launcher finds your interpreter (preferring
`.venv/`), installs Python dependencies if they're missing, builds the
dashboard on first run, starts the backend and opens
<http://127.0.0.1:8000> in your browser.

Leave the console window open while you use it; `Ctrl+C` stops the server.

In the dashboard, use **Share screen** and **Start live** to follow your work.
Live capture targets a five-second interval and reads a fresh frame each time;
recommendations update independently, so ranking does not delay the next capture.
The panel shows the latest screen-analysis and recommendation request times.
Stalled vision calls expire after 20 seconds (override with
`LIVE_SCREEN_MAX_LATENCY_SEC` in `.env`) before retrying with a fresh frame.

If Pacific is already running, launching again just opens the browser rather
than failing on a busy port. If something else holds port 8000, it moves to
the next free one and tells you.

### Options

| | |
|---|---|
| `Pacific.bat --port 8080` | listen somewhere else |
| `Pacific.bat --no-browser` | start the server only |
| **`Pacific Desktop.bat`** | the Electron overlay instead of the browser UI |

The desktop build adds a frameless always-on-top overlay with draggable
sticky notes, plus native window-focus tracking and screen capture. The
launcher starts the backend and the app attaches to it, so it will reuse a
Pacific you already have running rather than fighting it for the port.

## Configuration

Optional — copy `.env.example` to `.env`. With no keys at all Pacific runs on
deterministic mock embeddings, so the whole loop works offline.

```ini
EMBEDDING_PROVIDER=gemini      # or "mock" (default) / "anthropic"
GEMINI_API_KEY=...             # enables real embeddings + screen analysis
EMBED_DIM=3072
```

## Requirements

- Python 3.9+
- Node.js — only needed the first time, to build the dashboard. If
  `frontend/dist/` is already present you don't need it at all.

## Layout

```
backend/     FastAPI service — scoring, embeddings, screen analysis
frontend/    React dashboard (Vite)
desktop/     Electron shell — overlay window + native capture
FileGram/    behavioural user-modelling engine
data/        context pool, memory store, session state
```
