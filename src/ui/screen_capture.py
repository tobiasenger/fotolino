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
import tempfile
import time
from enum import Enum, auto
from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QColor, QPainter, QPixmap

from ..constants import FONT_HUGE, FONT_LARGE, FONT_SMALL
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

        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tick)

    # ------------------------------------------------------------------

    def on_enter(self):
        self._total_photos = self.app.context.capture_count()
        self._photo_idx = 0
        self._timing = self.app.config.settings.get("capture_timing", {})
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
                    self.transition_to("collage")
                    return
                self._set_phase(_Phase.COUNTDOWN)

        if self._phase != _Phase.FLASH:
            try:
                self._preview_pixmap = self.app.camera.get_qpixmap(mirror=True)
            except Exception:
                self._preview_pixmap = None
        self.update()

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
            text = self._timing.get("smile_text", "Lächeln!")
            self._draw_centered(painter, w, cy, FONT_LARGE, (255, 230, 0), text)
        elif self._phase == _Phase.POST:
            self._draw_centered(painter, w, h - 80, FONT_SMALL, (200, 255, 200),
                                f"Foto {self._photo_idx + 1} von {self._total_photos} aufgenommen")

    @staticmethod
    def _draw_centered(painter, w, y_center, size, color, text):
        draw_shadow_text(painter, 0, y_center - size - 10, w, size * 2 + 20,
                         text, size, color)

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
