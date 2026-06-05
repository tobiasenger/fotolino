"""
Admin Paths tab.
List of paths with probability display; create / edit / delete via inline editor panel.
"""
from __future__ import annotations

import pygame
import pygame_gui

from ...constants import (
    SCREEN_W, SCREEN_H, ADMIN_BG, ADMIN_PANEL, ADMIN_HIGHLIGHT,
    COLOR_TEXT, COLOR_TEXT_DIM, COLOR_ACCENT,
)

_TOP    = 70       # below tab bar
_MARGIN = 20
_LIST_W = 440
_PANEL_X = _LIST_W + _MARGIN * 2
_PANEL_W = SCREEN_W - _PANEL_X - _MARGIN
_CONTENT_H = SCREEN_H - _TOP - _MARGIN


class AdminPaths:
    def __init__(self, app, manager: pygame_gui.UIManager):
        self.app     = app
        self._mgr    = manager
        self._widgets: list = []
        self._active = False

        # Editor state
        self._editing_id: str | None = None
        self._editor_widgets: list   = []

        # Scrollable path list state
        self._path_buttons: dict = {}  # path_id -> (edit_btn, del_btn)

    # ------------------------------------------------------------------

    def show(self):
        self._active = True
        self._build_list()
        self._clear_editor()

    def hide(self):
        self._active = False
        self._kill_all()

    def handle_event(self, event: pygame.event.Event):
        if not self._active:
            return
        if event.type != pygame_gui.UI_BUTTON_PRESSED:
            return
        el = event.ui_element

        if el == self._add_btn:
            self._open_editor(None)
            return

        for pid, (ebtn, dbtn) in list(self._path_buttons.items()):
            if el == ebtn:
                path = self._find_path(pid)
                if path:
                    self._open_editor(path)
                return
            if el == dbtn:
                self.app.config.delete_path(pid)
                self._build_list()
                self._clear_editor()
                return

        if hasattr(self, "_save_btn") and el == self._save_btn:
            self._save_editor()
        elif hasattr(self, "_cancel_btn") and el == self._cancel_btn:
            self._clear_editor()

    def update(self, dt: float):
        pass

    def draw(self, surface: pygame.Surface):
        if not self._active:
            return
        # List panel background
        pygame.draw.rect(surface, ADMIN_PANEL,
                         (_MARGIN, _TOP, _LIST_W, _CONTENT_H), border_radius=8)
        # Editor panel background
        if self._editing_id is not None or hasattr(self, "_new_mode"):
            pygame.draw.rect(surface, ADMIN_PANEL,
                             (_PANEL_X, _TOP, _PANEL_W, _CONTENT_H), border_radius=8)

        self._draw_path_cards(surface)

    # ------------------------------------------------------------------

    def _kill_all(self):
        for w in self._widgets:
            try: w.kill()
            except Exception: pass
        self._widgets.clear()
        for ebtn, dbtn in self._path_buttons.values():
            try: ebtn.kill()
            except Exception: pass
            try: dbtn.kill()
            except Exception: pass
        self._path_buttons.clear()
        self._kill_editor()

    def _kill_editor(self):
        for w in self._editor_widgets:
            try: w.kill()
            except Exception: pass
        self._editor_widgets.clear()

    def _clear_editor(self):
        self._kill_editor()
        self._editing_id = None
        if hasattr(self, "_new_mode"):
            del self._new_mode

    # ------------------------------------------------------------------

    def _build_list(self):
        # Kill old list widgets
        for ebtn, dbtn in self._path_buttons.values():
            try: ebtn.kill()
            except Exception: pass
            try: dbtn.kill()
            except Exception: pass
        self._path_buttons.clear()
        for w in self._widgets:
            try: w.kill()
            except Exception: pass
        self._widgets.clear()

        # Add button
        self._add_btn = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(_MARGIN + _LIST_W - 160, _TOP + 10, 150, 40),
            text="+ Neuer Pfad",
            manager=self._mgr,
        )
        self._widgets.append(self._add_btn)

        paths = self.app.config.get_paths()
        y = _TOP + 60
        for path in paths:
            pid  = path["id"]
            name = path.get("name", "(kein Name)")
            prob = (self.app.config.compute_default_probability()
                    if path.get("is_default") else path.get("probability", 0))
            default_tag = " ★" if path.get("is_default") else ""
            capture = path.get("scenes", {}).get("capture_count", 0)
            label = f"{name}{default_tag}  |  {prob}%  |  {capture} Fotos"

            edit_btn = pygame_gui.elements.UIButton(
                relative_rect=pygame.Rect(_MARGIN + 4, y, _LIST_W - 100, 44),
                text=label,
                manager=self._mgr,
            )
            del_btn = pygame_gui.elements.UIButton(
                relative_rect=pygame.Rect(_MARGIN + _LIST_W - 88, y, 80, 44),
                text="Löschen",
                manager=self._mgr,
            )
            self._path_buttons[pid] = (edit_btn, del_btn)
            y += 52
            if y + 52 > _TOP + _CONTENT_H:
                break

    def _draw_path_cards(self, surface: pygame.Surface):
        pass  # Buttons are drawn by pygame_gui; nothing extra needed here

    # ------------------------------------------------------------------
    # Editor
    # ------------------------------------------------------------------

    def _open_editor(self, path: dict | None):
        self._clear_editor()
        self._new_mode = path is None
        self._editing_id = path["id"] if path else "__new__"

        x0 = _PANEL_X + 20
        y  = _TOP + 20
        w  = _PANEL_W - 40

        def label(text, yy):
            lbl = pygame_gui.elements.UILabel(
                relative_rect=pygame.Rect(x0, yy, w, 30),
                text=text, manager=self._mgr,
            )
            self._editor_widgets.append(lbl)
            return lbl

        def text_entry(initial, yy):
            entry = pygame_gui.elements.UITextEntryLine(
                relative_rect=pygame.Rect(x0, yy, w, 40),
                manager=self._mgr,
            )
            entry.set_text(initial)
            self._editor_widgets.append(entry)
            return entry

        def dropdown(options, selected, yy):
            if not options:
                options = ["(keine verfügbar)"]
                selected = options[0]
            if selected not in options:
                selected = options[0]
            dd = pygame_gui.elements.UIDropDownMenu(
                options_list=options,
                starting_option=selected,
                relative_rect=pygame.Rect(x0, yy, w, 44),
                manager=self._mgr,
            )
            self._editor_widgets.append(dd)
            return dd

        label("Name:", y);                 y += 32
        self._e_name = text_entry(path.get("name", "") if path else "", y); y += 50

        if not (path and path.get("is_default")):
            label("Wahrscheinlichkeit (%):", y);  y += 32
            self._e_prob = text_entry(str(path.get("probability", 5)) if path else "5", y); y += 50
        else:
            self._e_prob = None
            label(f"Standard-Pfad – Wahrscheinlichkeit: {self.app.config.compute_default_probability()}%", y)
            y += 40

        # Greeting scene
        greeting_scenes = [(s["id"], s.get("name", s["id"]))
                           for s in self.app.config.get_scenes_by_type("greeting")]
        g_options = [f"{n} [{i}]" for i, n in greeting_scenes]
        cur_greeting = path.get("scenes", {}).get("greeting", "") if path else ""
        g_sel = next((f"{n} [{i}]" for i, n in greeting_scenes if i == cur_greeting), "")
        label("Begrüßungsszene:", y);  y += 32
        self._e_greeting = dropdown(g_options if g_options else ["(keine)"], g_sel, y); y += 54

        # Capture count
        label("Aufnahmen:", y);  y += 32
        capture_options = ["0 – Nur Begrüßung", "1 Foto", "2 Fotos", "3 Fotos", "4 Fotos"]
        cur_count = path.get("scenes", {}).get("capture_count", 0) if path else 0
        self._e_capture = dropdown(capture_options, capture_options[min(cur_count, 4)], y); y += 54

        # Collage & print scenes
        collage_scenes = [(s["id"], s.get("name", s["id"]))
                          for s in self.app.config.get_scenes_by_type("collage")]
        print_scenes   = [(s["id"], s.get("name", s["id"]))
                          for s in self.app.config.get_scenes_by_type("print")]

        c_options = [f"{n} [{i}]" for i, n in collage_scenes]
        p_options = [f"{n} [{i}]" for i, n in print_scenes]
        cur_col   = path.get("scenes", {}).get("collage", "") if path else ""
        cur_prt   = path.get("scenes", {}).get("print",   "") if path else ""
        c_sel = next((f"{n} [{i}]" for i, n in collage_scenes if i == cur_col), "")
        p_sel = next((f"{n} [{i}]" for i, n in print_scenes   if i == cur_prt), "")

        label("Collage-Szene (bei ≥1 Foto):", y);  y += 32
        self._e_collage = dropdown(c_options if c_options else ["(keine)"], c_sel, y); y += 54

        label("Druck-Szene (bei ≥1 Foto):", y);  y += 32
        self._e_print = dropdown(p_options if p_options else ["(keine)"], p_sel, y); y += 54

        # Buttons
        self._save_btn = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(x0, y, 160, 44),
            text="Speichern", manager=self._mgr,
        )
        self._cancel_btn = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(x0 + 170, y, 120, 44),
            text="Abbrechen", manager=self._mgr,
        )
        self._editor_widgets += [self._save_btn, self._cancel_btn]

    def _save_editor(self):
        def extract_id(dd_text: str) -> str:
            # format "Name [id]"
            if "[" in dd_text and dd_text.endswith("]"):
                return dd_text.rsplit("[", 1)[1][:-1]
            return ""

        name = self._e_name.get_text().strip() if self._e_name else ""
        if not name:
            return

        try:
            prob = int(self._e_prob.get_text()) if self._e_prob else 0
        except ValueError:
            prob = 0

        capture_text = self._e_capture.selected_option if hasattr(self._e_capture, "selected_option") else "0"
        try:
            count = int(capture_text[0])
        except (ValueError, IndexError):
            count = 0

        greeting_id = extract_id(self._e_greeting.selected_option) if hasattr(self._e_greeting, "selected_option") else ""
        collage_id  = extract_id(self._e_collage.selected_option)  if hasattr(self._e_collage,  "selected_option") else ""
        print_id    = extract_id(self._e_print.selected_option)    if hasattr(self._e_print,    "selected_option") else ""

        # ── Validation ───────────────────────────────────────────────────
        if not greeting_id:
            self.app.show_notification(
                "Pfad konnte nicht gespeichert werden: "
                "Bitte eine Begrüßungsszene auswählen. "
                "Zuerst im Tab 'Szenen' eine Begrüßungsszene anlegen.",
                duration=8.0, level="error"
            )
            return
        if count > 0 and not collage_id:
            self.app.show_notification(
                "Pfad konnte nicht gespeichert werden: "
                "Bitte eine Collage-Szene auswählen (erforderlich bei ≥ 1 Foto).",
                duration=7.0, level="error"
            )
            return
        if count > 0 and not print_id:
            self.app.show_notification(
                "Pfad konnte nicht gespeichert werden: "
                "Bitte eine Druck-Szene auswählen (erforderlich bei ≥ 1 Foto).",
                duration=7.0, level="error"
            )
            return

        scenes_dict = {"greeting": greeting_id, "capture_count": count}
        if count > 0:
            scenes_dict["collage"] = collage_id
            scenes_dict["print"]   = print_id

        if self._editing_id == "__new__":
            new_path = {
                "name": name, "probability": prob,
                "is_default": not self.app.config.get_paths(),
                "scenes": scenes_dict,
            }
            self.app.config.add_path(new_path)
        else:
            existing = self._find_path(self._editing_id)
            if existing:
                updated = dict(existing)
                updated["name"] = name
                if not existing.get("is_default"):
                    updated["probability"] = prob
                updated["scenes"] = scenes_dict
                self.app.config.update_path(self._editing_id, updated)

        self._build_list()
        self._clear_editor()

    def _find_path(self, pid: str) -> dict | None:
        for p in self.app.config.get_paths():
            if p["id"] == pid:
                return p
        return None
