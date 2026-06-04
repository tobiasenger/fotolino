"""
Admin container screen.
Hosts three sub-views via a tab bar: Paths | Scenes | Settings.
"""
import pygame
import pygame_gui

from ..base_screen import BaseScreen, draw_text_centered, get_font
from ..admin.admin_paths    import AdminPaths
from ..admin.admin_scenes   import AdminScenes
from ..admin.admin_settings import AdminSettings
from ...constants import (
    SCREEN_W, SCREEN_H, BUTTON_EVENT,
    ADMIN_BG, ADMIN_PANEL, ADMIN_TAB_ACTIVE, ADMIN_TAB_IDLE, COLOR_TEXT,
)

_THEME = {
    "defaults": {
        "colours": {
            "dark_bg":       "#141428",
            "normal_bg":     "#1e1e3a",
            "hovered_bg":    "#2a2a50",
            "selected_bg":   "#ff6600",
            "active_bg":     "#2a2a50",
            "normal_text":   "#ffffff",
            "hovered_text":  "#ffffff",
            "selected_text": "#ffffff",
            "normal_border": "#2a2a50",
            "hovered_border":"#ff6600",
        },
        "font": {"size": "20", "bold": "0"},
    },
    "button": {
        "colours": {"normal_bg": "#2a2a50", "hovered_bg": "#3a3a70",
                    "normal_border": "#444488", "hovered_border": "#ff6600"},
    },
}

_TABS = ["Pfade", "Szenen", "Einstellungen"]
TAB_H    = 64
CLOSE_W  = 180
CLOSE_H  = 50


class AdminMain(BaseScreen):
    def __init__(self, app):
        super().__init__(app)
        self._manager: pygame_gui.UIManager | None = None
        self._tab_buttons: list[pygame_gui.elements.UIButton] = []
        self._close_btn: pygame_gui.elements.UIButton | None  = None
        self._active_tab = 0
        self._sub_views  = []

    def _ensure_manager(self):
        if self._manager is None:
            self._manager = pygame_gui.UIManager(
                (SCREEN_W, SCREEN_H),
                theme_path=None,
            )
            # Apply minimal inline theme
            try:
                self._manager.get_theme().load_theme(_THEME)
            except Exception:
                pass
            self._sub_views = [
                AdminPaths(self.app,    self._manager),
                AdminScenes(self.app,   self._manager),
                AdminSettings(self.app, self._manager),
            ]
            self._create_chrome()

    # ------------------------------------------------------------------

    def on_enter(self):
        self._ensure_manager()
        # Show active tab, hide others
        for i, sv in enumerate(self._sub_views):
            sv.hide()
        self._sub_views[self._active_tab].show()

    def on_exit(self):
        for sv in self._sub_views:
            sv.hide()

    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event):
        if self._manager:
            self._manager.process_events(event)

        # Note: admin_button toggle is handled centrally in main.py, not here.
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            for i, btn in enumerate(self._tab_buttons):
                if event.ui_element == btn:
                    self._switch_tab(i)
                    return
            if event.ui_element == self._close_btn:
                self.app.context.exit_admin()
                self.app.gpio.set_ready_led(True)
                self.transition_to("start")
                return

        # Pass to active sub-view
        if self._sub_views:
            self._sub_views[self._active_tab].handle_event(event)

    def update(self, dt: float):
        if self._manager:
            self._manager.update(dt)
        if self._sub_views:
            self._sub_views[self._active_tab].update(dt)

    def draw(self, surface: pygame.Surface):
        surface.fill(ADMIN_BG)
        self._draw_tab_bar(surface)
        if self._sub_views:
            self._sub_views[self._active_tab].draw(surface)
        if self._manager:
            self._manager.draw_ui(surface)

    # ------------------------------------------------------------------

    def _create_chrome(self):
        tab_w = (SCREEN_W - CLOSE_W - 40) // len(_TABS)
        self._tab_buttons = []
        for i, label in enumerate(_TABS):
            btn = pygame_gui.elements.UIButton(
                relative_rect=pygame.Rect(10 + i * tab_w, 8, tab_w - 6, TAB_H - 16),
                text=label,
                manager=self._manager,
            )
            self._tab_buttons.append(btn)

        self._close_btn = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(SCREEN_W - CLOSE_W - 10, 8, CLOSE_W, TAB_H - 16),
            text="✕  Schließen",
            manager=self._manager,
        )

    def _switch_tab(self, idx: int):
        if idx == self._active_tab:
            return
        self._sub_views[self._active_tab].hide()
        self._active_tab = idx
        self._sub_views[self._active_tab].show()

    def _draw_tab_bar(self, surface: pygame.Surface):
        pygame.draw.rect(surface, ADMIN_PANEL, (0, 0, SCREEN_W, TAB_H))
        pygame.draw.line(surface, (60, 60, 100), (0, TAB_H), (SCREEN_W, TAB_H), 2)
        # Highlight active tab
        tab_w = (SCREEN_W - CLOSE_W - 40) // len(_TABS)
        x = 10 + self._active_tab * tab_w
        pygame.draw.line(surface, ADMIN_TAB_ACTIVE, (x, TAB_H - 3),
                         (x + tab_w - 6, TAB_H - 3), 4)
