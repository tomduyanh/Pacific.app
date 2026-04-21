"""
Per-kind preference bias learner.

Learns an additive score offset per document kind (file/meta/data/people)
from attach (+1) and dismiss/detach (-1) signals.

Biases are stable cross-session because they depend only on item kind,
not on session-specific similarity scores that change with workspace context.
Additive offsets are orthogonal to compute_weights() dynamic reweighting,
so they don't dampen context-sensitive alpha/beta/gamma adjustments.
"""
import json
import math
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).parent.parent / "data"
WEIGHTS_FILE = DATA_DIR / "learned_weights.json"

LEARNING_RATE = 0.1
L2 = 0.2
MAX_BIAS = 0.12   # bias beyond this overwhelms genuine relevance differences
KINDS = ["file", "meta", "data", "people"]


def load() -> Optional[dict]:
    if WEIGHTS_FILE.exists():
        try:
            data = json.loads(WEIGHTS_FILE.read_text(encoding="utf-8"))
            # Accept old per-feature format by returning None (triggers fresh start)
            if all(k in data for k in KINDS):
                # Clamp any persisted values that exceed the current cap.
                return {k: max(-MAX_BIAS, min(MAX_BIAS, v)) for k, v in data.items()}
        except Exception:
            pass
    return None


def save(biases: dict) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    WEIGHTS_FILE.write_text(json.dumps(biases, indent=2), encoding="utf-8")


def default_biases() -> dict:
    return {k: 0.0 for k in KINDS}


def update(kind: str, label: int, biases: dict, score: float = 0.5) -> dict:
    """
    One gradient step on the bias for `kind`, weighted by how surprising the action is.

    Attach (+1): weight = 1 - score  (picking a low-ranked doc is a strong positive signal)
    Dismiss (-1): weight = score     (dismissing a high-ranked doc is a strong negative signal)

    This prevents testing-time detachments of low-ranked docs from polluting the bias.
    """
    new = dict(biases)
    if kind not in new:
        return new
    b = new[kind]
    sig = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, b))))
    grad = (1.0 - sig) if label == 1 else -sig
    weight = (1.0 - score) if label == 1 else score
    new[kind] = max(-MAX_BIAS, min(MAX_BIAS, b + LEARNING_RATE * weight * (grad - L2 * b)))
    return new


def apply_biases(
    biases: dict,
    scored: list,
) -> list:
    """Add per-kind bias to scores and re-sort."""
    adjusted = [
        (item, score + biases.get(item.kind, 0.0), feats)
        for item, score, feats in scored
    ]
    adjusted.sort(key=lambda x: -x[1])
    return adjusted
