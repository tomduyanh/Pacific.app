from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SessionStats:
    current_file: Optional[str] = None
    files_read: set[str] = field(default_factory=set)
    files_created: list[str] = field(default_factory=list)
    dirs_created: list[str] = field(default_factory=list)
    tool_sequence: list[str] = field(default_factory=list)
    total_lines_added: int = 0
    total_lines_deleted: int = 0
    context_switch_count: int = 0


class BehaviorCollector:
    def __init__(self) -> None:
        self.stats = SessionStats()
        self._events: list[dict] = []

    def record_event(self, event: dict) -> None:
        self._events.append(event)
        event_type = event.get("type", "")
        file_path = event.get("file", "")

        if event_type in {"read", "browse"}:
            if file_path:
                if self.stats.current_file and file_path != self.stats.current_file:
                    self.stats.context_switch_count += 1
                self.stats.current_file = file_path
                self.stats.files_read.add(file_path)
            self.stats.tool_sequence.append(event_type)

        elif event_type in {"search", "grep", "glob"}:
            self.stats.tool_sequence.append(event_type)

        elif event_type == "write":
            if file_path and file_path not in self.stats.files_created:
                self.stats.files_created.append(file_path)
            self.stats.total_lines_added += event.get("lines_added", 0)
            self.stats.tool_sequence.append("write")

        elif event_type == "edit":
            self.stats.total_lines_added += event.get("lines_added", 0)
            self.stats.total_lines_deleted += event.get("lines_removed", 0)
            self.stats.tool_sequence.append("edit")

        elif event_type == "mkdir":
            dir_path = event.get("dir", "")
            if dir_path and dir_path not in self.stats.dirs_created:
                self.stats.dirs_created.append(dir_path)

        elif event_type in {"move", "rename", "delete"}:
            self.stats.tool_sequence.append(event_type)

    @property
    def events(self) -> list[dict]:
        return list(self._events)
