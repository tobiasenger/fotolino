"""
Camera test screen – live preview with a "Testfoto" button and "Zurück" button.
Reachable from the admin settings (device tab). Uses QGlPicamera2 if available,
otherwise polls camera.get_qpixmap().
"""
import logging

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPainter, QColor, QPixmap
from PyQt6.QtWidgets import QPushButton

from .base_screen import BaseScreen

logger = logging.getLogger(__name__)

try:
    from picamera2.previews.qt import QGlPicamera2
    _QGL = True
except Exception:
    _QGL = False

_BTN_STYLE = (
    "QPushButton { background: #2a2a50; color: white; border: 2px solid #444488; "
    "border-radius: 6px; padding: 10px 20px; font-size: 20px; } "
    "QPushButton:hover { border-color: #ff6600; }"
)


class CameraTestScreen(BaseScreen):
    def __init__(self, app):
        super().__init__(app)
        self._preview_pixmap: QPixmap | None = None
        self._qgl = None
        self._tried_qgl = False
        self._status = ""

        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tick)

        self._back_btn = QPushButton("Zurück", self)
        self._back_btn.setStyleSheet(_BTN_STYLE)
        self._back_btn.clicked.connect(self._on_back)

        self._test_btn = QPushButton("Testfoto", self)
        self._test_btn.setStyleSheet(_BTN_STYLE)
        self._test_btn.clicked.connect(self._on_testfoto)

    # ------------------------------------------------------------------

    def on_enter(self):
        self._status = ""
        self._setup_preview()   # register QGlPicamera2 BEFORE camera starts streaming
        self.app.camera.start()
        self._position_buttons()
        self._back_btn.show()
        self._test_btn.show()
        if not self.app.camera.is_connected():
            self._status = "Kamera nicht verfügbar – Testbild wird angezeigt."
        self._timer.start()

    def on_exit(self):
        self._timer.stop()
        self._teardown_preview()
        self.app.camera.stop()

    # ------------------------------------------------------------------

    def _setup_preview(self):
        self._preview_pixmap = None
        if _QGL and self.app.camera.is_connected() and not self._tried_qgl:
            self._tried_qgl = True
            try:
                self._qgl = QGlPicamera2(
                    self.app.camera.picam2, width=self.width() or 1280,
                    height=self.height() or 720, keep_ar=True)
                self._qgl.setParent(self)
                self._qgl.setGeometry(self.rect())
                self._qgl.show()
                self._qgl.lower()
            except Exception as e:
                logger.warning("QGlPicamera2 failed (%s) – using polling", e)
                self._qgl = None

    def _teardown_preview(self):
        if self._qgl is not None:
            try:
                self._qgl.hide()
                self._qgl.setParent(None)
                self._qgl.deleteLater()
            except Exception:
                pass
            self._qgl = None
            self._tried_qgl = False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._qgl is not None:
            self._qgl.setGeometry(self.rect())
        self._position_buttons()

    def _position_buttons(self):
        w, h = self.width(), self.height()
        self._back_btn.setGeometry(20, h - 70, 160, 50)
        self._test_btn.setGeometry(w - 200, h - 70, 180, 50)

    # ------------------------------------------------------------------

    def _tick(self):
        if self._qgl is None:
            try:
                self._preview_pixmap = self.app.camera.get_qpixmap(mirror=True)
            except Exception:
                self._preview_pixmap = None
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        w, h = self.width(), self.height()
        if self._qgl is None:
            if self._preview_pixmap:
                scaled = self._scaled_cover(self._preview_pixmap, w, h)
                painter.drawPixmap((w - scaled.width()) // 2,
                                   (h - scaled.height()) // 2, scaled)
            else:
                painter.fillRect(self.rect(), QColor(10, 10, 20))
        if self._status:
            painter.setPen(QColor(255, 190, 0))
            painter.drawText(20, 40, self._status)
        painter.end()

    # ------------------------------------------------------------------

    def _on_back(self):
        self.transition_to("admin")

    def _on_testfoto(self):
        try:
            frame = self.app.camera.capture_photo()
            path = self.app.storage.save_photo(frame, 0)
            self._status = f"Testfoto gespeichert: {path}"
        except IOError as e:
            self._status = f"Fehler: {e}"
        except Exception as e:
            self._status = f"Fehler beim Testfoto: {e}"
        self.update()
