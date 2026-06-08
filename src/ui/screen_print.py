"""
Print screen – shows the collage with a loading bar for the print duration (40s).
Sends the collage to the printer and returns to start screen when done.
"""
from pathlib import Path

import pygame

from .base_screen import BaseScreen, draw_text_centered, draw_progress_bar, get_font
from ..constants import (
    SCREEN_W, SCREEN_H, COLOR_BG, COLOR_TEXT,
    FONT_MEDIUM, FONT_SMALL,
)


class PrintScreen(BaseScreen):
    def __init__(self, app):
        super().__init__(app)
        self._scene: dict | None = None
        self._duration   = 40.0
        self._elapsed    = 0.0
        self._collage_surf: pygame.Surface | None = None
        self._bg_surface:   pygame.Surface | None = None
        self._print_sent = False

    # ------------------------------------------------------------------

    def on_enter(self):
        self._elapsed    = 0.0
        self._print_sent = False
        self._collage_surf = None

        ctx = self.app.context
        scene_id = ctx.print_scene_id()
        self._scene = self.app.config.get_scene_by_id(scene_id) if scene_id else None
        self._duration = 40.0

        self._load_collage()
        self._load_bg()

        # Play audio
        if self._scene and self._scene.get("media_type") == "photo":
            audio = self._scene.get("audio", "")
            if audio:
                p = self.app.config.resolve_asset(audio)
                if p.exists():
                    self.app.audio.play_music(p)

        # Initiate print immediately
        self._send_print()

    def on_exit(self):
        self.app.audio.stop_music()
        self.app.context.current_path    = None
        self.app.context.captured_photos = []
        self.app.context.collage_path    = None

    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event):
        pass

    def update(self, dt: float):
        self._elapsed += dt
        if self._elapsed >= self._duration:
            self.transition_to("start")

    def draw(self, surface: pygame.Surface):
        if self._bg_surface:
            surface.blit(self._bg_surface, (0, 0))
        else:
            surface.fill(COLOR_BG)

        # Show collage centred
        if self._collage_surf:
            # Scale to fit vertically with some margin
            cw, ch = self._collage_surf.get_size()
            max_h = int(SCREEN_H * 0.70)
            max_w = int(SCREEN_W * 0.80)
            scale = min(max_w / cw, max_h / ch)
            disp_w = int(cw * scale)
            disp_h = int(ch * scale)
            scaled = pygame.transform.smoothscale(self._collage_surf, (disp_w, disp_h))
            cx = (SCREEN_W - disp_w) // 2
            cy = (SCREEN_H - disp_h) // 2 - 40
            surface.blit(scaled, (cx, cy))

        # Progress bar
        if self.app.config.settings.get("progress_bar_enabled", True):
            bar_color = self.app.config.loading_bar_color_rgb()
            progress  = min(1.0, self._elapsed / self._duration)
            draw_progress_bar(surface,
                              SCREEN_W // 2 - 500, SCREEN_H - 120,
                              1000, 28, progress, bar_color)

        # Info text
        font = get_font(FONT_SMALL)
        draw_text_centered(surface, "Dein Foto wird gedruckt…", font,
                           (230, 230, 230), SCREEN_W // 2, SCREEN_H - 65, shadow=True)

    # ------------------------------------------------------------------

    def _load_collage(self):
        path = self.app.context.collage_path
        if not path:
            return
        try:
            img = pygame.image.load(path).convert()
            self._collage_surf = img
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Cannot load collage for display: %s", e)

    def _load_bg(self):
        if self._scene and self._scene.get("media_type") == "photo":
            img_path = self._scene.get("image", "")
            if img_path:
                surf = self._load_image_scaled(img_path, (SCREEN_W, SCREEN_H))
                if surf:
                    self._bg_surface = surf
                    return
        self._bg_surface = None

    def _send_print(self):
        if self._print_sent:
            return
        self._print_sent = True
        path = self.app.context.collage_path
        if not path:
            if not self.app.printer.is_demo():
                self.app.show_notification(
                    "Druckfehler: Keine Collage-Datei vorhanden.",
                    level="error"
                )
            return

        def do_print():
            success = self.app.printer.print_collage(Path(path))
            if not success and not self.app.printer.is_demo():
                self.app.show_notification(
                    "Druckfehler: Drucker nicht erreichbar. "
                    "Verbindung, Papier und CUPS-Status prüfen.",
                    duration=10.0, level="error"
                )

        import threading
        threading.Thread(target=do_print, daemon=True).start()
