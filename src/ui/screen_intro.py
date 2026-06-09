"""
Intro / greeting screen – plays the greeting scene (image+audio or video).
Auto-advances after the scene duration (clamped to the configured
greeting min/max from the admin settings).
"""
from __future__ import annotations

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QPainter

from .base_screen import BaseScreen
from .video_widget import VlcVideoFrame

NO_SCENE_PAUSE_S = 3.0


class IntroScreen(BaseScreen):
    def __init__(self, app):
        super().__init__(app)
        self._scene: dict | None = None

        self._video = VlcVideoFrame(self)
        self._video.playback_failed.connect(self._on_video_failed)

        self._duration_timer = QTimer(self)
        self._duration_timer.setSingleShot(True)
        self._duration_timer.timeout.connect(self._finish)

    # ------------------------------------------------------------------

    def on_enter(self):
        scene_id = self.app.context.greeting_scene_id()
        self._scene = self.app.config.get_scene_by_id(scene_id) if scene_id else None

        if self._scene:
            lo, hi = self.app.config.scene_duration_limits("greeting")
            duration = max(lo, min(float(self._scene.get("duration", lo)), hi))
            self._setup_media()
        else:
            duration = NO_SCENE_PAUSE_S
        self._duration_timer.start(int(duration * 1000))

    def on_exit(self):
        self._duration_timer.stop()
        self.app.audio.stop_music()
        self._video.stop()

    # ------------------------------------------------------------------

    def _finish(self):
        ctx = self.app.context
        if ctx.capture_count() > 0:
            self.transition_to("capture")
        else:
            ctx.current_path = None
            self.transition_to("start")

    def resizeEvent(self, event):
        self._video.setGeometry(self.rect())
        super().resizeEvent(event)

    def paintEvent(self, event):
        if self._video.isVisible():
            return  # VLC paints directly into the video frame
        painter = QPainter(self)
        self._paint_background(painter)
        painter.end()

    # ------------------------------------------------------------------

    def _setup_media(self):
        if self._scene.get("media_type") == "video":
            video_path = self.app.config.resolve_asset(self._scene.get("video", ""))
            self._video.setGeometry(self.rect())
            if video_path.exists() and self._video.play(video_path):
                return
        self._load_image_and_audio()

    def _load_image_and_audio(self):
        self._set_background(self._load_pixmap(self._scene.get("image", "")))
        self._start_scene_music(self._scene)

    def _on_video_failed(self):
        if self._scene:
            self._set_background(self._load_pixmap(self._scene.get("image", "")))
        self.update()
