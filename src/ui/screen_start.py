"""
Start screen – waiting for the user to press the start button.
Ready LED is ON while this screen is active.
"""
import math
import pygame

from .base_screen import BaseScreen, draw_text_centered, get_font
from ..constants import (
    SCREEN_W, SCREEN_H, COLOR_TEXT, COLOR_TEXT_DIM, COLOR_BG,
    BUTTON_EVENT, FONT_HUGE, FONT_SMALL
)

try:
    import cv2
    import numpy as np
    _CV2 = True
except ImportError:
    _CV2 = False


class StartScreen(BaseScreen):
    def __init__(self, app):
        super().__init__(app)
        self._bg_surface: pygame.Surface | None = None
        self._video_cap = None
        self._video_fps = 30
        self._video_accum = 0.0
        self._pulse_t = 0.0

    # ------------------------------------------------------------------

    def on_enter(self):
        self.app.gpio.set_ready_led(True)
        self._load_background()

    def on_exit(self):
        self.app.gpio.set_ready_led(False)
        if self._video_cap:
            self._video_cap.release()
            self._video_cap = None

    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event):
        if event.type != BUTTON_EVENT:
            return
        if event.action == "start_button":
            path = self.app.config.select_random_path()
            if path:
                self.app.context.start_path(path)
                self.transition_to("intro")
            # If no paths configured, stay on start screen (nothing to do)

    def update(self, dt: float):
        self._pulse_t += dt
        if self._video_cap and _CV2:
            self._video_accum += dt
            frame_time = 1.0 / self._video_fps
            if self._video_accum >= frame_time:
                self._video_accum -= frame_time
                ret, frame = self._video_cap.read()
                if not ret:
                    self._video_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ret, frame = self._video_cap.read()
                if ret:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    frame = cv2.resize(frame, (SCREEN_W, SCREEN_H))
                    frame_wh = frame.transpose(1, 0, 2)
                    pygame.surfarray.blit_array(self._bg_surface, frame_wh)

    def draw(self, surface: pygame.Surface):
        if self._bg_surface:
            surface.blit(self._bg_surface, (0, 0))
        else:
            surface.fill(COLOR_BG)

        # Semi-transparent bottom bar
        bar_h = 180
        overlay = pygame.Surface((SCREEN_W, bar_h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        surface.blit(overlay, (0, SCREEN_H - bar_h))

        # Pulsing prompt text
        alpha = int(180 + 75 * math.sin(self._pulse_t * 2.5))
        font = get_font(FONT_SMALL + 4)
        text = "Drücke den Startknopf"
        surf = font.render(text, True, (255, 255, 255))
        surf.set_alpha(alpha)
        rect = surf.get_rect(center=(SCREEN_W // 2, SCREEN_H - 90))
        surface.blit(surf, rect)

    # ------------------------------------------------------------------

    def _load_background(self):
        bg = self.app.config.settings.get("idle_background", {})
        bg_type = bg.get("type", "image")
        bg_file = bg.get("file", "")
        path    = self.app.config.resolve_asset(bg_file)

        if bg_type in ("video", "Video-Loop") and _CV2 and path.exists():
            cap = cv2.VideoCapture(str(path))
            if cap.isOpened():
                self._video_fps = cap.get(cv2.CAP_PROP_FPS) or 30
                self._video_cap = cap
                self._bg_surface = pygame.Surface((SCREEN_W, SCREEN_H))
                return

        # Fallback: image
        self._video_cap = None
        if path.exists():
            try:
                img = pygame.image.load(str(path)).convert()
                self._bg_surface = pygame.transform.scale(img, (SCREEN_W, SCREEN_H))
                return
            except Exception:
                pass
        self._bg_surface = None
