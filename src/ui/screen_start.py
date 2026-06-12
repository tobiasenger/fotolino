"""
Start screen – idle/attract mode waiting for the start button.
Ready LED is ON while this screen is active.

Background: a static image, optionally with a PNG/GIF overlay on top
(admin menu, "Darstellung" tab). Video backgrounds are not supported:
VLC renders into a native window that would cover the overlay, and
muting it poisons the PulseAudio stream-restore state for all other
app sounds.
"""
from __future__ import annotations

import logging

from PyQt6.QtGui import QPainter

from .base_screen import BaseScreen

logger = logging.getLogger(__name__)


class StartScreen(BaseScreen):

    def on_enter(self):
        self.app.gpio.set_ready_led(True)
        self._load_background()
        self._apply_screen_overlay("start")

    def on_exit(self):
        self.app.gpio.set_ready_led(False)

    # ------------------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        self._paint_background(painter)
        self._paint_overlay(painter)
        painter.end()

    # ------------------------------------------------------------------

    def _load_background(self):
        bg = self.app.config.settings.get("idle_background", {})
        if bg.get("type") == "video":
            logger.warning(
                "Video-Hintergrund wird nicht mehr unterstützt – der "
                "Startbildschirm verwendet den Standardhintergrund. Bitte im "
                "Admin-Bereich (Darstellung) ein Bild auswählen.")
            self._set_background(None)
            return
        self._set_background(self._load_pixmap(bg.get("file", "")))
