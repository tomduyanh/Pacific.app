"""Pacific's FastAPI app with benchmark instrumentation bolted on from outside.

Wraps the rescore pipeline's stages with timers and runs an event-loop lag
probe, without editing the product code. Adds two routes:

    GET  /__bench/metrics   stage timings, loop lag, RSS
    POST /__bench/reset     clear collected samples

Run with:  uvicorn benchmarks.instrumented_app:app
(from a working copy whose backend/ and data/ the benchmark may freely mutate).
"""
from __future__ import annotations

import asyncio
import functools
import os
import time
from collections import defaultdict
from contextlib import asynccontextmanager

import psutil

import backend.main as main
import backend.scoring as scoring
from backend.state import AppState

SAMPLES: dict[str, list[float]] = defaultdict(list)
LAG: list[float] = []
_PROC = psutil.Process(os.getpid())


def _record(stage: str, started: float) -> None:
    SAMPLES[stage].append((time.perf_counter() - started) * 1000)


def _time_async(stage: str, fn):
    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        started = time.perf_counter()
        try:
            return await fn(*args, **kwargs)
        finally:
            _record(stage, started)
    return wrapper


def _time_sync(stage: str, fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        started = time.perf_counter()
        try:
            return fn(*args, **kwargs)
        finally:
            _record(stage, started)
    return wrapper


# Names main.py imported directly must be patched on main, not on their home module.
main._rescore = _time_async("rescore_total", main._rescore)
main.score_all_expanded = _time_async("score_all_expanded", main.score_all_expanded)
main.expand_query = _time_async("expand_query", main.expand_query)
main.build_task_profile = _time_async("task_profile", main.build_task_profile)
main.build_h_vec = _time_async("h_vec", main.build_h_vec)
main.async_embed = _time_async("embed_query", main.async_embed)
main.compute_fingerprint = _time_sync("fingerprint", main.compute_fingerprint)
main.select_suggestions = _time_sync("select_suggestions", main.select_suggestions)
main._state_payload = _time_sync("state_payload", main._state_payload)
scoring._build_index = _time_sync("build_index_bm25", scoring._build_index)
scoring._merge_scores = _time_sync("merge_scores", scoring._merge_scores)
AppState.save_session = _time_sync("save_session", AppState.save_session)


async def _lag_probe(interval: float = 0.01) -> None:
    """Sleep `interval` repeatedly; any overshoot is time the loop was blocked."""
    while True:
        started = time.perf_counter()
        await asyncio.sleep(interval)
        LAG.append(max(0.0, (time.perf_counter() - started - interval) * 1000))


def _pct(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    v = sorted(values)

    def at(q: float) -> float:
        return round(v[min(len(v) - 1, int(q * len(v)))], 2)

    return {"n": len(v), "mean": round(sum(v) / len(v), 2), "p50": at(0.5),
            "p95": at(0.95), "p99": at(0.99), "max": round(v[-1], 2)}


app = main.app
_inner_lifespan = app.router.lifespan_context


@asynccontextmanager
async def _lifespan(application):
    started = time.perf_counter()
    async with _inner_lifespan(application) as state:
        SAMPLES["startup"].append((time.perf_counter() - started) * 1000)
        probe = asyncio.create_task(_lag_probe())
        try:
            yield state
        finally:
            probe.cancel()


app.router.lifespan_context = _lifespan


@app.get("/__bench/metrics")
async def bench_metrics():
    mem = _PROC.memory_info()
    return {
        "stages": {k: _pct(v) for k, v in SAMPLES.items()},
        "loop_lag_ms": _pct(LAG),
        "rss_mb": round(mem.rss / 2**20, 1),
        "pool_size": len(main.app_state.pool),
        "session_events": len(main.app_state.session_events),
    }


@app.post("/__bench/reset")
async def bench_reset():
    for k in list(SAMPLES):
        if k != "startup":
            SAMPLES[k].clear()
    LAG.clear()
    return {"ok": True}


# The SPA catch-all registered by main.py would shadow routes added after it;
# move ours to the front.
_bench = [r for r in app.router.routes if getattr(r, "path", "").startswith("/__bench")]
app.router.routes[:] = _bench + [r for r in app.router.routes if r not in _bench]
