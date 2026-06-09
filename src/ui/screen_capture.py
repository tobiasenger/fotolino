"""
Capture screen – live mirrored camera preview with countdown and photo capture.
Flash LED is ON for the entire duration of this screen.

Preview: polls camera.get_qpixmap() via a 50 ms QTimer.
QGlPicamera2 is intentionally not used – it causes an OpenGL/EGL abort with
Camera Module v2 on Raspberry Pi 4 regardless of initialisation order.
"""
from enum import Enum, auto
from pathlib import Path
import logging
import time

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPainter, QColor, QFont, QPixmap
from PyQt6.QtWidgets import QLabel

from .base_screen import BaseScreen
from ..constants import FONT_HUGE, FONT_LARGE

logger = logging.getLogger(__name__)


class _Phase(Enum):
    PREVIEW   = auto()
    COUNTDOWN = auto()
    SMILE     = auto()
    FLASH     = auto()
    POST      = auto()


class CaptureScreen(BaseScreen):
    def __init__(self, app):
        super().__init__(app)
        self._phase = _Phase.PREVIEW
        self._phase_start = 0.0
        self._photo_idx = 0
        self._total_photos = 0
        self._timing: dict = {}

        self._preview_pixmap: QPixmap | None = None

        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tick)

    # ------------------------------------------------------------------

    def on_enter(self):
        ctx = self.app.context
        cfg = self.app.config
        self._total_photos = ctx.capture_count()
        self._photo_idx = 0
        self._timing = cfg.settings.get("capture_timing", {})
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

    def _elapsed(self) -> float:
        return time.monotonic() - self._phase_start

    def _tick(self):
        cfg = self._timing
        preview_dur = cfg.get("initial_preview_seconds", 2.0)
        countdown_n = int(cfg.get("countdown_from", 3))
        smile_dur   = cfg.get("smile_duration", 0.8)
        post_dur    = cfg.get("post_photo_pause", 2.0)
        flash_dur   = cfg.get("flash_duration", 0.15)
        t = self._elapsed()

        if self._phase == _Phase.PREVIEW:
            if t >= preview_dur:
                self._set_phase(_Phase.COUNTDOWN)
        elif self._phase == _Phase.COUNTDOWN:
            if t >= countdown_n:
                self._set_phase(_Phase.SMILE)
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
            scaled = self._scaled_cover(self._preview_pixmap, w, h)
            x = (w - scaled.width()) // 2
            y = (h - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        else:
            painter.fillRect(self.rect(), QColor(10, 10, 20))

        self._draw_hud(painter, w, h)
        painter.end()

    def _draw_hud(self, painter: QPainter, w: int, h: int):
        cfg = self._timing
        countdown_n = int(cfg.get("countdown_from", 3))
        cx, cy = w // 2, h // 2

        def draw_text(text, size, color, y_center, bold=True):
            font = QFont("DejaVu Sans", size)
            font.setBold(bold)
            painter.setFont(font)
            rect = (0, y_center - size - 10, w, size * 2 + 20)
            painter.setPen(QColor(0, 0, 0))
            painter.drawText(rect[0] + 3, rect[1] + 3, rect[2], rect[3],
                             Qt.AlignmentFlag.AlignCenter, text)
            painter.setPen(QColor(*color))
            painter.drawText(rect[0], rect[1], rect[2], rect[3],
                             Qt.AlignmentFlag.AlignCenter, text)

        if self._phase == _Phase.PREVIEW:
            draw_text(f"Foto {self._photo_idx + 1} von {self._total_photos}",
                      36, (255, 255, 255), h - 80)
        elif self._phase == _Phase.COUNTDOWN:
            remaining = max(1, countdown_n - int(self._elapsed()))
            draw_text(str(remaining), FONT_HUGE, (255, 255, 255), cy)
        elif self._phase == _Phase.SMILE:
            draw_text("Lächeln!", FONT_LARGE, (255, 230, 0), cy)
        elif self._phase == _Phase.POST:
            draw_text(f"Foto {self._photo_idx + 1} von {self._total_photos} aufgenommen",
                      36, (200, 255, 200), h - 80)

    # ------------------------------------------------------------------

    def _do_capture(self):
        frame = self.app.camera.capture_photo()

        try:
            path = self.app.storage.save_photo(frame, self._photo_idx)
        except IOError as e:
            self.app.show_notification(str(e), duration=8.0, level="error")
            import tempfile
            from PIL import Image as _Img
            tmp = Path(tempfile.mktemp(suffix=".jpg"))
            _Img.fromarray(frame, "RGB").save(tmp, "JPEG", quality=95)
            path = tmp

        self.app.context.captured_photos.append(path)

        click = self.app.config.settings.get("system_sounds", {}).get("shutter_click", "")
        if click:
            self.app.audio.play_sfx(self.app.config.resolve_asset(click))
