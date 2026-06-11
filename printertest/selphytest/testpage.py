"""Test page generation.

Generates a diagnostic image with edge frames (to judge borderless behaviour
and cropping), color bars, a gray gradient and — when Pillow is available —
text labels showing the exact settings used, so each physical print can be
matched to its report entry.

Pillow is optional: without it a plain PPM image (no text) is generated, which
CUPS prints just as well.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

log = logging.getLogger("selphytest.testpage")

# Postcard 100 x 148 mm at 300 dpi (portrait). Other page sizes are covered by
# the driver/filter scaling options under test; the aspect only matters mildly.
DEFAULT_SIZE = (1181, 1748)

FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",  # macOS dev machine
]


def have_pillow() -> bool:
    try:
        import PIL  # noqa: F401
        return True
    except ImportError:
        return False


def generate(out_dir: Path, label_lines: list[str], index: int | None = None,
             size: tuple[int, int] = DEFAULT_SIZE) -> Path:
    """Create a test image and return its path (JPEG with Pillow, else PPM)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    suffix = f"_{index:02d}" if index is not None else ""
    if have_pillow():
        path = out_dir / f"testpage_{stamp}{suffix}.jpg"
        _generate_pillow(path, label_lines, index, size)
    else:
        path = out_dir / f"testpage_{stamp}{suffix}.ppm"
        _generate_ppm(path, size)
        log.warning(
            "Pillow not installed — generated unlabeled PPM test page. "
            "For labeled pages: sudo apt install python3-pil"
        )
    log.info("Test page written: %s", path)
    return path


def _load_font(size: int):
    from PIL import ImageFont
    for path in FONT_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)  # Pillow >= 10.1
    except TypeError:
        return ImageFont.load_default()


def _generate_pillow(path: Path, label_lines: list[str], index: int | None,
                     size: tuple[int, int]) -> None:
    from PIL import Image, ImageDraw

    width, height = size
    img = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(img)

    # Edge frames: outermost red frame sits on the very edge — if it is visible
    # on paper the print is NOT borderless / is underscaled; if missing, the
    # edge was cropped (normal for borderless overscan).
    draw.rectangle([0, 0, width - 1, height - 1], outline=(220, 0, 0), width=6)
    draw.rectangle([30, 30, width - 31, height - 31], outline=(0, 90, 220), width=4)
    draw.rectangle([60, 60, width - 61, height - 61], outline=(0, 160, 60), width=2)

    # Color bars
    bar_colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (0, 255, 255),
                  (255, 0, 255), (255, 255, 0), (0, 0, 0)]
    bar_top, bar_height = 120, 140
    bar_width = (width - 240) // len(bar_colors)
    for i, color in enumerate(bar_colors):
        x0 = 120 + i * bar_width
        draw.rectangle([x0, bar_top, x0 + bar_width - 4, bar_top + bar_height],
                       fill=color)

    # Gray gradient
    grad_top = bar_top + bar_height + 30
    grad_width = width - 240
    for x in range(grad_width):
        value = int(255 * x / max(1, grad_width - 1))
        draw.line([(120 + x, grad_top), (120 + x, grad_top + 90)],
                  fill=(value, value, value))

    # Big index number for matching print <-> report entry
    y = grad_top + 140
    if index is not None:
        font_big = _load_font(260)
        draw.text((width // 2, y + 130), f"#{index}", fill=(0, 0, 0),
                  font=font_big, anchor="mm")
        y += 300

    font = _load_font(44)
    for line in label_lines:
        draw.text((width // 2, y), line[:60], fill=(0, 0, 0), font=font, anchor="mm")
        y += 62

    # Center cross
    cx, cy = width // 2, height - 320
    draw.line([(cx - 80, cy), (cx + 80, cy)], fill=(0, 0, 0), width=3)
    draw.line([(cx, cy - 80), (cx, cy + 80)], fill=(0, 0, 0), width=3)

    img.save(path, "JPEG", quality=92, dpi=(300, 300))


def _generate_ppm(path: Path, size: tuple[int, int]) -> None:
    """Pure-python fallback: red edge frame + horizontal gradient, binary PPM."""
    width, height = size
    frame = 6
    rows = []
    for y in range(height):
        row = bytearray()
        for x in range(width):
            if x < frame or x >= width - frame or y < frame or y >= height - frame:
                row += bytes((220, 0, 0))
            else:
                value = int(255 * x / max(1, width - 1))
                row += bytes((value, value, 255 - value))
        rows.append(bytes(row))
    with open(path, "wb") as fh:
        fh.write(f"P6\n{width} {height}\n255\n".encode("ascii"))
        fh.writelines(rows)
