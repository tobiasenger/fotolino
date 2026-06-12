"""
Capture screen – live mirrored camera preview with countdown and photo capture.
Flash LED is ON for the entire duration of this screen.

Preview: polls camera.get_qpixmap() via a 50 ms QTimer and draws it with fast
scaling (smooth scaling at 20 fps is too expensive on a Pi 4).
QGlPicamera2 is intentionally not used – it causes an OpenGL/EGL abort with
Camera Module v2 on Raspberry Pi 4 regardless of initialisation order.
"""
from __future__ import annotations

import logging
import random
import tempfile
import time
from enum import Enum, auto
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPixmap

from ..constants import FONT_HUGE, FONT_SMALL, SCREEN_H, SCREEN_W
from .base_screen import BaseScreen
from .widgets import draw_shadow_text

logger = logging.getLogger(__name__)


class _Phase(Enum):
    PREVIEW = auto()
    COUNTDOWN = auto()
    SMILE = auto()
    FLASH = auto()
    POST = auto()


class CaptureScreen(BaseScreen):
    def __init__(self, app):
        super().__init__(app)
        self._phase = _Phase.PREVIEW
        self._phase_start = 0.0
        self._photo_idx = 0
        self._total_photos = 0
        self._timing: dict = {}
        self._countdown_value: int | None = None
        self._preview_pixmap: QPixmap | None = None
        self._smile_pixmaps: list[QPixmap] = []
        self._smile_current: QPixmap | None = None   # pre-scaled to widget size

        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tick)

    # ------------------------------------------------------------------

    def on_enter(self):
        ctx = self.app.context
        ctx.captured_photos = []   # each capture (segment) starts a fresh set
        self._total_photos = ctx.capture_count()
        self._photo_idx = 0
        self._timing = self.app.config.settings.get("capture_timing", {})
        self._smile_pixmaps = [
            pix for f in self.app.config.smile_overlay_files()
            if (pix := self._load_pixmap(f)) is not None
        ]
        self._set_phase(_Phase.PREVIEW)

        self.app.gpio.set_flash_led(True)
        self.app.camera.start()

        if not self.app.camera.is_connected():
            self.app.show_notification(
                "Kamera nicht verfügbar – Testbild wird verwendet. "
                "Kabelverbindung und 'rpicam-hello' prüfen.",
                duration=5.0, level="warning",
            )
        self._timer.start()

    def on_exit(self):
        self._timer.stop()
        self.app.gpio.set_flash_led(False)
        self.app.camera.stop()

    # ------------------------------------------------------------------

    def _set_phase(self, phase: _Phase):
        self._phase = phase
        self._phase_start = time.monotonic()
        if phase == _Phase.COUNTDOWN:
            self._countdown_value = None
        elif phase == _Phase.SMILE:
            self._pick_smile_overlay()

    def _elapsed(self) -> float:
        return time.monotonic() - self._phase_start

    def _tick(self):
        cfg = self._timing
        preview_dur = cfg.get("initial_preview_seconds", 2.0)
        countdown_n = int(cfg.get("countdown_from", 3))
        smile_dur = cfg.get("smile_duration", 0.8)
        post_dur = cfg.get("post_photo_pause", 2.0)
        flash_dur = cfg.get("flash_duration", 0.15)
        t = self._elapsed()

        if self._phase == _Phase.PREVIEW:
            if t >= preview_dur:
                self._set_phase(_Phase.COUNTDOWN)
        elif self._phase == _Phase.COUNTDOWN:
            remaining = max(1, countdown_n - int(t))
            if remaining != self._countdown_value:
                self._countdown_value = remaining
                self._play_sound("countdown_beep")
            if t >= countdown_n:
                if cfg.get("smile_enabled", True):
                    self._set_phase(_Phase.SMILE)
                else:
                    self._do_capture()
                    self._set_phase(_Phase.FLASH)
        elif self._phase == _Phase.SMILE:
            if t >= smile_dur:
                self._do_capture()
                self._set_phase(_Phase.FLASH)
        elif self._phase == _Phase.FLASH:
            if t >= flash_dur:
                self._set_phase(_Phase.POST)
        elif self._phase == _Phase.POST:
            if t >= post_dur:
                self._photo_idx += 1
                if self._photo_idx >= self._total_photos:
                    self._finish_captures()
                    return
                self._set_phase(_Phase.COUNTDOWN)

        if self._phase != _Phase.FLASH:
            try:
                self._preview_pixmap = self.app.camera.get_qpixmap(mirror=True)
            except Exception:
                self._preview_pixmap = None
        self.update()

    def _finish_captures(self):
        """All photos taken: standard paths show the collage screen; custom
        paths build the collage in the background and continue the sequence."""
        if self.app.context.is_custom_path():
            self.app.start_collage_build()
            self.app.advance_segment()
        else:
            self.transition_to("collage")

    # ------------------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        w, h = self.width(), self.height()

        if self._phase == _Phase.FLASH:
            painter.fillRect(self.rect(), QColor(255, 255, 255))
            painter.end()
            return

        if self._preview_pixmap:
            self._draw_cover(painter, self._preview_pixmap, fast=True)
        else:
            self._paint_background(painter)

        self._draw_hud(painter, w, h)
        painter.end()

    def _draw_hud(self, painter: QPainter, w: int, h: int):
        cy = h // 2

        if self._phase == _Phase.PREVIEW:
            self._draw_centered(painter, w, h - 80, FONT_SMALL,
                                (255, 255, 255),
                                f"Foto {self._photo_idx + 1} von {self._total_photos}")
        elif self._phase == _Phase.COUNTDOWN:
            self._draw_centered(painter, w, cy, FONT_HUGE, (255, 255, 255),
                                str(self._countdown_value or 1))
        elif self._phase == _Phase.SMILE:
            if self._smile_current:
                painter.drawPixmap((w - self._smile_current.width()) // 2,
                                   cy - self._smile_current.height() // 2,
                                   self._smile_current)
        elif self._phase == _Phase.POST:
            self._draw_centered(painter, w, h - 80, FONT_SMALL, (200, 255, 200),
                                f"Foto {self._photo_idx + 1} von {self._total_photos} aufgenommen")

    @staticmethod
    def _draw_centered(painter, w, y_center, size, color, text):
        draw_shadow_text(painter, 0, y_center - size - 10, w, size * 2 + 20,
                         text, size, color)

    def _pick_smile_overlay(self):
        """Randomly choose one of the enabled smile PNGs for this photo and
        pre-scale it once (smooth scaling per paint tick is too slow on the
        Pi). PNG pixels are treated as 1920x1080 design coordinates."""
        if not self._smile_pixmaps:
            self._smile_current = None
            return
        pix = random.choice(self._smile_pixmaps)
        factor = min(self.width() / SCREEN_W, self.height() / SCREEN_H)
        self._smile_current = pix.scaled(
            max(1, round(pix.width() * factor)),
            max(1, round(pix.height() * factor)),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)

    # ------------------------------------------------------------------

    def _play_sound(self, key: str):
        sound = self.app.config.settings.get("system_sounds", {}).get(key, "")
        if sound:
            self.app.audio.play_sfx(self.app.config.resolve_asset(sound))

    def _do_capture(self):
        frame = self.app.camera.capture_photo()
        try:
            path = self.app.storage.save_photo(frame, self._photo_idx)
        except IOError as e:
            # Keep the session alive: park the photo in /tmp so the collage
            # can still be built and shown even without the USB stick.
            self.app.show_notification(str(e), duration=8.0, level="error")
            from PIL import Image
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                Image.fromarray(frame, "RGB").save(tmp, "JPEG", quality=95)
                path = Path(tmp.name)
            logger.warning("Foto ersatzweise zwischengespeichert: %s – wird beim "
                           "Entfernen des Temp-Verzeichnisses gelöscht!", path)

        self.app.context.captured_photos.append(path)
        self._play_sound("shutter_click")
