"""Check a model endpoint against Pacific's own client code before benchmarking.

    BENCH_API_KEY=... python -m benchmarks.preflight [--provider endpoint|mock] [--samples 5]

Calls every method Pacific uses (single and batch embedding, text generation,
vision) through backend/embed.py and backend/vlm_screen.py, so a pass means
Pacific itself can use the endpoint, not just that it answers HTTP. Exits
non-zero on any failure.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import os
import statistics
import sys
import time

from .frames import make_frames
from .providers import provider_context


def _cos(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


async def _timed(fn, samples: int):
    times, result = [], None
    for _ in range(samples):
        started = time.perf_counter()
        result = await fn()
        times.append((time.perf_counter() - started) * 1000)
    return result, times


async def run_checks(samples: int) -> list[tuple[str, bool, str]]:
    # Imported here: backend.embed reads its provider settings at import time.
    from backend import embed
    from backend.vlm_screen import analyze_live_screen

    dim = embed.EMBED_DIM
    results: list[tuple[str, bool, str]] = []

    def lat(times: list[float]) -> str:
        return f"p50 {statistics.median(times):.0f} ms, max {max(times):.0f} ms over {len(times)}"

    async def check(name, coro_fn, verify):
        try:
            value, times = await _timed(coro_fn, samples)
            ok, detail = verify(value)
            results.append((name, ok, f"{detail}; {lat(times)}"))
        except Exception as exc:  # noqa: BLE001 - report every failure, keep going
            results.append((name, False, f"{type(exc).__name__}: {exc}"))

    probe = f"preflight {time.time()}"  # bypass the embedding cache
    await check(
        "embedContent",
        lambda: embed._aembed_gemini(probe),
        lambda v: (len(v) == dim, f"dim {len(v)} (EMBED_DIM {dim})"),
    )
    texts = [f"{probe} {i}" for i in range(5)]
    await check(
        "batchEmbedContents",
        lambda: embed._aembed_gemini_batch(texts),
        lambda v: (len(v) == 5 and all(len(x) == dim for x in v), f"{len(v)} vectors"),
    )

    async def semantic():
        a, b, c = await embed._aembed_gemini_batch([
            "How do we roll back a failed production deployment?",
            "Steps to revert a bad release to the previous version",
            "Calories in an avocado",
        ])
        return _cos(a, b), _cos(a, c)

    await check(
        "embedding semantics",
        semantic,
        lambda v: (v[0] > v[1], f"related {v[0]:.3f} vs unrelated {v[1]:.3f}"),
    )
    await check(
        "generateContent (text)",
        lambda: embed._llm_gemini("List three words related to databases, one per line."),
        lambda v: (bool(v and v.strip()), repr(v.strip()[:60])),
    )
    frame = base64.b64decode(make_frames(1)[0])
    await check(
        "generateContent (vision, live-screen JSON)",
        lambda: analyze_live_screen(frame, "image/jpeg", "", ""),
        lambda v: (bool(v[0].get("screen_analysis")), repr(v[0].get("commentary", "")[:60])),
    )
    await embed.aclose_clients()
    return results


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="endpoint")
    ap.add_argument("--samples", type=int, default=5)
    args = ap.parse_args()
    if args.provider == "mock":
        raise SystemExit("preflight checks a remote endpoint; mock mode makes no calls to check")
    with provider_context(args.provider) as env:
        os.environ.update(env)
        results = asyncio.run(run_checks(args.samples))
    width = max(len(name) for name, _, _ in results)
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name.ljust(width)}  {detail}")
    sys.exit(0 if all(ok for _, ok, _ in results) else 1)


if __name__ == "__main__":
    main()
