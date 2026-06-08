"""
Start screen – waiting for the user to press the start button.
Ready LED is ON while this screen is active.

Background: VLC video loop (in a QFrame) OR a static image painted via QPainter.
Prompt text "Drücke den Startknopf" pulses via a QTimer.
"""
import math

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPainter, QColor, QFont, QPixmap
from PyQt6.QtWidgets import QFrame

from .base_screen import BaseScreen
from ..constants import COLOR_BG, FONT_SMALL

try:
    import vlc as _vlc
    _VLC = True
except ImportError:
    _VLC = False


class StartScreen(BaseScreen):
    def __init__(self, app):
        super().__init__(app)
        self._bg_pixmap: QPixmap | None = None
        self._scaled_bg: QPixmap | None = None

        # VLC video background
        self._video_frame = QFrame(self)
        self._video_frame.setStyleSheet("background: black;")
        self._video_frame.hide()
        self._vlc_instance = None
        self._vlc_player = None

        self._pulse_t = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tick)

    # ------------------------------------------------------------------

    def on_enter(self):
        self.app.gpio.set_ready_led(True)
        self._pulse_t = 0.0
        self._load_background()
        self._timer.start()

    def on_exit(self):
        self.app.gpio.set_ready_led(False)
        self._timer.stop()
        self._stop_video()

    # ------------------------------------------------------------------

    def _tick(self):
        self._pulse_t += 0.05
        self.update()  # trigger repaint for pulsing text

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._video_frame.setGeometry(self.rect())
        self._scaled_bg = None  # invalidate cache

    def paintEvent(self, event):
        painter = QPainter(self)
        w, h = self.width(), self.height()

        if self._video_frame.isVisible():
            # VLC paints into the frame; just draw the bottom bar + text.
            pass
        elif self._bg_pixmap:
            if self._scaled_bg is None or self._scaled_bg.size() != self.size():
                self._scaled_bg = self._scaled_cover(self._bg_pixmap, w, h)
            x = (w - self._scaled_bg.width()) // 2
            y = (h - self._scaled_bg.height()) // 2
            painter.drawPixmap(x, y, self._scaled_bg)
        else:
            painter.fillRect(self.rect(), QColor(*COLOR_BG))

        # Semi-transparent bottom bar
        bar_h = int(h * 0.16)
        painter.fillRect(0, h - bar_h, w, bar_h, QColor(0, 0, 0, 160))

        # Pulsing prompt text
        alpha = int(180 + 75 * math.sin(self._pulse_t * 2.5))
        alpha = max(0, min(255, alpha))
        font = QFont("DejaVu Sans", FONT_SMALL + 4)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255, alpha))
        painter.drawText(
            0, h - bar_h, w, bar_h,
            Qt.AlignmentFlag.AlignCenter,
            "Drücke den Startknopf",
        )
        painter.end()

    # ------------------------------------------------------------------

    def _load_background(self):
        self._stop_video()
        self._bg_pixmap = None
        self._scaled_bg = None

        bg = self.app.config.settings.get("idle_background", {})
        bg_type = bg.get("type", "image")
        bg_file = bg.get("file", "")
        if not bg_file:
            return
        path = self.app.config.resolve_asset(bg_file)
        if not path.exists():
            return

        if bg_type == "video" and _VLC:
            try:
                self._vlc_instance = _vlc.Instance("--no-xlib", "--quiet")
                media = self._vlc_instance.media_new(str(path))
                media.add_option("input-repeat=65535")
                self._vlc_player = self._vlc_instance.media_player_new()
                self._vlc_player.set_media(media)
                self._vlc_player.audio_set_mute(True)
                self._video_frame.setGeometry(self.rect())
                self._video_frame.show()
                self._video_frame.lower()
                QTimer.singleShot(0, self._attach_and_play_video)
                return
            except Exception:
                self._stop_video()

        # Fallback: static image
        pix = QPixmap(str(path))
        if not pix.isNull():
            self._bg_pixmap = pix

    def _attach_and_play_video(self):
        if not self._vlc_player:
            return
        try:
            import sys
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

    def _stop_video(self):
        if self._vlc_player is not None:
            try:
                self._vlc_player.stop()
            except Exception:
                pass
            self._vlc_player = None
        self._vlc_instance = None
        self._video_frame.hide()
