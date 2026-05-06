"""Programmatically generate small flat icons for the sidebar.

Avoids depending on bundled PNG/SVG files. Returns Qt QIcon objects.
"""
from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageDraw
from PySide6.QtGui import QIcon, QPixmap

SIZE = 40  # render size; Qt scales to display size automatically
STROKE_BLUE = (10, 132, 255, 255)
STROKE_DARK = (60, 60, 67, 255)
FILL_BLUE = (10, 132, 255, 255)
FILL_BLUE_LIGHT = (10, 132, 255, 120)


def _to_qicon(img: Image.Image) -> QIcon:
    buf = BytesIO()
    img.save(buf, format="PNG")
    px = QPixmap()
    px.loadFromData(buf.getvalue(), "PNG")
    return QIcon(px)


def _new() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def home_icon() -> QIcon:
    img, d = _new()
    # Rounded square (filled) like reference
    d.rounded_rectangle((4, 4, SIZE - 4, SIZE - 4), radius=10, fill=FILL_BLUE)
    # House shape (white)
    pts = [
        (SIZE / 2, 11),
        (SIZE - 11, SIZE / 2),
        (SIZE - 14, SIZE / 2),
        (SIZE - 14, SIZE - 11),
        (14, SIZE - 11),
        (14, SIZE / 2),
        (11, SIZE / 2),
    ]
    d.polygon(pts, fill=(255, 255, 255, 255))
    # Door
    d.rectangle((SIZE / 2 - 3, SIZE - 19, SIZE / 2 + 3, SIZE - 11), fill=FILL_BLUE)
    return _to_qicon(img)


def modes_icon() -> QIcon:
    img, d = _new()
    d.rounded_rectangle((4, 4, SIZE - 4, SIZE - 4), radius=10, fill=FILL_BLUE)
    # Plus sign in white
    cx, cy = SIZE / 2, SIZE / 2
    d.rectangle((cx - 8, cy - 2, cx + 8, cy + 2), fill=(255, 255, 255, 255))
    d.rectangle((cx - 2, cy - 8, cx + 2, cy + 8), fill=(255, 255, 255, 255))
    return _to_qicon(img)


def vocabulary_icon() -> QIcon:
    img, d = _new()
    d.rounded_rectangle((4, 4, SIZE - 4, SIZE - 4), radius=10, fill=FILL_BLUE)
    # Two stacked rectangles (white)
    d.rounded_rectangle((10, 13, SIZE - 14, 24), radius=2, fill=(255, 255, 255, 255))
    d.rounded_rectangle((14, 22, SIZE - 10, 33), radius=2, fill=(255, 255, 255, 255))
    return _to_qicon(img)


def configuration_icon() -> QIcon:
    img, d = _new()
    # Circle bg
    d.ellipse((6, 6, SIZE - 6, SIZE - 6), fill=STROKE_DARK)
    # Inner circle (white)
    d.ellipse((11, 11, SIZE - 11, SIZE - 11), fill=(255, 255, 255, 255))
    # Center dot
    d.ellipse((SIZE / 2 - 4, SIZE / 2 - 4, SIZE / 2 + 4, SIZE / 2 + 4), fill=STROKE_DARK)
    return _to_qicon(img)


def sound_icon() -> QIcon:
    img, d = _new()
    # Speaker shape
    body_pts = [
        (10, 16),
        (16, 16),
        (24, 10),
        (24, SIZE - 10),
        (16, SIZE - 16),
        (10, SIZE - 16),
    ]
    d.polygon(body_pts, fill=STROKE_DARK)
    # Sound waves (arcs)
    for r, w in [(6, 2), (12, 2)]:
        d.arc((24 + r, SIZE / 2 - r - 2, 24 + r * 3, SIZE / 2 + r + 2),
              start=300, end=60, fill=STROKE_DARK, width=w)
    return _to_qicon(img)


def transcribe_file_icon() -> QIcon:
    img, d = _new()
    # Document-with-folded-corner background
    d.rounded_rectangle((9, 6, SIZE - 9, SIZE - 6), radius=4, fill=FILL_BLUE)
    # Folded corner triangle (lighter)
    d.polygon([(SIZE - 9, 6), (SIZE - 9, 14), (SIZE - 17, 6)], fill=(255, 255, 255, 120))
    # Waveform bars (white)
    cx = SIZE / 2
    bar_w = 2
    heights = [6, 12, 18, 12, 8, 14, 10]
    start_x = cx - (len(heights) * (bar_w + 2)) / 2 + 1
    for i, h in enumerate(heights):
        x = start_x + i * (bar_w + 2)
        y0 = SIZE / 2 - h / 2
        y1 = SIZE / 2 + h / 2
        d.rounded_rectangle((x, y0, x + bar_w, y1), radius=1, fill=(255, 255, 255, 255))
    return _to_qicon(img)


def history_icon() -> QIcon:
    img, d = _new()
    # Clock circle outline
    d.ellipse((6, 6, SIZE - 6, SIZE - 6), outline=FILL_BLUE, width=3)
    # Hour + minute hand
    d.line((SIZE / 2, SIZE / 2, SIZE / 2, 14), fill=FILL_BLUE, width=3)
    d.line((SIZE / 2, SIZE / 2, SIZE - 14, SIZE / 2), fill=FILL_BLUE, width=3)
    return _to_qicon(img)


def all_icons() -> dict[str, QIcon]:
    return {
        "Home": home_icon(),
        "Modes": modes_icon(),
        "Transcribe File": transcribe_file_icon(),
        "Vocabulary": vocabulary_icon(),
        "Configuration": configuration_icon(),
        "Sound": sound_icon(),
        "History": history_icon(),
    }
