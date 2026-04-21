FINGERPRINT_FEATURES = [
    # A: Consumption (0-2)
    ("reading_strategy", "search_ratio"),
    ("reading_strategy", "browse_ratio"),
    ("reading_strategy", "revisit_ratio"),
    # B: Production (3-5)
    ("output_detail", "avg_output_length"),
    ("output_detail", "files_created"),
    ("output_detail", "total_output_chars"),
    # C: Organization (6-8)
    ("directory_style", "dirs_created"),
    ("directory_style", "max_dir_depth"),
    ("directory_style", "files_moved"),
    # D: Iteration (9-11)
    ("edit_strategy", "total_edits"),
    ("edit_strategy", "avg_lines_changed"),
    ("edit_strategy", "small_edit_ratio"),
    # E: Curation (12-13)
    ("version_strategy", "total_deletes"),
    ("version_strategy", "delete_to_create_ratio"),
    # F: Cross-Modal (14-16)
    ("cross_modal_behavior", "structured_files_created"),
    ("cross_modal_behavior", "markdown_table_rows"),
    ("cross_modal_behavior", "image_files_created"),
]
