"""
Admin Scenes tab.
Three sub-tabs (Begrüßung / Collage / Druck) with a scene list and create/edit/delete editor.
Validates media duration against per-type limits.
Dependency check on delete (paths using the scene).
"""
from __future__ import annotations
from pathlib import Path

import pygame
import pygame_gui

from ...constants import (
    SCREEN_W, SCREEN_H, ADMIN_BG, ADMIN_PANEL,
    COLOR_TEXT, COLOR_ACCENT, COLOR_ERROR,
    SCENE_GREETING_MIN, SCENE_GREETING_MAX,
    SCENE_COLLAGE_DURATION, SCENE_PRINT_DURATION,
)
from ..base_screen import get_font, draw_text_centered

_TOP     = 70
_MARGIN  = 20
_LIST_W  = 440
_PANEL_X = _LIST_W + _MARGIN * 2
_PANEL_W = SCREEN_W - _PANEL_X - _MARGIN
_CONTENT_H = SCREEN_H - _TOP - _MARGIN

_SCENE_TYPES = ["greeting", "collage", "print"]
_SCENE_LABELS = {"greeting": "Begrüßung", "collage": "Collage", "print": "Druck"}

_DURATION_LIMITS = {
    "greeting": (SCENE_GREETING_MIN, SCENE_GREETING_MAX),
    "collage":  (1, SCENE_COLLAGE_DURATION),
    "print":    (1, SCENE_PRINT_DURATION),
}


def _extract_id(dd_text: str) -> str:
    if "[" in dd_text and dd_text.endswith("]"):
        return dd_text.rsplit("[", 1)[1][:-1]
    return ""


