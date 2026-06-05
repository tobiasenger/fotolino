"""
Admin Scenes tab.
Three sub-tabs (Begrüßung / Collage / Druck) with a scene list and create/edit/delete editor.
- Media type toggle dynamically shows/hides photo vs. video fields.
- Browse buttons open a UIFileDialog for each file input.
- Duration is validated against per-type limits.
- Dependency check on delete.
"""
from __future__ import annotations
from pathlib import Path

import pygame
import pygame_gui

from ...constants import (
    SCREEN_W, SCREEN_H, ADMIN_PANEL,
    SCENE_GREETING_MIN, SCENE_GREETING_MAX,
    SCENE_COLLAGE_DURATION, SCENE_PRINT_DURATION,
)
from ..base_screen import get_font
from .file_dialog import open_file_dialog

# Project root – four parents up from this file (src/ui/admin/admin_scenes.py)
_PROJECT_ROOT = Path(__file__).parents[3]

_TOP       = 70
_MARGIN    = 20
_LIST_W    = 440
_PANEL_X   = _LIST_W + _MARGIN * 2
_PANEL_W   = SCREEN_W - _PANEL_X - _MARGIN
_CONTENT_H = SCREEN_H - _TOP - _MARGIN

_SCENE_TYPES  = ["greeting", "collage", "print"]
_SCENE_LABELS = {"greeting": "Begrüßung", "collage": "Collage", "print": "Druck"}

_DURATION_LIMITS = {
    "greeting": (SCENE_GREETING_MIN, SCENE_GREETING_MAX),
    "collage":  (1, SCENE_COLLAGE_DURATION),
    "print":    (1, SCENE_PRINT_DURATION),
}

# Allowed file extensions per field type
_EXT = {
    "image": {".jpg", ".jpeg", ".png"},
    "audio": {".mp3", ".wav"},
    "video": {".mp4", ".avi", ".mov"},
}

# Default start directory for file dialog per field type
_ASSET_DIRS = {
    "image": "assets/images",
    "audio": "assets/sounds",
    "video": "assets/videos",
}


