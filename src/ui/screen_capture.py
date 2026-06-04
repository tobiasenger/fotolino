"""
Capture screen – live mirrored camera preview with countdown and photo capture.
Flash LED is ON for the entire duration of this screen.
"""
from enum import Enum, auto
from pathlib import Path
import logging

import pygame

from .base_screen import BaseScreen, draw_text_centered, get_font
from ..constants import (
    SCREEN_W, SCREEN_H, COLOR_TEXT, COLOR_WHITE, COLOR_BG, FONT_HUGE, FONT_LARGE,
)


class _Phase(Enum):
    PREVIEW   = auto()   # initial preview before first countdown
    COUNTDOWN = auto()   # 3…2…1
    SMILE     = auto()   # "Smile!"
    FLASH     = auto()   # white screen flash
    POST      = auto()   # brief pause after capture


class CaptureScreen(BaseScreen):
    def __init__(self, app):
        super().__init__(app)
        self._phase    = _Phase.PREVIEW
        self._elapsed  = 0.0
        self._photo_idx = 0          # which photo we're currently taking
        self._total_photos = 0
        self._timing: dict = {}
        self._flash_surf: pygame.Surface | None = None
        self._font_countdown = None
        self._font_smile     = None

    # ------------------------------------------------------------------

    def on_enter(self):
        ctx  = self.app.context
        cfg  = self.app.config
        self._total_photos = ctx.capture_count()
        self._photo_idx    = 0
        self._elapsed      = 0.0
        self._phase        = _Phase.PREVIEW
        self._timing       = cfg.settings.get("capture_timing", {})

        # Flash LED ON for the whole capture sequence
        self.app.gpio.set_flash_led(True)
        self.app.camera.start()

        # Warn if camera is running in mock mode
        if not self.app.camera._cam:
            self.app.show_notification(
                "Kamera nicht verfügbar – Testbild wird verwendet. "
                "Kabelverbindung und 'rpicam-hello' prüfen.",
                duration=5.0, level="warning"
            )

    def on_exit(self):
        self.app.gpio.set_flash_led(False)
        # Keep camera running – screen_collage needs the photos but camera can stay on
        # (will be stopped in collage screen or when no longer needed)
        self.app.camera.stop()

    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event):
        pass  # No user input during capture

    def update(self, dt: float):
        self._elapsed += dt
        t = self._elapsed

        cfg = self._timing
        preview_dur  = cfg.get("initial_preview_seconds", 2.0)
        countdown_n  = int(cfg.get("countdown_from", 3))
        smile_dur    = cfg.get("smile_duration", 0.8)
        post_dur     = cfg.get("post_photo_pause", 2.0)
        flash_dur    = cfg.get("flash_duration", 0.15)

        if self._phase == _Phase.PREVIEW:
            if t >= preview_dur:
                self._phase   = _Phase.COUNTDOWN
                self._elapsed = 0.0

        elif self._phase == _Phase.COUNTDOWN:
            if t >= countdown_n:
                self._phase   = _Phase.SMILE
                self._elapsed = 0.0

        elif self._phase == _Phase.SMILE:
            if t >= smile_dur:
                self._do_capture()
                self._phase   = _Phase.FLASH
                self._elapsed = 0.0

        elif self._phase == _Phase.FLASH:
            if t >= flash_dur:
                self._phase   = _Phase.POST
                self._elapsed = 0.0

        elif self._phase == _Phase.POST:
            if t >= post_dur:
                self._photo_idx += 1
                if self._photo_idx >= self._total_photos:
                    # All photos taken → move to collage
                    self.transition_to("collage")
                else:
                    self._phase   = _Phase.COUNTDOWN
                    self._elapsed = 0.0

    def draw(self, surface: pygame.Surface):
        if self._phase == _Phase.FLASH:
            surface.fill((255, 255, 255))
            return

        # Camera preview (mirrored)
        cam_surf = self.app.camera.get_pygame_surface(mirror=True)
        surface.blit(cam_surf, (0, 0))

        # Overlay HUD
        self._draw_hud(surface)

    # ------------------------------------------------------------------

    def _do_capture(self):
        frame = self.app.camera.capture_photo()

        try:
            path = self.app.storage.save_photo(frame, self._photo_idx)
        except IOError as e:
            self.app.show_notification(str(e), duration=8.0, level="error")
            # Fall back to a temporary path so the session can continue
            import tempfile
            from PIL import Image as _Img
            tmp = Path(tempfile.mktemp(suffix=".jpg"))
            _Img.fromarray(frame, "RGB").save(tmp, "JPEG", quality=95)
            path = tmp

        self.app.context.captured_photos.append(path)

        # Shutter click sound
        click = self.app.config.settings.get("system_sounds", {}).get("shutter_click", "")
        if click:
            self.app.audio.play_sfx(self.app.config.resolve_asset(click))

    def _draw_hud(self, surface: pygame.Surface):
        cfg = self._timing
        countdown_n = int(cfg.get("countdown_from", 3))

        if not self._font_countdown:
            self._font_countdown = get_font(FONT_HUGE, bold=True)
        if not self._font_smile:
            self._font_smile = get_font(FONT_LARGE, bold=True)

        cx, cy = SCREEN_W // 2, SCREEN_H // 2

        if self._phase == _Phase.PREVIEW:
            # Show photo counter e.g. "1 / 4"
            font = get_font(48)
            txt = f"Foto {self._photo_idx + 1} von {self._total_photos}"
            draw_text_centered(surface, txt, font, (255, 255, 255), cx, SCREEN_H - 60, shadow=True)

        elif self._phase == _Phase.COUNTDOWN:
            remaining = countdown_n - int(self._elapsed)
            remaining = max(1, remaining)
            draw_text_centered(surface, str(remaining), self._font_countdown,
                               (255, 255, 255), cx, cy, shadow=True)

        elif self._phase == _Phase.SMILE:
            draw_text_centered(surface, "Lächeln!", self._font_smile,
                               (255, 230, 0), cx, cy, shadow=True)

        elif self._phase == _Phase.POST:
            font = get_font(48)
            txt = f"Foto {self._photo_idx + 1} von {self._total_photos} aufgenommen"
            draw_text_centered(surface, txt, font, (200, 255, 200), cx, SCREEN_H - 60, shadow=True)
