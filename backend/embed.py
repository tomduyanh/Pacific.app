from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import re
import threading
from pathlib import Path

import httpx

env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
try:
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
except Exception:
    pass

PROVIDER = os.getenv("EMBEDDING_PROVIDER", "mock").strip().lower()
EMBED_DIM = int(os.getenv("EMBED_DIM", "768"))
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Overridable so a Gemini-compatible proxy or local stub can stand in for the
# real API (benchmarks, offline testing, alternative model backends).
GEMINI_BASE = os.getenv("GEMINI_BASE", "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
GEMINI_EMBED_MODEL = os.getenv("GEMINI_EMBED_MODEL", "models/gemini-embedding-001")

# gemini-flash-latest resolves to a 2.5 Flash build with *thinking* on by
# default, and thinking tokens share maxOutputTokens. Measured on this project's
# own prompts it spent 191 thinking tokens to emit a 7-token answer against a
# 200-token cap — so every summary, subproblem and query expansion came back
# truncated — and it returned 503 on roughly half of text calls and all vision
# calls. flash-lite does no thinking, answers these extraction prompts in full,
# and measured 4.3x faster with zero errors. Override via env if that changes.
GEMINI_LLM_MODEL = os.getenv("GEMINI_LLM_MODEL", "models/gemini-flash-lite-latest")
GEMINI_VISION_MODEL = os.getenv("GEMINI_VISION_MODEL", GEMINI_LLM_MODEL)

# Transient statuses worth one more attempt before degrading to the fallback.
_RETRY_STATUS = frozenset({408, 429, 500, 502, 503, 504})

# Gemini caps batchEmbedContents at 100 requests per call.
EMBED_BATCH_SIZE = 100

CACHE_PATH = Path(__file__).parent.parent / "data" / "embed_cache.json"

_anthropic_client = None
_warnings_shown = set()


_SECRET_RE = re.compile(r"AIza[A-Za-z0-9_\-]{10,}|key=[A-Za-z0-9_\-]{10,}")


def _redact(text: object) -> str:
    """Strip anything that looks like an API key out of a message.

    Defence in depth: the key now travels in a header rather than the query
    string, but httpx exceptions quote whatever URL they were given, and a
    warning is the one place a raw exception reaches a console or a log file.
    """
    return _SECRET_RE.sub("key=***REDACTED***", str(text))


def _warn_once(key: str, message: str) -> None:
    if key not in _warnings_shown:
        print(_redact(message))
        _warnings_shown.add(key)


def _auth_headers() -> dict:
    """Gemini accepts the key as a header, which keeps it out of URLs entirely —
    out of exception text, access logs, and anything that records a request line."""
    return {"x-goog-api-key": GEMINI_API_KEY}


# ── HTTP clients ─────────────────────────────────────────────────────────────
# One pooled client per flavour. Reusing connections removes a DNS lookup and a
# TLS handshake (~100-300 ms) from every embed / LLM call; the previous code
# opened a fresh connection for each one.

_HTTP_LIMITS = httpx.Limits(max_connections=32, max_keepalive_connections=16, keepalive_expiry=90.0)

_sync_client: httpx.Client | None = None
_async_client: httpx.AsyncClient | None = None
_client_lock = threading.Lock()


def _sync_http() -> httpx.Client:
    global _sync_client
    if _sync_client is None:
        with _client_lock:
            if _sync_client is None:
                _sync_client = httpx.Client(timeout=30, limits=_HTTP_LIMITS)
    return _sync_client


def _async_http() -> httpx.AsyncClient:
    global _async_client
    if _async_client is None:
        _async_client = httpx.AsyncClient(timeout=60, limits=_HTTP_LIMITS)
    return _async_client


async def _post_retrying(url: str, payload: dict, *, attempts: int = 3) -> httpx.Response:
    """POST with exponential backoff over transient Gemini failures.

    The free tier returns 503 intermittently. Without a retry each one silently
    degraded a rescore to the generic fallback string, and _warn_once meant the
    warning was printed only the first time it ever happened.
    """
    delay = 0.4
    for attempt in range(attempts):
        try:
            resp = await _async_http().post(url, json=payload, headers=_auth_headers())
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            last_error: Exception = exc
        else:
            if resp.status_code not in _RETRY_STATUS:
                resp.raise_for_status()
                return resp
            last_error = httpx.HTTPStatusError(
                f"Gemini returned {resp.status_code}", request=resp.request, response=resp
            )
        if attempt == attempts - 1:
            raise last_error
        await asyncio.sleep(delay)
        delay *= 2
    raise RuntimeError("unreachable")


async def aclose_clients() -> None:
    """Release pooled connections on app shutdown."""
    global _async_client, _sync_client
    if _async_client is not None:
        await _async_client.aclose()
        _async_client = None
    if _sync_client is not None:
        _sync_client.close()
        _sync_client = None


# ── Embedding cache ──────────────────────────────────────────────────────────
# An embedding is a pure function of (provider, model, dim, text), so it caches
# perfectly. The in-memory map removes repeat work inside a session (the same
# workspace text is re-embedded on every live tick); the JSON file carries pool
# embeddings across restarts so a cold start doesn't re-embed all 44 items.

_CACHE_NS = "{0}:{1}:{2}".format(
    PROVIDER,
    GEMINI_EMBED_MODEL if PROVIDER == "gemini" else "mock",
    EMBED_DIM,
)
_cache: dict[str, list[float]] = {}
_cache_lock = threading.Lock()
_cache_dirty = False


def _cache_key(text: str) -> str:
    return hashlib.sha256((_CACHE_NS + "\x00" + text).encode("utf-8")).hexdigest()


def load_cache() -> None:
    """Populate the in-memory cache from disk. Safe to call when the file is missing."""
    try:
        raw = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return
    if raw.get("namespace") != _CACHE_NS:
        return  # provider/model/dim changed — stale vectors are unusable
    entries = raw.get("entries")
    if isinstance(entries, dict):
        with _cache_lock:
            _cache.update({k: v for k, v in entries.items() if isinstance(v, list)})


def save_cache() -> None:
    """Persist the cache if anything new was embedded since the last save."""
    global _cache_dirty
    with _cache_lock:
        if not _cache_dirty:
            return
        snapshot = dict(_cache)
        _cache_dirty = False
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(
            json.dumps({"namespace": _CACHE_NS, "entries": snapshot}),
            encoding="utf-8",
        )
    except Exception as exc:
        _warn_once("cache_save", "Could not persist embedding cache: {0}".format(_redact(exc)))


def _cache_get(text: str) -> list[float] | None:
    with _cache_lock:
        return _cache.get(_cache_key(text))


def _cache_put(text: str, vec: list[float]) -> None:
    global _cache_dirty
    if not vec:
        return
    with _cache_lock:
        _cache[_cache_key(text)] = vec
        _cache_dirty = True


def _gemini_available() -> bool:
    if not GEMINI_API_KEY:
        _warn_once("gemini_key", "GEMINI_API_KEY is not set; using mock embeddings.")
        return False
    return True


def _get_anthropic():
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic
        _anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _anthropic_client


def _embed_mock(text: str) -> list[float]:
    """Deterministic unit-normalized pseudo-embedding via LCG seeded from text hash."""
    seed = int.from_bytes(hashlib.sha256(text.encode()).digest(), "big")
    vec = []
    for _ in range(EMBED_DIM):
        seed = (seed * 6364136223846793005 + 1442695040888963407) & 0xFFFFFFFFFFFFFFFF
        vec.append((seed & 0xFFFF) / 0xFFFF * 2 - 1)
    norm = math.sqrt(sum(v * v for v in vec))
    return [v / norm for v in vec] if norm > 0 else vec


def _embed_payload(text: str) -> dict:
    return {
        "model": GEMINI_EMBED_MODEL,
        "content": {"parts": [{"text": text}]},
        "taskType": "RETRIEVAL_DOCUMENT",
    }


def _embed_url(method: str) -> str:
    return "{0}/{1}:{2}".format(GEMINI_BASE, GEMINI_EMBED_MODEL, method)


def _embed_gemini(text: str) -> list[float]:
    resp = _sync_http().post(_embed_url("embedContent"), json=_embed_payload(text), headers=_auth_headers())
    resp.raise_for_status()
    return resp.json()["embedding"]["values"]


async def _aembed_gemini(text: str) -> list[float]:
    resp = await _post_retrying(_embed_url("embedContent"), _embed_payload(text))
    resp.raise_for_status()
    return resp.json()["embedding"]["values"]


async def _aembed_gemini_batch(texts: list[str]) -> list[list[float]]:
    """One round trip for up to EMBED_BATCH_SIZE texts."""
    resp = await _post_retrying(
        _embed_url("batchEmbedContents"),
        {"requests": [_embed_payload(t) for t in texts]},
    )
    resp.raise_for_status()
    return [e["values"] for e in resp.json()["embeddings"]]


def embed(text: str) -> list[float]:
    """Synchronous embed. Prefer async_embed on request paths."""
    cached = _cache_get(text)
    if cached is not None:
        return cached

    if PROVIDER == "gemini" and _gemini_available():
        try:
            vec = _embed_gemini(text)
            _cache_put(text, vec)
            return vec
        except Exception as exc:
            _warn_once("gemini_embed", "Gemini embeddings unavailable; using mock. Reason: {0}".format(_redact(exc)))

    vec = _embed_mock(text)
    _cache_put(text, vec)
    return vec


async def async_embed(text: str) -> list[float]:
    """Non-blocking embed. Hits the cache first, then a pooled async HTTP call."""
    cached = _cache_get(text)
    if cached is not None:
        return cached

    if PROVIDER == "gemini" and _gemini_available():
        try:
            vec = await _aembed_gemini(text)
            _cache_put(text, vec)
            return vec
        except Exception as exc:
            _warn_once("gemini_embed", "Gemini embeddings unavailable; using mock. Reason: {0}".format(_redact(exc)))

    # The mock embedding loops EMBED_DIM times in Python — keep it off the loop.
    loop = asyncio.get_running_loop()
    vec = await loop.run_in_executor(None, _embed_mock, text)
    _cache_put(text, vec)
    return vec


async def async_embed_many(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts — deduplicated, cached, and batched into few round trips.

    Used for the startup pool warm-up: 44 sequential calls collapse into one
    batch request, or into zero when the disk cache is warm.
    """
    results: list[list[float] | None] = [None] * len(texts)
    pending: dict[str, list[int]] = {}

    for i, text in enumerate(texts):
        cached = _cache_get(text)
        if cached is not None:
            results[i] = cached
        else:
            pending.setdefault(text, []).append(i)

    if not pending:
        return [r or [] for r in results]

    unique = list(pending)
    vectors: list[list[float]] | None = None

    if PROVIDER == "gemini" and _gemini_available():
        chunks = [unique[i:i + EMBED_BATCH_SIZE] for i in range(0, len(unique), EMBED_BATCH_SIZE)]
        try:
            batched = await asyncio.gather(*(_aembed_gemini_batch(c) for c in chunks))
            vectors = [v for chunk in batched for v in chunk]
        except Exception as exc:
            _warn_once("gemini_batch", "Gemini batch embeddings unavailable; using mock. Reason: {0}".format(_redact(exc)))

    if vectors is None or len(vectors) != len(unique):
        loop = asyncio.get_running_loop()
        vectors = list(await asyncio.gather(
            *(loop.run_in_executor(None, _embed_mock, t) for t in unique)
        ))

    for text, vec in zip(unique, vectors):
        _cache_put(text, vec)
        for idx in pending[text]:
            results[idx] = vec

    return [r or [] for r in results]


async def llm_call(prompt: str) -> str:
    if PROVIDER == "anthropic" and ANTHROPIC_API_KEY:
        try:
            return await _llm_anthropic(prompt)
        except Exception as exc:
            _warn_once("anthropic_llm", "Anthropic LLM unavailable; using fallback. Reason: {0}".format(_redact(exc)))
    if PROVIDER == "gemini" and _gemini_available():
        try:
            return await _llm_gemini(prompt)
        except Exception as exc:
            _warn_once("gemini_llm", "Gemini LLM unavailable; using fallback. Reason: {0}".format(_redact(exc)))
    return "User is working on a software development task."


async def _llm_anthropic(prompt: str) -> str:
    client = _get_anthropic()
    loop = asyncio.get_running_loop()
    resp = await loop.run_in_executor(
        None,
        lambda: client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        ),
    )
    return resp.content[0].text


async def _llm_gemini(prompt: str) -> str:
    url = "{0}/{1}:generateContent".format(GEMINI_BASE, GEMINI_LLM_MODEL)
    resp = await _post_retrying(url, {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 200},
    })
    return resp.json()["candidates"][0]["content"]["parts"][0]["text"]


async def llm_vision_call(prompt: str, image_bytes: bytes, mime_type: str) -> str:
    """Multimodal Gemini call; used for screen → FileGram event extraction."""
    if not _gemini_available():
        raise RuntimeError("GEMINI_API_KEY is required for vision screen analysis.")
    import base64
    url = "{0}/{1}:generateContent".format(GEMINI_BASE, GEMINI_VISION_MODEL)
    loop = asyncio.get_running_loop()
    # base64 of a full frame is CPU-bound enough to stall the loop — offload it.
    encoded = await loop.run_in_executor(None, lambda: base64.b64encode(image_bytes).decode())
    resp = await _post_retrying(url, {
        "contents": [{"parts": [
            {"text": prompt},
            {"inline_data": {"mime_type": mime_type, "data": encoded}},
        ]}],
        "generationConfig": {"maxOutputTokens": 1024},
    })
    return resp.json()["candidates"][0]["content"]["parts"][0]["text"] or ""
