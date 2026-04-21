from dataclasses import dataclass
from datetime import datetime


@dataclass
class ContextItem:
    id: str
    display_name: str
    kind: str        # "meta" | "file" | "data" | "people"
    source: str
    description: str
    size_bytes: int
    last_used: datetime
    status: str      # "active" | "idle" | "suggested"
    embedding: list[float]
    channel: str     # "procedural" | "semantic" | "episodic"
    content: str
    score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "kind": self.kind,
            "source": self.source,
            "description": self.description,
            "size_bytes": self.size_bytes,
            "last_used": self.last_used.isoformat(),
            "status": self.status,
            "channel": self.channel,
            "content": self.content,
            "score": self.score,
        }
