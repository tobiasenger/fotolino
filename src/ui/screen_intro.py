"""
Intro / greeting screen – plays the greeting scene (image+audio or video).
Auto-advances after the scene duration.
"""
import pygame

from .base_screen import BaseScreen, draw_text_centered, get_font
from ..constants import (
    SCREEN_W, SCREEN_H, COLOR_BG, COLOR_TEXT,
    SCREEN_TRANSITION, FONT_MEDIUM
)

try:
    import cv2
    import numpy as np
    _CV2 = True
except ImportError:
    _CV2 = False


class IntroScreen(BaseScreen):
    def __init__(self, app):
        super().__init__(app)
        self._scene: dict | None = None
        self._elapsed  = 0.0
        self._duration = 5.0
        self._bg_surface: pygame.Surface | None = None
        self._video_cap = None
        self._video_fps = 30
        self._video_accum = 0.0
        self._video_frame_surf: pygame.Surface | None = None

    # ------------------------------------------------------------------

    def on_enter(self):
        self._elapsed = 0.0
        ctx = self.app.context
        scene_id = ctx.greeting_scene_id()
        self._scene = self.app.config.get_scene_by_id(scene_id) if scene_id else None

        if self._scene:
            self._duration = float(self._scene.get("duration", 5.0))
            self._setup_media()
        else:
            self._duration = 3.0  # no scene: short pause then continue

    def on_exit(self):
        self.app.audio.stop_music()
        if self._video_cap:
            self._video_cap.release()
            self._video_cap = None

    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event):
        pass  # No user interaction during intro

    def update(self, dt: float):
        self._elapsed += dt
        self._advance_video(dt)

        if self._elapsed >= self._duration:
            ctx = self.app.context
            if ctx.capture_count() > 0:
                self.transition_to("capture")
            else:
                # Path ends after greeting
                ctx.current_path = None
                self.transition_to("start")

    def draw(self, surface: pygame.Surface):
        if self._video_frame_surf:
            surface.blit(self._video_frame_surf, (0, 0))
        elif self._bg_surface:
            surface.blit(self._bg_surface, (0, 0))
        else:
            surface.fill(COLOR_BG)
            draw_text_centered(surface, "…", self._fm(),
                               COLOR_TEXT, SCREEN_W // 2, SCREEN_H // 2)

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
        img_path = self._scene.get("image", "") if self._scene else ""
        if img_path:
            surf = self._load_image_scaled(img_path, (SCREEN_W, SCREEN_H))
            if surf:
                self._bg_surface = surf
                return
        self._bg_surface = None

    def _load_video(self):
        if not self._scene or not _CV2:
            self._load_image_bg()
            return
        video_path = self._scene.get("video", "")
        p = self.app.config.resolve_asset(video_path)
        if not p.exists():
            self._load_image_bg()
            return
        cap = cv2.VideoCapture(str(p))
        if cap.isOpened():
            self._video_fps = cap.get(cv2.CAP_PROP_FPS) or 30
            self._video_cap = cap
            self._video_frame_surf = pygame.Surface((SCREEN_W, SCREEN_H))
        else:
            self._load_image_bg()

    def _advance_video(self, dt: float):
        if not self._video_cap or not _CV2:
            return
        self._video_accum += dt
        frame_time = 1.0 / self._video_fps
        while self._video_accum >= frame_time:
            self._video_accum -= frame_time
            ret, frame = self._video_cap.read()
            if not ret:
                break
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame = cv2.resize(frame, (SCREEN_W, SCREEN_H))
            pygame.surfarray.blit_array(self._video_frame_surf, frame.transpose(1, 0, 2))
