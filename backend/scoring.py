from __future__ import annotations

import asyncio
import math
import os
import re
import statistics
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent / "FileGram"))

import numpy as np
from rank_bm25 import BM25Okapi

from .embed import async_embed, embed, llm_call
from .models import ContextItem

# Additive bonus for people items whose display_name/description contains a name
# mentioned in the query. Bypasses cosine compression for explicit person lookups.
PEOPLE_NAME_BONUS = 0.06

SUBPROBLEM_PROMPT = "In one sentence, what is the user currently trying to accomplish?\nMessage: {message}"

TASK_PROFILE_PROMPT = (
    "In 2-3 sentences, describe what this user is currently working on. "
    "Focus on the specific topic/domain and task, not tools or file names.\n\n{evidence}"
)

QUERY_EXPANSION_PROMPT = (
    "A user said: \"{query}\"\n"
    "Context: {context}\n\n"
    "Write 3 short phrases (5-8 words each) describing the TYPE of document or resource that would "
    "be most useful to them right now — focus on what kind of reference they need, not the task itself. "
    "Output only the phrases, one per line, no numbering."
)


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return max(-1.0, min(1.0, dot / (na * nb)))


def compute_weights(
    delta: float,
    task_phase: str,
    budget_used: float,
    workspace_activity: float = 1.0,
    has_task_profile: bool = False,
) -> dict:
    k = 3.0
    beta = math.exp(-k * delta)
    gamma = (1.0 - math.exp(-k * delta)) * workspace_activity
    alpha = 0.4 + (0.1 if task_phase == "exploration" else 0.0)
    gamma += 0.1 if task_phase == "production" else 0.0
    lam = 0.25 + 0.25 * budget_used
    eta = 0.15
    # zeta: task-profile signal — boosts items relevant to the live task.
    # When zeta is active, halve beta so the historical profile doesn't drown
    # out specific people/topics the user is working with right now.
    if has_task_profile:
        beta *= 0.5
        zeta = 0.35
    else:
        zeta = 0.0
    raw = [alpha, beta, gamma, eta, lam, zeta]
    total = sum(raw)
    a, b, g, e, lv, z = [x / total for x in raw]
    return dict(alpha=a, beta=b, gamma=g, eta=e, lam=lv, zeta=z)


def u_to_text(store) -> str:
    return "\n".join([
        store.content_profile,
        *store.behavioral_patterns,
        "Dimension classifications: " + ", ".join(store.dimension_classifications),
        "Absent behaviors: " + "; ".join(store.absence_flags),
    ])


_U_CHUNK_MIN_SIM = 0.25

def get_u_vec(store, q_vec: list[float], u_static: list[float]) -> list[float]:
    chunks = [c for c in store.content_chunks if c.embedding]
    if not chunks:
        return u_static
    scored = sorted(((cosine(q_vec, c.embedding), c) for c in chunks), reverse=True)
    top = [c for sim, c in scored[:3] if sim >= _U_CHUNK_MIN_SIM]
    if not top:
        return u_static
    n = len(top[0].embedding)
    u_episodic = [sum(c.embedding[i] for c in top) / len(top) for i in range(n)]
    return [(a + b) / 2 for a, b in zip(u_static, u_episodic)]


def workspace_from_events(session_events: list[dict]) -> dict:
    """Extract workspace signal directly from raw session events.

    BehaviorCollector.stats may stay empty when VLM events don't match its
    expected format. session_events is always populated by _record_events, so
    this is the reliable source for files_read, tool_sequence, etc.
    """
    files_read: list[str] = []
    files_created: list[str] = []
    dirs_created: list[str] = []
    tool_sequence: list[str] = []
    current_file: str | None = None
    lines_added = 0
    lines_deleted = 0
    seen: set[str] = set()

    for ev in session_events[-120:]:
        t = ev.get("type", "")
        f = (ev.get("file") or "").strip()
        if t:
            tool_sequence.append(t)
        if t in {"read", "browse", "grep", "glob", "search"} and f and f not in seen:
            files_read.append(f)
            seen.add(f)
            current_file = f
        elif t in {"write", "edit"} and f:
            if f not in seen:
                files_created.append(f)
                seen.add(f)
            current_file = f
            lines_added += int(ev.get("lines_added") or 0)
            lines_deleted += int(ev.get("lines_removed") or 0)
        elif t == "mkdir":
            d = (ev.get("dir") or "").strip()
            if d:
                dirs_created.append(d)

    return {
        "current_file": current_file,
        "files_read": files_read,
        "files_created": files_created,
        "dirs_created": dirs_created,
        "tool_sequence": tool_sequence,
        "lines_added": lines_added,
        "lines_deleted": lines_deleted,
    }


