from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent / "FileGram"))

from bench.filegramos.engram import MemoryStore

from .models import ContextItem

DATA_DIR = Path(__file__).parent.parent / "data"
STATE_FILE = DATA_DIR / "session_state.json"


class AppState:
    def __init__(self) -> None:
        self.pool: list[ContextItem] = []
        self.attached: list[ContextItem] = []
        self.dismissed_ids: set[str] = set()
        self.recent_messages: list[str] = []
        self.u_static: list[float] = []
        self.memory_store: Optional[MemoryStore] = None
        self.norm_params: list[tuple[float, float]] = []
        self.token_budget: int = 10_000
        self.session_events: list[dict] = []
        self.current_ask: str = ""
        # Live screen VLM (in-memory; not persisted)
        self.live_screen_last_commentary: str = ""   # 1-sentence display string
        self.live_screen_last_analysis: str = ""     # rich description for embedding/scoring
        self.live_screen_last_events_sig: str = ""
        self.live_screen_last_vlm_monotonic: float = 0.0
        self.live_screen_inflight: bool = False
        self.live_screen_generation: int = 0
        # Subsystem A — structured accessibility context (in-memory; not persisted)
        self.active_app: str = ""
        self.window_title: str = ""
        self.selected_text: str = ""
        # Subsystem B — last computed proactive context-type suggestions
        self.context_types: dict = {}
        # Why the last rescore suggested what it did (or nothing).
        self.suggest_diag: dict = {}

    @property
    def tokens_used(self) -> int:
        return sum(item.size_bytes // 4 for item in self.attached)

    @property
    def budget_used(self) -> float:
        return min(1.0, self.tokens_used / self.token_budget)

    def get_pool_item(self, item_id: str) -> Optional[ContextItem]:
        return next((item for item in self.pool if item.id == item_id), None)

    def save_session(self) -> None:
        DATA_DIR.mkdir(exist_ok=True)
        state = {
            "dismissed_ids": list(self.dismissed_ids),
            # id + when it was attached; the old list-of-ids format still loads.
            "attached": [
                {"id": item.id,
                 "attached_at": item.attached_at.isoformat() if item.attached_at else None}
                for item in self.attached
            ],
            "recent_messages": self.recent_messages,
            "session_events": self.session_events,
            "current_ask": self.current_ask,
        }
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def load_session(self) -> None:
        if not STATE_FILE.exists():
            return
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            self.dismissed_ids = set(data.get("dismissed_ids", []))
            self.recent_messages = data.get("recent_messages", [])
            self.session_events = data.get("session_events", [])
            self.current_ask = data.get("current_ask", "")
            stamps = _attached_stamps(data)
            self.attached = []   # idempotent: never double-append on a reload
            for item in self.pool:
                if item.id in stamps:
                    item.status = "active"
                    item.attached_at = stamps[item.id]
                    self.attached.append(item)
        except Exception:
            pass


def _attached_stamps(data: dict) -> dict:
    """Map attached id -> attached_at, accepting both the current and legacy shapes."""
    stamps: dict = {}
    for entry in data.get("attached", []):
        if isinstance(entry, dict) and entry.get("id"):
            raw = entry.get("attached_at")
            try:
                stamps[entry["id"]] = datetime.fromisoformat(raw) if raw else None
            except (TypeError, ValueError):
                stamps[entry["id"]] = None
    for item_id in data.get("attached_ids", []):   # pre-timestamp sessions
        stamps.setdefault(item_id, None)
    return stamps


app_state = AppState()
