"""
Intro / greeting screen – plays the greeting scene (image+audio or video).
Auto-advances after the scene duration (capped at SCENE_GREETING_MAX).
"""
import sys

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPainter, QColor, QPixmap
from PyQt6.QtWidgets import QFrame

from .base_screen import BaseScreen
from ..constants import COLOR_BG, SCENE_GREETING_MAX

try:
    import vlc as _vlc
    _VLC = True
except ImportError:
    _VLC = False


class IntroScreen(BaseScreen):
    def __init__(self, app):
        super().__init__(app)
        self._scene: dict | None = None
        self._bg_pixmap: QPixmap | None = None
        self._scaled_bg: QPixmap | None = None

        self._video_frame = QFrame(self)
        self._video_frame.setStyleSheet("background: black;")
        self._video_frame.hide()
        self._vlc_instance = None
        self._vlc_player = None

        self._duration_timer = QTimer(self)
        self._duration_timer.setSingleShot(True)
        self._duration_timer.timeout.connect(self._finish)

    # ------------------------------------------------------------------

    def on_enter(self):
        ctx = self.app.context
        scene_id = ctx.greeting_scene_id()
        self._scene = self.app.config.get_scene_by_id(scene_id) if scene_id else None

        if self._scene:
            duration = float(self._scene.get("duration", 5.0))
            duration = min(duration, SCENE_GREETING_MAX)
            self._setup_media()
        else:
            duration = 3.0  # no scene: short pause then continue
        self._duration_timer.start(int(duration * 1000))

    def on_exit(self):
        self._duration_timer.stop()
        self.app.audio.stop_music()
        self._stop_video()

    # ------------------------------------------------------------------

    def _finish(self):
        ctx = self.app.context
        if ctx.capture_count() > 0:
            self.transition_to("capture")
        else:
            ctx.current_path = None
            self.transition_to("start")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._video_frame.setGeometry(self.rect())
        self._scaled_bg = None

    def paintEvent(self, event):
        if self._video_frame.isVisible():
            return
        painter = QPainter(self)
        w, h = self.width(), self.height()
        if self._bg_pixmap:
            if self._scaled_bg is None or self._scaled_bg.size() != self.size():
                self._scaled_bg = self._scaled_cover(self._bg_pixmap, w, h)
            x = (w - self._scaled_bg.width()) // 2
            y = (h - self._scaled_bg.height()) // 2
            painter.drawPixmap(x, y, self._scaled_bg)
        else:
            painter.fillRect(self.rect(), QColor(*COLOR_BG))
        painter.end()

    # ------------------------------------------------------------------

    def _setup_media(self):
        if not self._scene:
            return
        media_type = self._scene.get("media_type", "photo")
        if media_type == "video":
            self._load_video()
        else:
            self._load_image_bg()
            audio_path = self._scene.get("audio", "")
            if audio_path:
                p = self.app.config.resolve_asset(audio_path)
                if p.exists():
                    self.app.audio.play_music(p)

    def _load_image_bg(self):
        self._bg_pixmap = self._load_pixmap(self._scene.get("image", "") if self._scene else "")
        self._scaled_bg = None

    def _load_video(self):
        if not self._scene or not _VLC:
            self._load_image_bg()
            return
        video_path = self._scene.get("video", "")
        p = self.app.config.resolve_asset(video_path)
        if not p.exists():
            self._load_image_bg()
            return
        try:
            self._vlc_instance = _vlc.Instance("--quiet")
            media = self._vlc_instance.media_new(str(p))
            self._vlc_player = self._vlc_instance.media_player_new()
            self._vlc_player.set_media(media)
            self._video_frame.setGeometry(self.rect())
            self._video_frame.show()
            QTimer.singleShot(200, self._attach_and_play_video)
        except Exception:
            self._stop_video()
            self._load_image_bg()

    def _attach_and_play_video(self):
        if not self._vlc_player:
            return
        try:
            wid = int(self._video_frame.winId())
            if sys.platform.startswith("linux"):
                self._vlc_player.set_xwindow(wid)
            elif sys.platform == "darwin":
                self._vlc_player.set_nsobject(wid)
            elif sys.platform == "win32":
                self._vlc_player.set_hwnd(wid)
            self._vlc_player.play()
        except Exception:
            self._stop_video()
            self._load_image_bg()

    def _stop_video(self):
        if self._vlc_player is not None:
            try:
                self._vlc_player.stop()
            except Exception:
                pass
            self._vlc_player = None
        self._vlc_instance = None
        self._video_frame.hide()