def w_to_text(stats, ws: dict | None = None) -> str:
    current_file = (ws or {}).get("current_file") or stats.current_file or "unknown"
    lines_added = (ws or {}).get("lines_added") or stats.total_lines_added
    lines_deleted = (ws or {}).get("lines_deleted") or stats.total_lines_deleted
    return "\n".join([
        f"Currently working on: {current_file}",
        f"Edit intensity: {lines_added} added, {lines_deleted} deleted",
        f"Context switches: {stats.context_switch_count}",
    ])


def detect_task_phase(tool_sequence: list[str]) -> str:
    recent = tool_sequence[-10:]
    counts = {
        "exploration": sum(1 for t in recent if t in {"read", "browse", "search", "glob", "grep"}),
        "production": sum(1 for t in recent if t in {"write", "edit"}),
        "organization": sum(1 for t in recent if t in {"move", "rename", "delete", "mkdir"}),
    }
    return max(counts, key=counts.get) if any(counts.values()) else "exploration"


def build_query(
    current_ask: str,
    stats,
    h_t_recent: list[str],
    screen_commentary: str = "",
    ws: dict | None = None,
    screen_analysis: str = "",
) -> str:
    # commentary (1-sentence) seeds the query when there's no user message;
    # analysis (3-5 sentences) adds dense technical terms for BM25 + cosine.
    seed = current_ask or screen_commentary
    parts = [seed] if seed else []
    current_file = (ws or {}).get("current_file") or stats.current_file
    files_read = (ws or {}).get("files_read") or list(stats.files_read)
    if current_file:
        parts.append(f"Active file: {current_file}")
    recent_files = [f for f in files_read[:6] if f != current_file and f != "unknown" and not f.startswith("http")]
    if recent_files:
        parts.append(f"Recent files: {', '.join(recent_files[:3])}")
    if screen_analysis:
        parts.append(screen_analysis)
    elif screen_commentary and screen_commentary != seed:
        parts.append(screen_commentary)
    if h_t_recent:
        parts.append("Recent context: " + " | ".join(h_t_recent[-3:]))
    return " ".join(parts) if parts else "general software development"


async def build_h_vec(recent_messages: list[str], recent_files: list[str]) -> list[float]:
    if not recent_messages:
        return []
    subproblem = await llm_call(SUBPROBLEM_PROMPT.format(message=recent_messages[-1]))
    h_text = "\n".join([
        *recent_messages[-3:],
        f"Current focus: {subproblem}",
        f"Recently accessed: {', '.join(recent_files[:5])}",
    ])
    return await async_embed(h_text)


def build_norm_params(store) -> list[tuple[float, float]]:
    fps = [e.fingerprint for e in store.engrams]
    if not fps:
        return [(0.0, 1.0)] * 17
    return [
        (
            statistics.mean(v[i] for v in fps),
            statistics.stdev(v[i] for v in fps) if len(fps) > 1 else 1.0,
        )
        for i in range(17)
    ]


def normalize_fingerprint(w_fp: list[float], norm_params: list[tuple]) -> list[float]:
    return [(v - mu) / (std if std > 0 else 1.0) for v, (mu, std) in zip(w_fp, norm_params)]


def compute_drift(u_centroid: list[float], w_fingerprint: list[float]) -> float:
    dot = sum(a * b for a, b in zip(u_centroid, w_fingerprint))
    norm_u = math.sqrt(sum(a * a for a in u_centroid))
    norm_w = math.sqrt(sum(b * b for b in w_fingerprint))
    if norm_u == 0 or norm_w == 0:
        return 0.0
    return 1.0 - max(-1.0, min(1.0, dot / (norm_u * norm_w)))


