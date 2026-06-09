"""
Camera test screen – live preview with "Testfoto" and "Zurück" buttons.
Reachable from admin settings (Gerät tab). Polls camera.get_qpixmap() via a
QTimer; QGlPicamera2 is intentionally not used – see screen_capture.py.
"""
from __future__ import annotations

import logging

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QColor, QPainter, QPixmap
from PyQt6.QtWidgets import QPushButton

from . import theme
from .base_screen import BaseScreen

logger = logging.getLogger(__name__)


class CameraTestScreen(BaseScreen):
    def __init__(self, app):
        super().__init__(app)
        self._preview_pixmap: QPixmap | None = None
        self._status = ""

        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tick)

        self._back_btn = QPushButton("Zurück", self)
        self._back_btn.setStyleSheet(theme.LARGE_BTN_STYLE)
        self._back_btn.clicked.connect(lambda: self.transition_to("admin"))

        self._test_btn = QPushButton("Testfoto", self)
        self._test_btn.setStyleSheet(theme.LARGE_BTN_STYLE)
        self._test_btn.clicked.connect(self._on_testfoto)

    # ------------------------------------------------------------------

    def on_enter(self):
        self._status = ""
        self.app.camera.start()
        self._position_buttons()
        if not self.app.camera.is_connected():
            self._status = "Kamera nicht verfügbar – Testbild wird angezeigt."
        self._timer.start()

    def on_exit(self):
        self._timer.stop()
        self.app.camera.stop()

    # ------------------------------------------------------------------

    def resizeEvent(self, event):
        self._position_buttons()
        super().resizeEvent(event)

    def _position_buttons(self):
        w, h = self.width(), self.height()
        self._back_btn.setGeometry(20, h - 70, 160, 50)
        self._test_btn.setGeometry(w - 200, h - 70, 180, 50)

    # ------------------------------------------------------------------

    def _tick(self):
        try:
            self._preview_pixmap = self.app.camera.get_qpixmap(mirror=True)
        except Exception:
            self._preview_pixmap = None
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        if self._preview_pixmap:
            self._draw_cover(painter, self._preview_pixmap, fast=True)
        else:
            self._paint_background(painter)
        if self._status:
            painter.setPen(QColor(255, 190, 0))
            painter.drawText(20, 40, self._status)
        painter.end()

    # ------------------------------------------------------------------

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
