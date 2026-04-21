from dataclasses import dataclass, field


@dataclass
class ContentChunk:
    text: str
    embedding: list[float] = field(default_factory=list)


@dataclass
class Engram:
    fingerprint: list[float]  # 17-element raw fingerprint


@dataclass
class MemoryStore:
    content_profile: str
    behavioral_patterns: list[str]
    dimension_classifications: list[str]
    absence_flags: list[str]
    centroid: list[float]  # 17-element Z-score-normalized fingerprint centroid
    content_chunks: list[ContentChunk] = field(default_factory=list)
    engrams: list[Engram] = field(default_factory=list)
