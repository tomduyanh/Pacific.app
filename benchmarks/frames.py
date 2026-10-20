"""Synthetic screen captures for exercising the live-screen path.

Renders IDE-, email- and dashboard-like frames from the pool's own text at a
typical capture size, JPEG-encoded the way the dashboard sends them. They
load-test the vision path realistically (payload size, encode/decode cost);
they are not a vision-accuracy test set.
"""
from __future__ import annotations

import base64
import io
import json
import random
import textwrap

from PIL import Image, ImageDraw, ImageFont

from .harness import REPO

_LAYOUTS = [
    ("VS Code", (30, 30, 30), (212, 212, 212)),
    ("Gmail", (255, 255, 255), (32, 33, 36)),
    ("Datadog", (24, 26, 33), (190, 200, 210)),
    ("Jira", (244, 245, 247), (23, 43, 77)),
]


def make_frames(n: int = 12, size: tuple[int, int] = (1280, 800), seed: int = 3) -> list[str]:
    """Return `n` base64 JPEG frames."""
    rng = random.Random(seed)
    pool = json.loads((REPO / "data" / "pool.json").read_text(encoding="utf-8"))
    font = ImageFont.load_default()
    frames = []
    for i in range(n):
        app, bg, fg = _LAYOUTS[i % len(_LAYOUTS)]
        doc = rng.choice(pool)
        img = Image.new("RGB", size, bg)
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, size[0], 28], fill=tuple(max(0, c - 20) for c in bg))
        draw.text((12, 8), f"{app} — {doc['display_name']}", fill=fg, font=font)
        y = 44
        for line in textwrap.wrap(doc["content"], width=150)[:40]:
            draw.text((24, y), line, fill=fg, font=font)
            y += 16
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80)
        frames.append(base64.b64encode(buf.getvalue()).decode())
    return frames
