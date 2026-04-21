import asyncio
import hashlib
import math
import os

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

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_EMBED_MODEL = "models/gemini-embedding-001"
GEMINI_LLM_MODEL = "models/gemini-flash-latest"

_anthropic_client = None
_warnings_shown = set()


def _warn_once(key: str, message: str) -> None:
    if key not in _warnings_shown:
        print(message)
        _warnings_shown.add(key)


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


def _embed_gemini(text: str) -> list[float]:
    url = f"{GEMINI_BASE}/{GEMINI_EMBED_MODEL}:embedContent?key={GEMINI_API_KEY}"
    resp = httpx.post(url, json={
        "model": GEMINI_EMBED_MODEL,
        "content": {"parts": [{"text": text}]},
        "taskType": "RETRIEVAL_DOCUMENT",
    }, timeout=30)
    resp.raise_for_status()
    return resp.json()["embedding"]["values"]


def embed(text: str) -> list[float]:
    if PROVIDER == "gemini":
        if _gemini_available():
            try:
                return _embed_gemini(text)
            except Exception as exc:
                _warn_once("gemini_embed", f"Gemini embeddings unavailable; using mock. Reason: {exc}")
        return _embed_mock(text)
    if PROVIDER == "anthropic":
        return _embed_mock(text)
    return _embed_mock(text)


async def llm_call(prompt: str) -> str:
    if PROVIDER == "anthropic" and ANTHROPIC_API_KEY:
        try:
            return await _llm_anthropic(prompt)
        except Exception as exc:
            _warn_once("anthropic_llm", f"Anthropic LLM unavailable; using fallback. Reason: {exc}")
    if PROVIDER == "gemini" and _gemini_available():
        try:
            return await _llm_gemini(prompt)
        except Exception as exc:
            _warn_once("gemini_llm", f"Gemini LLM unavailable; using fallback. Reason: {exc}")
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
    url = f"{GEMINI_BASE}/{GEMINI_LLM_MODEL}:generateContent?key={GEMINI_API_KEY}"
    loop = asyncio.get_running_loop()

    def _call() -> str:
        resp = httpx.post(url, json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": 200},
        }, timeout=30)
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]

    return await loop.run_in_executor(None, _call)


async def async_embed(text: str) -> list[float]:
    """Non-blocking embed — runs the synchronous embed() in a thread so it doesn't block the event loop."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, embed, text)


async def llm_vision_call(prompt: str, image_bytes: bytes, mime_type: str) -> str:
    """Multimodal Gemini call; used for screen → FileGram event extraction."""
    if not _gemini_available():
        raise RuntimeError("GEMINI_API_KEY is required for vision screen analysis.")
    import base64
    url = f"{GEMINI_BASE}/{GEMINI_LLM_MODEL}:generateContent?key={GEMINI_API_KEY}"
    loop = asyncio.get_running_loop()

    def _call() -> str:
        resp = httpx.post(url, json={
            "contents": [{"parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": mime_type, "data": base64.b64encode(image_bytes).decode()}},
            ]}],
            "generationConfig": {"maxOutputTokens": 1024},
        }, timeout=60)
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"] or ""

    return await loop.run_in_executor(None, _call)
