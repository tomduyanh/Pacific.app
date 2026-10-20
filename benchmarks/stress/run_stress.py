"""Stress, scale and resilience tests for Pacific's backend.

    python -m benchmarks.stress.run_stress --provider endpoint [--phases scale concurrency ...]

Phases (each starts its own server on a throwaway copy of the app):
    scale        startup, latency, response size and memory vs context-pool size
    concurrency  throughput and tail latency as parallel clients ramp up
    live         the dashboard's live-capture loop: cadence, skips, staleness
    soak         long run with live capture, messages and attach/dismiss;
                 memory and state growth over time
    consistency  concurrent attach/dismiss/detach/message, then state invariants
    crash        SIGKILL during state writes; is session_state.json still valid?
    outage       the provider is unreachable: does Pacific degrade or fail?

Results go to <out>/stress.json; benchmarks/report.py renders them.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import time
from datetime import datetime
from pathlib import Path

import httpx

from ..frames import make_frames
from ..gen_pool import build_pool
from ..harness import PacificServer, make_workdir
from ..providers import pacific_env, provider_context

BENCH = Path(__file__).resolve().parent.parent
SCENARIOS = json.loads((BENCH / "quality" / "scenarios.json").read_text(encoding="utf-8"))["scenarios"]
MESSAGES = [s["messages"][-1] for s in SCENARIOS if s["messages"] and s["labels"]]
ITEM_IDS = [p["id"] for p in build_pool(44)]


def pct(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    v = sorted(values)

    def at(q: float) -> float:
        return round(v[min(len(v) - 1, int(q * len(v)))], 1)

    return {"n": len(v), "mean": round(statistics.fmean(v), 1), "p50": at(0.5), "p95": at(0.95),
            "p99": at(0.99), "max": round(v[-1], 1)}


def start(env: dict, pool_size: int, out: Path, tag: str) -> PacificServer:
    work = make_workdir(build_pool(pool_size))
    return PacificServer(work, env, log=out / f"server-{tag}.log").start()


# ── scale ────────────────────────────────────────────────────────────────────

def phase_scale(env: dict, out: Path, sizes: list[int], n_msgs: int = 30) -> dict:
    results = {}
    for n in sizes:
        server = start(env, n, out, f"scale-{n}")
        try:
            c = httpx.Client(base_url=server.url, timeout=300)
            boot = server.metrics()
            c.post("/api/session/clear")
            for m in MESSAGES[:3]:
                c.post("/api/message", json={"message": m})
            server.reset_metrics()
            msg_ms, msg_bytes, resc_ms = [], [], []
            for i in range(n_msgs):
                t = time.perf_counter()
                r = c.post("/api/message", json={"message": MESSAGES[i % len(MESSAGES)]})
                msg_ms.append((time.perf_counter() - t) * 1000)
                msg_bytes.append(len(r.content))
            for _ in range(n_msgs // 2):
                t = time.perf_counter()
                c.post("/api/rescore")
                resc_ms.append((time.perf_counter() - t) * 1000)
            upload_ms, after_upload_ms = [], []
            for i in range(5):
                t = time.perf_counter()
                c.post("/api/context/upload", json={
                    "display_name": f"bench_upload_{i}.md", "kind": "file", "channel": "semantic",
                    "description": "Benchmark upload", "content": "Notes on rollout of the billing cache. " * 20})
                upload_ms.append((time.perf_counter() - t) * 1000)
                t = time.perf_counter()
                c.post("/api/rescore")
                after_upload_ms.append((time.perf_counter() - t) * 1000)
            m = server.metrics()
            data = server.workdir / "data"
            results[str(n)] = {
                "startup_s": round(server.startup_s, 2),
                "rss_after_start_mb": boot["rss_mb"],
                "rss_after_run_mb": m["rss_mb"],
                "message_ms": pct(msg_ms),
                "rescore_ms": pct(resc_ms),
                "response_kb": round(statistics.fmean(msg_bytes) / 1024, 1),
                "upload_ms": pct(upload_ms),
                "rescore_after_upload_ms": pct(after_upload_ms),
                "pool_json_kb": round((data / "pool.json").stat().st_size / 1024, 1),
                "stages": m["stages"],
                "loop_lag_ms": m["loop_lag_ms"],
            }
            print(f"  scale n={n}: message p50 {results[str(n)]['message_ms']['p50']} ms, "
                  f"p95 {results[str(n)]['message_ms']['p95']} ms, startup {server.startup_s:.1f} s")
        finally:
            server.stop()
    return results


# ── concurrency ──────────────────────────────────────────────────────────────

async def _worker(c: httpx.AsyncClient, stop_at: float, rec: dict, rng: random.Random) -> None:
    while time.perf_counter() < stop_at:
        roll = rng.random()
        if roll < 0.6:
            op, call = "message", c.post("/api/message", json={"message": rng.choice(MESSAGES)})
        elif roll < 0.85:
            op, call = "rescore", c.post("/api/rescore")
        else:
            op, call = "state", c.get("/api/state")
        t = time.perf_counter()
        try:
            r = await call
            ok = r.status_code < 400
        except httpx.HTTPError:
            ok = False
        rec.setdefault(op, []).append((time.perf_counter() - t) * 1000)
        if not ok:
            rec["errors"] = rec.get("errors", 0) + 1


def phase_concurrency(env: dict, out: Path, pool_size: int, levels: list[int], seconds: float) -> dict:
    server = start(env, pool_size, out, "concurrency")
    results = {"pool_size": pool_size, "seconds_per_level": seconds, "levels": {}}
    try:
        async def run_level(k: int) -> dict:
            rec: dict = {}
            async with httpx.AsyncClient(base_url=server.url, timeout=120,
                                         limits=httpx.Limits(max_connections=k + 4)) as c:
                await c.post("/api/session/clear")
                await c.post("/api/message", json={"message": MESSAGES[0]})
                server.reset_metrics()
                stop_at = time.perf_counter() + seconds
                rngs = [random.Random(i) for i in range(k)]
                await asyncio.gather(*(_worker(c, stop_at, rec, r) for r in rngs))
            done = sum(len(v) for key, v in rec.items() if key != "errors")
            m = server.metrics()
            return {
                "throughput_rps": round(done / seconds, 2),
                "errors": rec.get("errors", 0),
                "ops": {op: pct(v) for op, v in rec.items() if op != "errors"},
                "loop_lag_ms": m["loop_lag_ms"],
                "rss_mb": m["rss_mb"],
            }

        for k in levels:
            results["levels"][str(k)] = asyncio.run(run_level(k))
            lv = results["levels"][str(k)]
            print(f"  concurrency {k}: {lv['throughput_rps']} req/s, message p95 "
                  f"{lv['ops'].get('message', {}).get('p95')} ms, errors {lv['errors']}")
    finally:
        server.stop()
    return results


# ── live capture loop (mirrors frontend/src/liveScreenLoop.js) ───────────────

class LiveLoop:
    def __init__(self, c: httpx.AsyncClient, frames: list[str], interval_s: float = 5.0):
        self.c, self.frames, self.interval = c, frames, interval_s
        self.ticks: list[dict] = []
        self.scores: list[dict] = []
        self.scoring = False
        self.pending = True
        self.stopped = False

    async def request_scores(self, frame_at: float) -> None:
        self.pending = True
        if self.scoring:
            return
        self.scoring = True
        try:
            while self.pending and not self.stopped:
                self.pending = False
                t = time.perf_counter()
                try:
                    r = await self.c.post("/api/rescore")
                    ok = r.status_code < 400
                except httpx.HTTPError:
                    ok = False
                done = time.perf_counter()
                self.scores.append({"ok": ok, "ms": (done - t) * 1000, "staleness_ms": (done - frame_at) * 1000})
                if not ok:
                    self.pending = True
                    break
        finally:
            self.scoring = False

    async def run(self, seconds: float) -> None:
        stop_at = time.perf_counter() + seconds
        i = 0
        while time.perf_counter() < stop_at:
            started = time.perf_counter()
            retry = 0.0
            rec = {"at": started}
            try:
                r = await self.c.post("/api/session/screen/live-tick", json={
                    "image_base64": self.frames[i % len(self.frames)], "mime_type": "image/jpeg", "rescore": False})
                i += 1
                rec["status"] = r.status_code
                body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
                if r.status_code >= 400:
                    rec["outcome"] = f"http_{r.status_code}"
                    retry = self.interval
                elif body.get("skipped"):
                    rec["outcome"] = f"skipped_{body.get('reason')}"
                    retry = float(body.get("retry_after_sec") or 0)
                else:
                    rec["outcome"] = "ok"
                    rec["vision_ms"] = (body.get("metrics") or {}).get("vision_ms")
                    if body.get("state_changed") or self.pending:
                        asyncio.create_task(self.request_scores(time.perf_counter()))
            except httpx.HTTPError as exc:
                rec["outcome"] = f"client_{type(exc).__name__}"
                retry = self.interval
            rec["ms"] = (time.perf_counter() - started) * 1000
            self.ticks.append(rec)
            await asyncio.sleep(max(retry, self.interval - (time.perf_counter() - started), 0))
        self.stopped = True

    def summary(self) -> dict:
        starts = [t["at"] for t in self.ticks]
        gaps = [(b - a) * 1000 for a, b in zip(starts, starts[1:])]
        outcomes: dict[str, int] = {}
        for t in self.ticks:
            outcomes[t["outcome"]] = outcomes.get(t["outcome"], 0) + 1
        return {
            "ticks": len(self.ticks),
            "outcomes": outcomes,
            "tick_interval_ms": pct(gaps),
            "tick_request_ms": pct([t["ms"] for t in self.ticks]),
            "vision_ms": pct([t["vision_ms"] for t in self.ticks if t.get("vision_ms") is not None]),
            "rescore_ms": pct([s["ms"] for s in self.scores if s["ok"]]),
            "frame_to_ranking_ms": pct([s["staleness_ms"] for s in self.scores if s["ok"]]),
            "rescore_failures": sum(1 for s in self.scores if not s["ok"]),
        }


async def _messages(c: httpx.AsyncClient, seconds: float, every_s: float, rec: list) -> None:
    stop_at = time.perf_counter() + seconds
    i = 0
    while time.perf_counter() < stop_at:
        await asyncio.sleep(every_s)
        t = time.perf_counter()
        try:
            r = await c.post("/api/message", json={"message": MESSAGES[i % len(MESSAGES)]})
            rec.append({"ok": r.status_code < 400, "ms": (time.perf_counter() - t) * 1000})
        except httpx.HTTPError:
            rec.append({"ok": False, "ms": (time.perf_counter() - t) * 1000})
        i += 1


def phase_live(env: dict, out: Path, pool_size: int, seconds: float) -> dict:
    server = start(env, pool_size, out, "live")
    try:
        async def go():
            async with httpx.AsyncClient(base_url=server.url, timeout=120) as c:
                await c.post("/api/session/clear")
                loop = LiveLoop(c, make_frames(12))
                msgs: list = []
                server.reset_metrics()
                await asyncio.gather(loop.run(seconds), _messages(c, seconds, 20, msgs))
                return {**loop.summary(), "message_ms": pct([m["ms"] for m in msgs if m["ok"]]),
                        "message_failures": sum(1 for m in msgs if not m["ok"])}
        res = asyncio.run(go())
        res["loop_lag_ms"] = server.metrics()["loop_lag_ms"]
        res["pool_size"] = pool_size
        res["seconds"] = seconds
        print(f"  live: {res['ticks']} ticks, outcomes {res['outcomes']}, "
              f"interval p50 {res['tick_interval_ms'].get('p50')} ms")
        return res
    finally:
        server.stop()


# ── soak ─────────────────────────────────────────────────────────────────────

def phase_soak(env: dict, out: Path, pool_size: int, seconds: float, event_rate: float) -> dict:
    """Live loop + messages + attach/dismiss, sampling growth every 10 s.

    Session events are also posted at `event_rate` per second, standing in
    for what live capture records over a much longer session, so growth that
    would take hours of real use shows up within the run.
    """
    server = start(env, pool_size, out, "soak")
    state_file = server.workdir / "data" / "session_state.json"
    samples: list[dict] = []
    try:
        async def sampler(c, stop_at):
            t0 = time.perf_counter()
            while time.perf_counter() < stop_at:
                m = (await c.get("/__bench/metrics")).json()
                t = time.perf_counter()
                await c.post("/api/message", json={"message": random.choice(MESSAGES)})
                samples.append({
                    "t_s": round(time.perf_counter() - t0, 1),
                    "rss_mb": m["rss_mb"],
                    "session_events": m["session_events"],
                    "embed_cache_entries": m["embed_cache_entries"],
                    "state_file_kb": round(state_file.stat().st_size / 1024, 1) if state_file.exists() else 0,
                    "message_ms": round((time.perf_counter() - t) * 1000, 1),
                })
                await asyncio.sleep(10)

        async def events(c, stop_at):
            files = ITEM_IDS[:20]
            n = 0
            while time.perf_counter() < stop_at:
                await c.post("/api/session/event", json={"event": {
                    "type": random.choice(["read", "edit", "browse"]), "file": random.choice(files),
                    "lines_added": random.randrange(10), "content": f"edit {n}"}})
                n += 1
                await asyncio.sleep(1 / event_rate)

        async def churn(c, stop_at):
            while time.perf_counter() < stop_at:
                await asyncio.sleep(15)
                item = random.choice(ITEM_IDS)
                await c.post(f"/api/attach/{item}")
                await asyncio.sleep(5)
                await c.delete(f"/api/attach/{item}")
                await c.post(f"/api/dismiss/{random.choice(ITEM_IDS)}")

        async def go():
            async with httpx.AsyncClient(base_url=server.url, timeout=300) as c:
                await c.post("/api/session/clear")
                stop_at = time.perf_counter() + seconds
                loop = LiveLoop(c, make_frames(12))
                await asyncio.gather(loop.run(seconds), sampler(c, stop_at), events(c, stop_at), churn(c, stop_at))
                return loop.summary()

        live = asyncio.run(go())
        m = server.metrics()
    finally:
        server.stop()

    half = samples[len(samples) // 2:]
    slope = None
    if len(half) >= 3:
        xs = [s["t_s"] for s in half]
        ys = [s["rss_mb"] for s in half]
        mx, my = statistics.fmean(xs), statistics.fmean(ys)
        den = sum((x - mx) ** 2 for x in xs)
        slope = round(sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den * 3600, 1) if den else None
    res = {"pool_size": pool_size, "seconds": seconds, "event_rate_per_s": event_rate,
           "samples": samples, "rss_slope_mb_per_hour_second_half": slope, "live": live,
           "save_session_ms": m["stages"].get("save_session"), "loop_lag_ms": m["loop_lag_ms"]}
    if samples:
        print(f"  soak: rss {samples[0]['rss_mb']} -> {samples[-1]['rss_mb']} MB, events "
              f"{samples[-1]['session_events']}, state file {samples[-1]['state_file_kb']} KB, "
              f"message {samples[0]['message_ms']} -> {samples[-1]['message_ms']} ms")
    return res


# ── consistency ──────────────────────────────────────────────────────────────

def check_invariants(state: dict) -> list[str]:
    problems = []
    attached = [a["id"] for a in state["attached"]]
    status = {p["id"]: p["status"] for p in state["pool"]}
    dismissed = set(state["dismissed_ids"])
    if len(attached) != len(set(attached)):
        problems.append("duplicate ids in attached")
    for i in attached:
        if status.get(i) != "active":
            problems.append(f"attached item {i} has status {status.get(i)!r}")
        if i in dismissed:
            problems.append(f"attached item {i} is also dismissed")
    for i, s in status.items():
        if s == "active" and i not in attached:
            problems.append(f"item {i} is 'active' but not attached")
    return problems


def phase_consistency(env: dict, out: Path, ops: int, concurrency: int) -> dict:
    server = start(env, 44, out, "consistency")
    try:
        async def go():
            violations: list[dict] = []
            async with httpx.AsyncClient(base_url=server.url, timeout=120) as c:
                await c.post("/api/session/clear")
                rng = random.Random(1)
                sem = asyncio.Semaphore(concurrency)
                targets = ITEM_IDS[:8]  # a small set so operations collide

                async def op(n: int):
                    async with sem:
                        roll, item = rng.random(), rng.choice(targets)
                        if roll < 0.3:
                            await c.post("/api/message", json={"message": rng.choice(MESSAGES)})
                        elif roll < 0.55:
                            await c.post(f"/api/attach/{item}")
                        elif roll < 0.8:
                            await c.post(f"/api/dismiss/{item}")
                        else:
                            await c.delete(f"/api/attach/{item}")
                        if n % 10 == 0:
                            problems = check_invariants((await c.get("/api/state")).json())
                            if problems:
                                violations.append({"after_op": n, "problems": problems})

                await asyncio.gather(*(op(n) for n in range(ops)))
                final = check_invariants((await c.get("/api/state")).json())
            return violations, final

        violations, final = asyncio.run(go())
    finally:
        server.stop()
    kinds: dict[str, int] = {}
    for v in violations:
        for p in v["problems"]:
            key = p.split(" ", 1)[0] + " " + p.split(" ", 3)[-1] if p.startswith(("attached", "item")) else p
            kinds[key] = kinds.get(key, 0) + 1
    res = {"ops": ops, "concurrency": concurrency, "snapshots_with_violations": len(violations),
           "violation_kinds": kinds, "final_violations": final, "examples": violations[:5]}
    print(f"  consistency: {len(violations)} snapshots with violations, final {len(final)}")
    return res


# ── crash safety ─────────────────────────────────────────────────────────────

def phase_crash(env: dict, out: Path, trials: int, preload_events: int) -> dict:
    work = make_workdir(build_pool(44))
    state_file = work / "data" / "session_state.json"
    outcomes = []
    for trial in range(trials):
        server = PacificServer(work, env, log=out / "server-crash.log").start()
        before = server.metrics()["session_events"]
        c = httpx.Client(base_url=server.url, timeout=60)
        if trial == 0:
            for i in range(preload_events):
                c.post("/api/session/event", json={"event": {"type": "read", "file": f"f{i % 50}.py",
                                                            "content": "x" * 200}})
            c.post("/api/message", json={"message": MESSAGES[0]})
            before = server.metrics()["session_events"]

        async def hammer(stop_after: float):
            async with httpx.AsyncClient(base_url=server.url, timeout=60) as ac:
                async def loop():
                    while True:
                        try:
                            await ac.post(f"/api/dismiss/{random.choice(ITEM_IDS)}")
                        except httpx.HTTPError:
                            return
                tasks = [asyncio.create_task(loop()) for _ in range(4)]
                await asyncio.sleep(stop_after)
                server.kill_hard()
                await asyncio.gather(*tasks, return_exceptions=True)

        asyncio.run(hammer(random.uniform(0.3, 1.5)))
        try:
            json.loads(state_file.read_text(encoding="utf-8"))
            valid = True
        except (json.JSONDecodeError, FileNotFoundError, UnicodeDecodeError):
            valid = False
        restarted = PacificServer(work, env, log=out / "server-crash.log").start()
        after = restarted.metrics()["session_events"]
        restarted.stop()
        outcomes.append({"trial": trial, "file_valid": valid, "events_before": before, "events_after_restart": after,
                         "state_file_kb": round(state_file.stat().st_size / 1024, 1) if state_file.exists() else 0})
        if not valid:
            # Repair so the next trial measures a fresh write, not the same corruption.
            state_file.unlink(missing_ok=True)
    corrupt = sum(1 for o in outcomes if not o["file_valid"])
    lost = sum(1 for o in outcomes if o["events_after_restart"] < o["events_before"])
    print(f"  crash: {corrupt}/{trials} corrupt state files, {lost}/{trials} restarts lost session events")
    return {"trials": trials, "corrupt_files": corrupt, "sessions_lost": lost, "outcomes": outcomes}


# ── outage ───────────────────────────────────────────────────────────────────

def phase_outage(out: Path, pool_size: int, n_msgs: int) -> dict:
    env = pacific_env("outage")
    server = start(env, pool_size, out, "outage")
    try:
        c = httpx.Client(base_url=server.url, timeout=300)
        c.post("/api/session/clear")
        ms, ok, suggested = [], 0, 0
        for i in range(n_msgs):
            t = time.perf_counter()
            r = c.post("/api/message", json={"message": MESSAGES[i % len(MESSAGES)]})
            ms.append((time.perf_counter() - t) * 1000)
            if r.status_code < 400:
                ok += 1
                suggested += bool(r.json().get("suggestions"))
        tick = c.post("/api/session/screen/live-tick", json={"image_base64": make_frames(1)[0], "mime_type": "image/jpeg"})
        m = server.metrics()
        res = {"pool_size": pool_size, "startup_s": round(server.startup_s, 2), "message_ms": pct(ms),
               "message_success": ok, "messages": n_msgs, "messages_with_suggestions": suggested,
               "live_tick_status": tick.status_code, "stages": m["stages"]}
        print(f"  outage: startup {res['startup_s']} s, message p50 {res['message_ms']['p50']} ms, "
              f"{ok}/{n_msgs} ok, live tick -> {tick.status_code}")
        return res
    finally:
        server.stop()


# ── main ─────────────────────────────────────────────────────────────────────

ALL_PHASES = ["scale", "concurrency", "live", "soak", "consistency", "crash", "outage"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="endpoint")
    ap.add_argument("--phases", nargs="+", default=ALL_PHASES, choices=ALL_PHASES)
    ap.add_argument("--sizes", type=int, nargs="+", default=[44, 1000, 5000, 10000])
    ap.add_argument("--pool-size", type=int, default=1000, help="pool for concurrency/live/soak/outage")
    ap.add_argument("--levels", type=int, nargs="+", default=[1, 2, 4, 8, 16])
    ap.add_argument("--level-seconds", type=float, default=15)
    ap.add_argument("--live-seconds", type=float, default=120)
    ap.add_argument("--soak-seconds", type=float, default=600)
    ap.add_argument("--soak-event-rate", type=float, default=10, help="session events per second during soak")
    ap.add_argument("--crash-trials", type=int, default=20)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    out = args.out or BENCH / "results" / f"{datetime.now():%Y%m%d-%H%M}-{args.provider}"
    out.mkdir(parents=True, exist_ok=True)
    path = out / "stress.json"
    results = json.loads(path.read_text()) if path.exists() else {}
    results["meta"] = {"provider": args.provider, "created": datetime.now().isoformat(timespec="seconds"),
                       "args": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()}}

    with provider_context(args.provider) as env:
        for phase in args.phases:
            print(f"[{phase}]")
            if phase == "scale":
                results[phase] = phase_scale(env, out, args.sizes)
            elif phase == "concurrency":
                results[phase] = phase_concurrency(env, out, args.pool_size, args.levels, args.level_seconds)
            elif phase == "live":
                results[phase] = phase_live(env, out, args.pool_size, args.live_seconds)
            elif phase == "soak":
                results[phase] = phase_soak(env, out, args.pool_size, args.soak_seconds, args.soak_event_rate)
            elif phase == "consistency":
                results[phase] = phase_consistency(env, out, ops=400, concurrency=16)
            elif phase == "crash":
                results[phase] = phase_crash(env, out, args.crash_trials, preload_events=3000)
            elif phase == "outage":
                results[phase] = phase_outage(out, args.pool_size, n_msgs=10)
            path.write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