async def build_task_profile(
    session_events: list[dict],
    recent_messages: list[str],
    screen_analysis: str,
    current_file: str,
) -> list[float]:
    """Build a user-profile vector from the current session, bypassing MemoryStore.

    Harvests semantic content the user is actually producing/viewing so that
    s_u scores relevance to the live task rather than long-term behavioural norms.
    Falls back to [] when no usable signal exists (caller should use u_static instead).
    """
    parts: list[str] = []

    if screen_analysis:
        parts.append(f"Visible now: {screen_analysis}")
    if current_file:
        parts.append(f"Active file: {current_file}")
    parts.extend(f"User said: {m}" for m in recent_messages[-5:])

    # Harvest written/edited content — best semantic signal for the current task
    seen: set[str] = set()
    for ev in reversed(session_events[-40:]):
        if ev.get("type") not in {"write", "edit"}:
            continue
        content = (ev.get("content") or "").strip()
        fpath = ev.get("file") or ""
        key = content[:80] or fpath
        if key in seen:
            continue
        seen.add(key)
        if content:
            parts.append(f"Edited in {fpath}: {content[:400]}")
        elif fpath:
            parts.append(f"Edited: {fpath}")
        if len(parts) >= 14:
            break

    if not parts:
        return []

    evidence = "\n".join(parts)
    if len(evidence.split()) >= 25:
        summary = await llm_call(TASK_PROFILE_PROMPT.format(evidence=evidence[:1800]))
        profile_text = f"{summary}\n\n{evidence[:600]}"
    else:
        profile_text = evidence

    return await async_embed(profile_text)


# ── Vectorized scoring ───────────────────────────────────────────────────────
# Every signal in the formula is a cosine between one query-side vector and all
# candidate embeddings. Done in interpreted Python at 3072 dimensions that is
# roughly 3M float ops per rescore; as unit-normalized matrix-vector products it
# is a handful of BLAS calls. The pool matrix is built once and reused, and
# candidate subsets are taken as row slices so attach/dismiss doesn't rebuild it.

_pool_matrix_cache: dict[tuple[str, ...], tuple[int, np.ndarray, dict[str, int]]] = {}


