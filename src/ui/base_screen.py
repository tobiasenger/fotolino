import pygame
from ..constants import SCREEN_W, SCREEN_H, COLOR_BG, FONT_LARGE, FONT_MEDIUM, FONT_SMALL


def get_font(size: int, bold: bool = False) -> pygame.font.Font:
    font = pygame.font.SysFont("dejavusans,freesans,sans-serif", size, bold=bold)
    return font


def draw_text_centered(surface: pygame.Surface, text: str, font: pygame.font.Font,
                       color: tuple, center_x: int, center_y: int,
                       shadow: bool = False):
    if shadow:
        shadow_surf = font.render(text, True, (0, 0, 0))
        sr = shadow_surf.get_rect(center=(center_x + 3, center_y + 3))
        surface.blit(shadow_surf, sr)
    rendered = font.render(text, True, color)
    rect = rendered.get_rect(center=(center_x, center_y))
    surface.blit(rendered, rect)
    return rect


def draw_progress_bar(surface: pygame.Surface, x: int, y: int, w: int, h: int,
                      progress: float, color: tuple, bg_color=(40, 40, 40),
                      radius: int = 8):
    """Draw a rounded progress bar. progress in [0, 1]."""
    pygame.draw.rect(surface, bg_color, (x, y, w, h), border_radius=radius)
    fill_w = int(w * max(0.0, min(1.0, progress)))
    if fill_w > 0:
        pygame.draw.rect(surface, color, (x, y, fill_w, h), border_radius=radius)


class BaseScreen:
    """Abstract base for all application screens."""

    def __init__(self, app):
        self.app   = app
        self._font_large  = None
        self._font_medium = None
        self._font_small  = None

    # Lazy font loading to avoid pre-init issues
    def _fl(self): # font large
        if not self._font_large:
            self._font_large = get_font(FONT_LARGE)
        return self._font_large

    def _fm(self): # font medium
        if not self._font_medium:
            self._font_medium = get_font(FONT_MEDIUM)
        return self._font_medium

    def _fs(self): # font small
        if not self._font_small:
            self._font_small = get_font(FONT_SMALL)
        return self._font_small

    # ------------------------------------------------------------------
    # Lifecycle hooks (override in subclasses)
    # ------------------------------------------------------------------

    def on_enter(self):
        pass

    def on_exit(self):
        pass

    def handle_event(self, event: pygame.event.Event):
        pass

    def update(self, dt: float):
        pass

    def draw(self, surface: pygame.Surface):
        surface.fill(COLOR_BG)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def transition_to(self, screen_name: str):
        from ..constants import SCREEN_TRANSITION
        pygame.event.post(pygame.event.Event(SCREEN_TRANSITION, {"target": screen_name}))

    def _load_image_scaled(self, path: str, size: tuple | None = None) -> pygame.Surface | None:
        from pathlib import Path
        p = self.app.config.resolve_asset(path)
        if not p.exists():
            return None
        try:
            img = pygame.image.load(str(p)).convert()
            if size:
                img = pygame.transform.scale(img, size)
            return img
        except Exception:
            return None
