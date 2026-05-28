"""Subsystem B — Context Store & Profiling.

Turns raw session activity into a rolling, queryable understanding of the user.
Unlike the pre-built long-term ``MemoryStore`` (loaded once at startup), this
profile is recomputed from the *live* session so it reflects what the user is
actually doing right now:

- a writing-style sample (tone / voice)
- active projects (path-prefix + kind clustering)
- frequent collaborators
- recurring document types

It also produces proactive *context-type* suggestions — e.g. "drafting an
email" pulls a tone profile and recipient history; "writing a report" pulls the
project glossary and prior docs. These describe the *kind* of context the user
will likely want next, independent of which specific items happen to be indexed.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass, field

from .embed import llm_call

# ── Prompts ──────────────────────────────────────────────────────────────────

WRITING_STYLE_PROMPT = (
    "Below are samples of text the user recently wrote or edited. In 2-3 "
    "sentences describe their writing style and tone — formality, voice, "
    "typical sentence length, vocabulary. Describe HOW they write, not the "
    "topic.\n\n{samples}"
)

# ── Task-type detection → proactive context types ────────────────────────────

# Ordered keyword sets; first match wins. Kept transparent and dependency-free
# so the behaviour is inspectable and testable without an LLM.
_TASK_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("email", ("email", "compose", "gmail", "outlook", "inbox", "reply", "recipient", "outreach")),
    ("report", ("report", "document", "doc", "essay", "memo", "proposal", "draft", "write-up", "whitepaper")),
    ("code", ("code", "function", "class", "debug", "refactor", "bug", "stack trace", "compile", "editor", "ide", ".py", ".ts", ".js", ".rs")),
    ("research", ("research", "reading", "article", "paper", "docs", "documentation", "thread", "pull request", "pr ", "issue")),
    ("messaging", ("slack", "teams", "chat", "message", "dm ", "discord")),
    ("data", ("spreadsheet", "csv", "table", "dataset", "query", "sql", "analytics", "dashboard")),
]

# For each detected task, the *types* of context worth surfacing, with a reason
# the UI can show and a ``kind_hint`` pointing at the pool kind most likely to
# satisfy it ("meta" | "file" | "data" | "people").
_TASK_CONTEXT_TYPES: dict[str, list[dict]] = {
    "email": [
        {"label": "Tone & writing-voice profile", "reason": "match how you usually write to this audience", "kind_hint": "meta"},
        {"label": "Recipient / collaborator history", "reason": "recall prior threads with the recipient", "kind_hint": "people"},
        {"label": "Prior emails on this topic", "reason": "reuse phrasing and commitments", "kind_hint": "file"},
    ],
    "report": [
        {"label": "Project glossary & terminology", "reason": "keep terms consistent with the project", "kind_hint": "meta"},
        {"label": "Prior documents in this project", "reason": "carry over structure and facts", "kind_hint": "file"},
        {"label": "Supporting data & figures", "reason": "ground claims in the underlying numbers", "kind_hint": "data"},
    ],
    "code": [
        {"label": "Related source files", "reason": "same module / nearby call sites", "kind_hint": "file"},
        {"label": "Coding conventions & standards", "reason": "match the project's style rules", "kind_hint": "meta"},
        {"label": "API / data schemas", "reason": "exact field names and types", "kind_hint": "data"},
    ],
    "research": [
        {"label": "Project background & goals", "reason": "frame what you're reading against the objective", "kind_hint": "meta"},
        {"label": "Prior notes on this topic", "reason": "avoid re-deriving what you already found", "kind_hint": "file"},
        {"label": "Domain experts to ask", "reason": "who on the team knows this area", "kind_hint": "people"},
    ],
    "messaging": [
        {"label": "Conversation / thread history", "reason": "recall the running context", "kind_hint": "people"},
        {"label": "Tone & writing-voice profile", "reason": "stay consistent with your voice", "kind_hint": "meta"},
    ],
    "data": [
        {"label": "Relevant datasets & records", "reason": "the numbers behind the question", "kind_hint": "data"},
        {"label": "Schema & metric definitions", "reason": "what each column actually means", "kind_hint": "meta"},
    ],
    "general": [
        {"label": "Active-project context", "reason": "what you're currently working on", "kind_hint": "file"},
        {"label": "User profile & preferences", "reason": "your standing conventions", "kind_hint": "meta"},
    ],
}

_NAME_RE = re.compile(r"\b([A-Z][a-z]{2,})\b")
_STOPWORDS = {
    "The", "This", "That", "User", "Active", "Recent", "Working", "Editing",
    "Composing", "Reading", "Subject", "File", "Gmail", "Outlook", "Slack",
    "Python", "React", "Code", "Email", "Document", "Currently", "Visible",
}


@dataclass
class UserProfile:
    """Rolling, session-derived profile (Subsystem B)."""

    writing_style: str = ""
    active_projects: list[str] = field(default_factory=list)
    frequent_collaborators: list[str] = field(default_factory=list)
    recurring_doc_types: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _file_paths_from_events(session_events: list[dict]) -> list[str]:
    paths: list[str] = []
    for ev in session_events:
        f = (ev.get("file") or "").strip()
        if f and f != "unknown" and not f.startswith("http"):
            paths.append(f)
    return paths


def cluster_projects(paths: list[str], top_n: int = 4) -> list[str]:
    """Group file paths into projects by their leading directory segment.

    Transparent heuristic: the first path component is treated as the project
    root (``backend/scoring.py`` → ``backend``). Files with no directory fall
    under a ``(root)`` bucket. Returns the most-touched project roots first.
    """
    counts: Counter[str] = Counter()
    for p in paths:
        norm = p.replace("\\", "/").lstrip("./")
        head = norm.split("/", 1)[0] if "/" in norm else "(root)"
        if head:
            counts[head] += 1
    return [name for name, _ in counts.most_common(top_n)]


def recurring_doc_types(paths: list[str], pool, top_n: int = 5) -> list[str]:
    """Most common file extensions across touched files and the indexed pool."""
    counts: Counter[str] = Counter()
    for p in [*paths, *[(getattr(d, "source", "") or "") for d in pool]]:
        m = re.search(r"\.([A-Za-z0-9]{1,8})$", p)
        if m:
            counts["." + m.group(1).lower()] += 1
    return [ext for ext, _ in counts.most_common(top_n)]


def frequent_collaborators(
    recent_messages: list[str],
    screen_analysis: str,
    pool,
    top_n: int = 5,
) -> list[str]:
    """People the user is working with.

    Combines explicit ``people`` items in the pool with capitalized name tokens
    mentioned in recent messages / screen analysis (a cheap NER proxy).
    """
    counts: Counter[str] = Counter()
    for d in pool:
        if getattr(d, "kind", "") == "people":
            counts[d.display_name] += 3  # explicit people items rank highest
    blob = " ".join([*recent_messages[-5:], screen_analysis or ""])
    for name in _NAME_RE.findall(blob):
        if name not in _STOPWORDS:
            counts[name] += 1
    return [name for name, _ in counts.most_common(top_n)]


def detect_task_type(text: str) -> str:
    """Classify the current task from free text (query + screen analysis)."""
    low = (text or "").lower()
    for task, keywords in _TASK_KEYWORDS:
        if any(kw in low for kw in keywords):
            return task
    return "general"


def suggest_context_types(query: str, screen_analysis: str, task_phase: str) -> dict:
    """Proactive *type-of-context* suggestions for the current task.

    Returns ``{"task_type": str, "types": [{label, reason, kind_hint}, ...]}``.
    """
    task_type = detect_task_type(f"{query} {screen_analysis}")
    types = _TASK_CONTEXT_TYPES.get(task_type, _TASK_CONTEXT_TYPES["general"])
    return {"task_type": task_type, "types": types}


def _harvest_writing_samples(session_events: list[dict], screen_analysis: str) -> list[str]:
    samples: list[str] = []
    seen: set[str] = set()
    for ev in reversed(session_events[-60:]):
        if ev.get("type") not in {"write", "edit"}:
            continue
        content = (ev.get("content") or "").strip()
        if len(content) < 24:
            continue
        key = content[:60]
        if key in seen:
            continue
        seen.add(key)
        samples.append(content[:600])
        if len(samples) >= 6:
            break
    # Screen analysis sometimes captures the user's own composed prose.
    if screen_analysis and "compos" in screen_analysis.lower():
        samples.append(screen_analysis[:400])
    return samples


async def build_user_profile(
    session_events: list[dict],
    recent_messages: list[str],
    screen_analysis: str,
    pool,
) -> UserProfile:
    """Assemble the rolling user profile from live session signals.

    Cheap to call: only the writing-style summary touches the LLM, and only when
    there are enough authored samples to be worth summarizing.
    """
    paths = _file_paths_from_events(session_events)

    writing_style = ""
    samples = _harvest_writing_samples(session_events, screen_analysis)
    if samples:
        joined = "\n---\n".join(samples)
        if len(joined.split()) >= 20:
            writing_style = (await llm_call(WRITING_STYLE_PROMPT.format(samples=joined[:1800]))).strip()
        else:
            writing_style = "Not enough authored text yet to characterize a style."

    return UserProfile(
        writing_style=writing_style,
        active_projects=cluster_projects(paths),
        frequent_collaborators=frequent_collaborators(recent_messages, screen_analysis, pool),
        recurring_doc_types=recurring_doc_types(paths, pool),
    )
