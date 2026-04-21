"""Map a screen frame (via VLM) onto FileGram session events for fingerprint / workspace stats."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from .embed import llm_vision_call

LIVE_NOVELTY_MIN = float(os.getenv("LIVE_SCREEN_NOVELTY_MIN", "0.36"))
LIVE_NOVELTY_BORDER = float(os.getenv("LIVE_SCREEN_NOVELTY_BORDER", "0.32"))
LIVE_MIN_INTERVAL_SEC = float(os.getenv("LIVE_SCREEN_MIN_INTERVAL_SEC", "4.0"))

ALLOWED_TYPES = frozenset(
    {"read", "browse", "search", "grep", "glob", "write", "edit", "mkdir", "move", "rename", "delete"}
)

SCREEN_ACTION_PROMPT = """You are labeling a single screenshot of the user's desktop or browser for a coding-assistant telemetry system.

Infer the PRIMARY user actions visible right now. Output ONLY valid JSON: an array of objects. No markdown fences, no commentary.

Each object MUST use this schema (choose the closest real action; omit speculative steps):
- "type": one of: read, browse, search, grep, glob, write, edit, mkdir, move, rename, delete
- "file": string path or URL (required for read, browse, search, grep, glob, write, edit, move, rename when applicable)
- "dir": string (for mkdir only)
- "content": string (optional; short excerpt if the user visibly composed text in an editor or form — truncate to ~200 chars)
- "lines_added", "lines_removed": non-negative integers (for edit/write when you can infer approximate change; else omit or use 0)

Guidelines:
- Browser on Gmail/Slack/docs → type "browse", file = page URL if visible in address bar else a short descriptive pseudo-URL like "https://mail/inbox"
- IDE or editor with code → "read" if only viewing, "edit" if diff line numbers / unsaved indicator / obvious typing; read visible text—small edits still count as edit when content changed
- Terminal running ripgrep/find → "grep" or "glob" or "search" as appropriate
- File tree / explorer only → "read" with the focused file path if visible
- At most 6 objects; prefer 1–3 high-confidence actions.

Example (format only):
[{"type":"browse","file":"https://github.com/org/repo/pull/42"},{"type":"read","file":"src/api.ts"}]
"""

LIVE_SCREEN_PROMPT = """You are monitoring consecutive screenshots of the user's desktop or browser for a live assistant.

PREVIOUS SITUATION (may be empty on first frame):
{previous_commentary}

PREVIOUS HIGH-LEVEL ACTIONS (signature, may be empty):
{previous_events_sig}

Look at the NEW screenshot only. Decide if there is a MEANINGFUL change worth reporting.

TEXT AND CODE (critical): Editors, IDEs, terminals, docs, email, and chat UIs often change by only a few characters. You MUST treat as HIGH novelty when actual words, code, stack traces, line numbers, diff hunks, commit messages, or terminal output differ from the PREVIOUS SITUATION — even if layout looks unchanged. Do NOT treat substantive edits as "no change" because global pixels moved little.

SCROLLING / SAME FILE (critical): If the user scrolled so the visible body text is mostly different from before (new section, new function, new paragraphs), that IS a meaningful change. Set significant_change true, novelty 0.45–0.75. Only ignore scroll when the same lines remain visibly dominant.

Ignore only: pure cursor blink with no text change, identical clock tickers, micro-scroll where the same text stays dominant.

Output ONLY valid JSON (one object, no markdown fences). Two examples showing correct screen_analysis style:

Example A — code editor:
{{
  "significant_change": true,
  "novelty": 0.7,
  "visual_change": 0.6,
  "commentary": "Editing the JWT validation function in auth.py.",
  "screen_analysis": "User is editing Python code in VS Code. Active file: backend/auth.py. Working on a validate_jwt() function — specifically the exception handling block where ExpiredSignatureError raises a 401 PermissionDenied. Imports visible: PyJWT, datetime, settings.SECRET_KEY.",
  "filegram_events": [{{"type": "edit", "file": "backend/auth.py"}}]
}}

Example B — email compose:
{{
  "significant_change": true,
  "novelty": 0.8,
  "visual_change": 0.7,
  "commentary": "Composing a business email about frontend architecture in Gmail.",
  "screen_analysis": "User is composing an email in Gmail. Email type: professional outreach / business discussion. Subject: 'Very important subject to discuss'. The user's own opening lines propose a conversation about UX design and frontend architecture, specifically React. Recipient appears to be a colleague or client.",
  "filegram_events": [{{"type": "browse", "file": "https://mail.google.com/compose"}}]
}}

Fields:
- "significant_change": true if the user's situation, visible task, or visible content clearly changed vs the previous situation.
- "novelty": 0.0–1.0 how much new information this frame adds vs PREVIOUS SITUATION.
- "visual_change": 0.0–1.0 how much the on-screen content differs from the previous summary.
- "commentary": ONE short sentence for live display to the user — always non-empty.
- "screen_analysis": 3–5 sentences written as a retrieval document. CRITICAL RULE: always lead with the user's ACTIVITY, then add specific content. The activity word is what drives context retrieval — "composing email" surfaces email templates; "debugging code" surfaces code references. Use these templates by context:
  • Code / IDE → "User is [writing/debugging/refactoring] [language] in [file]. Working on [function/class/feature]. [Key identifiers, error messages, imports visible]."
  • Email compose → "User is composing [email type: outreach/follow-up/escalation/internal/proposal/recap] in [Gmail/Outlook]. Subject: '[subject]'. [1–2 sentences of the user's own opening — their stated purpose and recipient context only]."
  • Document editing → "User is [writing/editing] a [document type] in [app]. Topic/purpose: [what the document is about]."
  • Browser / reading → "User is reading [article/docs/PR/thread] about [topic] in [browser/app]. [Key concepts or questions they appear to be researching]."
  • Terminal → "User is running [command] in terminal. Purpose: [what it does or what problem it solves]."
  • Chat / messaging → "User is [reading/drafting] a [Slack/Teams/chat] message about [topic]. [Context of the conversation]."
  COMPOSE RULE: In email or document compose windows, the body often contains pasted background info, quoted chains, or reference material the user did not write. Do NOT include that content in screen_analysis — it contaminates retrieval with irrelevant signals. Only describe what the user is actively authoring.
  Write "" only if the screen is a screensaver or completely blank.