def _unit_rows(mat: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    np.maximum(norms, 1e-12, out=norms)
    return mat / norms


def _unit_vec(vec, dim: int):
    """Unit-normalize `vec`, or return None when it can't be compared to `dim`-wide rows.

    Mirrors the guards in cosine(): empty vectors and dimension mismatches score 0.
    """
    if dim <= 0 or vec is None or len(vec) != dim:
        return None
    arr = np.asarray(vec, dtype=np.float32)
    norm = float(np.linalg.norm(arr))
    if norm == 0.0:
        return None
    return arr / norm


def _pool_index(pool: list[ContextItem]) -> tuple[int, np.ndarray, dict[str, int]]:
    """Unit-normalized embedding matrix for the whole pool, cached by item identity."""
    key = tuple(d.id for d in pool)
    hit = _pool_matrix_cache.get(key)
    if hit is not None:
        return hit

    dims = [len(d.embedding) for d in pool if d.embedding]
    dim = max(set(dims), key=dims.count) if dims else 0
    mat = np.zeros((len(pool), dim), dtype=np.float32)
    row_of: dict[str, int] = {}
    for i, d in enumerate(pool):
        row_of[d.id] = i
        # Rows whose embedding is missing or a different width stay zero, which
        # yields a 0.0 cosine — the same result the scalar path gave.
        if dim and len(d.embedding) == dim:
            mat[i] = d.embedding

    entry = (dim, _unit_rows(mat), row_of)
    _pool_matrix_cache.clear()  # one live pool per process; bound the memory
    _pool_matrix_cache[key] = entry
    return entry


class _CandidateIndex:
    """Reusable per-rescore view over the candidate subset."""

    __slots__ = ("candidates", "dim", "unit", "bm25", "_zeros")

    def __init__(self, candidates: list[ContextItem], dim: int, unit: np.ndarray) -> None:
        self.candidates = candidates
        self.dim = dim
        self.unit = unit
        self.bm25 = BM25Okapi([d.content.lower().split() for d in candidates])
        self._zeros = np.zeros(len(candidates), dtype=np.float32)

    def cos(self, vec) -> np.ndarray:
        """Cosine of `vec` against every candidate, aligned to self.candidates."""
        u = _unit_vec(vec, self.dim)
        if u is None:
            return self._zeros
        return self.unit @ u

    def bm25_normalized(self, query: str) -> np.ndarray:
        raw = np.asarray(self.bm25.get_scores(query.lower().split()), dtype=np.float32)
        peak = float(raw.max()) if raw.size else 0.0
        return raw / peak if peak > 0 else raw


def _build_index(pool: list[ContextItem], candidates: list[ContextItem]) -> _CandidateIndex:
    dim, pool_unit, row_of = _pool_index(pool)
    rows = np.fromiter((row_of[d.id] for d in candidates), dtype=np.intp, count=len(candidates))
    return _CandidateIndex(candidates, dim, pool_unit[rows])


def _redundancy(
    index: _CandidateIndex,
    attached: list[ContextItem],
    attached_sources: set[str],
) -> np.ndarray:
    """Max cosine to any attached item, with an exact-source match pinned to 1.0."""
    red = np.zeros(len(index.candidates), dtype=np.float32)

    attached_vecs = [_unit_vec(a.embedding, index.dim) for a in attached]
    attached_vecs = [v for v in attached_vecs if v is not None]
    if attached_vecs:
        red = (index.unit @ np.stack(attached_vecs, axis=1)).max(axis=1)

    if attached_sources:
        for i, d in enumerate(index.candidates):
            if d.source and d.source in attached_sources:
                red[i] = 1.0
    return red


def _people_bonus(query: str, candidates: list[ContextItem]) -> np.ndarray:
    """Additive boost for people items *about* a person named in the query.

    Checks display_name + description only, so documents that merely mention a
    name in their body (onboarding guides, rosters) don't get the boost.
    """
    bonus = np.zeros(len(candidates), dtype=np.float32)
    q_names = {w.lower() for w in query.split() if len(w) > 2 and w[0].isupper()}
    if not q_names:
        return bonus
    for i, d in enumerate(candidates):
        if d.kind != "people":
            continue
        item_meta = (d.display_name + " " + d.description).lower()
        if any(n in item_meta for n in q_names):
            bonus[i] = PEOPLE_NAME_BONUS
    return bonus


def score_all(
    query: str,
    q_emb: list[float],
    candidates: list[ContextItem],
    attached_sources: set[str],
    attached: list[ContextItem],
    u_vec: list[float],
    w_vec: list[float],
    h_vec: Optional[list[float]],
    task_vec: Optional[list[float]],
    weights: dict,
    pool: Optional[list[ContextItem]] = None,
) -> list[tuple[ContextItem, float, list[float]]]:
    """Score one query against the candidate set. Kept for single-query callers."""
    if not candidates:
        return []
    index = _build_index(pool or candidates, candidates)
    static = _static_signals(index, attached, attached_sources, u_vec, w_vec, h_vec, task_vec)
    return _merge_scores(index, static, [query], [q_emb], weights)


def _static_signals(
    index: _CandidateIndex,
    attached: list[ContextItem],
    attached_sources: set[str],
    u_vec: list[float],
    w_vec: list[float],
    h_vec: Optional[list[float]],
    task_vec: Optional[list[float]],
) -> dict[str, np.ndarray]:
    """Signals that don't depend on the query — computed once, not once per expansion."""
    return {
        "s_u": index.cos(u_vec),
        "s_w": index.cos(w_vec),
        "s_h": index.cos(h_vec) if h_vec else index.cos(None),
        "s_task": index.cos(task_vec) if task_vec else index.cos(None),
        "red": _redundancy(index, attached, attached_sources),
    }


def _merge_scores(
    index: _CandidateIndex,
    static: dict[str, np.ndarray],
    queries: list[str],
    query_embs: list[list[float]],
    weights: dict,
) -> list[tuple[ContextItem, float, list[float]]]:
    """Average-pool the per-query score across every expanded query.

    Only s_base varies with the query, so the query-independent terms are added
    once and only the base term is averaged — arithmetically identical to
    scoring each query in full and averaging, at a fraction of the work.
    """
    s_u, s_w = static["s_u"], static["s_w"]
    s_h, s_task, red = static["s_h"], static["s_task"], static["red"]

    base_sum = np.zeros(len(index.candidates), dtype=np.float32)
    bonus_sum = np.zeros(len(index.candidates), dtype=np.float32)
    first_base: Optional[np.ndarray] = None

    for query, q_emb in zip(queries, query_embs):
        s_base = 0.6 * index.bm25_normalized(query) + 0.4 * index.cos(q_emb)
        if first_base is None:
            first_base = s_base
        base_sum += s_base
        bonus_sum += _people_bonus(query, index.candidates)

    n = max(1, len(queries))
    s_base_mean = base_sum / n

    scores = (
        weights["alpha"] * s_base_mean
        + weights["beta"] * s_u
        + weights["gamma"] * s_w
        + weights["eta"] * s_h
        + weights["zeta"] * s_task
        - weights["lam"] * red
        + bonus_sum / n
    )

    # Feature vectors mirror the original: taken from the first query's pass.
    anchor_base = first_base if first_base is not None else s_base_mean
    results = [
        (
            d,
            float(scores[i]),
            [
                float(anchor_base[i]),
                float(s_u[i]),
                float(s_w[i]),
                float(s_h[i]),
                float(s_task[i]),
                -float(red[i]),
            ],
        )
        for i, d in enumerate(index.candidates)
    ]
    results.sort(key=lambda x: -x[1])
    return results


async def expand_query(query: str, context: str) -> list[str]:
    """Return [query] unchanged when it's already descriptive; otherwise prepend LLM-generated variants."""
    if len(query.split()) >= 8:
        return [query]
    raw = await llm_call(QUERY_EXPANSION_PROMPT.format(query=query, context=context[:400]))
    extras = [q.strip() for q in raw.strip().splitlines() if q.strip()][:3]
    return [query, *extras]


async def score_all_expanded(
    query: str,
    context: str,
    pool: list[ContextItem],
    attached: list[ContextItem],
    dismissed_ids: set[str],
    u_vec: list[float],
    w_vec: list[float],
    h_vec: Optional[list[float]],
    task_vec: Optional[list[float]],
    weights: dict,
    query_emb: Optional[list[float]] = None,
    queries: Optional[list[str]] = None,
) -> list[tuple[ContextItem, float, list[float]]]:
    """Score docs against every expanded query, then average-pool per document.

    Average pooling beats max-pooling here: a doc that keyword-matches one query
    but is irrelevant to the others (e.g. stakeholders.md matching 'email' literally)
    will have its inflated score diluted, while a doc that scores well across most
    expanded queries (e.g. tone_policy.txt on 'professional writing tone' variants)
    accumulates a higher average.

    `queries` lets the caller supply an already-expanded list so the expansion LLM
    call can run concurrently with the rest of the rescore instead of blocking it.
    """
    if queries is None:
        queries = await expand_query(query, context)

    candidates = [d for d in pool if d.status != "active" and d.id not in dismissed_ids]
    if not candidates:
        return []

    # Embed every expansion at once rather than one round trip after another.
    extra = [q for q in queries if not (q == query and query_emb)]
    extra_embs = dict(zip(extra, await asyncio.gather(*(async_embed(q) for q in extra)))) if extra else {}
    query_embs = [query_emb if (q == query and query_emb) else extra_embs.get(q, []) for q in queries]

    index = _build_index(pool, candidates)
    attached_sources = {a.source for a in attached if a.source}
    static = _static_signals(index, attached, attached_sources, u_vec, w_vec, h_vec, task_vec)
    return _merge_scores(index, static, queries, query_embs, weights)


# ── Suggestion gating ────────────────────────────────────────────────────────
# Suggesting three items unconditionally means the assistant is always confident,
# even when it has nothing. It can now return none — but deciding *when* took
# three attempts, and the first two were wrong in an instructive way.
#
# An absolute score floor fails: an off-topic query ("sourdough hydration")
# scored 0.608 at top-1, inside the 0.616-0.692 band of genuine requests,
# because s_u and s_w dominate whatever the topic is. Measuring how far the top
# item leads the pool median fails too — it separated on a clean session, then
# collapsed once the overlay's live screen analysis joined the query and lifted
# every score (a real request measured 0.124 against a 0.16 cut-off). A robust
# z-score over the median absolute deviation was no better: noise reached 4.92
# while a genuine request sat at 4.32, because MAD gets unstable when the pack
# is tightly clustered.
#
# The lesson is that these scores carry no reliable "is this relevant" signal —
# which is exactly what the sourdough result said. What actually separated the
# cases all along was the *input*: "hmm" carries no information, a real request
# does. So the gate is on evidence, not on the shape of the ranking:
#
#   suggest when the user said something informative, OR the workspace/screen
#   shows real activity; otherwise say nothing.
#
# A deliberately loose z-score backstop remains, to catch a genuinely degenerate
# ranking. It is a safety net, not the decision.

# Fillers that carry no retrieval signal on their own.
_FILLER_WORDS = frozenset({
    "hmm", "hmmm", "hm", "okay", "yeah", "yep", "nope", "idk", "dunno", "sure",
    "hey", "hello", "thanks", "thx", "huh", "wait", "lol", "the", "and", "but",
    "for", "you", "are", "was", "its", "this", "that", "what", "how", "why",
})

SUGGEST_MIN_WORDS = int(os.getenv("PACIFIC_SUGGEST_MIN_WORDS", "2"))
SUGGEST_MIN_Z = float(os.getenv("PACIFIC_SUGGEST_MIN_Z", "2.0"))
SUGGEST_ITEM_Z = float(os.getenv("PACIFIC_SUGGEST_ITEM_Z", "1.0"))
SUGGEST_MAX = int(os.getenv("PACIFIC_SUGGEST_MAX", "3"))


def informative_words(text: str) -> list[str]:
    """Words that could plausibly drive retrieval — fillers and stopwords removed."""
    words = re.findall(r"[a-z0-9'_.\-]+", (text or "").lower())
    return [w for w in words if len(w) > 2 and w not in _FILLER_WORDS]


def has_retrieval_signal(current_ask: str, screen_analysis: str, workspace: dict) -> bool:
    """Is there enough evidence to justify recommending anything at all?

    True when the user said something with content, or when the workspace/screen
    shows what they are actually doing — the ambient case, where saying nothing
    would defeat the point of watching.
    """
    if len(informative_words(current_ask)) >= SUGGEST_MIN_WORDS:
        return True
    if len(informative_words(screen_analysis)) >= 6:
        return True
    ws = workspace or {}
    if ws.get("current_file") or ws.get("files_read") or ws.get("files_created"):
        return True
    return False


def select_suggestions(
    scored: list[tuple[ContextItem, float, list[float]]],
    max_items: int = SUGGEST_MAX,
) -> tuple[list[tuple[ContextItem, float]], dict]:
    """Pick the items worth surfacing, which may legitimately be none.

    Returns (suggestions, diagnostics) so the UI can explain an empty result
    instead of just showing a blank shelf.
    """
    if not scored:
        return [], {"reason": "empty_pool", "z": 0.0, "considered": 0}

    scores = [s for _, s, _ in scored]
    median = statistics.median(scores)
    top = scores[0]

    # Median absolute deviation: a robust measure of how spread out the pack is,
    # unaffected by the handful of high scores we are trying to judge.
    mad = statistics.median([abs(s - median) for s in scores]) or 1e-6
    z = (top - median) / mad

    diag = {
        "median": round(median, 4),
        "top": round(top, 4),
        "mad": round(mad, 4),
        "z": round(z, 2),
        "min_z": SUGGEST_MIN_Z,
        "considered": len(scored),
        "reason": "",
    }

    if z < SUGGEST_MIN_Z:
        # Flat ranking: nothing stands out, so claiming a recommendation would
        # be noise dressed up as a suggestion.
        diag["reason"] = "no_clear_signal"
        return [], diag

    cut = median + SUGGEST_ITEM_Z * mad
    picked = [(item, score) for item, score, _ in scored[:max_items] if score >= cut]
    if not picked:
        diag["reason"] = "no_clear_signal"
        return [], diag

    diag["reason"] = "ok"
    return picked, diag
