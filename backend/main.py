import base64
import json
import re
import sys
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "FileGram"))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .embed import async_embed, embed
from .models import ContextItem
from .scoring import (
    build_h_vec,
    build_norm_params,
    build_query,
    build_task_profile,
    compute_drift,
    compute_weights,
    detect_task_phase,
    get_u_vec,
    normalize_fingerprint,
    score_all_expanded,
    u_to_text,
    w_to_text,
    workspace_from_events,
)
from .state import app_state
from .vlm_screen import (
    LIVE_MIN_INTERVAL_SEC,
    analyze_live_screen,
    analyze_screen_to_filegram_events,
    strip_image_base64,
)

from bench.filegramos.engram import ContentChunk, Engram, MemoryStore
from bench.filegramos.feature_extraction import FeatureExtractor
from bench.filegramos.fingerprint import compute_fingerprint
from filegramengine.behavior.collector import BehaviorCollector

DATA_DIR = Path(__file__).parent.parent / "data"
FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"
VALID_IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/webp"}
MAX_IMAGE_BYTES = 6 * 1024 * 1024

collector = BehaviorCollector()


def _decode_image_payload(image_base64: str, mime_type: str, default_mime: str) -> tuple[bytes, str]:
    b64 = strip_image_base64(image_base64)
    try:
        image_bytes = base64.b64decode(b64, validate=False)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid base64 image") from exc

    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="Image too large (max 6 MiB decoded)")

    mime = (mime_type or default_mime).strip().lower()
    if mime == "image/jpg":
        mime = "image/jpeg"
    if mime not in VALID_IMAGE_MIME_TYPES:
        allowed = ", ".join(sorted(VALID_IMAGE_MIME_TYPES))
        raise HTTPException(status_code=400, detail=f"mime_type must be one of {allowed}")

    return image_bytes, mime


def _record_events(events: list[dict], *, persist: bool = True) -> None:
    for event in events:
        collector.record_event(event)
        app_state.session_events.append(event)
    if persist:
        app_state.save_session()


def _stats_payload() -> dict:
    stats = collector.stats
    return {
        "current_file": stats.current_file,
        "files_read_count": len(stats.files_read),
        "tool_sequence_len": len(stats.tool_sequence),
        "task_phase": detect_task_phase(stats.tool_sequence),
    }


def _load_pool() -> list[ContextItem]:
    raw: list[dict] = json.loads((DATA_DIR / "pool.json").read_text(encoding="utf-8"))
    return [
        ContextItem(
            id=e["id"],
            display_name=e["display_name"],
            kind=e["kind"],
            source=e["source"],
            description=e["description"],
            size_bytes=e["size_bytes"],
            last_used=datetime.fromisoformat(e["last_used"]),
            status=e.get("status", "idle"),
            embedding=[],
            channel=e["channel"],
            content=e["content"],
        )
        for e in raw
    ]


def _save_pool() -> None:
    raw = [
        {
            "id": item.id,
            "display_name": item.display_name,
            "kind": item.kind,
            "source": item.source,
            "description": item.description,
            "size_bytes": item.size_bytes,
            "last_used": item.last_used.isoformat(),
            "status": "idle",
            "channel": item.channel,
            "content": item.content,
        }
        for item in app_state.pool
    ]
    (DATA_DIR / "pool.json").write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_memory_store() -> MemoryStore:
    data: dict = json.loads((DATA_DIR / "memory_store.json").read_text(encoding="utf-8"))
    return MemoryStore(
        content_profile=data["content_profile"],
        behavioral_patterns=data["behavioral_patterns"],
        dimension_classifications=data["dimension_classifications"],
        absence_flags=data["absence_flags"],
        centroid=data["centroid"],
        content_chunks=[ContentChunk(text=c["text"]) for c in data.get("content_chunks", [])],
        engrams=[Engram(fingerprint=e["fingerprint"]) for e in data.get("engrams", [])],
    )


@asynccontextmanager
async def lifespan(application: FastAPI):
    app_state.pool = _load_pool()
    app_state.memory_store = _load_memory_store()

    for item in app_state.pool:
        item.embedding = embed(f"{item.display_name}: {item.description}\n{item.content}")

    app_state.u_static = embed(u_to_text(app_state.memory_store))

    for chunk in app_state.memory_store.content_chunks:
        if not chunk.embedding:
            chunk.embedding = embed(chunk.text)

    app_state.norm_params = build_norm_params(app_state.memory_store)
    app_state.load_session()
    for evt in app_state.session_events:
        collector.record_event(evt)

    yield


