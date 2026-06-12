"""
Start screen – idle/attract mode waiting for the start button.
Ready LED is ON while this screen is active.

Background: looping muted VLC video OR a static image, optionally with a
PNG/GIF overlay on top (admin menu, "Darstellung" tab). With a video
background the overlay is not visible – VLC renders into a native window
that covers everything painted on this widget.
"""
from __future__ import annotations

from PyQt6.QtGui import QPainter

from .base_screen import BaseScreen
from .video_widget import VlcVideoFrame


class StartScreen(BaseScreen):
    def __init__(self, app):
        super().__init__(app)
        self._video = VlcVideoFrame(self)
        self._video.playback_failed.connect(self._on_video_failed)

    # ------------------------------------------------------------------

    def on_enter(self):
        self.app.gpio.set_ready_led(True)
        self._load_background_media()
        self._apply_screen_overlay("start")

    def on_exit(self):
        self.app.gpio.set_ready_led(False)
        self._video.stop()

    # ------------------------------------------------------------------

    def resizeEvent(self, event):
        self._video.setGeometry(self.rect())
        super().resizeEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        if not self._video.isVisible():
            self._paint_background(painter)
        self._paint_overlay(painter)
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
