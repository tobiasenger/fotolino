"""
Segment screen – plays the non-capture segments of a custom path.

A custom path (admin tab "Pfade") is a free sequence of up to
MAX_PATH_SEGMENTS segments. Capture segments run on the normal capture
screen; every other segment type is displayed here:

  * image  – full-screen image + optional overlay + optional audio
  * gif    – full-screen animated GIF + optional audio; plays in a loop or
             once (then black screen until the segment duration ends)
  * camera – live mirrored camera preview (no capture) + optional overlay
             + optional audio
  * print  – runs two phases, mirroring the regular collage and print
             screens: first a collage phase (slideshow of the captured
             photos, collage duration from the admin settings "Zeiten" tab),
             then a print phase that prints the most recently created collage
             and shows it (print duration). Each phase has its own
             configurable background, overlay and audio.

Audio always plays once from the start of the segment, followed by silence
(a print segment plays one audio file per phase).
When the segment duration has elapsed the screen hands control back to
FotoboxApp.advance_segment(), which enters the next segment or ends the
session.
"""
from __future__ import annotations

import logging
import time

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QMovie, QPainter, QPixmap

from ..constants import (
    MEDIA_PANEL_RECT, SEGMENT_DURATION_DEFAULT, SEGMENT_DURATION_RANGE,
)
from .base_screen import BaseScreen

logger = logging.getLogger(__name__)