class AdminScenes:
    def __init__(self, app, manager: pygame_gui.UIManager):
        self.app          = app
        self._mgr         = manager
        self._active      = False
        self._active_type = "greeting"

        self._type_btns:  dict = {}
        self._scene_btns: dict = {}
        self._list_widgets:   list = []
        self._editor_widgets: list = []
        self._editing_id: str | None = None

        # Confirm-delete state
        self._confirm_widgets: list = []
        self._pending_delete: str | None = None

        # File dialog state
        self._file_dialog = None
        self._file_dialog_target: str | None = None  # 'image' | 'audio' | 'video'

        # Dynamic field groups (show/hide on media type change)
        self._photo_group: list = []   # image + audio labels, entries, buttons
        self._video_group: list = []   # video label, entry, button

        # Entry widgets (needed in _save_editor and file dialog callback)
        self._e_name    = None
        self._e_type    = None
        self._e_media   = None
        self._e_image   = None
        self._e_audio   = None
        self._e_video   = None
        self._browse_image: pygame_gui.elements.UIButton | None = None
        self._browse_audio: pygame_gui.elements.UIButton | None = None
        self._browse_video: pygame_gui.elements.UIButton | None = None
        self._e_duration   = None
        self._is_photo     = True   # tracks current media type selection

        self._error_msg = ""

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def show(self):
        self._active = True
        self._build_list()

    def hide(self):
        self._active = False
        self._kill_all()

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event):
        if not self._active:
            return

        # ── File dialog result ──────────────────────────────────────────
        if event.type == pygame_gui.UI_FILE_DIALOG_PATH_PICKED:
            picked = Path(event.text)
            try:
                rel = str(picked.relative_to(_PROJECT_ROOT))
            except ValueError:
                rel = str(picked)

            target = self._file_dialog_target
            if target == "image" and self._e_image:
                self._e_image.set_text(rel)
            elif target == "audio" and self._e_audio:
                self._e_audio.set_text(rel)
                # Auto-fill duration from MP3
                if self._e_duration:
                    from ...audio import AudioPlayer
                    dur = AudioPlayer.get_mp3_duration(picked)
                    if dur:
                        self._e_duration.set_text(str(round(dur, 1)))
            elif target == "video" and self._e_video:
                self._e_video.set_text(rel)
                # Auto-fill duration from video
                if self._e_duration:
                    from ...audio import AudioPlayer
                    dur = AudioPlayer.get_video_duration(picked)
                    if dur:
                        self._e_duration.set_text(str(round(dur, 1)))

            self._file_dialog = None
            self._file_dialog_target = None
            return

        # ── Media type dropdown changed → toggle field visibility ───────
        if event.type == pygame_gui.UI_DROP_DOWN_MENU_CHANGED:
            if self._e_media and event.ui_element == self._e_media:
                self._is_photo = (event.text == "Foto + Ton")
                self._update_media_visibility(self._is_photo)
                return

        if event.type != pygame_gui.UI_BUTTON_PRESSED:
            return
        el = event.ui_element

        # ── Sub-tab buttons ─────────────────────────────────────────────
        for k, btn in self._type_btns.items():
            if el == btn:
                self._active_type = k
                self._build_list()
                self._clear_editor()
                return

        # ── Add new scene ───────────────────────────────────────────────
        if el == self._add_btn:
            self._open_editor(None)
            return

        # ── Scene list edit / delete ────────────────────────────────────
        for sid, (ebtn, dbtn) in list(self._scene_btns.items()):
            if el == ebtn:
                scene = self.app.config.get_scene_by_id(sid)
                if scene:
                    self._open_editor(scene)
                return
            if el == dbtn:
                self._confirm_delete(sid)
                return

        # ── Editor buttons ──────────────────────────────────────────────
        if hasattr(self, "_save_btn")   and el == self._save_btn:
            self._save_editor(); return
        if hasattr(self, "_cancel_btn") and el == self._cancel_btn:
            self._clear_editor(); return

        # ── Browse buttons ──────────────────────────────────────────────
        if self._browse_image and el == self._browse_image:
            self._open_file_dialog("image"); return
        if self._browse_audio and el == self._browse_audio:
            self._open_file_dialog("audio"); return
        if self._browse_video and el == self._browse_video:
            self._open_file_dialog("video"); return

        # ── Confirm-delete buttons ──────────────────────────────────────
        if hasattr(self, "_confirm_yes") and el == self._confirm_yes:
            self._do_delete(self._pending_delete)
            self._kill_confirm(); return
        if hasattr(self, "_confirm_no") and el == self._confirm_no:
            self._kill_confirm(); return

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
        for b in self._type_btns.values():
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
            ebtn = pygame_gui.elements.UIButton(
                relative_rect=pygame.Rect(_MARGIN + 4, y, _LIST_W - 94, 44),
                text=f"{name}  |  {mt}  |  {dur:.1f}s",
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
        self._photo_group.clear()
        self._video_group.clear()
        self._editing_id     = None
        self._browse_image   = None
        self._browse_audio   = None
        self._browse_video   = None
        self._e_name = self._e_type = self._e_media = self._e_duration = None
        self._e_image = self._e_audio = self._e_video = None
        self._error_msg = ""
        if self._file_dialog:
            try: self._file_dialog.kill()
            except Exception: pass
            self._file_dialog = None

    def _clear_editor(self):
        self._kill_editor()

    def _open_editor(self, scene: dict | None):
        self._clear_editor()
        self._editing_id = scene["id"] if scene else "__new__"
        scene = scene or {}

        x0 = _PANEL_X + 20
        w  = _PANEL_W - 40
        ENTRY_W  = w - 115   # width of text entries next to browse button
        BROWSE_W = 108        # width of browse button

        def reg(*widgets):
            """Register widgets to be killed when editor closes."""
            for wg in widgets:
                self._editor_widgets.append(wg)
            return widgets[-1] if len(widgets) == 1 else widgets

        def lbl(text, yy):
            lb = pygame_gui.elements.UILabel(
                relative_rect=pygame.Rect(x0, yy, w, 28),
                text=text, manager=self._mgr,
            )
            return reg(lb)

        def entry(val, yy, width=None):
            width = width if width is not None else w
            e = pygame_gui.elements.UITextEntryLine(
                relative_rect=pygame.Rect(x0, yy, width, 40),
                manager=self._mgr,
            )
            e.set_text(str(val))
            return reg(e)

        def browse_btn(yy):
            btn = pygame_gui.elements.UIButton(
                relative_rect=pygame.Rect(x0 + ENTRY_W + 10, yy, BROWSE_W, 40),
                text="📂 Suchen",
                manager=self._mgr,
            )
            return reg(btn)

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
            return reg(dd)

        # ── Fixed fields ─────────────────────────────────────────────────
        y = _TOP + 20

        # Scene type is fixed to whichever tab is active – no dropdown needed
        active_label = _SCENE_LABELS.get(self._active_type, self._active_type)
        lbl(f"Szenentyp: {active_label}  (bestimmt durch aktiven Tab)", y);  y += 34

        lbl("Name:", y);  y += 30
        self._e_name = entry(scene.get("name", ""), y);  y += 52

        lbl("Medientyp:", y);  y += 30
        is_photo = scene.get("media_type", "photo") == "photo"
        self._is_photo = is_photo   # initialise tracked state
        self._e_media = dropdown(["Foto + Ton", "Video"],
                                 "Foto + Ton" if is_photo else "Video", y);  y += 54

        # ── Dynamic fields (photo and video groups share the same Y) ─────
        group_y = y   # both groups start here

        # Photo group: image + audio
        lbl_img = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(x0, group_y, w, 28),
            text="Bilddatei (.jpg / .png):", manager=self._mgr,
        )
        reg(lbl_img)
        self._e_image = pygame_gui.elements.UITextEntryLine(
            relative_rect=pygame.Rect(x0, group_y + 30, ENTRY_W, 40),
            manager=self._mgr,
        )
        self._e_image.set_text(scene.get("image", ""))
        reg(self._e_image)
        self._browse_image = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(x0 + ENTRY_W + 10, group_y + 30, BROWSE_W, 40),
            text="📂 Suchen", manager=self._mgr,
        )
        reg(self._browse_image)

        lbl_aud = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(x0, group_y + 80, w, 28),
            text="Audiodatei (.mp3):", manager=self._mgr,
        )
        reg(lbl_aud)
        self._e_audio = pygame_gui.elements.UITextEntryLine(
            relative_rect=pygame.Rect(x0, group_y + 110, ENTRY_W, 40),
            manager=self._mgr,
        )
        self._e_audio.set_text(scene.get("audio", ""))
        reg(self._e_audio)
        self._browse_audio = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(x0 + ENTRY_W + 10, group_y + 110, BROWSE_W, 40),
            text="📂 Suchen", manager=self._mgr,
        )
        reg(self._browse_audio)

        self._photo_group = [lbl_img, self._e_image, self._browse_image,
                             lbl_aud, self._e_audio, self._browse_audio]

        # Video group: video (same starting Y as photo group)
        lbl_vid = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(x0, group_y, w, 28),
            text="Videodatei (.mp4 / .mov):", manager=self._mgr,
        )
        reg(lbl_vid)
        self._e_video = pygame_gui.elements.UITextEntryLine(
            relative_rect=pygame.Rect(x0, group_y + 30, ENTRY_W, 40),
            manager=self._mgr,
        )
        self._e_video.set_text(scene.get("video", ""))
        reg(self._e_video)
        self._browse_video = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(x0 + ENTRY_W + 10, group_y + 30, BROWSE_W, 40),
            text="📂 Suchen", manager=self._mgr,
        )
        reg(self._browse_video)

        self._video_group = [lbl_vid, self._e_video, self._browse_video]

        # ── Duration entry (auto-filled from file, but manually editable) ─
        dur_y = group_y + 165
        lbl_dur = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(x0, dur_y, w, 28),
            text="Dauer (Sekunden) – wird aus Datei ermittelt, kann manuell eingegeben werden:",
            manager=self._mgr,
        )
        reg(lbl_dur)
        self._e_duration = pygame_gui.elements.UITextEntryLine(
            relative_rect=pygame.Rect(x0, dur_y + 30, 120, 40),
            manager=self._mgr,
        )
        cur_dur = scene.get("duration", 0)
        self._e_duration.set_text(str(cur_dur) if cur_dur else "")
        reg(self._e_duration)

        lbl_limits = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(x0 + 130, dur_y + 38, w - 130, 24),
            text=f"Erlaubter Bereich für '{active_label}': "
                 f"{_DURATION_LIMITS.get(self._active_type, (0, 0))[0]}–"
                 f"{_DURATION_LIMITS.get(self._active_type, (0, 0))[1]} Sekunden",
            manager=self._mgr,
        )
        reg(lbl_limits)

        btn_y = dur_y + 80
        self._save_btn = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(x0, btn_y, 160, 44),
            text="Speichern", manager=self._mgr,
        )
        self._cancel_btn = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(x0 + 170, btn_y, 130, 44),
            text="Abbrechen", manager=self._mgr,
        )
        reg(self._save_btn, self._cancel_btn)

        # Apply initial visibility
        self._update_media_visibility(is_photo)

    def _update_media_visibility(self, is_photo: bool):
        """Show photo fields or video fields depending on media type selection."""
        for w in self._photo_group:
            try:
                w.show() if is_photo else w.hide()
            except Exception:
                pass
        for w in self._video_group:
            try:
                w.hide() if is_photo else w.show()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # File dialog
    # ------------------------------------------------------------------

    def _open_file_dialog(self, target: str):
        if self._file_dialog:
            try: self._file_dialog.kill()
            except Exception: pass
            self._file_dialog = None

        self._file_dialog_target = target
        start_dir = _PROJECT_ROOT / _ASSET_DIRS.get(target, "assets")
        if not start_dir.exists():
            start_dir = _PROJECT_ROOT

        self._file_dialog = open_file_dialog(
            manager=self._mgr,
            initial_path=start_dir,
            title="Datei auswählen",
            extensions=_EXT.get(target),
        )

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def _save_editor(self):
        self._error_msg = ""

        # Scene type is always the active tab – no dropdown involved
        scene_type = self._active_type
        is_photo   = self._is_photo   # set in _open_editor and updated on dropdown change
        name       = self._e_name.get_text().strip()  if self._e_name  else ""
        image      = self._e_image.get_text().strip()  if self._e_image else ""
        audio      = self._e_audio.get_text().strip()  if self._e_audio else ""
        video      = self._e_video.get_text().strip()  if self._e_video else ""
        dur_text   = self._e_duration.get_text().strip() if self._e_duration else ""

        if not name:
            self._error_msg = "Bitte einen Namen eingeben."; return

        # Validate that at least the primary media file is provided
        if is_photo and not image and not audio:
            self._error_msg = "Bitte mindestens eine Bilddatei oder Audiodatei angeben."; return
        if not is_photo and not video:
            self._error_msg = "Bitte eine Videodatei angeben."; return

        from ...audio import AudioPlayer

        # Step 1: try manual entry
        duration = 0.0
        if dur_text:
            try:
                duration = float(dur_text.replace(",", "."))
            except ValueError:
                self._error_msg = "Dauer muss eine Zahl sein (z.B. 8.5)."; return

        # Step 2: if not set manually, auto-detect from file
        if duration <= 0:
            if is_photo and audio:
                p = self.app.config.resolve_asset(audio)
                if not p.exists():
                    self._error_msg = (f"Audiodatei nicht gefunden: {audio} – "
                                       "bitte Pfad prüfen oder Datei über Browser wählen."); return
                dur = AudioPlayer.get_mp3_duration(p)
                if dur is None:
                    self._error_msg = ("Dauer konnte nicht aus der MP3 gelesen werden. "
                                       "Bitte Dauer manuell eingeben. "
                                       "(mutagen installiert? sudo pip3 install mutagen)"); return
                duration = dur
                if self._e_duration:
                    self._e_duration.set_text(str(round(duration, 1)))
            elif is_photo and not audio:
                # Image only: use minimum duration for this scene type
                duration = float(_DURATION_LIMITS[scene_type][0])
            elif not is_photo and video:
                p = self.app.config.resolve_asset(video)
                if not p.exists():
                    self._error_msg = (f"Videodatei nicht gefunden: {video} – "
                                       "bitte Pfad prüfen oder Datei über Browser wählen."); return
                dur = AudioPlayer.get_video_duration(p)
                if dur is None:
                    self._error_msg = ("Dauer konnte nicht aus dem Video gelesen werden. "
                                       "Bitte Dauer manuell eingeben. "
                                       "(opencv-python-headless installiert? pip3 install opencv-python-headless)"); return
                duration = dur
                if self._e_duration:
                    self._e_duration.set_text(str(round(duration, 1)))
            else:
                self._error_msg = ("Keine Mediendatei angegeben und keine manuelle Dauer. "
                                   "Bitte Datei auswählen oder Dauer eingeben."); return

        lo, hi = _DURATION_LIMITS[scene_type]
        if not (lo <= duration <= hi):
            self._error_msg = (
                f"Dauer {duration:.1f}s liegt außerhalb des erlaubten Bereichs "
                f"({lo}–{hi}s) für Szenentyp '{_SCENE_LABELS[scene_type]}'. "
                "Bitte Dauer anpassen."
            ); return

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
    # Delete + confirm dialog
    # ------------------------------------------------------------------

    def _kill_confirm(self):
        for w in self._confirm_widgets:
            try: w.kill()
            except Exception: pass
        self._confirm_widgets.clear()
        self._pending_delete = None

    def _confirm_delete(self, scene_id: str):
        self._kill_confirm()
        deps     = self.app.config.paths_using_scene(scene_id)
        dep_names = ", ".join(p.get("name", p["id"]) for p in deps)
        msg = (
            f"Szene wird von {len(deps)} Pfad(en) verwendet: {dep_names}. "
            "Diese Pfade werden ebenfalls gelöscht. Fortfahren?"
        ) if deps else "Szene wirklich löschen?"

        self._pending_delete = scene_id
        cx, cy = SCREEN_W // 2, SCREEN_H // 2
        lbl = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(cx - 380, cy - 80, 760, 60),
            text=msg, manager=self._mgr,
        )
        yes = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(cx - 140, cy, 130, 44),
            text="Ja, löschen", manager=self._mgr,
        )
        no = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(cx + 10, cy, 130, 44),
            text="Abbrechen", manager=self._mgr,
        )
        self._confirm_yes     = yes
        self._confirm_no      = no
        self._confirm_widgets = [lbl, yes, no]

    def _do_delete(self, scene_id: str):
        self.app.config.delete_scene(scene_id)
        self._build_list()
        self._clear_editor()
