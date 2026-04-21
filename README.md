# Pacific.app


## Prerequisites

- Python 3.11+
- Node.js 18+

## 1) Environment setup

From repo root:

```bash
cp .env.example .env
```

`EMBEDDING_PROVIDER=mock` works without API keys for local testing.

## 2) Backend setup and run

From repo root:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000
```

Backend runs at `http://localhost:8000`.

## 3) Frontend setup and run

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:5173`.
