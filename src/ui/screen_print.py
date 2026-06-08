"""
Print screen – shows the collage with a loading bar for the print duration (default 40 s).
Sends the collage to the printer in a background thread and returns to start when done.
"""
import logging
import threading
import time
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPainter, QColor, QFont, QPixmap
from PyQt6.QtWidgets import QProgressBar

from .base_screen import BaseScreen
from ..constants import COLOR_BG, FONT_SMALL, SCENE_PRINT_DURATION

logger = logging.getLogger(__name__)

_BAR_STYLE = """
QProgressBar {{ border: 2px solid #333; border-radius: 5px; background: #282828; height: 24px; }}
QProgressBar::chunk {{ background: {color}; border-radius: 3px; }}
"""


class PrintScreen(BaseScreen):
    def __init__(self, app):
        super().__init__(app)
        self._scene: dict | None = None
        self._duration = float(SCENE_PRINT_DURATION)
        self._collage_pixmap: QPixmap | None = None
        self._bg_pixmap: QPixmap | None = None
        self._scaled_bg: QPixmap | None = None
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
        self._print_sent = False
        self._collage_pixmap = None

        scene_id = ctx.print_scene_id()
        self._scene = self.app.config.get_scene_by_id(scene_id) if scene_id else None
        self._duration = float(self._scene.get("duration", SCENE_PRINT_DURATION)) \
            if self._scene else float(SCENE_PRINT_DURATION)

        self._load_collage()
        self._load_bg()

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
        super().resizeEvent(event)
        self._scaled_bg = None
        self._position_progress()

    def _position_progress(self):
        w, h = self.width(), self.height()
        bar_w = int(w * 0.66)
        self._progress.setGeometry((w - bar_w) // 2, h - 110, bar_w, 28)

    def paintEvent(self, event):
        painter = QPainter(self)
        w, h = self.width(), self.height()

        if self._bg_pixmap:
            if self._scaled_bg is None or self._scaled_bg.size() != self.size():
                self._scaled_bg = self._scaled_cover(self._bg_pixmap, w, h)
            painter.drawPixmap((w - self._scaled_bg.width()) // 2,
                               (h - self._scaled_bg.height()) // 2, self._scaled_bg)
        else:
            painter.fillRect(self.rect(), QColor(*COLOR_BG))

        if self._collage_pixmap:
            max_w = int(w * 0.80)
            max_h = int(h * 0.70)
            scaled = self._collage_pixmap.scaled(
                max_w, max_h, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            painter.drawPixmap((w - scaled.width()) // 2,
                               (h - scaled.height()) // 2 - 40, scaled)

        font = QFont("DejaVu Sans", FONT_SMALL)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(0, 0, 0))
        painter.drawText(2, h - 68 + 2, w, 40, Qt.AlignmentFlag.AlignHCenter, "Dein Foto wird gedruckt…")
        painter.setPen(QColor(230, 230, 230))
        painter.drawText(0, h - 68, w, 40, Qt.AlignmentFlag.AlignHCenter, "Dein Foto wird gedruckt…")
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

    def _load_bg(self):
        self._bg_pixmap = None
        self._scaled_bg = None
        if self._scene and self._scene.get("media_type") == "photo":
            self._bg_pixmap = self._load_pixmap(self._scene.get("image", ""))

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
                    duration=10.0, level="error"
                )

        threading.Thread(target=do_print, daemon=True).start()
