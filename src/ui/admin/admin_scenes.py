"""
Admin Scenes tab (PyQt6).
Sub-tab bar (Begrüßung / Collage / Druck), scene list, and an editor form with
file-browse buttons (QFileDialog) and media-format validation.

Scene audio uses VLC → WAV + MP3 + OGG allowed.
Scene video uses VLC → MP4 + AVI + MOV allowed.
Duration is derived from the media file and validated against per-type limits.
"""
from __future__ import annotations
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QFormLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QListWidget, QListWidgetItem, QScrollArea, QMessageBox,
)
from PyQt6.QtCore import Qt

from ...constants import (
    SCENE_GREETING_MIN, SCENE_GREETING_MAX,
    SCENE_COLLAGE_DURATION, SCENE_PRINT_DURATION,
)
from ...audio import AudioPlayer
from .file_dialog import open_file_dialog

_SCENE_TYPES = ["greeting", "collage", "print"]
_SCENE_LABELS = {"greeting": "Begrüßung", "collage": "Collage", "print": "Druck"}
_DURATION_LIMITS = {
    "greeting": (SCENE_GREETING_MIN, SCENE_GREETING_MAX),
    "collage":  (1, SCENE_COLLAGE_DURATION),
    "print":    (1, SCENE_PRINT_DURATION),
}

_AUDIO_EXTS = {".wav", ".mp3", ".ogg"}
_VIDEO_EXTS = {".mp4", ".avi", ".mov"}
_IMAGE_EXTS = {".jpg", ".jpeg", ".png"}

_BTN = (
    "QPushButton { background: #2a2a50; color: white; border: 1px solid #444488; "
    "border-radius: 5px; padding: 8px 14px; } QPushButton:hover { border-color: #ff6600; }"
)
_DEL = (
    "QPushButton { background: #5a2030; color: white; border: 1px solid #884444; "
    "border-radius: 5px; padding: 8px 14px; } QPushButton:hover { border-color: #ff6600; }"
)


