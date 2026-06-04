"""
Collage screen – shows individual photos briefly, then creates and saves the collage.
Duration follows the collage scene setting (max 10 seconds).
"""
import threading
from pathlib import Path

import pygame
from PIL import Image

from .base_screen import BaseScreen, draw_text_centered, draw_progress_bar, get_font
from ..constants import (
    SCREEN_W, SCREEN_H, COLOR_BG, COLOR_TEXT, COLOR_TEXT_DIM,
    FONT_MEDIUM, FONT_SMALL,
)


class CollageScreen(BaseScreen):
    def __init__(self, app):
        super().__init__(app)
        self._scene: dict | None = None
        self._duration   = 10.0
        self._elapsed    = 0.0
        self._bg_surface: pygame.Surface | None = None

        # Photo slideshow
        self._slideshow_surfaces: list[pygame.Surface] = []
        self._slide_idx   = 0
        self._slide_timer = 0.0
        self._slide_phase_end = 0.0   # when slideshow ends and bar starts

        # Collage creation
        self._collage_thread: threading.Thread | None = None
        self._collage_result: Image.Image | None = None
        self._collage_done   = False
        self._collage_error  = False
        self._collage_preview: pygame.Surface | None = None

    # ------------------------------------------------------------------

    def on_enter(self):
        self._elapsed        = 0.0
        self._collage_done   = False
        self._collage_error  = False
        self._collage_result = None
        self._collage_preview = None
        ctx = self.app.context

        scene_id = ctx.collage_scene_id()
        self._scene = self.app.config.get_scene_by_id(scene_id) if scene_id else None
        self._duration = float(self._scene.get("duration", 10.0)) if self._scene else 10.0

        self._build_slideshow()
        self._load_bg()
        # Play scene audio
        if self._scene and self._scene.get("media_type") == "photo":
            audio = self._scene.get("audio", "")
            if audio:
                p = self.app.config.resolve_asset(audio)
                if p.exists():
                    self.app.audio.play_music(p)

        # Calculate slide phase: 1 s per photo, but at most half of total duration
        n_photos = len(self._slideshow_surfaces)
        slide_total = min(n_photos * 1.0, self._duration * 0.45)
        self._slide_phase_end = slide_total
        self._slide_idx   = 0
        self._slide_timer = 0.0

        # Start background collage creation
        self._collage_thread = threading.Thread(target=self._create_collage, daemon=True)
        self._collage_thread.start()

    def on_exit(self):
        self.app.audio.stop_music()

    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event):
        pass

    def update(self, dt: float):
        self._elapsed += dt

        # Slideshow advance
        if self._elapsed < self._slide_phase_end and self._slideshow_surfaces:
            self._slide_timer += dt
            slide_dur = self._slide_phase_end / max(1, len(self._slideshow_surfaces))
            if self._slide_timer >= slide_dur:
                self._slide_timer -= slide_dur
                self._slide_idx = (self._slide_idx + 1) % len(self._slideshow_surfaces)

        # Cache collage preview surface once ready
        if self._collage_done and self._collage_result and not self._collage_preview:
            self._make_preview()

        if self._elapsed >= self._duration:
            if not self._collage_done:
                # Wait a bit more if creation is still running
                if self._collage_thread and self._collage_thread.is_alive():
                    return  # Let it finish
            self._save_and_transition()

    def draw(self, surface: pygame.Surface):
        # Background
        if self._bg_surface:
            surface.blit(self._bg_surface, (0, 0))
        else:
            surface.fill(COLOR_BG)

        bar_color = self.app.config.loading_bar_color_rgb()
        progress = min(1.0, self._elapsed / self._duration)

        if self._elapsed < self._slide_phase_end and self._slideshow_surfaces:
            # Slideshow phase
            surf = self._slideshow_surfaces[self._slide_idx]
            surface.blit(surf, (0, 0))
            # Semi-transparent overlay
            overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 80))
            surface.blit(overlay, (0, 0))
        elif self._collage_preview:
            # Show finished collage
            surface.blit(self._collage_preview, (0, 0))
        else:
            # Creating phase – show progress bar
            draw_text_centered(surface, "Collage wird erstellt…", self._fm(),
                               (255, 255, 255), SCREEN_W // 2, SCREEN_H // 2 - 60, shadow=True)
            draw_progress_bar(surface,
                              SCREEN_W // 2 - 400, SCREEN_H // 2 + 40,
                              800, 30, progress, bar_color)

    # ------------------------------------------------------------------

    def _build_slideshow(self):
        self._slideshow_surfaces = []
        for path in self.app.context.captured_photos:
            try:
                img = pygame.image.load(str(path)).convert()
                img = pygame.transform.scale(img, (SCREEN_W, SCREEN_H))
                self._slideshow_surfaces.append(img)
            except Exception:
                pass

    def _load_bg(self):
        if self._scene and self._scene.get("media_type") == "photo":
            img_path = self._scene.get("image", "")
            if img_path:
                surf = self._load_image_scaled(img_path, (SCREEN_W, SCREEN_H))
                if surf:
                    self._bg_surface = surf
                    return
        self._bg_surface = None

    def _create_collage(self):
        try:
            photos = self.app.context.captured_photos
            count  = self.app.context.capture_count()
            result = self.app.collage_creator.create(photos, count)
            self._collage_result = result
        except Exception as e:
            import logging
            logging.getLogger(__name__).error("Collage creation failed: %s", e)
            self._collage_error = True
        finally:
            self._collage_done = True

    def _make_preview(self):
        import numpy as np
        try:
            arr = self._collage_result
            arr_np = pygame.surfarray.make_surface(
                __import__("numpy").array(arr).transpose(1, 0, 2)
            )
            self._collage_preview = pygame.transform.scale(arr_np, (SCREEN_W, SCREEN_H))
        except Exception:
            self._collage_preview = None

    def _save_and_transition(self):
        if self._collage_result:
            path = self.app.storage.save_collage(self._collage_result)
            self.app.context.collage_path = str(path)
        self.transition_to("print")
