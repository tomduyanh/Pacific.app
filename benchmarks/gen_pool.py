"""Synthetic context pools for scale testing.

Keeps the real 44 items and pads with templated engineering documents that
share the domain's vocabulary (services, endpoints, people, tickets) without
duplicating any real item's facts. Distractors are therefore near-domain:
they compete for BM25 and cosine mass, which is what makes ranking harder as
the pool grows. Sizes are resampled from the real pool's token sizes.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

_SERVICES = ["billing", "search", "notifications", "ingest", "reporting", "export", "gateway",
             "scheduler", "media", "audit", "webhooks", "inventory", "pricing", "sync", "ledger"]
_TOPICS = ["runbook", "design doc", "postmortem", "meeting notes", "RFC", "onboarding notes",
           "capacity plan", "API reference", "test plan", "retro", "status report", "spec"]
_NAMES = ["Hiro Tanaka", "Nadia Petrov", "Omar Haddad", "Ines Duarte", "Kwame Asante", "Lena Vogel",
          "Ravi Iyer", "Sofia Marin", "Tomas Novak", "Yara Haddad", "Zoe Clarke", "Arjun Mehta"]
_FACETS = [
    "latency regressed after the {svc} cache was resized; p95 moved from {a}ms to {b}ms",
    "the {svc} queue backs up during the nightly batch window around {h}:00",
    "migration of the {svc} tables uses an expand and contract plan over {n} releases",
    "owner of the {svc} service is {person}, reachable in #{svc}-dev",
    "error budget for {svc} is {pct}% per month; current burn is {burn}%",
    "{svc} deploys go through the canary stage for {n} hours before full rollout",
    "load test of {svc} held {rps} RPS before CPU saturation on {n} pods",
    "customer tickets about {svc} mention timeouts and duplicate events",
    "the {svc} schema adds a nullable column then backfills in batches of {batch} rows",
    "{person} proposed replacing the {svc} cron jobs with an event driven worker",
    "security review of {svc} found missing rate limits on two internal endpoints",
    "dashboard for {svc} tracks queue depth, error rate and saturation",
]
_KINDS = [("file", "semantic"), ("data", "semantic"), ("meta", "procedural"), ("people", "episodic")]


def _doc(rng: random.Random, i: int, size_tokens: int) -> dict:
    svc = rng.choice(_SERVICES)
    topic = rng.choice(_TOPICS)
    person = rng.choice(_NAMES)
    kind, channel = rng.choice(_KINDS)
    facts = [
        f.format(svc=svc, person=person, a=rng.randrange(40, 300), b=rng.randrange(300, 900),
                 h=rng.randrange(24), n=rng.randrange(2, 6), pct=rng.choice([0.1, 0.5, 1]),
                 burn=rng.randrange(5, 95), rps=rng.randrange(200, 3000), batch=rng.choice([500, 1000, 5000]))
        for f in rng.sample(_FACETS, k=rng.randrange(3, 7))
    ]
    name = f"{svc}_{topic.replace(' ', '_')}_{i}.md"
    return {
        "id": name,
        "display_name": name,
        "kind": kind,
        "source": f"synthetic/{name}",
        "description": f"{svc.title()} {topic} — {facts[0][:60]}",
        "size_bytes": size_tokens * 4,
        "last_used": f"2026-0{rng.randrange(1, 5)}-{rng.randrange(10, 28)}T10:00:00",
        "status": "idle",
        "channel": channel,
        "content": f"{svc.title()} {topic}. " + ". ".join(facts) + ".",
    }


def build_pool(n_total: int, seed: int = 7) -> list[dict]:
    real = json.loads((REPO / "data" / "pool.json").read_text(encoding="utf-8"))
    if n_total <= len(real):
        return real
    rng = random.Random(seed)
    sizes = [max(1, d["size_bytes"] // 4) for d in real]
    return real + [_doc(rng, i, rng.choice(sizes)) for i in range(n_total - len(real))]
