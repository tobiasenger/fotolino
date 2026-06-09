import logging
from pathlib import Path

import numpy as np
from PIL import Image

from .constants import COLLAGE_W, COLLAGE_H, COLLAGE_LAYOUTS

logger = logging.getLogger(__name__)


def _crop_to_fill(img: Image.Image, target_w: int, target_h: int, rotation: int = 0) -> Image.Image:
    """Scale + centre-crop img to exactly (target_w, target_h)."""
    if rotation:
        img = img.rotate(-rotation, expand=True)

    src_w, src_h = img.size
    src_ratio    = src_w / src_h
    target_ratio = target_w / target_h

    if src_ratio > target_ratio:
        # Wider than target: fit height, crop width
        scale  = target_h / src_h
        new_w  = int(src_w * scale)
        img    = img.resize((new_w, target_h), Image.LANCZOS)
        x_off  = (new_w - target_w) // 2
        img    = img.crop((x_off, 0, x_off + target_w, target_h))
    else:
        # Taller than target: fit width, crop height
        scale  = target_w / src_w
        new_h  = int(src_h * scale)
        img    = img.resize((target_w, new_h), Image.LANCZOS)
        y_off  = (new_h - target_h) // 2
        img    = img.crop((0, y_off, target_w, y_off + target_h))

    return img


class CollageCreator:
    def __init__(self, config_manager):
        self._cfg = config_manager

    def create(self, photo_paths: list[Path | str], capture_count: int) -> Image.Image:
        """
        Build a 1800×1200 collage from photo_paths (JPEG files on disk).
        Overlays the PNG cover for capture_count if one is configured.
        Returns the finished PIL Image (RGB).
        """
        canvas   = Image.new("RGB", (COLLAGE_W, COLLAGE_H), (255, 255, 255))
        layout   = COLLAGE_LAYOUTS.get(capture_count, COLLAGE_LAYOUTS[1])
        n_photos = min(len(photo_paths), len(layout))

        for i in range(n_photos):
            slot = layout[i]            # (x, y, w, h, rotation)
            x, y, w, h, rot = slot
            try:
                photo = Image.open(photo_paths[i]).convert("RGB")
                photo = _crop_to_fill(photo, w, h, rot)
                canvas.paste(photo, (x, y))
            except Exception as e:
                logger.warning("Could not place photo %s: %s", photo_paths[i], e)

        # Overlay PNG cover
        cover_rel = self._cfg.cover_path(capture_count)
        if cover_rel:
            cover_path = self._cfg.resolve_asset(cover_rel)
            if cover_path.exists():
                try:
                    overlay = Image.open(cover_path).convert("RGBA")
                    if overlay.size != (COLLAGE_W, COLLAGE_H):
                        logger.warning(
                            "Cover %s is %dx%d (expected %dx%d) – auto-scaling",
                            cover_path, overlay.size[0], overlay.size[1], COLLAGE_W, COLLAGE_H,
                        )
                        overlay = overlay.resize((COLLAGE_W, COLLAGE_H), Image.LANCZOS)
                    canvas_rgba = canvas.convert("RGBA")
                    combined    = Image.alpha_composite(canvas_rgba, overlay)
                    canvas      = combined.convert("RGB")
                    logger.debug("Overlay applied: %s", cover_path)
                except Exception as e:
                    logger.warning("Could not apply overlay %s: %s", cover_path, e)
            else:
                logger.debug("Overlay file not found: %s", cover_path)

        return canvas

    def create_from_arrays(self, frames: list[np.ndarray], capture_count: int,
                           temp_dir: Path) -> Image.Image:
        """
        Build a collage directly from numpy RGB arrays (e.g. freshly captured frames).
        Saves them as temp JPEGs first, then delegates to create().
        """
        temp_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        for i, frame in enumerate(frames):
            p = temp_dir / f"tmp_{i:02d}.jpg"
            Image.fromarray(frame, "RGB").save(p, "JPEG", quality=95)
            paths.append(p)
        return self.create(paths, capture_count)