app = FastAPI(title="Pacific Context Recommender", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


async def _rescore() -> tuple[list[tuple[ContextItem, float]], dict, float, str]:
    stats = collector.stats
    has_session = bool(
        app_state.recent_messages
        or app_state.session_events
        or app_state.live_screen_last_commentary
    )
    if not has_session:
        return [], {}, 0.0, "exploration"

    h_t_recent = app_state.recent_messages[-3:]
    ws = workspace_from_events(app_state.session_events)
    screen_commentary = app_state.live_screen_last_commentary
    screen_analysis = app_state.live_screen_last_analysis
    query = build_query(
        app_state.current_ask,
        stats,
        h_t_recent,
        screen_commentary,
        ws,
        screen_analysis,
    )

    q_emb = await async_embed(query)
    u_vec = get_u_vec(app_state.memory_store, q_emb, app_state.u_static)
    task_vec = await build_task_profile(
        app_state.session_events,
        app_state.recent_messages,
        screen_analysis or screen_commentary,
        ws["current_file"] or stats.current_file or "",
    )
    w_text = w_to_text(stats, ws)
    screen_context = screen_analysis or screen_commentary
    if screen_context:
        w_text += f"\nCurrently viewing: {screen_context}"
    w_vec = await async_embed(w_text)
    raw_files = ws["files_read"][:5] or list(stats.files_read)[:5]
    clean_files = [f for f in raw_files if f and f != "unknown" and not f.startswith("http")]
    h_vec = await build_h_vec(app_state.recent_messages, clean_files)

    features = FeatureExtractor().extract_all(collector.events)
    w_fp = compute_fingerprint(features)
    w_fp_norm = normalize_fingerprint(w_fp, app_state.norm_params)
    delta = compute_drift(app_state.memory_store.centroid, w_fp_norm)

    task_phase = detect_task_phase(ws["tool_sequence"] or stats.tool_sequence)
    if screen_analysis or screen_commentary:
        workspace_activity = 1.0
    else:
        workspace_activity = min(1.0, len(ws["tool_sequence"]) / 10.0)
    weights = compute_weights(
        delta,
        task_phase,
        app_state.budget_used,
        workspace_activity,
        has_task_profile=bool(task_vec),
    )

    for item in app_state.pool:
        if item.status == "suggested":
            item.status = "idle"

    expansion_context = " | ".join(
        p for p in [
            *app_state.recent_messages[-3:],
            screen_analysis or screen_commentary,
        ] if p and p.strip()
    )
    scored = await score_all_expanded(
        query=query,
        context=expansion_context,
        pool=app_state.pool,
        attached=app_state.attached,
        dismissed_ids=app_state.dismissed_ids,
        u_vec=u_vec,
        w_vec=w_vec,
        h_vec=h_vec,
        task_vec=task_vec,
        weights=weights,
        query_emb=q_emb,
    )

    score_map = {item.id: score for item, score, _ in scored}
    for item in app_state.pool:
        item.score = score_map.get(item.id, 0.0)

    suggestions: list[tuple[ContextItem, float]] = []
    for item, score, _ in scored[:3]:
        item.status = "suggested"
        suggestions.append((item, score))

    return suggestions, weights, delta, task_phase


# ── Pydantic request bodies ──────────────────────────────────────────────────

class MessageBody(BaseModel):
    message: str


class SessionEventBody(BaseModel):
    event: dict


class ContextUploadBody(BaseModel):
    display_name: str
    kind: str        # "meta" | "file" | "data" | "people"
    channel: str     # "procedural" | "semantic" | "episodic"
    description: str
    content: str
    source: str = ""


class ScreenAnalyzeBody(BaseModel):
    """Single frame; analyzed by Gemini vision into FileGram session events."""

    image_base64: str
    mime_type: str = "image/png"
    apply: bool = True


class LiveScreenTickBody(BaseModel):
    """Live stream tick: full frame to the VLM (no coarse pixel gate—unreliable with letterboxing / scroll)."""

    image_base64: str
    mime_type: str = "image/jpeg"
    apply: bool = True


# ── API routes ───────────────────────────────────────────────────────────────

@app.get("/api/state")
async def get_state():
    return {
        "pool": [item.to_dict() for item in app_state.pool],
        "attached": [item.to_dict() for item in app_state.attached],
        "dismissed_ids": list(app_state.dismissed_ids),
        "recent_messages": app_state.recent_messages,
        "current_ask": app_state.current_ask,
        "tokens_used": app_state.tokens_used,
        "token_budget": app_state.token_budget,
        "budget_used": app_state.budget_used,
        "session_events": app_state.session_events,
    }


@app.post("/api/message")
async def post_message(body: MessageBody):
    app_state.recent_messages.append(body.message)
    app_state.current_ask = body.message
    if len(app_state.recent_messages) > 10:
        app_state.recent_messages = app_state.recent_messages[-10:]

    suggestions, weights, delta, task_phase = await _rescore()
    app_state.save_session()

    return {
        "suggestions": [item.to_dict() for item, _ in suggestions],
        "weights": weights,
        "delta": delta,
        "task_phase": task_phase,
        "tokens_used": app_state.tokens_used,
    }


@app.post("/api/rescore")
async def manual_rescore():
    suggestions, weights, delta, task_phase = await _rescore()
    return {
        "suggestions": [item.to_dict() for item, _ in suggestions],
        "weights": weights,
        "delta": delta,
        "task_phase": task_phase,
    }


@app.post("/api/attach/{item_id}")
async def attach_item(item_id: str):
    item = app_state.get_pool_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if item.status != "active":
        item.status = "active"
        item.last_used = datetime.now(timezone.utc)
        if item not in app_state.attached:
            app_state.attached.append(item)
    app_state.dismissed_ids.discard(item_id)
    app_state.save_session()
    return {"ok": True, "item": item.to_dict(), "tokens_used": app_state.tokens_used}


@app.delete("/api/attach/{item_id}")
async def detach_item(item_id: str):
    item = app_state.get_pool_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    item.status = "idle"
    app_state.attached = [a for a in app_state.attached if a.id != item_id]
    app_state.save_session()
    return {"ok": True, "tokens_used": app_state.tokens_used}


@app.post("/api/dismiss/{item_id}")
async def dismiss_item(item_id: str):
    item = app_state.get_pool_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    item.status = "idle"
    app_state.dismissed_ids.add(item_id)
    app_state.save_session()
    return {"ok": True}



@app.post("/api/context/upload")
async def upload_context(body: ContextUploadBody):
    valid_kinds = {"meta", "file", "data", "people"}
    valid_channels = {"procedural", "semantic", "episodic"}
    if body.kind not in valid_kinds:
        raise HTTPException(status_code=400, detail=f"kind must be one of {valid_kinds}")
    if body.channel not in valid_channels:
        raise HTTPException(status_code=400, detail=f"channel must be one of {valid_channels}")
    if not body.display_name.strip() or not body.content.strip():
        raise HTTPException(status_code=400, detail="display_name and content are required")

    slug = re.sub(r"[^a-z0-9_\-.]", "_", body.display_name.strip().lower())[:48]
    item_id = f"{slug}-{uuid.uuid4().hex[:8]}"

    item = ContextItem(
        id=item_id,
        display_name=body.display_name.strip(),
        kind=body.kind,
        source=body.source or f"upload/{item_id}",
        description=body.description.strip(),
        size_bytes=len(body.content.encode("utf-8")),
        last_used=datetime.now(timezone.utc),
        status="idle",
        embedding=[],
        channel=body.channel,
        content=body.content,
    )
    item.embedding = embed(f"{item.display_name}: {item.description}\n{item.content}")

    app_state.pool.append(item)
    _save_pool()

    return {"ok": True, "item": item.to_dict()}


@app.post("/api/session/clear")
async def clear_session():
    global collector
    collector = BehaviorCollector()
    for item in app_state.pool:
        if item.status in {"active", "suggested"}:
            item.status = "idle"
    app_state.attached = []
    app_state.session_events = []
    app_state.recent_messages = []
    app_state.current_ask = ""
    app_state.dismissed_ids = set()
    app_state.live_screen_last_commentary = ""
    app_state.live_screen_last_analysis = ""
    app_state.live_screen_last_events_sig = ""
    app_state.live_screen_last_vlm_monotonic = 0.0
    app_state.save_session()
    return {"ok": True}


@app.post("/api/session/event")
async def add_session_event(body: SessionEventBody):
    event = body.event
    _record_events([event], persist=False)
    return {
        "ok": True,
        "stats": _stats_payload(),
    }


@app.post("/api/session/screen/analyze")
async def analyze_screen(body: ScreenAnalyzeBody):
    """VLM → FileGram-shaped events; optional apply updates BehaviorCollector + session_events."""
    image_bytes, mime = _decode_image_payload(body.image_base64, body.mime_type, "image/png")

    try:
        events, vlm_raw = await analyze_screen_to_filegram_events(image_bytes, mime)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Vision model failed: {exc}") from exc

    if body.apply:
        _record_events(events)
        await _rescore()

    return {
        "ok": True,
        "events": events,
        "applied": body.apply,
        "vlm_raw_preview": (vlm_raw or "")[:4000],
        "stats": _stats_payload(),
    }


@app.post("/api/session/screen/live-tick")
async def live_screen_tick(body: LiveScreenTickBody):
    """
    Stateful live VLM: compares to previous commentary / event signature, filters low-novelty
    updates, optionally records new FileGram events.
    """
    now = time.monotonic()
    elapsed = now - app_state.live_screen_last_vlm_monotonic
    if app_state.live_screen_last_vlm_monotonic > 0 and elapsed < LIVE_MIN_INTERVAL_SEC:
        wait = round(LIVE_MIN_INTERVAL_SEC - elapsed, 2)
        return {
            "ok": True,
            "skipped": True,
            "reason": "rate_limit",
            "retry_after_sec": wait,
            "commentary": None,
            "live_commentary": f"[tick] Rate limit: next vision call in ~{wait}s.",
            "events": [],
            "applied": False,
        }

    image_bytes, mime = _decode_image_payload(body.image_base64, body.mime_type, "image/jpeg")

    try:
        result, vlm_raw = await analyze_live_screen(
            image_bytes,
            mime,
            app_state.live_screen_last_commentary,
            app_state.live_screen_last_events_sig,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Vision model failed: {exc}") from exc

    app_state.live_screen_last_vlm_monotonic = time.monotonic()

    sig_change = bool(result.get("significant_change"))
    novelty = float(result.get("novelty") or 0.0)
    visual = float(result.get("visual_change") or 0.0)
    commentary_text = (result.get("commentary") or "").strip()
    analysis_text = (result.get("screen_analysis") or "").strip()
    events = list(result.get("events") or [])
    commentary_out = commentary_text if commentary_text else None
    prev_commentary = app_state.live_screen_last_commentary
    if commentary_text:
        app_state.live_screen_last_commentary = commentary_text
    if analysis_text:
        app_state.live_screen_last_analysis = analysis_text

    applied = False
    if events and body.apply:
        _record_events(events)
        applied = True
        app_state.live_screen_last_events_sig = json.dumps(events[:8], ensure_ascii=True)

    if applied or (commentary_text and commentary_text != prev_commentary):
        await _rescore()

    if commentary_out:
        live_line = commentary_out
    elif applied and events:
        kinds = ", ".join(f"{e.get('type', '?')}:{e.get('file') or e.get('dir') or ''}" for e in events[:4])
        live_line = f"[tick] Update recorded ({len(events)} action(s)): {kinds}"
    elif applied:
        live_line = "[tick] Update recorded (session events applied)."
    else:
        live_line = "[tick] No commentary from model on this frame."

    return {
        "ok": True,
        "skipped": False,
        "filtered": False,
        "commentary": commentary_out,
        "live_commentary": live_line,
        "events": events,
        "applied": applied,
        "metrics": {
            "significant_change": sig_change,
            "novelty": novelty,
            "visual_change": visual,
            "signal_filtering": False,
        },
        "vlm_raw_preview": (vlm_raw or "")[:2500],
        "stats": _stats_payload(),
    }


# Serve frontend build (production). Do NOT mount StaticFiles at "/" — POST /api/* would hit
# StaticFiles and return 405. Use GET-only routes + /assets mount instead.
if FRONTEND_DIST.exists():
    _dist = FRONTEND_DIST.resolve()
    _assets = _dist / "assets"
    if _assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(_assets)), name="spa_assets")

    @app.get("/")
    async def spa_index():
        index = _dist / "index.html"
        if not index.is_file():
            raise HTTPException(status_code=404)
        return FileResponse(index)

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        if full_path.startswith("api/") or full_path == "api":
            raise HTTPException(status_code=404)
        candidate = (_dist / full_path).resolve()
        try:
            candidate.relative_to(_dist)
        except ValueError:
            index = _dist / "index.html"
            if index.is_file():
                return FileResponse(index)
            raise HTTPException(status_code=404) from None
        if candidate.is_file():
            return FileResponse(candidate)
        index = _dist / "index.html"
        if index.is_file():
            return FileResponse(index)
        raise HTTPException(status_code=404)
