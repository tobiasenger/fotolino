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
import threading
import time
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPainter, QPixmap
from PyQt6.QtWidgets import QProgressBar

from ..constants import FONT_SMALL, MEDIA_PANEL_RECT, SCENE_DURATION_DEFAULTS
from . import theme
from .base_screen import BaseScreen
from .widgets import draw_shadow_text

logger = logging.getLogger(__name__)

STATUS_TEXT = "Dein Foto wird gedruckt…"


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

        self._progress = QProgressBar(self)
        self._progress.setRange(0, 100)
        self._progress.setTextVisible(False)

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
        self._start_scene_music(self._scene)

        self._progress.setStyleSheet(theme.progress_bar_style(
            cfg.settings.get("loading_bar_color", "#FF6600")))
        self._progress.setValue(0)
        self._position_progress()
        self._progress.setVisible(cfg.settings.get("progress_bar_enabled", True))
        self._progress.raise_()

        self._send_print()
        self._start_time = time.monotonic()
        self._timer.start()

    def on_exit(self):
        self._timer.stop()
        self.app.audio.stop_music()
        self.app.context.current_path = None
        self.app.context.captured_photos = []
        self.app.context.collage_path = None

    # ------------------------------------------------------------------

    def _tick(self):
        elapsed = time.monotonic() - self._start_time
        self._progress.setValue(int(min(1.0, elapsed / self._duration) * 100))
        if elapsed >= self._duration:
            self.transition_to("start")

    def resizeEvent(self, event):
        self._position_progress()
        super().resizeEvent(event)

    def _position_progress(self):
        self._position_progress_bar(self._progress)

    def paintEvent(self, event):
        painter = QPainter(self)
        w = self.width()

        self._paint_background(painter)

        if self._collage_pixmap:
            self._draw_cover_in_rect(painter, self._collage_pixmap,
                                     self._design_rect(*MEDIA_PANEL_RECT))

        # Keep the status text above the full-width bar at the bottom edge.
        draw_shadow_text(painter, 0, self._progress.y() - 56, w, 40, STATUS_TEXT,
                         FONT_SMALL, (230, 230, 230),
                         align=Qt.AlignmentFlag.AlignHCenter)
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

        def do_print():
            success = self.app.printer.print_collage(Path(path))
            if not success and not self.app.printer.is_demo():
                self.app.show_notification(
                    "Druck fehlgeschlagen – Details in fotobox.log. "
                    "Drucker, Papier und CUPS-Status prüfen.",
                    duration=10.0, level="error",
                )

        threading.Thread(target=do_print, daemon=True).start()
