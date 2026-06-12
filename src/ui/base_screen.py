"""
Base class for all application screens (PyQt6).

Each screen is a QWidget on the main QStackedWidget. Besides the
on_enter/on_exit lifecycle it provides the shared plumbing every screen
needs: cached full-screen background painting, cover-scaled pixmap drawing
and starting the music of an image+audio scene.
"""
from __future__ import annotations

import logging

from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QColor, QMovie, QPainter, QPixmap
from PyQt6.QtWidgets import QWidget

from ..constants import COLOR_BG, PROGRESS_BAR_H, SCREEN_H, SCREEN_W

logger = logging.getLogger(__name__)


class BaseScreen(QWidget):
    """Abstract base for all application screens."""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self._bg_pixmap: QPixmap | None = None
        self._bg_scaled: QPixmap | None = None   # cache, invalidated on resize
        self._overlay_pixmap: QPixmap | None = None
        self._overlay_scaled: QPixmap | None = None
        self._overlay_movie: QMovie | None = None

    # ------------------------------------------------------------------
    # Lifecycle hooks (override in subclasses)
    # ------------------------------------------------------------------

    def on_enter(self):
        pass

    def on_exit(self):
        pass

    def handle_button(self, action: str) -> bool:
        """Screen-local button handling (GPIO action name). The app offers
        every button press to the active screen first; return True to consume
        it, False to fall through to the global handling in FotoboxApp."""
        return False

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
            logger.warning("Szenen-Audio-Datei fehlt: %s – Szene läuft ohne Ton. "
                           "Pfad im Admin-Szeneneditor prüfen.", p)

    # ------------------------------------------------------------------
    # Background / pixmap helpers
    # ------------------------------------------------------------------

    def _load_pixmap(self, path: str) -> QPixmap | None:
        """Load an image (resolved relative to project root) as a QPixmap."""
        if not path:
            return None
        p = self.app.config.resolve_asset(path)
        if not p.exists():
            logger.warning("Bild-Datei fehlt: %s – Standardhintergrund wird "
                           "verwendet. Pfad im Admin-Bereich prüfen.", p)
            return None
        pix = QPixmap(str(p))
        if pix.isNull():
            logger.warning("Bild-Datei %s konnte nicht geladen werden (defekt "
                           "oder kein unterstütztes Format) – "
                           "Standardhintergrund wird verwendet.", p)
            return None
        return pix

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

    # ------------------------------------------------------------------
    # Overlay helpers (topmost layer above background and media)
    # ------------------------------------------------------------------

    def _apply_screen_overlay(self, screen_key: str):
        """Load the admin-configured overlay (PNG/GIF) for this screen."""
        ov = self.app.config.settings.get("screen_overlays", {}).get(screen_key, {})
        if ov.get("enabled", True):
            self._set_overlay(ov.get("file", ""))
        else:
            self._set_overlay(None)

    def _set_overlay(self, path: str | None):
        if self._overlay_movie is not None:
            self._overlay_movie.stop()
            self._overlay_movie.deleteLater()
            self._overlay_movie = None
        self._overlay_pixmap = None
        self._overlay_scaled = None
        if not path:
            return
        p = self.app.config.resolve_asset(path)
        if p.suffix.lower() == ".gif" and p.exists():
            movie = QMovie(str(p))
            # frameCount() is 1 for static GIFs (0 = unknown, assume animated)
            if movie.isValid() and movie.frameCount() != 1:
                self._overlay_movie = movie
                movie.frameChanged.connect(lambda _frame: self.update())
                self._scale_overlay_movie()
                movie.start()
                return
            movie.deleteLater()   # static or broken GIF: load as plain image
        self._overlay_pixmap = self._load_pixmap(path)

    def _scale_overlay_movie(self):
        """Cover-scale the GIF: QMovie then decodes frames pre-scaled."""
        movie = self._overlay_movie
        if movie is None:
            return
        movie.jumpToFrame(0)
        size = movie.currentImage().size()
        if not size.isEmpty():
            movie.setScaledSize(size.scaled(
                self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding))

    def _paint_overlay(self, painter: QPainter):
        """Paint the overlay centre-cropped over everything painted so far."""
        if self._overlay_movie is not None:
            pix = self._overlay_movie.currentPixmap()
        elif self._overlay_pixmap is not None:
            if self._overlay_scaled is None:
                self._overlay_scaled = self._overlay_pixmap.scaled(
                    self.width(), self.height(),
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation)
            pix = self._overlay_scaled
        else:
            return
        if not pix.isNull():
            painter.drawPixmap((self.width() - pix.width()) // 2,
                               (self.height() - pix.height()) // 2, pix)

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

    def _design_rect(self, x: int, y: int, w: int, h: int) -> QRect:
        """Map a rect from 1920x1080 design coordinates to the widget size."""
        sx = self.width() / SCREEN_W
        sy = self.height() / SCREEN_H
        return QRect(round(x * sx), round(y * sy), round(w * sx), round(h * sy))

    def _draw_cover_in_rect(self, painter: QPainter, pixmap: QPixmap, rect: QRect):
        """Draw a pixmap filling `rect` exactly (cover-scaled, centre-cropped)."""
        scaled = pixmap.scaled(
            rect.width(), rect.height(),
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation)
        painter.save()
        painter.setClipRect(rect)
        painter.drawPixmap(rect.x() - (scaled.width() - rect.width()) // 2,
                           rect.y() - (scaled.height() - rect.height()) // 2,
                           scaled)
        painter.restore()

    def _position_progress_bar(self, bar):
        """Place a progress bar full-width, flush with the bottom edge."""
        bar_h = round(PROGRESS_BAR_H * self.height() / SCREEN_H)
        bar.setGeometry(0, self.height() - bar_h, self.width(), bar_h)

    def resizeEvent(self, event):
        self._bg_scaled = None
        self._overlay_scaled = None
        self._scale_overlay_movie()
        super().resizeEvent(event)

    def hideEvent(self, event):
        """Pause GIF decoding while the screen is not on the stack top."""
        if self._overlay_movie is not None:
            self._overlay_movie.setPaused(True)
        super().hideEvent(event)

    def showEvent(self, event):
        if (self._overlay_movie is not None
                and self._overlay_movie.state() == QMovie.MovieState.Paused):
            self._overlay_movie.setPaused(False)
        super().showEvent(event)
