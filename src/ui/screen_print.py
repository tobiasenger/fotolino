"""
Print screen – shows the collage with a loading bar for the print duration.
The screen runs for the fixed duration configured in the admin settings
("Zeiten" tab); the scene audio starts with the screen and plays once to
the end, followed by silence. Sends the collage to the printer in a
background thread and returns to the start screen when the duration has
elapsed.
"""
from __future__ import annotations

import logging
import time

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QPainter, QPixmap

from ..constants import MEDIA_PANEL_RECT, SCENE_DURATION_DEFAULTS
from .base_screen import BaseScreen

logger = logging.getLogger(__name__)


class PrintScreen(BaseScreen):
    def __init__(self, app):
        super().__init__(app)
        self._scene: dict | None = None
        self._duration = float(SCENE_DURATION_DEFAULTS["print"])
        self._collage_pixmap: QPixmap | None = None
        self._print_sent = False
        self._start_time = 0.0

        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tick)

        self._progress = self._make_progress_bar()

    # ------------------------------------------------------------------

    def on_enter(self):
        ctx = self.app.context
        cfg = self.app.config
        self._print_sent = False
        self._collage_pixmap = None

        scene_id = ctx.print_scene_id()
        self._scene = cfg.get_scene_by_id(scene_id) if scene_id else None
        self._duration = cfg.scene_durations()["print"]

        self._load_collage()
        if self._scene:
            self._set_background(self._load_pixmap(self._scene.get("image", "")))
        else:
            self._set_background(None)
        self._apply_screen_overlay("print")
        self._start_scene_music(self._scene)

        self._reset_progress_bar(self._progress)

        self._send_print()
        self._start_time = time.monotonic()
        self._timer.start()

    def on_exit(self):
        self._timer.stop()
        self.app.audio.stop_music()
        self.app.context.end_session()

    # ------------------------------------------------------------------

    def _tick(self):
        elapsed = time.monotonic() - self._start_time
        self._progress.setValue(int(min(1.0, elapsed / self._duration) * 100))
        if elapsed >= self._duration:
            self.transition_to("start")

    def resizeEvent(self, event):
        self._position_progress_bar(self._progress)
        super().resizeEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        self._paint_background(painter)
        if self._collage_pixmap:
            self._draw_cover_in_rect(painter, self._collage_pixmap,
                                     self._design_rect(*MEDIA_PANEL_RECT))
        self._paint_overlay(painter)
        painter.end()

    # ------------------------------------------------------------------

    def _load_collage(self):
        path = self.app.context.collage_path
        if not path:
            return
        pix = QPixmap(str(path))
        if not pix.isNull():
            self._collage_pixmap = pix
        else:
            logger.warning("Collage %s kann nicht angezeigt werden (Datei defekt "
                           "oder nicht lesbar) – Druck wird trotzdem versucht.", path)

    def _send_print(self):
        if self._print_sent:
            return
        self._print_sent = True
        path = self.app.context.collage_path
        if not path:
            self.app.show_notification(
                "Druckfehler: Keine Collage-Datei vorhanden.", level="error")
            return
        self._print_collage_file(path)
