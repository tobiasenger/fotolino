"""
Collage screen – cycles through the captured photos for 10 s while the
collage is assembled in the background, then hands off to the print screen.

Timing: each photo is shown for (total_duration / n_photos) seconds.
The finished collage is shown on the print screen, NOT here.
"""
import logging
import threading
import time

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QPainter, QColor, QFont, QPixmap
from PyQt6.QtWidgets import QProgressBar

from .base_screen import BaseScreen
from ..constants import COLOR_BG, FONT_MEDIUM, SCENE_COLLAGE_DURATION

logger = logging.getLogger(__name__)

_BAR_STYLE = """
QProgressBar {{ border: 2px solid #333; border-radius: 5px; background: #282828; height: 24px; }}
QProgressBar::chunk {{ background: {color}; border-radius: 3px; }}
"""


class _CollageWorker(QObject):
    done = pyqtSignal(object, bool)   # (PIL.Image | None, error: bool)


class CollageScreen(BaseScreen):
    def __init__(self, app):
        super().__init__(app)
        self._scene: dict | None = None
        self._duration = float(SCENE_COLLAGE_DURATION)

        self._bg_pixmap: QPixmap | None = None
        self._scaled_bg: QPixmap | None = None

        # Slideshow state
        self._slide_pixmaps: list[QPixmap] = []
        self._slide_idx = 0
        self._slide_dur = 1.0           # seconds per photo
        self._last_slide_switch = 0.0

        # Collage worker state
        self._collage_result = None     # PIL.Image delivered by worker
        self._collage_done = False
        self._collage_error = False
        self._saved = False

        self._worker = _CollageWorker()
        self._worker.done.connect(self._on_collage_done)

        self._start_time = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tick)

        self._progress = QProgressBar(self)
        self._progress.setRange(0, 100)
        self._progress.setTextVisible(False)

    # ------------------------------------------------------------------

    def on_enter(self):
        ctx = self.app.context
        self._collage_result = None
        self._collage_done = False
        self._collage_error = False
        self._saved = False
        self._slide_idx = 0

        scene_id = ctx.collage_scene_id()
        self._scene = self.app.config.get_scene_by_id(scene_id) if scene_id else None
        self._duration = float(self._scene.get("duration", SCENE_COLLAGE_DURATION)) \
            if self._scene else float(SCENE_COLLAGE_DURATION)

        self._build_slideshow()
        self._load_bg()

        n = len(self._slide_pixmaps)
        self._slide_dur = self._duration / max(1, n)

        if self._scene and self._scene.get("media_type") == "photo":
            audio = self._scene.get("audio", "")
            if audio:
                p = self.app.config.resolve_asset(audio)
                if p.exists():
                    self.app.audio.play_music(p)

        color = self.app.config.settings.get("loading_bar_color", "#FF6600")
        self._progress.setStyleSheet(_BAR_STYLE.format(color=color))
        self._progress.setValue(0)
        self._position_progress()
        self._progress.show()
        self._progress.raise_()

        threading.Thread(target=self._create_collage, daemon=True).start()

        self._start_time = time.monotonic()
        self._last_slide_switch = self._start_time
        self._timer.start()

    def on_exit(self):
        self._timer.stop()
        self.app.audio.stop_music()

    # ------------------------------------------------------------------

    def _elapsed(self) -> float:
        return time.monotonic() - self._start_time

    def _tick(self):
        elapsed = self._elapsed()
        now = time.monotonic()

        # Advance slideshow
        if self._slide_pixmaps and now - self._last_slide_switch >= self._slide_dur:
            self._last_slide_switch = now
            self._slide_idx = (self._slide_idx + 1) % len(self._slide_pixmaps)

        # Progress bar tracks the 10-second slideshow window
        self._progress.setValue(int(min(1.0, elapsed / self._duration) * 100))

        if elapsed >= self._duration:
            if not self._collage_done:
                # Slideshow continues while we wait for the worker
                self.update()
                return
            self._save_and_transition()
            return

        self.update()

    # ------------------------------------------------------------------

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._scaled_bg = None
        self._position_progress()

    def _position_progress(self):
        w, h = self.width(), self.height()
        bar_w = int(w * 0.6)
        self._progress.setGeometry((w - bar_w) // 2, h - 70, bar_w, 28)

    def paintEvent(self, event):
        painter = QPainter(self)
        w, h = self.width(), self.height()

        if self._slide_pixmaps:
            pix = self._slide_pixmaps[self._slide_idx]
            scaled = self._scaled_cover(pix, w, h)
            painter.drawPixmap((w - scaled.width()) // 2,
                               (h - scaled.height()) // 2, scaled)
            # Subtle dim so the photo isn't too raw
            painter.fillRect(self.rect(), QColor(0, 0, 0, 60))
        else:
            # No photos – edge case
            if self._bg_pixmap:
                if self._scaled_bg is None or self._scaled_bg.size() != self.size():
                    self._scaled_bg = self._scaled_cover(self._bg_pixmap, w, h)
                painter.drawPixmap((w - self._scaled_bg.width()) // 2,
                                   (h - self._scaled_bg.height()) // 2, self._scaled_bg)
            else:
                painter.fillRect(self.rect(), QColor(*COLOR_BG))
            font = QFont("DejaVu Sans", FONT_MEDIUM)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor(0, 0, 0))
            painter.drawText(3, 3 - 80, w, h, Qt.AlignmentFlag.AlignCenter, "Collage wird erstellt…")
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(0, -80, w, h, Qt.AlignmentFlag.AlignCenter, "Collage wird erstellt…")

        painter.end()

    # ------------------------------------------------------------------

    def _build_slideshow(self):
        self._slide_pixmaps = []
        for path in self.app.context.captured_photos:
            pix = QPixmap(str(path))
            if not pix.isNull():
                self._slide_pixmaps.append(pix)

    def _load_bg(self):
        self._bg_pixmap = None
        self._scaled_bg = None
        if self._scene and self._scene.get("media_type") == "photo":
            self._bg_pixmap = self._load_pixmap(self._scene.get("image", ""))

    def _create_collage(self):
        result = None
        error = False
        try:
            photos = self.app.context.captured_photos
            count = self.app.context.capture_count()
            result = self.app.collage_creator.create(photos, count)
        except Exception as e:
            logger.error("Collage creation failed: %s", e)
            error = True
        self._worker.done.emit(result, error)

    def _on_collage_done(self, result, error):
        self._collage_result = result
        self._collage_done = True
        self._collage_error = error
        if error or result is None:
            logger.warning("Collage worker reported failure")

    def _save_and_transition(self):
        if self._saved:
            return
        self._saved = True
        if self._collage_result is not None:
            try:
                path = self.app.storage.save_collage(self._collage_result)
                self.app.context.collage_path = str(path)
            except IOError as e:
                self.app.show_notification(str(e), duration=8.0, level="error")
        self.transition_to("print")