- "filegram_events": array of action objects with "type" in read,browse,search,grep,glob,write,edit,mkdir,move,rename,delete and file paths or URLs. Use [] if not actionable.

If scene and text are essentially unchanged, set significant_change false, novelty below 0.25, filegram_events []. Always write non-empty commentary and screen_analysis regardless.
"""


def strip_image_base64(b64_or_data_url: str) -> str:
    s = b64_or_data_url.strip()
    if "," in s and s.lower().startswith("data:"):
        return s.split(",", 1)[1]
    return s


def _parse_json_array(text: str) -> list[Any]:
    text = text.strip()
    if "```" in text:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
        if m:
            text = m.group(1).strip()
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []
    chunk = text[start : end + 1]
    try:
        data = json.loads(chunk)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _parse_json_object(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if "```" in text:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
        if m:
            text = m.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    chunk = text[start : end + 1]
    try:
        data = json.loads(chunk)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def events_signature(events: list[dict]) -> str:
    key = [(e.get("type", ""), e.get("file", ""), e.get("dir", "")) for e in events]
    return json.dumps(key, ensure_ascii=True)


def normalize_filegram_event(raw: dict) -> dict | None:
    if not isinstance(raw, dict):
        return None
    t = raw.get("type")
    if not isinstance(t, str) or t not in ALLOWED_TYPES:
        return None

    file_val = raw.get("file")
    file_s = file_val.strip() if isinstance(file_val, str) else ""
    dir_val = raw.get("dir")
    dir_s = dir_val.strip() if isinstance(dir_val, str) else ""

    def _int(name: str, default: int = 0) -> int:
        v = raw.get(name, default)
        try:
            return max(0, int(v))
        except (TypeError, ValueError):
            return default

    src = raw.get("source")
    source = src if isinstance(src, str) and src else "vlm_screen"
    out: dict[str, Any] = {"type": t, "source": source}

    if t in {"read", "browse", "search", "grep", "glob"}:
        out["file"] = file_s or "unknown"
    elif t in {"write", "edit", "move", "rename"}:
        out["file"] = file_s or "unknown"
        if t == "edit" or t == "write":
            out["lines_added"] = _int("lines_added", 0)
            out["lines_removed"] = _int("lines_removed", 0)
            c = raw.get("content")
            if isinstance(c, str) and c.strip():
                out["content"] = c.strip()[:2000]
    elif t == "mkdir":
        out["dir"] = dir_s or file_s or "unknown"
    elif t == "delete":
        if file_s:
            out["file"] = file_s

    return out


def normalize_filegram_events(raw_list: list[Any]) -> list[dict]:
    out: list[dict] = []
    for item in raw_list[:8]:
        n = normalize_filegram_event(item) if isinstance(item, dict) else None
        if n:
            out.append(n)
    return out


async def analyze_screen_to_filegram_events(image_bytes: bytes, mime_type: str) -> tuple[list[dict], str]:
    """
    Returns (normalized_events, raw_model_text).
    """
    text = await llm_vision_call(SCREEN_ACTION_PROMPT, image_bytes, mime_type)
    parsed = _parse_json_array(text)
    events = normalize_filegram_events(parsed)
    for ev in events:
        ev.setdefault("source", "vlm_screen")
    return events, text


def _clamp01(x: Any) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, v))


async def analyze_live_screen(
    image_bytes: bytes,
    mime_type: str,
    previous_commentary: str,
    previous_events_sig: str,
) -> tuple[dict[str, Any], str]:
    """
    Returns a result dict:
      significant_change, novelty, visual_change, commentary, events (normalized),
      raw_model_text
    """
    prompt = LIVE_SCREEN_PROMPT.format(
        previous_commentary=previous_commentary or "(none)",
        previous_events_sig=previous_events_sig or "(none)",
    )
    text = await llm_vision_call(prompt, image_bytes, mime_type)
    obj = _parse_json_object(text) or {}
    sig = bool(obj.get("significant_change"))
    novelty = _clamp01(obj.get("novelty"))
    visual = _clamp01(obj.get("visual_change"))
    commentary = obj.get("commentary")
    comm_s = commentary.strip() if isinstance(commentary, str) else ""
    analysis = obj.get("screen_analysis")
    analysis_s = analysis.strip() if isinstance(analysis, str) else ""
    raw_events = obj.get("filegram_events")
    raw_list = raw_events if isinstance(raw_events, list) else []
    # Force source for live pipeline
    cleaned: list[dict] = []
    for item in raw_list:
        if isinstance(item, dict):
            item = {**item, "source": "vlm_screen_live"}
            cleaned.append(item)
    events = normalize_filegram_events(cleaned)

    return {
        "significant_change": sig,
        "novelty": novelty,
        "visual_change": visual,
        "commentary": comm_s,
        "screen_analysis": analysis_s,
        "events": events,
    }, text
