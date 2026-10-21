"""Gemini-format front for the custom model endpoint.

Only needed when the endpoint does not implement benchmarks/ENDPOINT_SPEC.md
directly. Pacific keeps speaking Gemini; this process forwards each call to
an OpenAI-compatible API (/chat/completions for text and vision,
/embeddings for vectors), as served by vLLM.

    BENCH_UPSTREAM_URL=https://... BENCH_API_KEY=... python -m benchmarks.adapter --port 8766

The harness starts it automatically when endpoint.env sets BENCH_USE_ADAPTER=1.
"""
from __future__ import annotations

import argparse
import base64
import os
import re

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


# ── Upstream: OpenAI-compatible chat completions (vLLM gateway) ──────────────

UPSTREAM_MODEL = os.environ.get("BENCH_UPSTREAM_MODEL", "")
# Embeddings may live on a different server than the chat model.
EMBED_URL = os.environ.get("BENCH_UPSTREAM_EMBED_URL", "").rstrip("/") or UPSTREAM_URL
EMBED_MODEL = os.environ.get("BENCH_UPSTREAM_EMBED_MODEL", "")
# Qwen3-family models think out loud by default. The thinking counts against
# max_tokens and lands in the reply, which breaks Pacific's short extraction
# prompts and its JSON parsing, so it is switched off unless asked for.
DISABLE_THINKING = os.environ.get("BENCH_DISABLE_THINKING", "1").lower() in {"1", "true", "yes"}
_THINK = re.compile(r"<think>.*?</think>", re.S)


def _headers() -> dict:
    return {"Authorization": f"Bearer {API_KEY}"} if API_KEY else {}


async def upstream_embed(texts: list[str]) -> list[list[float]]:
    """Return one vector per text, in order, all of the same length."""
    if not EMBED_MODEL:
        raise RuntimeError("no embedding model configured (BENCH_UPSTREAM_EMBED_MODEL)")
    resp = await client().post(f"{EMBED_URL}/embeddings", headers=_headers(),
                               json={"model": EMBED_MODEL, "input": texts})
    resp.raise_for_status()
    data = sorted(resp.json()["data"], key=lambda d: d["index"])
    return [d["embedding"] for d in data]


async def upstream_generate(prompt: str, image: bytes | None, mime_type: str | None,
                            max_output_tokens: int) -> str:
    """Return the model's text reply. `image` is set for vision calls."""
    content: list[dict] | str = prompt
    if image is not None:
        data_url = f"data:{mime_type or 'image/jpeg'};base64,{base64.b64encode(image).decode()}"
        content = [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": data_url}}]
    body: dict = {"model": UPSTREAM_MODEL, "messages": [{"role": "user", "content": content}],
                  "max_tokens": max_output_tokens}
    if DISABLE_THINKING:
        body["chat_template_kwargs"] = {"enable_thinking": False}
    resp = await client().post(f"{UPSTREAM_URL}/chat/completions", headers=_headers(), json=body)
    resp.raise_for_status()
    text = resp.json()["choices"][0]["message"].get("content") or ""
    return _THINK.sub("", text).strip()


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
    except RuntimeError as exc:
        # Not transient: a 501 skips Pacific's retries and surfaces in preflight.
        return JSONResponse({"error": {"message": str(exc)}}, status_code=501)
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
