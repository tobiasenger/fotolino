"""
Start screen – idle/attract mode waiting for the start button.
Ready LED is ON while this screen is active.

Background: looping muted VLC video OR a static image.
The prompt text pulses; only the bottom bar is repainted per tick to keep
CPU usage low on the Pi.
"""
from __future__ import annotations

import math

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QPainter

from ..constants import FONT_FAMILY, FONT_SMALL
from .base_screen import BaseScreen
from .video_widget import VlcVideoFrame

PROMPT_TEXT = "Drücke den Startknopf"
BAR_HEIGHT_RATIO = 0.16


class StartScreen(BaseScreen):
    def __init__(self, app):
        super().__init__(app)
        self._video = VlcVideoFrame(self)
        self._video.playback_failed.connect(self._on_video_failed)

        self._pulse_t = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tick)

    # ------------------------------------------------------------------

    def on_enter(self):
        self.app.gpio.set_ready_led(True)
        self._pulse_t = 0.0
        self._load_background_media()
        self._timer.start()

    def on_exit(self):
        self.app.gpio.set_ready_led(False)
        self._timer.stop()
        self._video.stop()

    # ------------------------------------------------------------------

    def _tick(self):
        self._pulse_t += 0.05
        bar_h = int(self.height() * BAR_HEIGHT_RATIO)
        self.update(0, self.height() - bar_h, self.width(), bar_h)

    def resizeEvent(self, event):
        self._video.setGeometry(self.rect())
        super().resizeEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        w, h = self.width(), self.height()

        if not self._video.isVisible():
            self._paint_background(painter)

        # Semi-transparent bottom bar with pulsing prompt text
        bar_h = int(h * BAR_HEIGHT_RATIO)
        painter.fillRect(0, h - bar_h, w, bar_h, QColor(0, 0, 0, 160))

        alpha = int(180 + 75 * math.sin(self._pulse_t * 2.5))
        font = QFont(FONT_FAMILY, FONT_SMALL + 4)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255, max(0, min(255, alpha))))
        painter.drawText(0, h - bar_h, w, bar_h,
                         Qt.AlignmentFlag.AlignCenter, PROMPT_TEXT)
        painter.end()

    # ------------------------------------------------------------------

    def _load_background_media(self):
        self._video.stop()
        self._set_background(None)

        bg = self.app.config.settings.get("idle_background", {})
        bg_file = bg.get("file", "")
        if not bg_file:
            return
        path = self.app.config.resolve_asset(bg_file)
        if not path.exists():
            return

        if bg.get("type") == "video":
            self._video.setGeometry(self.rect())
            if self._video.play(path, loop=True, muted=True):
                self._video.lower()
                return

        self._set_background(self._load_pixmap(bg_file))

    def _on_video_failed(self):
        bg_file = self.app.config.settings.get("idle_background", {}).get("file", "")
        self._set_background(self._load_pixmap(bg_file))
        self.update()
