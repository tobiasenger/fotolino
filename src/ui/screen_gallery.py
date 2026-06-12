"""
Gallery mode – browse and re-print the photos and the collage of the most
recent session.

Three screens, all driven by two buttons:
  * GalleryMenuScreen   – "Fotos / Collage / Beenden". The gallery button
    cycles the highlighted entry, the start button confirms it.
  * GalleryBrowseScreen – shows one image at a time in the shared media
    panel: the 1–4 photos of the last session in capture order, or its one
    collage. Gallery button steps forward and returns to the menu after the
    last image; start button re-prints the current image.
  * GalleryPrintScreen  – like the normal print screen, but for a single
    re-printed file: progress bar for the configured print duration, then
    back to the start screen. Demo mode only simulates the print.

The background images of the browse and print screens and a PNG overlay
for the print screen are configured in the admin menu (settings.json key
"gallery").
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QPainter, QPixmap
from PyQt6.QtWidgets import QProgressBar

from ..constants import (
    FONT_LARGE, FONT_MEDIUM, FONT_SMALL, MEDIA_PANEL_RECT,
    SCENE_DURATION_DEFAULTS, SCREEN_W,
)
from . import theme
from .base_screen import BaseScreen
from .widgets import draw_shadow_text

logger = logging.getLogger(__name__)

_ACCENT_RGB = (255, 102, 0)
_WHITE = (255, 255, 255)
_MUTED = (190, 190, 200)


class GalleryMenuScreen(BaseScreen):
    """Entry menu of the gallery: Fotos / Collage / Beenden."""

    _ITEMS = (("photos", "Fotos"), ("collages", "Collage"), ("exit", "Beenden"))

    def __init__(self, app):
        super().__init__(app)
        self._selected = 0

    def on_enter(self):
        self._selected = 0
        self._set_background(self._load_pixmap(
            self.app.config.gallery_background()))

    def handle_button(self, action: str) -> bool:
        if action == "gallery_button":
            self._selected = (self._selected + 1) % len(self._ITEMS)
            self.update()
            return True
        if action == "start_button":
            choice = self._ITEMS[self._selected][0]
            if choice == "exit":
                self.transition_to("start")
            else:
                self.app.screens["gallery_browse"].set_mode(choice)
                self.transition_to("gallery_browse")
            return True
        return False

    def paintEvent(self, event):
        painter = QPainter(self)
        self._paint_background(painter)

        r = self._design_rect(0, 120, SCREEN_W, 140)
        draw_shadow_text(painter, r.x(), r.y(), r.width(), r.height(),
                         "Galerie", FONT_MEDIUM, _WHITE)

        for i, (_key, label) in enumerate(self._ITEMS):
            r = self._design_rect(0, 360 + i * 170, SCREEN_W, 150)
            if i == self._selected:
                draw_shadow_text(painter, r.x(), r.y(), r.width(), r.height(),
                                 f"▶  {label}  ◀", FONT_LARGE, _ACCENT_RGB)
            else:
                draw_shadow_text(painter, r.x(), r.y(), r.width(), r.height(),
                                 label, FONT_LARGE, _WHITE)

        r = self._design_rect(0, 980, SCREEN_W, 70)
        draw_shadow_text(painter, r.x(), r.y(), r.width(), r.height(),
                         "Galerie-Taste: Auswahl  ·  Start-Taste: Bestätigen",
                         FONT_SMALL, _MUTED)
        painter.end()


class GalleryBrowseScreen(BaseScreen):
    """Steps through the photos or the collage of the most recent session."""

    def __init__(self, app):
        super().__init__(app)
        self._mode = "photos"             # "photos" | "collages"
        self._files: list[Path] = []
        self._idx = 0
        self._current_pixmap: QPixmap | None = None

    def set_mode(self, mode: str):
        """Must be called before switching to this screen."""
        self._mode = mode

    def on_enter(self):
        cfg = self.app.config
        self._set_background(self._load_pixmap(cfg.gallery_background()))
        if self._mode == "photos":
            self._files = self.app.storage.last_session_photos()
        else:
            self._files = self.app.storage.last_session_collage()
        self._idx = 0
        self._load_current()
        logger.info("Galerie: %d %s der letzten Sitzung zum Durchblättern.",
                    len(self._files), self._mode)

    def handle_button(self, action: str) -> bool:
        if action == "gallery_button":
            if not self._files or self._idx + 1 >= len(self._files):
                self.transition_to("gallery_menu")
            else:
                self._idx += 1
                self._load_current()
                self.update()
            return True
        if action == "start_button":
            if self._files:
                self.app.screens["gallery_print"].set_file(self._files[self._idx])
                self.transition_to("gallery_print")
            return True
        return False

    def _load_current(self):
        self._current_pixmap = None
        while self._files:
            pix = QPixmap(str(self._files[self._idx]))
            if not pix.isNull():
                self._current_pixmap = pix
                return
            logger.warning("Galerie: Bild %s kann nicht geladen werden – "
                           "wird übersprungen.", self._files[self._idx])
            del self._files[self._idx]
            if self._idx >= len(self._files):
                self._idx = max(0, len(self._files) - 1)
                if not self._files:
                    return

    def paintEvent(self, event):
        painter = QPainter(self)
        self._paint_background(painter)
        if not self._files:
            label = ("Keine Fotos vorhanden" if self._mode == "photos"
                     else "Keine Collage vorhanden")
            r = self._design_rect(0, 440, SCREEN_W, 200)
            draw_shadow_text(painter, r.x(), r.y(), r.width(), r.height(),
                             label, FONT_MEDIUM, _WHITE)
            hint = "Beliebige Taste: Zurück zum Menü"
        else:
            if self._current_pixmap:
                self._draw_cover_in_rect(painter, self._current_pixmap,
                                         self._design_rect(*MEDIA_PANEL_RECT))
            r = self._design_rect(0, 850, SCREEN_W, 70)
            draw_shadow_text(painter, r.x(), r.y(), r.width(), r.height(),
                             f"{self._idx + 1} / {len(self._files)}",
                             FONT_SMALL, _WHITE)
            hint = "Galerie-Taste: Weiter  ·  Start-Taste: Drucken"
        r = self._design_rect(0, 980, SCREEN_W, 70)
        draw_shadow_text(painter, r.x(), r.y(), r.width(), r.height(),
                         hint, FONT_SMALL, _MUTED)
        painter.end()


class GalleryPrintScreen(BaseScreen):
    """Re-prints one gallery file, mirroring the normal print screen timing."""

    def __init__(self, app):
        super().__init__(app)
        self._file: Path | None = None
        self._pixmap: QPixmap | None = None
        self._duration = float(SCENE_DURATION_DEFAULTS["print"])
        self._print_sent = False
        self._start_time = 0.0

        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tick)

        self._progress = QProgressBar(self)
        self._progress.setRange(0, 100)
        self._progress.setTextVisible(False)

    def set_file(self, path: Path):
        """Must be called before switching to this screen."""
        self._file = Path(path)

    def on_enter(self):
        cfg = self.app.config
        self._print_sent = False
        self._duration = cfg.scene_durations()["print"]
        self._set_background(self._load_pixmap(
            cfg.gallery_background("print_background")))
        self._set_overlay(cfg.gallery_background("print_overlay"))

        self._pixmap = QPixmap(str(self._file)) if self._file else QPixmap()
        if self._pixmap.isNull():
            self._pixmap = None

        self._progress.setStyleSheet(theme.progress_bar_style(
            cfg.settings.get("loading_bar_color", "#FF6600")))
        self._progress.setValue(0)
        self._position_progress_bar(self._progress)
        self._progress.setVisible(cfg.settings.get("progress_bar_enabled", True))
        self._progress.raise_()

        self._send_print()
        self._start_time = time.monotonic()
        self._timer.start()

    def on_exit(self):
        self._timer.stop()

    def handle_button(self, action: str) -> bool:
        # Swallow both buttons while the print countdown runs.
        return action in ("gallery_button", "start_button")

    def _tick(self):
        elapsed = time.monotonic() - self._start_time
        self._progress.setValue(int(min(1.0, elapsed / self._duration) * 100))
        if elapsed >= self._duration:
            self.transition_to("start")

    def resizeEvent(self, event):
        self._position_progress_bar(self._progress)
        super().resizeEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        self._paint_background(painter)
        if self._pixmap:
            self._draw_cover_in_rect(painter, self._pixmap,
                                     self._design_rect(*MEDIA_PANEL_RECT))
        self._paint_overlay(painter)
        painter.end()

    def _send_print(self):
        if self._print_sent:
            return
        self._print_sent = True
        if not self._file:
            self.app.show_notification(
                "Druckfehler: Keine Datei ausgewählt.", level="error")
            return
        path = self._file

        def do_print():
            success = self.app.printer.print_collage(path)
            if not success and not self.app.printer.is_demo():
                self.app.show_notification(
                    "Druck fehlgeschlagen – Details in fotobox.log. "
                    "Drucker, Papier und CUPS-Status prüfen.",
                    duration=10.0, level="error",
                )

        threading.Thread(target=do_print, daemon=True).start()
