"""Budget-constrained retrieval metrics.

Every method produces a ranking; the same packer turns each ranking into the
set of items that fit a token budget, so methods are compared on what they
would actually put into a context window, not on ranking alone.

Gain per item: 3 for grade 2 (essential), 1 for grade 1 (useful), 0 otherwise.
Cost per item: size_bytes // 4 tokens, the same estimate Pacific's budget uses.
"""
from __future__ import annotations

import math
import random
from typing import Callable

GAIN = {2: 3.0, 1: 1.0}


def tokens(item: dict) -> int:
    return max(1, item["size_bytes"] // 4)


def pack(ranking: list[str], cost: dict[str, int], budget: int) -> list[str]:
    """First-fit down the ranking: take each item that still fits, skip the rest."""
    out, used = [], 0
    for item_id in ranking:
        c = cost[item_id]
        if used + c <= budget:
            out.append(item_id)
            used += c
    return out


def oracle(labels: dict[str, int], cost: dict[str, int], budget: int) -> list[str]:
    """Max-gain subset of the labelled items under the budget (0/1 knapsack), best first."""
    items = [(i, GAIN[g], cost[i]) for i, g in labels.items() if g in GAIN]
    best: dict[int, tuple[float, tuple[str, ...]]] = {0: (0.0, ())}
    for item_id, gain, c in items:
        for used, (g, chosen) in list(best.items()):
            nu = used + c
            if nu <= budget and (nu not in best or best[nu][0] < g + gain):
                best[nu] = (g + gain, chosen + (item_id,))
    _, chosen = max(best.values(), key=lambda t: t[0])
    return sorted(chosen, key=lambda i: (-GAIN[labels[i]], cost[i]))


def _dcg(ids: list[str], labels: dict[str, int]) -> float:
    return sum(GAIN.get(labels.get(i, 0), 0.0) / math.log2(pos + 2) for pos, i in enumerate(ids))


def score_selection(selected: list[str], labels: dict[str, int], cost: dict[str, int], budget: int) -> dict:
    gain = lambda ids: sum(GAIN.get(labels.get(i, 0), 0.0) for i in ids)  # noqa: E731
    total_gain = gain(labels)
    best = oracle(labels, cost, budget)
    best_gain = gain(best)
    used = sum(cost[i] for i in selected)
    relevant_used = sum(cost[i] for i in selected if labels.get(i, 0) > 0)
    essentials = [i for i, g in labels.items() if g == 2]
    ideal_dcg = _dcg(best, labels)
    return {
        "recall": gain(selected) / total_gain if total_gain else None,
        "pct_oracle": gain(selected) / best_gain if best_gain else None,
        "token_precision": relevant_used / used if used else 0.0,
        "essential_hit": (sum(i in selected for i in essentials) / len(essentials)) if essentials else None,
        "ndcg": _dcg(selected, labels) / ideal_dcg if ideal_dcg else None,
        "tokens_used": used,
        "items": len(selected),
    }


def mean(values: list[float | None]) -> float | None:
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


def bootstrap_diff(a: list[float], b: list[float], n: int = 2000, seed: int = 0) -> dict:
    """Paired bootstrap of mean(a - b) with a 95% interval."""
    pairs = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
    if not pairs:
        return {"mean": None, "lo": None, "hi": None, "n": 0}
    diffs = [x - y for x, y in pairs]
    rng = random.Random(seed)
    samples = sorted(
        sum(rng.choice(diffs) for _ in diffs) / len(diffs) for _ in range(n)
    )
    return {"mean": sum(diffs) / len(diffs), "lo": samples[int(0.025 * n)],
            "hi": samples[int(0.975 * n) - 1], "n": len(diffs)}


def bootstrap_mean(values: list[float | None], n: int = 2000, seed: int = 0) -> dict:
    vals = [v for v in values if v is not None]
    if not vals:
        return {"mean": None, "lo": None, "hi": None, "n": 0}
    rng = random.Random(seed)
    samples = sorted(sum(rng.choice(vals) for _ in vals) / len(vals) for _ in range(n))
    return {"mean": sum(vals) / len(vals), "lo": samples[int(0.025 * n)],
            "hi": samples[int(0.975 * n) - 1], "n": len(vals)}


Ranker = Callable[[dict], list[str]]