class AdminScenes(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self._active_type = "greeting"
        self._editing_id: str | None = None

        root = QHBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(16)

        # ---- Left ----
        left = QVBoxLayout()
        tab_row = QHBoxLayout()
        self._type_btns = {}
        for key in _SCENE_TYPES:
            b = QPushButton(_SCENE_LABELS[key])
            b.setCheckable(True)
            b.setStyleSheet(
                "QPushButton { background: #2a2a50; color: white; border: none; "
                "border-radius: 5px; padding: 8px; } QPushButton:checked { background: #ff6600; }")
            b.clicked.connect(lambda _, k=key: self._switch_type(k))
            tab_row.addWidget(b)
            self._type_btns[key] = b
        left.addLayout(tab_row)

        self._list = QListWidget()
        self._list.itemClicked.connect(self._on_select)
        left.addWidget(self._list, 1)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("+ Neue Szene")
        add_btn.setStyleSheet(_BTN)
        add_btn.clicked.connect(self._new_scene)
        del_btn = QPushButton("Löschen")
        del_btn.setStyleSheet(_DEL)
        del_btn.clicked.connect(self._delete_selected)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(del_btn)
        left.addLayout(btn_row)

        left_w = QWidget()
        left_w.setLayout(left)
        left_w.setFixedWidth(440)
        root.addWidget(left_w)

        # ---- Right: editor ----
        self._editor = QScrollArea()
        self._editor.setWidgetResizable(True)
        self._editor_inner = QWidget()
        self._form = QFormLayout(self._editor_inner)
        self._editor.setWidget(self._editor_inner)
        root.addWidget(self._editor, 1)

        self._build_form()
        self._set_editor_enabled(False)

    # ------------------------------------------------------------------

    def _build_form(self):
        self._name = QLineEdit()

        self._media = QComboBox()
        self._media.addItem("Foto + Ton", "photo")
        self._media.addItem("Video", "video")
        self._media.currentIndexChanged.connect(self._update_field_visibility)

        # Image row
        self._image = QLineEdit()
        img_browse = QPushButton("…")
        img_browse.setStyleSheet(_BTN)
        img_browse.clicked.connect(lambda: self._browse(self._image, _IMAGE_EXTS, "Bild", self._image_warn))
        self._image_warn = QLabel("")
        self._image_warn.setStyleSheet("color: #ff6060;")
        self._image_row = self._make_row(self._image, img_browse)

        # Audio row
        self._audio = QLineEdit()
        aud_browse = QPushButton("…")
        aud_browse.setStyleSheet(_BTN)
        aud_browse.clicked.connect(lambda: self._browse(self._audio, _AUDIO_EXTS, "Audio", self._audio_warn))
        self._audio_warn = QLabel("")
        self._audio_warn.setStyleSheet("color: #ff6060;")
        self._audio_row = self._make_row(self._audio, aud_browse)

        # Video row
        self._video = QLineEdit()
        vid_browse = QPushButton("…")
        vid_browse.setStyleSheet(_BTN)
        vid_browse.clicked.connect(lambda: self._browse(self._video, _VIDEO_EXTS, "Video", self._video_warn))
        self._video_warn = QLabel("")
        self._video_warn.setStyleSheet("color: #ff6060;")
        self._video_row = self._make_row(self._video, vid_browse)

        self._form.addRow("Name:", self._name)
        self._form.addRow("Medientyp:", self._media)
        self._lbl_image = QLabel("Bilddatei (.jpg/.png):")
        self._form.addRow(self._lbl_image, self._image_row)
        self._form.addRow("", self._image_warn)
        self._lbl_audio = QLabel("Audiodatei (.wav/.mp3/.ogg):")
        self._form.addRow(self._lbl_audio, self._audio_row)
        self._form.addRow("", self._audio_warn)
        self._lbl_video = QLabel("Videodatei (.mp4/.avi/.mov):")
        self._form.addRow(self._lbl_video, self._video_row)
        self._form.addRow("", self._video_warn)

        self._info = QLabel("→ Pfad relativ zu Projektordner, z.B. assets/sounds/welcome.mp3.\n"
                            "Dauer wird automatisch aus der Mediendatei berechnet.")
        self._info.setWordWrap(True)
        self._form.addRow(self._info)

        save = QPushButton("Speichern")
        save.setStyleSheet(_BTN)
        save.clicked.connect(self._save)
        self._form.addRow("", save)

    @staticmethod
    def _make_row(line: QLineEdit, browse: QPushButton) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(line, 1)
        lay.addWidget(browse)
        return w

    def _set_row_visible(self, label: QLabel, row: QWidget, warn: QLabel, visible: bool):
        label.setVisible(visible)
        row.setVisible(visible)
        warn.setVisible(visible)

    def _update_field_visibility(self):
        is_photo = self._media.currentData() == "photo"
        self._set_row_visible(self._lbl_image, self._image_row, self._image_warn, is_photo)
        self._set_row_visible(self._lbl_audio, self._audio_row, self._audio_warn, is_photo)
        self._set_row_visible(self._lbl_video, self._video_row, self._video_warn, not is_photo)

    # ------------------------------------------------------------------

    def _browse(self, line: QLineEdit, exts: set, kind: str, warn: QLabel):
        base = str(self.app.config.resolve_asset("assets"))
        sel = open_file_dialog(self, base, f"{kind} auswählen", exts)
        if not sel:
            return
        # Store path relative to project root when possible.
        try:
            rel = Path(sel).resolve().relative_to(
                self.app.config.resolve_asset("").resolve())
            line.setText(str(rel))
        except (ValueError, Exception):
            line.setText(sel)
        self._validate_ext(sel, exts, kind, warn)

    @staticmethod
    def _validate_ext(path: str, exts: set, kind: str, warn: QLabel):
        if path and Path(path).suffix.lower() not in exts:
            allowed = ", ".join(sorted(exts))
            warn.setText(f"Warnung: {kind} sollte eines dieser Formate sein: {allowed}")
        else:
            warn.setText("")

    # ------------------------------------------------------------------

    def refresh(self):
        for k, b in self._type_btns.items():
            b.setChecked(k == self._active_type)
        self._reload_list()
        self._editing_id = None
        self._set_editor_enabled(False)

    def _switch_type(self, key: str):
        self._active_type = key
        self.refresh()

    def _reload_list(self):
        self._list.clear()
        for s in self.app.config.get_scenes_by_type(self._active_type):
            mt = "Foto" if s.get("media_type") == "photo" else "Video"
            dur = s.get("duration", 0)
            item = QListWidgetItem(f"{s.get('name', '(kein Name)')}  |  {mt}  |  {dur:.1f}s")
            item.setData(Qt.ItemDataRole.UserRole, s["id"])
            self._list.addItem(item)

    # ------------------------------------------------------------------

    def _on_select(self, item: QListWidgetItem):
        scene = self.app.config.get_scene_by_id(item.data(Qt.ItemDataRole.UserRole))
        if scene:
            self._load_into_editor(scene)

    def _new_scene(self):
        self._editing_id = "__new__"
        self._name.setText("")
        self._media.setCurrentIndex(0)
        self._image.setText("")
        self._audio.setText("")
        self._video.setText("")
        for warn in (self._image_warn, self._audio_warn, self._video_warn):
            warn.setText("")
        self._update_field_visibility()
        self._set_editor_enabled(True)

    def _load_into_editor(self, scene: dict):
        self._editing_id = scene["id"]
        self._name.setText(scene.get("name", ""))
        self._media.setCurrentIndex(0 if scene.get("media_type", "photo") == "photo" else 1)
        self._image.setText(scene.get("image", ""))
        self._audio.setText(scene.get("audio", ""))
        self._video.setText(scene.get("video", ""))
        self._validate_ext(scene.get("image", ""), _IMAGE_EXTS, "Bild", self._image_warn)
        self._validate_ext(scene.get("audio", ""), _AUDIO_EXTS, "Audio", self._audio_warn)
        self._validate_ext(scene.get("video", ""), _VIDEO_EXTS, "Video", self._video_warn)
        self._update_field_visibility()
        self._set_editor_enabled(True)

    def _set_editor_enabled(self, on: bool):
        self._editor_inner.setEnabled(on)

    # ------------------------------------------------------------------

    def _save(self):
        scene_type = self._active_type
        is_photo = self._media.currentData() == "photo"
        name = self._name.text().strip()
        image = self._image.text().strip()
        audio = self._audio.text().strip()
        video = self._video.text().strip()

        if not name:
            self.app.show_notification("Bitte einen Namen eingeben.", level="warning")
            return

        # Determine duration
        duration = 0.0
        if is_photo:
            if audio:
                p = self.app.config.resolve_asset(audio)
                dur = AudioPlayer.get_mp3_duration(p)
                duration = dur if dur else 0.0
            else:
                duration = _DURATION_LIMITS[scene_type][0]
        else:
            if video:
                p = self.app.config.resolve_asset(video)
                dur = AudioPlayer.get_video_duration(p)
                duration = dur if dur else 0.0

        lo, hi = _DURATION_LIMITS[scene_type]
        if duration < lo or duration > hi:
            self.app.show_notification(
                f"Dauer {duration:.1f}s liegt außerhalb des erlaubten Bereichs "
                f"({lo}–{hi}s) für diesen Szenentyp.",
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
            scene_data["id"] = self._editing_id
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
        reply = QMessageBox.question(self, "Szene löschen", msg,
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.app.config.delete_scene(sid)
            self.refresh()
