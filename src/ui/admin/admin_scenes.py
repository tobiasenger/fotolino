"""
Admin Scenes tab (PyQt6).
Sub-tab bar (Begrüßung / Collage / Druck), scene list, and an editor form
with file-browse rows and media-format validation.

Scene audio plays via VLC → WAV + MP3 + OGG allowed.
Scene video plays via VLC → MP4 + AVI + MOV allowed (greeting only).
Media duration is derived from the file and validated against the duration
limits configured in the admin settings ("Zeiten" tab):
  * greeting – media duration must lie within [min, max]
  * collage / print – image+audio only; the screen runs for the fixed
    configured duration, the audio may be at most that long
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from ...audio import AudioPlayer
from ..widgets import FileSelectRow, add_form_section, make_hint, set_kind

_SCENE_TYPES = ["greeting", "collage", "print"]
_SCENE_LABELS = {"greeting": "Begrüßung", "collage": "Collage", "print": "Druck"}

_AUDIO_EXTS = {".wav", ".mp3", ".ogg"}
_VIDEO_EXTS = {".mp4", ".avi", ".mov"}
_IMAGE_EXTS = {".jpg", ".jpeg", ".png"}


class AdminScenes(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self._active_type = _SCENE_TYPES[0]
        self._editing_id: str | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        # ---- Header ----
        title = QLabel("Szenen")
        set_kind(title, "title")
        root.addWidget(title)
        root.addWidget(make_hint(
            "Szenen sind die Bausteine eines Durchlaufs: Begrüßung, Collage- "
            "und Druck-Anzeige. Pfade (nächster Tab) verknüpfen sie zu einem "
            "Ablauf."))

        content = QHBoxLayout()
        content.setSpacing(16)
        root.addLayout(content, 1)

        # ---- Left: type tabs + scene list ----
        left = QVBoxLayout()
        left.setSpacing(10)
        tab_row = QHBoxLayout()
        self._type_btns = {}
        for key in _SCENE_TYPES:
            b = QPushButton(_SCENE_LABELS[key])
            b.setCheckable(True)
            set_kind(b, "pill")
            b.clicked.connect(lambda _, k=key: self._switch_type(k))
            tab_row.addWidget(b)
            self._type_btns[key] = b
        left.addLayout(tab_row)

        self._list = QListWidget()
        self._list.itemClicked.connect(self._on_select)
        left.addWidget(self._list, 1)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("+ Neue Szene")
        set_kind(add_btn, "primary")
        add_btn.clicked.connect(self._new_scene)
        del_btn = QPushButton("Löschen")
        set_kind(del_btn, "danger")
        del_btn.clicked.connect(self._delete_selected)
        btn_row.addWidget(add_btn, 1)
        btn_row.addWidget(del_btn)
        left.addLayout(btn_row)

        left_w = QWidget()
        left_w.setLayout(left)
        left_w.setFixedWidth(440)
        content.addWidget(left_w)

        # ---- Right: editor ----
        self._editor = QScrollArea()
        self._editor.setWidgetResizable(True)
        self._editor_inner = QWidget()
        self._form = QFormLayout(self._editor_inner)
        self._form.setVerticalSpacing(10)
        self._editor.setWidget(self._editor_inner)
        content.addWidget(self._editor, 1)

        self._build_form()
        self._set_editor_enabled(False)

    # ------------------------------------------------------------------

    def _build_form(self):
        self._editor_status = QLabel()
        set_kind(self._editor_status, "section")
        self._form.addRow(self._editor_status)

        self._name = QLineEdit()

        self._media = QComboBox()
        self._media.addItem("Foto + Ton", "photo")
        self._media.addItem("Video", "video")
        self._media.currentIndexChanged.connect(self._update_field_visibility)

        cfg = self.app.config
        self._image = FileSelectRow(cfg, _IMAGE_EXTS, "Bild")
        self._audio = FileSelectRow(cfg, _AUDIO_EXTS, "Audio")
        self._video = FileSelectRow(cfg, _VIDEO_EXTS, "Video")

        self._form.addRow("Name:", self._name)
        self._lbl_media = QLabel("Medientyp:")
        self._form.addRow(self._lbl_media, self._media)

        add_form_section(self._form, "Medien")
        self._lbl_image = QLabel("Bilddatei (.jpg/.png):")
        self._form.addRow(self._lbl_image, self._image)
        self._lbl_audio = QLabel("Audiodatei (.wav/.mp3/.ogg):")
        self._form.addRow(self._lbl_audio, self._audio)
        self._lbl_video = QLabel("Videodatei (.mp4/.avi/.mov):")
        self._form.addRow(self._lbl_video, self._video)

        self._info = QLabel()
        self._info.setWordWrap(True)
        set_kind(self._info, "hint")
        self._form.addRow(self._info)

        save = QPushButton("Szene speichern")
        set_kind(save, "primary")
        save.clicked.connect(self._save)
        self._form.addRow("", save)

    def _update_field_visibility(self):
        # Video is only available for greeting scenes; collage and print
        # are always image + audio with a fixed configured duration.
        allow_video = self._active_type == "greeting"
        is_photo = not allow_video or self._media.currentData() == "photo"
        for label, row, visible in (
            (self._lbl_media, self._media, allow_video),
            (self._lbl_image, self._image, is_photo),
            (self._lbl_audio, self._audio, is_photo),
            (self._lbl_video, self._video, not is_photo),
        ):
            label.setVisible(visible)
            row.setVisible(visible)
        self._update_info_text()

    def _update_info_text(self):
        d = self.app.config.scene_durations()
        base = "→ Pfad relativ zum Projektordner, z.B. assets/sounds/welcome.mp3."
        if self._active_type == "greeting":
            hint = (f"Die Mediendauer (Audio/Video) muss zwischen "
                    f"{d['greeting_min']:g} und {d['greeting_max']:g} Sekunden "
                    f"liegen (einstellbar unter Einstellungen → Zeiten).")
        else:
            fixed = d[self._active_type]
            hint = (f"Die Szene dauert fest {fixed:g} Sekunden (einstellbar unter "
                    f"Einstellungen → Zeiten). Das Audio spielt einmal bis zum "
                    f"Ende und darf höchstens {fixed:g} Sekunden lang sein.")
        self._info.setText(f"{base}\n{hint}")

    # ------------------------------------------------------------------

    def refresh(self):
        for k, b in self._type_btns.items():
            b.setChecked(k == self._active_type)
        self._reload_list()
        self._editing_id = None
        self._update_field_visibility()
        self._set_editor_enabled(False)

    def _switch_type(self, key: str):
        self._active_type = key
        self.refresh()

    def _reload_list(self):
        self._list.clear()
        for s in self.app.config.get_scenes_by_type(self._active_type):
            mt = "Foto" if s.get("media_type") == "photo" else "Video"
            dur = s.get("duration", 0)
            if self._active_type == "greeting":
                detail = f"{mt}  |  {dur:.1f}s"
            else:
                detail = f"Audio {dur:.1f}s" if dur else "ohne Audio"
            item = QListWidgetItem(f"{s.get('name', '(kein Name)')}  |  {detail}")
            item.setData(Qt.ItemDataRole.UserRole, s["id"])
            self._list.addItem(item)

    # ------------------------------------------------------------------

    def _on_select(self, item: QListWidgetItem):
        scene = self.app.config.get_scene_by_id(item.data(Qt.ItemDataRole.UserRole))
        if scene:
            self._load_into_editor(scene)

    def _new_scene(self):
        self._editing_id = "__new__"
        self._editor_status.setText(
            f"Neue Szene ({_SCENE_LABELS[self._active_type]})")
        self._name.setText("")
        self._media.setCurrentIndex(0)
        self._image.setText("")
        self._audio.setText("")
        self._video.setText("")
        self._update_field_visibility()
        self._set_editor_enabled(True)

    def _load_into_editor(self, scene: dict):
        self._editing_id = scene["id"]
        self._editor_status.setText(
            f"Szene bearbeiten: {scene.get('name', '(kein Name)')}")
        self._name.setText(scene.get("name", ""))
        self._media.setCurrentIndex(0 if scene.get("media_type", "photo") == "photo" else 1)
        self._image.setText(scene.get("image", ""))
        self._audio.setText(scene.get("audio", ""))
        self._video.setText(scene.get("video", ""))
        self._update_field_visibility()
        self._set_editor_enabled(True)

    def _set_editor_enabled(self, on: bool):
        self._editor_inner.setEnabled(on)
        if not on:
            self._editor_status.setText(
                "Szene links auswählen oder „+ Neue Szene“ erstellen")

    # ------------------------------------------------------------------

    def _compute_duration(self, scene_type: str, is_photo: bool,
                          audio: str, video: str) -> float:
        if is_photo:
            if audio:
                dur = AudioPlayer.get_audio_duration(self.app.config.resolve_asset(audio))
                return dur or 0.0
            # Greeting without audio: the screen still has to fill the
            # configured minimum. Collage/print without audio: silence (0s).
            if scene_type == "greeting":
                return self.app.config.scene_duration_limits("greeting")[0]
            return 0.0
        if video:
            dur = AudioPlayer.get_video_duration(self.app.config.resolve_asset(video))
            return dur or 0.0
        return 0.0

    def _save(self):
        scene_type = self._active_type
        is_photo = scene_type != "greeting" or self._media.currentData() == "photo"
        name = self._name.text().strip()
        image, audio = self._image.text(), self._audio.text()
        video = self._video.text() if not is_photo else ""

        if not name:
            self.app.show_notification("Bitte einen Namen eingeben.", level="warning")
            return

        duration = self._compute_duration(scene_type, is_photo, audio, video)
        lo, hi = self.app.config.scene_duration_limits(scene_type)
        if scene_type == "greeting":
            if not lo <= duration <= hi:
                self.app.show_notification(
                    f"Mediendauer {duration:.1f}s liegt außerhalb des erlaubten "
                    f"Bereichs ({lo:g}–{hi:g}s) für Begrüßungsszenen.",
                    duration=8.0, level="error")
                return
        elif duration > hi:
            self.app.show_notification(
                f"Audio ({duration:.1f}s) ist länger als die konfigurierte "
                f"Szenendauer ({hi:g}s). Kürzere Datei wählen oder Dauer unter "
                f"Einstellungen → Zeiten erhöhen.",
                duration=8.0, level="error")
            return

        scene_data = {
            "name": name, "type": scene_type,
            "media_type": "photo" if is_photo else "video",
            "duration": round(duration, 2),
            "image": image, "audio": audio, "video": video,
        }

        if self._editing_id == "__new__":
            self.app.config.add_scene(scene_data)
        else:
            self.app.config.update_scene(self._editing_id, scene_data)

        self.app.show_notification("Szene gespeichert.", duration=3.0, level="info")
        self.refresh()

    def _delete_selected(self):
        item = self._list.currentItem()
        if not item:
            return
        sid = item.data(Qt.ItemDataRole.UserRole)
        deps = self.app.config.paths_using_scene(sid)
        if deps:
            names = ", ".join(p.get("name", p["id"]) for p in deps)
            msg = (f"Szene wird von {len(deps)} Pfad(en) verwendet: {names}. "
                   "Diese Pfade werden ebenfalls gelöscht. Fortfahren?")
        else:
            msg = "Szene wirklich löschen?"
        reply = QMessageBox.question(
            self, "Szene löschen", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.app.config.delete_scene(sid)
            self.refresh()
