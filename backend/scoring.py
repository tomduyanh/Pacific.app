import math
import statistics
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent / "FileGram"))

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


def score_all(
    query: str,
    q_emb: list[float],
    candidates: list[ContextItem],
    attached_sources: set[str],
    attached_embeddings: list[list[float]],
    u_vec: list[float],
    w_vec: list[float],
    h_vec: Optional[list[float]],
    task_vec: Optional[list[float]],
    weights: dict,
    bm25: BM25Okapi,
) -> list[tuple[ContextItem, float, list[float]]]:
    if not candidates:
        return []

    raw_bm25 = bm25.get_scores(query.lower().split())
    max_bm25 = max(raw_bm25) if len(raw_bm25) > 0 else 1.0
    bm25_map = {
        candidates[i].id: float(raw_bm25[i]) / (max_bm25 if max_bm25 > 0 else 1.0)
        for i in range(len(candidates))
    }

    results = []
    for d in candidates:
        s_base = 0.6 * bm25_map.get(d.id, 0.0) + 0.4 * cosine(q_emb, d.embedding)
        s_u = cosine(u_vec, d.embedding)
        s_w = cosine(w_vec, d.embedding)
        s_h = cosine(h_vec, d.embedding) if h_vec else 0.0
        s_task = cosine(task_vec, d.embedding) if task_vec else 0.0
        # O(1) source check first; cosine only when source is absent or unmatched.
        if d.source and d.source in attached_sources:
            red = 1.0
        elif attached_embeddings:
            red = max(cosine(d.embedding, ae) for ae in attached_embeddings)
        else:
            red = 0.0
        features = [s_base, s_u, s_w, s_h, s_task, -red]
        score = (
            weights["alpha"] * s_base
            + weights["beta"] * s_u
            + weights["gamma"] * s_w
            + weights["eta"] * s_h
            + weights["zeta"] * s_task
            - weights["lam"] * red
        )
        # Boost people items that are *about* a person named in the query —
        # checks only display_name+description so documents that merely mention
        # a name in their body (onboarding guides, rosters) don't get the boost.
        if d.kind == "people":
            q_names = {w.lower() for w in query.split() if len(w) > 2 and w[0].isupper()}
            item_meta = (d.display_name + " " + d.description).lower()
            if q_names and any(n in item_meta for n in q_names):
                score += PEOPLE_NAME_BONUS
        results.append((d, score, features))

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
) -> list[tuple[ContextItem, float, list[float]]]:
    """Score docs against every expanded query, then average-pool per document.

    Average pooling beats max-pooling here: a doc that keyword-matches one query
    but is irrelevant to the others (e.g. stakeholders.md matching 'email' literally)
    will have its inflated score diluted, while a doc that scores well across most
    expanded queries (e.g. tone_policy.txt on 'professional writing tone' variants)
    accumulates a higher average.
    """
    queries = await expand_query(query, context)

    # Build attached index once — O(1) source lookup replaces per-candidate cosine for exact-source matches.
    attached_sources = {a.source for a in attached if a.source}
    attached_embeddings = [a.embedding for a in attached]

    # Filter candidates and build BM25 once — corpus is identical across all expanded queries.
    candidates = [d for d in pool if d.status != "active" and d.id not in dismissed_ids]
    if not candidates:
        return []
    bm25 = BM25Okapi([d.content.lower().split() for d in candidates])

    # Store (item, features) from the first run; accumulate scores from all runs.
    anchors: dict[str, tuple[ContextItem, list[float]]] = {}
    score_sums: dict[str, float] = {}
    score_counts: dict[str, int] = {}

    for q in queries:
        q_emb = query_emb if (q == query and query_emb) else await async_embed(q)
        for item, score, features in score_all(q, q_emb, candidates, attached_sources, attached_embeddings, u_vec, w_vec, h_vec, task_vec, weights, bm25):
            if item.id not in anchors:
                anchors[item.id] = (item, features)
                score_sums[item.id] = 0.0
                score_counts[item.id] = 0
            score_sums[item.id] += score
            score_counts[item.id] += 1

    merged = [
        (item, score_sums[id_] / score_counts[id_], features)
        for id_, (item, features) in anchors.items()
    ]
    merged.sort(key=lambda x: -x[1])
    return merged
