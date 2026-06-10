"""
Collage screen – cycles through the captured photos while the collage is
assembled in a background thread, then hands off to the print screen.

Timing: the screen runs for the fixed duration configured in the admin
settings ("Zeiten" tab); each photo is shown for (duration / n_photos)
seconds. The scene audio starts with the screen and plays once to the end –
afterwards there is silence for the rest of the duration. If the worker is
still busy when the slideshow ends, the slideshow continues until the
collage is ready. The finished collage is shown on the print screen.
"""
from __future__ import annotations

import logging
import threading
import time

from PyQt6.QtCore import Qt, QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QPainter, QPixmap
from PyQt6.QtWidgets import QProgressBar

from ..constants import FONT_MEDIUM, MEDIA_PANEL_RECT, SCENE_DURATION_DEFAULTS
from . import theme
from .base_screen import BaseScreen
from .widgets import draw_shadow_text

logger = logging.getLogger(__name__)


class _CollageWorker(QObject):
    """Signal bridge: the worker thread emits, the GUI thread receives."""
    done = pyqtSignal(object, bool)   # (PIL.Image | None, error: bool)


class CollageScreen(BaseScreen):
    def __init__(self, app):
        super().__init__(app)
        self._scene: dict | None = None
        self._duration = float(SCENE_DURATION_DEFAULTS["collage"])

        # Slideshow state
        self._slide_pixmaps: list[QPixmap] = []
        self._slide_idx = 0
        self._slide_dur = 1.0            # seconds per photo
        self._last_slide_switch = 0.0

        # Collage worker state
        self._collage_result = None
        self._collage_done = False
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
        cfg = self.app.config
        self._collage_result = None
        self._collage_done = False
        self._saved = False
        self._slide_idx = 0

        scene_id = ctx.collage_scene_id()
        self._scene = cfg.get_scene_by_id(scene_id) if scene_id else None
        self._duration = cfg.scene_durations()["collage"]

        self._build_slideshow()
        if self._scene:
            self._set_background(self._load_pixmap(self._scene.get("image", "")))
        else:
            self._set_background(None)
        self._slide_dur = self._duration / max(1, len(self._slide_pixmaps))
        self._start_scene_music(self._scene)

        self._progress.setStyleSheet(theme.progress_bar_style(
            cfg.settings.get("loading_bar_color", "#FF6600")))
        self._progress.setValue(0)
        self._position_progress()
        self._progress.setVisible(cfg.settings.get("progress_bar_enabled", True))
        self._progress.raise_()

        threading.Thread(target=self._create_collage, daemon=True).start()

        self._start_time = time.monotonic()
        self._last_slide_switch = self._start_time
        self._timer.start()

    def on_exit(self):
        self._timer.stop()
        self.app.audio.stop_music()

    # ------------------------------------------------------------------

    def _tick(self):
        now = time.monotonic()
        elapsed = now - self._start_time

        slide_changed = False
        if self._slide_pixmaps and now - self._last_slide_switch >= self._slide_dur:
            self._last_slide_switch = now
            self._slide_idx = (self._slide_idx + 1) % len(self._slide_pixmaps)
            slide_changed = True

        # The bar tracks the slideshow window; it repaints itself.
        self._progress.setValue(int(min(1.0, elapsed / self._duration) * 100))

        if elapsed >= self._duration and self._collage_done:
            self._save_and_transition()
            return

        if slide_changed:
            self.update()

    # ------------------------------------------------------------------

    def resizeEvent(self, event):
        self._position_progress()
        super().resizeEvent(event)

    def _position_progress(self):
        self._position_progress_bar(self._progress)

    def paintEvent(self, event):
        painter = QPainter(self)
        w, h = self.width(), self.height()

        self._paint_background(painter)
        if self._slide_pixmaps:
            self._draw_cover_in_rect(painter, self._slide_pixmaps[self._slide_idx],
                                     self._design_rect(*MEDIA_PANEL_RECT))
        else:
            # No photos – edge case
            draw_shadow_text(painter, 0, -80, w, h, "Collage wird erstellt…",
                             FONT_MEDIUM, (255, 255, 255),
                             align=Qt.AlignmentFlag.AlignCenter, offset=3)
        painter.end()

    # ------------------------------------------------------------------

    def _build_slideshow(self):
        self._slide_pixmaps = []
        for path in self.app.context.captured_photos:
            pix = QPixmap(str(path))
            if not pix.isNull():
                self._slide_pixmaps.append(pix)

    def _create_collage(self):
        """Runs in a background thread; reports back via the worker signal."""
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
