"""Which model backend a benchmark run talks to.

    mock      Pacific's own offline mode: built-in hash embeddings, canned LLM
              text, no vision. Measures Pacific's compute with zero network.
              Ranking quality numbers from this mode are NOT meaningful
              (the embeddings carry no semantics); use it to validate the
              harness and as the zero-network performance floor.
    endpoint  The custom model endpoint, configured in benchmarks/endpoint.env
              (copy endpoint.env.example). The API key is read from the
              BENCH_API_KEY environment variable, never from a file.
    outage    Provider configured but unreachable (a closed local port), to
              measure how Pacific degrades when the endpoint is down.
"""
from __future__ import annotations

import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

from .harness import REPO, free_port, wait_http

BENCH_DIR = Path(__file__).resolve().parent
ENDPOINT_ENV = BENCH_DIR / "endpoint.env"


def _read_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def endpoint_settings() -> dict[str, str]:
    """endpoint.env, overridable by real environment variables of the same name."""
    settings = _read_env_file(ENDPOINT_ENV)
    for key in list(settings) + ["BENCH_GEMINI_BASE", "BENCH_EMBED_DIM", "BENCH_EMBED_MODEL",
                                 "BENCH_LLM_MODEL", "BENCH_VISION_MODEL", "BENCH_USE_ADAPTER"]:
        if os.environ.get(key):
            settings[key] = os.environ[key]
    return settings


def pacific_env(provider: str, *, gemini_base: str | None = None) -> dict[str, str]:
    """Environment for a Pacific process (and for in-process baseline embeddings)."""
    common = {"PYTHONDONTWRITEBYTECODE": "1"}
    if provider == "mock":
        return {**common, "EMBEDDING_PROVIDER": "mock", "GEMINI_API_KEY": "", "EMBED_DIM": "768"}
    if provider == "outage":
        return {**common, "EMBEDDING_PROVIDER": "gemini", "GEMINI_API_KEY": "unused",
                "GEMINI_BASE": f"http://127.0.0.1:{free_port()}", "EMBED_DIM": "768"}
    if provider == "endpoint":
        s = endpoint_settings()
        base = gemini_base or s.get("BENCH_GEMINI_BASE")
        key = os.environ.get("BENCH_API_KEY", "")
        missing = [name for name, val in (("BENCH_GEMINI_BASE", base), ("BENCH_EMBED_DIM", s.get("BENCH_EMBED_DIM")),
                                          ("BENCH_API_KEY (env var)", key)) if not val]
        if missing:
            raise SystemExit(f"endpoint provider is not configured; missing: {', '.join(missing)}. "
                             f"See benchmarks/endpoint.env.example.")
        env = {**common, "EMBEDDING_PROVIDER": "gemini", "GEMINI_API_KEY": key,
               "GEMINI_BASE": base, "EMBED_DIM": s["BENCH_EMBED_DIM"]}
        for src, dst in (("BENCH_EMBED_MODEL", "GEMINI_EMBED_MODEL"), ("BENCH_LLM_MODEL", "GEMINI_LLM_MODEL"),
                         ("BENCH_VISION_MODEL", "GEMINI_VISION_MODEL")):
            if s.get(src):
                env[dst] = s[src]
        return env
    raise SystemExit(f"unknown provider {provider!r}; expected mock, endpoint or outage")


def uses_adapter() -> bool:
    return endpoint_settings().get("BENCH_USE_ADAPTER", "0").lower() in {"1", "true", "yes"}


@contextmanager
def provider_context(provider: str):
    """Yield the Pacific environment for `provider`, starting the adapter if configured."""
    if provider != "endpoint" or not uses_adapter():
        yield pacific_env(provider)
        return
    upstream = endpoint_settings().get("BENCH_UPSTREAM_URL", "")
    if not upstream:
        raise SystemExit("BENCH_USE_ADAPTER=1 but BENCH_UPSTREAM_URL is empty in endpoint.env")
    port = free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "benchmarks.adapter", "--port", str(port)],
        cwd=REPO, env={**os.environ, "BENCH_UPSTREAM_URL": upstream},
    )
    try:
        wait_http(f"http://127.0.0.1:{port}/", 30, proc)
        yield pacific_env(provider, gemini_base=f"http://127.0.0.1:{port}")
    finally:
        proc.terminate()
        proc.wait(10)
