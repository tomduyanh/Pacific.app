"""Retrieval quality under a token budget: Pacific vs baselines.

    python -m benchmarks.quality.run_quality --provider endpoint [--pool-size 44] [--out DIR]

For each labelled scenario, Pacific is driven through its real HTTP API
(clear session, replay events and window context, send the messages) and its
full ranking is read back. Baselines rank the same pool from the same text.
Every ranking is packed into each budget with the same first-fit packer and
scored against the labels (see metrics.py).

Baselines see the final message plus the window context and file names as
one query string: the same evidence Pacific gets, minus Pacific's learned
signals, history and query expansion. That makes the hybrid baseline a strong
ablation, not a straw man.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import time
from datetime import datetime
from pathlib import Path

import httpx
import numpy as np
from rank_bm25 import BM25Okapi

from ..gen_pool import build_pool
from ..harness import PacificServer, make_workdir
from ..providers import provider_context
from .metrics import bootstrap_diff, bootstrap_mean, mean, oracle, pack, score_selection, tokens

HERE = Path(__file__).resolve().parent
BUDGETS = [2000, 5000, 10000, 20000]
RANDOM_SEEDS = 20


def scenario_text(s: dict) -> str:
    parts = list(s.get("messages", [])[-1:])
    ctx = s.get("context") or {}
    parts += [ctx.get(k, "") for k in ("app_name", "window_title", "selected_text")]
    for ev in s.get("events", []):
        parts += [ev.get("file", ""), ev.get("content", "")]
    return " ".join(p for p in parts if p).strip()


# ── Pacific ──────────────────────────────────────────────────────────────────

def run_pacific(client: httpx.Client, s: dict) -> dict:
    started = time.perf_counter()
    client.post("/api/session/clear").raise_for_status()
    for ev in s.get("events", []):
        client.post("/api/session/event", json={"event": ev}).raise_for_status()
    if s.get("context"):
        client.post("/api/session/context", json={**s["context"], "rescore": False}).raise_for_status()
    resp = None
    for msg in s.get("messages", []):
        resp = client.post("/api/message", json={"message": msg})
        resp.raise_for_status()
    if resp is None:
        resp = client.post("/api/rescore")
        resp.raise_for_status()
    body = resp.json()
    ranked = sorted((p for p in body["pool"] if p["status"] != "active"), key=lambda p: -p["score"])
    return {
        "ranking": [p["id"] for p in ranked],
        "shipped": [p["id"] for p in body.get("suggestions", [])],
        "gate_reason": (body.get("suggest_diag") or {}).get("reason", ""),
        "latency_ms": (time.perf_counter() - started) * 1000,
    }


# ── Baselines ────────────────────────────────────────────────────────────────

class Baselines:
    def __init__(self, pool: list[dict], env: dict[str, str], strict: bool):
        self.strict = strict
        self.pool = pool
        self.ids = [p["id"] for p in pool]
        self.bm25 = BM25Okapi([p["content"].lower().split() for p in pool])
        self.env = env
        self.doc_unit: np.ndarray | None = None

    async def _embed(self, texts: list[str]) -> np.ndarray:
        os.environ.update(self.env)
        from backend import embed  # provider settings are read at import time
        if self.strict:
            # Call the provider directly: async_embed_many silently substitutes
            # placeholder vectors on failure, which would invalidate the baselines.
            vecs = []
            try:
                for i in range(0, len(texts), embed.EMBED_BATCH_SIZE):
                    vecs += await embed._aembed_gemini_batch(texts[i:i + embed.EMBED_BATCH_SIZE])
            finally:
                # The pooled client is bound to this event loop; the next
                # asyncio.run() needs a fresh one.
                await embed.aclose_clients()
        else:
            vecs = [embed._embed_mock(t) for t in texts]
        mat = np.asarray(vecs, dtype=np.float32)
        return mat / np.maximum(np.linalg.norm(mat, axis=1, keepdims=True), 1e-9)

    def prepare(self, queries: list[str]) -> dict[str, np.ndarray]:
        texts = [f"{p['display_name']}: {p['description']}\n{p['content']}" for p in self.pool]
        mats = asyncio.run(self._embed(texts + queries))
        self.doc_unit = mats[: len(texts)]
        return dict(zip(queries, mats[len(texts):]))

    def _order(self, scores: np.ndarray) -> list[str]:
        return [self.ids[i] for i in np.argsort(-scores, kind="stable")]

    def bm25_scores(self, q: str) -> np.ndarray:
        raw = np.asarray(self.bm25.get_scores(q.lower().split()), dtype=np.float32)
        return raw / raw.max() if raw.size and raw.max() > 0 else raw

    def rankings(self, q: str, q_vec: np.ndarray) -> dict[str, list[str]]:
        cos = self.doc_unit @ q_vec
        bm = self.bm25_scores(q)
        return {
            "recency": [p["id"] for p in sorted(self.pool, key=lambda p: p["last_used"], reverse=True)],
            "pool_order": list(self.ids),
            "bm25": self._order(bm),
            "embedding": self._order(cos),
            "hybrid": self._order(0.6 * bm + 0.4 * cos),
        }


# ── Run ──────────────────────────────────────────────────────────────────────

METHODS = ["pacific", "hybrid", "embedding", "bm25", "recency", "pool_order", "random"]


def evaluate(provider: str, pool_size: int, out_dir: Path) -> dict:
    scenarios = json.loads((HERE / "scenarios.json").read_text(encoding="utf-8"))["scenarios"]
    pool = build_pool(pool_size)
    cost = {p["id"]: tokens(p) for p in pool}

    with provider_context(provider) as env:
        work = make_workdir(pool)
        with PacificServer(work, env, log=out_dir / f"server-quality-{pool_size}.log") as server:
            client = httpx.Client(base_url=server.url, timeout=120)
            pacific = {s["id"]: run_pacific(client, s) for s in scenarios}
            client.post("/api/session/clear")
        # Under "outage" Pacific falls back to placeholder vectors, so the
        # baselines do too; under "endpoint" any embedding failure is fatal.
        base = Baselines(pool, env, strict=provider == "endpoint")
        queries = [scenario_text(s) for s in scenarios]
        q_vecs = base.prepare(queries)

    rng = random.Random(0)
    per_scenario = []
    for s, q in zip(scenarios, queries):
        labels = s["labels"]
        p = pacific[s["id"]]
        row = {"id": s["id"], "type": s["type"], "pacific_shipped": p["shipped"],
               "pacific_gate": p["gate_reason"], "pacific_latency_ms": round(p["latency_ms"], 1),
               "budgets": {}}
        if labels:
            rankings = {"pacific": p["ranking"], **base.rankings(q, q_vecs[q])}
            randoms = []
            for _ in range(RANDOM_SEEDS):
                ids = list(base.ids)
                rng.shuffle(ids)
                randoms.append(ids)
            for budget in BUDGETS:
                cell = {m: score_selection(pack(r, cost, budget), labels, cost, budget) for m, r in rankings.items()}
                rand = [score_selection(pack(r, cost, budget), labels, cost, budget) for r in randoms]
                cell["random"] = {k: mean([x[k] for x in rand]) for k in rand[0]}
                cell["oracle_items"] = oracle(labels, cost, budget)
                row["budgets"][str(budget)] = cell
            shipped = score_selection(p["shipped"], labels, cost, 10**9)
            row["shipped"] = {k: shipped[k] for k in ("recall", "token_precision", "essential_hit", "tokens_used", "items")}
        per_scenario.append(row)

    return {"meta": {"provider": provider, "pool_size": len(pool), "scenarios": len(scenarios),
                     "budgets": BUDGETS, "created": datetime.now().isoformat(timespec="seconds")},
            "summary": summarize(per_scenario), "scenarios": per_scenario}


def summarize(rows: list[dict]) -> dict:
    labelled = [r for r in rows if r["budgets"]]
    empty = [r for r in rows if not r["budgets"]]
    out: dict = {"budgets": {}, "by_type": {}}
    for budget in BUDGETS:
        b = str(budget)
        col = {}
        for m in METHODS:
            col[m] = {k: bootstrap_mean([r["budgets"][b][m][k] for r in labelled])
                      for k in ("recall", "pct_oracle", "token_precision", "essential_hit", "ndcg")}
            col[m]["tokens_used"] = mean([r["budgets"][b][m]["tokens_used"] for r in labelled])
        col["pacific_vs"] = {
            m: {k: bootstrap_diff([r["budgets"][b]["pacific"][k] for r in labelled],
                                  [r["budgets"][b][m][k] for r in labelled])
                for k in ("recall", "pct_oracle", "token_precision")}
            for m in METHODS if m != "pacific"
        }
        out["budgets"][b] = col
    for t in sorted({r["type"] for r in labelled}):
        rs = [r for r in labelled if r["type"] == t]
        out["by_type"][t] = {m: mean([r["budgets"]["5000"][m]["pct_oracle"] for r in rs]) for m in METHODS}
        out["by_type"][t]["n"] = len(rs)
    out["shipped"] = {k: mean([r["shipped"][k] for r in labelled])
                      for k in ("recall", "token_precision", "essential_hit", "tokens_used", "items")}
    out["gate"] = {
        "false_suggest_rate": mean([1.0 if r["pacific_shipped"] else 0.0 for r in empty]),
        "false_silence_rate": mean([0.0 if r["pacific_shipped"] else 1.0 for r in labelled]),
        "n_should_be_silent": len(empty),
        "n_should_suggest": len(labelled),
    }
    out["latency_ms"] = bootstrap_mean([r["pacific_latency_ms"] for r in rows])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="endpoint")
    ap.add_argument("--pool-size", type=int, nargs="+", default=[44])
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    out = args.out or HERE.parent / "results" / f"{datetime.now():%Y%m%d-%H%M}-{args.provider}"
    out.mkdir(parents=True, exist_ok=True)
    results = {str(n): evaluate(args.provider, n, out) for n in args.pool_size}
    (out / "quality.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(f"wrote {out / 'quality.json'}")


if __name__ == "__main__":
    main()
