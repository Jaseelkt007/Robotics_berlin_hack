"""Pixel-grid overlay for the TOP planning frame.

Drawn ONLY on the frame the brain uses to *read* object coordinates (`look("top", grid=True)`).
Never overlay the wrist frame or anything fed to a policy/model — it would corrupt the input.
Helps Claude report a pixel against labelled gridlines instead of guessing absolute coordinates.
"""
from __future__ import annotations

import io


def draw_grid(jpeg: bytes, step: int = 80, color: tuple[int, int, int] = (0, 255, 0)) -> bytes:
    """Overlay labelled gridlines every `step` px and return a new JPEG."""
    from PIL import Image, ImageDraw  # Pillow is a station_mcp dependency (used for mock frames)

    img = Image.open(io.BytesIO(jpeg)).convert("RGB")
    d = ImageDraw.Draw(img)
    w, h = img.size
    for x in range(0, w, step):
        d.line([(x, 0), (x, h)], fill=color, width=1)
        if x > 0:
            d.text((x + 2, 2), str(x), fill=color)
    for y in range(0, h, step):
        d.line([(0, y), (w, y)], fill=color, width=1)
        if y > 0:
            d.text((2, y + 2), str(y), fill=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()
