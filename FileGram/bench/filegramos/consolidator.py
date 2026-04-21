from .engram import ContentChunk, Engram, MemoryStore
from typing import Optional


def build_memory_store(
    content_profile: str,
    behavioral_patterns: list[str],
    dimension_classifications: list[str],
    absence_flags: list[str],
    fingerprints: list[list[float]],
    centroid: Optional[list[float]] = None,
    content_chunks: Optional[list[dict]] = None,
) -> MemoryStore:
    """Build a MemoryStore from trajectory data (called by offline consolidation pipeline)."""
    engrams = [Engram(fingerprint=fp) for fp in fingerprints]

    if centroid is None:
        if fingerprints:
            n = len(fingerprints[0])
            centroid = [sum(fp[i] for fp in fingerprints) / len(fingerprints) for i in range(n)]
        else:
            centroid = [0.0] * 17

    chunks = [ContentChunk(text=c.get("text", ""), embedding=c.get("embedding", [])) for c in (content_chunks or [])]

    return MemoryStore(
        content_profile=content_profile,
        behavioral_patterns=behavioral_patterns,
        dimension_classifications=dimension_classifications,
        absence_flags=absence_flags,
        centroid=centroid,
        content_chunks=chunks,
        engrams=engrams,
    )
