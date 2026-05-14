from .schema import FINGERPRINT_FEATURES


def compute_fingerprint(features: list[dict]) -> list[float]:
    """Compute 17-element fingerprint from extracted features. Fixed order per schema."""
    if not features:
        return [0.0] * 17

    merged: dict[str, dict[str, float]] = {}
    for f in features:
        for category, values in f.items():
            if category not in merged:
                merged[category] = {}
            for key, val in values.items():
                if key in merged[category]:
                    merged[category][key] = (merged[category][key] + float(val)) / 2
                else:
                    merged[category][key] = float(val)

    return [merged.get(cat, {}).get(key, 0.0) for cat, key in FINGERPRINT_FEATURES]
