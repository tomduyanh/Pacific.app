"""Gemini-format front for the custom model endpoint.

Only needed when the endpoint does not implement benchmarks/ENDPOINT_SPEC.md
directly. Pacific keeps speaking Gemini; this process forwards each call to
the custom API. Fill in the two `upstream_*` functions once its request and
response format is known. Everything else (routing, batching, errors) is done.

    BENCH_UPSTREAM_URL=https://... BENCH_API_KEY=... python -m benchmarks.adapter --port 8766

The harness starts it automatically when endpoint.env sets BENCH_USE_ADAPTER=1.
"""
from __future__ import annotations

import argparse
import base64
import os

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

UPSTREAM_URL = os.environ.get("BENCH_UPSTREAM_URL", "").rstrip("/")
API_KEY = os.environ.get("BENCH_API_KEY", "")

app = FastAPI()
_client: httpx.AsyncClient | None = None


def client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=60)
    return _client


# ── Fill these in once the custom endpoint's format is known ────────────────

async def upstream_embed(texts: list[str]) -> list[list[float]]:
    """Return one vector per text, in order, all of the same length."""
    raise NotImplementedError("adapter.upstream_embed: custom endpoint format not filled in yet")


async def upstream_generate(prompt: str, image: bytes | None, mime_type: str | None,
                            max_output_tokens: int) -> str:
    """Return the model's text reply. `image` is set for vision calls."""
    raise NotImplementedError("adapter.upstream_generate: custom endpoint format not filled in yet")


# ── Gemini-format routing ────────────────────────────────────────────────────

def _texts(content: dict) -> str:
    return "".join(p.get("text", "") for p in content.get("parts", []))


@app.post("/{path:path}")
async def gemini(path: str, request: Request):
    method = path.rsplit(":", 1)[-1]
    body = await request.json()
    try:
        if method == "embedContent":
            [vec] = await upstream_embed([_texts(body["content"])])
            return {"embedding": {"values": vec}}
        if method == "batchEmbedContents":
            vecs = await upstream_embed([_texts(r["content"]) for r in body["requests"]])
            return {"embeddings": [{"values": v} for v in vecs]}
        if method == "generateContent":
            parts = body["contents"][0]["parts"]
            prompt = "".join(p.get("text", "") for p in parts)
            inline = next((p["inline_data"] for p in parts if "inline_data" in p), None)
            image = base64.b64decode(inline["data"]) if inline else None
            text = await upstream_generate(prompt, image, inline["mime_type"] if inline else None,
                                           int(body.get("generationConfig", {}).get("maxOutputTokens", 1024)))
            return {"candidates": [{"content": {"parts": [{"text": text}]}}]}
    except httpx.HTTPStatusError as exc:
        # Pass the upstream status through so Pacific's retry policy still applies.
        return JSONResponse({"error": {"message": str(exc)}}, status_code=exc.response.status_code)
    except httpx.TransportError as exc:
        return JSONResponse({"error": {"message": f"upstream unreachable: {exc}"}}, status_code=503)
    return JSONResponse({"error": {"message": f"unsupported method {method}"}}, status_code=404)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8766)
    args = ap.parse_args()
    if not UPSTREAM_URL:
        raise SystemExit("BENCH_UPSTREAM_URL is not set")
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