class AdminScenes:
    def __init__(self, app, manager: pygame_gui.UIManager):
        self.app   = app
        self._mgr  = manager
        self._active = False
        self._active_type = "greeting"

        self._type_btns: dict  = {}   # type_key -> UIButton
        self._scene_btns: dict = {}   # scene_id -> (edit_btn, del_btn)
        self._list_widgets: list = []
        self._editor_widgets: list = []
        self._editing_id: str | None = None
        self._confirm_widgets: list  = []
        self._pending_delete: str | None = None
        self._error_msg = ""

    # ------------------------------------------------------------------

    def show(self):
        self._active = True
        self._build_list()

    def hide(self):
        self._active = False
        self._kill_all()

    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event):
        if not self._active or event.type != pygame_gui.UI_BUTTON_PRESSED:
            return
        el = event.ui_element

        # Sub-tab buttons
        for k, btn in self._type_btns.items():
            if el == btn:
                self._active_type = k
                self._build_list()
                self._clear_editor()
                return

        if el == self._add_btn:
            self._open_editor(None)
            return

        for sid, (ebtn, dbtn) in list(self._scene_btns.items()):
            if el == ebtn:
                scene = self.app.config.get_scene_by_id(sid)
                if scene:
                    self._open_editor(scene)
                return
            if el == dbtn:
                self._confirm_delete(sid)
                return

        # Editor actions
        if hasattr(self, "_save_btn") and el == self._save_btn:
            self._save_editor()
            return
        if hasattr(self, "_cancel_btn") and el == self._cancel_btn:
            self._clear_editor()
            return

        # Confirm dialog
        if hasattr(self, "_confirm_yes") and el == self._confirm_yes:
            self._do_delete(self._pending_delete)
            self._kill_confirm()
            return
        if hasattr(self, "_confirm_no") and el == self._confirm_no:
            self._kill_confirm()
            return

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
        if self._error_msg:
            font = get_font(22)
            surf = font.render(self._error_msg, True, (220, 60, 60))
            surface.blit(surf, (_PANEL_X + 20, SCREEN_H - 60))

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def _kill_all(self):
        for w in self._list_widgets:
            try: w.kill()
            except Exception: pass
        self._list_widgets.clear()
        for ebtn, dbtn in self._scene_btns.values():
            try: ebtn.kill()
            except Exception: pass
            try: dbtn.kill()
            except Exception: pass
        self._scene_btns.clear()
        for k, b in self._type_btns.items():
            try: b.kill()
            except Exception: pass
        self._type_btns.clear()
        self._kill_editor()
        self._kill_confirm()

    def _build_list(self):
        for w in self._list_widgets:
            try: w.kill()
            except Exception: pass
        self._list_widgets.clear()
        for ebtn, dbtn in self._scene_btns.values():
            try: ebtn.kill()
            except Exception: pass
            try: dbtn.kill()
            except Exception: pass
        self._scene_btns.clear()
        for b in self._type_btns.values():
            try: b.kill()
            except Exception: pass
        self._type_btns.clear()

        # Sub-tab buttons
        tab_w = (_LIST_W - 10) // 3
        for i, key in enumerate(_SCENE_TYPES):
            btn = pygame_gui.elements.UIButton(
                relative_rect=pygame.Rect(_MARGIN + 5 + i * tab_w, _TOP + 8, tab_w - 4, 36),
                text=_SCENE_LABELS[key],
                manager=self._mgr,
            )
            self._type_btns[key] = btn
            self._list_widgets.append(btn)

        self._add_btn = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(_MARGIN + _LIST_W - 160, _TOP + 52, 150, 38),
            text="+ Neue Szene",
            manager=self._mgr,
        )
        self._list_widgets.append(self._add_btn)

        scenes = self.app.config.get_scenes_by_type(self._active_type)
        y = _TOP + 100
        for scene in scenes:
            sid  = scene["id"]
            name = scene.get("name", "(kein Name)")
            dur  = scene.get("duration", 0)
            mt   = "Foto" if scene.get("media_type") == "photo" else "Video"
            label = f"{name}  |  {mt}  |  {dur:.1f}s"
            ebtn = pygame_gui.elements.UIButton(
                relative_rect=pygame.Rect(_MARGIN + 4, y, _LIST_W - 94, 44),
                text=label,
                manager=self._mgr,
            )
            dbtn = pygame_gui.elements.UIButton(
                relative_rect=pygame.Rect(_MARGIN + _LIST_W - 82, y, 74, 44),
                text="Löschen",
                manager=self._mgr,
            )
            self._scene_btns[sid] = (ebtn, dbtn)
            y += 52
            if y + 52 > _TOP + _CONTENT_H:
                break

    # ------------------------------------------------------------------
    # Editor
    # ------------------------------------------------------------------

    def _kill_editor(self):
        for w in self._editor_widgets:
            try: w.kill()
            except Exception: pass
        self._editor_widgets.clear()
        self._editing_id = None
        self._error_msg  = ""

    def _clear_editor(self):
        self._kill_editor()

    def _open_editor(self, scene: dict | None):
        self._clear_editor()
        self._editing_id = scene["id"] if scene else "__new__"
        scene = scene or {}

        x0, y, w = _PANEL_X + 20, _TOP + 20, _PANEL_W - 40

        def lbl(text, yy):
            lb = pygame_gui.elements.UILabel(
                relative_rect=pygame.Rect(x0, yy, w, 28),
                text=text, manager=self._mgr,
            )
            self._editor_widgets.append(lb)

        def entry(val, yy):
            e = pygame_gui.elements.UITextEntryLine(
                relative_rect=pygame.Rect(x0, yy, w, 40),
                manager=self._mgr,
            )
            e.set_text(str(val))
            self._editor_widgets.append(e)
            return e

        def dropdown(options, sel, yy):
            if not options:
                options = ["(leer)"]
            if sel not in options:
                sel = options[0]
            dd = pygame_gui.elements.UIDropDownMenu(
                options_list=options, starting_option=sel,
                relative_rect=pygame.Rect(x0, yy, w, 44),
                manager=self._mgr,
            )
            self._editor_widgets.append(dd)
            return dd

        lbl("Name:", y); y += 30
        self._e_name = entry(scene.get("name", ""), y); y += 50

        lbl("Szenentyp:", y); y += 30
        self._e_type = dropdown(
            list(_SCENE_LABELS.values()),
            _SCENE_LABELS.get(scene.get("type", self._active_type), "Begrüßung"), y
        ); y += 54

        lbl("Medientyp:", y); y += 30
        media_opts = ["Foto + Ton", "Video"]
        cur_media = "Foto + Ton" if scene.get("media_type", "photo") == "photo" else "Video"
        self._e_media = dropdown(media_opts, cur_media, y); y += 54

        lbl("Bilddatei (bei Foto):", y); y += 30
        self._e_image = entry(scene.get("image", ""), y); y += 50

        lbl("Audiodatei (bei Foto, .mp3):", y); y += 30
        self._e_audio = entry(scene.get("audio", ""), y); y += 50

        lbl("Videodatei (.mp4):", y); y += 30
        self._e_video = entry(scene.get("video", ""), y); y += 50

        lbl("→ Pfad relativ zu Projektordner, z.B. assets/sounds/welcome.mp3", y); y += 30

        self._duration_lbl = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(x0, y, w, 28),
            text="Dauer wird aus Mediendatei berechnet.",
            manager=self._mgr,
        )
        self._editor_widgets.append(self._duration_lbl)
        y += 38

        self._save_btn = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(x0, y, 150, 44),
            text="Speichern", manager=self._mgr,
        )
        self._cancel_btn = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(x0 + 160, y, 120, 44),
            text="Abbrechen", manager=self._mgr,
        )
        self._editor_widgets += [self._save_btn, self._cancel_btn]

    def _save_editor(self):
        self._error_msg = ""
        type_text  = self._e_type.selected_option if hasattr(self._e_type, "selected_option") else ""
        scene_type = next((k for k, v in _SCENE_LABELS.items() if v == type_text), self._active_type)
        media_text = self._e_media.selected_option if hasattr(self._e_media, "selected_option") else ""
        is_photo   = media_text == "Foto + Ton"
        name       = self._e_name.get_text().strip()
        image      = self._e_image.get_text().strip()
        audio      = self._e_audio.get_text().strip()
        video      = self._e_video.get_text().strip()

        if not name:
            self._error_msg = "Bitte einen Namen eingeben."; return

        # Determine duration
        duration = 0.0
        if is_photo:
            if audio:
                p = self.app.config.resolve_asset(audio)
                from ...audio import AudioPlayer
                dur = AudioPlayer.get_mp3_duration(p)
                duration = dur if dur else 0.0
            else:
                # No audio – use minimum duration for type
                duration = _DURATION_LIMITS[scene_type][0]
        else:
            if video:
                p = self.app.config.resolve_asset(video)
                from ...audio import AudioPlayer
                dur = AudioPlayer.get_video_duration(p)
                duration = dur if dur else 0.0

        lo, hi = _DURATION_LIMITS[scene_type]
        if duration < lo or duration > hi:
            self._error_msg = (f"Dauer {duration:.1f}s liegt außerhalb des erlaubten "
                               f"Bereichs ({lo}–{hi}s) für diesen Szenentyp."); return

        scene_data = {
            "name": name, "type": scene_type,
            "media_type": "photo" if is_photo else "video",
            "duration": round(duration, 2),
            "image": image, "audio": audio, "video": video,
        }

        if self._editing_id == "__new__":
            self.app.config.add_scene(scene_data)
        else:
            scene_data["id"] = self._editing_id
            self.app.config.update_scene(self._editing_id, scene_data)

        self._build_list()
        self._clear_editor()

    # ------------------------------------------------------------------
    # Delete + confirm
    # ------------------------------------------------------------------

    def _kill_confirm(self):
        for w in self._confirm_widgets:
            try: w.kill()
            except Exception: pass
        self._confirm_widgets.clear()
        self._pending_delete = None

    def _confirm_delete(self, scene_id: str):
        self._kill_confirm()
        deps = self.app.config.paths_using_scene(scene_id)
        dep_names = ", ".join(p.get("name", p["id"]) for p in deps)
        msg = (f"Szene wird von {len(deps)} Pfad(en) verwendet: {dep_names}. "
               "Diese Pfade werden ebenfalls gelöscht. Fortfahren?") if deps else \
              "Szene wirklich löschen?"
        self._pending_delete = scene_id
        cx, cy = SCREEN_W // 2, SCREEN_H // 2
        lbl = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(cx - 350, cy - 80, 700, 60),
            text=msg, manager=self._mgr,
        )
        yes = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(cx - 130, cy, 120, 44),
            text="Ja, löschen", manager=self._mgr,
        )
        no = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(cx + 20, cy, 120, 44),
            text="Abbrechen", manager=self._mgr,
        )
        self._confirm_yes  = yes
        self._confirm_no   = no
        self._confirm_widgets = [lbl, yes, no]

    def _do_delete(self, scene_id: str):
        self.app.config.delete_scene(scene_id)
        self._build_list()
        self._clear_editor()
