"""
Base class for all application screens (PyQt6).

Each screen is a QWidget on the main QStackedWidget. Besides the
on_enter/on_exit lifecycle it provides the shared plumbing every screen
needs: cached full-screen background painting, cover-scaled pixmap drawing
and starting the music of an image+audio scene.
"""
from __future__ import annotations

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter, QPixmap
from PyQt6.QtWidgets import QWidget

from ..constants import COLOR_BG

logger = logging.getLogger(__name__)


class BaseScreen(QWidget):
    """Abstract base for all application screens."""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self._bg_pixmap: QPixmap | None = None
        self._bg_scaled: QPixmap | None = None   # cache, invalidated on resize

    # ------------------------------------------------------------------
    # Lifecycle hooks (override in subclasses)
    # ------------------------------------------------------------------

    def on_enter(self):
        pass

    def on_exit(self):
        pass

    # ------------------------------------------------------------------
    # Navigation / scene helpers
    # ------------------------------------------------------------------

    def transition_to(self, screen_name: str):
        self.app.switch_screen(screen_name)

    def _start_scene_music(self, scene: dict | None):
        """Start the audio track of an image+audio scene (no-op otherwise)."""
        if not scene or scene.get("media_type") != "photo":
            return
        audio = scene.get("audio", "")
        if not audio:
            return
        p = self.app.config.resolve_asset(audio)
        if p.exists():
            self.app.audio.play_music(p)
        else:
            logger.warning("Scene audio file missing: %s", p)

    # ------------------------------------------------------------------
    # Background / pixmap helpers
    # ------------------------------------------------------------------

    def _load_pixmap(self, path: str) -> QPixmap | None:
        """Load an image (resolved relative to project root) as a QPixmap."""
        if not path:
            return None
        p = self.app.config.resolve_asset(path)
        if not p.exists():
            return None
        pix = QPixmap(str(p))
        return pix if not pix.isNull() else None

    def _set_background(self, pixmap: QPixmap | None):
        self._bg_pixmap = pixmap
        self._bg_scaled = None

    def _paint_background(self, painter: QPainter):
        """Paint the background pixmap cover-scaled (cached), or the base color."""
        if self._bg_pixmap is None:
            painter.fillRect(self.rect(), QColor(*COLOR_BG))
            return
        if self._bg_scaled is None:
            self._bg_scaled = self._bg_pixmap.scaled(
                self.width(), self.height(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
        painter.drawPixmap((self.width() - self._bg_scaled.width()) // 2,
                           (self.height() - self._bg_scaled.height()) // 2,
                           self._bg_scaled)

    def _draw_cover(self, painter: QPainter, pixmap: QPixmap, fast: bool = False):
        """Draw a pixmap covering the whole screen (centre-cropped).

        fast=True uses nearest-neighbour scaling – use it for live camera
        frames, where smooth scaling at 20 fps is too expensive for the Pi.
        """
        if pixmap.size() == self.size():
            painter.drawPixmap(0, 0, pixmap)
            return
        mode = (Qt.TransformationMode.FastTransformation if fast
                else Qt.TransformationMode.SmoothTransformation)
        scaled = pixmap.scaled(
            self.width(), self.height(),
            Qt.AspectRatioMode.KeepAspectRatioByExpanding, mode)
        painter.drawPixmap((self.width() - scaled.width()) // 2,
                           (self.height() - scaled.height()) // 2, scaled)

    def resizeEvent(self, event):
        self._bg_scaled = None
        super().resizeEvent(event)
