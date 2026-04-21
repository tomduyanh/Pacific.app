from .schema import FINGERPRINT_FEATURES


class FeatureExtractor:
    def extract_all(self, events: list[dict]) -> list[dict]:
        """Extract feature dict from session events for fingerprint computation."""
        reads = [e for e in events if e.get("type") == "read"]
        searches = [e for e in events if e.get("type") in {"search", "grep", "glob"}]
        browses = [e for e in events if e.get("type") == "browse"]
        writes = [e for e in events if e.get("type") in {"write", "edit"}]

        files_seen: set[str] = set()
        revisit_count = 0
        for e in reads + browses:
            f = e.get("file", "")
            if f and f in files_seen:
                revisit_count += 1
            if f:
                files_seen.add(f)

        total_reads = max(len(reads) + len(browses) + len(searches), 1)
        files_created = [e.get("file", "") for e in events if e.get("type") == "write" and e.get("file")]
        dirs_created = [e.get("dir", "") for e in events if e.get("type") == "mkdir" and e.get("dir")]
        edits = [e for e in events if e.get("type") == "edit"]
        lines_changed = [abs(e.get("lines_added", 0) + e.get("lines_removed", 0)) for e in edits]
        small_edits = sum(1 for lc in lines_changed if lc <= 5)
        deletes = [e for e in events if e.get("type") == "delete"]
        output_chars = sum(len(e.get("content", "")) for e in writes)
        output_lengths = [len(e.get("content", "")) for e in writes] if writes else [0]
        structured_exts = {".json", ".csv", ".yaml", ".yml", ".xml", ".sql"}
        image_exts = {".png", ".jpg", ".jpeg", ".svg", ".gif", ".webp"}
        structured_files = [f for f in files_created if any(f.endswith(x) for x in structured_exts)]
        image_files = [f for f in files_created if any(f.endswith(x) for x in image_exts)]
        all_paths = [e.get("file", "") for e in events if e.get("file")]
        max_depth = max((len(p.split("/")) for p in all_paths if p), default=0)
        moves = [e for e in events if e.get("type") in {"move", "rename"}]

        return [{
            "reading_strategy": {
                "search_ratio": len(searches) / total_reads,
                "browse_ratio": len(browses) / total_reads,
                "revisit_ratio": revisit_count / total_reads,
            },
            "output_detail": {
                "avg_output_length": sum(output_lengths) / max(len(output_lengths), 1),
                "files_created": float(len(files_created)),
                "total_output_chars": float(output_chars),
            },
            "directory_style": {
                "dirs_created": float(len(dirs_created)),
                "max_dir_depth": float(max_depth),
                "files_moved": float(len(moves)),
            },
            "edit_strategy": {
                "total_edits": float(len(edits)),
                "avg_lines_changed": sum(lines_changed) / max(len(lines_changed), 1),
                "small_edit_ratio": small_edits / max(len(edits), 1),
            },
            "version_strategy": {
                "total_deletes": float(len(deletes)),
                "delete_to_create_ratio": len(deletes) / max(len(files_created), 1),
            },
            "cross_modal_behavior": {
                "structured_files_created": float(len(structured_files)),
                "markdown_table_rows": 0.0,
                "image_files_created": float(len(image_files)),
            },
        }]