class SegmentScreen(BaseScreen):
    def __init__(self, app):
        super().__init__(app)
        self._segment: dict = {}
        self._duration = SEGMENT_DURATION_DEFAULT
        self._start_time = 0.0

        # GIF segment
        self._movie: QMovie | None = None
        self._gif_loop = True
        self._gif_last_frame = -1
        self._gif_done = False           # play-once finished → black screen

        # Camera segment
        self._camera_active = False
        self._preview_pixmap: QPixmap | None = None

        # Print segment (two phases: "collage" → "print")
        self._print_phase = "collage"
        self._print_duration = 0.0
        self._collage_pixmap: QPixmap | None = None
        self._print_sent = False
        self._slide_pixmaps: list[QPixmap] = []
        self._slide_idx = 0
        self._slide_dur = 1.0            # seconds per slideshow photo
        self._last_slide_switch = 0.0

        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tick)

        self._progress = self._make_progress_bar()

    # ------------------------------------------------------------------

    def on_enter(self):
        self._segment = self.app.context.current_segment() or {}
        seg = self._segment
        self._reset_media_state()

        stype = seg.get("type", "")
        if stype == "image":
            self._duration = self._segment_duration(seg)
            self._set_background(self._load_pixmap(seg.get("image", "")))
            self._set_overlay(seg.get("overlay", ""))
        elif stype == "gif":
            self._duration = self._segment_duration(seg)
            self._gif_loop = bool(seg.get("loop", True))
            self._setup_gif(seg.get("gif", ""))
        elif stype == "camera":
            self._duration = self._segment_duration(seg)
            self._set_overlay(seg.get("overlay", ""))
            self.app.camera.start()
            self._camera_active = True
        elif stype == "print":
            durations = self.app.config.scene_durations()
            self._duration = durations["collage"]
            self._print_duration = durations["print"]
            self._set_background(self._load_pixmap(
                self._phase_media(seg, "collage", "image")))
            self._set_overlay(self._phase_media(seg, "collage", "overlay"))
            self._build_slideshow()
            self._slide_dur = self._duration / max(1, len(self._slide_pixmaps))
            self._reset_progress_bar(self._progress)
        else:
            logger.warning("Unbekannter Segment-Typ '%s' – Segment wird "
                           "übersprungen.", stype)
            self._duration = 0.1

        if stype == "print":
            self._play_audio_file(self._phase_media(seg, "collage", "audio"))
        else:
            self._play_audio_file(seg.get("audio", ""))
        self._start_time = time.monotonic()
        self._last_slide_switch = self._start_time
        self._timer.start()
        self.update()

    def on_exit(self):
        self._timer.stop()
        self.app.audio.stop_music()
        self._stop_movie()
        if self._camera_active:
            self.app.camera.stop()
            self._camera_active = False

    def _reset_media_state(self):
        self._stop_movie()
        self._gif_last_frame = -1
        self._gif_done = False
        self._preview_pixmap = None
        self._print_phase = "collage"
        self._collage_pixmap = None
        self._print_sent = False
        self._slide_pixmaps = []
        self._slide_idx = 0
        self._progress.hide()
        self._set_background(None)
        self._set_overlay(None)

    @staticmethod
    def _segment_duration(seg: dict) -> float:
        lo, hi = SEGMENT_DURATION_RANGE
        try:
            return min(hi, max(lo, float(seg.get("duration",
                                                 SEGMENT_DURATION_DEFAULT))))
        except (TypeError, ValueError):
            return SEGMENT_DURATION_DEFAULT

    @staticmethod
    def _phase_media(seg: dict, phase: str, key: str) -> str:
        """Media file of a print-segment phase ("collage"/"print" +
        image/overlay/audio). Print-phase fields fall back to the flat keys
        older configurations stored (image/overlay/audio)."""
        value = seg.get(f"{phase}_{key}", "")
        if not value and phase == "print":
            value = seg.get(key, "")
        return value or ""

    # ------------------------------------------------------------------

    def _tick(self):
        now = time.monotonic()
        elapsed = now - self._start_time
        stype = self._segment.get("type")

        if stype == "camera":
            try:
                self._preview_pixmap = self.app.camera.get_qpixmap(mirror=True)
            except Exception:
                self._preview_pixmap = None
            self.update()
        elif stype == "print":
            self._progress.setValue(int(min(1.0, elapsed / self._duration) * 100))
            if self._print_phase == "collage":
                if (self._slide_pixmaps
                        and now - self._last_slide_switch >= self._slide_dur):
                    self._last_slide_switch = now
                    self._slide_idx = (self._slide_idx + 1) % len(self._slide_pixmaps)
                    self.update()
                # The slideshow keeps running until the background build is done.
                if elapsed >= self._duration \
                        and not self.app.context.collage_pending:
                    self._enter_print_phase()
                return
            if not self._print_sent:
                self._try_send_print()

        if elapsed >= self._duration:
            self.app.advance_segment()

    # ------------------------------------------------------------------
    # GIF segment
    # ------------------------------------------------------------------

    def _setup_gif(self, path: str):
        p = self.app.config.resolve_asset(path)
        if not path or not p.exists():
            logger.warning("GIF-Datei fehlt: %s – Segment zeigt einen schwarzen "
                           "Bildschirm. Pfad im Admin-Bereich prüfen.", p)
            return
        movie = QMovie(str(p))
        if not movie.isValid():
            logger.warning("GIF-Datei %s kann nicht abgespielt werden (defekt "
                           "oder kein GIF) – Segment zeigt einen schwarzen "
                           "Bildschirm.", p)
            movie.deleteLater()
            return
        self._movie = movie
        movie.frameChanged.connect(self._on_gif_frame)
        movie.finished.connect(self._on_gif_finished)
        self._scale_movie()
        movie.start()

    def _stop_movie(self):
        if self._movie is not None:
            self._movie.stop()
            self._movie.deleteLater()
            self._movie = None

    def _scale_movie(self):
        """Cover-scale the GIF: QMovie then decodes frames pre-scaled."""
        if self._movie is None:
            return
        self._movie.jumpToFrame(0)
        size = self._movie.currentImage().size()
        if not size.isEmpty():
            self._movie.setScaledSize(size.scaled(
                self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding))

    def _on_gif_frame(self, frame: int):
        # A wrapped frame number means the GIF finished a pass and restarted.
        if not self._gif_loop and not self._gif_done \
                and frame < self._gif_last_frame:
            self._finish_gif()
            return
        self._gif_last_frame = frame
        self.update()

    def _on_gif_finished(self):
        """The GIF's file-internal loop count is exhausted (QMovie stopped)."""
        # Static (single-frame) GIF: keep the frame visible instead of
        # blacking out instantly or restarting in a tight loop.
        if self._movie is not None and self._movie.frameCount() == 1:
            return
        if self._gif_loop and self._movie is not None:
            self._movie.start()
        else:
            self._finish_gif()

    def _finish_gif(self):
        """Play-once GIF ended: black screen until the segment duration ends."""
        self._gif_done = True
        self._stop_movie()
        self.update()

    # ------------------------------------------------------------------
    # Print segment
    # ------------------------------------------------------------------

    def _build_slideshow(self):
        self._slide_pixmaps = []
        for path in self.app.context.captured_photos:
            pix = QPixmap(str(path))
            if not pix.isNull():
                self._slide_pixmaps.append(pix)
            else:
                logger.warning("Foto %s kann nicht für die Diashow geladen "
                               "werden – wird übersprungen.", path)

    def _enter_print_phase(self):
        """Collage phase finished: switch media and timing to the print phase."""
        seg = self._segment
        self._print_phase = "print"
        self.app.audio.stop_music()
        self._duration = self._print_duration
        self._set_background(self._load_pixmap(
            self._phase_media(seg, "print", "image")))
        self._set_overlay(self._phase_media(seg, "print", "overlay"))
        self._reset_progress_bar(self._progress)
        self._play_audio_file(self._phase_media(seg, "print", "audio"))
        self._try_send_print()
        self._start_time = time.monotonic()
        self.update()

    def _try_send_print(self):
        """Print the most recent collage: the one of this session if available
        (waiting for a pending background build), otherwise the newest stored
        collage from the USB stick."""
        if self._print_sent or self.app.context.collage_pending:
            return
        path = self.app.context.collage_path
        if not path:
            stored = self.app.storage.last_session_collage()
            path = str(stored[0]) if stored else None
        self._print_sent = True
        if not path:
            self.app.show_notification(
                "Druckfehler: Keine Collage vorhanden – das Druck-Segment "
                "benötigt ein vorheriges Aufnahme-Segment oder eine "
                "gespeicherte Collage.", duration=8.0, level="error")
            return
        pix = QPixmap(str(path))
        if pix.isNull():
            logger.warning("Collage %s kann nicht angezeigt werden (Datei defekt "
                           "oder nicht lesbar) – Druck wird trotzdem versucht.",
                           path)
        else:
            self._collage_pixmap = pix
        self._print_collage_file(path)
        self.update()

    # ------------------------------------------------------------------

    def resizeEvent(self, event):
        self._scale_movie()
        self._position_progress_bar(self._progress)
        super().resizeEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        stype = self._segment.get("type")

        if stype == "gif":
            painter.fillRect(self.rect(), QColor(0, 0, 0))
            if self._movie is not None and not self._gif_done:
                pix = self._movie.currentPixmap()
                if not pix.isNull():
                    painter.drawPixmap((self.width() - pix.width()) // 2,
                                       (self.height() - pix.height()) // 2, pix)
        elif stype == "camera" and self._preview_pixmap:
            self._draw_cover(painter, self._preview_pixmap, fast=True)
        else:
            self._paint_background(painter)
            if stype == "print":
                if self._print_phase == "collage":
                    if self._slide_pixmaps:
                        self._draw_cover_in_rect(
                            painter, self._slide_pixmaps[self._slide_idx],
                            self._design_rect(*MEDIA_PANEL_RECT))
                elif self._collage_pixmap:
                    self._draw_cover_in_rect(painter, self._collage_pixmap,
                                             self._design_rect(*MEDIA_PANEL_RECT))

        self._paint_overlay(painter)
        painter.end()
