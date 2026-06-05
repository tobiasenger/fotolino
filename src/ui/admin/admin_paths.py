"""
Admin Paths tab.
Dynamic form: greeting scene (required) + photo count (0–4).
When count = 0, only greeting is played (no collage/print).
When count ≥ 1, collage and print scene fields appear and are mandatory.
Selections are tracked in instance variables so no reliance on
UIDropDownMenu.selected_option being available before a change event.
"""
from __future__ import annotations

import pygame
import pygame_gui

from ...constants import (
    SCREEN_W, SCREEN_H, ADMIN_PANEL,
)

_TOP       = 70
_MARGIN    = 20
_LIST_W    = 440
_PANEL_X   = _LIST_W + _MARGIN * 2
_PANEL_W   = SCREEN_W - _PANEL_X - _MARGIN
_CONTENT_H = SCREEN_H - _TOP - _MARGIN

# Sentinel shown when no scene has been chosen yet
_NONE = "(Auswählen…)"

_COUNT_OPTIONS = [
    "0 – Nur Begrüßung",
    "1 Foto",
    "2 Fotos",
    "3 Fotos",
    "4 Fotos",
]


def _count_from_label(text: str) -> int:
    try:
        return int(text[0])
    except (ValueError, IndexError):
        return 0


class AdminPaths:
    def __init__(self, app, manager: pygame_gui.UIManager):
        self.app     = app
        self._mgr    = manager
        self._active = False

        self._widgets:       list = []
        self._editor_widgets: list = []
        self._path_buttons:   dict = {}   # path_id -> (edit_btn, del_btn)
        self._editing_id: str | None = None

        # Name → scene_id mappings for each dropdown (populated in _open_editor)
        self._greeting_opts: dict = {}
        self._collage_opts:  dict = {}
        self._print_opts:    dict = {}

        # Currently selected labels (updated on UI_DROP_DOWN_MENU_CHANGED)
        self._sel_greeting = _NONE
        self._sel_collage  = _NONE
        self._sel_print    = _NONE
        self._sel_count    = _COUNT_OPTIONS[0]

        # Widgets that are shown/hidden based on capture count
        self._photo_detail_widgets: list = []

        # Editor widget refs
        self._e_name:     pygame_gui.elements.UITextEntryLine | None = None
        self._e_prob:     pygame_gui.elements.UITextEntryLine | None = None
        self._e_greeting: pygame_gui.elements.UIDropDownMenu | None = None
        self._e_capture:  pygame_gui.elements.UIDropDownMenu | None = None
        self._e_collage:  pygame_gui.elements.UIDropDownMenu | None = None
        self._e_print:    pygame_gui.elements.UIDropDownMenu | None = None
        self._save_btn:   pygame_gui.elements.UIButton | None = None
        self._cancel_btn: pygame_gui.elements.UIButton | None = None

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

        # Track dropdown selections so _save_editor can read them reliably
        # regardless of pygame_gui version behaviour with selected_option.
        if event.type == pygame_gui.UI_DROP_DOWN_MENU_CHANGED:
            el = event.ui_element
            if self._e_capture and el == self._e_capture:
                self._sel_count = event.text
                self._update_count_visibility()
            elif self._e_greeting and el == self._e_greeting:
                self._sel_greeting = event.text
            elif self._e_collage and el == self._e_collage:
                self._sel_collage = event.text
            elif self._e_print and el == self._e_print:
                self._sel_print = event.text
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

        if self._save_btn and el == self._save_btn:
            self._save_editor()
        elif self._cancel_btn and el == self._cancel_btn:
            self._clear_editor()

    def update(self, dt: float):
        pass

    def draw(self, surface: pygame.Surface):
        if not self._active:
            return
        pygame.draw.rect(surface, ADMIN_PANEL,
                         (_MARGIN, _TOP, _LIST_W, _CONTENT_H), border_radius=8)
        if self._editing_id is not None:
            pygame.draw.rect(surface, ADMIN_PANEL,
                             (_PANEL_X, _TOP, _PANEL_W, _CONTENT_H), border_radius=8)

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
        self._photo_detail_widgets.clear()
        self._e_name = self._e_prob = self._e_greeting = None
        self._e_capture = self._e_collage = self._e_print = None
        self._save_btn = self._cancel_btn = None

    def _clear_editor(self):
        self._kill_editor()
        self._editing_id = None

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def _build_list(self):
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

        self._add_btn = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(_MARGIN + _LIST_W - 160, _TOP + 10, 150, 40),
            text="+ Neuer Pfad",
            manager=self._mgr,
        )
        self._widgets.append(self._add_btn)

        paths = self.app.config.get_paths()
        y = _TOP + 60
        for path in paths:
            pid     = path["id"]
            name    = path.get("name", "(kein Name)")
            prob    = (self.app.config.compute_default_probability()
                       if path.get("is_default") else path.get("probability", 0))
            dtag    = " ★" if path.get("is_default") else ""
            capture = path.get("scenes", {}).get("capture_count", 0)
            label   = f"{name}{dtag}  |  {prob}%  |  {capture} Fotos"

            edit_btn = pygame_gui.elements.UIButton(
                relative_rect=pygame.Rect(_MARGIN + 4, y, _LIST_W - 100, 44),
                text=label, manager=self._mgr,
            )
            del_btn = pygame_gui.elements.UIButton(
                relative_rect=pygame.Rect(_MARGIN + _LIST_W - 88, y, 80, 44),
                text="Löschen", manager=self._mgr,
            )
            self._path_buttons[pid] = (edit_btn, del_btn)
            y += 52
            if y + 52 > _TOP + _CONTENT_H:
                break

    # ------------------------------------------------------------------
    # Editor
    # ------------------------------------------------------------------

    def _open_editor(self, path: dict | None):
        self._clear_editor()
        self._editing_id = path["id"] if path else "__new__"

        x0 = _PANEL_X + 20
        y  = _TOP + 20
        w  = _PANEL_W - 40

        def reg(widget):
            self._editor_widgets.append(widget)
            return widget

        def lbl(text, yy, height=28):
            return reg(pygame_gui.elements.UILabel(
                relative_rect=pygame.Rect(x0, yy, w, height),
                text=text, manager=self._mgr,
            ))

        def entry(initial, yy, width=None):
            e = reg(pygame_gui.elements.UITextEntryLine(
                relative_rect=pygame.Rect(x0, yy, width or w, 40),
                manager=self._mgr,
            ))
            e.set_text(str(initial))
            return e

        def ddmenu(options: list, sel: str, yy: int):
            if not options:
                options = [_NONE]
            if sel not in options:
                sel = options[0]
            return reg(pygame_gui.elements.UIDropDownMenu(
                options_list=options, starting_option=sel,
                relative_rect=pygame.Rect(x0, yy, w, 44),
                manager=self._mgr,
            ))

        # ── Build name→id maps ──────────────────────────────────────────
        def _build_map(scene_type: str) -> dict:
            m = {_NONE: ""}
            for s in self.app.config.get_scenes_by_type(scene_type):
                m[s.get("name", s["id"])] = s["id"]
            return m

        self._greeting_opts = _build_map("greeting")
        self._collage_opts  = _build_map("collage")
        self._print_opts    = _build_map("print")

        def _find_label(opts: dict, scene_id: str) -> str:
            return next((lbl for lbl, sid in opts.items()
                         if sid == scene_id and lbl != _NONE), _NONE)

        scenes_cfg = path.get("scenes", {}) if path else {}
        self._sel_greeting = _find_label(self._greeting_opts, scenes_cfg.get("greeting", ""))
        self._sel_collage  = _find_label(self._collage_opts,  scenes_cfg.get("collage",  ""))
        self._sel_print    = _find_label(self._print_opts,    scenes_cfg.get("print",    ""))
        cur_count          = scenes_cfg.get("capture_count", 0)
        self._sel_count    = _COUNT_OPTIONS[min(cur_count, 4)]

        # ── Fixed fields ────────────────────────────────────────────────
        lbl("Name:", y);  y += 30
        self._e_name = entry(path.get("name", "") if path else "", y);  y += 50

        if path and path.get("is_default"):
            lbl(f"★ Standard-Pfad  –  Wahrscheinlichkeit: "
                f"{self.app.config.compute_default_probability()}%", y, 36)
            y += 44
            self._e_prob = None
        else:
            lbl("Wahrscheinlichkeit (%):", y);  y += 30
            self._e_prob = entry(str(path.get("probability", 5)) if path else "5", y, 120)
            y += 50

        lbl("Begrüßungsszene:", y);  y += 30
        self._e_greeting = ddmenu(list(self._greeting_opts.keys()), self._sel_greeting, y)
        y += 54

        lbl("Anzahl Fotos:", y);  y += 30
        self._e_capture = ddmenu(_COUNT_OPTIONS, self._sel_count, y)
        y += 54

        # ── Conditional fields (count ≥ 1) ──────────────────────────────
        lbl_col = lbl("Collage-Szene:", y);  y += 30
        self._e_collage = ddmenu(list(self._collage_opts.keys()), self._sel_collage, y);  y += 54
        lbl_prt = lbl("Druck-Szene:", y);  y += 30
        self._e_print   = ddmenu(list(self._print_opts.keys()),   self._sel_print,   y);  y += 54

        self._photo_detail_widgets = [lbl_col, self._e_collage, lbl_prt, self._e_print]

        # ── Action buttons ───────────────────────────────────────────────
        self._save_btn = reg(pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(x0, y, 160, 44),
            text="Speichern", manager=self._mgr,
        ))
        self._cancel_btn = reg(pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(x0 + 170, y, 120, 44),
            text="Abbrechen", manager=self._mgr,
        ))

        self._update_count_visibility()

    def _update_count_visibility(self):
        show = _count_from_label(self._sel_count) > 0
        for w in self._photo_detail_widgets:
            try:
                w.show() if show else w.hide()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def _save_editor(self):
        name = self._e_name.get_text().strip() if self._e_name else ""
        if not name:
            self.app.show_notification("Bitte einen Namen eingeben.", level="error")
            return

        try:
            prob = int(self._e_prob.get_text()) if self._e_prob else 0
        except ValueError:
            prob = 0

        count = _count_from_label(self._sel_count)

        greeting_id = self._greeting_opts.get(self._sel_greeting, "")
        if not greeting_id:
            self.app.show_notification(
                "Bitte eine Begrüßungsszene auswählen. "
                "(Tab 'Szenen' → Begrüßung → neue Szene anlegen)",
                duration=8.0, level="error",
            )
            return

        scenes_dict: dict = {"greeting": greeting_id, "capture_count": count}

        if count > 0:
            collage_id = self._collage_opts.get(self._sel_collage, "")
            if not collage_id:
                self.app.show_notification(
                    "Bitte eine Collage-Szene auswählen.",
                    duration=7.0, level="error",
                )
                return
            print_id = self._print_opts.get(self._sel_print, "")
            if not print_id:
                self.app.show_notification(
                    "Bitte eine Druck-Szene auswählen.",
                    duration=7.0, level="error",
                )
                return
            scenes_dict["collage"] = collage_id
            scenes_dict["print"]   = print_id

        if self._editing_id == "__new__":
            self.app.config.add_path({
                "name": name,
                "probability": prob,
                "is_default": not self.app.config.get_paths(),
                "scenes": scenes_dict,
            })
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
