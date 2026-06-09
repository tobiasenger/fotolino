"""
Print screen – shows the collage with a loading bar for the print duration.
Sends the collage to the printer in a background thread and returns to the
start screen when the duration has elapsed.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPainter, QPixmap
from PyQt6.QtWidgets import QProgressBar

from ..constants import FONT_SMALL, SCENE_PRINT_DURATION
from . import theme
from .base_screen import BaseScreen
from .widgets import draw_shadow_text

logger = logging.getLogger(__name__)

STATUS_TEXT = "Dein Foto wird gedruckt…"


class PrintScreen(BaseScreen):
    def __init__(self, app):
        super().__init__(app)
        self._scene: dict | None = None
        self._duration = float(SCENE_PRINT_DURATION)
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
        self._duration = float(self._scene.get("duration", SCENE_PRINT_DURATION)) \
            if self._scene else float(SCENE_PRINT_DURATION)

        self._load_collage()
        if self._scene and self._scene.get("media_type") == "photo":
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
        w, h = self.width(), self.height()
        bar_w = int(w * 0.66)
        self._progress.setGeometry((w - bar_w) // 2, h - 110, bar_w, 28)

    def paintEvent(self, event):
        painter = QPainter(self)
        w, h = self.width(), self.height()

        self._paint_background(painter)

        if self._collage_pixmap:
            scaled = self._collage_pixmap.scaled(
                int(w * 0.80), int(h * 0.70),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            painter.drawPixmap((w - scaled.width()) // 2,
                               (h - scaled.height()) // 2 - 40, scaled)

        draw_shadow_text(painter, 0, h - 68, w, 40, STATUS_TEXT,
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
            logger.warning("Cannot load collage for display: %s", path)

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
                    "Druckfehler: Drucker nicht erreichbar. "
                    "Verbindung, Papier und CUPS-Status prüfen.",
                    duration=10.0, level="error",
                )

        threading.Thread(target=do_print, daemon=True).start()
